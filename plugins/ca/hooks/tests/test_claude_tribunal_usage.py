"""Claude tribunal usage recovery and surface wiring tests."""
import importlib.util
import json
import os
import tempfile
import unittest
from unittest import mock


_REPO = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", "..", ".."))
_SCRIPT = os.path.join(_REPO, "plugins", "ca", "hooks", "tribunal-usage.py")


def _load_usage():
    spec = importlib.util.spec_from_file_location("claude_tribunal_usage", _SCRIPT)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _write_jsonl(path, records):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as handle:
        for record in records:
            handle.write(json.dumps(record) + "\n")


def _assistant(agent_id, input_tokens, output_tokens, cache_create, cache_read):
    return {
        "type": "assistant",
        "agentId": agent_id,
        "message": {
            "role": "assistant",
            "usage": {
                "input_tokens": input_tokens,
                "output_tokens": output_tokens,
                "cache_creation_input_tokens": cache_create,
                "cache_read_input_tokens": cache_read,
            },
        },
    }


class ObserveClaudeUsageTests(unittest.TestCase):
    AGENT_ID = "a0e2261cfa8ee1499"

    @staticmethod
    def _path(root, agent_id):
        return os.path.join(
            root, "project-key", "session-id", "subagents",
            f"agent-{agent_id}.jsonl")

    def test_exact_agent_sums_every_usage_component(self):
        usage = _load_usage()
        with tempfile.TemporaryDirectory() as root:
            _write_jsonl(self._path(root, self.AGENT_ID), [
                _assistant(self.AGENT_ID, 11, 13, 17, 19),
                {"type": "user", "agentId": self.AGENT_ID,
                 "message": {"role": "user"}},
                _assistant(self.AGENT_ID, 23, 29, 31, 37),
            ])

            result = usage.observe_usage(self.AGENT_ID, root)

        self.assertEqual(result, {
            "status": "observed",
            "source": "claude-subagent-transcript",
            "tokens": 180,
            "token_usage": {
                "input_tokens": 34,
                "cache_creation_input_tokens": 48,
                "cache_read_input_tokens": 56,
                "output_tokens": 42,
                "total_tokens": 180,
            },
        })

    def test_missing_exact_agent_is_explicitly_unavailable(self):
        usage = _load_usage()
        with tempfile.TemporaryDirectory() as root:
            result = usage.observe_usage(self.AGENT_ID, root)

        self.assertEqual(result, {
            "status": "unavailable",
            "reason": "transcript-unavailable",
        })

    def test_changed_transcript_shape_has_a_distinct_reason(self):
        usage = _load_usage()
        with tempfile.TemporaryDirectory() as root:
            _write_jsonl(self._path(root, self.AGENT_ID), [
                {"type": "assistant", "agentId": self.AGENT_ID,
                 "message": {"role": "assistant"}},
            ])

            result = usage.observe_usage(self.AGENT_ID, root)

        self.assertEqual(result, {
            "status": "unavailable",
            "reason": "transcript-format-unsupported",
        })

    def test_usage_on_non_assistant_record_is_invalid(self):
        usage = _load_usage()
        with tempfile.TemporaryDirectory() as root:
            record = _assistant(self.AGENT_ID, 1, 2, 3, 4)
            record["type"] = "user"
            record["message"]["role"] = "user"
            _write_jsonl(self._path(root, self.AGENT_ID), [record])

            result = usage.observe_usage(self.AGENT_ID, root)

        self.assertEqual(result, {
            "status": "unavailable",
            "reason": "usage-invalid",
        })

    def test_usage_missing_a_component_is_invalid(self):
        usage = _load_usage()
        with tempfile.TemporaryDirectory() as root:
            record = _assistant(self.AGENT_ID, 1, 2, 3, 4)
            del record["message"]["usage"]["cache_read_input_tokens"]
            _write_jsonl(self._path(root, self.AGENT_ID), [record])

            result = usage.observe_usage(self.AGENT_ID, root)

        self.assertEqual(result, {
            "status": "unavailable",
            "reason": "usage-invalid",
        })

    def test_invalid_agent_id_never_becomes_a_path_probe(self):
        usage = _load_usage()
        with tempfile.TemporaryDirectory() as root:
            result = usage.observe_usage("../../outside", root)

        self.assertEqual(result, {
            "status": "unavailable",
            "reason": "invalid-agent-id",
        })

    def test_candidate_scan_limit_fails_soft(self):
        usage = _load_usage()
        with tempfile.TemporaryDirectory() as root:
            for index in range(2):
                _write_jsonl(
                    os.path.join(root, str(index), f"agent-{self.AGENT_ID}.jsonl"),
                    [_assistant(self.AGENT_ID, 1, 1, 1, 1)])
            with mock.patch.object(usage, "MAX_CANDIDATES", 1):
                result = usage.observe_usage(self.AGENT_ID, root)

        self.assertEqual(result, {
            "status": "unavailable",
            "reason": "transcript-scan-limit-exceeded",
        })

    def test_deep_malformed_usage_fails_soft(self):
        usage = _load_usage()
        with tempfile.TemporaryDirectory() as root:
            path = self._path(root, self.AGENT_ID)
            os.makedirs(os.path.dirname(path), exist_ok=True)
            nested = "[" * 2000 + "0" + "]" * 2000
            with open(path, "w", encoding="utf-8") as handle:
                handle.write(
                    '{"type":"assistant","agentId":"' + self.AGENT_ID
                    + '","message":{"usage":' + nested + '}}\n')

            result = usage.observe_usage(self.AGENT_ID, root)

        self.assertEqual(result, {
            "status": "unavailable",
            "reason": "usage-invalid",
        })

    def test_transcript_size_limit_remains_distinct(self):
        usage = _load_usage()
        with tempfile.TemporaryDirectory() as root:
            _write_jsonl(
                self._path(root, self.AGENT_ID),
                [_assistant(self.AGENT_ID, 1, 1, 1, 1)])
            with mock.patch.object(usage, "MAX_TRANSCRIPT_BYTES", 8):
                result = usage.observe_usage(self.AGENT_ID, root)

        self.assertEqual(result, {
            "status": "unavailable",
            "reason": "transcript-over-limit",
        })

    def test_candidate_replaced_by_outside_symlink_is_not_followed(self):
        usage = _load_usage()
        with tempfile.TemporaryDirectory() as parent:
            root = os.path.join(parent, "projects")
            path = self._path(root, self.AGENT_ID)
            outside = os.path.join(parent, "outside.jsonl")
            _write_jsonl(path, [_assistant(self.AGENT_ID, 1, 1, 1, 1)])
            _write_jsonl(outside, [_assistant(self.AGENT_ID, 99, 99, 99, 99)])
            os.remove(path)
            try:
                os.symlink(outside, path)
            except (OSError, NotImplementedError) as error:
                self.skipTest(f"symlinks unavailable: {error}")

            result = usage.observe_usage(self.AGENT_ID, root)

        self.assertEqual(result, {
            "status": "unavailable",
            "reason": "transcript-unavailable",
        })


class ClaudeSurfaceWiringTests(unittest.TestCase):
    @staticmethod
    def _read(*parts):
        with open(os.path.join(_REPO, *parts), encoding="utf-8") as handle:
            return handle.read()

    def test_claude_tribunal_records_agent_receipt_and_explicit_states(self):
        routine = self._read("plugins", "ca", "skills", "tribunal", "SKILL.md")
        schema = self._read(
            "plugins", "ca", "skills", "tribunal", "references", "schemas.md")

        self.assertIn("tribunal-usage.py observe --agent-id", routine)
        self.assertIn("returned `agentId`", routine)
        self.assertIn("Before constructing any shell command", routine)
        self.assertIn("^[A-Za-z0-9][A-Za-z0-9_-]{0,127}$", routine)
        self.assertIn('"agent_id"', schema)
        self.assertIn('"tokens_source":"claude-subagent-transcript"', schema)
        self.assertIn("cache_creation_input_tokens", schema)
        self.assertIn("transcript-format-unsupported", schema)

    def test_codex_tribunal_keeps_its_thread_parser_only(self):
        routine = self._read(
            "plugins", "ca-codex", "routines", "tribunal", "SKILL.md")

        self.assertIn("tribunal-usage.py observe --thread-id", routine)
        self.assertNotIn("tribunal-usage.py observe --agent-id", routine)


if __name__ == "__main__":
    unittest.main()
