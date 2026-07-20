"""Codex tribunal usage recovery and telemetry aggregation tests."""
import importlib.util
import io
import json
import os
import tempfile
import unittest
from contextlib import redirect_stdout
from unittest import mock


_REPO = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", "..", ".."))
_SCRIPT = os.path.join(
    _REPO, "plugins", "ca-codex", "hooks", "tribunal-usage.py")
_SPEC = importlib.util.spec_from_file_location("codex_tribunal_usage", _SCRIPT)
_usage = importlib.util.module_from_spec(_SPEC)
_SPEC.loader.exec_module(_usage)


def _write_jsonl(path, records):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as handle:
        for record in records:
            handle.write(json.dumps(record) + "\n")


def _meta(thread_id):
    return {"type": "session_meta", "payload": {"id": thread_id}}


def _token_count(total, last=None):
    usage = {
        "input_tokens": total - 9,
        "cached_input_tokens": total - 20,
        "cache_write_input_tokens": 0,
        "output_tokens": 9,
        "reasoning_output_tokens": 4,
        "total_tokens": total,
    }
    return {
        "type": "event_msg",
        "payload": {
            "type": "token_count",
            "info": {
                "total_token_usage": usage,
                "last_token_usage": last or usage,
            },
        },
    }


class ObserveUsageTests(unittest.TestCase):
    THREAD_ID = "019f7db8-de8e-7dc2-9aa7-5dc06865d3d2"

    def test_exact_thread_uses_latest_cumulative_token_count(self):
        with tempfile.TemporaryDirectory() as root:
            path = os.path.join(
                root, "2026", "07", "20", f"rollout-{self.THREAD_ID}.jsonl")
            _write_jsonl(path, [
                _meta(self.THREAD_ID),
                _token_count(100),
                {"type": "response_item", "payload": {"type": "message"}},
                _token_count(250),
            ])

            result = _usage.observe_usage(self.THREAD_ID, root)

        self.assertEqual(result["status"], "observed")
        self.assertEqual(result["source"], "codex-session-transcript-best-effort")
        self.assertEqual(result["tokens"], 250)
        self.assertEqual(result["token_usage"]["input_tokens"], 241)
        self.assertEqual(result["token_usage"]["cached_input_tokens"], 230)
        self.assertEqual(result["token_usage"]["output_tokens"], 9)
        self.assertEqual(result["token_usage"]["reasoning_output_tokens"], 4)

    def test_missing_exact_thread_is_explicitly_unavailable(self):
        with tempfile.TemporaryDirectory() as root:
            result = _usage.observe_usage(self.THREAD_ID, root)

        self.assertEqual(result, {
            "status": "unavailable",
            "reason": "transcript-unavailable",
        })

    def test_present_transcript_with_changed_shape_reports_format_reason(self):
        with tempfile.TemporaryDirectory() as root:
            path = os.path.join(root, f"rollout-{self.THREAD_ID}.jsonl")
            _write_jsonl(path, [
                _meta(self.THREAD_ID),
                {"type": "usage_event", "payload": {"total": 99}},
            ])

            result = _usage.observe_usage(self.THREAD_ID, root)

        self.assertEqual(result, {
            "status": "unavailable",
            "reason": "transcript-format-unsupported",
        })

    def test_deep_malformed_usage_fails_soft(self):
        with tempfile.TemporaryDirectory() as root:
            path = os.path.join(root, f"rollout-{self.THREAD_ID}.jsonl")
            nested = "[" * 2000 + "0" + "]" * 2000
            with open(path, "w", encoding="utf-8") as handle:
                handle.write(json.dumps(_meta(self.THREAD_ID)) + "\n")
                handle.write(
                    '{"type":"event_msg","payload":{"type":"token_count",'
                    '"info":{"total_token_usage":' + nested + '}}}\n')

            result = _usage.observe_usage(self.THREAD_ID, root)

        self.assertEqual(result, {
            "status": "unavailable",
            "reason": "usage-invalid",
        })

    def test_candidate_scan_limit_fails_soft(self):
        with tempfile.TemporaryDirectory() as root:
            for index in range(2):
                path = os.path.join(
                    root, str(index), f"rollout-{self.THREAD_ID}.jsonl")
                _write_jsonl(path, [_meta(self.THREAD_ID), _token_count(10)])
            with mock.patch.object(_usage, "MAX_CANDIDATES", 1):
                result = _usage.observe_usage(self.THREAD_ID, root)

        self.assertEqual(result, {
            "status": "unavailable",
            "reason": "transcript-scan-limit-exceeded",
        })

    def test_transcript_size_limit_remains_distinct(self):
        with tempfile.TemporaryDirectory() as root:
            path = os.path.join(root, f"rollout-{self.THREAD_ID}.jsonl")
            _write_jsonl(path, [_meta(self.THREAD_ID), _token_count(10)])
            with mock.patch.object(_usage, "MAX_TRANSCRIPT_BYTES", 8):
                result = _usage.observe_usage(self.THREAD_ID, root)

        self.assertEqual(result, {
            "status": "unavailable",
            "reason": "transcript-over-limit",
        })

    def test_candidate_replaced_by_outside_symlink_is_not_followed(self):
        with tempfile.TemporaryDirectory() as parent:
            root = os.path.join(parent, "sessions")
            outside = os.path.join(parent, "outside.jsonl")
            path = os.path.join(root, f"rollout-{self.THREAD_ID}.jsonl")
            _write_jsonl(path, [_meta(self.THREAD_ID), _token_count(10)])
            _write_jsonl(outside, [_meta(self.THREAD_ID), _token_count(999)])
            os.remove(path)
            try:
                os.symlink(outside, path)
            except (OSError, NotImplementedError) as error:
                self.skipTest(f"symlinks unavailable: {error}")

            usage, reason = _usage._read_candidate(
                path, self.THREAD_ID, root)

        self.assertIsNone(usage)
        self.assertEqual(reason, "transcript-unavailable")

    def test_invalid_thread_id_never_becomes_a_path_probe(self):
        with tempfile.TemporaryDirectory() as root:
            result = _usage.observe_usage("../../outside", root)

        self.assertEqual(result, {
            "status": "unavailable",
            "reason": "invalid-agent-thread-id",
        })


class AggregateUsageTests(unittest.TestCase):
    @staticmethod
    def _observed(tokens):
        usage = {
            "input_tokens": tokens,
            "cached_input_tokens": 0,
            "cache_write_input_tokens": 0,
            "output_tokens": 0,
            "reasoning_output_tokens": 0,
            "total_tokens": tokens,
        }
        return {
            "event": "lens-completed",
            "tokens": tokens,
            "tokens_status": "observed",
            "tokens_source": "codex-session-transcript-best-effort",
            "token_usage": usage,
        }

    def test_numeric_lenses_aggregate_to_complete_actual(self):
        result = _usage.aggregate_events([
            self._observed(120),
            {"event": "wave-flushed"},
            self._observed(80),
        ])

        self.assertEqual(result, {
            "tokens_actual": 200,
            "tokens_actual_status": "complete",
            "tokens_unavailable_reasons": [],
        })

    def test_mixed_observation_is_partial_and_preserves_reason(self):
        result = _usage.aggregate_events([
            self._observed(120),
            {"event": "lens-completed", "tokens_status": "unavailable",
             "tokens_reason": "transcript-unavailable"},
        ])

        self.assertEqual(result, {
            "tokens_actual": 120,
            "tokens_actual_status": "partial",
            "tokens_unavailable_reasons": ["transcript-unavailable"],
        })

    def test_explicit_unavailable_status_cannot_be_erased_by_numeric_tokens(self):
        result = _usage.aggregate_events([
            {"event": "lens-completed", "tokens": 0,
             "tokens_status": "unavailable",
             "tokens_reason": "host-usage-unsupported"},
        ])

        self.assertEqual(result, {
            "tokens_actual": None,
            "tokens_actual_status": "unavailable",
            "tokens_unavailable_reasons": ["host-usage-unsupported"],
        })

    def test_explicit_observed_status_requires_valid_numeric_tokens(self):
        result = _usage.aggregate_events([
            {"event": "lens-completed", "tokens": None,
             "tokens_status": "observed"},
        ])

        self.assertEqual(result, {
            "tokens_actual": None,
            "tokens_actual_status": "unavailable",
            "tokens_unavailable_reasons": ["usage-invalid"],
        })

    def test_observed_status_requires_the_schema_receipt(self):
        result = _usage.aggregate_events([
            {"event": "lens-completed", "tokens": 12,
             "tokens_status": "observed"},
        ])

        self.assertEqual(result, {
            "tokens_actual": None,
            "tokens_actual_status": "unavailable",
            "tokens_unavailable_reasons": ["usage-invalid"],
        })

    def test_observed_receipt_requires_every_usage_component(self):
        result = _usage.aggregate_events([
            {"event": "lens-completed", "tokens": 12,
             "tokens_status": "observed",
             "tokens_source": "codex-session-transcript-best-effort",
             "token_usage": {"total_tokens": 12}},
        ])

        self.assertEqual(result, {
            "tokens_actual": None,
            "tokens_actual_status": "unavailable",
            "tokens_unavailable_reasons": ["usage-invalid"],
        })

    def test_unknown_reason_is_scrubbed_to_fixed_enum(self):
        result = _usage.aggregate_events([
            {"event": "lens-completed", "tokens_status": "unavailable",
             "tokens_reason": r"C:\\Users\\alice\\private customer"},
        ])

        self.assertEqual(result, {
            "tokens_actual": None,
            "tokens_actual_status": "unavailable",
            "tokens_unavailable_reasons": ["reason-invalid"],
        })

    def test_unknown_status_cannot_bypass_reason_scrubbing(self):
        result = _usage.aggregate_events([
            {"event": "lens-completed", "tokens_status": "bogus",
             "tokens_reason": r"C:\\Users\\alice\\private customer"},
        ])

        self.assertEqual(result, {
            "tokens_actual": None,
            "tokens_actual_status": "unavailable",
            "tokens_unavailable_reasons": ["reason-invalid"],
        })

    def test_no_observed_usage_distinguishes_host_and_instrumentation(self):
        result = _usage.aggregate_events([
            {"event": "lens-completed", "tokens_status": "unavailable",
             "tokens_reason": "host-usage-unsupported"},
            {"event": "lens-completed", "tokens_status": "unavailable",
             "tokens_reason": "transcript-format-unsupported"},
        ])

        self.assertEqual(result, {
            "tokens_actual": None,
            "tokens_actual_status": "unavailable",
            "tokens_unavailable_reasons": [
                "host-usage-unsupported", "transcript-format-unsupported"],
        })

    def test_cli_aggregate_reads_run_log_and_emits_one_json_line(self):
        with tempfile.TemporaryDirectory() as root:
            run_log = os.path.join(root, "run.jsonl")
            _write_jsonl(run_log, [
                self._observed(42),
            ])
            stdout = io.StringIO()
            with redirect_stdout(stdout):
                code = _usage.main(["aggregate", "--run-log", run_log])

        self.assertEqual(code, 0)
        self.assertEqual(json.loads(stdout.getvalue()), {
            "tokens_actual": 42,
            "tokens_actual_status": "complete",
            "tokens_unavailable_reasons": [],
        })

    def test_oversized_run_log_returns_fixed_reason(self):
        with tempfile.TemporaryDirectory() as root:
            run_log = os.path.join(root, "run.jsonl")
            _write_jsonl(run_log, [{"event": "lens-completed"}])
            stdout = io.StringIO()
            with mock.patch.object(_usage, "MAX_RUN_LOG_BYTES", 8):
                with redirect_stdout(stdout):
                    code = _usage.main(["aggregate", "--run-log", run_log])

        self.assertEqual(code, 0)
        self.assertEqual(json.loads(stdout.getvalue()), {
            "tokens_actual": None,
            "tokens_actual_status": "unavailable",
            "tokens_unavailable_reasons": ["run-log-over-limit"],
        })


class SurfaceWiringTests(unittest.TestCase):
    @staticmethod
    def _read(*parts):
        with open(os.path.join(_REPO, *parts), encoding="utf-8") as handle:
            return handle.read()

    def test_codex_tribunal_records_thread_receipt_and_explicit_states(self):
        routine = self._read(
            "plugins", "ca-codex", "routines", "tribunal", "SKILL.md")
        schema = self._read(
            "plugins", "ca-codex", "routines", "tribunal", "references",
            "schemas.md")

        self.assertIn("tribunal-usage.py observe --thread-id", routine)
        self.assertIn("copy `source` as `tokens_source`", routine)
        self.assertIn('"agent_thread_id"', schema)
        self.assertIn('"tokens_status":"observed|unavailable"', schema)
        self.assertIn("transcript-format-unsupported", schema)
        self.assertIn("transcript-scan-limit-exceeded", schema)
        self.assertIn("reason-invalid", schema)
        self.assertIn(
            "no subagent dispatch capability", routine)
        self.assertIn(
            "dispatch succeeds but returns no usable thread ID", routine)

    def test_codex_telemetry_uses_aggregate_result_not_a_hand_tally(self):
        telemetry = self._read(
            "plugins", "ca-codex", "routines", "tribunal", "references",
            "telemetry.md")

        self.assertIn("tribunal-usage.py aggregate --run-log", telemetry)
        self.assertIn('"tokens_actual_status":"complete|partial|unavailable"',
                      telemetry)
        self.assertIn('"tokens_unavailable_reasons":[]', telemetry)
        self.assertIn("`run-log-over-limit`", telemetry)

    def test_claude_tribunal_does_not_reference_codex_session_parser(self):
        claude = self._read("plugins", "ca", "skills", "tribunal", "SKILL.md")
        telemetry = self._read(
            "plugins", "ca", "skills", "tribunal", "references", "telemetry.md")

        self.assertNotIn("tribunal-usage.py", claude)
        self.assertNotIn("tokens_actual_status", telemetry)


if __name__ == "__main__":
    unittest.main()
