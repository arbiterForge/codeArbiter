"""Lint + shape proof for the sanitized statusline-accounting fixtures (spec AC-51).

The fixtures are copied from real Claude Code transcripts into a PUBLIC repo, so
this suite is the gate that keeps them structural: no conversation content, no
real identifiers, no machine/user/environment fields. It also proves each
observed shape the accounting spec relies on is actually present, so a fixture
refresh cannot silently drop the evidence a principal accounting test depends on.
"""
import json
import os
import re
import unittest

FIXTURES = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                        "fixtures", "statusline_accounting")

# Every key that may appear anywhere in a fixture record. Anything else is a
# potential leak of host/environment data and fails the lint.
_ALLOWED_KEYS = {
    # record envelope
    "type", "timestamp", "isSidechain", "requestId", "uuid", "parentUuid",
    "agentId", "sessionId", "message", "parentSessionId", "parentLastUuid",
    "contextLength", "totalCostUSD", "modelUsage", "hasUnknownModelCost",
    "attachment", "commandMode",
    # message
    "id", "role", "model", "usage", "content", "name",
    # usage
    "input_tokens", "output_tokens", "cache_creation_input_tokens",
    "cache_read_input_tokens", "cache_creation", "ephemeral_5m_input_tokens",
    "ephemeral_1h_input_tokens", "server_tool_use", "web_search_requests",
    "web_fetch_requests", "service_tier", "inference_geo", "speed", "iterations",
    "output_tokens_details", "thinking_tokens", "reasoning_tokens",
    # cost-state modelUsage entries
    "inputTokens", "outputTokens", "cacheReadInputTokens",
    "cacheCreationInputTokens", "webSearchRequests", "costUSD", "thinkingTokens",
    # attachment usage summary
    "totalTokens", "toolUses", "durationMs",
}
# modelUsage is keyed by model id; those keys are values, not field names.
_MODEL_ID = re.compile(r"^(claude-[a-z0-9.\-]+(\[1m\])?|<synthetic>)$")
_ID_PATTERNS = {
    "requestId": re.compile(r"^req_fx_\d{3}$"),
    "uuid": re.compile(r"^uuid-fx-\d{3}$"),
    "parentUuid": re.compile(r"^uuid-fx-\d{3}$"),
    "parentLastUuid": re.compile(r"^uuid-fx-\d{3}$"),
    "sessionId": re.compile(r"^sess-fx-\d{3}$"),
    "parentSessionId": re.compile(r"^sess-fx-\d{3}$"),
    "agentId": re.compile(r"^fxagent\d{3}$"),
}
_MESSAGE_ID = re.compile(r"^msg_fx_\d{3}$")
_FORBIDDEN_TEXT = [
    re.compile(r"[A-Za-z]:[\\/]"),                 # Windows absolute path
    re.compile(r"(?<![A-Za-z])/(Users|home|root|tmp|var)/"),  # POSIX home-ish paths
    re.compile(r"[\w.+-]+@[\w-]+\.[\w.]+"),        # e-mail
    re.compile(r"\\\\[A-Za-z0-9_-]+\\"),           # UNC host
]
_ALLOWED_USER_CONTENT = re.compile(r"^Fixture [A-Za-z0-9 ]+$")


def _files():
    out = []
    for base, _dirs, names in os.walk(FIXTURES):
        for name in names:
            if name.endswith(".jsonl"):
                out.append(os.path.join(base, name))
    return sorted(out)


def _records(path):
    with open(path, encoding="utf-8") as f:
        return [json.loads(line) for line in f if line.strip()]


def _load(rel):
    return _records(os.path.join(FIXTURES, *rel.split("/")))


def lint_record(rec):
    """Return a list of human-readable violations for one fixture record."""
    problems = []

    def walk(value, path, parent_key=None):
        if isinstance(value, dict):
            for key, sub in value.items():
                if parent_key == "modelUsage":
                    if not _MODEL_ID.match(key):
                        problems.append(f"{path}: model key {key!r} is not a model id")
                elif key not in _ALLOWED_KEYS:
                    problems.append(f"{path}: key {key!r} is not whitelisted")
                walk(sub, f"{path}.{key}", key)
        elif isinstance(value, list):
            for i, sub in enumerate(value):
                walk(sub, f"{path}[{i}]", parent_key)
        elif isinstance(value, str):
            for rx in _FORBIDDEN_TEXT:
                if rx.search(value):
                    problems.append(f"{path}: forbidden text {value!r}")
            if parent_key in _ID_PATTERNS and not _ID_PATTERNS[parent_key].match(value):
                problems.append(f"{path}: {parent_key} {value!r} is not a fixture token")

    walk(rec, "$")
    msg = rec.get("message")
    if isinstance(msg, dict):
        if "id" in msg and not _MESSAGE_ID.match(str(msg["id"])):
            problems.append(f"message.id {msg['id']!r} is not a fixture token")
        content = msg.get("content")
        if msg.get("role") == "user":
            if not (isinstance(content, str) and _ALLOWED_USER_CONTENT.match(content)):
                problems.append("user content is not a fixture label")
        elif content is not None:
            if not isinstance(content, list):
                problems.append("assistant content is not a block skeleton list")
            else:
                for blk in content:
                    if not isinstance(blk, dict) or set(blk) - {"type", "name"}:
                        problems.append(f"content block carries more than type/name: {blk!r}")
    return problems


class TestFixtureLint(unittest.TestCase):

    def test_fixture_set_is_present(self):
        self.assertGreaterEqual(len(_files()), 9)

    def test_every_record_is_structural_only(self):
        for path in _files():
            for n, rec in enumerate(_records(path), 1):
                with self.subTest(file=os.path.relpath(path, FIXTURES), line=n):
                    self.assertEqual(lint_record(rec), [])

    def test_lint_rejects_leaks(self):
        # The lint must actually bite: each seeded leak is reported.
        leaks = [
            {"type": "user", "cwd": "x"},
            {"type": "user", "gitBranch": "main"},
            {"type": "assistant", "requestId": "req_011Cf5real"},
            {"type": "assistant", "message": {"id": "msg_real", "role": "assistant"}},
            {"type": "user", "message": {"role": "user", "content": "please fix my bug"}},
            {"type": "assistant", "message": {"role": "assistant",
                                              "content": [{"type": "text", "text": "hi"}]}},
            {"type": "system", "content": "C:\\Users\\someone\\repo"},
            {"type": "system", "attachment": {"type": "x", "commandMode": "me@example.com"}},
            {"type": "system", "attachment": {"type": "/home/someone/x"}},
            {"type": "cost-state", "modelUsage": {"not a model": {}}},
        ]
        for leak in leaks:
            with self.subTest(leak=leak):
                self.assertNotEqual(lint_record(leak), [])


class TestObservedShapes(unittest.TestCase):
    """Each spec observation the accounting tests rely on is really present."""

    def test_fork_replay_shape(self):
        parent = _load("fork_replay/parent.jsonl")
        parent_rids = {r.get("requestId") for r in parent if r.get("type") == "assistant"}
        for n in (1, 2):
            child = _load(f"fork_replay/parent/subagents/agent-fxchild{n}.jsonl")
            with self.subTest(child=n):
                self.assertEqual(child[0]["type"], "fork-context-ref")
                replay = child[1]
                self.assertEqual(replay["type"], "assistant")
                self.assertTrue(replay["isSidechain"])
                self.assertIn(replay["requestId"], parent_rids)
                own = [r for r in child[2:] if r.get("type") == "assistant"]
                self.assertTrue(own, "child has its own requests after the replay")
                self.assertTrue(all(r["requestId"] not in parent_rids for r in own))

    def test_fork_replay_copy_is_an_earlier_partial_snapshot(self):
        parent = _load("fork_replay/parent.jsonl")
        child = _load("fork_replay/parent/subagents/agent-fxchild1.jsonl")
        rid = child[1]["requestId"]
        parent_outs = [r["message"]["usage"]["output_tokens"] for r in parent
                       if r.get("requestId") == rid]
        self.assertLess(child[1]["message"]["usage"]["output_tokens"], max(parent_outs))

    def test_advisor_iteration_shape(self):
        reps = _load("advisor_iterations.jsonl")
        final = max(reps, key=lambda r: len(r["message"]["usage"].get("iterations") or []))
        usage = final["message"]["usage"]
        its = usage["iterations"]
        self.assertEqual([i["type"] for i in its],
                         ["message", "advisor_message", "message"])
        self.assertTrue(its[1].get("model"))
        for key in ("input_tokens", "output_tokens", "cache_read_input_tokens",
                    "cache_creation_input_tokens"):
            with self.subTest(counter=key):
                self.assertEqual(usage[key],
                                 sum(i[key] for i in its if i["type"] == "message"))
        top_split = sum(usage["cache_creation"].values())
        iter_split = sum(sum(i["cache_creation"].values())
                         for i in its if i["type"] == "message")
        self.assertNotEqual(top_split, usage["cache_creation_input_tokens"])
        self.assertEqual(iter_split, usage["cache_creation_input_tokens"])
        self.assertEqual(len({r["requestId"] for r in reps}), 1)

    def test_streaming_snapshots_grow(self):
        reps = _load("streaming_snapshots.jsonl")
        self.assertEqual(len({r["requestId"] for r in reps}), 1)
        outs = [r["message"]["usage"]["output_tokens"] for r in reps]
        self.assertGreater(len(set(outs)), 1)

    def test_synthetic_records_are_zero_usage(self):
        reps = _load("synthetic.jsonl")
        self.assertTrue(any("requestId" not in r or r["requestId"] is None for r in reps))
        for r in reps:
            self.assertEqual(r["message"]["model"], "<synthetic>")
            u = r["message"]["usage"]
            self.assertEqual(sum(v for k, v in u.items()
                                 if k.endswith("_tokens") and isinstance(v, int)), 0)

    def test_modifier_fields(self):
        reps = _load("modifiers.jsonl")
        self.assertEqual({("speed" in r["message"]["usage"]) for r in reps}, {True, False})
        for r in reps:
            self.assertEqual(r["message"]["usage"].get("inference_geo"), "not_available")

    def test_nonusage_types_include_attachment_usage_summary(self):
        recs = _load("nonusage_types.jsonl")
        types = {r["type"] for r in recs}
        for t in ("mode", "user", "attachment", "fork-context-ref", "system"):
            self.assertIn(t, types)
        summaries = [r for r in recs if r["type"] == "attachment"
                     and isinstance(r.get("attachment"), dict)
                     and "usage" in r["attachment"]]
        self.assertTrue(summaries)
        self.assertIn("totalTokens", summaries[0]["attachment"]["usage"])

    def test_cost_state_has_host_only_side_query_model(self):
        rec = _load("cost_state.jsonl")[0]
        self.assertEqual(rec["type"], "cost-state")
        self.assertGreaterEqual(len(rec["modelUsage"]), 3)


if __name__ == "__main__":
    unittest.main()
