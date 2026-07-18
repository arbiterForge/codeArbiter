#!/usr/bin/env python3
"""Task 8 contract tests for host-neutral transcript prune planning."""

import os
import json
import subprocess
import sys
import unittest


ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
CORE = os.path.join(ROOT, "core", "pysrc")
sys.path.insert(0, CORE)

from _prunepolicy import (  # noqa: E402
    PrunePolicy,
    SemanticEntry,
    audit_outcomes,
    has_marker,
    marker_for,
    plan_prune,
    reduction_metrics,
    select_strategies,
)


def claude_codec(records):
    entries = []
    for index, record in enumerate(records):
        content = record.get("message", {}).get("content", [])
        entries.append(SemanticEntry(
            id=record["uuid"],
            ordinal=index,
            role=record["type"],
            kind=("tool-result" if any(block.get("type") == "tool_result" for block in content)
                  else "message"),
            byte_size=len(str(record).encode("utf-8")),
            tool_bearing=any(block.get("type") == "tool_use" for block in content),
            marked=has_marker(str(record)),
        ))
    return entries


def pi_codec(records):
    entries = []
    for index, record in enumerate(records):
        message = record.get("message", {})
        content = message.get("content", [])
        role = message.get("role", record.get("type", "other"))
        entries.append(SemanticEntry(
            id=record["id"],
            ordinal=index,
            role=("assistant" if role == "assistant" else
                  "user" if role == "user" else
                  "tool" if role == "toolResult" else role),
            kind=("tool-result" if role == "toolResult" else "message"),
            byte_size=len(str(record).encode("utf-8")),
            tool_bearing=any(block.get("type") in ("toolCall", "tool_use") for block in content),
            marked=has_marker(str(record)),
        ))
    return entries


class PrunePolicyParityTests(unittest.TestCase):
    def test_codecs_choose_identical_policy_outcomes(self):
        claude = []
        pi = []
        for turn in range(5):
            claude.extend([
                {"uuid": f"u{turn}", "type": "user", "message": {"content": [{"type": "text", "text": f"turn {turn}"}]}},
                {"uuid": f"a{turn}", "type": "assistant", "message": {"content": [{"type": "tool_use", "id": f"t{turn}", "name": "Read"}]}},
                {"uuid": f"r{turn}", "type": "user", "message": {"content": [{"type": "tool_result", "tool_use_id": f"t{turn}", "content": "x" * 200}]}},
            ])
            pi.extend([
                {"id": f"u{turn}", "type": "message", "message": {"role": "user", "content": [{"type": "text", "text": f"turn {turn}"}]}},
                {"id": f"a{turn}", "type": "message", "message": {"role": "assistant", "content": [{"type": "toolCall", "id": f"t{turn}", "name": "read"}]}},
                {"id": f"r{turn}", "type": "message", "message": {"role": "toolResult", "content": [{"type": "text", "text": "x" * 200}]}},
            ])

        policy = PrunePolicy(tier="standard", keep_recent=2, max_bytes=64)
        left = plan_prune(claude_codec(claude), policy)
        right = plan_prune(pi_codec(pi), policy)
        self.assertEqual(left.protected_ids, right.protected_ids)
        self.assertEqual(left.first_kept_id, "a3")
        self.assertTrue(left.actions, "parity fixture produced an empty prune plan")
        self.assertEqual(left.actions, right.actions)
        self.assertEqual(left.metrics, right.metrics)
        self.assertEqual(left.audit_codes, right.audit_codes)

    def test_markers_tiers_metrics_and_plans_are_idempotent(self):
        marker = marker_for("secret-free payload")
        self.assertTrue(has_marker(marker))
        self.assertEqual(marker_for(marker), marker)
        self.assertEqual(
            select_strategies("standard"),
            ("sidecar-collapse", "reasoning-fold", "mcp-payload-condense",
             "shell-tail-keep", "aged-result-condense", "oversize-result-clamp"),
        )
        entries = [
            SemanticEntry("u0", 0, "user", "message", 40),
            SemanticEntry("a0", 1, "assistant", "message", 60, tool_bearing=True),
            SemanticEntry("r0", 2, "tool", "tool-result", 500),
            SemanticEntry("u1", 3, "user", "message", 40),
            SemanticEntry("a1", 4, "assistant", "message", 60, tool_bearing=True),
        ]
        policy = PrunePolicy(tier="gentle", keep_recent=1, max_bytes=64)
        once = plan_prune(entries, policy)
        twice = plan_prune(entries, policy)
        self.assertEqual(once, twice)
        self.assertEqual(once.metrics["entries_before"], 5)
        self.assertEqual(once.metrics["candidate_entries"], 4)
        self.assertEqual(once.audit_codes, ("CA-PRUNE-PLAN",))
        self.assertEqual(reduction_metrics(1000, 600), {
            "bytes_before": 1000, "bytes_after": 600, "freed_bytes": 400,
            "est_tokens_before": 250, "est_tokens_after": 150, "pct": 40.0,
        })
        self.assertEqual(reduction_metrics(100, 120)["freed_bytes"], -20)
        self.assertEqual(audit_outcomes(parse_errors=1, orphans=0, unpaired=2),
                         ("FAIL", "OK", "WARN", "OK"))

    def test_pi_bridge_returns_only_a_bounded_semantic_plan(self):
        request = {
            "version": 1,
            "event": "prune_plan",
            "cwd": ROOT,
            "input": {
                "entries": [
                    {"id": "u0", "ordinal": 0, "role": "user", "kind": "message", "byteSize": 20, "toolBearing": False, "marked": False},
                    {"id": "a0", "ordinal": 1, "role": "assistant", "kind": "message", "byteSize": 20, "toolBearing": True, "marked": False},
                    {"id": "r0", "ordinal": 2, "role": "tool", "kind": "tool-result", "byteSize": 500, "toolBearing": False, "marked": False},
                    {"id": "u1", "ordinal": 3, "role": "user", "kind": "message", "byteSize": 20, "toolBearing": False, "marked": False},
                    {"id": "a1", "ordinal": 4, "role": "assistant", "kind": "message", "byteSize": 20, "toolBearing": True, "marked": False},
                ],
                "policy": {"tier": "standard", "keepRecent": 1, "maxBytes": 64},
            },
        }
        result = subprocess.run(
            [sys.executable, os.path.join(ROOT, "plugins", "ca-pi", "hooks", "pi-bridge.py")],
            input=json.dumps(request), text=True, encoding="utf-8", capture_output=True, timeout=10,
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        response = json.loads(result.stdout)
        self.assertEqual(response["outcome"], "notice")
        plan = response["resultPatch"]["prunePlan"]
        self.assertEqual(plan["firstKeptEntryId"], "a1")
        self.assertEqual(plan["metrics"]["candidateEntries"], 4)
        self.assertRegex(plan["fingerprint"], r"^[0-9a-f]{64}$")

        request["input"]["entries"][1]["id"] = "u0"
        duplicate = subprocess.run(
            [sys.executable, os.path.join(ROOT, "plugins", "ca-pi", "hooks", "pi-bridge.py")],
            input=json.dumps(request), text=True, encoding="utf-8", capture_output=True, timeout=10,
        )
        self.assertEqual(duplicate.returncode, 1)
        self.assertEqual(duplicate.stderr, "PI bridge error (ProtocolError)\n")


if __name__ == "__main__":
    unittest.main()
