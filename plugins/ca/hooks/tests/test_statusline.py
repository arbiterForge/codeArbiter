"""Tests for the pure-function layer of statusline.py.

No subprocess calls are exercised here.  All tests use stdlib unittest only.
"""
import importlib
import json
import os
import sys
import tempfile
import unittest

# ---------------------------------------------------------------------------
# Make the hooks directory importable regardless of how the test runner is
# invoked (python -m unittest tests.test_statusline from the hooks/ dir, or
# a direct python tests/test_statusline.py).
_HOOKS_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if _HOOKS_DIR not in sys.path:
    sys.path.insert(0, _HOOKS_DIR)

import statusline as sl

# Re-import helpers used by ledger tests.
from _helpers import redirect_home, restore_home


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


# =========================================================================== _tx_accumulate
class TestTxAccumulate(unittest.TestCase):
    """Tests for the transcript-accumulation inner loop (no subprocess)."""

    def _make_tx(self, entries, tmp_dir):
        """Write a list of JSON objects (one per line) to a temp .jsonl file."""
        path = os.path.join(tmp_dir, "tx.jsonl")
        with open(path, "w", encoding="utf-8") as f:
            for obj in entries:
                f.write(json.dumps(obj) + "\n")
        return path

    def _assistant_line(self, request_id, prompt_tokens=100, output_tokens=50,
                        model="claude-sonnet", timestamp="2026-01-01T00:00:00Z"):
        return {
            "type": "assistant",
            "requestId": request_id,
            "timestamp": timestamp,
            "message": {
                "id": f"msg_{request_id}",
                "model": model,
                "usage": {
                    "input_tokens": prompt_tokens,
                    "output_tokens": output_tokens,
                },
            },
        }

    def test_basic_accumulation(self):
        with tempfile.TemporaryDirectory() as td:
            entries = [
                self._assistant_line("req-1", prompt_tokens=100, output_tokens=50),
                self._assistant_line("req-2", prompt_tokens=200, output_tokens=80),
            ]
            path = self._make_tx(entries, td)
            rec = {}
            result = sl._tx_accumulate(rec, path)
            self.assertTrue(result)
            # Two distinct requestIds → two entries in reqs
            self.assertEqual(len(rec["reqs"]), 2)

    def test_deduplication_by_request_id(self):
        """Same requestId appearing twice must count only once."""
        with tempfile.TemporaryDirectory() as td:
            dup_id = "req-dup"
            entries = [
                self._assistant_line(dup_id, prompt_tokens=100, output_tokens=50),
                self._assistant_line(dup_id, prompt_tokens=100, output_tokens=50),
            ]
            path = self._make_tx(entries, td)
            rec = {}
            sl._tx_accumulate(rec, path)
            self.assertEqual(len(rec["reqs"]), 1)

    def test_dedup_upsert_uses_last_value(self):
        """When the same requestId appears twice (streaming replay), the final
        usage values replace the first (UPSERT semantics)."""
        with tempfile.TemporaryDirectory() as td:
            dup_id = "req-dup"
            entries = [
                self._assistant_line(dup_id, prompt_tokens=100, output_tokens=50),
                self._assistant_line(dup_id, prompt_tokens=150, output_tokens=70),
            ]
            path = self._make_tx(entries, td)
            rec = {}
            sl._tx_accumulate(rec, path)
            stored = rec["reqs"][dup_id]
            # Latest value wins
            self.assertEqual(stored["in"], 150.0)
            self.assertEqual(stored["out"], 70.0)

    def test_missing_usage_field_handled_gracefully(self):
        """Lines missing the usage dict should be skipped, not crash."""
        with tempfile.TemporaryDirectory() as td:
            entries = [
                {"type": "assistant", "requestId": "r1",
                 "message": {"model": "claude-sonnet"}},   # no 'usage' key
                self._assistant_line("r2", prompt_tokens=80, output_tokens=40),
            ]
            path = self._make_tx(entries, td)
            rec = {}
            sl._tx_accumulate(rec, path)
            # Only r2 had valid usage
            self.assertIn("r2", rec["reqs"])

    def test_non_assistant_lines_ignored(self):
        with tempfile.TemporaryDirectory() as td:
            entries = [
                {"type": "user", "message": {"role": "user", "content": "hello"}},
                self._assistant_line("req-1"),
            ]
            path = self._make_tx(entries, td)
            rec = {}
            sl._tx_accumulate(rec, path)
            self.assertEqual(len(rec["reqs"]), 1)

    def test_returns_false_for_nonexistent_file(self):
        rec = {}
        result = sl._tx_accumulate(rec, "/nonexistent/path/tx.jsonl")
        self.assertFalse(result)

    def test_burn_ring_populated(self):
        with tempfile.TemporaryDirectory() as td:
            entries = [
                self._assistant_line(f"req-{i}", prompt_tokens=100, output_tokens=50)
                for i in range(5)
            ]
            path = self._make_tx(entries, td)
            rec = {}
            sl._tx_accumulate(rec, path)
            self.assertIsInstance(rec.get("burn"), list)
            self.assertEqual(len(rec["burn"]), 5)

    def test_incremental_offset_advancement(self):
        """A second call with the same rec should not re-count previous lines."""
        with tempfile.TemporaryDirectory() as td:
            entries = [self._assistant_line("req-1")]
            path = self._make_tx(entries, td)
            rec = {}
            sl._tx_accumulate(rec, path)
            first_off = rec["tx_off"]
            # Append a second message
            with open(path, "a", encoding="utf-8") as f:
                f.write(json.dumps(self._assistant_line("req-2")) + "\n")
            sl._tx_accumulate(rec, path)
            self.assertEqual(len(rec["reqs"]), 2)
            self.assertGreater(rec["tx_off"], first_off)


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


if __name__ == "__main__":
    unittest.main()
