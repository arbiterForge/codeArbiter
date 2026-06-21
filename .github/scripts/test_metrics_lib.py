#!/usr/bin/env python3
"""codeArbiter — unit tests for the window-tiling foundation (_metricslib, T-01).

Proves the pure window-tiling logic (AC-01): correct commit-count windows,
timestamp-to-window mapping, boundary semantics, and edge values. The git
wrapper (commit_timeline) is NOT tested here — only the pure functions are
exercised with synthetic commit lists, keeping git out of the test suite.

Test class: WindowTest (select with: python .github/scripts/test_metrics_lib.py WindowTest)
Stdlib only. Exit 0 = all tests pass; non-zero = failure.
"""

import sys
import os
import unittest
from datetime import datetime, timezone, timedelta

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(os.path.dirname(HERE))
HOOKS = os.path.join(REPO, "plugins", "ca", "hooks")
sys.path.insert(0, HOOKS)

import _metricslib  # noqa: E402 — needs sys.path mutation above


# ---------------------------------------------------------------------------
# helpers
# ---------------------------------------------------------------------------

def _utc(year, month, day, hour=0, minute=0, second=0):
    """Produce a timezone-aware UTC datetime for test fixtures."""
    return datetime(year, month, day, hour, minute, second, tzinfo=timezone.utc)


def _make_timeline(n, start=None, step_days=1):
    """Return a list of n timezone-aware UTC datetimes, oldest first,
    spaced `step_days` days apart from `start` (default 2020-01-01)."""
    if start is None:
        start = _utc(2020, 1, 1)
    return [start + timedelta(days=i * step_days) for i in range(n)]


class WindowTest(unittest.TestCase):
    """AC-01: window-tiling pure functions."""

    # ------------------------------------------------------------------
    # tile_windows: basic window production
    # ------------------------------------------------------------------

    def test_60_commits_n20_yields_3_windows(self):
        """60 commits / N=20 produces exactly 3 windows indexed 0, 1, 2."""
        timeline = _make_timeline(60)
        windows = _metricslib.tile_windows(timeline, window_size=20)
        self.assertEqual(len(windows), 3)

    def test_60_commits_window_indices_are_0_1_2(self):
        """Windows are indexed 0 (oldest) through 2 (most recent / current)."""
        timeline = _make_timeline(60)
        windows = _metricslib.tile_windows(timeline, window_size=20)
        indices = [w.index for w in windows]
        self.assertEqual(indices, [0, 1, 2])

    def test_most_recent_window_is_highest_index(self):
        """The highest-index window covers the newest commits."""
        timeline = _make_timeline(60)
        windows = _metricslib.tile_windows(timeline, window_size=20)
        newest_window = windows[-1]
        self.assertEqual(newest_window.index, 2)
        # Its last commit must be the very last commit in the timeline.
        self.assertEqual(newest_window.end_dt, timeline[-1])

    def test_window_boundaries_cover_all_commits(self):
        """Each commit falls into exactly one window's [start_dt, end_dt] span."""
        timeline = _make_timeline(60)
        windows = _metricslib.tile_windows(timeline, window_size=20)
        # Window i covers commits [i*20, (i+1)*20 - 1].
        self.assertEqual(windows[0].start_dt, timeline[0])
        self.assertEqual(windows[0].end_dt, timeline[19])
        self.assertEqual(windows[1].start_dt, timeline[20])
        self.assertEqual(windows[1].end_dt, timeline[39])
        self.assertEqual(windows[2].start_dt, timeline[40])
        self.assertEqual(windows[2].end_dt, timeline[59])

    def test_default_window_size_is_20(self):
        """tile_windows defaults to window_size=20 when not supplied."""
        timeline = _make_timeline(40)
        windows = _metricslib.tile_windows(timeline)
        self.assertEqual(len(windows), 2)

    # ------------------------------------------------------------------
    # tile_windows: partial window (non-divisible M)
    # ------------------------------------------------------------------

    def test_partial_window_is_oldest_when_not_divisible(self):
        """With 45 commits and N=20, the oldest window (index 0) is partial
        (5 commits); windows 1 and 2 are full (20 commits each).
        The newest two windows are always full; the partial group is oldest."""
        timeline = _make_timeline(45)
        windows = _metricslib.tile_windows(timeline, window_size=20)
        # 45 = 5 (partial oldest) + 20 + 20 => 3 windows
        self.assertEqual(len(windows), 3)
        # oldest window has 5 commits (the partial group)
        w0 = windows[0]
        self.assertEqual(w0.start_dt, timeline[0])
        self.assertEqual(w0.end_dt, timeline[4])
        # middle window is full
        w1 = windows[1]
        self.assertEqual(w1.start_dt, timeline[5])
        self.assertEqual(w1.end_dt, timeline[24])
        # newest window is full
        w2 = windows[2]
        self.assertEqual(w2.start_dt, timeline[25])
        self.assertEqual(w2.end_dt, timeline[44])

    def test_fewer_than_window_size_commits_is_one_window(self):
        """With M < N, there is exactly one window (index 0) that is partial."""
        timeline = _make_timeline(7)
        windows = _metricslib.tile_windows(timeline, window_size=20)
        self.assertEqual(len(windows), 1)
        self.assertEqual(windows[0].index, 0)
        self.assertEqual(windows[0].start_dt, timeline[0])
        self.assertEqual(windows[0].end_dt, timeline[6])

    def test_empty_timeline_yields_no_windows(self):
        """An empty commit list produces an empty window list, not a crash."""
        windows = _metricslib.tile_windows([], window_size=20)
        self.assertEqual(windows, [])

    def test_exactly_one_commit_is_one_window(self):
        """A single-commit timeline produces one window covering that commit."""
        timeline = _make_timeline(1)
        windows = _metricslib.tile_windows(timeline, window_size=20)
        self.assertEqual(len(windows), 1)
        self.assertEqual(windows[0].start_dt, timeline[0])
        self.assertEqual(windows[0].end_dt, timeline[0])

    # ------------------------------------------------------------------
    # map_to_window: timestamp → window index
    # ------------------------------------------------------------------

    def test_timestamp_inside_window_maps_correctly(self):
        """A timestamp in the middle of window 1's date span maps to index 1."""
        timeline = _make_timeline(60)
        windows = _metricslib.tile_windows(timeline, window_size=20)
        # Middle of window 1 (commits 20–39): pick commit 29's date
        ts = timeline[29]
        idx = _metricslib.map_to_window(ts, windows)
        self.assertEqual(idx, 1)

    def test_timestamp_at_window_start_maps_to_that_window(self):
        """A timestamp equal to a window's start_dt maps to that window's index."""
        timeline = _make_timeline(60)
        windows = _metricslib.tile_windows(timeline, window_size=20)
        # timeline[20] is the start of window 1
        ts = timeline[20]
        idx = _metricslib.map_to_window(ts, windows)
        self.assertEqual(idx, 1)

    def test_timestamp_at_boundary_maps_to_higher_index_window(self):
        """A timestamp exactly equal to a window-boundary commit date maps to the
        higher-index (more recent) window, not the lower-index one that ends there.

        With windows [0: t0..t19], [1: t20..t39], [2: t40..t59]:
        timeline[39] is end_dt of window 1 AND start_dt of window 2 in
        the half-open [start, end) sense — it must map to window 2 (index 2).
        """
        timeline = _make_timeline(60)
        windows = _metricslib.tile_windows(timeline, window_size=20)
        # timeline[40] is start of window 2; timeline[39] is end of window 1.
        # The boundary in question is timeline[40]: it should map to window 2.
        boundary_ts = windows[2].start_dt
        idx = _metricslib.map_to_window(boundary_ts, windows)
        self.assertEqual(idx, 2, "boundary commit date must map to the more-recent window")

    def test_timestamp_newer_than_newest_commit_maps_to_last_window(self):
        """A timestamp newer than the last commit maps to the most-recent window."""
        timeline = _make_timeline(60)
        windows = _metricslib.tile_windows(timeline, window_size=20)
        future_ts = timeline[-1] + timedelta(days=365)
        idx = _metricslib.map_to_window(future_ts, windows)
        self.assertEqual(idx, 2)

    def test_timestamp_older_than_oldest_commit_maps_to_sentinel(self):
        """A timestamp older than the oldest commit returns BEFORE_HISTORY sentinel
        (a defined value, not a crash)."""
        timeline = _make_timeline(60)
        windows = _metricslib.tile_windows(timeline, window_size=20)
        ancient_ts = timeline[0] - timedelta(days=365)
        idx = _metricslib.map_to_window(ancient_ts, windows)
        self.assertEqual(idx, _metricslib.BEFORE_HISTORY)

    def test_map_to_window_accepts_iso8601_z_string(self):
        """map_to_window accepts an ISO-8601 string with trailing Z (log format)."""
        timeline = _make_timeline(60)
        windows = _metricslib.tile_windows(timeline, window_size=20)
        # Pick a timestamp inside window 0 and encode it as a Z-string.
        ts_dt = timeline[5]
        ts_str = ts_dt.strftime("%Y-%m-%dT%H:%M:%SZ")
        idx = _metricslib.map_to_window(ts_str, windows)
        self.assertEqual(idx, 0)

    def test_map_to_window_empty_windows_returns_sentinel(self):
        """map_to_window with an empty window list returns BEFORE_HISTORY, not crash."""
        idx = _metricslib.map_to_window(_utc(2024, 1, 1), [])
        self.assertEqual(idx, _metricslib.BEFORE_HISTORY)

    # ------------------------------------------------------------------
    # tile_windows: ISO-8601 string input
    # ------------------------------------------------------------------

    def test_tile_windows_accepts_iso8601_z_strings(self):
        """tile_windows accepts a list of ISO-8601 Z strings (as the log emits)."""
        base = _utc(2026, 1, 1)
        strs = [(base + timedelta(days=i)).strftime("%Y-%m-%dT%H:%M:%SZ")
                for i in range(40)]
        windows = _metricslib.tile_windows(strs, window_size=20)
        self.assertEqual(len(windows), 2)

    # ------------------------------------------------------------------
    # sentinel constant
    # ------------------------------------------------------------------

    def test_before_history_sentinel_is_negative(self):
        """BEFORE_HISTORY sentinel is a negative integer (clearly not a valid index)."""
        self.assertIsInstance(_metricslib.BEFORE_HISTORY, int)
        self.assertLess(_metricslib.BEFORE_HISTORY, 0)


# ---------------------------------------------------------------------------
# OverrideRateTest — T-02: override-rate metric (AC-02)
# ---------------------------------------------------------------------------

class OverrideRateTest(unittest.TestCase):
    """AC-02: override-rate pure function — counts overrides.log entries per window."""

    # Shared window setup: 60 synthetic commits producing 3 windows (N=20).
    # window 0: commits 0–19   (oldest)
    # window 1: commits 20–39  (prior)
    # window 2: commits 40–59  (current)
    _TIMELINE_START = _utc(2026, 1, 1)

    def _make_windows(self):
        """Return a 3-window list using a 60-commit timeline, N=20."""
        timeline = _make_timeline(60, start=self._TIMELINE_START, step_days=1)
        return _metricslib.tile_windows(timeline, window_size=20)

    def _ts_in_window(self, windows, window_index, offset_hours=1):
        """Return an ISO-8601 Z string for a timestamp strictly inside `window_index`."""
        band = windows[window_index]
        # Use start_dt + offset to land well inside the band.
        dt = band.start_dt + timedelta(hours=offset_hours)
        return dt.strftime("%Y-%m-%dT%H:%M:%SZ")

    def _make_log_line(self, ts_str, hook="H-02", actor="user@example.com"):
        """Return a synthetic overrides.log non-comment line."""
        return (
            f"[{ts_str}] | BY: {actor} | "
            f"OVERRIDE: {hook} force-push | REASON: test"
        )

    # ------------------------------------------------------------------
    # Happy path: current > prior  (arrow "↑")
    # ------------------------------------------------------------------

    def test_current_greater_than_prior_arrow_up(self):
        """C=3 in current window, P=1 in prior window -> current==3, prior==1, arrow='↑'."""
        windows = self._make_windows()
        current_idx = len(windows) - 1
        prior_idx = current_idx - 1

        lines = []
        # 3 entries in the current window
        for _ in range(3):
            lines.append(self._make_log_line(self._ts_in_window(windows, current_idx)))
        # 1 entry in the prior window
        lines.append(self._make_log_line(self._ts_in_window(windows, prior_idx)))

        result = _metricslib.override_rate(lines, windows)
        self.assertEqual(result["current"], 3)
        self.assertEqual(result["prior"], 1)
        self.assertEqual(result["arrow"], "↑")

    # ------------------------------------------------------------------
    # Happy path: current < prior  (arrow "↓")
    # ------------------------------------------------------------------

    def test_current_less_than_prior_arrow_down(self):
        """C=1 in current window, P=4 in prior window -> arrow='↓'."""
        windows = self._make_windows()
        current_idx = len(windows) - 1
        prior_idx = current_idx - 1

        lines = []
        lines.append(self._make_log_line(self._ts_in_window(windows, current_idx)))
        for _ in range(4):
            lines.append(self._make_log_line(self._ts_in_window(windows, prior_idx)))

        result = _metricslib.override_rate(lines, windows)
        self.assertEqual(result["current"], 1)
        self.assertEqual(result["prior"], 4)
        self.assertEqual(result["arrow"], "↓")

    # ------------------------------------------------------------------
    # Happy path: current == prior  (arrow "→")
    # ------------------------------------------------------------------

    def test_current_equal_prior_arrow_flat(self):
        """C=2 in current window, P=2 in prior window -> arrow='→'."""
        windows = self._make_windows()
        current_idx = len(windows) - 1
        prior_idx = current_idx - 1

        lines = []
        for _ in range(2):
            lines.append(self._make_log_line(self._ts_in_window(windows, current_idx)))
        for _ in range(2):
            lines.append(self._make_log_line(self._ts_in_window(windows, prior_idx)))

        result = _metricslib.override_rate(lines, windows)
        self.assertEqual(result["current"], 2)
        self.assertEqual(result["prior"], 2)
        self.assertEqual(result["arrow"], "→")

    # ------------------------------------------------------------------
    # Comment lines and blank lines are excluded
    # ------------------------------------------------------------------

    def test_comment_lines_excluded(self):
        """Lines starting with '#' must not be counted, even if they contain a timestamp."""
        windows = self._make_windows()
        current_idx = len(windows) - 1

        ts_str = self._ts_in_window(windows, current_idx)
        # One real entry and two comment lines that look like entries.
        lines = [
            self._make_log_line(ts_str),
            f"# [{ts_str}] | BY: actor | OVERRIDE: H-02 | REASON: comment",
            "# another comment",
        ]
        result = _metricslib.override_rate(lines, windows)
        self.assertEqual(result["current"], 1, "comment lines must not be counted")

    def test_blank_lines_excluded(self):
        """Blank lines (and whitespace-only lines) must not cause errors or counts."""
        windows = self._make_windows()
        current_idx = len(windows) - 1

        ts_str = self._ts_in_window(windows, current_idx)
        lines = [
            "",
            "   ",
            self._make_log_line(ts_str),
            "",
        ]
        result = _metricslib.override_rate(lines, windows)
        self.assertEqual(result["current"], 1)

    # ------------------------------------------------------------------
    # Entries that map to BEFORE_HISTORY are not counted
    # ------------------------------------------------------------------

    def test_before_history_entries_not_counted(self):
        """An entry timestamped before the first window must not appear in any count."""
        windows = self._make_windows()
        current_idx = len(windows) - 1

        # A timestamp 1 year before the oldest window start
        ancient_dt = windows[0].start_dt - timedelta(days=365)
        ancient_str = ancient_dt.strftime("%Y-%m-%dT%H:%M:%SZ")

        lines = [
            self._make_log_line(ancient_str),
            self._make_log_line(self._ts_in_window(windows, current_idx)),
        ]
        result = _metricslib.override_rate(lines, windows)
        self.assertEqual(result["current"], 1, "ancient entry must not be counted")
        self.assertEqual(result["prior"], 0)

    # ------------------------------------------------------------------
    # Fewer than 2 windows: prior == 0, arrow compares against 0
    # ------------------------------------------------------------------

    def test_single_window_prior_is_zero(self):
        """With only 1 window, prior==0 and arrow reflects current vs 0."""
        # 7 commits => 1 window (N=20)
        timeline = _make_timeline(7, start=self._TIMELINE_START, step_days=1)
        windows = _metricslib.tile_windows(timeline, window_size=20)
        self.assertEqual(len(windows), 1)

        ts_str = self._ts_in_window(windows, 0)
        lines = [self._make_log_line(ts_str), self._make_log_line(ts_str)]
        result = _metricslib.override_rate(lines, windows)
        self.assertEqual(result["prior"], 0)
        self.assertEqual(result["current"], 2)
        self.assertEqual(result["arrow"], "↑")  # 2 > 0

    def test_single_window_zero_entries_arrow_flat(self):
        """With 1 window and zero entries in it, current==0, prior==0, arrow='→'."""
        timeline = _make_timeline(7, start=self._TIMELINE_START, step_days=1)
        windows = _metricslib.tile_windows(timeline, window_size=20)

        result = _metricslib.override_rate([], windows)
        self.assertEqual(result["current"], 0)
        self.assertEqual(result["prior"], 0)
        self.assertEqual(result["arrow"], "→")

    def test_empty_windows_returns_zeros(self):
        """With an empty windows list, both counts are 0 and arrow is '→'."""
        result = _metricslib.override_rate([], [])
        self.assertEqual(result["current"], 0)
        self.assertEqual(result["prior"], 0)
        self.assertEqual(result["arrow"], "→")

    # ------------------------------------------------------------------
    # Text-block input (accepts str with newlines, not just list)
    # ------------------------------------------------------------------

    def test_accepts_text_block(self):
        """override_rate may accept a single multi-line string as well as a list."""
        windows = self._make_windows()
        current_idx = len(windows) - 1
        ts_str = self._ts_in_window(windows, current_idx)

        text = "\n".join([
            "# header comment",
            self._make_log_line(ts_str),
            "",
            self._make_log_line(ts_str),
        ])
        result = _metricslib.override_rate(text, windows)
        self.assertEqual(result["current"], 2)


# ---------------------------------------------------------------------------
# SmallLaneTest — T-03: small-lane-rate metric (AC-03)
# ---------------------------------------------------------------------------

class SmallLaneTest(unittest.TestCase):
    """AC-03: small_lane_rate pure function — counts LANE: small entries in
    triage.log per window.

    Line format (non-comment):
        [<ISO-8601 Z timestamp>] | BY: <actor> | LANE: small | SCOPE: ... | BASIS: ...

    Only lines containing 'LANE: small' are counted.  'LANE: full' and any other
    lane value must NOT be counted.  Comment (#) and blank lines are excluded.
    Entries mapping to BEFORE_HISTORY are excluded.
    """

    _TIMELINE_START = _utc(2026, 1, 1)

    def _make_windows(self):
        """Return a 3-window list using a 60-commit timeline, N=20.
        window 0: oldest  (prior's prior)
        window 1: prior
        window 2: current
        """
        timeline = _make_timeline(60, start=self._TIMELINE_START, step_days=1)
        return _metricslib.tile_windows(timeline, window_size=20)

    def _ts_in_window(self, windows, window_index, offset_hours=1):
        """Return an ISO-8601 Z string for a timestamp strictly inside `window_index`."""
        band = windows[window_index]
        dt = band.start_dt + timedelta(hours=offset_hours)
        return dt.strftime("%Y-%m-%dT%H:%M:%SZ")

    def _make_small_lane_line(self, ts_str, actor="tester@example.com"):
        """Return a synthetic triage.log line with LANE: small."""
        return (
            f"[{ts_str}] | BY: {actor} | LANE: small | "
            f"SCOPE: commit-quality | BASIS: short fix"
        )

    def _make_full_lane_line(self, ts_str, actor="tester@example.com"):
        """Return a synthetic triage.log line with LANE: full (must NOT be counted)."""
        return (
            f"[{ts_str}] | BY: {actor} | LANE: full | "
            f"SCOPE: broad-refactor | BASIS: large change"
        )

    # ------------------------------------------------------------------
    # Happy path: current > prior  (arrow "↑")
    # ------------------------------------------------------------------

    def test_current_greater_than_prior_arrow_up(self):
        """3 LANE: small in current, 1 in prior -> current==3, prior==1, arrow='↑'."""
        windows = self._make_windows()
        current_idx = len(windows) - 1
        prior_idx = current_idx - 1

        lines = []
        for _ in range(3):
            lines.append(self._make_small_lane_line(self._ts_in_window(windows, current_idx)))
        lines.append(self._make_small_lane_line(self._ts_in_window(windows, prior_idx)))

        result = _metricslib.small_lane_rate(lines, windows)
        self.assertEqual(result["current"], 3)
        self.assertEqual(result["prior"], 1)
        self.assertEqual(result["arrow"], "↑")

    # ------------------------------------------------------------------
    # Happy path: current < prior  (arrow "↓")
    # ------------------------------------------------------------------

    def test_current_less_than_prior_arrow_down(self):
        """1 LANE: small in current, 4 in prior -> arrow='↓'."""
        windows = self._make_windows()
        current_idx = len(windows) - 1
        prior_idx = current_idx - 1

        lines = []
        lines.append(self._make_small_lane_line(self._ts_in_window(windows, current_idx)))
        for _ in range(4):
            lines.append(self._make_small_lane_line(self._ts_in_window(windows, prior_idx)))

        result = _metricslib.small_lane_rate(lines, windows)
        self.assertEqual(result["current"], 1)
        self.assertEqual(result["prior"], 4)
        self.assertEqual(result["arrow"], "↓")

    # ------------------------------------------------------------------
    # Happy path: current == prior  (arrow "→")
    # ------------------------------------------------------------------

    def test_current_equal_prior_arrow_flat(self):
        """2 LANE: small in current, 2 in prior -> arrow='→'."""
        windows = self._make_windows()
        current_idx = len(windows) - 1
        prior_idx = current_idx - 1

        lines = []
        for _ in range(2):
            lines.append(self._make_small_lane_line(self._ts_in_window(windows, current_idx)))
        for _ in range(2):
            lines.append(self._make_small_lane_line(self._ts_in_window(windows, prior_idx)))

        result = _metricslib.small_lane_rate(lines, windows)
        self.assertEqual(result["current"], 2)
        self.assertEqual(result["prior"], 2)
        self.assertEqual(result["arrow"], "→")

    # ------------------------------------------------------------------
    # Comment lines are excluded
    # ------------------------------------------------------------------

    def test_comment_lines_excluded(self):
        """Lines starting with '#' must not be counted."""
        windows = self._make_windows()
        current_idx = len(windows) - 1

        ts_str = self._ts_in_window(windows, current_idx)
        lines = [
            self._make_small_lane_line(ts_str),
            f"# [{ts_str}] | BY: actor | LANE: small | SCOPE: x | BASIS: y",
            "# just a comment",
        ]
        result = _metricslib.small_lane_rate(lines, windows)
        self.assertEqual(result["current"], 1, "comment lines must not be counted")

    # ------------------------------------------------------------------
    # LANE: full must NOT be counted
    # ------------------------------------------------------------------

    def test_full_lane_not_counted(self):
        """A LANE: full line must not contribute to the small-lane count."""
        windows = self._make_windows()
        current_idx = len(windows) - 1

        ts_str = self._ts_in_window(windows, current_idx)
        lines = [
            self._make_small_lane_line(ts_str),   # counted
            self._make_full_lane_line(ts_str),     # NOT counted
        ]
        result = _metricslib.small_lane_rate(lines, windows)
        self.assertEqual(result["current"], 1, "LANE: full must not be counted")

    # ------------------------------------------------------------------
    # Blank lines are excluded
    # ------------------------------------------------------------------

    def test_blank_lines_excluded(self):
        """Blank and whitespace-only lines must not cause errors or counts."""
        windows = self._make_windows()
        current_idx = len(windows) - 1

        ts_str = self._ts_in_window(windows, current_idx)
        lines = [
            "",
            "   ",
            self._make_small_lane_line(ts_str),
            "",
        ]
        result = _metricslib.small_lane_rate(lines, windows)
        self.assertEqual(result["current"], 1)

    # ------------------------------------------------------------------
    # Entries mapping to BEFORE_HISTORY are excluded
    # ------------------------------------------------------------------

    def test_before_history_entries_not_counted(self):
        """An entry timestamped before the first window must not appear in any count."""
        windows = self._make_windows()
        current_idx = len(windows) - 1

        ancient_dt = windows[0].start_dt - timedelta(days=365)
        ancient_str = ancient_dt.strftime("%Y-%m-%dT%H:%M:%SZ")

        lines = [
            self._make_small_lane_line(ancient_str),
            self._make_small_lane_line(self._ts_in_window(windows, current_idx)),
        ]
        result = _metricslib.small_lane_rate(lines, windows)
        self.assertEqual(result["current"], 1, "ancient entry must not be counted")
        self.assertEqual(result["prior"], 0)

    # ------------------------------------------------------------------
    # Fewer than 2 windows: prior == 0
    # ------------------------------------------------------------------

    def test_single_window_prior_is_zero(self):
        """With only 1 window, prior==0 and arrow reflects current vs 0."""
        timeline = _make_timeline(7, start=self._TIMELINE_START, step_days=1)
        windows = _metricslib.tile_windows(timeline, window_size=20)
        self.assertEqual(len(windows), 1)

        ts_str = self._ts_in_window(windows, 0)
        lines = [self._make_small_lane_line(ts_str), self._make_small_lane_line(ts_str)]
        result = _metricslib.small_lane_rate(lines, windows)
        self.assertEqual(result["prior"], 0)
        self.assertEqual(result["current"], 2)
        self.assertEqual(result["arrow"], "↑")  # 2 > 0

    def test_single_window_zero_entries_arrow_flat(self):
        """With 1 window and no entries, current==0, prior==0, arrow='→'."""
        timeline = _make_timeline(7, start=self._TIMELINE_START, step_days=1)
        windows = _metricslib.tile_windows(timeline, window_size=20)

        result = _metricslib.small_lane_rate([], windows)
        self.assertEqual(result["current"], 0)
        self.assertEqual(result["prior"], 0)
        self.assertEqual(result["arrow"], "→")

    def test_empty_windows_returns_zeros(self):
        """With an empty windows list, both counts are 0 and arrow is '→'."""
        result = _metricslib.small_lane_rate([], [])
        self.assertEqual(result["current"], 0)
        self.assertEqual(result["prior"], 0)
        self.assertEqual(result["arrow"], "→")

    # ------------------------------------------------------------------
    # Text-block input accepted
    # ------------------------------------------------------------------

    def test_accepts_text_block(self):
        """small_lane_rate may accept a single multi-line string as well as a list."""
        windows = self._make_windows()
        current_idx = len(windows) - 1
        ts_str = self._ts_in_window(windows, current_idx)

        text = "\n".join([
            "# header comment",
            self._make_small_lane_line(ts_str),
            "",
            self._make_small_lane_line(ts_str),
        ])
        result = _metricslib.small_lane_rate(text, windows)
        self.assertEqual(result["current"], 2)


# ---------------------------------------------------------------------------
# SprintRatioTest — T-04: sprint low-confidence ratio (AC-04)
# ---------------------------------------------------------------------------

class SprintRatioTest(unittest.TestCase):
    """AC-04: sprint_low_confidence_ratio pure function.

    Counts the literal bold tokens **high** and **low** (case-sensitive) in
    sprint-log.md text, per window (by sprint-header date), and returns:
        current = round(L/(L+H), 2)  for the current (highest-index) window,
                  or "n/a" when L+H == 0
        prior   = same for the prior window (current - 1),
                  or "n/a" when no prior window or L+H == 0
        arrow   = "↑"/"↓"/"→" comparing current to prior;
                  "→" when EITHER value is the "n/a" sentinel

    Parsing rules:
        - Bold tokens **high** and **low** are counted; all other bold tokens
          (including **strong**, **moderate**, **weak**) are excluded.
        - Each sprint section is introduced by a header matching:
              # Sprint[^\\n]* · <YYYY-MM-DD>
          The date is parsed as midnight UTC and mapped to a window via
          map_to_window.
        - Markers without a parseable sprint date are excluded (not counted).
        - A **medium** token, if present, is neither high nor low and is
          excluded from the ratio denominator.
    """

    _TIMELINE_START = _utc(2026, 1, 1)

    def _make_windows(self):
        """Return a 3-window list using a 60-commit timeline, N=20.

        window 0: commits 0-19   (oldest, ~2026-01-01 to 2026-01-20)
        window 1: commits 20-39  (prior,  ~2026-01-21 to 2026-02-09)
        window 2: commits 40-59  (current,~2026-02-10 to 2026-03-01)
        """
        timeline = _make_timeline(60, start=self._TIMELINE_START, step_days=1)
        return _metricslib.tile_windows(timeline, window_size=20)

    def _date_in_window(self, windows, window_index):
        """Return a YYYY-MM-DD string for a date inside the given window."""
        band = windows[window_index]
        dt = band.start_dt + timedelta(hours=12)  # noon on start day
        return dt.strftime("%Y-%m-%d")

    # ------------------------------------------------------------------
    # Happy path: ratio computed correctly (H and L in current window)
    # ------------------------------------------------------------------

    def test_ratio_computed_from_high_and_low_counts(self):
        """With 1 high and 3 low in current window, ratio = round(3/4, 2) = 0.75."""
        windows = self._make_windows()
        date_cur = self._date_in_window(windows, 2)

        text = (
            f"# Sprint — alpha · {date_cur}\n"
            "- Decision. **high**.\n"
            "- Decision. **low**.\n"
            "- Decision. **low**.\n"
            "- Decision. **low**.\n"
        )
        result = _metricslib.sprint_low_confidence_ratio(text, windows)
        self.assertEqual(result["current"], round(3 / 4, 2))

    def test_ratio_all_high_is_zero(self):
        """All-high window yields current == 0.0 (zero low markers)."""
        windows = self._make_windows()
        date_cur = self._date_in_window(windows, 2)

        text = (
            f"# Sprint — beta · {date_cur}\n"
            "- Decision. **high**.\n"
            "- Decision. **high**.\n"
        )
        result = _metricslib.sprint_low_confidence_ratio(text, windows)
        self.assertEqual(result["current"], 0.0)

    def test_ratio_all_low_is_one(self):
        """All-low window yields current == 1.0."""
        windows = self._make_windows()
        date_cur = self._date_in_window(windows, 2)

        text = (
            f"# Sprint — gamma · {date_cur}\n"
            "- Decision. **low**.\n"
            "- Decision. **low**.\n"
        )
        result = _metricslib.sprint_low_confidence_ratio(text, windows)
        self.assertEqual(result["current"], 1.0)

    # ------------------------------------------------------------------
    # n/a sentinel: L+H == 0 in a window
    # ------------------------------------------------------------------

    def test_empty_current_window_is_na(self):
        """A current window with zero **high**/**low** markers returns "n/a"."""
        windows = self._make_windows()
        # No sprint sections with dates in the current window.
        text = "# Some other header\nNo confidence markers here.\n"
        result = _metricslib.sprint_low_confidence_ratio(text, windows)
        self.assertEqual(result["current"], "n/a")

    def test_empty_prior_window_is_na(self):
        """A prior window with zero markers returns "n/a" for prior."""
        windows = self._make_windows()
        date_cur = self._date_in_window(windows, 2)
        # Only put content in the current window; prior window stays empty.
        text = (
            f"# Sprint — delta · {date_cur}\n"
            "- Decision. **high**.\n"
        )
        result = _metricslib.sprint_low_confidence_ratio(text, windows)
        self.assertEqual(result["prior"], "n/a")

    # ------------------------------------------------------------------
    # Arrow comparisons
    # ------------------------------------------------------------------

    def test_arrow_up_when_current_greater_than_prior(self):
        """current ratio > prior ratio -> arrow == '↑'."""
        windows = self._make_windows()
        date_cur = self._date_in_window(windows, 2)
        date_pri = self._date_in_window(windows, 1)

        # current: 3 low / 1 high = 0.75
        # prior:   1 low / 3 high = 0.25
        text = (
            f"# Sprint — epsilon · {date_pri}\n"
            "- **high**. **high**. **high**. **low**.\n"
            f"# Sprint — zeta · {date_cur}\n"
            "- **low**. **low**. **low**. **high**.\n"
        )
        result = _metricslib.sprint_low_confidence_ratio(text, windows)
        self.assertGreater(result["current"], result["prior"])
        self.assertEqual(result["arrow"], "↑")

    def test_arrow_down_when_current_less_than_prior(self):
        """current ratio < prior ratio -> arrow == '↓'."""
        windows = self._make_windows()
        date_cur = self._date_in_window(windows, 2)
        date_pri = self._date_in_window(windows, 1)

        # current: 0 low / 2 high = 0.0
        # prior:   2 low / 0 high = 1.0
        text = (
            f"# Sprint — eta · {date_pri}\n"
            "- **low**. **low**.\n"
            f"# Sprint — theta · {date_cur}\n"
            "- **high**. **high**.\n"
        )
        result = _metricslib.sprint_low_confidence_ratio(text, windows)
        self.assertLess(result["current"], result["prior"])
        self.assertEqual(result["arrow"], "↓")

    def test_arrow_flat_when_current_equals_prior(self):
        """current ratio == prior ratio -> arrow == '→'."""
        windows = self._make_windows()
        date_cur = self._date_in_window(windows, 2)
        date_pri = self._date_in_window(windows, 1)

        # both: 1 low / 1 high = 0.5
        text = (
            f"# Sprint — iota · {date_pri}\n"
            "- **low**. **high**.\n"
            f"# Sprint — kappa · {date_cur}\n"
            "- **low**. **high**.\n"
        )
        result = _metricslib.sprint_low_confidence_ratio(text, windows)
        self.assertEqual(result["current"], result["prior"])
        self.assertEqual(result["arrow"], "→")

    def test_arrow_flat_when_current_is_na(self):
        """When current is "n/a", arrow must be "→" (no spurious comparison)."""
        windows = self._make_windows()
        date_pri = self._date_in_window(windows, 1)

        text = (
            f"# Sprint — lambda · {date_pri}\n"
            "- **low**. **high**.\n"
            # No section in current window.
        )
        result = _metricslib.sprint_low_confidence_ratio(text, windows)
        self.assertEqual(result["current"], "n/a")
        self.assertEqual(result["arrow"], "→")

    def test_arrow_flat_when_prior_is_na(self):
        """When prior is "n/a", arrow must be "→" (no spurious comparison)."""
        windows = self._make_windows()
        date_cur = self._date_in_window(windows, 2)

        text = (
            f"# Sprint — mu · {date_cur}\n"
            "- **low**. **high**.\n"
            # No section in prior window.
        )
        result = _metricslib.sprint_low_confidence_ratio(text, windows)
        self.assertEqual(result["prior"], "n/a")
        self.assertEqual(result["arrow"], "→")

    # ------------------------------------------------------------------
    # Disambiguation: strength words must NOT be counted
    # ------------------------------------------------------------------

    def test_strength_words_not_counted(self):
        """**strong**, **moderate**, **weak** must NOT be counted as high or low."""
        windows = self._make_windows()
        date_cur = self._date_in_window(windows, 2)

        # Only strength words bolded — no **high** or **low** present.
        text = (
            f"# Sprint — nu · {date_cur}\n"
            "- Decision. **strong**.\n"
            "- Decision. **moderate**.\n"
            "- Decision. **weak**.\n"
            "- Other bold: **D-01**, **Point:**, **Chosen:**.\n"
        )
        result = _metricslib.sprint_low_confidence_ratio(text, windows)
        self.assertEqual(result["current"], "n/a",
                         "strength words must not be counted as high/low")

    def test_medium_not_counted_in_denominator(self):
        """**medium**, if present, is excluded from the L+H denominator."""
        windows = self._make_windows()
        date_cur = self._date_in_window(windows, 2)

        # 1 high + 1 medium; medium excluded, so denominator = 1 (just the high)
        text = (
            f"# Sprint — xi · {date_cur}\n"
            "- Decision A. **high**.\n"
            "- Decision B. **medium**.\n"
        )
        result = _metricslib.sprint_low_confidence_ratio(text, windows)
        # L=0, H=1 → ratio = 0/(0+1) = 0.0
        self.assertEqual(result["current"], 0.0,
                         "**medium** must not inflate the denominator")

    # ------------------------------------------------------------------
    # Markers without a parseable sprint header date are excluded
    # ------------------------------------------------------------------

    def test_markers_without_date_excluded(self):
        """A sprint section with no parseable date — its markers are excluded."""
        windows = self._make_windows()
        date_cur = self._date_in_window(windows, 2)

        text = (
            # Section with no date in the header — markers should be dropped.
            "# Sprint log — general notes\n"
            "- **low**. **low**. **low**.\n"
            # Section with a proper date — only these markers count.
            f"# Sprint — omicron · {date_cur}\n"
            "- **high**.\n"
        )
        result = _metricslib.sprint_low_confidence_ratio(text, windows)
        # Only the 1 high from the dated section counts; the 3 low from the
        # undated section are excluded.  L=0, H=1 → 0.0
        self.assertEqual(result["current"], 0.0,
                         "markers in undated sections must be excluded")

    # ------------------------------------------------------------------
    # Single window: prior == "n/a"
    # ------------------------------------------------------------------

    def test_single_window_prior_is_na(self):
        """With only one window, prior == "n/a" and arrow == "→"."""
        # 7 commits → 1 window (N=20)
        timeline = _make_timeline(7, start=self._TIMELINE_START, step_days=1)
        windows = _metricslib.tile_windows(timeline, window_size=20)
        self.assertEqual(len(windows), 1)

        date_cur = windows[0].start_dt.strftime("%Y-%m-%d")
        text = (
            f"# Sprint — pi · {date_cur}\n"
            "- **high**. **low**.\n"
        )
        result = _metricslib.sprint_low_confidence_ratio(text, windows)
        self.assertEqual(result["prior"], "n/a")
        self.assertEqual(result["arrow"], "→")

    # ------------------------------------------------------------------
    # Empty windows list
    # ------------------------------------------------------------------

    def test_empty_windows_returns_na(self):
        """With an empty windows list, both current and prior are "n/a"."""
        text = "# Sprint — rho · 2026-01-05\n- **high**. **low**.\n"
        result = _metricslib.sprint_low_confidence_ratio(text, [])
        self.assertEqual(result["current"], "n/a")
        self.assertEqual(result["prior"], "n/a")
        self.assertEqual(result["arrow"], "→")

    # ------------------------------------------------------------------
    # Multiple sprint sections with the same window accumulate markers
    # ------------------------------------------------------------------

    def test_multiple_sections_same_window_accumulate(self):
        """Multiple sprint sections whose dates fall in the same window
        accumulate their **high**/**low** markers together."""
        windows = self._make_windows()
        date_cur = self._date_in_window(windows, 2)
        # Second date also in window 2 (one day later)
        band = windows[2]
        date_cur2 = (band.start_dt + timedelta(days=2)).strftime("%Y-%m-%d")

        text = (
            f"# Sprint — sigma · {date_cur}\n"
            "- **low**. **high**.\n"
            f"# Sprint — tau · {date_cur2}\n"
            "- **low**. **low**.\n"
        )
        result = _metricslib.sprint_low_confidence_ratio(text, windows)
        # L=3, H=1 → 0.75
        self.assertEqual(result["current"], round(3 / 4, 2))

    # ------------------------------------------------------------------
    # Accepts both string and list-of-strings input
    # ------------------------------------------------------------------

    def test_accepts_list_of_strings(self):
        """sprint_low_confidence_ratio accepts a list of lines as well as a str."""
        windows = self._make_windows()
        date_cur = self._date_in_window(windows, 2)

        lines = [
            f"# Sprint — upsilon · {date_cur}",
            "- **low**. **high**.",
        ]
        result = _metricslib.sprint_low_confidence_ratio(lines, windows)
        self.assertEqual(result["current"], 0.5)


# ---------------------------------------------------------------------------
# EmptySourceTest — T-05: empty / missing-source safety (AC-05)
# ---------------------------------------------------------------------------

class EmptySourceTest(unittest.TestCase):
    """AC-05: every metric degrades safely when the source file is absent or
    a window contains no relevant entries.

    Proves (and hardens where needed) that:
      - The thin readers return [] / "" on a non-existent path, never raise.
      - Feeding that empty content to each metric yields the defined sentinel
        (counts 0/0 with arrow "→"; ratio "n/a" with arrow "→").
      - Calling each metric with windows=[] returns the sentinel result.
      - Non-empty windows but zero matching log entries → sentinel.
      - sprint ratio with low+high == 0 returns "n/a", never ZeroDivisionError.
    """

    # ------------------------------------------------------------------
    # Shared helpers
    # ------------------------------------------------------------------

    _NONEXISTENT = "/tmp/__ca_metrics_no_such_file_t05__.log"

    _TIMELINE_START = _utc(2026, 1, 1)

    def _make_windows(self):
        """Return a 3-window list (60 commits, N=20)."""
        timeline = _make_timeline(60, start=self._TIMELINE_START, step_days=1)
        return _metricslib.tile_windows(timeline, window_size=20)

    def _date_in_window(self, windows, window_index):
        """Return a YYYY-MM-DD date string inside the given window."""
        band = windows[window_index]
        return (band.start_dt + timedelta(hours=12)).strftime("%Y-%m-%d")

    def _ts_in_window(self, windows, window_index):
        """Return an ISO-8601 Z timestamp string inside the given window."""
        band = windows[window_index]
        return (band.start_dt + timedelta(hours=1)).strftime("%Y-%m-%dT%H:%M:%SZ")

    # ==================================================================
    # PART 1 — Thin readers: missing file returns empty, never raises
    # ==================================================================

    def test_read_override_log_missing_file_returns_empty_list(self):
        """read_override_log on a non-existent path returns [], does not raise."""
        result = _metricslib.read_override_log(self._NONEXISTENT)
        self.assertIsInstance(result, list)
        self.assertEqual(result, [])

    def test_read_triage_log_missing_file_returns_empty_list(self):
        """read_triage_log on a non-existent path returns [], does not raise."""
        result = _metricslib.read_triage_log(self._NONEXISTENT)
        self.assertIsInstance(result, list)
        self.assertEqual(result, [])

    def test_read_sprint_log_missing_file_returns_empty_string(self):
        """read_sprint_log on a non-existent path returns "", does not raise."""
        result = _metricslib.read_sprint_log(self._NONEXISTENT)
        self.assertIsInstance(result, str)
        self.assertEqual(result, "")

    # ==================================================================
    # PART 2 — Missing file → reader result fed directly to metric
    #           Expected: sentinel values, no raise
    # ==================================================================

    def test_override_rate_from_missing_file_yields_sentinel(self):
        """read_override_log (missing) → override_rate → 0/0/"→" sentinel."""
        windows = self._make_windows()
        lines = _metricslib.read_override_log(self._NONEXISTENT)
        result = _metricslib.override_rate(lines, windows)
        self.assertEqual(result["current"], 0)
        self.assertEqual(result["prior"], 0)
        self.assertEqual(result["arrow"], "→")

    def test_small_lane_rate_from_missing_file_yields_sentinel(self):
        """read_triage_log (missing) → small_lane_rate → 0/0/"→" sentinel."""
        windows = self._make_windows()
        lines = _metricslib.read_triage_log(self._NONEXISTENT)
        result = _metricslib.small_lane_rate(lines, windows)
        self.assertEqual(result["current"], 0)
        self.assertEqual(result["prior"], 0)
        self.assertEqual(result["arrow"], "→")

    def test_sprint_ratio_from_missing_file_yields_sentinel(self):
        """read_sprint_log (missing) → sprint_low_confidence_ratio → "n/a"/"n/a"/"→"."""
        windows = self._make_windows()
        text = _metricslib.read_sprint_log(self._NONEXISTENT)
        result = _metricslib.sprint_low_confidence_ratio(text, windows)
        self.assertEqual(result["current"], "n/a")
        self.assertEqual(result["prior"], "n/a")
        self.assertEqual(result["arrow"], "→")

    # ==================================================================
    # PART 3 — Empty window set: windows=[]
    # ==================================================================

    def test_override_rate_empty_windows_sentinel(self):
        """override_rate with windows=[] returns 0/0/"→", does not raise."""
        result = _metricslib.override_rate([], [])
        self.assertEqual(result["current"], 0)
        self.assertEqual(result["prior"], 0)
        self.assertEqual(result["arrow"], "→")

    def test_override_rate_content_with_empty_windows_sentinel(self):
        """override_rate with real log lines but windows=[] returns sentinel (no crash)."""
        # Provide a plausible log line; with no windows, nothing should be counted.
        lines = [
            "[2026-02-01T10:00:00Z] | BY: user@example.com | OVERRIDE: H-02 | REASON: test"
        ]
        result = _metricslib.override_rate(lines, [])
        self.assertEqual(result["current"], 0)
        self.assertEqual(result["prior"], 0)
        self.assertEqual(result["arrow"], "→")

    def test_small_lane_rate_empty_windows_sentinel(self):
        """small_lane_rate with windows=[] returns 0/0/"→", does not raise."""
        result = _metricslib.small_lane_rate([], [])
        self.assertEqual(result["current"], 0)
        self.assertEqual(result["prior"], 0)
        self.assertEqual(result["arrow"], "→")

    def test_small_lane_rate_content_with_empty_windows_sentinel(self):
        """small_lane_rate with LANE: small lines but windows=[] returns sentinel."""
        lines = [
            "[2026-02-01T10:00:00Z] | BY: user@example.com | LANE: small | SCOPE: x | BASIS: y"
        ]
        result = _metricslib.small_lane_rate(lines, [])
        self.assertEqual(result["current"], 0)
        self.assertEqual(result["prior"], 0)
        self.assertEqual(result["arrow"], "→")

    def test_sprint_ratio_empty_windows_sentinel(self):
        """sprint_low_confidence_ratio with windows=[] returns "n/a"/"n/a"/"→"."""
        text = "# Sprint — alpha · 2026-02-01\n- **high**. **low**.\n"
        result = _metricslib.sprint_low_confidence_ratio(text, [])
        self.assertEqual(result["current"], "n/a")
        self.assertEqual(result["prior"], "n/a")
        self.assertEqual(result["arrow"], "→")

    def test_sprint_ratio_empty_content_empty_windows_sentinel(self):
        """sprint_low_confidence_ratio with "" and windows=[] returns sentinel."""
        result = _metricslib.sprint_low_confidence_ratio("", [])
        self.assertEqual(result["current"], "n/a")
        self.assertEqual(result["prior"], "n/a")
        self.assertEqual(result["arrow"], "→")

    # ==================================================================
    # PART 4 — Non-empty windows, zero matching log entries
    # ==================================================================

    def test_override_rate_no_matching_entries_yields_zeros(self):
        """override_rate with non-empty windows but zero log entries → 0/0/"→"."""
        windows = self._make_windows()
        result = _metricslib.override_rate([], windows)
        self.assertEqual(result["current"], 0)
        self.assertEqual(result["prior"], 0)
        self.assertEqual(result["arrow"], "→")

    def test_override_rate_only_comment_lines_yields_zeros(self):
        """override_rate where all lines are comments → 0/0/"→" (no counts)."""
        windows = self._make_windows()
        lines = [
            "# This is a comment",
            "# [2026-02-01T10:00:00Z] | BY: x | OVERRIDE: H-02 | REASON: commented",
            "",
            "   ",
        ]
        result = _metricslib.override_rate(lines, windows)
        self.assertEqual(result["current"], 0)
        self.assertEqual(result["prior"], 0)
        self.assertEqual(result["arrow"], "→")

    def test_small_lane_rate_no_matching_entries_yields_zeros(self):
        """small_lane_rate with non-empty windows but empty lines → 0/0/"→"."""
        windows = self._make_windows()
        result = _metricslib.small_lane_rate([], windows)
        self.assertEqual(result["current"], 0)
        self.assertEqual(result["prior"], 0)
        self.assertEqual(result["arrow"], "→")

    def test_small_lane_rate_only_full_lane_entries_yields_zeros(self):
        """small_lane_rate where all entries are LANE: full → 0/0/"→".

        Verifies that LANE: full never bleeds into the LANE: small count.
        """
        windows = self._make_windows()
        ts = self._ts_in_window(windows, len(windows) - 1)
        lines = [
            f"[{ts}] | BY: tester@example.com | LANE: full | SCOPE: x | BASIS: y",
            f"[{ts}] | BY: tester@example.com | LANE: full | SCOPE: x | BASIS: y",
        ]
        result = _metricslib.small_lane_rate(lines, windows)
        self.assertEqual(result["current"], 0)
        self.assertEqual(result["prior"], 0)
        self.assertEqual(result["arrow"], "→")

    def test_sprint_ratio_no_matching_sections_yields_na(self):
        """sprint_low_confidence_ratio with windows but no dated sections → "n/a"."""
        windows = self._make_windows()
        # Text has bold tokens but inside an undated section.
        text = "# Sprint log — general\n- **high**. **low**.\n"
        result = _metricslib.sprint_low_confidence_ratio(text, windows)
        self.assertEqual(result["current"], "n/a")
        self.assertEqual(result["prior"], "n/a")
        self.assertEqual(result["arrow"], "→")

    def test_sprint_ratio_empty_text_with_windows_yields_na(self):
        """sprint_low_confidence_ratio with empty string and non-empty windows → "n/a"."""
        windows = self._make_windows()
        result = _metricslib.sprint_low_confidence_ratio("", windows)
        self.assertEqual(result["current"], "n/a")
        self.assertEqual(result["prior"], "n/a")
        self.assertEqual(result["arrow"], "→")

    # ==================================================================
    # PART 5 — No division by zero: low+high == 0 inside a dated section
    # ==================================================================

    def test_sprint_ratio_zero_markers_in_dated_section_no_divzero(self):
        """A dated sprint section with zero **high**/**low** markers returns "n/a",
        never raises ZeroDivisionError.

        The section header is parseable and maps to the current window, but
        the section body contains only strength words (**strong**, **moderate**,
        **weak**) and other bold tokens — none of which are **high** or **low**.
        """
        windows = self._make_windows()
        date_cur = self._date_in_window(windows, len(windows) - 1)
        text = (
            f"# Sprint — noscore · {date_cur}\n"
            "- Decision A. **strong**.\n"
            "- Decision B. **moderate**.\n"
            "- Decision C. **weak**.\n"
            "- Other: **D-01**, **Chosen:**.\n"
        )
        try:
            result = _metricslib.sprint_low_confidence_ratio(text, windows)
        except ZeroDivisionError as exc:
            self.fail(f"ZeroDivisionError raised when low+high==0: {exc}")
        self.assertEqual(result["current"], "n/a",
                         "zero confidence markers must yield sentinel 'n/a', not divide by zero")
        self.assertEqual(result["arrow"], "→")

    def test_sprint_ratio_both_windows_zero_markers_no_divzero(self):
        """Both current and prior sections have zero **high**/**low** markers.
        Must return "n/a"/"n/a"/"→", never raise ZeroDivisionError.
        """
        windows = self._make_windows()
        date_cur = self._date_in_window(windows, len(windows) - 1)
        date_pri = self._date_in_window(windows, len(windows) - 2)
        text = (
            f"# Sprint — prior-noscore · {date_pri}\n"
            "- Only **strong** here.\n"
            f"# Sprint — cur-noscore · {date_cur}\n"
            "- Only **moderate** here.\n"
        )
        try:
            result = _metricslib.sprint_low_confidence_ratio(text, windows)
        except ZeroDivisionError as exc:
            self.fail(f"ZeroDivisionError raised when both windows have low+high==0: {exc}")
        self.assertEqual(result["current"], "n/a")
        self.assertEqual(result["prior"], "n/a")
        self.assertEqual(result["arrow"], "→")

    def test_sprint_ratio_empty_list_input_no_divzero(self):
        """Empty list input must not raise ZeroDivisionError under any window set."""
        windows = self._make_windows()
        try:
            result = _metricslib.sprint_low_confidence_ratio([], windows)
        except ZeroDivisionError as exc:
            self.fail(f"ZeroDivisionError raised on empty list input: {exc}")
        self.assertEqual(result["current"], "n/a")
        self.assertEqual(result["prior"], "n/a")


# ---------------------------------------------------------------------------
# ComputeApiTest — T-06: public compute() API + fixed output surface (AC-07)
# ---------------------------------------------------------------------------

class ComputeApiTest(unittest.TestCase):
    """AC-07: compute() public entry point.

    Tests the single callable the /ca:metrics command will invoke.  The function
    signature is:

        compute(project_dir, window_size=20, *, _timeline=None) -> dict

    Testability seam: the optional keyword-only ``_timeline`` parameter accepts
    an injected list[datetime] that replaces the ``commit_timeline(project_dir)``
    git call.  When ``_timeline`` is None (the default), the real git wrapper is
    called.  This keeps the test suite hermetic while the production code path
    reads real git — the seam is documented in the function docstring.

    Fixture layout:
        <tmpdir>/.codearbiter/overrides.log   — two data lines
        <tmpdir>/.codearbiter/triage.log      — two data lines (LANE: small)
        <tmpdir>/.codearbiter/sprint-log.md   — one sprint section with markers

    The injected timeline is 40 datetimes starting 2024-01-01 (two full windows
    of N=20 so both current and prior window indices exist).  All fixture log
    lines are timestamped inside window 1 (prior) so the current window counts
    are predictably 0 — but the exact counts don't matter for AC-07; only the
    key-set and shape assertions matter.
    """

    # Distinctive raw strings that MUST NOT appear in the json.dumps(result).
    # These are substrings unique to the fixture log lines that would betray
    # that a raw log line had leaked into the output dict.
    _OVERRIDE_RAW_MARKER = "BY: override-actor@example.com"
    _TRIAGE_RAW_MARKER   = "SCOPE: commit-quality-fixture"
    _SPRINT_RAW_MARKER   = "Sprint — fixture-sprint"

    @classmethod
    def setUpClass(cls):
        """Create the fixture project directory once for the whole class."""
        import tempfile
        cls._tmpdir = tempfile.mkdtemp(prefix="ca_metrics_t06_")
        ca_dir = os.path.join(cls._tmpdir, ".codearbiter")
        os.makedirs(ca_dir, exist_ok=True)

        # --- Build a timeline: 40 commits starting 2024-01-01, daily.
        # window 0 (index 0): commits  0-19  ~ 2024-01-01 to 2024-01-20  (prior)
        # window 1 (index 1): commits 20-39  ~ 2024-01-21 to 2024-02-09  (current)
        start = datetime(2024, 1, 1, tzinfo=timezone.utc)
        cls._injected_timeline = [
            start + timedelta(days=i) for i in range(40)
        ]
        # window 1 = index 1 = current; window 0 = index 0 = prior
        # Place fixture log entries inside window 0 (prior) so current==0,
        # ensuring the assertions are independent of window count.
        prior_ts = (start + timedelta(days=5)).strftime("%Y-%m-%dT%H:%M:%SZ")
        prior_date = (start + timedelta(days=5)).strftime("%Y-%m-%d")

        # overrides.log — two entries in the prior window
        override_lines = (
            "# codeArbiter overrides log\n"
            f"[{prior_ts}] | BY: {cls._OVERRIDE_RAW_MARKER} | "
            "OVERRIDE: H-02 force-push | REASON: fixture test\n"
            f"[{prior_ts}] | BY: {cls._OVERRIDE_RAW_MARKER} | "
            "OVERRIDE: H-02 force-push | REASON: fixture test 2\n"
        )
        with open(os.path.join(ca_dir, "overrides.log"), "w", newline="\n",
                  encoding="utf-8") as fh:
            fh.write(override_lines)

        # triage.log — two LANE: small entries in the prior window
        triage_lines = (
            "# codeArbiter triage log\n"
            f"[{prior_ts}] | BY: triage-actor@example.com | LANE: small | "
            f"SCOPE: {cls._TRIAGE_RAW_MARKER} | BASIS: fixture\n"
            f"[{prior_ts}] | BY: triage-actor@example.com | LANE: small | "
            f"SCOPE: {cls._TRIAGE_RAW_MARKER} | BASIS: fixture 2\n"
        )
        with open(os.path.join(ca_dir, "triage.log"), "w", newline="\n",
                  encoding="utf-8") as fh:
            fh.write(triage_lines)

        # sprint-log.md — one section in the prior window with 1 high + 1 low
        sprint_text = (
            f"# {cls._SPRINT_RAW_MARKER} · {prior_date}\n"
            "- Decision A. **high**.\n"
            "- Decision B. **low**.\n"
        )
        with open(os.path.join(ca_dir, "sprint-log.md"), "w", newline="\n",
                  encoding="utf-8") as fh:
            fh.write(sprint_text)

    @classmethod
    def tearDownClass(cls):
        """Remove the fixture temp directory after all tests in this class."""
        import shutil
        shutil.rmtree(cls._tmpdir, ignore_errors=True)

    def _compute(self, **kwargs):
        """Call compute() with the injected timeline to keep tests hermetic."""
        return _metricslib.compute(
            self._tmpdir,
            _timeline=self._injected_timeline,
            **kwargs,
        )

    # ------------------------------------------------------------------
    # AC-07-1: exact key set — no extras, none missing
    # ------------------------------------------------------------------

    def test_key_set_is_exactly_three_keys(self):
        """compute() returns a dict with EXACTLY the three contracted keys."""
        result = self._compute()
        self.assertIsInstance(result, dict)
        self.assertEqual(
            set(result.keys()),
            {"override_rate", "small_lane_rate", "sprint_low_conf_ratio"},
            "compute() must return exactly the three contracted keys",
        )

    def test_no_extra_keys_in_result(self):
        """compute() must not return any key beyond the three contracted ones."""
        result = self._compute()
        extra = set(result.keys()) - {"override_rate", "small_lane_rate",
                                       "sprint_low_conf_ratio"}
        self.assertEqual(extra, set(), f"unexpected extra keys: {extra!r}")

    def test_all_three_contracted_keys_present(self):
        """compute() must include all three contracted keys — none may be absent."""
        result = self._compute()
        for key in ("override_rate", "small_lane_rate", "sprint_low_conf_ratio"):
            self.assertIn(key, result, f"contracted key {key!r} is missing")

    # ------------------------------------------------------------------
    # AC-07-3: each sub-result has the current/prior/arrow shape
    # ------------------------------------------------------------------

    def test_override_rate_has_current_prior_arrow(self):
        """The override_rate sub-result must have current, prior, and arrow keys."""
        result = self._compute()
        sub = result["override_rate"]
        self.assertIsInstance(sub, dict)
        for key in ("current", "prior", "arrow"):
            self.assertIn(key, sub,
                          f"override_rate sub-result missing key {key!r}")

    def test_small_lane_rate_has_current_prior_arrow(self):
        """The small_lane_rate sub-result must have current, prior, and arrow keys."""
        result = self._compute()
        sub = result["small_lane_rate"]
        self.assertIsInstance(sub, dict)
        for key in ("current", "prior", "arrow"):
            self.assertIn(key, sub,
                          f"small_lane_rate sub-result missing key {key!r}")

    def test_sprint_low_conf_ratio_has_current_prior_arrow(self):
        """The sprint_low_conf_ratio sub-result must have current, prior, and arrow keys."""
        result = self._compute()
        sub = result["sprint_low_conf_ratio"]
        self.assertIsInstance(sub, dict)
        for key in ("current", "prior", "arrow"):
            self.assertIn(key, sub,
                          f"sprint_low_conf_ratio sub-result missing key {key!r}")

    def test_arrow_values_are_valid_arrows(self):
        """Each sub-result arrow must be one of the three defined arrow strings."""
        result = self._compute()
        valid = {"↑", "↓", "→"}
        for metric_key in ("override_rate", "small_lane_rate", "sprint_low_conf_ratio"):
            arrow = result[metric_key]["arrow"]
            self.assertIn(arrow, valid,
                          f"{metric_key}['arrow'] = {arrow!r} is not a valid arrow")

    # ------------------------------------------------------------------
    # AC-07-2: no raw log line appears in any value (no-raw-line guardrail)
    # ------------------------------------------------------------------

    def test_no_raw_override_log_line_in_result(self):
        """The distinctive override log marker must not appear in json.dumps(result).

        This guards against compute() accidentally passing raw log text through
        instead of only the derived metric dict.
        """
        import json
        result = self._compute()
        serialised = json.dumps(result, ensure_ascii=False)
        self.assertNotIn(
            self._OVERRIDE_RAW_MARKER,
            serialised,
            "raw override log line leaked into the compute() result",
        )

    def test_no_raw_triage_log_line_in_result(self):
        """The distinctive triage log marker must not appear in json.dumps(result)."""
        import json
        result = self._compute()
        serialised = json.dumps(result, ensure_ascii=False)
        self.assertNotIn(
            self._TRIAGE_RAW_MARKER,
            serialised,
            "raw triage log line leaked into the compute() result",
        )

    def test_no_raw_sprint_log_line_in_result(self):
        """The distinctive sprint-log marker must not appear in json.dumps(result)."""
        import json
        result = self._compute()
        serialised = json.dumps(result, ensure_ascii=False)
        self.assertNotIn(
            self._SPRINT_RAW_MARKER,
            serialised,
            "raw sprint-log line leaked into the compute() result",
        )

    def test_no_iso_timestamp_bracket_in_result(self):
        """No value in the result may contain a raw '[' ISO-8601 timestamp prefix.

        Log lines begin with '[YYYY-' so the substring '[2024-' is unique to
        raw log lines and must not appear in the serialised metric output.
        """
        import json
        result = self._compute()
        serialised = json.dumps(result, ensure_ascii=False)
        self.assertNotIn(
            "[2024-",
            serialised,
            "a raw '[<ISO-timestamp>' log-line prefix leaked into the result",
        )

    # ------------------------------------------------------------------
    # Degrade safely: missing .codearbiter dir — never raise
    # ------------------------------------------------------------------

    def test_missing_codearbiter_dir_does_not_raise(self):
        """compute() on a dir with no .codearbiter sub-dir must return the sentinel
        dict with zero counts / 'n/a' — it must never raise."""
        import tempfile
        with tempfile.TemporaryDirectory(prefix="ca_metrics_t06_nodotca_") as empty_dir:
            try:
                result = _metricslib.compute(
                    empty_dir,
                    _timeline=self._injected_timeline,
                )
            except Exception as exc:
                self.fail(
                    f"compute() raised {type(exc).__name__} on missing "
                    f".codearbiter dir: {exc}"
                )
            # Key-set must still be correct.
            self.assertEqual(
                set(result.keys()),
                {"override_rate", "small_lane_rate", "sprint_low_conf_ratio"},
            )

    def test_missing_codearbiter_dir_returns_sentinels(self):
        """compute() with a missing .codearbiter dir returns zero-count / n/a
        sentinels for all three metrics."""
        import tempfile
        with tempfile.TemporaryDirectory(prefix="ca_metrics_t06_sentinels_") as empty_dir:
            result = _metricslib.compute(
                empty_dir,
                _timeline=self._injected_timeline,
            )
        self.assertEqual(result["override_rate"]["current"], 0)
        self.assertEqual(result["override_rate"]["prior"], 0)
        self.assertEqual(result["small_lane_rate"]["current"], 0)
        self.assertEqual(result["small_lane_rate"]["prior"], 0)
        self.assertEqual(result["sprint_low_conf_ratio"]["current"], "n/a")
        self.assertEqual(result["sprint_low_conf_ratio"]["prior"], "n/a")

    # ------------------------------------------------------------------
    # Degrade safely: empty injected timeline (no git history)
    # ------------------------------------------------------------------

    def test_empty_timeline_does_not_raise(self):
        """compute() with an empty timeline (no git history) must not raise."""
        try:
            result = _metricslib.compute(self._tmpdir, _timeline=[])
        except Exception as exc:
            self.fail(
                f"compute() raised {type(exc).__name__} on empty timeline: {exc}"
            )
        self.assertEqual(
            set(result.keys()),
            {"override_rate", "small_lane_rate", "sprint_low_conf_ratio"},
        )

    def test_empty_timeline_returns_sentinels(self):
        """compute() with an empty timeline returns sentinel values for all metrics."""
        result = _metricslib.compute(self._tmpdir, _timeline=[])
        self.assertEqual(result["override_rate"]["current"], 0)
        self.assertEqual(result["override_rate"]["prior"], 0)
        self.assertEqual(result["small_lane_rate"]["current"], 0)
        self.assertEqual(result["small_lane_rate"]["prior"], 0)
        self.assertEqual(result["sprint_low_conf_ratio"]["current"], "n/a")
        self.assertEqual(result["sprint_low_conf_ratio"]["prior"], "n/a")

    # ------------------------------------------------------------------
    # window_size parameter is forwarded
    # ------------------------------------------------------------------

    def test_window_size_parameter_is_accepted(self):
        """compute() accepts window_size kwarg without raising."""
        try:
            result = _metricslib.compute(
                self._tmpdir,
                window_size=10,
                _timeline=self._injected_timeline,
            )
        except Exception as exc:
            self.fail(
                f"compute() raised {type(exc).__name__} with window_size=10: {exc}"
            )
        self.assertEqual(
            set(result.keys()),
            {"override_rate", "small_lane_rate", "sprint_low_conf_ratio"},
        )


# ---------------------------------------------------------------------------
# ReadOnlyTest — T-07: read-only invariant (AC-06)
# ---------------------------------------------------------------------------

class ReadOnlyTest(unittest.TestCase):
    """AC-06: compute() leaves every file in .codearbiter/ byte-for-byte unchanged.

    Strategy:
        1. Build a fixture .codearbiter/ subtree with known byte content in a
           temporary directory.  Include a nested sub-directory to catch any write
           that might land in an unexpected location.
        2. Take a byte-level snapshot BEFORE calling compute(): for every regular
           file, record its SHA-256 digest (binary read) keyed by its path relative
           to .codearbiter/.  Also record the set of all paths so that file
           creation or deletion is also caught.
        3. Call compute() with an injected _timeline to avoid any git subprocess.
        4. Take an identical snapshot AFTER the call.
        5. Assert both snapshots are identical.

    Why the assertion is non-trivial:
        If compute() (or any function it calls) opened any file for writing —
        even writing the same bytes back — the open-for-write call on a POSIX or
        Windows filesystem may truncate and rewrite the file.  On Windows, the
        file's modification time and other metadata change as well; but more
        critically: if any byte were added, removed, or changed (e.g. a trailing
        newline appended to a log), the SHA-256 digest would differ.  If a new
        file were created (e.g. a cache or lock file), the path set would differ.
        If an existing file were deleted, the path set would also differ.
        Either failure mode causes the test to fail — asserting both path-set
        equality AND per-file hash equality ensures there is no loophole.
    """

    # Injected timeline: 40 commits starting 2024-01-01 (two full N=20 windows).
    _TIMELINE_START = datetime(2024, 1, 1, tzinfo=timezone.utc)

    @classmethod
    def _injected_timeline(cls):
        return [cls._TIMELINE_START + timedelta(days=i) for i in range(40)]

    @classmethod
    def setUpClass(cls):
        """Build the fixture .codearbiter/ subtree once for the whole class."""
        import tempfile
        cls._tmpdir = tempfile.mkdtemp(prefix="ca_metrics_t07_")
        ca_dir = os.path.join(cls._tmpdir, ".codearbiter")
        os.makedirs(ca_dir, exist_ok=True)

        # Nested sub-directory — catches any write that might land one level deeper.
        nested_dir = os.path.join(ca_dir, "nested")
        os.makedirs(nested_dir, exist_ok=True)

        # Timestamps in the prior window (window index 0: days 0-19 from start).
        prior_ts = (cls._TIMELINE_START + timedelta(days=5)).strftime(
            "%Y-%m-%dT%H:%M:%SZ"
        )
        prior_date = (cls._TIMELINE_START + timedelta(days=5)).strftime("%Y-%m-%d")

        # overrides.log — fixed byte content (LF line endings).
        override_content = (
            "# codeArbiter overrides log — T-07 fixture\n"
            f"[{prior_ts}] | BY: readonly-actor@example.com | "
            "OVERRIDE: H-02 force-push | REASON: readonly fixture test\n"
        )
        with open(
            os.path.join(ca_dir, "overrides.log"), "w", newline="\n", encoding="utf-8"
        ) as fh:
            fh.write(override_content)

        # triage.log — fixed byte content (LF line endings).
        triage_content = (
            "# codeArbiter triage log — T-07 fixture\n"
            f"[{prior_ts}] | BY: readonly-actor@example.com | LANE: small | "
            "SCOPE: readonly-test | BASIS: fixture\n"
        )
        with open(
            os.path.join(ca_dir, "triage.log"), "w", newline="\n", encoding="utf-8"
        ) as fh:
            fh.write(triage_content)

        # sprint-log.md — fixed byte content (LF line endings).
        sprint_content = (
            f"# Sprint — readonly-fixture · {prior_date}\n"
            "- Decision A. **high**.\n"
            "- Decision B. **low**.\n"
        )
        with open(
            os.path.join(ca_dir, "sprint-log.md"), "w", newline="\n", encoding="utf-8"
        ) as fh:
            fh.write(sprint_content)

        # nested/notes.txt — a sentinel file one directory deeper.
        # Its presence extends the path set so a write to the wrong place is caught.
        nested_content = "nested sentinel file — must not be touched\n"
        with open(
            os.path.join(nested_dir, "notes.txt"), "w", newline="\n", encoding="utf-8"
        ) as fh:
            fh.write(nested_content)

    @classmethod
    def tearDownClass(cls):
        """Remove the fixture temp directory after all tests in the class."""
        import shutil
        shutil.rmtree(cls._tmpdir, ignore_errors=True)

    # ------------------------------------------------------------------
    # Snapshot helpers
    # ------------------------------------------------------------------

    def _snapshot(self):
        """Return a dict mapping relative-path -> sha256 hex digest for every
        regular file found recursively under <tmpdir>/.codearbiter/.

        Files are read in binary mode so that any byte-level change — including
        a CRLF/LF difference or a trailing newline append — is captured by the
        digest.

        The path set is also captured implicitly by the dict's key set.
        """
        import hashlib

        ca_dir = os.path.join(self._tmpdir, ".codearbiter")
        snapshot = {}
        for dirpath, _dirnames, filenames in os.walk(ca_dir):
            for fname in filenames:
                abs_path = os.path.join(dirpath, fname)
                rel_path = os.path.relpath(abs_path, ca_dir)
                # Normalise path separators so the dict is OS-agnostic.
                rel_path = rel_path.replace(os.sep, "/")
                with open(abs_path, "rb") as fh:
                    digest = hashlib.sha256(fh.read()).hexdigest()
                snapshot[rel_path] = digest
        return snapshot

    # ------------------------------------------------------------------
    # Tests
    # ------------------------------------------------------------------

    def test_no_file_created_or_deleted(self):
        """compute() must not create or delete any file under .codearbiter/."""
        before = self._snapshot()
        _metricslib.compute(self._tmpdir, _timeline=self._injected_timeline())
        after = self._snapshot()

        before_paths = set(before.keys())
        after_paths = set(after.keys())

        created = after_paths - before_paths
        deleted = before_paths - after_paths

        self.assertEqual(
            created,
            set(),
            f"compute() created unexpected files under .codearbiter/: {sorted(created)}",
        )
        self.assertEqual(
            deleted,
            set(),
            f"compute() deleted files from .codearbiter/: {sorted(deleted)}",
        )

    def test_no_file_bytes_changed(self):
        """compute() must not modify the byte content of any file under .codearbiter/.

        The SHA-256 digest is compared per file so that even a single-byte change
        (e.g. an appended newline or CRLF conversion) causes a failure.
        """
        before = self._snapshot()
        _metricslib.compute(self._tmpdir, _timeline=self._injected_timeline())
        after = self._snapshot()

        # Only compare files present in both snapshots (creation/deletion is
        # covered by test_no_file_created_or_deleted above).
        common_paths = set(before.keys()) & set(after.keys())
        changed = {
            p for p in common_paths if before[p] != after[p]
        }
        self.assertEqual(
            changed,
            set(),
            f"compute() modified byte content of file(s) under .codearbiter/: "
            f"{sorted(changed)}",
        )

    def test_full_snapshot_identical(self):
        """Composite assertion: both path set and all per-file digests must be
        identical before and after compute() — single-call proof of the invariant.

        This is the primary AC-06 assertion.  The two helper tests above decompose
        the failure mode for easier diagnosis; this test asserts the combined
        invariant as the spec states it.
        """
        before = self._snapshot()
        _metricslib.compute(self._tmpdir, _timeline=self._injected_timeline())
        after = self._snapshot()

        self.assertEqual(
            before,
            after,
            "compute() altered the .codearbiter/ subtree — snapshot mismatch.\n"
            "Expected: no file created, deleted, or modified.\n"
            f"Before keys: {sorted(before.keys())}\n"
            f"After  keys: {sorted(after.keys())}\n"
            "Changed digests: "
            + str({p: (before.get(p), after.get(p))
                   for p in set(before) | set(after)
                   if before.get(p) != after.get(p)}),
        )

    def test_nested_file_unchanged(self):
        """The sentinel file in .codearbiter/nested/ must also be byte-identical
        after compute(), proving the snapshot covers the full subtree recursively.
        """
        import hashlib

        nested_path = os.path.join(
            self._tmpdir, ".codearbiter", "nested", "notes.txt"
        )
        with open(nested_path, "rb") as fh:
            before_digest = hashlib.sha256(fh.read()).hexdigest()

        _metricslib.compute(self._tmpdir, _timeline=self._injected_timeline())

        with open(nested_path, "rb") as fh:
            after_digest = hashlib.sha256(fh.read()).hexdigest()

        self.assertEqual(
            before_digest,
            after_digest,
            "compute() modified .codearbiter/nested/notes.txt — "
            "the nested sentinel file must not be touched.",
        )

    def test_compute_still_returns_correct_shape_after_snapshot(self):
        """Sanity check: compute() still returns the three-key dict with the
        correct shape during the read-only test run (no silent no-op regression).
        """
        result = _metricslib.compute(
            self._tmpdir, _timeline=self._injected_timeline()
        )
        self.assertIsInstance(result, dict)
        self.assertEqual(
            set(result.keys()),
            {"override_rate", "small_lane_rate", "sprint_low_conf_ratio"},
            "compute() must still return all three contracted keys during T-07 run",
        )
        for metric_key in ("override_rate", "small_lane_rate", "sprint_low_conf_ratio"):
            sub = result[metric_key]
            self.assertIsInstance(sub, dict)
            for field in ("current", "prior", "arrow"):
                self.assertIn(
                    field, sub,
                    f"{metric_key} sub-dict is missing key {field!r}",
                )


if __name__ == "__main__":
    unittest.main(verbosity=2)
