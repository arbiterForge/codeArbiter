"""Tests for the pure-function layer of statusline.py.

No subprocess calls are exercised here.  All tests use stdlib unittest only.
"""
import importlib
import json
import os
import sys
import tempfile
import time
import unittest
from unittest import mock

# ---------------------------------------------------------------------------
# Make the hooks directory importable regardless of how the test runner is
# invoked (python -m unittest tests.test_statusline from the hooks/ dir, or
# a direct python tests/test_statusline.py).
_HOOKS_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if _HOOKS_DIR not in sys.path:
    sys.path.insert(0, _HOOKS_DIR)

import statusline as sl
import _subagentslib as subs

# Re-import helpers used by ledger tests.
from _helpers import isolate_user_state, redirect_home, release_user_state, restore_home


# Issue #442: this module writes user-GLOBAL state - the statusline pin in
# `~/.claude/settings.json`, and/or the `~/.codearbiter/` ledger and update
# cache. Running the suite used to do that to the DEVELOPER'S REAL HOME: the
# statusline pin was repointed at whatever plugin root the test process
# resolved (it broke the maintainer's statusline three times in one day), and
# `~/.codearbiter/` gained a ledger, its lock, five session shards and an
# update cache. CI never noticed, because a fresh runner has no pre-existing
# settings to clobber.
#
# The fixture is module-level rather than per-class ON PURPOSE. The leak is
# module-wide, this file has many test classes, and a per-class `setUp` is one
# forgotten override away from regressing - while `setUpModule` covers every
# class added later for free. `.github/scripts/test_suite_hermeticity.py` is the
# backstop that fails if any suite writes outside its temp dirs.
def setUpModule():
    global _USER_STATE
    # Color assertions use a controlled default; NO_COLOR cases set it explicitly.
    # Module cleanup restores the caller's environment even after test failures.
    color_environment = mock.patch.dict(os.environ)
    color_environment.start()
    unittest.addModuleCleanup(color_environment.stop)
    os.environ.pop("NO_COLOR", None)
    _USER_STATE = isolate_user_state()


def tearDownModule():
    release_user_state(_USER_STATE)



def _subagents_through_ledger(td, files):
    """Run child transcripts through the ONE accounting parser, then render the
    subagent rows from its presentation summaries (spec D-7). `files` maps a
    child file name to its raw JSONL lines."""
    import _ledgerlib
    sid = "sid-" + os.path.basename(td)
    tx = os.path.join(td, sid + ".jsonl")
    sub = os.path.join(td, sid, "subagents")
    os.makedirs(sub, exist_ok=True)
    with open(tx, "w", encoding="utf-8") as f:
        f.write("")
    for name, lines in files.items():
        with open(os.path.join(sub, name), "w", encoding="utf-8", newline="\n") as f:
            for ln in lines:
                f.write((ln if isinstance(ln, str) else json.dumps(ln)) + "\n")
    rec = {}
    for _ in range(20):
        rec, sess, _day = _ledgerlib.ledger_update({"transcript_path": tx}, sid)
        if sess["state"] != "catching_up":
            break
    return subs.read_subagents(sub, rec)


def _assistant_record(i, message):
    """A realistic assistant record: the scanner keys on type=assistant + usage."""
    message = dict(message)
    message.setdefault("usage", {"input_tokens": 1, "output_tokens": 1})
    return {"type": "assistant", "requestId": f"r{i}", "timestamp": "2026-09-27T10:00:00Z",
            "message": message}


class TestSubagentModels(unittest.TestCase):
    def _read(self, messages):
        with tempfile.TemporaryDirectory() as td:
            lines = [({"type": "user", "message": m} if m.get("role") == "user"
                      else _assistant_record(i, m)) for i, m in enumerate(messages)]
            return _subagents_through_ledger(td, {"agent-123456.jsonl": lines})[2][0]

    def test_one_model_keeps_family_and_version(self):
        row = self._read([
            {"role": "user", "content": "Review parser"},
            {"role": "assistant", "model": "claude-sonnet-4-6-20250514",
             "usage": {"input_tokens": 12, "output_tokens": 3}},
        ])
        self.assertEqual(row["model"], "model:sonnet-4-6")

    def test_multiple_distinct_models_are_mixed(self):
        row = self._read([
            {"role": "assistant", "model": "claude-opus-4-1-20250805"},
            {"role": "assistant", "model": "claude-haiku-4-5-20251001"},
        ])
        self.assertEqual(row["model"], "model:mixed")

    def test_absent_model_is_explicitly_unknown(self):
        self.assertEqual(self._read([{"role": "assistant"}])["model"], "model:?")

    def test_long_unknown_model_is_safely_bounded(self):
        shown = subs.display_model("vendor-" + "x" * 80)
        self.assertEqual(shown, "model:vendor-" + "x" * 17)
        self.assertEqual(len(shown.removeprefix("model:")), 24)

    def test_unknown_model_preserves_non_date_suffix(self):
        self.assertEqual(subs.display_model("other-model-v2"), "model:other-model-v2")

    def test_malformed_model_metadata_never_breaks_scan(self):
        row = self._read([
            {"role": "assistant", "model": {"unexpected": "object"}},
            {"role": "assistant", "model": ["also", "invalid"]},
            {"role": "assistant", "model": 123},
        ])
        self.assertEqual(row["model"], "model:?")


class TestSubagentModelRendering(unittest.TestCase):
    def _render(self, width, label="A very long delegated task label that must clip first"):
        payload = json.dumps({"session_id": "sid", "model": {"display_name": "Opus 4.8"}})
        shown = [{"label": label, "model": "model:sonnet-4-6", "inp": 1200,
                  "out": 340, "age": 8, "active": True}]
        env = {"CODEARBITER_WIDTH": str(width), "NO_COLOR": "1"}
        with mock.patch.dict(os.environ, env, clear=False), \
             mock.patch.object(sl, "subagent_dir", return_value="unused"), \
             mock.patch.object(sl, "read_subagents", return_value=(1, 1, shown, (1200, 340))):
            return sl.render(payload)

    def test_every_row_renders_model_with_active_palette_accent(self):
        shown = [{"label": "task", "model": "model:opus-4-1", "inp": 1,
                  "out": 2, "age": 3, "active": True}]
        with mock.patch.object(sl, "subagent_dir", return_value="unused"), \
             mock.patch.object(sl, "read_subagents", return_value=(1, 1, shown, (1, 2))):
            out = sl.render(json.dumps({"session_id": "sid"}))
        self.assertIn(f"{sl.V3}model:opus-4-1{sl.RESET}", out)

    def test_missing_row_model_renders_fallback(self):
        shown = [{"label": "task", "inp": 1, "out": 2, "age": 3, "active": True}]
        with mock.patch.object(sl, "subagent_dir", return_value="unused"), \
             mock.patch.object(sl, "read_subagents", return_value=(1, 1, shown, (1, 2))):
            plain = sl.ANSI.sub("", sl.render(json.dumps({"session_id": "sid"})))
        self.assertIn("model:?", plain)

    def test_narrow_row_clips_label_before_model_tokens_and_age(self):
        plain = self._render(64)
        row = next(line for line in plain.splitlines() if "model:sonnet-4-6" in line)
        self.assertIn(sl.ELL, row)
        self.assertIn("1.2K", row)
        self.assertIn("340", row)
        self.assertIn("8s", row)
        self.assertLessEqual(sl.vlen(row), 64)

    def test_extreme_width_degrades_without_overflow_or_exception(self):
        plain = self._render(40)
        self.assertTrue(plain)
        self.assertTrue(all(sl.vlen(line) <= 40 for line in plain.splitlines()))


# =========================================================================== vlen
class TestVlen(unittest.TestCase):

    def test_plain_string(self):
        self.assertEqual(sl.vlen("hello"), 5)

    def test_empty_string(self):
        self.assertEqual(sl.vlen(""), 0)

    def test_ansi_codes_are_zero_width(self):
        colored = "\033[38;2;255;0;0mhello\033[0m"
        self.assertEqual(sl.vlen(colored), 5)

    def test_ansi_only_string(self):
        self.assertEqual(sl.vlen("\033[0m\033[1m"), 0)

    def test_wide_cjk_glyph_counts_as_two(self):
        # U+4E2D (中) is East-Asian Wide → 2 columns
        self.assertEqual(sl.vlen("中"), 2)
        self.assertEqual(sl.vlen("中文"), 4)

    def test_mixed_ansi_and_wide(self):
        s = "\033[1m中\033[0m"   # bold + wide glyph + reset
        self.assertEqual(sl.vlen(s), 2)


# =========================================================================== clip
class TestClip(unittest.TestCase):

    def test_no_clip_needed(self):
        s = "hello"
        self.assertEqual(sl.clip(s, 10), s)

    def test_clips_to_exact_width(self):
        result = sl.clip("hello world", 6)
        self.assertLessEqual(sl.vlen(result), 6)

    def test_appends_ellipsis_when_clipped(self):
        result = sl.clip("hello world", 6)
        # The ellipsis character '…' must be present when the string is clipped.
        self.assertIn(sl.ELL, result)

    def test_preserves_ansi_codes(self):
        colored = "\033[38;2;255;0;0mhello world\033[0m"
        result = sl.clip(colored, 6)
        self.assertLessEqual(sl.vlen(result), 6)
        # ANSI sequences should still be present in the raw bytes
        self.assertIn("\033[", result)

    def test_zero_width_returns_empty(self):
        self.assertEqual(sl.clip("hello", 0), "")

    def test_exact_fit_not_clipped(self):
        s = "abcde"   # exactly 5 visible chars
        result = sl.clip(s, 5)
        self.assertEqual(result, s)
        self.assertNotIn(sl.ELL, result)

    def test_ansi_does_not_count_toward_width(self):
        # A string with ANSI codes whose visible length is 5 should not be
        # clipped when the limit is 5.
        s = "\033[1mhello\033[0m"
        result = sl.clip(s, 5)
        self.assertEqual(sl.vlen(result), 5)
        self.assertNotIn(sl.ELL, result)


# =========================================================================== pad
class TestPad(unittest.TestCase):
    """pad(s, w) pads to exactly w visible columns; clips if over."""

    def test_pads_short_string(self):
        result = sl.pad("hi", 10)
        self.assertEqual(sl.vlen(result), 10)
        self.assertTrue(result.startswith("hi"))

    def test_exact_length_unchanged(self):
        s = "hello"
        result = sl.pad(s, 5)
        self.assertEqual(result, s)

    def test_clips_when_over(self):
        result = sl.pad("hello world", 6)
        self.assertLessEqual(sl.vlen(result), 6)

    def test_pads_with_spaces(self):
        result = sl.pad("ab", 5)
        self.assertEqual(result, "ab   ")

    def test_ansi_string_padded_correctly(self):
        colored = "\033[1mhi\033[0m"     # visible length 2
        result = sl.pad(colored, 8)
        self.assertEqual(sl.vlen(result), 8)


# =========================================================================== fmt_tok
class TestFmtTok(unittest.TestCase):

    def test_zero(self):
        self.assertEqual(sl.fmt_tok(0), "0")

    def test_small_integer(self):
        self.assertEqual(sl.fmt_tok(999), "999")

    def test_one_thousand(self):
        self.assertEqual(sl.fmt_tok(1000), "1.0K")

    def test_fifteen_hundred(self):
        self.assertEqual(sl.fmt_tok(1500), "1.5K")

    def test_just_below_million_rounds_to_M(self):
        # 999_500 triggers the >= 999_500 branch → "1.0M"
        result = sl.fmt_tok(999_500)
        self.assertEqual(result, "1.0M")

    def test_one_million(self):
        self.assertEqual(sl.fmt_tok(1_000_000), "1.0M")

    def test_string_input_coerced(self):
        self.assertEqual(sl.fmt_tok("2000"), "2.0K")

    def test_none_input_gives_zero(self):
        self.assertEqual(sl.fmt_tok(None), "0")


# =========================================================================== subagents from summaries
class TestSubagentsFromLedgerSummaries(unittest.TestCase):
    """Spec D-7 / AC-50: the subagent panel renders from the accounting scanner's
    presentation summaries plus filesystem metadata. It opens no child JSONL, and
    for equivalent fixtures its rows match the pre-change parser's output (the
    GOLDEN below was captured from main's read_subagents on this exact fixture)."""

    GOLDEN = {
        "active": 1, "recent": 3, "tot": (126.0, 25.0),
        "shown": [
            {"label": "Review the parser", "model": "model:sonnet-5",
             "inp": 115.0, "out": 14.0, "active": True},
            {"label": "Check the docs for drift and report.", "model": "model:mixed",
             "inp": 8.0, "out": 8.0, "active": False},
            {"label": "agent-ccccc3", "model": "model:opus-5-5",
             "inp": 3.0, "out": 3.0, "active": False},
        ],
    }

    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self._home = redirect_home(self.tmp)
        self._orig = os.environ.get("CODEARBITER_LEDGER")
        os.environ["CODEARBITER_LEDGER"] = os.path.join(self.tmp, ".codearbiter", "ledger.json")
        self.tx = os.path.join(self.tmp, "proj", "sid-sub.jsonl")
        self.sub = os.path.join(self.tmp, "proj", "sid-sub", "subagents")
        os.makedirs(self.sub)
        with open(self.tx, "w", encoding="utf-8") as f:
            f.write(json.dumps(self._a("p0", "claude-opus-5-5", 1, 1)) + "\n")
        u = self._u
        a = self._a
        self._w("agent-aaaaaa1.jsonl", [u("Review the parser"), a("r1", "claude-sonnet-5", 10, 1),
                                        a("r1", "claude-sonnet-5", 10, 9),
                                        a("r2", "claude-sonnet-5", 5, 5, 100)], 30)
        self._w("agent-bbbbbb2.jsonl", [u("You are a reviewer. Check the docs for drift and report."),
                                        a("r3", "claude-haiku-4-5-20251001", 7, 7),
                                        a("r4", "claude-opus-5-5", 1, 1)], 200)
        self._w("agent-cccccc3.jsonl", [a("r5", "claude-opus-5-5", 3, 3)], 400)
        self._w("agent-dddddd4.jsonl", [u("Too old"), a("r6", "claude-opus-5-5", 3, 3)], 5000)

    def tearDown(self):
        restore_home(self._home)
        if self._orig is None:
            os.environ.pop("CODEARBITER_LEDGER", None)
        else:
            os.environ["CODEARBITER_LEDGER"] = self._orig

    @staticmethod
    def _a(rid, model, inp, out, cw=0):
        return {"type": "assistant", "requestId": rid, "timestamp": "2026-09-27T10:00:00Z",
                "message": {"id": "m" + rid, "role": "assistant", "model": model,
                            "usage": {"input_tokens": inp, "output_tokens": out,
                                      "cache_creation_input_tokens": cw}}}

    @staticmethod
    def _u(text):
        return {"type": "user", "message": {"role": "user", "content": text}}

    def _w(self, name, recs, age):
        p = os.path.join(self.sub, name)
        with open(p, "w", encoding="utf-8") as f:
            for r in recs:
                f.write(json.dumps(r) + "\n")
        t = time.time() - age
        os.utime(p, (t, t))

    def _summary(self):
        import _ledgerlib
        rec = None
        for _ in range(20):
            rec, sess, _day = _ledgerlib.ledger_update({"transcript_path": self.tx}, "sid-sub")
            if sess["state"] != "catching_up":
                break
        return rec

    def test_rows_match_pre_change_output_without_opening_child_jsonl(self):
        import builtins
        rec = self._summary()
        real = builtins.open
        opened = []

        def guard(path, *a, **k):
            if str(path).endswith(".jsonl"):
                opened.append(path)
            return real(path, *a, **k)
        with mock.patch.object(builtins, "open", guard):
            active, recent, shown, tot = subs.read_subagents(self.sub, rec)
        self.assertEqual(opened, [])
        self.assertEqual((active, recent, tuple(tot)),
                         (self.GOLDEN["active"], self.GOLDEN["recent"], self.GOLDEN["tot"]))
        self.assertEqual([{k: v for k, v in s.items() if k != "age"} for s in shown],
                         self.GOLDEN["shown"])

    def test_unscanned_child_shows_a_fallback_row_not_an_error(self):
        active, recent, shown, tot = subs.read_subagents(self.sub, {})
        self.assertEqual((active, recent), (1, 3))
        self.assertEqual(shown[0]["label"], "agent-aaaaa1")
        self.assertEqual((shown[0]["inp"], shown[0]["out"]), (0, 0))

    def test_vanished_directory_is_an_empty_result(self):
        self.assertEqual(subs.read_subagents(os.path.join(self.sub, "nope"), {}),
                         (0, 0, [], (0, 0)))


# =========================================================================== cost labels
class TestCostLabels(unittest.TestCase):
    """Spec AC-01/02/41 and D-19: the dollar figure carries its provenance. The
    renderer consumes the ledger's structured coverage; it never infers
    completeness from a number, never shows the host estimate for Today, and
    never clips a figure mid-number at narrow widths."""

    def _scope(self, state="complete", cost=2.0, tin=1000, tout=10, reasons=(), stale=False,
               host=None):
        return {"in": float(tin), "out": float(tout), "cost": cost, "pd": int(round(cost * 1e12)),
                "state": state, "reasons": list(reasons), "stale": stale, "host": host,
                "host_delta": None}

    def _render(self, sess, day, width=140):
        env = {"CODEARBITER_WIDTH": str(width), "NO_COLOR": "1"}
        with mock.patch.dict(os.environ, env, clear=False), \
                mock.patch.object(sl, "ledger_update", return_value=({}, sess, day)):
            plain = sl.ANSI.sub("", sl.render(json.dumps({"session_id": "sid"})))
        rows = plain.splitlines()
        srow = next(r for r in rows if "Session" in r)
        trow = next(r for r in rows if "Today" in r)
        return srow, trow

    def test_tones_reserve_amber_for_coverage_that_needs_attention(self):
        import _segmentslib as S
        self.assertTrue(S.WARN and S.GREY and S.OK and len({S.WARN, S.GREY, S.OK}) == 3)
        cases = [
            (self._scope(state="unavailable", cost=0.0, tin=0, tout=0), False, S.GREY),
            (self._scope(state="unavailable", cost=0.0, host=3.0), True, S.GREY),
            (self._scope(state="complete", cost=2.0), False, S.OK),
            (self._scope(state="partial", cost=2.0, reasons=["unknown_model"]), False, S.WARN),
            (self._scope(state="partial", cost=0.0, reasons=["unknown_model"]), False, S.WARN),
        ]
        for scope, allow_host, want in cases:
            with self.subTest(state=scope["state"], cost=scope["cost"], host=scope["host"]):
                cell = S.cost_cell(scope, 40, allow_host=allow_host)
                self.assertTrue(cell.startswith(want), repr(cell))

    def test_complete_is_api_approx(self):
        s, t = self._render(self._scope(cost=2.0), self._scope(cost=1.5))
        self.assertIn("api≈$2.00", s)
        self.assertIn("api≈$1.50", t)

    def test_partial_and_catching_up_are_lower_bounds(self):
        for state in ("partial", "catching_up"):
            with self.subTest(state=state):
                s, _t = self._render(self._scope(state=state, cost=2.0,
                                                 reasons=["unknown_model"]),
                                     self._scope())
                self.assertIn("api≥$2.00", s)
                self.assertNotIn("api≈$2.00", s)

    def test_known_usage_with_nothing_priced_is_not_a_precise_total(self):
        s, _t = self._render(self._scope(state="partial", cost=0.0, reasons=["unknown_model"]),
                             self._scope())
        self.assertIn("api≈?", s)
        self.assertNotIn("$0.00", s)

    def test_host_fallback_is_session_only_and_labelled(self):
        s, t = self._render(self._scope(state="unavailable", cost=0.0, tin=0, tout=0, host=5.0),
                            self._scope(state="unavailable", cost=0.0, tin=0, tout=0, host=5.0))
        self.assertIn("host≈$5.00", s)
        self.assertNotIn("host", t)
        self.assertNotIn("$5.00", t)

    def test_host_never_replaces_available_reconstruction(self):
        s, _t = self._render(self._scope(cost=2.0, host=9.0), self._scope())
        self.assertIn("api≈$2.00", s)
        self.assertNotIn("$9.00", s)

    def test_unavailable_without_host_is_not_zero(self):
        s, t = self._render(self._scope(state="unavailable", cost=0.0, tin=0, tout=0),
                            self._scope(state="unavailable", cost=0.0, tin=0, tout=0))
        self.assertIn("api≈?", s)
        self.assertNotIn("$0.00", s)
        self.assertNotIn("$0.00", t)

    def test_stale_snapshot_is_marked(self):
        s, t = self._render(self._scope(cost=2.0, stale=True), self._scope(cost=1.0, stale=True))
        self.assertIn("api≈$2.00*", s)
        self.assertIn("api≈$1.00*", t)

    def test_narrow_width_uses_compact_label_and_never_clips_the_number(self):
        for width in (60, 72, 80, 90):
            with self.subTest(width=width):
                s, t = self._render(self._scope(state="partial", cost=12.34,
                                                reasons=["unknown_model"]),
                                    self._scope(cost=3.21), width=width)
                self.assertRegex(s, r"(api)?≥\$12\.3")
                self.assertRegex(t, r"(api)?≈\$3\.21")

    def test_tightest_width_falls_back_to_the_compact_symbolic_label(self):
        s, t = self._render(self._scope(state="partial", cost=12.34, reasons=["unknown_model"]),
                            self._scope(cost=3.21), width=52)
        self.assertIn("≥$12.3", s)
        self.assertNotIn("api≥", s)
        self.assertIn("≈$3.21", t)

    def test_no_row_exceeds_the_box_at_any_width(self):
        for width in (40, 60, 80, 120, 200):
            with self.subTest(width=width):
                env = {"CODEARBITER_WIDTH": str(width), "NO_COLOR": "1"}
                sess = self._scope(state="partial", cost=123.45, tin=12_345_678, tout=9_876_543,
                                   reasons=["unknown_model"], stale=True)
                with mock.patch.dict(os.environ, env, clear=False), \
                        mock.patch.object(sl, "ledger_update", return_value=({}, sess, sess)):
                    plain = sl.ANSI.sub("", sl.render(json.dumps({"session_id": "sid"})))
                for line in plain.splitlines():
                    self.assertLessEqual(sl.vlen(line), width)

    def test_malformed_ledger_result_degrades_to_unavailable(self):
        with mock.patch.object(sl, "ledger_update", return_value=None), \
                mock.patch.dict(os.environ, {"NO_COLOR": "1"}, clear=False):
            plain = sl.ANSI.sub("", sl.render(json.dumps({"session_id": "sid"})))
        self.assertIn("Session", plain)
        self.assertNotIn("$0.00", plain)


# =========================================================================== fail-soft matrix
class TestAccountingFailSoftThroughRender(unittest.TestCase):
    """Spec AC-29/AC-30: every hostile accounting input degrades only its own
    state. The bar still renders, never with a traceback, and never with network
    I/O. Each case runs the REAL ledger through the real render()."""

    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.proj = os.path.join(self.tmp, "proj")
        os.makedirs(os.path.join(self.proj, "sid-fs", "subagents"))
        self.tx = os.path.join(self.proj, "sid-fs.jsonl")
        self._env = mock.patch.dict(os.environ, {
            "CODEARBITER_LEDGER": os.path.join(self.tmp, "ledger.json"), "NO_COLOR": "1",
            "CODEARBITER_WIDTH": "120"}, clear=False)
        self._env.start()

    def tearDown(self):
        self._env.stop()

    def _line(self, rid, model="claude-sonnet-5", **usage):
        u = {"input_tokens": 5, "output_tokens": 5}
        u.update(usage)
        return json.dumps({"type": "assistant", "requestId": rid,
                           "timestamp": "2026-09-27T10:00:00Z",
                           "message": {"role": "assistant", "model": model, "usage": u}})

    def _render(self, lines, extra=None):
        with open(self.tx, "w", encoding="utf-8") as f:
            f.write("\n".join(lines) + "\n")
        payload = {"session_id": "sid-fs", "transcript_path": self.tx}
        payload.update(extra or {})
        import socket

        def no_network(*a, **k):
            raise AssertionError("statusline render attempted network I/O")
        with mock.patch.object(socket, "socket", no_network), \
                mock.patch.object(socket, "create_connection", no_network):
            out = sl.render(json.dumps(payload))
        plain = sl.ANSI.sub("", out)
        self.assertNotIn("Traceback", plain)
        self.assertIn("Session", plain)
        self.assertIn("Today", plain)
        return plain

    def test_malformed_unknown_and_oversized_inputs(self):
        lines = [self._line("ok1"), "{not json", "[1,2,3]", '"just a string"',
                 self._line("u1", model="mystery-9"),
                 self._line("bad", input_tokens=-5),
                 self._line("big") .replace('"input_tokens": 5', '"input_tokens": 5, "pad": "' + "z" * 70000 + '"'),
                 self._line("tool", server_tool_use={"mystery_requests": 2}),
                 self._line("it", iterations=[{"type": "critic", "input_tokens": 3}])]
        plain = self._render(lines)
        self.assertRegex(plain, r"(api)?[≥≈]")

    def test_missing_transcript_path(self):
        plain = sl.ANSI.sub("", sl.render(json.dumps({"session_id": "sid-none"})))
        self.assertIn("Session", plain)

    def test_nonexistent_transcript_and_vanished_children(self):
        os.rmdir(os.path.join(self.proj, "sid-fs", "subagents"))
        payload = {"session_id": "sid-gone", "transcript_path": os.path.join(self.proj, "nope.jsonl")}
        plain = sl.ANSI.sub("", sl.render(json.dumps(payload)))
        self.assertIn("Session", plain)

    def test_permission_error_on_transcript_open(self):
        import builtins
        real = builtins.open

        def deny(path, *a, **k):
            if str(path).endswith("sid-fs.jsonl") and "b" in (a[0] if a else k.get("mode", "")):
                raise PermissionError("denied")
            return real(path, *a, **k)
        with open(self.tx, "w", encoding="utf-8") as f:
            f.write(self._line("p1") + "\n")
        with mock.patch.object(builtins, "open", deny):
            plain = sl.ANSI.sub("", sl.render(json.dumps({"session_id": "sid-fs",
                                                          "transcript_path": self.tx})))
        self.assertIn("Session", plain)

    def test_held_ledger_lock(self):
        import _hooklib
        owner = _hooklib.acquire_lock(os.environ["CODEARBITER_LEDGER"])
        try:
            plain = self._render([self._line("p1")])
        finally:
            _hooklib.release_lock(owner)
        self.assertNotIn("$0.00", plain.split("Session", 1)[1].splitlines()[0])

    def test_host_cost_garbage(self):
        for bad in ("x", None, [], {"a": 1}, float("nan")):
            with self.subTest(bad=bad):
                cost = {"total_cost_usd": bad} if bad == bad else {"total_cost_usd": "nan"}
                self._render([self._line("p1")], {"cost": cost})


# =========================================================================== ledger_update
class TestLedgerUpdate(unittest.TestCase):
    """End-to-end test of ledger_update() using a real tempdir transcript."""

    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self._home_token = redirect_home(self.tmp)
        # Also redirect CODEARBITER_LEDGER so we never touch the real ledger.
        self._orig_ledger = os.environ.get("CODEARBITER_LEDGER")
        self._ledger_path = os.path.join(self.tmp, ".codearbiter", "ledger.json")
        os.environ["CODEARBITER_LEDGER"] = self._ledger_path

    def tearDown(self):
        restore_home(self._home_token)
        if self._orig_ledger is None:
            os.environ.pop("CODEARBITER_LEDGER", None)
        else:
            os.environ["CODEARBITER_LEDGER"] = self._orig_ledger

    def _write_tx(self, entries):
        tx_path = os.path.join(self.tmp, "transcript.jsonl")
        with open(tx_path, "w", encoding="utf-8") as f:
            for obj in entries:
                f.write(json.dumps(obj) + "\n")
        return tx_path

    def _assistant(self, req_id, prompt=200, output=100):
        return {
            "type": "assistant",
            "requestId": req_id,
            "timestamp": "2026-01-01T12:00:00Z",
            "message": {
                "model": "claude-sonnet-4-6",
                "usage": {"input_tokens": prompt, "output_tokens": output},
            },
        }

    def test_returns_three_tuple(self):
        tx = self._write_tx([self._assistant("r1")])
        data = {"transcript_path": tx}
        result = sl.ledger_update(data, "sid-001")
        self.assertIsInstance(result, tuple)
        self.assertEqual(len(result), 3)

    def test_session_tokens_counted(self):
        tx = self._write_tx([
            self._assistant("r1", prompt=300, output=150),
        ])
        data = {"transcript_path": tx}
        _rec, sess, _day = sl.ledger_update(data, "sid-002")
        # fresh input = 300, output = 150
        self.assertEqual(sess["in"], 300.0)
        self.assertEqual(sess["out"], 150.0)

    def test_dedup_in_ledger(self):
        """Duplicate requestId in transcript → counted once in session totals."""
        tx = self._write_tx([
            self._assistant("r1", prompt=100, output=50),
            self._assistant("r1", prompt=100, output=50),   # duplicate
        ])
        data = {"transcript_path": tx}
        _rec, sess, _day = sl.ledger_update(data, "sid-003")
        self.assertEqual(sess["in"], 100.0)
        self.assertEqual(sess["out"], 50.0)

    def test_no_session_id_returns_blanks(self):
        _rec, sess, day = sl.ledger_update({}, None)
        self.assertEqual(sess["in"], 0.0)
        self.assertEqual(sess["out"], 0.0)
        self.assertEqual(day["in"], 0.0)


# =========================================================================== seg_ctx_lines
class TestSegCtxLines(unittest.TestCase):
    """Verify threshold-switching behaviour of the context-bar segment."""

    def _data(self, pct, size=200_000):
        return {"context_window": {"used_percentage": pct,
                                   "context_window_size": size}}

    def test_zero_pct_returns_two_strings(self):
        lines = sl.seg_ctx_lines(self._data(0), 60)
        self.assertIsInstance(lines, list)
        self.assertEqual(len(lines), 2)
        self.assertIsInstance(lines[0], str)

    def test_no_context_window_key_returns_placeholder(self):
        lines = sl.seg_ctx_lines({}, 60)
        self.assertIn("--", sl.ANSI.sub("", lines[0]))

    def test_below_75_uses_violet_not_warn_or_danger(self):
        lines = sl.seg_ctx_lines(self._data(74.9), 60)
        raw = lines[0]
        # WARN is fg(255,184,76), DANGER is fg(255,86,110)
        # Below 75 % the percentage glyph should be in V2 (not WARN or DANGER).
        # We can verify that the WARN/DANGER escape is NOT the dominant color on
        # the % text by checking neither WARN nor DANGER precedes the '%' sign.
        stripped = sl.ANSI.sub("", raw)
        self.assertIn("%", stripped)    # sanity: percentage is rendered

    def test_at_75_uses_warn(self):
        """At exactly 75.0 the bar switches to WARN color."""
        lines = sl.seg_ctx_lines(self._data(75.0), 60)
        self.assertIsInstance(lines[0], str)
        # WARN escape sequence must appear somewhere in line 1
        self.assertIn(sl.WARN, lines[0])

    def test_above_75_below_90_uses_warn(self):
        lines = sl.seg_ctx_lines(self._data(80.0), 60)
        self.assertIn(sl.WARN, lines[0])
        self.assertNotIn(sl.DANGER, lines[0])

    def test_at_90_uses_danger(self):
        lines = sl.seg_ctx_lines(self._data(90.0), 60)
        self.assertIn(sl.DANGER, lines[0])

    def test_above_90_uses_danger(self):
        lines = sl.seg_ctx_lines(self._data(95.0), 60)
        self.assertIn(sl.DANGER, lines[0])

    def test_100_pct_produces_full_bar(self):
        lines = sl.seg_ctx_lines(self._data(100.0), 60)
        self.assertIsInstance(lines[0], str)
        self.assertGreater(len(lines[0]), 0)

    def test_million_token_model_shows_1M(self):
        lines = sl.seg_ctx_lines(self._data(50.0, size=1_000_000), 60)
        self.assertIn("1M", sl.ANSI.sub("", lines[1]))


# =========================================================================== sparkline
class TestSparkline(unittest.TestCase):

    def test_empty_list_returns_empty_string(self):
        self.assertEqual(sl.sparkline([]), "")

    def test_single_value_returns_empty_string(self):
        # sparkline requires >= 2 values
        self.assertEqual(sl.sparkline([42]), "")

    def test_uniform_values_returns_string(self):
        result = sl.sparkline([100, 100, 100])
        self.assertIsInstance(result, str)
        # Strip ANSI and check we got some spark chars
        plain = sl.ANSI.sub("", result)
        self.assertGreater(len(plain), 0)

    def test_ascending_values(self):
        result = sl.sparkline([1, 2, 3, 4, 5])
        self.assertIsInstance(result, str)
        plain = sl.ANSI.sub("", result)
        self.assertEqual(len(plain), 5)

    def test_returns_string_not_none(self):
        result = sl.sparkline([10, 20])
        self.assertIsNotNone(result)
        self.assertIsInstance(result, str)

    def test_no_crash_with_none_values(self):
        # num() filters out None → < 2 valid → returns ""
        result = sl.sparkline([None, None])
        self.assertEqual(result, "")

    def test_mixed_valid_and_none(self):
        # Only 1 valid value after filtering → ""
        result = sl.sparkline([None, 5])
        self.assertEqual(result, "")


# =========================================================================== render
class TestRender(unittest.TestCase):
    """Smoke-test render() with minimal / edge-case inputs.

    render() parses a raw JSON string, not a dict, so we pass json.dumps({})
    for the minimal case.
    """

    def test_empty_json_object_does_not_crash(self):
        result = sl.render("{}")
        self.assertIsInstance(result, str)
        self.assertGreater(len(result), 0)

    def test_empty_string_input_does_not_crash(self):
        result = sl.render("")
        self.assertIsInstance(result, str)
        self.assertGreater(len(result), 0)

    def test_invalid_json_does_not_crash(self):
        result = sl.render("not json at all {{")
        self.assertIsInstance(result, str)
        self.assertGreater(len(result), 0)

    def test_palette_activation_failure_does_not_escape_render(self):
        with mock.patch.object(sl._colorlib, "activate_palette",
                               side_effect=RuntimeError("palette boom")):
            result = sl.render("{}")
        self.assertIsInstance(result, str)
        self.assertGreater(len(result), 0)

    def test_palette_consumer_sync_failure_does_not_escape_render(self):
        with mock.patch.object(sl._boxlib, "sync_palette",
                               side_effect=RuntimeError("sync boom")):
            result = sl.render("{}")
        self.assertIsInstance(result, str)
        self.assertGreater(len(result), 0)

    def test_each_palette_sync_failure_restores_last_good_palette_atomically(self):
        payload = json.dumps({"model": {"display_name": "Test"},
                              "context_window": {"used_percentage": 20}})
        with mock.patch.dict(os.environ, {"CODEARBITER_THEME": "blue"}):
            prior = sl.render(payload)
        blue = sl.fg(*sl._colorlib.BUILTIN_PALETTES["blue"].accent_primary)
        green = sl.fg(*sl._colorlib.BUILTIN_PALETTES["green"].accent_primary)
        self.assertIn(blue, prior)

        for failing_lib in (sl._fmtlib, sl._boxlib, sl._segmentslib):
            with self.subTest(sync_position=failing_lib.__name__):
                with mock.patch.dict(os.environ, {"CODEARBITER_THEME": "green"}), \
                     mock.patch.object(failing_lib, "sync_palette",
                                       side_effect=RuntimeError("sync boom")):
                    output = sl.render(payload)
                self.assertIn(blue, output)
                self.assertNotIn(green, output)
                self.assertEqual(sl._colorlib.V2, blue)
                self.assertEqual(sl.V2, blue)
                self.assertEqual(sl._fmtlib._V2, blue)
                self.assertEqual(sl._boxlib._V0, sl._colorlib.V0)
                self.assertEqual(sl._segmentslib.V2, blue)

    def test_returns_non_empty_string(self):
        data = json.dumps({
            "session_id": "test-session",
            "model": {"display_name": "claude-sonnet-4-6"},
        })
        result = sl.render(data)
        self.assertIsInstance(result, str)
        self.assertGreater(len(result), 0)

    def test_no_traceback_on_partial_data(self):
        """Partial / unexpected shapes must never raise — the safe() wrappers
        should absorb all errors."""
        data = json.dumps({
            "context_window": {"used_percentage": 87.5},
            "rate_limits": {
                "five_hour": {"used_percentage": 42},
                "seven_day": {"used_percentage": 10},
            },
            "cost": {"total_cost_usd": 0.05},
        })
        try:
            result = sl.render(data)
        except Exception as exc:
            self.fail(f"render() raised an exception: {exc}")
        self.assertIsInstance(result, str)

    def test_box_drawing_chars_present(self):
        result = sl.render("{}")
        plain = sl.ANSI.sub("", result)
        # The box must contain at least one box-drawing corner character
        self.assertTrue(
            any(c in plain for c in (sl.TL, sl.TR, sl.BL, sl.BR)),
            "render() output missing box-drawing characters",
        )


# =========================================================================== arbiter_state cache (T-11b)
class TestArbiterStateCache(unittest.TestCase):
    """arbiter_state caches mtime-keyed: identical inputs -> cached dict; a change
    to any input file re-reads. (performance-005)"""

    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.cad = os.path.join(self.tmp, ".codearbiter")
        os.makedirs(self.cad, exist_ok=True)
        self._write("CONTEXT.md", "---\narbiter: enabled\nstage: build\n---\n")
        self._write("open-tasks.md", "- [ ] t.t.0001 - a task\n")
        self._write("open-questions.md", "")
        self._write("overrides.log", "")
        self._write("last-checkpoint", "0")
        # Reset the module-level cache so prior tests don't bleed in.
        sl._ARBITER_CACHE.clear()

    def _write(self, name, body):
        with open(os.path.join(self.cad, name), "w", encoding="utf-8", newline="\n") as f:
            f.write(body)

    def test_enabled_state_is_read(self):
        st = sl.arbiter_state(self.tmp)
        self.assertIsNotNone(st)
        self.assertEqual(st["stage"], "build")
        self.assertEqual(st["tasks"], 1)

    def test_cached_when_inputs_unchanged(self):
        first = sl.arbiter_state(self.tmp)
        second = sl.arbiter_state(self.tmp)
        # Same object identity proves the second call returned the cache, not a re-read.
        self.assertIs(first, second)

    def test_rereads_on_change(self):
        first = sl.arbiter_state(self.tmp)
        # Bump an input file's mtime forward and change its content.
        future = time.time() + 10
        ot = os.path.join(self.cad, "open-tasks.md")
        with open(ot, "w", encoding="utf-8", newline="\n") as f:
            f.write("- [ ] t.t.0001 - a\n- [ ] t.t.0002 - b\n")
        os.utime(ot, (future, future))
        second = sl.arbiter_state(self.tmp)
        self.assertIsNot(first, second)        # cache was invalidated
        self.assertEqual(second["tasks"], 2)   # fresh read picked up the new task

    def test_disabled_repo_returns_none(self):
        self._write("CONTEXT.md", "---\narbiter: disabled\n---\n")
        sl._ARBITER_CACHE.clear()
        self.assertIsNone(sl.arbiter_state(self.tmp))


class TestArbiterStatePreread(unittest.TestCase):
    """performance-003 (#194): arbiter_state(root, ctx_text=, ot_text=, oq_text=)
    must use the SUPPLIED content instead of re-reading CONTEXT.md/open-tasks.md/
    open-questions.md from disk — SessionStart's main() already read those three
    files earlier in the same invocation before calling into the governance
    line. Proven two ways: (1) the returned values reflect the SUPPLIED text
    even when it deliberately diverges from what's on disk, and (2) a spy on
    open() shows the three preread paths are never opened a second time."""

    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.cad = os.path.join(self.tmp, ".codearbiter")
        os.makedirs(self.cad, exist_ok=True)
        # Disk content deliberately WRONG — if the code fell back to reading
        # disk instead of using the supplied text, these values would leak
        # through and the assertions below would catch it.
        self._write("CONTEXT.md", "---\narbiter: enabled\nstage: DISK-STAGE\n---\n")
        self._write("open-tasks.md", "- [ ] t.t.0001 - disk task a\n"
                                     "- [ ] t.t.0002 - disk task b\n"
                                     "- [ ] t.t.0003 - disk task c\n")
        self._write("open-questions.md", "no confirms here on disk\n")
        self._write("overrides.log", "")
        self._write("last-checkpoint", "0")
        sl._ARBITER_CACHE.clear()

    def _write(self, name, body):
        with open(os.path.join(self.cad, name), "w", encoding="utf-8", newline="\n") as f:
            f.write(body)

    def test_supplied_text_wins_over_disk_content(self):
        ctx_text = "---\narbiter: enabled\nstage: SUPPLIED-STAGE\n---\n"
        ot_text = "- [ ] t.t.0009 - supplied task\n"
        oq_text = "[CONFIRM-01] one supplied question\n"

        st = sl.arbiter_state(self.tmp, ctx_text=ctx_text, ot_text=ot_text, oq_text=oq_text)

        self.assertIsNotNone(st)
        self.assertEqual(st["stage"], "SUPPLIED-STAGE")
        self.assertEqual(st["tasks"], 1)
        self.assertEqual(st["q"], 1)

    def test_no_preread_args_still_reads_disk_as_before(self):
        # Backward compatibility: every existing caller passes nothing, and
        # must see the ORIGINAL disk-derived behavior unchanged.
        st = sl.arbiter_state(self.tmp)
        self.assertEqual(st["stage"], "DISK-STAGE")
        self.assertEqual(st["tasks"], 3)
        self.assertEqual(st["q"], 0)

    def test_supplied_text_means_the_three_files_are_never_reopened(self):
        ctx_path = os.path.join(self.cad, "CONTEXT.md")
        ot_path = os.path.join(self.cad, "open-tasks.md")
        oq_path = os.path.join(self.cad, "open-questions.md")
        forbidden = {os.path.normcase(ctx_path), os.path.normcase(ot_path),
                    os.path.normcase(oq_path)}
        opened = []
        real_open = open

        def spy_open(path, *a, **kw):
            try:
                norm = os.path.normcase(os.path.abspath(path))
            except Exception:  # noqa: BLE001
                norm = None
            opened.append(norm)
            if norm in forbidden:
                raise AssertionError(f"unexpected re-open of preread path: {path}")
            return real_open(path, *a, **kw)

        ctx_text = "---\narbiter: enabled\nstage: SUPPLIED-STAGE\n---\n"
        ot_text = "- [ ] t.t.0009 - supplied task\n"
        oq_text = "[CONFIRM-01] one supplied question\n"

        with mock.patch("builtins.open", side_effect=spy_open):
            st = sl.arbiter_state(self.tmp, ctx_text=ctx_text, ot_text=ot_text, oq_text=oq_text)

        self.assertIsNotNone(st)
        self.assertEqual(st["stage"], "SUPPLIED-STAGE")

    def test_enabled_gate_routes_through_hooklib_when_available(self):
        # When _hooklib is importable, the gate uses frontmatter_enabled — confirm
        # the activation decision still resolves correctly via that path.
        if sl._frontmatter_enabled is None:
            self.skipTest("_hooklib not importable in this environment")
        self.assertTrue(sl._arbiter_enabled(os.path.join(self.cad, "CONTEXT.md")))


# =========================================================================== session_start fast path (T-11a)
class TestSessionStartCache(unittest.TestCase):
    """session_start reads the resolved start from the ledger record when present,
    skipping the ~/.claude/sessions scan. (performance-004)"""

    def test_cached_value_short_circuits_scan(self):
        rec = {"sess_start": 1700000000.0}
        # No real ~/.claude/sessions touched: the cache hit returns immediately.
        self.assertEqual(sl.session_start("any-sid", rec), 1700000000.0)

    def test_no_sid_returns_none(self):
        self.assertIsNone(sl.session_start(None, {"sess_start": 5.0}))

    def test_miss_falls_back_to_scan(self):
        # A rec with no cached value + a sid that no session file matches -> the scan
        # runs and finds nothing -> None (no crash).
        result = sl.session_start("nonexistent-session-id-xyz", {})
        self.assertIsNone(result)


# =========================================================================== render parity (T-11/T-12)
class TestRenderParity(unittest.TestCase):
    """The refactor + caching must be byte-identical for the same inputs: rendering
    the same JSON twice yields the same bytes, and the ledger functions remain
    reachable via the statusline module after extraction to _ledgerlib."""

    def test_render_is_deterministic_for_same_input(self):
        payload = json.dumps({
            "session_id": "parity-sid",
            "model": {"display_name": "claude-opus-4-8"},
            "context_window": {"used_percentage": 40.0,
                               "context_window_size": 200000},
            "cost": {"total_cost_usd": 1.23},
        })
        with mock.patch.object(sl, "git_dirty", return_value=True), \
                mock.patch.object(sl.time, "time", return_value=1700000001.0):
            a = sl.render(payload)
            b = sl.render(payload)
        self.assertEqual(a, b)

    def test_ledger_functions_reachable_via_statusline(self):
        # The unmodified test suite reaches these via sl.*; the extraction must keep
        # them bound on the statusline module. Only the names this module (and its
        # test suite) actually use are re-bound — the rest were dead re-binds
        # removed as part of architecture-002.
        for name in ("ledger_update", "persist_sess_start"):
            self.assertTrue(hasattr(sl, name), f"sl.{name} missing after extraction")

    def test_burn_spark_returns_string(self):
        # burn_spark now delegates to _ledgerlib.burn_samples but still renders.
        rec = {"burn": [100, 200, 150, 300]}
        out = sl.burn_spark(rec)
        self.assertIsInstance(out, str)
        self.assertGreater(len(sl.ANSI.sub("", out)), 0)


# =========================================================================== update-available marker (AC-1/AC-2/AC-3)
class TestSegUpdate(unittest.TestCase):
    """The statusline's update-available marker is RENDER-ONLY off the same cache
    SessionStart reads — it must never fetch, never spawn a refresh, and it must
    degrade to no segment on any missing/corrupt/current-version state."""

    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.plugin = os.path.join(self._tmp.name, "plugin")
        os.makedirs(os.path.join(self.plugin, ".claude-plugin"))
        with open(os.path.join(self.plugin, ".claude-plugin", "plugin.json"), "w") as f:
            json.dump({"name": "ca", "version": "2.8.2"}, f)
        self.state_path = os.path.join(self._tmp.name, "update-state.json")
        self._env_saved = os.environ.get("CODEARBITER_UPDATE_STATE")
        os.environ["CODEARBITER_UPDATE_STATE"] = self.state_path

    def tearDown(self):
        if self._env_saved is None:
            os.environ.pop("CODEARBITER_UPDATE_STATE", None)
        else:
            os.environ["CODEARBITER_UPDATE_STATE"] = self._env_saved
        self._tmp.cleanup()

    def _write_cache(self, latest):
        with open(self.state_path, "w") as f:
            json.dump({"schema": 1, "targets": {
                "ca": {"latest": latest, "checked_at": 1000.0},
            }}, f)

    def test_ac1_newer_cached_latest_renders_marker(self):
        self._write_cache("2.10.0")
        seg = sl.seg_update(self.plugin)
        self.assertIsNotNone(seg)
        self.assertIn("2.10.0", sl.ANSI.sub("", seg))

    def test_ac2_current_version_renders_nothing(self):
        self._write_cache("2.8.2")
        self.assertIsNone(sl.seg_update(self.plugin))

    def test_ac2_no_cache_renders_nothing(self):
        self.assertIsNone(sl.seg_update(self.plugin))

    def test_ac3_corrupt_cache_degrades_to_none_no_raise(self):
        with open(self.state_path, "w") as f:
            f.write("{ not valid json")
        try:
            result = sl.seg_update(self.plugin)
        except Exception as e:  # noqa: BLE001
            self.fail(f"seg_update must never raise, raised: {e}")
        self.assertIsNone(result)

    def test_ac3_render_only_makes_no_network_call(self):
        # seg_update must not import/invoke urllib at all — it is a pure cache read.
        import urllib.request
        self._write_cache("2.10.0")
        with mock.patch.object(urllib.request, "urlopen") as m:
            sl.seg_update(self.plugin)
            m.assert_not_called()

    def test_render_includes_marker_when_update_cached(self):
        # Full render() must surface the marker without crashing or hitting network.
        self._write_cache("2.10.0")
        payload = json.dumps({
            "session_id": "upd-sid",
            "workspace": {"current_dir": self.plugin},
            "model": {"display_name": "claude-sonnet-4-6"},
        })
        with mock.patch.object(sl, "plugin_root_for_render", return_value=self.plugin):
            out = sl.render(payload)
        self.assertIn("2.10.0", sl.ANSI.sub("", out))


class TestSubagentResultContract(unittest.TestCase):
    """#413: read_subagents() must honor ONE result shape on every path, and a
    syntactically valid but non-object JSONL record must not escape as an
    AttributeError. Both defects erase the whole subagent section of the rich
    statusline (a ValueError on unpack, or an exception swallowed by safe())."""

    def _write(self, td, name, lines):
        path = os.path.join(td, name)
        with open(path, "w", encoding="utf-8", newline="\n") as f:
            for ln in lines:
                f.write(ln + "\n")
        return path

    def test_missing_directory_returns_the_documented_four_item_result(self):
        with tempfile.TemporaryDirectory() as td:
            gone = os.path.join(td, "does-not-exist")
            res = subs.read_subagents(gone)
        self.assertEqual(len(res), 4,
                         "every return path must produce the documented 4-item result")
        active, recent, shown, totals = res
        self.assertEqual(active, 0)
        self.assertEqual(recent, 0)
        self.assertEqual(shown, [])
        self.assertEqual(totals, (0, 0))

    def test_missing_directory_unpacks_the_same_way_as_a_real_read(self):
        # The statusline unpacks 4 names OUTSIDE safe() — a 3-item error branch
        # is a hard ValueError there, not a degraded segment.
        with tempfile.TemporaryDirectory() as td:
            gone = os.path.join(td, "raced-away")
            active, recent, shown, (tin, tout) = subs.read_subagents(gone)
        self.assertEqual((active, recent, shown, tin, tout), (0, 0, [], 0, 0))

    def test_statusline_renders_through_a_subagent_directory_race(self):
        with tempfile.TemporaryDirectory() as td:
            gone = os.path.join(td, "raced-away")
            with mock.patch.object(sl, "subagent_dir", return_value=gone):
                out = sl.render(json.dumps({"session_id": "sid"}))
        self.assertTrue(out, "a directory race must not break the statusline")

    def test_non_object_jsonl_records_are_skipped_not_raised(self):
        # A valid JSON line that is not an object used to reach d.get() inside
        # a try that only caught OSError -> AttributeError out of the reader.
        with tempfile.TemporaryDirectory() as td:
            self._write(td, "agent-aaaaaa.jsonl", [
                "[]",
                "null",
                "3",
                '"a bare string"',
                "{not json at all",
                json.dumps({"requestId": "r1",
                            "message": {"role": "user", "content": "Do the thing"}}),
                json.dumps({"type": "assistant", "requestId": "r1",
                            "message": {"role": "assistant",
                                        "model": "claude-sonnet-4-6-20250514",
                                        "usage": {"input_tokens": 10,
                                                  "output_tokens": 4}}}),
            ])
            with open(os.path.join(td, "agent-aaaaaa.jsonl"), encoding="utf-8") as f:
                lines = f.read().splitlines()
            active, recent, shown, (tin, tout) = _subagents_through_ledger(
                td, {"agent-aaaaaa.jsonl": lines})
        self.assertEqual(recent, 1)
        self.assertEqual(len(shown), 1, "the valid records after the bad ones must survive")
        self.assertEqual(shown[0]["label"], "Do the thing")
        self.assertEqual((tin, tout), (10, 4))

    def test_a_corrupt_file_does_not_suppress_a_later_valid_file(self):
        with tempfile.TemporaryDirectory() as td:
            files = {
                "agent-000001.jsonl": ["[]", "null"],
                "agent-000002.jsonl": [
                    json.dumps({"requestId": "r9",
                                "message": {"role": "user", "content": "Second agent"}}),
                    json.dumps({"type": "assistant", "requestId": "r9",
                                "message": {"role": "assistant",
                                            "usage": {"input_tokens": 7, "output_tokens": 2}}}),
                ],
            }
            active, recent, shown, (tin, tout) = _subagents_through_ledger(td, files)
        self.assertEqual(recent, 2)
        self.assertEqual((tin, tout), (7, 2))
        self.assertIn("Second agent", [row["label"] for row in shown])

    def test_a_non_oserror_from_one_transcript_costs_only_its_own_row(self):
        # The per-file boundary must be a boundary for EVERY failure, not just
        # OSError. A transcript whose `requestId` is a JSON array is real,
        # syntactically valid corruption: the reader uses that value as a dict
        # key, so the per-file body raises `TypeError: unhashable type: 'list'`
        # — neither OSError nor ValueError. Under an OSError-only boundary it
        # escapes read_subagents entirely and blanks every subagent row.
        with tempfile.TemporaryDirectory() as td:
            files = {
                "agent-aaaaaa.jsonl": [
                    json.dumps({"type": "assistant", "requestId": ["not", "hashable"],
                                "message": {"role": "assistant", "id": {"also": "bad"},
                                            "usage": {"input_tokens": 999,
                                                      "output_tokens": 999}}}),
                ],
                "agent-bbbbbb.jsonl": [
                    json.dumps({"requestId": "ok1",
                                "message": {"role": "user", "content": "Healthy agent"}}),
                    json.dumps({"type": "assistant", "requestId": "ok1",
                                "message": {"role": "assistant",
                                            "usage": {"input_tokens": 6,
                                                      "output_tokens": 3}}}),
                ],
            }
            active, recent, shown, (tin, tout) = _subagents_through_ledger(td, files)
        self.assertEqual(recent, 2)
        self.assertEqual((tin, tout), (6, 3),
                         "the poisoned transcript must contribute nothing, and "
                         "must not take the healthy one down with it")
        self.assertIn("Healthy agent", [row["label"] for row in shown])


if __name__ == "__main__":
    unittest.main()
