#!/usr/bin/env python3
"""codeArbiter — unit tests for the mode-plane READERS (#437,
mode-plane-deterministic-flip, Lane F / T-51, T-52, T-53, T-55).

Lane F's job is not the mode plane itself (Lane A's `_modelib.py`) but the
surfaces that RENDER off it: `_arbiterstatelib.current_mode` (T-51),
`statusline.py`'s badge/redshift and override counter (T-52/T-55), and
`_hooklib._STALE_FLOWS` (T-53). Imports every module straight from
`core/pysrc` (GR-4 precedent: test_prune_policy_parity.py / test_modelib.py)
so this suite is [LL] — it never depends on the vendored `plugins/*/hooks/`
copies `sync-core.py` produces, and needs no write-mode regeneration to run.

Two hazards this file exists to catch, named in the Lane F brief:
  1. `_hooklib._STALE_FLOWS` is a WARN, not a gate — a matcher that still
     names the retired 'dev-active' marker (or one that warns on ANY mode
     marker presence, arbiter included) goes permanently silent with an
     otherwise green suite. TestStaleFlowsModeAware asserts BOTH directions.
  2. A statusline test that only checks "not arbiter" would pass even if
     `dangerous` and `ops` rendered identically to each other.
     TestStatuslineDistinctModeRendering asserts the actual distinct bytes,
     not an absence.

Stdlib only. Exit 0 = all tests pass; non-zero = failure.
"""

import json
import os
import re
import sys
import tempfile
import unittest
from unittest import mock

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
CORE = os.path.join(ROOT, "core", "pysrc")
sys.path.insert(0, CORE)

import _activationlib  # noqa: E402
import _arbiterstatelib  # noqa: E402
import _hooklib  # noqa: E402
import _modelib  # noqa: E402
import statusline  # noqa: E402


def _write_mode_file(root, entries):
    """Seed `<root>/.codearbiter/.markers/mode` with `entries`
    ({session_id: mode}), creating the directory tree as needed."""
    markers = os.path.join(root, ".codearbiter", ".markers")
    os.makedirs(markers, exist_ok=True)
    with open(os.path.join(markers, "mode"), "w", encoding="utf-8") as f:
        f.write(json.dumps(entries))


def _age(path, age_seconds):
    t = os.path.getmtime(path) - age_seconds if os.path.exists(path) else None
    if t is None:
        return
    os.utime(path, (t, t))


def _isolated_render_env(tmp_root, project_root, extra=None):
    """A `mock.patch.dict` context that pins EVERY user-global state seam
    `statusline.py` touches (ledger, update-notifier cache, ~) at a fresh
    directory under `tmp_root`, alongside CLAUDE_PROJECT_DIR (mirrors the
    #442 fix in plugins/ca/hooks/tests/_helpers.isolate_user_state — a bare
    CLAUDE_PROJECT_DIR patch is not enough: statusline.render() reads
    ~/.codearbiter/ledger.json and ~/.codearbiter's update-cache directly,
    and a test that skips this WILL read and write the real developer's
    ledger, as an earlier draft of this file did before this helper existed
    — caught by an unexpectedly non-zero "Today" usage row in a supposedly
    hermetic render). `extra` merges in additional env overrides (e.g. a
    pinned CODEARBITER_WIDTH) without duplicating the isolation set."""
    home = os.path.join(tmp_root, "home")
    os.makedirs(home, exist_ok=True)
    env = {
        "CLAUDE_PROJECT_DIR": project_root,
        "HOME": home,
        "USERPROFILE": home,
        "CODEARBITER_LEDGER": os.path.join(home, "ledger.json"),
        "CODEARBITER_UPDATE_STATE": os.path.join(home, "update-state.json"),
    }
    if extra:
        env.update(extra)
    return mock.patch.dict(os.environ, env, clear=False)


# ---------------------------------------------------------------------------
# T-51 — _arbiterstatelib.current_mode
# ---------------------------------------------------------------------------
class TestCurrentModeReaderRoutesThroughModelib(unittest.TestCase):
    """`_arbiterstatelib.current_mode` must be a thin pass-through to
    `_modelib.current_mode` — never its own re-implementation of mode
    resolution — so it inherits `_modelib`'s marker_root routing (AC-5)
    verbatim rather than drifting from it. Proven by call-args, not
    behavior: a mutant that hand-rolls its own JSON read here would still
    happen to work in the common case but silently diverge on marker_root
    escalation, session-scoping edge cases, or diagnostic handling — all of
    which `_modelib.current_mode` already owns and is separately tested."""

    def test_forwards_session_id_root_and_payload_verbatim(self):
        sentinel_root = "/sentinel/root"
        sentinel_payload = {"cwd": "/sentinel/cwd"}
        with mock.patch.object(
            _arbiterstatelib, "_modelib_current_mode",
            return_value=("dangerous", None),
        ) as spy:
            result = _arbiterstatelib.current_mode(
                "sess-1", root=sentinel_root, payload=sentinel_payload)
        spy.assert_called_once_with(
            "sess-1", root=sentinel_root, payload=sentinel_payload)
        self.assertEqual(result, "dangerous")

    def test_returns_only_the_mode_half_not_the_diagnostic(self):
        with mock.patch.object(
            _arbiterstatelib, "_modelib_current_mode",
            return_value=("arbiter", _modelib.MODE_DIAG_UNREADABLE),
        ):
            result = _arbiterstatelib.current_mode("sess-1", root="/x")
        self.assertEqual(result, "arbiter")  # not a tuple, not the diagnostic


class TestCurrentModeReaderIntegration(unittest.TestCase):
    """End-to-end against a real marker file (the explicit-`root` escape
    hatch, mirroring `_modelib.current_mode`'s own test-only contract) —
    proves the three modes resolve to three DISTINCT tokens, not just
    "truthy vs. falsy" the way the retired boolean `dev_active` did."""

    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.root = self._tmp.name

    def tearDown(self):
        self._tmp.cleanup()

    def test_three_sessions_three_distinct_modes(self):
        _write_mode_file(self.root, {
            "sess-arbiter": "arbiter",
            "sess-dangerous": "dangerous",
            "sess-ops": "ops",
        })
        modes = {
            sid: _arbiterstatelib.current_mode(sid, root=self.root)
            for sid in ("sess-arbiter", "sess-dangerous", "sess-ops")
        }
        self.assertEqual(modes["sess-arbiter"], "arbiter")
        self.assertEqual(modes["sess-dangerous"], "dangerous")
        self.assertEqual(modes["sess-ops"], "ops")
        # the whole point of a 3-value plane: pairwise distinct, not a bool
        self.assertEqual(len(set(modes.values())), 3)

    def test_unknown_session_resolves_arbiter(self):
        _write_mode_file(self.root, {"sess-dangerous": "dangerous"})
        self.assertEqual(
            _arbiterstatelib.current_mode("sess-never-flipped", root=self.root),
            "arbiter")

    def test_absent_marker_resolves_arbiter(self):
        self.assertEqual(
            _arbiterstatelib.current_mode("sess-1", root=self.root), "arbiter")


# ---------------------------------------------------------------------------
# T-53 — _hooklib._STALE_FLOWS / staleness_warning, mode-aware
# ---------------------------------------------------------------------------
class TestStaleFlowsModeAware(unittest.TestCase):
    """AC-36: `_STALE_FLOWS` warns for a stale non-arbiter mode and NEVER
    warns for arbiter. This is a WARN, not a gate — the hazard named in the
    Lane F brief is that a matcher still keyed on the retired 'dev-active'
    marker goes permanently silent with a green suite, and nothing else in
    this repo would ever notice. Both directions are asserted; the negative
    arm is what catches a matcher that (wrongly) warns on ANY marker
    presence, arbiter included."""

    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.root = self._tmp.name
        self.cad = os.path.join(self.root, ".codearbiter")
        os.makedirs(self.cad)

    def tearDown(self):
        self._tmp.cleanup()

    def _mode_marker_path(self):
        return os.path.join(self.cad, ".markers", "mode")

    def test_stale_dangerous_session_warns(self):
        _write_mode_file(self.root, {"sess-1": "dangerous"})
        _age(self._mode_marker_path(), age_seconds=3600)  # 60 min, past the 30-min default window
        messages = _hooklib.staleness_warning(self.root, window_minutes=30)
        self.assertTrue(any("mode" in m for m in messages), messages)

    def test_stale_ops_session_warns(self):
        _write_mode_file(self.root, {"sess-1": "ops"})
        _age(self._mode_marker_path(), age_seconds=3600)
        messages = _hooklib.staleness_warning(self.root, window_minutes=30)
        self.assertTrue(any("mode" in m for m in messages), messages)

    def test_stale_arbiter_only_marker_never_warns(self):
        # AC-36 negative arm: the marker file EXISTS and IS old, but every
        # session in it is 'arbiter' — a matcher keying on presence alone
        # (the shape of the old dev-active boolean check) would wrongly warn
        # here. This is the case that catches that mutant.
        _write_mode_file(self.root, {"sess-1": "arbiter", "sess-2": "arbiter"})
        _age(self._mode_marker_path(), age_seconds=3600)
        messages = _hooklib.staleness_warning(self.root, window_minutes=30)
        self.assertEqual(messages, [])

    def test_fresh_dangerous_session_does_not_warn_yet(self):
        _write_mode_file(self.root, {"sess-1": "dangerous"})
        _age(self._mode_marker_path(), age_seconds=5)  # well inside the window
        messages = _hooklib.staleness_warning(self.root, window_minutes=30)
        self.assertEqual(messages, [])

    def test_no_marker_file_never_warns(self):
        messages = _hooklib.staleness_warning(self.root, window_minutes=30)
        self.assertEqual(messages, [])

    def test_recent_overrides_log_activity_suppresses_the_warn(self):
        _write_mode_file(self.root, {"sess-1": "dangerous"})
        _age(self._mode_marker_path(), age_seconds=3600)
        with open(os.path.join(self.cad, "overrides.log"), "w", encoding="utf-8") as f:
            f.write("[recent] | BY: session-mode | MODE: dangerous enter | NOTE: -\n")
        # overrides.log itself is fresh (just written) -> last_activity is recent
        messages = _hooklib.staleness_warning(self.root, window_minutes=30)
        self.assertEqual(messages, [])

    def test_never_raises_on_corrupt_mode_marker(self):
        markers = os.path.join(self.cad, ".markers")
        os.makedirs(markers)
        with open(os.path.join(markers, "mode"), "w", encoding="utf-8") as f:
            f.write("{not valid json")
        _age(self._mode_marker_path(), age_seconds=3600)
        messages = _hooklib.staleness_warning(self.root, window_minutes=30)
        self.assertEqual(messages, [])  # corrupt -> nothing provably active, never raises


class TestStaleFlowsReadsPerSessionEntries(unittest.TestCase):
    """(#681) The same AC-36 contract, driven through `write_mode` rather than
    a hand-seeded legacy map.

    The class above still seeds `.markers/mode` directly, which is now the
    PRE-SPLIT shape nothing writes any more. Left alone, every one of those
    cases would keep passing while the matcher no longer saw a single live
    session — the permanently-silent WARN the Lane F brief names, arrived at
    from a new direction. These cases go through the writer the running code
    uses, so the registry is measured against state a real session produces.
    """

    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.root = self._tmp.name
        self.cad = os.path.join(self.root, ".codearbiter")
        os.makedirs(self.cad)

    def tearDown(self):
        self._tmp.cleanup()

    def _entry(self, session_id):
        return _modelib.mode_entry_path(session_id, root=self.root)

    def test_stale_dangerous_session_warns(self):
        _modelib.write_mode("sess-1", "dangerous", root=self.root)
        _age(self._entry("sess-1"), age_seconds=3600)
        messages = _hooklib.staleness_warning(self.root, window_minutes=30)
        self.assertTrue(any("mode" in m for m in messages), messages)

    def test_stale_ops_session_warns(self):
        _modelib.write_mode("sess-1", "ops", root=self.root)
        _age(self._entry("sess-1"), age_seconds=3600)
        messages = _hooklib.staleness_warning(self.root, window_minutes=30)
        self.assertTrue(any("mode" in m for m in messages), messages)

    def test_stale_arbiter_only_entries_never_warn(self):
        for sid in ("sess-1", "sess-2"):
            _modelib.write_mode(sid, "arbiter", root=self.root)
            _age(self._entry(sid), age_seconds=3600)
        self.assertEqual(_hooklib.staleness_warning(self.root, window_minutes=30), [])

    def test_fresh_dangerous_session_does_not_warn_yet(self):
        _modelib.write_mode("sess-1", "dangerous", root=self.root)
        _age(self._entry("sess-1"), age_seconds=5)
        self.assertEqual(_hooklib.staleness_warning(self.root, window_minutes=30), [])

    def test_another_sessions_flip_no_longer_resets_this_sessions_clock(self):
        """The accuracy the split buys, asserted so it cannot regress.

        Under the shared map, ANY session's write bumped the one file's mtime,
        so an unrelated session starting up reset the staleness clock for a
        session sitting in `dangerous` — the warning could be deferred forever
        by traffic that had nothing to do with it. Per-session entries make the
        timestamp the flipping session's own.
        """
        _modelib.write_mode("stale-one", "dangerous", root=self.root)
        _age(self._entry("stale-one"), age_seconds=3600)
        _modelib.write_mode("busy-one", "arbiter", root=self.root)   # fresh, unrelated
        messages = _hooklib.staleness_warning(self.root, window_minutes=30)
        self.assertTrue(any("mode" in m for m in messages),
                        "an unrelated session's write suppressed a stale "
                        "dangerous session's warning")

    def test_the_newest_non_arbiter_entry_sets_the_clock_not_the_oldest(self):
        """With several non-arbiter sessions, staleness is judged from the most
        recent one — the oldest must not trip a warn on its own.

        The scan reads newest-first and stops at the first non-arbiter entry, so
        an ordering bug here would silently answer with whichever entry the
        filesystem happened to list first.
        """
        _modelib.write_mode("old-one", "dangerous", root=self.root)
        _age(self._entry("old-one"), age_seconds=3600)
        _modelib.write_mode("new-one", "dangerous", root=self.root)   # fresh
        self.assertEqual(_hooklib.staleness_warning(self.root, window_minutes=30), [],
                         "an old entry decided the clock while a newer session "
                         "in the same posture was still active")
        _age(self._entry("new-one"), age_seconds=3600)
        self.assertTrue(
            any("mode" in m for m in _hooklib.staleness_warning(self.root, window_minutes=30)),
            "once every non-arbiter entry is old, the warn must fire")

    def test_corrupt_entry_never_raises_and_proves_nothing_active(self):
        _modelib.write_mode("sess-1", "dangerous", root=self.root)
        with open(self._entry("sess-1"), "w", encoding="utf-8") as f:
            f.write("{not valid json")
        _age(self._entry("sess-1"), age_seconds=3600)
        self.assertEqual(_hooklib.staleness_warning(self.root, window_minutes=30), [])


# ---------------------------------------------------------------------------
# T-55 — override counter excludes MODE:/legacy DEV: rows
# ---------------------------------------------------------------------------
class TestOverrideCounterExcludesModeRows(unittest.TestCase):
    """AC-40: the statusline's override counter (`arbiter_state()["over"]`,
    rendered as `over:N`) must exclude MODE:/legacy DEV: ledger rows. Mode
    transitions are about to become routine traffic in overrides.log, so an
    uncorrected counter goes from noisy to actively WRONG — a governance
    metric a maintainer might act on."""

    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.root = self._tmp.name
        self.cad = os.path.join(self.root, ".codearbiter")
        os.makedirs(self.cad)
        with open(os.path.join(self.cad, "CONTEXT.md"), "w", encoding="utf-8") as f:
            f.write("---\narbiter: enabled\nstage: build\n---\n# ctx\n")

    def tearDown(self):
        self._tmp.cleanup()

    def _write_log(self, lines):
        with open(os.path.join(self.cad, "overrides.log"), "w", encoding="utf-8") as f:
            f.write("\n".join(lines) + "\n")

    def test_mode_and_legacy_dev_rows_alone_count_zero(self):
        self._write_log([
            "[2026-08-11T10:00:00Z] | BY: session-mode | HOST: claude | MODE: dangerous enter | NOTE: -",
            "[2026-08-11T10:05:00Z] | BY: session-mode | HOST: claude | MODE: dangerous exit | NOTE: -",
            "[2026-01-01T00:00:00Z] | BY: dev | DEV: enter | NOTE: -",
            "[2026-01-01T01:00:00Z] | BY: dev | DEV: exit | NOTE: -",
        ])
        state = _arbiterstatelib.arbiter_state(self.root)
        self.assertIsNotNone(state)
        self.assertEqual(state["over"], 0)

    def test_a_genuine_override_row_still_counts(self):
        self._write_log([
            "[2026-08-11T10:00:00Z] | BY: session-mode | HOST: claude | MODE: dangerous enter | NOTE: -",
            "[2026-08-11T10:01:00Z] | BY: user | GATE: H-05 | NOTE: manual override",
        ])
        state = _arbiterstatelib.arbiter_state(self.root)
        self.assertEqual(state["over"], 1)

    def test_a_note_merely_mentioning_mode_is_not_excluded(self):
        # The exclusion is a pipe-delimited FIELD match, not a substring
        # search — a genuine override whose NOTE happens to say "mode" or
        # "dev" must still count. This is the case that catches a mutant
        # that over-broadens the exclusion to any line containing "mode".
        self._write_log([
            "[2026-08-11T10:00:00Z] | BY: user | GATE: H-19 | NOTE: dev requested a mode change",
        ])
        state = _arbiterstatelib.arbiter_state(self.root)
        self.assertEqual(state["over"], 1)

    def test_statusline_render_shows_over_0_for_mode_only_log(self):
        self._write_log([
            "[2026-08-11T10:00:00Z] | BY: session-mode | HOST: claude | MODE: ops enter | NOTE: -",
        ])
        data = {
            "session_id": "sess-1",
            "cwd": self.root,
            "workspace": {"project_dir": self.root},
            "model": {"display_name": "test-model"},
        }
        with _isolated_render_env(self._tmp.name, self.root):
            out = statusline.render(json.dumps(data))
        plain = statusline.ANSI.sub("", out)
        self.assertIn("over:0", plain)


# ---------------------------------------------------------------------------
# T-52 — statusline: three modes, three DISTINCT tested renderings
# ---------------------------------------------------------------------------
class TestStatuslineDistinctModeRendering(unittest.TestCase):
    """AC-38: arbiter/dangerous/ops each render distinctly; arbiter is
    unchanged from today (no badge, no redshift) and dangerous keeps the
    red-shift. Asserted on the ACTUAL rendered bytes — a test that only
    checked "not arbiter" would pass even if dangerous and ops rendered
    identically to each other, which is exactly the gap this class exists
    to close.

    Known local trap: the harness exports NO_COLOR=1, which strips every
    SGR sequence before this test ever sees it and would fake green on
    every color assertion below. Explicitly unset for this class."""

    _TRUECOLOR_RE = re.compile(r"\033\[(?:38|48);2;(\d+);(\d+);(\d+)m")

    def setUp(self):
        self._had_no_color = "NO_COLOR" in os.environ
        self._no_color_val = os.environ.pop("NO_COLOR", None)
        self._tmp = tempfile.TemporaryDirectory()
        self.root = os.path.join(self._tmp.name, "repo")
        os.makedirs(os.path.join(self.root, ".codearbiter"))
        # Full user-state isolation (mirrors #442's fix for the same leak,
        # via the shared `_isolated_render_env` helper): a bare
        # CLAUDE_PROJECT_DIR patch is not enough — statusline.py's
        # ledger/session/update-notifier reads all fall back to the REAL
        # ~/.codearbiter/ and ~/.claude/ otherwise, which would (a) pollute
        # the developer's actual ledger with test session ids and (b) make
        # the three renders below non-reproducible (accumulated ledger state
        # differs run to run), sinking the redshift comparison in incidental
        # drift rather than the property under test.
        self._env_patch = _isolated_render_env(
            self._tmp.name, self.root, extra={"CODEARBITER_WIDTH": "120"})
        self._env_patch.start()
        os.environ.pop("HOMEDRIVE", None)
        os.environ.pop("HOMEPATH", None)

    def tearDown(self):
        self._env_patch.stop()
        if self._had_no_color:
            os.environ["NO_COLOR"] = self._no_color_val
        self._tmp.cleanup()

    def _render_for_mode(self, session_id, mode):
        if mode != "arbiter":
            _write_mode_file(self.root, {session_id: mode})
        data = {
            "session_id": session_id,
            "cwd": self.root,
            "workspace": {"project_dir": self.root},
            "model": {"display_name": "test-model"},
        }
        with mock.patch.object(statusline, "session_start", return_value=1_700_000_000.0):
            return statusline.render(json.dumps(data))

    def test_arbiter_has_no_badge_and_no_redshift(self):
        out = self._render_for_mode("sess-a", "arbiter")
        self.assertNotIn("[DANGEROUS]", out)
        self.assertNotIn("[OPS]", out)
        self.assertNotIn("[DEV]", out)

    def test_dangerous_shows_its_own_badge(self):
        out = self._render_for_mode("sess-d", "dangerous")
        self.assertIn("[DANGEROUS]", out)
        self.assertNotIn("[OPS]", out)

    def test_ops_shows_its_own_badge(self):
        out = self._render_for_mode("sess-o", "ops")
        self.assertIn("[OPS]", out)
        self.assertNotIn("[DANGEROUS]", out)

    def test_dangerous_and_ops_and_arbiter_badges_are_pairwise_distinct(self):
        out_a = self._render_for_mode("sess-a2", "arbiter")
        out_d = self._render_for_mode("sess-d2", "dangerous")
        out_o = self._render_for_mode("sess-o2", "ops")
        self.assertNotEqual(out_a, out_d)
        self.assertNotEqual(out_a, out_o)
        self.assertNotEqual(out_d, out_o)

    def test_dangerous_keeps_the_redshift_arbiter_and_ops_do_not(self):
        # NOTE on approach: comparing the raw truecolor CODE SETS across the
        # three renders is not a valid test on its own — `_boxlib.Box.top`
        # sizes its top-border fill gradient off the BADGE's own width
        # (`fillw = W - 1 - used - 1`, `used` includes `vlen(badge)`), so
        # arbiter ("" badge) and ops ("[OPS]" badge) legitimately produce a
        # DIFFERENT (non-redshifted) code set from each other even with no
        # redshift involved at all — that difference is a badge-width
        # artifact, not evidence of anything about the redshift gate.
        #
        # The actual redshift signature is checked structurally instead:
        # `_segmentslib.redshift`'s repl() always sets the red channel to
        # `min(255, 96 + lum)` (dominant) and green/blue to small fractions
        # of that same `lum` (`lum // 6`, `lum // 7`) — so a redshifted code
        # is always RED-DOMINANT (r > g and r > b). The native neon-violet
        # palette this box otherwise uses is blue-dominant (every sampled
        # gradient stop has b as its largest channel) — the two signatures
        # cannot be confused with each other.
        out_a = self._render_for_mode("sess-a3", "arbiter")
        out_d = self._render_for_mode("sess-d3", "dangerous")
        out_o = self._render_for_mode("sess-o3", "ops")

        def _rgb_triples(out):
            return [(int(r), int(g), int(b)) for r, g, b in self._TRUECOLOR_RE.findall(out)]

        def _red_dominant(triples):
            return [(r, g, b) for r, g, b in triples if r > g and r > b]

        triples_a = _rgb_triples(out_a)
        triples_d = _rgb_triples(out_d)
        triples_o = _rgb_triples(out_o)

        self.assertTrue(triples_a, "expected real truecolor SGR sequences with NO_COLOR unset")
        self.assertTrue(triples_d)
        self.assertTrue(triples_o)

        # dangerous: EVERY truecolor code is red-dominant (redshift touches
        # the whole box, per `_segmentslib.redshift`'s docstring).
        self.assertEqual(_red_dominant(triples_d), triples_d)
        # arbiter/ops: the native violet palette is blue-dominant throughout
        # — NONE of their codes match the redshifted signature.
        self.assertEqual(_red_dominant(triples_a), [])
        self.assertEqual(_red_dominant(triples_o), [])


if __name__ == "__main__":
    unittest.main()
