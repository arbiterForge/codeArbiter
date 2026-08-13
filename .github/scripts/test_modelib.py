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
import pathlib
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
        self.entry_dir = os.path.join(self.markers, "mode.d")
        self.entry_path = _modelib.mode_entry_path("sess-1", root=self.root)

    def tearDown(self):
        self._tmp.cleanup()

    def test_write_mode_delegates_to_write_text_atomic(self):
        # The spy: write_mode must not do its own open()/write() -- it must
        # route through write_text_atomic, the module's one atomic-write
        # primitive (mkstemp + os.replace).
        #
        # The spy WRAPS the real primitive rather than replacing it. write_mode
        # now confirms its write by re-reading (the lost-update fix), so a mock
        # that persists nothing makes every write legitimately unverifiable --
        # the delegation this test is about would then be masked by a failure
        # the test itself created.
        real = _modelib.write_text_atomic
        with mock.patch("_modelib.write_text_atomic", side_effect=real) as spy:
            ok = _modelib.write_mode("sess-1", "dangerous", root=self.root)
        self.assertTrue(ok)
        spy.assert_called_once()
        args, kwargs = spy.call_args
        self.assertEqual(args[0], self.entry_path)
        self.assertIn("dangerous", args[1])
        self.assertEqual(kwargs.get("newline"), "\n")

    def test_a_write_touches_only_this_sessions_entry(self):
        """The structural guarantee, asserted on the filesystem.

        A write that touched any second path would be a shared cell again, and
        the interleave tests below would be the only thing standing between
        that and a silent posture revert.
        """
        _modelib.write_mode("sess-OTHER", "ops", root=self.root)
        before = {n: os.stat(os.path.join(self.entry_dir, n)).st_mtime_ns
                  for n in os.listdir(self.entry_dir)}
        _modelib.write_mode("sess-1", "dangerous", root=self.root)
        after = {n: os.stat(os.path.join(self.entry_dir, n)).st_mtime_ns
                 for n in os.listdir(self.entry_dir)}
        self.assertEqual(set(after) - set(before),
                         {os.path.basename(self.entry_path)})
        for name, stamp in before.items():
            self.assertEqual(after[name], stamp,
                             "writing one session's mode rewrote another's entry")
        self.assertFalse(os.path.exists(self.mode_path),
                         "the legacy shared map must never be written again")

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
        self.assertFalse(os.path.isfile(self.entry_path),
                         "an interrupted write must leave no partial mode entry")
        # Scanned in the entry directory, where the temp now lands. Left
        # pointed at `.markers/` this would pass while measuring nothing.
        leftovers = [n for n in os.listdir(self.entry_dir) if n.endswith(".tmp")]
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

    # --- AC-3: the row is an AUTHORIZATION, so it is scoped to a session -----
    # A repo-wide match let session A's `enter` row authorize session B's
    # gates-off marker. Every other part of the mode plane is keyed per
    # session; an unkeyed authorization defeats that isolation, and it is
    # reachable here because worktree agents share one `.codearbiter/` store.

    def test_another_sessions_enter_row_does_not_authorize_this_session(self):
        _modelib.flip("session-a", "dangerous", root=self.root)
        self.assertTrue(_modelib.ledger_backs(self.root, "dangerous", session_id="session-a"))
        self.assertFalse(
            _modelib.ledger_backs(self.root, "dangerous", session_id="session-b"),
            "one session's enter row authorized another session's gates-off marker")

    def test_a_row_written_before_session_attribution_backs_no_session(self):
        """Fails toward arbiter: gates ON and one re-flip, never a silent pass."""
        self._seed("[2026-01-01T00:00:00Z] | BY: session-mode | MODE: ops enter | NOTE: —\n")
        self.assertFalse(_modelib.ledger_backs(self.root, "ops", session_id="s1"))

    def test_the_legacy_dev_migration_still_works_and_is_bounded_to_dangerous(self):
        """The one deliberate session-blind exception, and its limit.

        A pre-mode-plane `DEV: enter` row predates session attribution, so
        requiring one would break the very migration it serves. It must never
        reach `ops`, which did not exist when any DEV row could be written.
        """
        self._seed("[2026-01-01T00:00:00Z] | BY: someone | DEV: enter | NOTE: —\n")
        self.assertTrue(_modelib.ledger_backs(self.root, "dangerous", session_id="s1"))
        self.assertFalse(_modelib.ledger_backs(self.root, "ops", session_id="s1"))

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


# ---------------------------------------------------------------------------
# T-73 — the domain vocabulary in .codearbiter/CONTEXT.md must define `mode`
# and name the three modes STRING-EQUAL to `_modelib.MODES` (AC-52).
#
# String equality against the tuple, not a hand-typed list: a docs-only rename
# of one mode, or a fourth mode added in code and not documented, is exactly the
# drift this catches. ORCHESTRATOR §3 forbids redefining domain vocabulary
# without updating CONTEXT.md, so the vocabulary is a governed surface, not prose.
# ---------------------------------------------------------------------------
class TestContextDomainVocabulary(unittest.TestCase):
    def _context_text(self):
        root = pathlib.Path(__file__).resolve().parents[2]
        return (root / ".codearbiter" / "CONTEXT.md").read_text(encoding="utf-8")

    def test_context_defines_the_term_mode(self):
        text = self._context_text()
        self.assertIn("Domain vocabulary", text,
                      "CONTEXT.md must carry a domain-vocabulary section")
        self.assertRegex(text, r"(?m)^\s*[-*]\s*\*\*`?mode`?\*\*",
                         "CONTEXT.md's domain vocabulary must define the term `mode`")

    def test_context_names_exactly_the_canonical_modes(self):
        text = self._context_text()
        for name in _modelib.MODES:
            self.assertIn("`{}`".format(name), text,
                          "CONTEXT.md must name the mode `{}` exactly as _modelib.MODES "
                          "spells it".format(name))

    def test_context_no_longer_claims_sessionstart_injects_the_persona(self):
        # The activation flag still gates injection, but injection moved to the
        # per-turn prompt seam. Leaving the old sentence would document a
        # mechanism that no longer exists, in the file that defines this repo's
        # own vocabulary.
        text = self._context_text()
        self.assertNotIn("SessionStart persona injection", text)


class TestWriteModeIsVerified(unittest.TestCase):
    """A lost update must not read as a successful write.

    `write_text_atomic` makes each replace atomic but does not serialize the
    read-modify-write PAIR. Two sessions sharing one `.codearbiter/` store
    interleave: A reads, B reads and writes, A's write lands and drops B — or
    B's lands last and restores the mode A explicitly LEFT. `ledger_backs`
    does not compensate, because A's own earlier enter row still authorizes
    the stale entry. This repo runs worktree agents against one store.

    ADR-0030 position 5 calls the return out of `dangerous` a verified write
    whose failure must surface; an unverified write that is then overwritten
    surfaces nothing.
    """

    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.root = self._tmp.name

    def tearDown(self):
        self._tmp.cleanup()

    def test_a_write_undone_before_it_can_be_confirmed_reports_failure(self):
        """A write that does not survive to its own verification is a failure.

        This case used to assert the opposite — that `write_mode` RETRIED until
        it landed — because the entry was a shared map any session might
        replace, so a clobber was routine and recoverable. Per-session entries
        make it neither: nothing else writes this path, so content that is not
        ours means the file was corrupted or replaced out of band. Retrying
        would be a loop that overwrites whatever did that, and reporting
        success would claim a posture the entry does not carry. ADR-0030
        position 5 wants the failure surfaced, and `flip` turns this False into
        FLIP_FAILED.
        """
        original = _modelib.write_text_atomic
        calls = {"n": 0}

        def clobbering(path, text, **kwargs):
            original(path, text, **kwargs)
            calls["n"] += 1
            if calls["n"] == 1:                      # something replaces it behind us
                original(path, json.dumps({"session": "someone-else",
                                           "mode": "ops"}), **kwargs)

        with mock.patch.object(_modelib, "write_text_atomic", clobbering):
            ok = _modelib.write_mode("mine", "arbiter", root=self.root)

        self.assertFalse(ok, "reported success for a write it could not confirm")
        mode, diag = _modelib.current_mode("mine", root=self.root)
        self.assertEqual(mode, "arbiter", "an unconfirmed write must resolve safe")
        self.assertEqual(diag, _modelib.MODE_DIAG_UNRECOGNIZED,
                         "an entry belonging to another session is an anomaly, "
                         "not a silent default")

    def test_a_write_that_never_lands_reports_failure(self):
        """Never claim a success that cannot be demonstrated."""
        def swallow(path, text, **kwargs):
            return None                              # accepts, persists nothing

        with mock.patch.object(_modelib, "write_text_atomic", swallow):
            self.assertFalse(_modelib.write_mode("mine", "dangerous", root=self.root))

    def test_a_concurrent_sessions_entry_is_preserved(self):
        _modelib.write_mode("other", "dangerous", root=self.root)
        _modelib.write_mode("mine", "ops", root=self.root)
        self.assertEqual(_modelib.current_mode("other", root=self.root)[0], "dangerous")
        self.assertEqual(_modelib.current_mode("mine", root=self.root)[0], "ops")

    # -- the interleave the own-key verify cannot see ----------------------
    #
    # Serial writes both read the LATEST state, so they can never express the
    # ordering that actually loses data: `other` reads, `mine` writes, `other`
    # then replaces the file from the map it read BEFORE that write. `other`'s
    # verify passes — it only ever checks its OWN key — and `mine` has already
    # returned True, so neither writer can observe the loss.
    #
    # `_interleaved_write` reproduces exactly that ordering: it lets `victim`
    # complete an entire write in the window between the stale writer's read
    # and its replace.

    def _interleaved_write(self, victim_session, victim_mode):
        """Patch context: run one full `write_mode(victim…)` inside the next
        `write_text_atomic` call, before it lands."""
        original = _modelib.write_text_atomic
        state = {"fired": False}
        root = self.root

        def interleave(path, text, **kwargs):
            if not state["fired"]:
                state["fired"] = True   # set first: the nested write re-enters here
                _modelib.write_mode(victim_session, victim_mode, root=root)
            return original(path, text, **kwargs)

        return mock.patch.object(_modelib, "write_text_atomic", interleave)

    def test_a_stale_writer_cannot_revert_another_sessions_return_to_arbiter(self):
        """The fail-OPEN direction, and the reason this is not merely state loss.

        `A` enters `dangerous`, then explicitly returns to `arbiter` — gates back
        on. A concurrent session completes its own write from the map it read
        before that return, reinstating `dangerous` for `A` with no operator
        action and no new audit row. `ledger_backs` still matches `A`'s original
        `enter` row, so the reinstated posture is authorized: exactly the silent
        gates-off transition ADR-0030 position 5 forbids.
        """
        self.assertEqual(_modelib.flip("A", "dangerous", root=self.root),
                         _modelib.FLIP_FLIPPED)

        # A's return to arbiter happens INSIDE the window — after the other
        # session has read the map that still says `dangerous`, before its
        # replace lands. Flipping A back before the window instead would leave
        # the stale reader holding an already-correct map and prove nothing.
        with self._interleaved_write("A", "arbiter"):
            _modelib.write_mode("B", "ops", root=self.root)

        self.assertEqual(
            _modelib.current_mode("A", root=self.root)[0], "arbiter",
            "a concurrent session's write reinstated a gates-off mode that A "
            "had explicitly left — and A's original enter row still backs it: "
            "ledger_backs={}".format(
                _modelib.ledger_backs(self.root, "dangerous", session_id="A")))

    def test_a_stale_writer_cannot_erase_another_sessions_entry(self):
        """The erase direction, which is a distinct defect from the revert.

        A dropped entry does not merely lose a posture: an ABSENT entry is how
        the compaction path (`session-start.py`, T-47) recognises a session with
        no mode-plane opinion yet, so erasing one re-arms a legacy `dev-active`
        marker to be converted to `dangerous` on top of a session that had
        already chosen.
        """
        with self._interleaved_write("A", "dangerous"):
            _modelib.write_mode("B", "ops", root=self.root)

        self.assertTrue(
            _modelib.session_has_entry("A", root=self.root)[0],
            "a concurrent session's write erased A's entry — absence is read as "
            "'never flipped', which re-arms the legacy dangerous conversion")
        self.assertEqual(_modelib.current_mode("A", root=self.root)[0], "dangerous")

    def test_two_sessions_never_write_the_same_path(self):
        """The structural property that makes the two cases above impossible.

        Asserted directly rather than only through the interleave, so a future
        change that reintroduces a shared cell fails here first, with a message
        that names the cause instead of a symptom.
        """
        self.assertNotEqual(_modelib.mode_entry_path("A", root=self.root),
                            _modelib.mode_entry_path("B", root=self.root))

    def test_a_session_id_cannot_escape_the_entry_directory(self):
        """A session id reaches this from host-supplied hook input, so it is
        untrusted for path construction. Traversal, separators, and reserved
        names must all resolve inside the entry directory."""
        entry_dir = os.path.abspath(_modelib.mode_entry_dir(root=self.root))
        for hostile in ("../../escaped", r"..\..\escaped", "a/b", "a\\b",
                        ".", "..", "", "con", "x" * 400):
            with self.subTest(session_id=hostile):
                path = os.path.abspath(
                    _modelib.mode_entry_path(hostile, root=self.root))
                self.assertEqual(os.path.dirname(path), entry_dir,
                                 "entry path escaped the mode entry directory")
                self.assertTrue(os.path.basename(path))

    def test_distinct_session_ids_never_share_an_entry_file(self):
        """Sanitisation must be injective: two ids collapsing onto one filename
        would reintroduce the shared cell this design removes.

        Compared CASE-INSENSITIVELY, because this repo is Windows-primary and
        NTFS is case-insensitive — two names differing only in case are one
        file there. A sanitiser that merely substitutes unsafe characters
        passes a case-sensitive set comparison while `A` and `a` share an entry
        on the platform most of this project's sessions run on.
        """
        ids = ["a/b", "a\\b", "a_b", "../b", "A", "a", "x" * 400, "x" * 401]
        names = [os.path.basename(_modelib.mode_entry_path(s, root=self.root))
                 for s in ids]
        self.assertEqual(len({n.lower() for n in names}), len(set(ids)))


class TestEnterRowIsLedgerBacked(unittest.TestCase):
    """ADR-0030 position 4: every transition row goes through the write-ahead
    ledger, never a bare append.

    The exit half complied; `flip` did not. An unwritable audit trail therefore
    dropped the `MODE: <name> enter` row with no replay while `flip` still
    returned FLIP_FLIPPED — an unaudited entry INTO a gates-off posture, which
    is the one transition that must never be silent.
    """

    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.root = self._tmp.name

    def tearDown(self):
        self._tmp.cleanup()

    def _refuse_appends(self):
        return mock.patch.object(_modelib, "_append_override_line", return_value=False)

    def _trail_text(self):
        try:
            with open(_modelib._overrides_log_path(self.root), encoding="utf-8") as f:
                return f.read()
        except FileNotFoundError:
            return ""

    def test_an_unwritable_trail_leaves_the_enter_row_owed_not_lost(self):
        with self._refuse_appends():
            _modelib.flip("s1", "dangerous", root=self.root)
        pending = _modelib._read_dev_pending_close(self.root)
        self.assertIsNotNone(pending, "the enter row was dropped instead of staged")
        self.assertTrue(any("MODE: dangerous enter" in line for line in pending["lines"]))

    def test_a_flip_whose_row_never_landed_reports_failure(self):
        """Consistent, not pessimistic: `ledger_backs` would refuse the mode
        anyway, so the caller must not be told the flip took."""
        with self._refuse_appends():
            result = _modelib.flip("s1", "dangerous", root=self.root)
        self.assertEqual(result, _modelib.FLIP_FAILED)

    def test_the_owed_row_replays_on_the_next_settle(self):
        with self._refuse_appends():
            _modelib.flip("s1", "dangerous", root=self.root)
        _modelib._settle_dev_close(self.root)
        self.assertIn("MODE: dangerous enter", self._trail_text())

    def test_a_writable_trail_still_reports_a_flip_and_writes_exactly_one_row(self):
        """The ledger route must not double-append or change the happy path."""
        self.assertEqual(_modelib.flip("s1", "dangerous", root=self.root),
                         _modelib.FLIP_FLIPPED)
        self.assertEqual(self._trail_text().count("MODE: dangerous enter"), 1)


if __name__ == "__main__":
    unittest.main()
