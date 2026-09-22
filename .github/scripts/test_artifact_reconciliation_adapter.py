#!/usr/bin/env python3
"""Regression tests for exact-prompt task/scope reconciliation authority."""

import importlib
import hashlib
import json
from pathlib import Path
import sys
import tempfile
import unittest

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent.parent / "core" / "pysrc"))


class FakeClient:
    def __init__(self, root):
        self.root = root
        self.calls = []
        self.identity = {
            "artifact_id": "PLAN-EXAMPLE", "revision": 3,
            "model_sha256": "1" * 64, "normative_sha256": "2" * 64,
        }
        self.record = {"id": "T-001", "title": "Task", "state": "IN_PROGRESS"}
        self.snapshot_sha = "3" * 64

    def call(self, operation, request=None, **_kwargs):
        self.calls.append((operation, dict(request or {})))
        if operation == "identity":
            return dict(self.identity)
        if operation == "snapshot":
            return {"sha256": self.snapshot_sha}
        if operation == "read":
            return {"record": dict(self.record)}
        if operation == "evidence-context":
            context = {
                "format": "codearbiter.evidence-context/0.1.0",
                "activity": "reconciliation",
                "subject": {"artifact_id": self.identity["artifact_id"], "normative_sha256": self.identity["normative_sha256"], "record_id": request["record_id"]},
                "input_sha256": self.snapshot_sha,
                "prompt_sha256": request["prompt_sha256"],
                "record": dict(self.record),
            }
            context["record_sha256"] = hashlib.sha256(json.dumps(context["record"], ensure_ascii=True, sort_keys=True, separators=(",", ":")).encode()).hexdigest()
            raw = json.dumps(context, ensure_ascii=True, sort_keys=True, separators=(",", ":")).encode()
            digest = hashlib.sha256(raw).hexdigest()
            relative = Path(".codearbiter/.artifacts/evidence-contexts") / f"{digest}.json"
            target = self.root / relative
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(raw)
            return {"context_ref": relative.as_posix(), "context_sha256": digest}
        if operation == "capture-observation":
            return {"receipt": ".codearbiter/.artifacts/receipts/" + "4" * 64 + ".json"}
        if operation in {"task-reconcile", "scope-reconcile"}:
            return {"revision": 4}
        raise AssertionError(operation)


class ReconciliationTest(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        (self.root / ".codearbiter").mkdir()
        self.adapter = importlib.import_module("_reconciliationlib")
        self.routes = importlib.import_module("_artifactpromptlib")
        self.old_registry = self.routes.REGISTRY_PARENT
        self.routes.REGISTRY_PARENT = self.root
        self.client = FakeClient(self.root)

    def tearDown(self):
        self.routes.REGISTRY_PARENT = self.old_registry
        self.temp.cleanup()

    def test_exact_observed_prompt_captures_and_applies_task_reconciliation(self):
        armed = self.adapter.arm_reconciliation(
            self.root, self.client, "PLAN-EXAMPLE", "T-001", "task-reconcile",
            target_state="PENDING", reason="Interrupted verifier.",
            assessment="The prior attempt has no established completion.",
            token="fixed-reconcile-token",
        )
        self.assertEqual(
            armed["reply"],
            "reconcile-task PLAN-EXAMPLE T-001 PENDING fixed-reconcile-token",
        )
        result = self.adapter.consume_reconciliation(
            self.root, self.client, armed["reply"], host="codex", session_id="session-1"
        )
        self.assertTrue(result["reconciled"])
        mutation = [request for name, request in self.client.calls if name == "task-reconcile"][0]
        self.assertEqual(mutation["state"], "PENDING")
        source = next((self.root / ".codearbiter/.artifacts/authority-sources").glob("*.json"))
        event = json.loads(source.read_text(encoding="utf-8"))
        self.assertEqual(event["source_text"], armed["reply"])
        self.assertEqual(event["authority_kind"], "user_workflow")

    def test_wrong_prompt_and_cross_repo_ambiguity_fail_closed(self):
        armed = self.adapter.arm_reconciliation(
            self.root, self.client, "PLAN-EXAMPLE", "T-001", "task-reconcile",
            target_state="BLOCKED", reason="Uncertain.", assessment="Needs user triage.",
            token="fixed-reconcile-token",
        )
        self.assertFalse(self.adapter.consume_reconciliation(
            self.root, self.client, armed["reply"] + "x", host="codex", session_id="s"
        )["reconciled"])
        other = self.root / "other"
        other.mkdir()
        self.routes.register(other, "reconciliation", "PLAN-EXAMPLE", armed["reply"])
        with self.assertRaisesRegex(RuntimeError, "multiple repositories"):
            self.routes.resolve("reconciliation", armed["reply"])

    def test_scope_reconciliation_uses_distinct_closed_mutation(self):
        self.client.record = {"id": "CP-01", "title": "Scope", "tasks": ["T-001"]}
        armed = self.adapter.arm_reconciliation(
            self.root, self.client, "PLAN-EXAMPLE", "CP-01", "scope-reconcile",
            assessment="Current scope baseline was inspected against the exact input.",
            token="fixed-scope-token",
        )
        result = self.adapter.consume_reconciliation(
            self.root, self.client, armed["reply"], host="codex", session_id="scope-session"
        )
        self.assertTrue(result["reconciled"])
        mutation = [request for name, request in self.client.calls if name == "scope-reconcile"][0]
        self.assertEqual(mutation["scope"], "CP-01")
        self.assertNotIn("state", mutation)

    def test_second_arm_preserves_the_original_pending_request(self):
        armed = self.adapter.arm_reconciliation(
            self.root, self.client, "PLAN-EXAMPLE", "T-001", "task-reconcile",
            target_state="PENDING", reason="Interrupted.", assessment="First request.",
            token="first-reconcile-token",
        )
        pending = self.root / ".codearbiter/.markers/reconciliations/PLAN-EXAMPLE.json"
        original = pending.read_bytes()
        with self.assertRaisesRegex(RuntimeError, "PENDING_RECONCILIATION"):
            self.adapter.arm_reconciliation(
                self.root, self.client, "PLAN-EXAMPLE", "T-001", "task-reconcile",
                target_state="BLOCKED", reason="Second.", assessment="Second request.",
                token="second-reconcile-token",
            )
        self.assertEqual(original, pending.read_bytes())
        self.assertEqual(
            self.root.resolve(), self.routes.resolve("reconciliation", armed["reply"])
        )

    def test_identity_input_or_record_drift_blocks_reconciliation(self):
        for label, mutate in (
            ("identity", lambda: self.client.identity.update(revision=4)),
            ("input", lambda: setattr(self.client, "snapshot_sha", "8" * 64)),
            ("record", lambda: self.client.record.update(title="Changed")),
        ):
            with self.subTest(label=label):
                self.tearDown()
                self.setUp()
                armed = self.adapter.arm_reconciliation(
                    self.root, self.client, "PLAN-EXAMPLE", "T-001", "task-reconcile",
                    target_state="PENDING", reason="Interrupted.", assessment="Reviewed.",
                    token="drift-reconcile-token",
                )
                mutate()
                with self.assertRaisesRegex(RuntimeError, "changed after arming"):
                    self.adapter.consume_reconciliation(
                        self.root, self.client, armed["reply"], host="codex", session_id="drift-session"
                    )

    def test_pending_mutation_fields_are_bound_outside_the_repository(self):
        for field, value in (
            ("target_state", "BLOCKED"),
            ("reason", "Tampered reason"),
            ("assessment", "Tampered assessment"),
        ):
            with self.subTest(field=field):
                self.tearDown()
                self.setUp()
                armed = self.adapter.arm_reconciliation(
                    self.root, self.client, "PLAN-EXAMPLE", "T-001", "task-reconcile",
                    target_state="PENDING", reason="Interrupted.", assessment="Reviewed.",
                    token="bound-reconcile-token",
                )
                pending_path = self.root / ".codearbiter/.markers/reconciliations/PLAN-EXAMPLE.json"
                pending = json.loads(pending_path.read_text(encoding="utf-8"))
                pending[field] = value
                pending_path.write_text(json.dumps(pending), encoding="utf-8")
                with self.assertRaisesRegex(RuntimeError, "changed after arming"):
                    self.adapter.consume_reconciliation(
                        self.root, self.client, armed["reply"], host="codex", session_id="bound-session"
                    )


if __name__ == "__main__":
    unittest.main()
