#!/usr/bin/env python3
"""codeArbiter — unit tests for the task-board lifecycle helper (_taskboardlib).

Proves the pure parsing/counting/staleness logic for `open-tasks.md` and its
two readers (session-start.py, statusline.py), per spec
`.codearbiter/specs/task-board-lifecycle.md`:

  AC-01  count_in_flight excludes done
  AC-02  both readers reflect that count (session-start startup_summary + statusline arbiter_state)
  AC-03  stale_in_progress detects [~] older than the threshold
  AC-04  the SessionStart stale nudge line emits only when >=1 stale
  AC-05  an oversize board (>65536B) degrades instead of being body-parsed
  AC-06  the init scaffold template documents the schema
  AC-07  a malformed (started ...) date never crashes
  AC-08  this repo's own open-tasks.md conforms to the schema (parse==count, valid IDs)
  AC-09  validate_id accepts the dotted grammar, rejects malformed, reports duplicates
  AC-10  parse_board parses Desc/Done-when/Boundaries; partial (TBD/absent) is allowed

Stdlib only. Exit 0 = all tests pass; non-zero = failure.
"""

import datetime
import importlib.util as _ilu
import os
import sys
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(os.path.dirname(HERE))
HOOKS = os.path.join(REPO, "plugins", "ca", "hooks")
sys.path.insert(0, HOOKS)

import _taskboardlib as tb  # noqa: E402 — needs sys.path mutation above


def _load(modname, filename):
    """Load a hyphenated hook module (e.g. session-start.py) by path."""
    spec = _ilu.spec_from_file_location(modname, os.path.join(HOOKS, filename))
    mod = _ilu.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def _date(y, m, d):
    return datetime.date(y, m, d)


# A representative board exercising every state + the legacy bare bullet.
SAMPLE = """\
# Open tasks

## In-flight
- [~] poc.auth.0001 — Validate session tokens  (started 2026-06-18)
  - Desc: reject expired/forged tokens at the auth middleware
  - Done when: an expired token returns 401; a valid one passes
  - Boundaries: auth, secrets
- [ ] poc.api.0002 — Rate-limit the login endpoint
  - Desc: TBD
- legacy bare bullet with no checkbox

## Done
- [x] poc.auth.0003 — Hash passwords with bcrypt  (done 2026-06-15)
- [x] poc.api.0004 — Return 404 on unknown route  (done 2026-06-16)
- [x] mvp1.ui.0005 — Login form skeleton  (done 2026-06-17)
"""


class CountTest(unittest.TestCase):
    """AC-01: count_in_flight = top-level '- ' lines excluding '- [x]'."""

    def test_excludes_done_counts_rest(self):
        # 1 [~] + 1 [ ] + 1 legacy bare = 3 in-flight; 3 [x] excluded.
        self.assertEqual(tb.count_in_flight(SAMPLE), 3)

    def test_empty_and_headers_only(self):
        self.assertEqual(tb.count_in_flight("# Open tasks\n\nNo tasks yet.\n"), 0)

    def test_indented_subitems_not_counted(self):
        text = "- [ ] a.b.0001 — A\n  - Desc: sub item\n- [ ] a.b.0002 — B\n"
        self.assertEqual(tb.count_in_flight(text), 2)

    def test_done_case_insensitive(self):
        self.assertEqual(tb.count_in_flight("- [X] a.b.0001 — done upper\n"), 0)

    def test_parse_count_agree(self):
        # The cross-check that guards parse/count drift (also used on the repo board).
        non_done = [t for t in tb.parse_board(SAMPLE) if t.state != "done"]
        self.assertEqual(tb.count_in_flight(SAMPLE), len(non_done))

    def test_blank_bullets_not_counted(self):
        # H-2: a bare "- ", whitespace-only, or empty "- [ ]" has no content and
        # must not inflate the count (lint surfaces them instead).
        self.assertEqual(tb.count_in_flight("- \n-  \n- [ ]\n"), 0)
        # ...but a real legacy bare bullet WITH content still counts.
        self.assertEqual(tb.count_in_flight("- real legacy task\n"), 1)


class ValidateIdTest(unittest.TestCase):
    """AC-09: dotted ‹group›.‹type›.‹seq4› grammar + duplicate reporting."""

    def test_accepts_well_formed(self):
        for good in ("poc.auth.0001", "mvp1.api.0042", "v1.infra.0100", "v12.ui.99999"):
            self.assertTrue(tb.validate_id(good), good)

    def test_rejects_malformed(self):
        for bad in ("poc.auth", "poc.auth.1", "poc.auth.42", "poc..0001",
                    "poc.auth.0001x", "PoC.auth.0001", "poc.auth.", "", "auth.0001"):
            self.assertFalse(tb.validate_id(bad), bad)

    def test_rejects_trailing_newline(self):
        # M-3: `$` would accept a trailing newline; `\Z` must not.
        self.assertFalse(tb.validate_id("poc.auth.0001\n"))
        self.assertFalse(tb.validate_id("poc.auth.0001 "))

    def test_duplicate_ids_reported(self):
        text = ("- [ ] poc.auth.0001 — first\n"
                "- [~] poc.auth.0001 — dup  (started 2026-06-18)\n"
                "- [ ] poc.api.0002 — unique\n")
        self.assertEqual(tb.duplicate_ids(text), ["poc.auth.0001"])

    def test_no_duplicates(self):
        self.assertEqual(tb.duplicate_ids(SAMPLE), [])


class ParseTest(unittest.TestCase):
    """AC-10: structured fields parse; partial/absent is allowed, never raises."""

    def test_full_entry_fields(self):
        tasks = {t.id: t for t in tb.parse_board(SAMPLE)}
        t = tasks["poc.auth.0001"]
        self.assertEqual(t.state, "in_progress")
        self.assertEqual(t.started, _date(2026, 6, 18))
        self.assertIn("auth middleware", t.desc)
        self.assertIn("401", t.done_when)
        self.assertEqual(t.boundaries, ["auth", "secrets"])

    def test_partial_fields_tbd(self):
        tasks = {t.id: t for t in tb.parse_board(SAMPLE)}
        t = tasks["poc.api.0002"]
        self.assertEqual(t.state, "queued")
        self.assertEqual(t.desc, "TBD")
        self.assertEqual(t.done_when, "")     # absent -> empty, never a throw
        self.assertEqual(t.boundaries, [])

    def test_legacy_bare_bullet_parses_as_queued(self):
        tasks = tb.parse_board(SAMPLE)
        legacy = [t for t in tasks if t.id is None]
        self.assertEqual(len(legacy), 1)
        self.assertEqual(legacy[0].state, "queued")

    def test_done_entry_has_done_date(self):
        tasks = {t.id: t for t in tb.parse_board(SAMPLE)}
        self.assertEqual(tasks["poc.auth.0003"].state, "done")
        self.assertEqual(tasks["poc.auth.0003"].done, _date(2026, 6, 15))

    def test_subfields_do_not_leak_across_heading(self):
        # M-1: a ## heading between a task and an indented sub-bullet must close
        # the task so the sub-field cannot bind to the wrong (prior) task.
        text = ("- [ ] poc.api.0001 — first\n"
                "## Done\n"
                "  - Desc: this belongs to nobody\n")
        first = tb.parse_board(text)[0]
        self.assertEqual(first.id, "poc.api.0001")
        self.assertEqual(first.desc, "")   # NOT leaked across the heading

    def test_decoy_started_phrase_does_not_shadow_real_date(self):
        # M-2: a non-date "(started ...)" earlier in the title must not block the
        # real trailing date from being parsed.
        text = "- [~] poc.api.0001 — Refactor (started by Bob) cache  (started 2026-06-18)\n"
        t = tb.parse_board(text)[0]
        self.assertEqual(t.started, _date(2026, 6, 18))


class StaleTest(unittest.TestCase):
    """AC-03 / AC-07: stale [~] detection with an injected 'today'."""

    def test_reports_stale_at_threshold(self):
        r = tb.stale_in_progress(SAMPLE, today=_date(2026, 6, 21), threshold_days=3)
        self.assertEqual(r["count"], 1)
        self.assertEqual(r["oldest_age"], 3)
        self.assertEqual(r["oldest_id"], "poc.auth.0001")

    def test_started_today_not_stale(self):
        text = "- [~] poc.auth.0001 — x  (started 2026-06-21)\n"
        r = tb.stale_in_progress(text, today=_date(2026, 6, 21), threshold_days=3)
        self.assertEqual(r["count"], 0)
        self.assertIsNone(r["oldest_id"])

    def test_malformed_started_date_never_crashes(self):
        # AC-07: garbage date -> age-unknown (in-progress, not stale), no throw.
        text = "- [~] poc.auth.0001 — x  (started not-a-date)\n"
        r = tb.stale_in_progress(text, today=_date(2026, 6, 21), threshold_days=3)
        self.assertEqual(r["count"], 0)
        # still counted as in-flight despite the bad date
        self.assertEqual(tb.count_in_flight(text), 1)

    def test_same_age_tie_with_legacy_bullet_never_crashes(self):
        # B-1 regression: two same-age stale [~] tasks where one is a legacy bare
        # bullet (id=None). A naive (age, id) sort raises TypeError on the tie —
        # which would take down the whole SessionStart hook.
        text = ("- [~] a.b.0001 — A  (started 2026-06-10)\n"
                "- [~] legacy bare in progress  (started 2026-06-10)\n")
        r = tb.stale_in_progress(text, today=_date(2026, 6, 21), threshold_days=3)
        self.assertEqual(r["count"], 2)            # both stale, no crash
        lines = tb.startup_summary(text, today=_date(2026, 6, 21))  # public path
        self.assertTrue(any("stale" in ln for ln in lines))


class UndatedTest(unittest.TestCase):
    """Drop-off #3: an in-progress [~] with no start date must be surfaced (it
    can never age, so the stale nudge alone would miss it forever)."""

    def test_undated_in_progress_collected(self):
        text = ("- [~] a.b.0001 — no date here\n"
                "- [~] a.b.0002 — dated  (started 2026-06-18)\n"
                "- [ ] a.b.0003 — queued\n")
        undated = tb.undated_in_progress(text)
        self.assertEqual([t.id for t in undated], ["a.b.0001"])

    def test_startup_surfaces_undated(self):
        text = "- [~] a.b.0001 — no date here\n"
        lines = tb.startup_summary(text, today=_date(2026, 6, 21))
        self.assertTrue(any("no start date" in ln for ln in lines))


class LintTest(unittest.TestCase):
    """Drop-off #2: lint_board SURFACES tasks at risk of vanishing — a marker
    not in the canonical column-0 position, an invalid ID, or a duplicate ID."""

    def test_clean_board_no_warnings(self):
        self.assertEqual(tb.lint_board(SAMPLE), [])

    def test_flags_markers_not_at_column_zero(self):
        for bad in ("  - [ ] a.b.0001 — indented",     # indented
                    "-[ ] a.b.0001 — no space",         # no space after dash
                    "* [ ] a.b.0001 — wrong bullet",    # asterisk bullet
                    "\t- [~] a.b.0001 — tab",           # tab-indented
                    "[ ] a.b.0001 — no dash"):          # bare marker
            warnings = tb.lint_board(bad)
            self.assertTrue(any("malformed" in w for w in warnings), bad)
            # ...and the count is structurally blind to it (that's why we lint):
            self.assertEqual(tb.count_in_flight(bad), 0, bad)

    def test_marker_inside_title_is_not_flagged(self):
        # A legacy bullet whose TITLE contains "[x]" must not be a false positive.
        self.assertEqual(tb.lint_board("- fix the [x] rendering bug\n"), [])

    def test_flags_invalid_id(self):
        warnings = tb.lint_board("- [ ] poc.auth.1 — under-padded seq\n")
        self.assertTrue(any("invalid task id" in w for w in warnings))

    def test_flags_duplicate_id(self):
        text = "- [ ] a.b.0001 — one\n- [ ] a.b.0001 — two\n"
        warnings = tb.lint_board(text)
        self.assertTrue(any("duplicate task id" in w for w in warnings))


class NudgeTest(unittest.TestCase):
    """AC-04: the startup nudge line emits only when >=1 stale; ASCII-only."""

    def test_line_present_when_stale(self):
        line = tb.stale_nudge_line(SAMPLE, today=_date(2026, 6, 25), threshold_days=3)
        self.assertIsNotNone(line)
        self.assertIn("poc.auth.0001", line)
        self.assertEqual(line, line.encode("ascii", "strict").decode())  # no non-ASCII

    def test_no_line_when_none_stale(self):
        line = tb.stale_nudge_line(SAMPLE, today=_date(2026, 6, 18), threshold_days=3)
        self.assertIsNone(line)


class StartupSummaryTest(unittest.TestCase):
    """AC-02 (session side) + AC-05: the exact lines session-start prints."""

    def test_count_line_and_stale_line(self):
        lines = tb.startup_summary(SAMPLE, today=_date(2026, 6, 25), threshold_days=3)
        self.assertEqual(lines[0], "in-flight tasks: 3")
        self.assertTrue(any("stale" in ln for ln in lines[1:]))

    def test_count_line_only_when_fresh(self):
        lines = tb.startup_summary(SAMPLE, today=_date(2026, 6, 18), threshold_days=3)
        self.assertEqual(lines, ["in-flight tasks: 3"])

    def test_oversize_board_degrades(self):
        big = "- [ ] poc.api.0001 — x\n" * 5000  # well over 65536 bytes
        self.assertGreater(len(big.encode("utf-8")), tb.MAX_BOARD_BYTES)
        lines = tb.startup_summary(big, today=_date(2026, 6, 21))
        self.assertEqual(len(lines), 1)
        self.assertIn("too large", lines[0].lower())
        # never reports a parsed count for an oversize board
        self.assertNotIn("in-flight tasks:", lines[0])

    def test_none_text_is_empty(self):
        self.assertEqual(tb.startup_summary(None, today=_date(2026, 6, 21)), [])


class ReaderIntegrationTest(unittest.TestCase):
    """AC-02: the REAL readers route through the helper (not a reimplementation)."""

    def test_session_start_uses_startup_summary(self):
        mod = _load("session_start", "session-start.py")
        # session-start must delegate to the helper, not hand-roll the count.
        self.assertIs(mod._taskboardlib.count_in_flight, tb.count_in_flight)

    def test_statusline_tasks_excludes_done(self):
        import tempfile
        mod = _load("statusline", "statusline.py")
        with tempfile.TemporaryDirectory() as tmp:
            cad = os.path.join(tmp, ".codearbiter")
            os.makedirs(cad)
            with open(os.path.join(cad, "CONTEXT.md"), "w", encoding="utf-8") as f:
                f.write("---\narbiter: enabled\nstage: 2\n---\n")
            with open(os.path.join(cad, "open-tasks.md"), "w", encoding="utf-8") as f:
                f.write(SAMPLE)
            open(os.path.join(cad, "overrides.log"), "w").close()
            with open(os.path.join(cad, "last-checkpoint"), "w") as f:
                f.write("0\n")
            state = mod.arbiter_state(tmp)
            self.assertEqual(state["tasks"], 3)   # done excluded, not 6

    def test_statusline_fallback_still_excludes_done(self):
        # H-1: if _taskboardlib import fails, the degraded fallback must STILL
        # exclude done — never silently re-inflate to the pre-schema count.
        import tempfile
        mod = _load("statusline", "statusline.py")
        mod._count_in_flight = None   # simulate the import-failure path
        with tempfile.TemporaryDirectory() as tmp:
            cad = os.path.join(tmp, ".codearbiter")
            os.makedirs(cad)
            with open(os.path.join(cad, "CONTEXT.md"), "w", encoding="utf-8") as f:
                f.write("---\narbiter: enabled\nstage: 2\n---\n")
            with open(os.path.join(cad, "open-tasks.md"), "w", encoding="utf-8") as f:
                f.write(SAMPLE)
            open(os.path.join(cad, "overrides.log"), "w").close()
            with open(os.path.join(cad, "last-checkpoint"), "w") as f:
                f.write("0\n")
            state = mod.arbiter_state(tmp)
            self.assertEqual(state["tasks"], 3)   # fallback excludes done too


class ScaffoldTest(unittest.TestCase):
    """AC-06: the init template documents the schema."""

    def test_template_documents_grammar(self):
        mod = _load("init_codearbiter", "init-codearbiter.py")
        tmpl = mod.OPEN_TASKS
        for token in ("[ ]", "[~]", "[x]", "group", "type", "Done when", "Boundaries"):
            self.assertIn(token, tmpl, token)


class SetStateGuardTest(unittest.TestCase):
    """dx-004: set_state with an unknown state must degrade gracefully (no KeyError)."""

    def test_unknown_state_returns_text_unchanged(self):
        # dx-004: an unknown state string must NOT raise KeyError; degrade by
        # returning the text unchanged so the hook-stdin path cannot crash.
        result = tb.set_state(SAMPLE, "poc.auth.0001", "pending", _date(2026, 6, 21))
        self.assertEqual(result, SAMPLE,
                         "set_state with unknown state must return text unchanged")

    def test_known_states_still_work(self):
        # Regression guard: the fix must not break valid state transitions.
        out = tb.set_state(SAMPLE, "poc.auth.0001", "done", _date(2026, 6, 21))
        self.assertIn("- [x]", out)


class MalformedIdHardeningTest(unittest.TestCase):
    """issue #157: an over-segmented id (e.g. 'a.b.c.d', produced by a mistyped
    --id) must NOT be silently absorbed into the title. It parses as an id so
    validate_id rejects it, lint_board surfaces it, and set_state can target it
    for repair — instead of stranding an un-targetable, un-lintable task."""

    BOARD = ("# Open tasks\n\n## In-flight\n"
             "- [ ] mvp1.store.0002.0001 - Fix the thing  (from review)\n")

    def test_four_segment_token_parses_as_id(self):
        self.assertEqual(tb.parse_board(self.BOARD)[0].id, "mvp1.store.0002.0001")

    def test_validate_id_rejects_four_segments(self):
        self.assertFalse(tb.validate_id("mvp1.store.0002.0001"))

    def test_lint_surfaces_the_invalid_id(self):
        self.assertTrue(any("invalid task id" in w for w in tb.lint_board(self.BOARD)))

    def test_set_state_can_target_for_repair(self):
        out = tb.set_state(self.BOARD, "mvp1.store.0002.0001", "done", _date(2026, 6, 28))
        self.assertIn("- [x] mvp1.store.0002.0001", out)
        self.assertIn("(done 2026-06-28)", out)

    def test_well_formed_three_segment_unaffected(self):
        board = "# Open tasks\n\n## In-flight\n- [ ] mvp1.store.0001 - X\n"
        self.assertEqual(tb.parse_board(board)[0].id, "mvp1.store.0001")
        self.assertTrue(tb.validate_id("mvp1.store.0001"))
        self.assertEqual(tb.lint_board(board), [])


class PromoteModeGuardTest(unittest.TestCase):
    """dx-005: promote with an unknown mode must not silently auto-apply."""

    def _cands(self):
        return [tb.Candidate(kind="work", desc="do the thing", origin="o-work",
                             boundaries=[])]

    def test_unknown_mode_raises_valueerror(self):
        # dx-005: an unknown mode (e.g. 'dry-run', a typo) must raise ValueError
        # rather than silently applying candidates to the board.
        with self.assertRaises(ValueError):
            tb.promote(SAMPLE, "# Open questions\n", self._cands(),
                       mode="dry-run", today=_date(2026, 6, 21))

    def test_known_modes_still_work(self):
        # Regression guard: interactive and auto must be unaffected.
        res_i = tb.promote(SAMPLE, "# Open questions\n", self._cands(),
                           mode="interactive", today=_date(2026, 6, 21))
        self.assertFalse(res_i.applied)
        res_a = tb.promote(SAMPLE, "# Open questions\n", self._cands(),
                           mode="auto", today=_date(2026, 6, 21))
        self.assertTrue(res_a.applied)


class RepoBoardConformsTest(unittest.TestCase):
    """AC-08: this repo's own open-tasks.md conforms after migration."""

    def test_repo_board_is_well_formed(self):
        board = os.path.join(REPO, ".codearbiter", "open-tasks.md")
        with open(board, encoding="utf-8") as f:
            text = f.read()
        # parse/count agree, no duplicate IDs, and every ID present is valid.
        non_done = [t for t in tb.parse_board(text) if t.state != "done"]
        self.assertEqual(tb.count_in_flight(text), len(non_done))
        self.assertEqual(tb.duplicate_ids(text), [])
        for t in tb.parse_board(text):
            if t.id is not None:
                self.assertTrue(tb.validate_id(t.id), f"bad id: {t.id}")
        # Independent ground-truth check (NOT self-consistent with count): lint
        # would catch a malformed/indented/duplicate entry the count is blind to.
        self.assertEqual(tb.lint_board(text), [])


class ClassifyBoardDiffTest(unittest.TestCase):
    """AC-01/02/03: classify_board_diff — done-flip, start-flip, add positive;
    reword/delete/unstamped/double-flip/unrelated-line/empty/garbled negative."""

    # Minimal two-section board used across all cases in this class.
    _BASE = (
        "# Open tasks\n\n"
        "## In-flight\n"
        "- [~] a.b.0001 - Validate tokens  (started 2026-06-18)\n"
        "- [ ] a.b.0002 - Rate-limit endpoint\n\n"
        "## Done\n"
        "- [x] a.b.0003 - Hash passwords  (done 2026-06-15)\n"
    )

    # ── positive: done-flip ──────────────────────────────────────────────────

    def test_done_flip_is_clean_transition(self):
        """AC-01: [~]+started → [x]+done with no other change is a clean transition."""
        old = self._BASE
        new = old.replace(
            "- [~] a.b.0001 - Validate tokens  (started 2026-06-18)",
            "- [x] a.b.0001 - Validate tokens  (done 2026-06-26)",
        )
        self.assertTrue(tb.classify_board_diff(old, new))

    # ── positive: start-flip ─────────────────────────────────────────────────

    def test_start_flip_is_clean_transition(self):
        """AC-02a: [ ] → [~]+started with no other change is a clean transition."""
        old = self._BASE
        new = old.replace(
            "- [ ] a.b.0002 - Rate-limit endpoint",
            "- [~] a.b.0002 - Rate-limit endpoint  (started 2026-06-26)",
        )
        self.assertTrue(tb.classify_board_diff(old, new))

    # ── positive: add ────────────────────────────────────────────────────────

    def test_add_queued_entry_is_clean_transition(self):
        """AC-02b: appending a single - [ ] entry with no other change is a clean transition."""
        old = self._BASE
        new = old.rstrip("\n") + "\n- [ ] a.b.0004 - Implement caching\n"
        self.assertTrue(tb.classify_board_diff(old, new))

    def test_add_with_from_backref_is_clean_transition(self):
        """AC-02b: add with a (from origin) back-ref is still a clean transition."""
        old = self._BASE
        new = old.rstrip("\n") + "\n- [ ] a.b.0004 - Implement caching  (from sprint-3)\n"
        self.assertTrue(tb.classify_board_diff(old, new))

    def test_add_with_boundaries_subbullet_is_clean_transition(self):
        """AC-02b: add with an indented - Boundaries: sub-bullet is still a clean transition."""
        old = self._BASE
        new = (old.rstrip("\n")
               + "\n- [ ] a.b.0004 - Implement caching\n"
               + "  - Boundaries: cache, perf\n")
        self.assertTrue(tb.classify_board_diff(old, new))

    # ── negative: reworded description ───────────────────────────────────────

    def test_reworded_desc_is_not_transition(self):
        """AC-03: changing a task title (not just the stamp) is not a clean transition."""
        old = self._BASE
        new = old.replace(
            "- [~] a.b.0001 - Validate tokens  (started 2026-06-18)",
            "- [~] a.b.0001 - Validate ALL the tokens reworded  (started 2026-06-18)",
        )
        self.assertFalse(tb.classify_board_diff(old, new))

    # ── negative: deleted task ────────────────────────────────────────────────

    def test_deleted_task_is_not_transition(self):
        """AC-03: removing an existing entry is not a clean transition."""
        old = self._BASE
        new = old.replace("- [ ] a.b.0002 - Rate-limit endpoint\n", "")
        self.assertFalse(tb.classify_board_diff(old, new))

    # ── negative: marker flip without date stamp ──────────────────────────────

    def test_done_flip_without_stamp_is_not_transition(self):
        """AC-03: [~] → [x] without a (done YYYY-MM-DD) stamp is not a clean transition."""
        old = self._BASE
        new = old.replace(
            "- [~] a.b.0001 - Validate tokens  (started 2026-06-18)",
            "- [x] a.b.0001 - Validate tokens",
        )
        self.assertFalse(tb.classify_board_diff(old, new))

    def test_start_flip_without_stamp_is_not_transition(self):
        """AC-03: [ ] → [~] without a (started YYYY-MM-DD) stamp is not a clean transition."""
        old = self._BASE
        new = old.replace(
            "- [ ] a.b.0002 - Rate-limit endpoint",
            "- [~] a.b.0002 - Rate-limit endpoint",
        )
        self.assertFalse(tb.classify_board_diff(old, new))

    # ── negative: two transitions at once ────────────────────────────────────

    def test_two_simultaneous_flips_is_not_transition(self):
        """AC-03: two state changes at once is not a single clean transition."""
        old = self._BASE
        new = old.replace(
            "- [~] a.b.0001 - Validate tokens  (started 2026-06-18)",
            "- [x] a.b.0001 - Validate tokens  (done 2026-06-26)",
        ).replace(
            "- [ ] a.b.0002 - Rate-limit endpoint",
            "- [~] a.b.0002 - Rate-limit endpoint  (started 2026-06-26)",
        )
        self.assertFalse(tb.classify_board_diff(old, new))

    # ── negative: unrelated-line edit ─────────────────────────────────────────

    def test_unrelated_line_edit_is_not_transition(self):
        """AC-03: editing a non-task line (e.g., a section heading) is not a clean transition."""
        old = self._BASE
        new = old.replace("## In-flight", "## In-flight (modified)")
        self.assertFalse(tb.classify_board_diff(old, new))

    # ── negative: empty / garbled input ──────────────────────────────────────

    def test_empty_old_text_degrades_to_false(self):
        """AC-03: empty old_text never raises; degrades to False (not-transition)."""
        self.assertFalse(tb.classify_board_diff("", self._BASE))

    def test_empty_new_text_degrades_to_false(self):
        """AC-03: empty new_text never raises; degrades to False (not-transition)."""
        self.assertFalse(tb.classify_board_diff(self._BASE, ""))

    def test_none_inputs_degrade_to_false(self):
        """AC-03: None inputs never raise and degrade to False (not-transition)."""
        self.assertFalse(tb.classify_board_diff(None, None))

    def test_garbled_input_degrades_to_false(self):
        """AC-03: completely unparseable input degrades to False without raising."""
        self.assertFalse(tb.classify_board_diff("not a board at all", "also not a board"))


class ExtractTaskIdsTest(unittest.TestCase):
    """AC-10: extract_task_ids — valid dotted task-ids from arbitrary text;
    non-id tokens ignored; dedup preserves first-seen order; crash-safe."""

    # Simulated multi-commit git log output with a variety of token types.
    _GIT_LOG = (
        "commit 836154a fix(farm): scrub dispatcher secrets (#143)\n"
        "commit 3dbfd14 chore(board): mark v2.rev.0020 + v2.release.0002-0006 done (#141)\n"
        "commit 86c5b7b refactor(farm): split farm.ts god-module (#140)\n"
        "commit cafeb8e fix(hooks): heredoc false-block fix (H-09b) (#139)\n"
        "    - closes poc.auth.0001, poc.api.0002\n"
        "    - also refs v2, #142, 2026-06-20\n"
        "    - mvp1.ui.0005 was merged\n"
    )

    # ── happy-path: ids extracted from multi-line log ─────────────────────────

    def test_ids_from_git_log(self):
        """IDs embedded in real-shaped git log output are all found."""
        ids = tb.extract_task_ids(self._GIT_LOG)
        self.assertIn("v2.rev.0020", ids)
        self.assertIn("poc.auth.0001", ids)
        self.assertIn("poc.api.0002", ids)
        self.assertIn("mvp1.ui.0005", ids)

    def test_only_valid_ids_returned(self):
        """Every element returned must pass validate_id."""
        ids = tb.extract_task_ids(self._GIT_LOG)
        for tid in ids:
            self.assertTrue(tb.validate_id(tid), f"invalid id in result: {tid!r}")

    # ── non-id tokens ignored ─────────────────────────────────────────────────

    def test_issue_refs_ignored(self):
        """Issue refs like #142 are never returned."""
        ids = tb.extract_task_ids(self._GIT_LOG)
        self.assertNotIn("#142", ids)
        self.assertNotIn("#143", ids)

    def test_version_shorthand_ignored(self):
        """Two-part tokens like 'v2' (missing seq) are not extracted."""
        ids = tb.extract_task_ids("v2 some prose")
        self.assertNotIn("v2", ids)

    def test_date_string_ignored(self):
        """Date strings like 2026-06-20 are not extracted."""
        ids = tb.extract_task_ids("fixed on 2026-06-20")
        self.assertNotIn("2026-06-20", ids)

    def test_bare_words_ignored(self):
        """Plain prose words without dots are not extracted."""
        ids = tb.extract_task_ids("farm refactor hooks heredoc")
        self.assertEqual(ids, [])

    def test_git_hash_ignored(self):
        """Short git hashes (no dots) are not extracted."""
        ids = tb.extract_task_ids("commit 836154a cafeb8e 3dbfd14")
        self.assertEqual(ids, [])

    def test_under_padded_seq_ignored(self):
        """A token whose seq is fewer than 4 digits is not extracted."""
        # 3-digit seq: scanner requires {4,}
        self.assertEqual(tb.extract_task_ids("poc.auth.001"), [])
        # 2-digit seq
        self.assertEqual(tb.extract_task_ids("poc.auth.42"), [])
        # 1-digit seq
        self.assertEqual(tb.extract_task_ids("poc.auth.1"), [])

    def test_uppercase_token_ignored(self):
        """Tokens with uppercase characters are rejected by validate_id."""
        self.assertEqual(tb.extract_task_ids("PoC.auth.0001"), [])

    def test_extended_token_not_partial_matched(self):
        """A token like poc.auth.0001x is not extracted (trailing alnum blocks match)."""
        self.assertEqual(tb.extract_task_ids("poc.auth.0001x"), [])

    # ── mid-line and punctuation-surrounded ids ───────────────────────────────

    def test_mid_line_ids_found(self):
        """IDs surrounded by punctuation/whitespace mid-line are found."""
        text = "fixes (poc.auth.0001), closes poc.api.0002; done: mvp1.ui.0005.\n"
        ids = tb.extract_task_ids(text)
        self.assertIn("poc.auth.0001", ids)
        self.assertIn("poc.api.0002", ids)
        self.assertIn("mvp1.ui.0005", ids)

    def test_id_preceded_by_colon_found(self):
        """An ID immediately after a colon (e.g. 'closes: v2.rev.0020') is found."""
        ids = tb.extract_task_ids("closes: v2.rev.0020")
        self.assertIn("v2.rev.0020", ids)

    def test_id_in_parentheses_found(self):
        """An ID inside parentheses is found."""
        ids = tb.extract_task_ids("(poc.auth.0001)")
        self.assertIn("poc.auth.0001", ids)

    # ── dedup preserves first-seen order ─────────────────────────────────────

    def test_dedup_preserves_first_seen_order(self):
        """A duplicate ID appears only once; position matches first occurrence."""
        text = (
            "poc.auth.0001 some stuff\n"
            "poc.api.0002 other stuff\n"
            "poc.auth.0001 again\n"
        )
        ids = tb.extract_task_ids(text)
        self.assertEqual(ids, ["poc.auth.0001", "poc.api.0002"])

    def test_order_reflects_first_occurrence(self):
        """Ordering is by first-seen position across the whole input."""
        text = "mvp1.ui.0005 poc.auth.0001 poc.api.0002 poc.auth.0001"
        ids = tb.extract_task_ids(text)
        self.assertEqual(ids.index("mvp1.ui.0005"), 0)
        self.assertEqual(ids.index("poc.auth.0001"), 1)
        self.assertEqual(ids.index("poc.api.0002"), 2)

    # ── None / empty / garbled → [] ──────────────────────────────────────────

    def test_none_returns_empty(self):
        """None input never raises and returns []."""
        self.assertEqual(tb.extract_task_ids(None), [])

    def test_empty_string_returns_empty(self):
        """Empty string returns []."""
        self.assertEqual(tb.extract_task_ids(""), [])

    def test_garbled_input_returns_empty(self):
        """Non-matching garbled text returns []."""
        self.assertEqual(tb.extract_task_ids("#142 v2 2026-06-20 hello world"), [])

    def test_return_type_is_list(self):
        """Return type is always list, never set or other."""
        self.assertIsInstance(tb.extract_task_ids("poc.auth.0001"), list)
        self.assertIsInstance(tb.extract_task_ids(""), list)
        self.assertIsInstance(tb.extract_task_ids(None), list)


class FindBoardDriftTest(unittest.TestCase):
    """AC-08 / AC-09: find_board_drift — detects tasks whose work merged but
    whose board state was never flipped to done; unknown-id safety; pure."""

    # A minimal board with one [~], one [ ], and one [x] task.
    _BOARD = (
        "# Open tasks\n\n"
        "## In-flight\n"
        "- [~] poc.auth.0001 — Validate session tokens  (started 2026-06-18)\n"
        "- [ ] poc.api.0002 — Rate-limit the login endpoint\n"
        "- [ ] poc.ui.0003 — Login form skeleton\n\n"
        "## Done\n"
        "- [x] poc.auth.0004 — Hash passwords  (done 2026-06-15)\n"
    )
    _TODAY = datetime.date(2026, 6, 26)

    # AC-08: a [~] (in_progress) task whose id is in merged_ids → drifted
    def test_in_progress_task_in_merged_ids_is_drift(self):
        """AC-08: a [~] task that merged is returned in drifted."""
        result = tb.find_board_drift(self._BOARD, ["poc.auth.0001"], self._TODAY)
        ids = [t.id for t in result.drifted]
        self.assertIn("poc.auth.0001", ids)

    # AC-08: a [ ] (queued) task whose id is in merged_ids → drifted
    def test_queued_task_in_merged_ids_is_drift(self):
        """AC-08: a [ ] task that merged is returned in drifted."""
        result = tb.find_board_drift(self._BOARD, ["poc.api.0002"], self._TODAY)
        ids = [t.id for t in result.drifted]
        self.assertIn("poc.api.0002", ids)

    # AC-09: a [x] task in merged_ids is NOT drift
    def test_done_task_in_merged_ids_is_not_drift(self):
        """AC-09: a [x] task is excluded from drifted (already done)."""
        result = tb.find_board_drift(self._BOARD, ["poc.auth.0004"], self._TODAY)
        self.assertEqual(result.drifted, [])

    # AC-09: a merged_id absent from the board → unknown (not drifted)
    def test_unknown_merged_id_lands_in_unknown_not_drifted(self):
        """AC-09: a merged_id not present on the board surfaces in unknown, never drifted."""
        result = tb.find_board_drift(self._BOARD, ["poc.absent.9999"], self._TODAY)
        self.assertIn("poc.absent.9999", result.unknown)
        self.assertEqual(result.drifted, [])

    # A task on the board but NOT in merged_ids is completely ignored
    def test_board_task_not_in_merged_ids_is_ignored(self):
        """A board task not referenced in merged_ids does not appear in any result field."""
        result = tb.find_board_drift(self._BOARD, [], self._TODAY)
        self.assertEqual(result.drifted, [])
        self.assertEqual(result.unknown, [])

    # today is preserved in result.observed (parameter is not dead)
    def test_observed_field_is_today(self):
        """The observed field is exactly the today argument passed by the caller."""
        result = tb.find_board_drift(self._BOARD, ["poc.auth.0001"], self._TODAY)
        self.assertEqual(result.observed, self._TODAY)

    # empty board text → empty DriftResult (degenerate input rule)
    def test_empty_board_returns_empty_result(self):
        """Empty board text → empty DriftResult (drifted=[], unknown=[])."""
        result = tb.find_board_drift("", ["poc.auth.0001"], self._TODAY)
        self.assertEqual(result.drifted, [])
        self.assertEqual(result.unknown, [])

    # None board → empty DriftResult (never raises)
    def test_none_board_returns_empty_result(self):
        """None board_text → empty DriftResult, no exception."""
        result = tb.find_board_drift(None, ["poc.auth.0001"], self._TODAY)
        self.assertEqual(result.drifted, [])
        self.assertEqual(result.unknown, [])

    # empty merged_ids → empty DriftResult
    def test_empty_merged_ids_returns_empty_result(self):
        """Empty merged_ids list → nothing to check → empty DriftResult."""
        result = tb.find_board_drift(self._BOARD, [], self._TODAY)
        self.assertEqual(result.drifted, [])
        self.assertEqual(result.unknown, [])

    # None merged_ids → empty DriftResult (never raises)
    def test_none_merged_ids_returns_empty_result(self):
        """None merged_ids → empty DriftResult, no exception."""
        result = tb.find_board_drift(self._BOARD, None, self._TODAY)
        self.assertEqual(result.drifted, [])
        self.assertEqual(result.unknown, [])

    # AC-09: unknown ids are deduped, first-seen order
    def test_unknown_ids_deduped_first_seen_order(self):
        """A repeated absent id appears exactly once in unknown, in first-seen order."""
        ids = ["poc.absent.9999", "poc.other.0001", "poc.absent.9999"]
        result = tb.find_board_drift(self._BOARD, ids, self._TODAY)
        self.assertEqual(result.unknown.count("poc.absent.9999"), 1)
        # first-seen: poc.absent.9999 must precede poc.other.0001
        self.assertLess(result.unknown.index("poc.absent.9999"),
                        result.unknown.index("poc.other.0001"))

    # pure: board_text string reference is unchanged after the call
    def test_no_mutation_board_text_unchanged(self):
        """find_board_drift is pure — the board_text argument is not mutated."""
        original = self._BOARD
        snapshot = str(original)
        tb.find_board_drift(original, ["poc.auth.0001"], self._TODAY)
        self.assertEqual(original, snapshot)

    # structural: return type is DriftResult
    def test_return_type_is_driftresult(self):
        """Return value is always a DriftResult namedtuple."""
        result = tb.find_board_drift(self._BOARD, [], self._TODAY)
        self.assertIsInstance(result, tb.DriftResult)


if __name__ == "__main__":
    unittest.main()
