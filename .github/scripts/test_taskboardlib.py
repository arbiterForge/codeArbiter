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


class ValidateIdTest(unittest.TestCase):
    """AC-09: dotted ‹group›.‹type›.‹seq4› grammar + duplicate reporting."""

    def test_accepts_well_formed(self):
        for good in ("poc.auth.0001", "mvp1.api.0042", "v1.infra.0100", "v12.ui.99999"):
            self.assertTrue(tb.validate_id(good), good)

    def test_rejects_malformed(self):
        for bad in ("poc.auth", "poc.auth.1", "poc.auth.42", "poc..0001",
                    "poc.auth.0001x", "PoC.auth.0001", "poc.auth.", "", "auth.0001"):
            self.assertFalse(tb.validate_id(bad), bad)

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


class ScaffoldTest(unittest.TestCase):
    """AC-06: the init template documents the schema."""

    def test_template_documents_grammar(self):
        mod = _load("init_codearbiter", "init-codearbiter.py")
        tmpl = mod.OPEN_TASKS
        for token in ("[ ]", "[~]", "[x]", "group", "type", "Done when", "Boundaries"):
            self.assertIn(token, tmpl, token)


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


if __name__ == "__main__":
    unittest.main()
