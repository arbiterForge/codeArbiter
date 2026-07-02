#!/usr/bin/env python3
"""codeArbiter — unit tests for the task-board writer + follow-up harvest.

Per spec `.codearbiter/specs/task-writer-harvest.md`:

  AC-01  next_seq allocation
  AC-02  add_entry: ID-less default + mint-on-request, lint-clean, count+1
  AC-03  set_state: dated start/done transitions, safe re-done
  AC-04  start of an ID-less item mints a dotted ID + stamps the date (pick-up path)
  AC-05  set_state on a missing target: unchanged, no raise
  AC-06  dedup by (from <origin>)
  AC-07  extract_needs_triage
  AC-08  extract_deferrable (checkpoint DEFERRABLE section)
  AC-09  extract_low_confidence (sprint-log)
  AC-10  promote routing: work -> board, decision -> questions
  AC-11  promote modes: interactive = no mutation; auto = mutate + audit

(AC-12 — /ca:task command registration — is covered by check-plugin-refs in CI.)
Stdlib only. Exit 0 = all tests pass.
"""

import datetime
import os
import sys
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(os.path.dirname(HERE))
HOOKS = os.path.join(REPO, "plugins", "ca", "hooks")
sys.path.insert(0, HOOKS)

import _taskboardlib as tb  # noqa: E402


def _d(y, m, d):
    return datetime.date(y, m, d)


BOARD = """\
# Open tasks

## In-flight
- [ ] v2.api.0001 - existing queued task
- [ ] follow up on the cache thing  (from checkpoint-2026-06-13#H-2)
"""


class NextSeqTest(unittest.TestCase):
    """AC-01."""

    def test_empty_namespace_is_one(self):
        self.assertEqual(tb.next_seq("", "v2", "followup"), 1)

    def test_next_after_gap(self):
        text = "- [ ] v2.followup.0001 - a\n- [x] v2.followup.0003 - b  (done 2026-06-10)\n"
        self.assertEqual(tb.next_seq(text, "v2", "followup"), 4)

    def test_namespaces_independent(self):
        text = "- [ ] v2.api.0009 - a\n"
        self.assertEqual(tb.next_seq(text, "v2", "followup"), 1)


class AddEntryTest(unittest.TestCase):
    """AC-02."""

    def test_idless_default(self):
        out = tb.add_entry(BOARD, desc="new thing", origin="checkpoint-2026-06-13#H-7")
        self.assertIn("- [ ] new thing  (from checkpoint-2026-06-13#H-7)", out)
        self.assertEqual(tb.count_in_flight(out), tb.count_in_flight(BOARD) + 1)
        self.assertEqual(tb.lint_board(out), [])

    def test_mint_id_when_group_type_given(self):
        out = tb.add_entry(BOARD, desc="X", origin="o", group="v2", type="followup")
        self.assertIn("- [ ] v2.followup.0001 - X  (from o)", out)
        self.assertEqual(tb.lint_board(out), [])

    def test_creates_section_when_absent(self):
        out = tb.add_entry("# Open tasks\n", desc="first", section="## In-flight")
        self.assertIn("## In-flight", out)
        self.assertIn("- [ ] first", out)
        self.assertEqual(tb.count_in_flight(out), 1)

    def test_sanitizes_multiline_desc(self):
        # M3: a multi-line candidate desc must not inject an orphan second line.
        out = tb.add_entry(BOARD, desc="line one\nline two", origin="o")
        self.assertIn("- [ ] line one line two  (from o)", out)
        self.assertEqual(tb.lint_board(out), [])


class SetStateTest(unittest.TestCase):
    """AC-03 / AC-04 / AC-05."""

    def test_start_flips_and_dates(self):
        out = tb.set_state(BOARD, "v2.api.0001", "in_progress", _d(2026, 6, 21))
        self.assertIn("- [~] v2.api.0001 - existing queued task  (started 2026-06-21)", out)
        # the started item is no longer dateless
        self.assertEqual(tb.undated_in_progress(out), [])

    def test_done_flips_and_dates(self):
        out = tb.set_state(BOARD, "v2.api.0001", "done", _d(2026, 6, 21))
        self.assertIn("- [x] v2.api.0001 - existing queued task  (done 2026-06-21)", out)
        self.assertEqual(tb.count_in_flight(out), tb.count_in_flight(BOARD) - 1)

    def test_re_done_is_safe_noop(self):
        once = tb.set_state(BOARD, "v2.api.0001", "done", _d(2026, 6, 21))
        twice = tb.set_state(once, "v2.api.0001", "done", _d(2026, 6, 22))
        self.assertEqual(once, twice)   # idempotent

    def test_start_idless_item_mints_id_and_dates(self):
        # AC-04: pick-up path — target by title, assign group.type, mint + date.
        out = tb.set_state(BOARD, "follow up on the cache thing", "in_progress",
                           _d(2026, 6, 21), assign="v2.api")
        self.assertIn("v2.api.0002", out)              # minted next seq in v2.api
        self.assertIn("(started 2026-06-21)", out)
        self.assertEqual(tb.undated_in_progress(out), [])
        # the minted line is a valid, lint-clean task
        self.assertEqual(tb.lint_board(out), [])

    def test_missing_target_unchanged(self):
        # AC-05: not found -> unchanged, no raise.
        self.assertEqual(tb.set_state(BOARD, "v2.nope.9999", "done", _d(2026, 6, 21)), BOARD)

    def test_preserves_desc_with_parens(self):
        # H1: a desc with a literal parenthetical must not be lost on flip.
        board = "## In-flight\n- [ ] v2.api.0005 - handle the (legacy) path\n"
        out = tb.set_state(board, "v2.api.0005", "in_progress", _d(2026, 6, 21))
        self.assertIn("handle the (legacy) path", out)
        self.assertIn("(started 2026-06-21)", out)

    def test_done_line_does_not_shadow_open(self):
        # H2: an open task is preferred over a done line of the same title.
        board = ("## Done\n- [x] foo  (done 2026-06-01)\n"
                 "## In-flight\n- [ ] foo\n")
        out = tb.set_state(board, "foo", "done", _d(2026, 6, 21))
        self.assertIn("- [x] foo  (done 2026-06-21)", out)   # the OPEN one got marked
        self.assertIn("- [x] foo  (done 2026-06-01)", out)   # the old done one untouched


class DedupTest(unittest.TestCase):
    """AC-06."""

    def test_already_promoted_true_for_open_origin(self):
        self.assertTrue(tb.already_promoted(BOARD, "checkpoint-2026-06-13#H-2"))

    def test_already_promoted_false_for_unknown(self):
        self.assertFalse(tb.already_promoted(BOARD, "checkpoint-2026-06-13#H-99"))

    def test_done_entry_does_not_block_repromote(self):
        done = "- [x] old  (from o1)  (done 2026-06-10)\n"
        self.assertFalse(tb.already_promoted(done, "o1"))  # only OPEN entries block


class ExtractTest(unittest.TestCase):
    """AC-07 / AC-08 / AC-09."""

    def test_needs_triage(self):
        text = ("some prose\n"
                "[NEEDS-TRIAGE] the auth refactor is out of scope here\n"
                "more\n"
                "- [NEEDS-TRIAGE] split the oversized migration\n")
        cands = tb.extract_needs_triage(text, origin="spec:foo")
        self.assertEqual(len(cands), 2)
        self.assertEqual(cands[0].kind, "work")
        self.assertIn("auth refactor", cands[0].desc)
        self.assertTrue(cands[0].origin.startswith("spec:foo"))

    def test_needs_triage_none(self):
        self.assertEqual(tb.extract_needs_triage("nothing here\n", origin="x"), [])

    def test_deferrable_table(self):
        # The REAL checkpoint-aggregator emits a markdown TABLE, not bullets.
        chk = ("## Dispositions\n"
               "### BLOCKS — must resolve before this change lands\n"
               "| Finding | Source | Severity |\n"
               "|---------|--------|----------|\n"
               "| a blocker | security-reviewer | HIGH |\n"
               "### DEFERRABLE — real, safe to follow up\n"
               "| Finding | Source | Severity |\n"
               "|---------|--------|----------|\n"
               "| tighten the retry backoff | coverage-auditor | MEDIUM |\n"
               "| add a contract test for the 401 path | security-reviewer | LOW |\n"
               "### NON_BLOCKING\n"
               "| a nit | architecture-drift | LOW |\n")
        cands = tb.extract_deferrable(chk, origin="checkpoint-2026-06-13")
        self.assertEqual([c.desc for c in cands],
                         ["tighten the retry backoff",
                          "add a contract test for the 401 path"])
        self.assertTrue(cands[0].origin.startswith("checkpoint-2026-06-13"))

    def test_deferrable_bullets_still_work(self):
        chk = "### DEFERRABLE\n- bullet item one\n- bullet item two\n"
        self.assertEqual(len(tb.extract_deferrable(chk, origin="c")), 2)

    def test_deferrable_ignores_prose_heading_and_nested(self):
        # A prose ### mentioning DEFERRABLE must NOT trigger; nested bullets ignored.
        chk = ("### Notes on DEFERRABLE policy\n"
               "- this is prose, not a finding\n"
               "### DEFERRABLE\n"
               "- real finding\n"
               "  - a nested sub-bullet (not its own candidate)\n")
        self.assertEqual([c.desc for c in tb.extract_deferrable(chk, origin="c")],
                         ["real finding"])

    def test_low_confidence_ignores_prose_line(self):
        log = ("## SD-01 — real heading · confidence: low\n"
               "the decision had confidence: low overall, just prose\n")
        self.assertEqual(len(tb.extract_low_confidence(log, origin="s")), 1)

    def test_low_confidence(self):
        log = ("# Sprint — foo\n"
               "## SH-T1 — pick a queue lib · confidence: high\n"
               "## SH-T2 — guess the timeout · confidence: low\n"
               "## SH-T3 — naming · confidence: low\n")
        cands = tb.extract_low_confidence(log, origin="sprint:foo")
        self.assertEqual(len(cands), 2)
        self.assertTrue(all("low" not in c.desc.lower() or "timeout" in c.desc or "naming" in c.desc
                            for c in cands))


class PromoteTest(unittest.TestCase):
    """AC-10 / AC-11."""

    def _cands(self):
        return [
            tb.Candidate(kind="work", desc="do the thing", origin="o-work", boundaries=[]),
            tb.Candidate(kind="decision", desc="decide the other thing",
                         origin="o-dec", boundaries=[]),
        ]

    def test_interactive_does_not_mutate(self):
        # AC-11: interactive returns the candidate list, writes nothing.
        res = tb.promote(BOARD, "# Open questions\n", self._cands(),
                         mode="interactive", today=_d(2026, 6, 21))
        self.assertEqual(res.board, BOARD)
        self.assertEqual(len(res.candidates), 2)
        self.assertFalse(res.applied)

    def test_auto_routes_and_audits(self):
        # AC-10 + AC-11: work -> board, decision -> questions; audit names both.
        res = tb.promote(BOARD, "# Open questions\n\n## Deferred decisions\n", self._cands(),
                         mode="auto", today=_d(2026, 6, 21))
        self.assertTrue(res.applied)
        self.assertIn("do the thing", res.board)              # work landed on the board
        self.assertNotIn("decide the other thing", res.board)  # decision did NOT
        self.assertIn("decide the other thing", res.questions)  # decision -> questions
        self.assertIn("o-dec", res.questions)                   # back-ref preserved
        self.assertEqual(len(res.audit), 2)

    def test_auto_dedups_already_promoted(self):
        # A work candidate whose origin is already open on the board is skipped.
        dup = [tb.Candidate(kind="work", desc="x", origin="checkpoint-2026-06-13#H-2",
                            boundaries=[])]
        res = tb.promote(BOARD, "# Open questions\n", dup,
                         mode="auto", today=_d(2026, 6, 21))
        self.assertEqual(res.board, BOARD)   # nothing added — already promoted
        self.assertEqual(res.audit, [])

    def test_blocking_decision_escalates_not_filed(self):
        # A blocking decision must NOT land in the non-gating Deferred section.
        cands = [tb.Candidate(kind="decision", desc="must decide the auth model",
                              origin="o-block", boundaries=[], blocking=True)]
        res = tb.promote(BOARD, "# Open questions\n\n## Deferred decisions\n", cands,
                         mode="auto", today=_d(2026, 6, 21))
        self.assertNotIn("must decide the auth model", res.questions)
        self.assertTrue(any("ESCALATE" in a for a in res.audit))


class TaskwriteCliTest(unittest.TestCase):
    """The thin CLI wrapper: bad-date guard (H3) and dash-leading desc via `--` (M2)."""

    def _board(self):
        import tempfile
        d = tempfile.mkdtemp()
        os.makedirs(os.path.join(d, ".codearbiter"))
        p = os.path.join(d, ".codearbiter", "open-tasks.md")
        with open(p, "w", encoding="utf-8") as f:
            f.write("# Open tasks\n\n## In-flight\n- [ ] a.b.0001 - seed\n")
        return d, p

    def test_bad_date_returns_1_no_crash(self):
        import taskwrite
        d, p = self._board()
        taskwrite.project_root = lambda: d
        self.assertEqual(taskwrite.main(["start", "a.b.0001", "--date", "nope"]), 1)

    def test_dash_leading_desc_via_separator(self):
        import taskwrite
        d, p = self._board()
        taskwrite.project_root = lambda: d
        rc = taskwrite.main(["add", "--", "-rf important task"])
        self.assertEqual(rc, 0)
        with open(p, encoding="utf-8") as f:
            self.assertIn("-rf important task", f.read())

    def test_malformed_multipart_id_rejected_no_write(self):
        """issue #157: a --id with more than GROUP.TYPE (e.g. a full 3-part id)
        must be rejected (exit 1) and write nothing, rather than minting an
        un-targetable 4-segment id like 'mvp1.store.0002.0001'."""
        import taskwrite
        d, p = self._board()
        taskwrite.project_root = lambda: d
        with open(p, encoding="utf-8") as f:
            before = f.read()
        self.assertEqual(taskwrite.main(["add", "--id", "mvp1.store.0002", "--", "x"]), 1)
        with open(p, encoding="utf-8") as f:
            self.assertEqual(f.read(), before)  # board untouched

    def test_well_formed_group_type_id_still_mints(self):
        """A proper GROUP.TYPE --id still mints group.type.NNNN (no regression)."""
        import taskwrite
        d, p = self._board()
        taskwrite.project_root = lambda: d
        self.assertEqual(taskwrite.main(["add", "--id", "mvp1.store", "--", "x"]), 0)
        with open(p, encoding="utf-8") as f:
            self.assertIn("mvp1.store.0001 - x", f.read())

    def test_atomic_write_board_survives_interrupted_write(self):
        """migration-001: the original board must survive a write interrupted after
        truncation.  We monkeypatch the temp-file write to raise, then assert the
        real open-tasks.md is unchanged (no truncation)."""
        import importlib
        import types
        import tempfile
        import taskwrite

        d, p = self._board()
        with open(p, encoding="utf-8") as _f:
            original_content = _f.read()

        # Patch os.replace in taskwrite's namespace to raise before the rename
        # completes, simulating a crash between temp-write and rename.
        original_replace = taskwrite.os.replace

        def _failing_replace(src, dst):
            # Remove the temp file but do NOT copy it to dst — simulates a crash
            # mid-rename. The real board at dst must remain untouched.
            try:
                taskwrite.os.remove(src)
            except OSError:
                pass
            raise OSError("simulated crash during os.replace")

        taskwrite.os.replace = _failing_replace
        try:
            taskwrite.project_root = lambda: d
            try:
                taskwrite.main(["add", "should not land"])
            except OSError:
                pass  # expected — the simulated crash propagates
        finally:
            taskwrite.os.replace = original_replace

        # The original board must be intact — no truncation occurred.
        with open(p, encoding="utf-8") as f:
            self.assertEqual(f.read(), original_content,
                             "board was truncated/corrupted by an interrupted write")

    def test_missing_board_returns_1_no_file_created(self):
        """coverage-004: an uninitialized repo (no .codearbiter/open-tasks.md)
        must exit 1 with the 'no board at' stderr message and must not create
        any file as a side effect."""
        import io
        import tempfile
        import contextlib
        import taskwrite

        d = tempfile.mkdtemp()  # deliberately no .codearbiter/ dir at all
        taskwrite.project_root = lambda: d

        stderr = io.StringIO()
        with contextlib.redirect_stderr(stderr):
            rc = taskwrite.main(["add", "x"])

        self.assertEqual(rc, 1)
        self.assertIn("no board at", stderr.getvalue())
        self.assertEqual(os.listdir(d), [], "no file should be created for an uninitialized repo")


if __name__ == "__main__":
    unittest.main()
