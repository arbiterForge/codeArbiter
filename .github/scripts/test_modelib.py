#!/usr/bin/env python3
"""Tests for `_modelib`: the mode plane (arbiter/dangerous/ops), its
deterministic token flip, and the write-ahead audit-close ledger that backs
it (#437, mode-plane-deterministic-flip, Lane A / T-06..T-16).

Imports `_modelib` directly from `core/pysrc` (GR-4 precedent:
test_prune_policy_parity.py) so this suite is [LL] — it never depends on the
vendored `plugins/*/hooks/` copies sync-core.py produces."""

import contextlib
import json
import os
import sys
import tempfile
import unittest
from unittest import mock

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
CORE = os.path.join(ROOT, "core", "pysrc")
sys.path.insert(0, CORE)

import _modelib  # noqa: E402
import _prunepolicy  # noqa: E402 — T-16's collision check against MARKER_PREFIX


# ---------------------------------------------------------------------------
# T-06 — ledger extraction (pure refactor, no behavior change)
#
# The two classes below REPLAY, unchanged, the two
# `plugins/ca/hooks/tests/test_session_start.py::TestDevExitRetryablePendingClose`
# cases that call `_settle_dev_close` DIRECTLY (not through the
# SessionStart-specific `clear_dev_marker` wrapper, which stays in
# session-start.py and is out of this module's scope). Assertions are
# byte-for-byte identical to the pre-move originals; only the import target
# changed (`_mod` -> `_modelib`, loaded straight from core/pysrc instead of
# the vendored plugin copy).
# ---------------------------------------------------------------------------
class TestSettleDevCloseLedgerReplay(unittest.TestCase):
    """T-06 proof: `_settle_dev_close` and its pending-close record, moved
    verbatim from session-start.py, still behave identically."""

    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.root = self._tmp.name
        self.ca = os.path.join(self.root, ".codearbiter")
        self.markers = os.path.join(self.ca, ".markers")
        os.makedirs(self.markers)
        self.log = os.path.join(self.ca, "overrides.log")
        self.marker = os.path.join(self.markers, "dev-active")
        self.pending = os.path.join(self.markers, "dev-close-pending.json")
        self._seed_log("[2026-01-01T00:00:00Z] | BY: dev | DEV: enter | NOTE: —\n")

    def tearDown(self):
        self._tmp.cleanup()

    def _seed_log(self, text):
        with open(self.log, "w", encoding="utf-8") as f:
            f.write(text)

    def _read_log(self):
        with open(self.log, encoding="utf-8") as f:
            return f.read()

    def _drop_marker(self):
        with open(self.marker, "w", encoding="utf-8") as f:
            f.write("active\n")

    def _exit_lines(self):
        return [ln for ln in self._read_log().splitlines() if "DEV: exit" in ln]

    @contextlib.contextmanager
    def _append_fails(self):
        """Make ONLY the append-mode open of overrides.log raise OSError."""
        real_open = open

        def fake_open(file, mode="r", *a, **kw):
            if "a" in mode and str(file).endswith("overrides.log"):
                raise OSError("locked")
            return real_open(file, mode, *a, **kw)

        with mock.patch("builtins.open", fake_open):
            yield

    def test_a_freshly_minted_close_is_never_deduped_against_the_trail(self):
        # The dedupe tail scan compares WHOLE LINES, and a close row is
        # timestamped only to the second — so two genuinely distinct closes
        # minted in the same second are byte-identical. The scan exists to stop
        # a crash-after-append REPLAY from landing twice; it must never be
        # applied to the freshly minted line, which by construction cannot
        # already be on the trail. Otherwise the second session's close is
        # swallowed by the first session's owed copy of it.
        same_second = ("[2026-01-01T00:00:07Z] | BY: session-cleanup | HOST: claude "
                       "| DEV: exit | NOTE: cleared by SessionStart\n")
        self._drop_marker()
        with self._append_fails():
            _modelib._settle_dev_close(self.root, marker=self.marker, new_line=same_second)
        self.assertEqual(self._exit_lines(), [], "the first append really did fail")

        self._drop_marker()
        _modelib._settle_dev_close(self.root, marker=self.marker, new_line=same_second)
        self.assertEqual(len(self._exit_lines()), 2,
                         "two owed closes must both land even when the second "
                         "granularity makes their lines identical")
        self.assertFalse(os.path.isfile(self.pending))

    def test_the_pending_close_cap_never_discards_a_close_silently(self):
        # The record is bounded to _DEV_PENDING_CLOSE_MAX, so a long-lived
        # write failure DOES lose the oldest owed rows. That loss must not be
        # silent: it is counted while the log is unwritable and written to the
        # trail as one attributable note the moment the log accepts writes.
        cap = _modelib._DEV_PENDING_CLOSE_MAX
        owed = [
            f"[2026-01-01T00:00:{i:02d}Z] | BY: session-cleanup | HOST: claude "
            f"| DEV: exit | NOTE: owed close {i}\n"
            for i in range(cap + 4)
        ]
        with self._append_fails():
            for line in owed:
                _modelib._settle_dev_close(self.root, new_line=line)

        with open(self.pending, encoding="utf-8") as f:
            rec = json.load(f)
        self.assertEqual(len(rec.get("lines") or []), cap, "the record stays bounded")
        self.assertEqual(rec.get("dropped"), 4,
                         "every discarded close row must be counted, not forgotten")

        # overrides.log becomes writable again: the owed rows AND the note land.
        _modelib._settle_dev_close(self.root)
        self.assertEqual(len(self._exit_lines()), cap,
                         "every retained owed close must land exactly once")
        notes = [ln for ln in self._read_log().splitlines()
                 if "DEV: close-dropped" in ln]
        self.assertEqual(len(notes), 1,
                         "the discarded closes must be reported once on the trail")
        self.assertIn("4", notes[0], "the note must carry how many were discarded")
        self.assertFalse(os.path.isfile(self.pending))


# ---------------------------------------------------------------------------
# T-07 — MODES tuple; absent/empty/unreadable/garbage -> arbiter, with
# unreadable and absent emitting DIFFERENT diagnostic strings.
# ---------------------------------------------------------------------------
class TestModesTuple(unittest.TestCase):
    def test_modes_is_exactly_arbiter_dangerous_ops(self):
        self.assertEqual(_modelib.MODES, ("arbiter", "dangerous", "ops"))


class TestCurrentModeResolution(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.root = self._tmp.name
        self.markers = os.path.join(self.root, ".codearbiter", ".markers")
        os.makedirs(self.markers)
        self.mode_path = os.path.join(self.markers, "mode")

    def tearDown(self):
        self._tmp.cleanup()

    def test_absent_marker_resolves_arbiter_with_absent_diagnostic(self):
        mode, diag = _modelib.current_mode("sess-1", root=self.root)
        self.assertEqual(mode, "arbiter")
        self.assertEqual(diag, _modelib.MODE_DIAG_ABSENT)

    def test_empty_marker_resolves_arbiter(self):
        with open(self.mode_path, "w", encoding="utf-8") as f:
            f.write("")
        mode, diag = _modelib.current_mode("sess-1", root=self.root)
        self.assertEqual(mode, "arbiter")
        self.assertIsNotNone(diag)

    def test_unreadable_marker_resolves_arbiter_with_unreadable_diagnostic(self):
        # Portable, no-chmod-needed stand-in for "OSError other than
        # FileNotFoundError" (precedent: test_release_lib.py
        # UnreadableTargetsFileTest): a directory can never be open()'d as a
        # file on any platform.
        os.makedirs(self.mode_path)
        mode, diag = _modelib.current_mode("sess-1", root=self.root)
        self.assertEqual(mode, "arbiter")
        self.assertEqual(diag, _modelib.MODE_DIAG_UNREADABLE)

    def test_unreadable_and_absent_diagnostics_are_distinct_strings(self):
        # [[never-fold-unreadable-into-absent]]: this is the house-rule
        # assertion itself — two DIFFERENT strings, not two truthy values.
        _mode_absent, diag_absent = _modelib.current_mode("sess-1", root=self.root)
        os.makedirs(self.mode_path)
        _mode_unreadable, diag_unreadable = _modelib.current_mode("sess-1", root=self.root)
        self.assertNotEqual(diag_absent, diag_unreadable)
        self.assertIsInstance(diag_absent, str)
        self.assertIsInstance(diag_unreadable, str)

    def test_garbage_json_resolves_arbiter(self):
        with open(self.mode_path, "w", encoding="utf-8") as f:
            f.write("{not json")
        mode, diag = _modelib.current_mode("sess-1", root=self.root)
        self.assertEqual(mode, "arbiter")
        self.assertIsNotNone(diag)

    def test_unknown_mode_value_for_session_resolves_arbiter(self):
        with open(self.mode_path, "w", encoding="utf-8") as f:
            json.dump({"sess-1": "prototype"}, f)
        mode, diag = _modelib.current_mode("sess-1", root=self.root)
        self.assertEqual(mode, "arbiter")
        self.assertEqual(diag, _modelib.MODE_DIAG_UNRECOGNIZED,
                          "a garbage per-session value is an anomaly worth "
                          "reporting, not a silent default")

    def test_recognized_value_round_trips_with_no_diagnostic(self):
        with open(self.mode_path, "w", encoding="utf-8") as f:
            json.dump({"sess-1": "dangerous"}, f)
        mode, diag = _modelib.current_mode("sess-1", root=self.root)
        self.assertEqual(mode, "dangerous")
        self.assertIsNone(diag)

    def test_fresh_session_with_no_entry_in_an_otherwise_clean_file_is_not_an_anomaly(self):
        with open(self.mode_path, "w", encoding="utf-8") as f:
            json.dump({"sess-OTHER": "dangerous"}, f)
        mode, diag = _modelib.current_mode("sess-1", root=self.root)
        self.assertEqual(mode, "arbiter")
        self.assertIsNone(diag)


# ---------------------------------------------------------------------------
# T-08 — write_mode routes through write_text_atomic; an interrupted write
# leaves no partial file and no orphaned temp (AC-1).
# ---------------------------------------------------------------------------
class TestWriteMode(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.root = self._tmp.name
        self.markers = os.path.join(self.root, ".codearbiter", ".markers")
        self.mode_path = os.path.join(self.markers, "mode")

    def tearDown(self):
        self._tmp.cleanup()

    def test_write_mode_delegates_to_write_text_atomic(self):
        # The spy: write_mode must not do its own open()/write() -- it must
        # route through write_text_atomic, the module's one atomic-write
        # primitive (mkstemp + os.replace).
        with mock.patch("_modelib.write_text_atomic") as spy:
            ok = _modelib.write_mode("sess-1", "dangerous", root=self.root)
        self.assertTrue(ok)
        spy.assert_called_once()
        args, kwargs = spy.call_args
        self.assertEqual(args[0], self.mode_path)
        self.assertIn("dangerous", args[1])
        self.assertEqual(kwargs.get("newline"), "\n")

    def test_a_real_write_round_trips_through_current_mode(self):
        ok = _modelib.write_mode("sess-1", "dangerous", root=self.root)
        self.assertTrue(ok)
        mode, diag = _modelib.current_mode("sess-1", root=self.root)
        self.assertEqual(mode, "dangerous")
        self.assertIsNone(diag)

    def test_interrupted_write_leaves_no_file_and_no_temp(self):
        os.makedirs(self.markers)
        with mock.patch("_modelib.write_text_atomic", side_effect=OSError("disk full")):
            ok = _modelib.write_mode("sess-1", "dangerous", root=self.root)
        self.assertFalse(ok)
        self.assertFalse(os.path.isfile(self.mode_path),
                         "an interrupted write must leave no partial mode file")
        leftovers = [n for n in os.listdir(self.markers) if n.endswith(".tmp")]
        self.assertEqual(leftovers, [], "no orphaned temp file may survive a failed write")


# ---------------------------------------------------------------------------
# T-09 — the mode is session-keyed: a flip in one session does not change the
# mode resolved by a different, concurrently live session in the same repo
# (AC-3).
# ---------------------------------------------------------------------------
class TestSessionKeying(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.root = self._tmp.name

    def tearDown(self):
        self._tmp.cleanup()

    def test_flipping_one_session_does_not_change_a_different_sessions_mode(self):
        # B is seeded BEFORE A flips, so a mutant that rebuilds the marker's
        # state from scratch on every write_mode call (dropping every OTHER
        # session's entry) is individually caught here, not just by the
        # sibling "two sessions simultaneously" test below.
        _modelib.write_mode("sess-B", "ops", root=self.root)
        ok = _modelib.write_mode("sess-A", "dangerous", root=self.root)
        self.assertTrue(ok)
        mode_a, _ = _modelib.current_mode("sess-A", root=self.root)
        mode_b, diag_b = _modelib.current_mode("sess-B", root=self.root)
        self.assertEqual(mode_a, "dangerous")
        self.assertEqual(mode_b, "ops",
                         "flipping A must not clobber B's already-recorded mode")
        self.assertIsNone(diag_b, "B's recorded value is not an anomaly")

    def test_two_sessions_hold_independent_modes_simultaneously(self):
        _modelib.write_mode("sess-A", "dangerous", root=self.root)
        _modelib.write_mode("sess-B", "ops", root=self.root)
        mode_a, _ = _modelib.current_mode("sess-A", root=self.root)
        mode_b, _ = _modelib.current_mode("sess-B", root=self.root)
        self.assertEqual(mode_a, "dangerous")
        self.assertEqual(mode_b, "ops")


# ---------------------------------------------------------------------------
# T-10 — the mode marker resolves through `marker_root`, NOT `project_root`,
# so a linked worktree and its main checkout agree (#604). Asserted on the
# resolved PATH by mocking `_modelib.marker_root` to a distinct sentinel
# root and confirming mode_marker_path() used exactly that value -- the same
# escalation every other `.codearbiter/.markers/` writer in this repo
# already depends on (security-pass.py, migration-pass.py).
# ---------------------------------------------------------------------------
class TestModeMarkerResolvesThroughMarkerRoot(unittest.TestCase):
    def test_mode_marker_path_uses_marker_root_return_value(self):
        with mock.patch("_modelib.marker_root", return_value="/main-checkout") as spy:
            path = _modelib.mode_marker_path()
        spy.assert_called_once()
        self.assertEqual(
            path,
            os.path.join("/main-checkout", ".codearbiter", ".markers", "mode"))

    def test_worktree_and_main_checkout_agree_because_both_resolve_via_marker_root(self):
        # Simulate the #604 scenario directly: a linked worktree's OWN
        # checkout would resolve a different project_root, but marker_root
        # escalates both to the SAME main-checkout path. _modelib never even
        # imports project_root -- it can only ever see the escalated value.
        #
        # The fake tracks WHICH payload it was called with and always answers
        # the same escalated main-checkout path regardless -- so a mutant
        # that reads the payload's cwd directly (bypassing marker_root's
        # actual escalation) would drift the two results apart, while a
        # mutant that ignores marker_root's return value entirely (e.g.
        # falls back to a hardcoded/os.getcwd() path) is caught because that
        # path does not equal the fake's distinctive sentinel value.
        main_checkout = "/repo/main-checkout-ESCALATED-SENTINEL"
        seen_payloads = []

        def fake_marker_root(payload=None):
            seen_payloads.append(payload)
            return main_checkout  # marker_root ALWAYS escalates to the main checkout

        with mock.patch("_modelib.marker_root", side_effect=fake_marker_root):
            from_worktree_session = _modelib.mode_marker_path(payload={"cwd": "/repo/.worktrees/feature"})
            from_main_session = _modelib.mode_marker_path(payload={"cwd": "/repo/main"})

        self.assertEqual(from_worktree_session, from_main_session)
        self.assertEqual(
            from_worktree_session,
            os.path.join(main_checkout, ".codearbiter", ".markers", "mode"),
            "the resolved path must be exactly marker_root's escalated value, "
            "not a payload-derived or hardcoded stand-in")
        self.assertEqual(len(seen_payloads), 2,
                         "marker_root must be consulted on every call -- not cached "
                         "or bypassed for a second payload")

    def test_explicit_root_bypasses_marker_root_for_test_fixture_isolation(self):
        with mock.patch("_modelib.marker_root") as spy:
            path = _modelib.mode_marker_path(root="/fixture-root")
        spy.assert_not_called()
        self.assertEqual(
            path, os.path.join("/fixture-root", ".codearbiter", ".markers", "mode"))


# ---------------------------------------------------------------------------
# T-11 — flip(): a genuine transition writes state + an audit row; a flip to
# the already-active mode is a no-op and appends nothing (AC-6). Verified by
# byte-identity of overrides.log across the no-op flip.
# ---------------------------------------------------------------------------
class TestFlip(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.root = self._tmp.name
        self.log_path = _modelib._overrides_log_path(self.root)

    def tearDown(self):
        self._tmp.cleanup()

    def _read_log_bytes(self):
        try:
            with open(self.log_path, "rb") as f:
                return f.read()
        except FileNotFoundError:
            return b""

    def test_first_flip_transitions_and_appends_one_enter_row(self):
        result = _modelib.flip("sess-1", "dangerous", root=self.root)
        self.assertEqual(result, _modelib.FLIP_FLIPPED)
        mode, diag = _modelib.current_mode("sess-1", root=self.root)
        self.assertEqual(mode, "dangerous")
        self.assertIsNone(diag)
        log = self._read_log_bytes().decode("utf-8")
        self.assertEqual(log.count("MODE: dangerous enter"), 1)

    def test_double_flip_to_the_same_mode_is_a_noop_with_byte_identical_log(self):
        first = _modelib.flip("sess-1", "dangerous", root=self.root)
        self.assertEqual(first, _modelib.FLIP_FLIPPED)
        after_first = self._read_log_bytes()

        second = _modelib.flip("sess-1", "dangerous", root=self.root)
        self.assertEqual(second, _modelib.FLIP_NOOP)
        after_second = self._read_log_bytes()

        self.assertEqual(after_first, after_second,
                         "a no-op flip must not append any audit row")

    def test_flip_to_the_default_arbiter_when_already_arbiter_is_also_a_noop(self):
        # Freshly-resolved default is "arbiter" with no marker file at all --
        # flipping to arbiter must still be recognised as a no-op rather than
        # writing a redundant marker/audit row.
        result = _modelib.flip("sess-1", "arbiter", root=self.root)
        self.assertEqual(result, _modelib.FLIP_NOOP)
        self.assertEqual(self._read_log_bytes(), b"")


# ---------------------------------------------------------------------------
# T-12 — token table: exact + whitespace/case variants match; embedded and
# multiline prompts do NOT; bare `mode` -> the report sentinel (AC-8/AC-9).
# ---------------------------------------------------------------------------
class TestMatchModeToken(unittest.TestCase):
    def test_exact_lowercase_token_matches(self):
        self.assertEqual(_modelib.match_mode_token("mode --dangerous"), "dangerous")

    def test_case_and_surrounding_whitespace_insensitive(self):
        self.assertEqual(_modelib.match_mode_token("  MODE --DANGEROUS  "), "dangerous")
        self.assertEqual(_modelib.match_mode_token("\tMode --Arbiter\n"), "arbiter")

    def test_all_three_modes_match(self):
        for name in _modelib.MODES:
            self.assertEqual(_modelib.match_mode_token(f"mode --{name}"), name)

    def test_substring_embedding_does_not_match(self):
        self.assertIsNone(_modelib.match_mode_token("please run mode --dangerous later"))

    def test_multiline_prompt_does_not_match(self):
        self.assertIsNone(_modelib.match_mode_token("hi\nmode --dangerous"))
        self.assertIsNone(_modelib.match_mode_token("mode --dangerous\nplease"))

    def test_bare_mode_returns_report_sentinel(self):
        self.assertEqual(_modelib.match_mode_token("mode"), _modelib.MODE_TOKEN_REPORT)
        self.assertEqual(_modelib.match_mode_token("  MODE  "), _modelib.MODE_TOKEN_REPORT)

    def test_unrelated_prompt_returns_none(self):
        self.assertIsNone(_modelib.match_mode_token("what does this codebase do?"))
        self.assertIsNone(_modelib.match_mode_token(""))
        self.assertIsNone(_modelib.match_mode_token("mode --prototype"))

    def test_the_same_exact_match_control_flips_on_a_substring(self):
        # T-27/T-28's own contract, pinned here at the pure-logic layer: the
        # SAME underlying matcher must both accept the exact-match control and
        # reject the substring variant of the identical token.
        exact = "mode --ops"
        embedded = "well, mode --ops then"
        self.assertEqual(_modelib.match_mode_token(exact), "ops")
        self.assertIsNone(_modelib.match_mode_token(embedded))


# ---------------------------------------------------------------------------
# T-13 — ledger_backs(): False without a matching row; True on `MODE:` and
# on legacy `DEV:` rows -- but the legacy acceptance is DANGEROUS-ONLY
# (AC-11).
# ---------------------------------------------------------------------------
class TestLedgerBacks(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.root = self._tmp.name
        os.makedirs(os.path.join(self.root, ".codearbiter"))
        self.log = os.path.join(self.root, ".codearbiter", "overrides.log")

    def tearDown(self):
        self._tmp.cleanup()

    def _seed(self, text):
        with open(self.log, "w", encoding="utf-8") as f:
            f.write(text)

    def test_absent_log_does_not_back_anything(self):
        self.assertFalse(_modelib.ledger_backs(self.root, "dangerous"))

    def test_empty_log_does_not_back_anything(self):
        self._seed("")
        self.assertFalse(_modelib.ledger_backs(self.root, "dangerous"))

    def test_unrelated_row_does_not_back_the_mode(self):
        self._seed("[2026-01-01T00:00:00Z] | BY: dev | SECURITY-OVERRIDE | NOTE: —\n")
        self.assertFalse(_modelib.ledger_backs(self.root, "dangerous"))

    def test_matching_mode_enter_row_backs_the_mode(self):
        self._seed("[2026-01-01T00:00:00Z] | BY: session-mode | MODE: dangerous enter | NOTE: —\n")
        self.assertTrue(_modelib.ledger_backs(self.root, "dangerous"))

    def test_a_different_modes_enter_row_does_not_back_this_mode(self):
        self._seed("[2026-01-01T00:00:00Z] | BY: session-mode | MODE: ops enter | NOTE: —\n")
        self.assertFalse(_modelib.ledger_backs(self.root, "dangerous"))

    def test_legacy_dev_enter_row_backs_dangerous(self):
        self._seed("[2026-01-01T00:00:00Z] | BY: dev | DEV: enter | NOTE: —\n")
        self.assertTrue(_modelib.ledger_backs(self.root, "dangerous"))

    def test_legacy_dev_enter_row_never_backs_ops(self):
        # ops did not exist when any DEV: row could have been minted -- a
        # legacy row authorizing it would be a fail-open into an
        # unrequested mode. This is THE mutant-killer for the legacy branch.
        self._seed("[2026-01-01T00:00:00Z] | BY: dev | DEV: enter | NOTE: —\n")
        self.assertFalse(_modelib.ledger_backs(self.root, "ops"))

    def test_legacy_dev_enter_row_never_backs_arbiter(self):
        self._seed("[2026-01-01T00:00:00Z] | BY: dev | DEV: enter | NOTE: —\n")
        self.assertFalse(_modelib.ledger_backs(self.root, "arbiter"))


# ---------------------------------------------------------------------------
# T-14 — the fail direction is asymmetric (AC-10): a failed flip TO
# dangerous must leave gates ON (resolves arbiter); a flip BACK to arbiter
# must never wedge the session. The unwritable-markers-dir fixture is
# portable everywhere via a write_text_atomic mock (chmod-based
# unwritability is unreliable on Windows -- precedent: test_sync_core.py's
# `IS_WINDOWS` skip) with a REAL chmod 500 arm added for POSIX CI.
# ---------------------------------------------------------------------------
class TestFlipFailsSafeUnderAnUnwritableMarkersDir(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.root = self._tmp.name

    def tearDown(self):
        self._tmp.cleanup()

    def test_flip_to_dangerous_under_write_failure_reports_failure_and_stays_arbiter(self):
        with mock.patch("_modelib.write_text_atomic", side_effect=OSError("no write perm")):
            result = _modelib.flip("sess-1", "dangerous", root=self.root)
        self.assertEqual(result, _modelib.FLIP_FAILED,
                         "AC-10: a failed write must not report success")
        mode, _diag = _modelib.current_mode("sess-1", root=self.root)
        self.assertEqual(mode, "arbiter", "gates must stay ON when the flip failed")

    def test_flipping_back_to_arbiter_after_a_failed_dangerous_flip_never_wedges(self):
        with mock.patch("_modelib.write_text_atomic", side_effect=OSError("no write perm")):
            _modelib.flip("sess-1", "dangerous", root=self.root)  # fails, stays arbiter
            result = _modelib.flip("sess-1", "arbiter", root=self.root)  # already arbiter
        self.assertEqual(result, _modelib.FLIP_NOOP)
        mode, _diag = _modelib.current_mode("sess-1", root=self.root)
        self.assertEqual(mode, "arbiter")

    def test_a_stale_persisted_dangerous_entry_cannot_self_heal_once_unwritable(self):
        # Honest residual, not a guarantee this module cannot deliver: once
        # "dangerous" is durably ON DISK and the markers dir THEN becomes
        # unwritable, flip() still fails safely (FAILED, never raises) but
        # current_mode legitimately still reads the stale "dangerous" back --
        # _modelib cannot erase state it cannot reach. The compensating
        # control for this residual is AC-11's ledger_backs check at the
        # injector (Lane B), not a fake self-heal here.
        ok = _modelib.write_mode("sess-1", "dangerous", root=self.root)
        self.assertTrue(ok)
        with mock.patch("_modelib.write_text_atomic", side_effect=OSError("no write perm")):
            result = _modelib.flip("sess-1", "arbiter", root=self.root)
        self.assertEqual(result, _modelib.FLIP_FAILED)
        mode, _diag = _modelib.current_mode("sess-1", root=self.root)
        self.assertEqual(mode, "dangerous")

    @unittest.skipIf(os.name == "nt",
                     "chmod-based unwritability is unreliable on Windows "
                     "(precedent: test_sync_core.py's IS_WINDOWS skip)")
    def test_real_chmod_500_markers_dir_flip_to_dangerous_fails_safe(self):
        markers = os.path.join(self.root, ".codearbiter", ".markers")
        os.makedirs(markers)
        os.chmod(markers, 0o500)
        try:
            result = _modelib.flip("sess-1", "dangerous", root=self.root)
        finally:
            os.chmod(markers, 0o700)
        self.assertEqual(result, _modelib.FLIP_FAILED)
        mode, _diag = _modelib.current_mode("sess-1", root=self.root)
        self.assertEqual(mode, "arbiter")


@contextlib.contextmanager
def _append_fails_for(suffix):
    """Make ONLY the append-mode open of a path ending in `suffix` raise
    OSError -- shared portable stand-in for an unwritable log, used by the
    T-15 settle() proof below (precedent: TestSettleDevCloseLedgerReplay's
    identical, class-local helper)."""
    real_open = open

    def fake_open(file, mode="r", *a, **kw):
        if "a" in mode and str(file).endswith(suffix):
            raise OSError("locked")
        return real_open(file, mode, *a, **kw)

    with mock.patch("builtins.open", fake_open):
        yield


# ---------------------------------------------------------------------------
# T-15 — an interrupted exit row is owed; the next settle() appends it
# EXACTLY ONCE (line count), proving the moved ledger machinery is mode-plane
# generic — it never special-cased the literal "DEV: exit" text, so a
# `MODE: <name> exit` row settles through the identical write-ahead path
# (AC-12).
# ---------------------------------------------------------------------------
class TestSettleGenericModeExitRow(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.root = self._tmp.name
        os.makedirs(os.path.join(self.root, ".codearbiter", ".markers"))
        self.log = os.path.join(self.root, ".codearbiter", "overrides.log")
        with open(self.log, "w", encoding="utf-8") as f:
            f.write("[2026-01-01T00:00:00Z] | BY: session-mode | MODE: dangerous enter | NOTE: —\n")

    def tearDown(self):
        self._tmp.cleanup()

    def _line_count(self):
        with open(self.log, encoding="utf-8") as f:
            return len(f.read().splitlines())

    def test_interrupted_mode_exit_row_is_owed_and_settles_exactly_once(self):
        exit_line = _modelib._mode_audit_line("exit", "dangerous", host_name="claude", now=1735689600)

        with _append_fails_for("overrides.log"):
            appended = _modelib._settle_dev_close(self.root, new_line=exit_line)
        self.assertEqual(appended, 0, "the append really did fail -- nothing landed yet")
        before = self._line_count()

        appended = _modelib._settle_dev_close(self.root)  # log writable again: pure replay
        self.assertEqual(appended, 1, "the owed exit row must land exactly once")
        after = self._line_count()
        self.assertEqual(after, before + 1, "exactly one line added by the retry")

        appended_again = _modelib._settle_dev_close(self.root)
        self.assertEqual(appended_again, 0, "nothing left owed -- a third call is a no-op")
        self.assertEqual(self._line_count(), after, "no duplicate on a later session")


# ---------------------------------------------------------------------------
# T-16 — PERSONA_SENTINEL: a single stable exported literal, distinct from
# `_prunepolicy.MARKER_PREFIX`'s elision-marker shape, for the later pruner
# (T-49/T-50) to match and pin (AC-26).
# ---------------------------------------------------------------------------
class TestPersonaSentinel(unittest.TestCase):
    def test_persona_sentinel_is_a_non_empty_stable_string(self):
        self.assertIsInstance(_modelib.PERSONA_SENTINEL, str)
        self.assertTrue(_modelib.PERSONA_SENTINEL.strip())

    def test_persona_sentinel_does_not_collide_with_the_prune_elision_marker_shape(self):
        self.assertNotIn(_prunepolicy.MARKER_PREFIX, _modelib.PERSONA_SENTINEL)
        self.assertFalse(_modelib.PERSONA_SENTINEL.startswith(_prunepolicy.MARKER_PREFIX))


if __name__ == "__main__":
    unittest.main()
