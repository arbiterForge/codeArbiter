#!/usr/bin/env python3
"""codeArbiter — unit tests for the task-board writer + follow-up harvest.

Per spec `.codearbiter/specs/task-writer-harvest.md`:

  AC-01  next_seq allocation
  AC-02  add_entry: ID-less default + mint-on-request, lint-clean, count+1
  AC-03  set_state: queued -> in-progress -> done, dated transitions, safe re-done
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
import taskwrite as taskwrite_mod  # noqa: E402 — for its declared exit codes


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

    def test_rejects_blank_or_multiline_desc_unchanged(self):
        for desc in ("", "   ", "line one\nline two", "line one\rline two",
                     "line one\u2028line two"):
            with self.subTest(desc=desc):
                self.assertEqual(tb.add_entry(BOARD, desc=desc, origin="o"), BOARD)

    def test_rejects_malformed_section_unchanged(self):
        for section in ("Other", "### Other", " ## Other", "## Other ",
                        "## Other\nmalicious", "## Other\rmalicious"):
            with self.subTest(section=section):
                self.assertEqual(
                    tb.add_entry(BOARD, desc="new thing", section=section), BOARD
                )

    def test_rejects_multiline_origin_or_boundary_unchanged(self):
        self.assertEqual(
            tb.add_entry(BOARD, desc="new thing", origin="source\ninjected"), BOARD
        )
        self.assertEqual(
            tb.add_entry(BOARD, desc="new thing", boundaries=["auth\ninjected"]), BOARD
        )
        self.assertEqual(
            tb.add_entry(BOARD, desc="new thing", origin="source\u2028injected"), BOARD
        )

    def test_valid_custom_section_creation_classifies(self):
        old = "# Open tasks\n\n## Done\n- [x] a.b.0001 - old  (done 2026-07-19)\n"
        out = tb.add_entry(old, desc="new thing", section="## Other")
        self.assertIn("## Other\n- [ ] new thing", out)
        self.assertTrue(tb.classify_board_diff(old, out))


class SetStateTest(unittest.TestCase):
    """AC-03 / AC-04 / AC-05."""

    def test_start_flips_and_dates(self):
        out = tb.set_state(BOARD, "v2.api.0001", "in_progress", _d(2026, 6, 21))
        self.assertIn("- [~] v2.api.0001 - existing queued task  (started 2026-06-21)", out)
        # the started item is no longer dateless
        self.assertEqual(tb.undated_in_progress(out), [])

    def test_done_flips_and_dates(self):
        started = tb.set_state(BOARD, "v2.api.0001", "in_progress", _d(2026, 6, 20))
        out = tb.set_state(started, "v2.api.0001", "done", _d(2026, 6, 21))
        self.assertIn("- [x] v2.api.0001 - existing queued task  (done 2026-06-21)", out)
        self.assertEqual(tb.count_in_flight(out), tb.count_in_flight(started) - 1)
        self.assertTrue(tb.classify_board_diff(started, out))

    def test_done_rejects_queued_task(self):
        out = tb.set_state(BOARD, "v2.api.0001", "done", _d(2026, 6, 21))
        self.assertEqual(out, BOARD)

    def test_start_rejects_done_task(self):
        started = tb.set_state(BOARD, "v2.api.0001", "in_progress", _d(2026, 6, 20))
        done = tb.set_state(started, "v2.api.0001", "done", _d(2026, 6, 21))
        self.assertEqual(
            tb.set_state(done, "v2.api.0001", "in_progress", _d(2026, 6, 22)), done
        )

    def test_start_rejects_invalid_assign_namespace(self):
        for assign in ("", "mvp1.store.0002", ".api", "mvp1.", "bad group.api"):
            with self.subTest(assign=assign):
                self.assertEqual(
                    tb.set_state(
                        BOARD, "follow up on the cache thing", "in_progress",
                        _d(2026, 6, 21), assign=assign,
                    ),
                    BOARD,
                )

    def test_re_done_is_safe_noop(self):
        started = tb.set_state(BOARD, "v2.api.0001", "in_progress", _d(2026, 6, 20))
        once = tb.set_state(started, "v2.api.0001", "done", _d(2026, 6, 21))
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
        self.assertTrue(tb.classify_board_diff(BOARD, out))

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
                 "## In-flight\n- [~] foo  (started 2026-06-20)\n")
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

    def test_low_confidence_with_trailing_intent_field_keeps_title_clean(self):
        # ADR-0025: sprint-log headings may carry an `intent:` field AFTER the
        # confidence token (SPRINT.md pins that order — the parser takes the
        # title as everything BEFORE `· confidence:`). Prove a conformant
        # heading extracts an unpolluted title; intent must never leak into
        # the promoted board description.
        log = ("# Sprint — bar\n"
               "## SB-T1 — choose retry shape · confidence: low · intent: silent\n"
               "## SB-T2 — conform to cache ADR · confidence: high · intent: per ADR-0007\n")
        cands = tb.extract_low_confidence(log, origin="sprint:bar")
        self.assertEqual(len(cands), 1)
        # The parser keeps the heading ID in the desc (existing behavior);
        # the pin here is that neither field leaks past the confidence token.
        self.assertEqual(cands[0].desc, "SB-T1 — choose retry shape")
        self.assertNotIn("intent", cands[0].desc)
        self.assertNotIn("confidence", cands[0].desc)


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

    def test_done_rejects_queued_task_before_write_with_start_guidance(self):
        import contextlib
        import io
        import taskwrite
        d, p = self._board()
        taskwrite.project_root = lambda: d
        with open(p, encoding="utf-8") as f:
            before = f.read()
        stderr = io.StringIO()
        with contextlib.redirect_stderr(stderr):
            rc = taskwrite.main(["done", "a.b.0001", "--date", "2026-07-20"])
        self.assertEqual(rc, 1)
        self.assertIn("start", stderr.getvalue().lower())
        self.assertIn("queued", stderr.getvalue().lower())
        with open(p, encoding="utf-8") as f:
            self.assertEqual(f.read(), before)

    def test_successful_start_and_done_outputs_are_commit_gate_classifiable(self):
        import taskwrite
        d, p = self._board()
        taskwrite.project_root = lambda: d
        with open(p, encoding="utf-8") as f:
            queued = f.read()
        self.assertEqual(
            taskwrite.main(["start", "a.b.0001", "--date", "2026-07-19"]),
            0,
        )
        with open(p, encoding="utf-8") as f:
            started = f.read()
        self.assertTrue(tb.classify_board_diff(queued, started))
        self.assertEqual(
            taskwrite.main(["done", "a.b.0001", "--date", "2026-07-20"]),
            0,
        )
        with open(p, encoding="utf-8") as f:
            done = f.read()
        self.assertTrue(tb.classify_board_diff(started, done))

    def test_start_rejects_invalid_assign_namespace_before_write(self):
        import contextlib
        import io
        import taskwrite
        for assign in ("", "mvp1.store.0002", ".api", "mvp1.", "bad group.api"):
            with self.subTest(assign=assign):
                d, p = self._board()
                taskwrite.project_root = lambda: d
                with open(p, encoding="utf-8") as f:
                    before = f.read()
                stderr = io.StringIO()
                with contextlib.redirect_stderr(stderr):
                    rc = taskwrite.main([
                        "start", "a.b.0001", "--as", assign,
                        "--date", "2026-07-20",
                    ])
                self.assertEqual(rc, 1)
                self.assertIn("--as", stderr.getvalue())
                self.assertIn("GROUP.TYPE", stderr.getvalue())
                with open(p, encoding="utf-8") as f:
                    self.assertEqual(f.read(), before)

    def test_start_accepts_valid_assign_and_classifies(self):
        import taskwrite
        d, p = self._board()
        taskwrite.project_root = lambda: d
        with open(p, "w", encoding="utf-8") as f:
            f.write("# Open tasks\n\n## In-flight\n- [ ] seed\n")
        with open(p, encoding="utf-8") as f:
            before = f.read()
        self.assertEqual(
            taskwrite.main([
                "start", "seed", "--as", "mvp1.store",
                "--date", "2026-07-20",
            ]),
            0,
        )
        with open(p, encoding="utf-8") as f:
            after = f.read()
        self.assertIn("mvp1.store.0001 - seed", after)
        self.assertTrue(tb.classify_board_diff(before, after))

    def test_dash_leading_desc_via_separator(self):
        import taskwrite
        d, p = self._board()
        taskwrite.project_root = lambda: d
        rc = taskwrite.main(["add", "--", "-rf important task"])
        self.assertEqual(rc, 0)
        with open(p, encoding="utf-8") as f:
            self.assertIn("-rf important task", f.read())

    def test_add_creates_missing_section_and_classifies(self):
        import taskwrite
        d, p = self._board()
        taskwrite.project_root = lambda: d
        with open(p, "w", encoding="utf-8") as f:
            f.write("# Open tasks\n\n## Done\n- [x] a.b.0001 - seed  (done 2026-07-19)\n")
        with open(p, encoding="utf-8") as f:
            before = f.read()
        self.assertEqual(taskwrite.main(["add", "new work"]), 0)
        with open(p, encoding="utf-8") as f:
            after = f.read()
        self.assertIn("## In-flight\n- [ ] new work", after)
        self.assertTrue(tb.classify_board_diff(before, after))

    def test_add_rejects_malformed_fields_before_write(self):
        import contextlib
        import io
        import taskwrite
        cases = (
            (["add", ""], "description"),
            (["add", "   "], "description"),
            (["add", "line one\nline two"], "description"),
            (["add", "new work", "--section", "Other"], "--section"),
            (["add", "new work", "--section", "## Other\nmalicious"], "--section"),
            (["add", "new work", "--from", "source\ninjected"], "--from"),
            (["add", "new work", "--boundaries", "auth\ninjected"], "--boundaries"),
        )
        for argv, field in cases:
            with self.subTest(argv=argv):
                d, p = self._board()
                taskwrite.project_root = lambda: d
                with open(p, encoding="utf-8") as f:
                    before = f.read()
                stderr = io.StringIO()
                with contextlib.redirect_stderr(stderr):
                    rc = taskwrite.main(argv)
                self.assertEqual(rc, 1)
                self.assertIn(field, stderr.getvalue())
                with open(p, encoding="utf-8") as f:
                    self.assertEqual(f.read(), before)

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


class ArchiveTransformTest(unittest.TestCase):
    """B-20/T-57: the pure text->text move, and B-21/T-59 dedup."""

    OPEN = ("# Open tasks\n\n## In-flight\n"
            "- [x] a.b.0001 - old (done 2026-07-01)\n"
            "- [x] a.b.0002 - recent (done 2026-07-30)\n"
            "- [x] undated legacy\n"
            "- [~] a.b.0003 - live (started 2026-07-20)\n")
    TODAY = datetime.date(2026, 8, 1)

    def _task(self, ident):
        for line in self.OPEN.splitlines():
            parsed = tb.parse_board(line)
            if parsed and (parsed[0].id == ident or parsed[0].title == ident):
                return parsed[0]
        raise AssertionError(f"no task {ident!r} in the fixture")

    def test_archive_cutoff_uses_an_injected_date(self):
        # A cutoff test keyed on the real clock passes for eleven days and
        # then starts failing on its own, so `today` is required with no
        # default anywhere in the chain.
        aged, _undated = tb.archive_candidates(self.OPEN, today=self.TODAY)
        self.assertEqual([t.id for t in aged], ["a.b.0001"])

    def test_archive_cutoff_is_a_named_constant(self):
        self.assertEqual(tb.ARCHIVE_CUTOFF_DAYS, 14)
        # Boundary: exactly at the cutoff is NOT yet aged; one day past is.
        at = self.TODAY - datetime.timedelta(days=tb.ARCHIVE_CUTOFF_DAYS)
        past = at - datetime.timedelta(days=1)
        board = (f"## In-flight\n- [x] x.y.0001 - a (done {at})\n"
                 f"- [x] x.y.0002 - b (done {past})\n")
        aged, _ = tb.archive_candidates(board, today=self.TODAY)
        self.assertEqual([t.id for t in aged], ["x.y.0002"])

    def test_archive_undated_items_are_returned_separately(self):
        # They cannot be aged, and the spec admits them only under explicit
        # per-item confirmation -- a single combined list would let a caller
        # sweep them by accident.
        aged, undated = tb.archive_candidates(self.OPEN, today=self.TODAY)
        self.assertEqual([t.title for t in undated], ["undated legacy"])
        self.assertNotIn("undated legacy", [t.title for t in aged])

    def test_archive_transform_moves_one_item_and_keeps_the_rest(self):
        new_open, new_done = tb.archive_transform(self.OPEN, "", self._task("a.b.0001"))
        self.assertIn("a.b.0001", new_done)
        self.assertNotIn("a.b.0001", new_open)
        for survivor in ("a.b.0002", "a.b.0003", "undated legacy"):
            self.assertIn(survivor, new_open, survivor)

    def test_archive_transform_creates_the_done_heading_when_absent(self):
        _open, new_done = tb.archive_transform(self.OPEN, "", self._task("a.b.0001"))
        self.assertTrue(new_done.startswith(tb.DONE_TASKS_HEADING))

    def test_archive_rerun_does_not_duplicate_by_dotted_id(self):
        # B-21. Dedup is on the ID, not the text.
        #
        # Found by a surviving mutant: my first version archived the SAME
        # text twice, which text-dedup also handles — so switching the
        # implementation to text-only kept the test green. The ID rule only
        # bites when the title CHANGED between runs, which is the case the
        # docstring actually claims and the case a board edit produces.
        task = self._task("a.b.0001")
        _first_open, first_done = tb.archive_transform(self.OPEN, "", task)
        self.assertIn("old", first_done)

        # Same ID, title edited since it was archived.
        edited_board = self.OPEN.replace("- old (done 2026-07-01)",
                                         "- RENAMED (done 2026-07-01)")
        edited = next(p[0] for p in
                      (tb.parse_board(l) for l in edited_board.splitlines())
                      if p and p[0].id == "a.b.0001")
        self.assertNotEqual(edited.raw.strip(), task.raw.strip())

        _open2, second_done = tb.archive_transform(edited_board, first_done, edited)
        self.assertEqual(
            second_done, first_done,
            "a re-archive after a title edit appended a second copy; dedup "
            "must key on the dotted ID, not the line text")
        self.assertEqual(second_done.count("a.b.0001"), 1)

    def test_archive_rerun_identical_text_is_also_deduped(self):
        # The simple case, kept explicitly so both dedup paths are pinned.
        task = self._task("a.b.0001")
        first_open, first_done = tb.archive_transform(self.OPEN, "", task)
        second_open, second_done = tb.archive_transform(first_open, first_done, task)
        self.assertEqual(second_done, first_done)
        self.assertEqual(second_open, first_open)

    def test_archive_rerun_dedups_an_id_less_entry_on_exact_text(self):
        # An ID-less entry has no stable handle, so its own text is the
        # only thing that identifies it.
        task = self._task("undated legacy")
        _o, done = tb.archive_transform(self.OPEN, "", task)
        _o2, done2 = tb.archive_transform(_o, done, task)
        self.assertEqual(done2.count("undated legacy"), 1)

    def test_archive_rerun_still_removes_from_open_when_already_archived(self):
        # THE interrupted-run state (B-22): the record is in done-tasks but
        # was never removed from open-tasks. The next run must finish the
        # move rather than refuse it.
        task = self._task("a.b.0001")
        _first_open, done = tb.archive_transform(self.OPEN, "", task)
        new_open, new_done = tb.archive_transform(self.OPEN, done, task)
        self.assertNotIn("a.b.0001", new_open)
        self.assertEqual(new_done.count("a.b.0001"), 1)

    def test_archive_transform_never_raises_on_junk(self):
        for bad_open, bad_done, bad_task in ((None, "", None), ("", None, None),
                                             ("x", "y", object())):
            result = tb.archive_transform(bad_open, bad_done, bad_task)
            self.assertEqual(len(result), 2)


class DoneTasksShapeTest(unittest.TestCase):
    """B-23/T-61: `done-tasks.md` is scaffolded at init, not conjured on
    the first archive.

    An append-only file that springs into existence mid-sweep has no
    reviewed initial content and no header saying what it is — and
    `archive`'s first write would be the thing that defines the format.
    Scaffolding it means the shape is reviewed once, in the initializer,
    like every other `.codearbiter/` artifact.
    """

    def _init_module(self):
        import importlib.util
        spec = importlib.util.spec_from_file_location(
            "_init_ca_under_test", os.path.join(HOOKS, "init-codearbiter.py"))
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        return module

    def test_done_tasks_shape_is_scaffolded_by_init(self):
        init = self._init_module()
        self.assertIn("done-tasks.md", init.FILES)

    def test_done_tasks_shape_states_append_only_and_its_writer(self):
        init = self._init_module()
        body = init.FILES["done-tasks.md"]
        self.assertIn("APPEND-ONLY", body)
        self.assertIn("taskwrite archive", body)
        # The stamp rule, because it is what makes an entry ageable and
        # what `archive` refuses to invent.
        self.assertIn("(done YYYY-MM-DD)", body)

    def test_done_tasks_shape_heading_matches_what_archive_writes(self):
        # If the scaffold's heading and the transform's fallback heading
        # disagreed, an archive into a scaffolded file would produce one
        # heading and an archive into a missing file another.
        init = self._init_module()
        self.assertTrue(
            init.FILES["done-tasks.md"].startswith(tb.DONE_TASKS_HEADING),
            "the scaffold heading and DONE_TASKS_HEADING must agree")

    def test_done_tasks_shape_scaffold_is_a_valid_archive_target(self):
        # The scaffolded text must accept an appended entry without the
        # transform inventing a second heading.
        init = self._init_module()
        scaffold = init.FILES["done-tasks.md"]
        board = "## In-flight\n- [x] a.b.0001 - t (done 2026-07-01)\n"
        task = next(p[0] for p in
                    (tb.parse_board(l) for l in board.splitlines()) if p)
        _open, done = tb.archive_transform(board, scaffold, task)
        self.assertEqual(done.count(tb.DONE_TASKS_HEADING), 1)
        self.assertIn("a.b.0001", done)


class ArchiveVerbTest(unittest.TestCase):
    """B-20/B-23/T-58 and B-22/T-60: the CLI verb, end to end on disk."""

    BOARD = ("# Open tasks\n\n## In-flight\n"
             "- [x] a.b.0001 - old (done 2026-07-01)\n"
             "- [x] a.b.0002 - keep (done 2026-07-30)\n"
             "- [x] undated legacy\n")

    def _repo(self):
        import tempfile as tf
        root = tf.mkdtemp(prefix="ca-archive-")
        self.addCleanup(__import__("shutil").rmtree, root, True)
        os.makedirs(os.path.join(root, ".codearbiter"))
        with open(os.path.join(root, ".codearbiter", "open-tasks.md"),
                  "w", encoding="utf-8", newline="\n") as handle:
            handle.write(self.BOARD)
        return root

    def _run(self, root, *argv):
        import subprocess
        env = dict(os.environ, CLAUDE_PROJECT_DIR=root,
                   PYTHONDONTWRITEBYTECODE="1")
        return subprocess.run(
            [sys.executable, os.path.join(HOOKS, "taskwrite.py"), *argv],
            capture_output=True, text=True, env=env, cwd=root)

    def _read(self, root, name):
        path = os.path.join(root, ".codearbiter", name)
        if not os.path.isfile(path):
            return None
        with open(path, encoding="utf-8") as handle:
            return handle.read()

    def test_archive_verb_creates_done_tasks_and_moves_the_item(self):
        # B-23: done-tasks.md need not exist beforehand; the verb creates it.
        root = self._repo()
        self.assertIsNone(self._read(root, "done-tasks.md"))
        proc = self._run(root, "archive", "a.b.0001")
        self.assertEqual(proc.returncode, 0, proc.stderr)
        done = self._read(root, "done-tasks.md")
        self.assertIsNotNone(done, "done-tasks.md was not created")
        self.assertIn("a.b.0001", done)
        self.assertNotIn("a.b.0001", self._read(root, "open-tasks.md"))

    def test_archive_verb_leaves_other_items_untouched(self):
        root = self._repo()
        self._run(root, "archive", "a.b.0001")
        board = self._read(root, "open-tasks.md")
        self.assertIn("a.b.0002", board)
        self.assertIn("undated legacy", board)

    def test_archive_verb_refuses_an_item_that_is_not_done(self):
        root = self._repo()
        with open(os.path.join(root, ".codearbiter", "open-tasks.md"),
                  "a", encoding="utf-8", newline="\n") as handle:
            handle.write("- [~] a.b.0009 - live (started 2026-07-20)\n")
        proc = self._run(root, "archive", "a.b.0009")
        self.assertEqual(proc.returncode, 1)
        self.assertIn("only moves", proc.stderr)

    def test_archive_verb_refuses_an_undated_item_without_the_flag(self):
        # Undated items archive only under explicit per-item confirmation:
        # both `taskwrite done` and the ADR-0008 classifier require the
        # stamp, so an unstamped entry is legacy or override-era.
        root = self._repo()
        proc = self._run(root, "archive", "undated legacy")
        self.assertEqual(proc.returncode, 1)
        self.assertIn("--allow-undated", proc.stderr)
        self.assertIsNone(self._read(root, "done-tasks.md"),
                          "a refused archive must write nothing at all")

    def test_archive_verb_accepts_an_undated_item_with_the_flag(self):
        root = self._repo()
        proc = self._run(root, "archive", "undated legacy", "--allow-undated")
        self.assertEqual(proc.returncode, 0, proc.stderr)
        self.assertIn("undated legacy", self._read(root, "done-tasks.md"))

    def test_archive_verb_is_rerun_safe_on_disk(self):
        root = self._repo()
        self.assertEqual(self._run(root, "archive", "a.b.0001").returncode, 0)
        second = self._run(root, "archive", "a.b.0001")
        # The item is gone from the board, so the second run has nothing to
        # match -- it must refuse cleanly, never duplicate.
        self.assertEqual(second.returncode, 1)
        self.assertEqual(self._read(root, "done-tasks.md").count("a.b.0001"), 1)

    # ---- workstream-B adversary HIGH-2/HIGH-3/HIGH-4 --------------------
    #
    # Every pre-existing archive fixture in this file is pure top-level
    # bullets, which is exactly why the sub-bullet defects were invisible.
    # This one carries the shape `add --desc/--boundaries` actually emits.
    BLOCK_BOARD = ("# Open tasks\n\n## In-flight\n"
                   "- [x] g.t.0001 - first (done 2026-07-01)\n"
                   "  - Desc: the rationale that must survive\n"
                   "  - Boundaries: egress, secrets\n"
                   "- [ ] g.t.0002 - second\n")

    def _block_repo(self):
        root = self._repo()
        with open(os.path.join(root, ".codearbiter", "open-tasks.md"),
                  "w", encoding="utf-8", newline="\n") as handle:
            handle.write(self.BLOCK_BOARD)
        return root

    def test_archive_moves_the_sub_bullets_with_the_task(self):
        # HIGH-2. `archive_transform` moved `task.raw` -- the TOP LINE
        # alone -- so Desc/Boundaries were left behind and silently
        # re-attributed to whatever task followed. Boundaries is a
        # security-scoping field, so the orphan does not merely vanish
        # from the record: it reappears as a claim about a different task.
        root = self._block_repo()
        proc = self._run(root, "archive", "g.t.0001")
        self.assertEqual(proc.returncode, 0, proc.stderr)

        done = self._read(root, "done-tasks.md")
        self.assertIn("- Desc: the rationale that must survive", done)
        self.assertIn("- Boundaries: egress, secrets", done)

        open_after = self._read(root, "open-tasks.md")
        self.assertNotIn("the rationale that must survive", open_after)
        self.assertNotIn("egress, secrets", open_after)

        # The decisive assertion: the surviving task must not have
        # inherited the archived task's fields.
        survivor = next(t for t in tb.parse_board(open_after)
                        if t.id == "g.t.0002")
        self.assertEqual(survivor.desc, "")
        self.assertEqual(survivor.boundaries, [])

    def test_indented_continuation_prose_does_not_split_the_block(self):
        # CodeRabbit MAJOR, confirmed. `task_block`'s close scan advanced
        # only past `- Key:` sub-bullets and blanks, while `parse_board`
        # keeps a task open across ANY indented line. So an indented
        # continuation line stopped the block early and orphaned every
        # sub-bullet after it onto the following task -- re-opening HIGH-2
        # through a different door. The two rules are now identical.
        root = self._repo()
        with open(os.path.join(root, ".codearbiter", "open-tasks.md"),
                  "w", encoding="utf-8", newline="\n") as handle:
            handle.write("# Open tasks\n\n## In-flight\n"
                         "- [x] g.t.0001 - one (done 2026-07-01)\n"
                         "    continuation prose, indented, not a sub-bullet\n"
                         "  - Boundaries: egress, secrets\n"
                         "- [ ] g.t.0002 - two\n")
        proc = self._run(root, "archive", "g.t.0001")
        self.assertEqual(proc.returncode, 0, proc.stderr)
        open_after = self._read(root, "open-tasks.md")
        self.assertNotIn("continuation prose", open_after)
        self.assertNotIn("egress, secrets", open_after)
        survivor = next(t for t in tb.parse_board(open_after) if t.id == "g.t.0002")
        self.assertEqual(survivor.boundaries, [])
        self.assertIn("- Boundaries: egress, secrets", self._read(root, "done-tasks.md"))

    def test_the_board_is_parsed_whole_so_lineno_is_real(self):
        # CodeRabbit MAJOR, confirmed. `_archive` parsed the board one line
        # at a time, so every Task carried lineno == 1 and no sub-fields --
        # meaning `task_block`'s index-based location could never match and
        # always fell through to its first-line fallback. Asserted on the
        # parse itself, because the archive OUTCOME was right either way and
        # so could not detect the dead mechanism.
        text = ("# Open tasks\n\n## In-flight\n"
                "- [x] a.b.0001 - one (done 2026-07-01)\n"
                "- [x] a.b.0002 - two (done 2026-07-01)\n")
        whole = tb.parse_board(text)
        self.assertEqual([t.lineno for t in whole], [4, 5])
        per_line = [p[0] for p in
                    (tb.parse_board(line) for line in text.splitlines()) if p]
        self.assertEqual([t.lineno for t in per_line], [1, 1],
                         "the per-line parse this replaced should still be "
                         "demonstrably lineno-blind")

    def test_archive_of_a_block_is_rerun_safe(self):
        # The interrupted-run recovery property held before this fix and
        # must still hold now that the moved unit is a block: dedup keys
        # on the ID while the move keys on the block, so the two operate
        # on different units and could drift apart.
        root = self._block_repo()
        with open(os.path.join(root, ".codearbiter", "done-tasks.md"),
                  "w", encoding="utf-8", newline="\n") as handle:
            handle.write("# Done tasks\n"
                         "- [x] g.t.0001 - first (done 2026-07-01)\n"
                         "  - Desc: the rationale that must survive\n"
                         "  - Boundaries: egress, secrets\n")
        proc = self._run(root, "archive", "g.t.0001")
        self.assertEqual(proc.returncode, 0, proc.stderr)
        done = self._read(root, "done-tasks.md")
        self.assertEqual(done.count("g.t.0001"), 1, "recovery duplicated the block")
        self.assertEqual(done.count("- Desc: the rationale"), 1)
        self.assertNotIn("g.t.0001", self._read(root, "open-tasks.md"))

    def test_archive_of_one_duplicate_leaves_the_other_on_the_board(self):
        # HIGH-3. Removal was `line.strip() != raw` over every line, so
        # two character-identical done entries both disappeared while a
        # single record was appended -- one task destroyed, rc=0, "archived".
        # Reachable through the sanctioned helper alone: `add` is
        # documented rerun-safe, so two adds of one description is an
        # ordinary state, not a hand-crafted file.
        root = self._repo()
        with open(os.path.join(root, ".codearbiter", "open-tasks.md"),
                  "w", encoding="utf-8", newline="\n") as handle:
            handle.write("# Open tasks\n\n## In-flight\n"
                         "- [x] tidy the log (done 2026-06-02)\n"
                         "- [x] tidy the log (done 2026-06-02)\n")
        proc = self._run(root, "archive", "tidy the log")
        self.assertEqual(proc.returncode, 0, proc.stderr)
        self.assertEqual(
            self._read(root, "open-tasks.md").count("tidy the log"), 1,
            "archiving one duplicate removed both — a record was destroyed")
        self.assertEqual(
            self._read(root, "done-tasks.md").count("tidy the log"), 1)

    def test_an_unreadable_archive_refuses_and_writes_nothing(self):
        # HIGH-4. `except OSError: done_text = ""` folded "I could not
        # read it" into "there is nothing there", and the write REPLACES
        # done-tasks.md wholesale -- so any transient read failure (an
        # editor holding the file, a deny-read ACL, a failing volume)
        # silently wiped every historical record with rc=0 and the word
        # "archived". Injected as PermissionError because the Windows
        # deny-read ACL that found this surfaces as exactly that in-process.
        root = self._repo()
        historical = ("# Done tasks\n"
                      "- [x] a.b.9001 - historical one (done 2026-01-01)\n"
                      "- [x] a.b.9002 - historical two (done 2026-02-01)\n")
        with open(os.path.join(root, ".codearbiter", "done-tasks.md"),
                  "w", encoding="utf-8", newline="\n") as handle:
            handle.write(historical)
        board_before = self._read(root, "open-tasks.md")

        driver = (
            "import sys, builtins\n"
            f"sys.path.insert(0, {HOOKS!r})\n"
            "import taskwrite\n"
            "real = builtins.open\n"
            "def guarded(path, *a, **k):\n"
            "    if 'done-tasks' in str(path) and 'r' in str(k.get('mode', a[0] if a else 'r')):\n"
            "        raise PermissionError(13, 'denied')\n"
            "    return real(path, *a, **k)\n"
            "builtins.open = guarded\n"
            "sys.exit(taskwrite.main(['archive', 'a.b.0001']))\n"
        )
        import subprocess
        proc = subprocess.run(
            [sys.executable, "-c", driver], capture_output=True, text=True,
            env=dict(os.environ, CLAUDE_PROJECT_DIR=root,
                     PYTHONDONTWRITEBYTECODE="1"), cwd=root)

        self.assertEqual(proc.returncode, taskwrite_mod.EXIT_ARCHIVE_UNREADABLE,
                         f"expected the distinct unreadable-archive exit, got "
                         f"{proc.returncode}: {proc.stderr}")
        self.assertIn("append-only", proc.stderr)
        # Neither file moved. This is the assertion the defect failed.
        self.assertEqual(self._read(root, "done-tasks.md"), historical)
        self.assertEqual(self._read(root, "open-tasks.md"), board_before)

    def test_the_unreadable_refusal_is_not_an_oserror(self):
        # The refusal must not be catchable by the very idiom that caused
        # the bug. `except OSError: text = ""` is what destroyed the
        # archive; if ArchiveUnreadable were an OSError subclass, the next
        # caller to write that idiom one level up would swallow the refusal
        # and reintroduce the same data loss silently.
        self.assertFalse(issubclass(taskwrite_mod.ArchiveUnreadable, OSError))
        self.assertTrue(issubclass(taskwrite_mod.ArchiveUnreadable, RuntimeError))
        with self.assertRaises(taskwrite_mod.ArchiveUnreadable):
            try:
                raise taskwrite_mod.ArchiveUnreadable("refused")
            except OSError:                      # must NOT catch it
                self.fail("a generic OSError handler swallowed the refusal")

    def test_archive_still_seeds_an_absent_done_tasks_file(self):
        # The other half of the HIGH-4 split: ABSENT is not UNREADABLE.
        # An existing repo has no done-tasks.md until its first archive,
        # so seeding one must keep working — a fix that refused on every
        # OSError would break the first archive in every repo.
        root = self._repo()
        self.assertIsNone(self._read(root, "done-tasks.md"))
        proc = self._run(root, "archive", "a.b.0001")
        self.assertEqual(proc.returncode, 0, proc.stderr)
        self.assertIn("a.b.0001", self._read(root, "done-tasks.md"))

    def test_archive_interrupted_between_writes_loses_nothing(self):
        # B-22. Simulate the exact interruption: done-tasks.md already has
        # the record (phase 1 completed) but open-tasks.md still lists it
        # (phase 2 never ran) -- which is what a kill between the two writes
        # leaves behind. Recovery must complete the move, not duplicate and
        # not lose.
        root = self._repo()
        with open(os.path.join(root, ".codearbiter", "done-tasks.md"),
                  "w", encoding="utf-8", newline="\n") as handle:
            handle.write("# Done tasks\n- [x] a.b.0001 - old (done 2026-07-01)\n")
        proc = self._run(root, "archive", "a.b.0001")
        self.assertEqual(proc.returncode, 0, proc.stderr)
        done = self._read(root, "done-tasks.md")
        self.assertEqual(done.count("a.b.0001"), 1, "recovery duplicated the record")
        self.assertNotIn("a.b.0001", self._read(root, "open-tasks.md"))

    def test_archive_writes_done_before_open_so_a_failed_second_write_keeps_it(self):
        # M-1 (workstream-B adversary). The test this REPLACES claimed to
        # measure the ordering and did not: it called `archive_transform`
        # -- a pure function that writes nothing -- and closed on
        # `assertNotIn("a.b.0001", removed_first + "")`, which is the
        # identical string it had just asserted on. The "other order" was
        # never executed, and a mutant reversing the two writes in
        # `taskwrite.py` survived the entire suite.
        #
        # Measured instead by making the SECOND write fail and looking at
        # what survived on disk. Under the shipped order (done first) the
        # record is in done-tasks.md; under the reversed order the
        # done-tasks write is never reached and the record is in NEITHER
        # file -- which is the loss the ordering exists to prevent.
        root = self._repo()
        driver = (
            "import sys\n"
            f"sys.path.insert(0, {HOOKS!r})\n"
            "import taskwrite\n"
            "real = taskwrite._atomic_write\n"
            "def boom(path, text, prefix):\n"
            "    if prefix == 'open-tasks.':\n"
            "        raise RuntimeError('simulated crash before the second write')\n"
            "    return real(path, text, prefix)\n"
            "taskwrite._atomic_write = boom\n"
            "taskwrite.main(['archive', 'a.b.0001'])\n"
        )
        import subprocess
        proc = subprocess.run(
            [sys.executable, "-c", driver], capture_output=True, text=True,
            env=dict(os.environ, CLAUDE_PROJECT_DIR=root,
                     PYTHONDONTWRITEBYTECODE="1"), cwd=root)
        self.assertIn("simulated crash", proc.stderr)

        done = self._read(root, "done-tasks.md") or ""
        self.assertIn(
            "a.b.0001", done,
            "the record was NOT written to done-tasks.md before open-tasks "
            "was rewritten — reversing the two writes loses it outright")
        # open-tasks still lists it: recoverable, and the next run dedups.
        self.assertIn("a.b.0001", self._read(root, "open-tasks.md"))


class AddRationaleTest(unittest.TestCase):
    """B-17/T-53: `add` carries a `- Desc:` rationale sub-bullet.

    `debug` Exit (c) used to append its "no action" note to
    `open-tasks.md` DIRECTLY, because the helper had no way to express a
    rationale sub-bullet. That made it the last real surface still writing
    the board by hand — and under the `helper-only` protected-state class
    the board is heading for, a direct write is exactly what stops being
    possible. The conversion needed the helper extension first; this is it.
    """

    BOARD = "# Open tasks\n\n## In-flight\n\n"

    def test_add_rationale_emits_an_indented_desc_sub_bullet(self):
        out = tb.add_entry(self.BOARD, desc="parser drops the final row",
                           rationale="no action: upstream fixes it in 4.2")
        self.assertIn("  - Desc: no action: upstream fixes it in 4.2", out)

    def test_add_rationale_round_trips_through_the_board_parser(self):
        # The point of routing through the helper: the entry must still be
        # a task the board's own readers see. A sub-bullet that broke
        # parsing would drop the note out of the in-flight count, which is
        # the opposite of what Exit (c) wants.
        out = tb.add_entry(self.BOARD, desc="parser drops the final row",
                           rationale="no action", group="debug", type="note")
        parsed = [tb.parse_board(line) for line in out.splitlines()]
        tasks = [p[0] for p in parsed if p]
        self.assertEqual(len(tasks), 1)
        self.assertEqual(tasks[0].id, "debug.note.0001")
        self.assertEqual(tasks[0].title, "parser drops the final row")
        self.assertEqual(tasks[0].state, "queued")

    def test_add_rationale_sits_above_boundaries_when_both_are_given(self):
        out = tb.add_entry(self.BOARD, desc="d", rationale="why",
                           boundaries=["a", "b"])
        body = out.splitlines()
        desc_at = next(i for i, l in enumerate(body) if "- Desc:" in l)
        bounds_at = next(i for i, l in enumerate(body) if "- Boundaries:" in l)
        self.assertLess(desc_at, bounds_at)

    def test_add_rationale_absent_emits_no_sub_bullet(self):
        # The default path must be byte-identical to before this feature.
        self.assertNotIn("- Desc:", tb.add_entry(self.BOARD, desc="d"))

    def test_add_rationale_rejects_a_line_break(self):
        # A newline would emit an orphan physical line the board parser
        # cannot attribute to any task — the exact schema drift routing
        # through the helper exists to prevent.
        self.assertIsNotNone(tb.add_error(desc="d", rationale="a\nb"))
        self.assertEqual(tb.add_entry(self.BOARD, desc="d", rationale="a\nb"),
                         self.BOARD, "an invalid field must fail soft, unchanged")

    def test_add_rationale_rejects_blank_and_non_string(self):
        for bad in ("", "   ", 42, []):
            with self.subTest(rationale=bad):
                self.assertIsNotNone(tb.add_error(desc="d", rationale=bad))

    def test_add_rationale_is_exposed_by_the_taskwrite_cli(self):
        # A helper extension nobody can invoke is the defect class this
        # campaign already hit once (a mechanism with no CLI entry point
        # while prose aimed at it), so assert the flag is actually wired.
        source = os.path.join(HOOKS, "taskwrite.py")
        with open(source, encoding="utf-8") as handle:
            text = handle.read()
        self.assertIn('"--desc"', text)
        self.assertIn("rationale=args.rationale", text)


if __name__ == "__main__":
    unittest.main()
