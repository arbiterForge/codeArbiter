#!/usr/bin/env python3
# codeArbiter — metrics helper foundation (T-01 + T-02, /ca:metrics).
#
# Builds the window-tiling layer for governance-log trend computation. Governance
# history is tiled into commit-count windows of N=20 commits (default, parameterized).
# Each log entry will later be mapped into a window by its ISO-8601 timestamp.
#
# Design principles (mirroring _previewlib.py / _prunelib.py):
#   - Stdlib only; no third-party imports ever — runs on stock Python.
#   - Zero side effects at import time: no git calls, no file I/O.
#   - Pure functions are fully testable with synthetic data (no real git needed).
#   - The thin git wrapper (commit_timeline) is the ONLY function that shells out.
#
# Public API (T-01 scope — window tiling):
#   tile_windows(timestamps, window_size=20) -> list[WindowBand]
#   map_to_window(timestamp, windows) -> int   (window index or BEFORE_HISTORY)
#   commit_timeline(root) -> list[datetime]     (git wrapper, not unit-tested)
#   BEFORE_HISTORY: int = -1                   (sentinel for pre-history timestamps)
#
# Public API (T-02 scope — override-rate metric):
#   override_rate(lines_or_text, windows) -> dict with keys: current, prior, arrow
#   read_override_log(path) -> list[str]        (thin file reader, not unit-tested)
#
# Public API (T-03 scope — small-lane-rate metric):
#   small_lane_rate(lines_or_text, windows) -> dict with keys: current, prior, arrow
#   read_triage_log(path) -> list[str]          (thin file reader, not unit-tested)
#
# Public API (T-04 scope — sprint low-confidence ratio):
#   sprint_low_confidence_ratio(lines_or_text, windows) -> dict: current, prior, arrow
#   read_sprint_log(path) -> str                (thin file reader, not unit-tested)
#
# [NEEDS-TRIAGE] Later tasks will add the public compute() API, the /ca:metrics
# command file, and command registration in plugin.json — none of that is
# implemented here.

import subprocess
from collections import namedtuple
from datetime import datetime, timezone

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

# Default commit-count window size (parameterized on every call).
DEFAULT_WINDOW_SIZE = 20

# Sentinel returned by map_to_window when the timestamp precedes the entire
# known history. Negative so it can never be confused with a valid window index.
BEFORE_HISTORY = -1

# ---------------------------------------------------------------------------
# Data types
# ---------------------------------------------------------------------------

# One window band as produced by tile_windows.
#
# Fields:
#   index    — 0-based integer; 0 = oldest, highest = most recent ("current").
#   start_dt — timezone-aware UTC datetime of the first (oldest) commit in the band.
#   end_dt   — timezone-aware UTC datetime of the last  (newest) commit in the band.
#
# Window semantics: consecutive commit-count groups of `window_size` commits.
# When M commits are not evenly divisible by N, the OLDEST group is partial
# (smaller than N). All subsequent groups are full-size. This keeps the most
# recent window always "full" — the current window is never artificially short.
WindowBand = namedtuple("WindowBand", ["index", "start_dt", "end_dt"])

# ---------------------------------------------------------------------------
# ISO-8601 parsing
# ---------------------------------------------------------------------------

def _parse_ts(ts):
    """Accept either a timezone-aware datetime or an ISO-8601 string with
    trailing Z (e.g. '2026-06-14T02:06:45Z') and always return a
    timezone-aware UTC datetime.

    Raises ValueError on unrecognised string format.
    Raises TypeError on values that are neither str nor datetime.
    """
    if isinstance(ts, datetime):
        if ts.tzinfo is None:
            # Treat naive datetimes as UTC for robustness; caller should pass
            # aware datetimes.  [NEEDS-TRIAGE] — consider rejecting naive
            # datetimes once the call-sites are fully settled.
            return ts.replace(tzinfo=timezone.utc)
        return ts
    if isinstance(ts, str):
        # The governance logs emit '2026-06-14T02:06:45Z'. Python 3.11+
        # fromisoformat handles the Z suffix, but earlier 3.x versions do not,
        # so we normalise the Z to +00:00 for broad compatibility.
        normalised = ts.rstrip()
        if normalised.endswith("Z"):
            normalised = normalised[:-1] + "+00:00"
        return datetime.fromisoformat(normalised)
    raise TypeError(f"timestamp must be a datetime or ISO-8601 str, got {type(ts)!r}")

# ---------------------------------------------------------------------------
# Pure function: tile_windows
# ---------------------------------------------------------------------------

def tile_windows(timestamps, window_size=DEFAULT_WINDOW_SIZE):
    """Tile a commit timeline into consecutive commit-count windows.

    Args:
        timestamps: ordered (oldest → newest) list of timezone-aware datetimes
                    OR ISO-8601 strings ending in Z.  Empty list is accepted.
        window_size: number of commits per full window (default 20, must be >= 1).

    Returns:
        list of WindowBand in ascending index order (index 0 = oldest).
        Empty list when `timestamps` is empty.

    Partial-window rule:
        When len(timestamps) % window_size != 0, the OLDEST window is the
        partial (smaller) group.  All windows from index 1 onward are full-size.
        Example: 45 commits, N=20 → window 0 has 5 commits (partial/oldest),
        window 1 has 20, window 2 has 20.
    """
    if window_size < 1:
        raise ValueError(f"window_size must be >= 1, got {window_size!r}")

    parsed = [_parse_ts(t) for t in timestamps]
    m = len(parsed)
    if m == 0:
        return []

    # Compute the size of the (possibly partial) oldest group.
    remainder = m % window_size
    oldest_size = remainder if remainder != 0 else window_size

    # Build slices: [oldest_group] + [full groups...]
    # The oldest group starts at index 0 in the parsed list.
    groups = []
    pos = 0
    # First group (partial when remainder != 0, full when m % window_size == 0)
    groups.append(parsed[pos: pos + oldest_size])
    pos += oldest_size
    # Remaining full-size groups
    while pos < m:
        groups.append(parsed[pos: pos + window_size])
        pos += window_size

    return [
        WindowBand(index=i, start_dt=grp[0], end_dt=grp[-1])
        for i, grp in enumerate(groups)
    ]

# ---------------------------------------------------------------------------
# Pure function: map_to_window
# ---------------------------------------------------------------------------

def map_to_window(timestamp, windows):
    """Map a single timestamp to a window index.

    Boundary semantics (half-open intervals, higher-index wins at boundaries):
        A timestamp T maps to the highest-index window whose start_dt <= T.
        Concretely: if T >= windows[i].start_dt for multiple i, the largest
        such i is returned.  This ensures a timestamp exactly equal to a
        window-boundary commit date maps to the more-recent (higher-index) window.

    Args:
        timestamp: timezone-aware datetime OR ISO-8601 Z string.
        windows:   list of WindowBand from tile_windows (may be empty).

    Returns:
        int — the matching window index (0-based), or BEFORE_HISTORY (-1)
        when `timestamp` precedes all windows or `windows` is empty.

    Never raises on valid input.
    """
    if not windows:
        return BEFORE_HISTORY

    ts = _parse_ts(timestamp)

    # Walk from the most-recent window downward; return the first whose
    # start_dt <= ts.  This implements "highest-index wins at a boundary".
    for band in reversed(windows):
        if ts >= band.start_dt:
            return band.index

    # ts is older than every window's start_dt
    return BEFORE_HISTORY

# ---------------------------------------------------------------------------
# Git wrapper: commit_timeline (thin shell; NOT unit-tested with real git)
# ---------------------------------------------------------------------------

def commit_timeline(root):
    """Return a list of timezone-aware UTC datetimes for every commit in the
    repository at `root`, ordered oldest → newest.

    Shells out to `git log --format=%cI --reverse` (ISO-8601 strict format,
    with timezone offset).  Returns an empty list if git is unavailable, if
    `root` is not a git repository, or if any other error occurs — callers
    must not assume a non-empty return.

    This wrapper is intentionally thin: it exists only to bridge the git
    boundary and feed the pure tile_windows / map_to_window functions with
    real commit data.  It is NOT unit-tested with real git; the pure functions
    carry all the testable contract.

    Args:
        root: absolute path to a git repository root (or any worktree path).

    Returns:
        list[datetime] — timezone-aware UTC datetimes, oldest first.
        Empty list on any error.
    """
    try:
        result = subprocess.run(
            ["git", "log", "--format=%cI", "--reverse"],
            cwd=root,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=30,
        )
    except Exception:  # noqa: BLE001 — missing git binary, timeout, etc.
        return []

    if result.returncode != 0:
        return []

    datetimes = []
    for line in result.stdout.splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            datetimes.append(_parse_ts(line))
        except (ValueError, TypeError):
            # Malformed git output line — skip rather than crash.
            continue
    return datetimes

# ---------------------------------------------------------------------------
# Pure function: override_rate  (T-02)
# ---------------------------------------------------------------------------

# Regex to extract the leading timestamp from an overrides.log data line.
# Format: [<ISO-8601-Z>] | BY: ...
# Only the timestamp portion inside the first [...] is captured.
import re as _re
_OVERRIDE_TS_RE = _re.compile(r"^\[([^\]]+)\]")


def override_rate(lines_or_text, windows):
    """Compute the override rate for the current and prior windows.

    Parses overrides.log content, maps each entry to a window, and returns
    counts for the most-recent (current) window and the preceding (prior) window,
    together with a trend arrow.

    Args:
        lines_or_text: either a list of strings (one per log line) or a single
                       multi-line string.  Both forms are accepted so that callers
                       can pass raw file text or pre-split lines with equal ease.
        windows:       list of WindowBand from tile_windows (may be empty).

    Returns:
        dict with keys:
            "current" (int)  — count of override entries mapped to the current
                               window (highest index in `windows`).
            "prior"   (int)  — count mapped to the prior window (current − 1),
                               or 0 when fewer than 2 windows exist.
            "arrow"   (str)  — "↑" if current > prior, "↓" if current < prior,
                               "→" if equal.

    Filtering rules:
        - Lines that start with "#" (after stripping leading whitespace) are
          comment lines and are excluded.
        - Blank and whitespace-only lines are excluded.
        - Entries whose parsed timestamp maps to BEFORE_HISTORY are excluded
          from all window counts.
    """
    # Normalise input: accept either a str block or an iterable of strings.
    if isinstance(lines_or_text, str):
        raw_lines = lines_or_text.splitlines()
    else:
        raw_lines = list(lines_or_text)

    # Determine current and prior window indices.
    if windows:
        current_idx = windows[-1].index
        prior_idx = current_idx - 1 if len(windows) >= 2 else None
    else:
        current_idx = None
        prior_idx = None

    current_count = 0
    prior_count = 0

    for raw in raw_lines:
        line = raw.strip()
        # Skip blank lines and comment lines.
        if not line or line.startswith("#"):
            continue

        # Extract the leading timestamp token "[<ts>]".
        m = _OVERRIDE_TS_RE.match(line)
        if not m:
            # No recognisable timestamp; skip rather than crash.
            continue

        ts_str = m.group(1).strip()
        try:
            window_idx = map_to_window(ts_str, windows)
        except (ValueError, TypeError):
            # Malformed timestamp in log line; skip.
            continue

        if window_idx == BEFORE_HISTORY:
            continue
        if window_idx == current_idx:
            current_count += 1
        elif prior_idx is not None and window_idx == prior_idx:
            prior_count += 1
        # Entries in older windows (index < prior_idx) are intentionally ignored;
        # they contribute to neither current nor prior.

    if current_count > prior_count:
        arrow = "↑"  # ↑
    elif current_count < prior_count:
        arrow = "↓"  # ↓
    else:
        arrow = "→"  # →

    return {"current": current_count, "prior": prior_count, "arrow": arrow}


# ---------------------------------------------------------------------------
# Pure function: small_lane_rate  (T-03)
# ---------------------------------------------------------------------------

# Match "LANE: small" as a field value — the pipe-delimited field must read
# exactly "LANE: small" (not "LANE: smallX" or "LANE: full").
# We look for the literal token after optional surrounding whitespace.
_SMALL_LANE_RE = _re.compile(r"\|\s*LANE:\s*small\s*(?:\||$)")


def small_lane_rate(lines_or_text, windows):
    """Compute the small-lane rate for the current and prior windows.

    Parses triage.log content, counts only entries containing 'LANE: small',
    maps each to a window, and returns counts for the most-recent (current)
    window and the preceding (prior) window, together with a trend arrow.

    triage.log line format (non-comment):
        [<ISO-8601 Z timestamp>] | BY: <actor> | LANE: small | SCOPE: ... | BASIS: ...

    Args:
        lines_or_text: either a list of strings (one per log line) or a single
                       multi-line string.
        windows:       list of WindowBand from tile_windows (may be empty).

    Returns:
        dict with keys:
            "current" (int)  — count of LANE: small entries mapped to the
                               current window (highest index in `windows`).
            "prior"   (int)  — count mapped to the prior window (current - 1),
                               or 0 when fewer than 2 windows exist.
            "arrow"   (str)  — "↑" if current > prior, "↓" if current < prior,
                               "→" if equal.

    Filtering rules:
        - Lines that start with "#" (after stripping leading whitespace) are
          comment lines and are excluded.
        - Blank and whitespace-only lines are excluded.
        - Lines that do NOT contain 'LANE: small' are excluded (e.g. LANE: full).
        - Entries whose parsed timestamp maps to BEFORE_HISTORY are excluded
          from all window counts.
    """
    # Normalise input: accept either a str block or an iterable of strings.
    if isinstance(lines_or_text, str):
        raw_lines = lines_or_text.splitlines()
    else:
        raw_lines = list(lines_or_text)

    # Determine current and prior window indices.
    if windows:
        current_idx = windows[-1].index
        prior_idx = current_idx - 1 if len(windows) >= 2 else None
    else:
        current_idx = None
        prior_idx = None

    current_count = 0
    prior_count = 0

    for raw in raw_lines:
        line = raw.strip()
        # Skip blank lines and comment lines.
        if not line or line.startswith("#"):
            continue

        # Only count lines that contain the exact field 'LANE: small'.
        if not _SMALL_LANE_RE.search(line):
            continue

        # Extract the leading timestamp token "[<ts>]".
        m = _OVERRIDE_TS_RE.match(line)
        if not m:
            # No recognisable timestamp; skip rather than crash.
            continue

        ts_str = m.group(1).strip()
        try:
            window_idx = map_to_window(ts_str, windows)
        except (ValueError, TypeError):
            # Malformed timestamp in log line; skip.
            continue

        if window_idx == BEFORE_HISTORY:
            continue
        if window_idx == current_idx:
            current_count += 1
        elif prior_idx is not None and window_idx == prior_idx:
            prior_count += 1
        # Entries in older windows (index < prior_idx) are intentionally
        # ignored; they contribute to neither current nor prior.

    if current_count > prior_count:
        arrow = "↑"  # ↑
    elif current_count < prior_count:
        arrow = "↓"  # ↓
    else:
        arrow = "→"  # →

    return {"current": current_count, "prior": prior_count, "arrow": arrow}


# ---------------------------------------------------------------------------
# Thin file reader: read_triage_log  (T-03, not unit-tested)
# ---------------------------------------------------------------------------

def read_triage_log(path):
    """Read triage.log from `path` and return its lines as a list of strings.

    This is the only function in T-03 that performs file I/O.  It is kept
    intentionally thin — callers pass the result to the pure small_lane_rate()
    function for all business logic.

    Returns an empty list if the file does not exist or cannot be read.
    """
    try:
        with open(path, encoding="utf-8", errors="replace") as fh:
            return fh.readlines()
    except OSError:
        return []


# ---------------------------------------------------------------------------
# Thin file reader: read_override_log  (T-02, not unit-tested)
# ---------------------------------------------------------------------------

def read_override_log(path):
    """Read overrides.log from `path` and return its lines as a list of strings.

    This is the only function in T-02 that performs file I/O.  It is kept
    intentionally thin — callers pass the result to the pure override_rate()
    function for all business logic.

    Returns an empty list if the file does not exist or cannot be read.
    """
    try:
        with open(path, encoding="utf-8", errors="replace") as fh:
            return fh.readlines()
    except OSError:
        return []


# ---------------------------------------------------------------------------
# Pure function: sprint_low_confidence_ratio  (T-04)
# ---------------------------------------------------------------------------

# Match a sprint-section header and capture the YYYY-MM-DD date.
# Handles both "# Sprint — name · YYYY-MM-DD" and "# Sprint: name · YYYY-MM-DD".
# The date must follow a " · " (space-middot-space) separator anywhere in the
# header line.  Other "# Sprint …" headers without this pattern produce no match
# and their markers are excluded (documented below).
_SPRINT_HEADER_RE = _re.compile(r"^#\s+Sprint[^\n]*·\s*(\d{4}-\d{2}-\d{2})")

# Match exactly the bold tokens **high** and **low** (case-sensitive).
# The pattern anchors on the literal ** delimiters, so **strong**, **moderate**,
# **weak**, **medium**, **D-01**, etc. cannot match.
_CONFIDENCE_MARKER_RE = _re.compile(r"\*\*(high|low)\*\*")


def sprint_low_confidence_ratio(lines_or_text, windows):
    """Compute the sprint low-confidence ratio for the current and prior windows.

    Scans sprint-log.md content for SMARTS confidence markers.  Only the literal
    bold tokens ``**high**`` and ``**low**`` are counted — confidence markers only.
    All other bold tokens, including the SMARTS strength words (``**strong**``,
    ``**moderate**``, ``**weak**``) and ``**medium**``, are explicitly excluded.

    Each marker is attributed to the sprint section it appears in.  A section
    begins at a header matching::

        # Sprint[...] · YYYY-MM-DD

    and extends until the next such header (or end-of-text).  The header date is
    parsed as midnight UTC and mapped to a window via ``map_to_window``.  Markers
    in sections whose header contains no parseable date are excluded entirely
    (never mapped, never counted).

    Args:
        lines_or_text: either a list of strings (one per line) or a single
                       multi-line string.  Both forms are accepted.
        windows:       list of WindowBand from tile_windows (may be empty).

    Returns:
        dict with keys:
            "current" — ``round(L/(L+H), 2)`` for the current (highest-index)
                        window, or the sentinel string ``"n/a"`` when ``L+H == 0``
                        in that window.
            "prior"   — same for the prior window (current − 1); ``"n/a"`` when
                        no prior window exists or its ``L+H == 0``.
            "arrow"   — ``"↑"`` if current > prior, ``"↓"`` if current < prior,
                        ``"→"`` if equal.  When EITHER ``current`` or ``prior``
                        is the ``"n/a"`` sentinel, ``arrow`` is always ``"→"``.

    Exclusion rules (documented):
        - Sections with no parseable date in their header: markers excluded.
        - ``**medium**`` tokens: excluded (neither high nor low).
        - ``**strong**``, ``**moderate**``, ``**weak**`` and all other bold
          tokens: excluded (different SMARTS axis).
        - Markers mapping to BEFORE_HISTORY: excluded (older than all windows).
    """
    # Normalise input.
    if isinstance(lines_or_text, str):
        raw_lines = lines_or_text.splitlines()
    else:
        raw_lines = list(lines_or_text)

    # Determine the current and prior window indices.
    if windows:
        current_idx = windows[-1].index
        prior_idx = current_idx - 1 if len(windows) >= 2 else None
    else:
        current_idx = None
        prior_idx = None

    # Accumulate high/low counts per window index.
    # Keys: window index (int).  Values: [low_count, high_count].
    counts = {}  # {window_idx: [low, high]}

    # Walk lines, tracking which window the current sprint section belongs to.
    # section_window_idx: the window index for the active sprint section,
    # or None when no section is active (or the last header had no parseable date).
    section_window_idx = None

    for raw in raw_lines:
        line = raw.rstrip("\n").rstrip("\r")

        # Check whether this line starts a new sprint-section header.
        m_header = _SPRINT_HEADER_RE.match(line)
        if m_header:
            date_str = m_header.group(1)
            try:
                # Treat the sprint date as midnight UTC.
                dt = datetime.strptime(date_str, "%Y-%m-%d").replace(
                    tzinfo=timezone.utc
                )
                window_idx = map_to_window(dt, windows)
            except (ValueError, TypeError):
                # Malformed date — exclude this section's markers.
                section_window_idx = None
                continue

            if window_idx == BEFORE_HISTORY:
                # Predates all windows; exclude this section.
                section_window_idx = None
            else:
                section_window_idx = window_idx
            continue

        # Not a sprint header: scan for confidence markers if inside a dated section.
        if section_window_idx is None:
            continue

        for m_marker in _CONFIDENCE_MARKER_RE.finditer(line):
            token = m_marker.group(1)  # "high" or "low"
            bucket = counts.setdefault(section_window_idx, [0, 0])
            if token == "low":
                bucket[0] += 1
            else:  # "high"
                bucket[1] += 1

    # Compute ratio for a given window index.
    def _ratio(idx):
        if idx is None or idx not in counts:
            return "n/a"
        low_c, high_c = counts[idx]
        total = low_c + high_c
        if total == 0:
            return "n/a"
        return round(low_c / total, 2)

    current_val = _ratio(current_idx)
    prior_val = _ratio(prior_idx)

    # Arrow: "→" when either value is the sentinel string (no numeric comparison).
    if current_val == "n/a" or prior_val == "n/a":
        arrow = "→"  # →
    elif current_val > prior_val:
        arrow = "↑"  # ↑
    elif current_val < prior_val:
        arrow = "↓"  # ↓
    else:
        arrow = "→"  # →

    return {"current": current_val, "prior": prior_val, "arrow": arrow}


# ---------------------------------------------------------------------------
# Thin file reader: read_sprint_log  (T-04, not unit-tested)
# ---------------------------------------------------------------------------

def read_sprint_log(path):
    """Read sprint-log.md from `path` and return its text as a single string.

    This is the only function in T-04 that performs file I/O.  It is kept
    intentionally thin — callers pass the result to the pure
    sprint_low_confidence_ratio() function for all business logic.

    Returns an empty string if the file does not exist or cannot be read.
    """
    try:
        with open(path, encoding="utf-8", errors="replace") as fh:
            return fh.read()
    except OSError:
        return ""


# ---------------------------------------------------------------------------
# Public entry point: compute()  (T-06 — AC-07)
# ---------------------------------------------------------------------------

import os as _os


def compute(project_dir, window_size=DEFAULT_WINDOW_SIZE, *, _timeline=None):
    """Compute all three governance metrics for `project_dir` and return them.

    This is the single public entry point the ``/ca:metrics`` command calls.
    It ties the window-tiling, log-reading, and metric-computation layers
    together and returns a fixed-surface dict.

    Args:
        project_dir: absolute path to the project root (the directory that
                     contains ``.codearbiter/``).  The git repository at this
                     path (or any of its parents) is used for the commit
                     timeline when ``_timeline`` is not supplied.
        window_size: number of commits per window (default 20).
        _timeline:   [testability seam] optional list[datetime] injected in
                     place of ``commit_timeline(project_dir)``.  When None
                     (the default), the real git wrapper is called.  Tests
                     pass a synthetic timeline to keep the suite hermetic.
                     This parameter is keyword-only and intentionally not part
                     of the public /ca:metrics API surface — callers should
                     omit it.

    Returns:
        dict with EXACTLY these three keys and no others:
            "override_rate"       — result of override_rate(...)
            "small_lane_rate"     — result of small_lane_rate(...)
            "sprint_low_conf_ratio" — result of sprint_low_confidence_ratio(...)

        Each sub-value is a dict with keys "current", "prior", "arrow".

    Degradation contract:
        The function is READ-ONLY.  It never writes, creates, or modifies any
        file.  On any missing resource (logs absent, .codearbiter/ not found,
        git unavailable, etc.) the affected sub-metric returns its sentinel
        (counts 0 / ratio "n/a") and the function never raises.
    """
    # -- Step 1: build the commit timeline and tile it into windows.
    # The injected _timeline seam replaces the git call when testing.
    try:
        if _timeline is not None:
            timeline = list(_timeline)
        else:
            timeline = commit_timeline(project_dir)
        windows = tile_windows(timeline, window_size=window_size)
    except Exception:  # noqa: BLE001 — never crash regardless of git state
        windows = []

    # -- Step 2: resolve log paths under <project_dir>/.codearbiter/
    ca_dir = _os.path.join(project_dir, ".codearbiter")
    override_path = _os.path.join(ca_dir, "overrides.log")
    triage_path   = _os.path.join(ca_dir, "triage.log")
    sprint_path   = _os.path.join(ca_dir, "sprint-log.md")

    # -- Step 3: read each log (thin readers degrade to empty on missing files).
    override_lines = read_override_log(override_path)
    triage_lines   = read_triage_log(triage_path)
    sprint_text    = read_sprint_log(sprint_path)

    # -- Step 4: compute the three metrics and assemble the fixed output dict.
    return {
        "override_rate":        override_rate(override_lines, windows),
        "small_lane_rate":      small_lane_rate(triage_lines, windows),
        "sprint_low_conf_ratio": sprint_low_confidence_ratio(sprint_text, windows),
    }
