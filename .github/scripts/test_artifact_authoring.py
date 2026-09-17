#!/usr/bin/env python3
"""Behavioral producer fixtures for the typed spec/plan authoring path.

The receipts in this file are synthetic workflow events. They exercise the
existing authority boundary but do not approve this package or any real plan.
"""

from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest


REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO / "core" / "pysrc"))

from _artifactlib import ArtifactClient, ArtifactError  # noqa: E402


def canonical_hash(value: object) -> str:
    raw = json.dumps(
        value,
        ensure_ascii=False,
        allow_nan=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    return hashlib.sha256(raw).hexdigest()


def spec_normative() -> dict:
    return {
        "title": "Configuration precedence",
        "summary": "Select present validated values without treating false as absent.",
        "baseline": {"repository": None, "commit": None, "observed_date": "2026-09-16"},
        "sections": [],
        "sources": [],
        "retired_symbols": [],
        "intent": {
            "id": "INTENT-01",
            "problem": "Configuration precedence is ambiguous.",
            "caller": "Application initialization",
            "outcome": "Deterministic effective configuration",
            "source_refs": [],
        },
        "approach": {
            "id": "APPROACH-01",
            "choice": "Resolve validated values in explicit order.",
            "tradeoff": "Validation remains a separate boundary.",
            "binding_decision_refs": [],
        },
        "constraints": [],
        "scope": [{"id": "SCOPE-01", "statement": "Resolve present values."}],
        "non_goals": [{"id": "NON-GOAL-01", "statement": "Parse raw configuration."}],
        "decisions": [],
        "governs": ["src/*.py"],
        "open_decisions": [],
        "criteria": [
            {
                "id": "AC-001",
                "title": "Select the environment value",
                "kind": "behavior",
                "obligation": "must",
                "intent_refs": ["SCOPE-01"],
                "statement": "When both sources are valid, select the environment value.",
                "preconditions": ["Both values are validated."],
                "trigger": "Resolve a supported key.",
                "guarantees": ["The effective value equals the environment value."],
                "scenarios": [
                    {
                        "id": "SCN-AC-001",
                        "given": "Environment=false and file=true.",
                        "when": "Resolve the key.",
                        "then": "The effective value is false.",
                    }
                ],
                "verification": {
                    "id": "VER-AC-001",
                    "method": "automated",
                    "planned_target": "test_environment_overrides",
                    "oracle": "Assert the effective value is false.",
                    "negative_control": "A file-first resolver returns true.",
                    "evidence_state": "planned",
                },
                "source_refs": [],
                "constraint_refs": [],
                "applicability": {
                    "mode": "conditional",
                    "rationale": "Both sources are present.",
                },
            }
        ],
    }


def plan_normative(spec_id: str, spec_hash: str) -> dict:
    verification = {
        "availability": "proposed",
        "cwd": ".",
        "argv": ["python", "-m", "unittest", "tests.test_config"],
        "expected_exit": 0,
        "assertion": "The named test runs and passes.",
        "required_tests": ["test_environment_overrides"],
    }
    task = {
        "id": "T-001",
        "title": "Implement configuration precedence",
        "checkpoint": "CP-01",
        "execution_scope": "CP-01",
        "depends_on": [],
        "paths": [{"path": "src/config.py", "action": "modify"}],
        "criterion_refs": [f"{spec_id}#AC-001"],
        "steps": ["Write the negative test.", "Implement the contract."],
        "verification": [verification],
        "done_when": ["The named test passes."],
        "rollback": "Revert the implementation change.",
        "source_refs": [],
    }
    return {
        "title": "Configuration precedence implementation",
        "summary": "Implement and verify the approved precedence contract.",
        "baseline": {"repository": None, "commit": None, "observed_date": "2026-09-16"},
        "sections": [],
        "sources": [],
        "retired_symbols": [],
        "spec_ref": {
            "artifact_id": spec_id,
            "normative_sha256": spec_hash,
            "binding_mode": "draft_preview",
        },
        "tasks": [task],
        "checkpoints": [
            {
                "id": "CP-01",
                "title": "Complete implementation",
                "tasks": ["T-001"],
                "exit": "The combined scope is verified and reviewed.",
                "depends_on": [],
            }
        ],
        "prerequisites": [],
        "criterion_dispositions": [],
    }


def build_installation(
    owner: unittest.TestCase | None = None,
) -> tuple[tempfile.TemporaryDirectory | None, Path]:
    supplied = os.environ.get("ARTIFACT_TEST_INSTALLATION")
    if supplied:
        installation = Path(supplied).resolve()
        if not installation.is_dir():
            raise AssertionError(f"ARTIFACT_TEST_INSTALLATION is not a directory: {installation}")
        return None, installation
    temporary = tempfile.TemporaryDirectory(prefix="ca-artifact-authoring-install-")
    if owner is not None:
        owner.addCleanup(temporary.cleanup)
    installation = Path(temporary.name) / "payload"
    subprocess.run(
        [sys.executable, str(REPO / "tools" / "build-artifacts.py"), "--output", str(installation)],
        cwd=REPO,
        text=True,
        capture_output=True,
        check=True,
    )
    return temporary, installation


class WorkflowHarness:
    def __init__(self, root: Path, installation: Path):
        self.root = root
        self.client = ArtifactClient(root, installation)
        self.sequence = 0

    def operation_id(self, purpose: str) -> str:
        self.sequence += 1
        return f"fixture-{purpose}-{self.sequence:04d}"

    def mutate(self, operation: str, artifact_id: str, **request: object) -> dict:
        identity = self.client.call("identity", {"artifact_id": artifact_id})
        return self.client.call(
            operation,
            {
                "artifact_id": artifact_id,
                "operation_id": self.operation_id(operation),
                "expected": {
                    "revision": identity["revision"],
                    "model_sha256": identity["model_sha256"],
                },
                **request,
            },
        )

    def create_pair(self) -> tuple[dict, dict]:
        spec = spec_normative()
        self.client.call(
            "create",
            {
                "operation_id": self.operation_id("create-spec"),
                "artifact_id": "SPEC-FLOW",
                "kind": "spec",
                "slug": "flow",
                "title": spec["title"],
                "summary": spec["summary"],
                "normative": spec,
            },
        )
        spec_identity = self.client.call("identity", {"artifact_id": "SPEC-FLOW"})
        plan = plan_normative("SPEC-FLOW", spec_identity["normative_sha256"])
        self.client.call(
            "create",
            {
                "operation_id": self.operation_id("create-plan"),
                "artifact_id": "PLAN-FLOW",
                "kind": "plan",
                "slug": "flow",
                "title": plan["title"],
                "summary": plan["summary"],
                "spec_id": "SPEC-FLOW",
                "normative": plan,
            },
        )
        return spec_identity, self.client.call("identity", {"artifact_id": "PLAN-FLOW"})

    def capture(
        self,
        artifact_id: str,
        record_id: str,
        kind: str,
        authority_kind: str,
        verdict: str,
        payload: dict,
    ) -> str:
        identity = self.client.call("identity", {"artifact_id": artifact_id})
        result = self.client.call(
            "capture",
            {
                "event": {
                    "format": "codearbiter.workflow-event/0.1.0",
                    "kind": kind,
                    "authority_kind": authority_kind,
                    "subject": {
                        "artifact_id": artifact_id,
                        "normative_sha256": identity["normative_sha256"],
                        "record_id": record_id,
                    },
                    "actor": "synthetic behavioral fixture",
                    "origin": f"isolated test {self.operation_id('event')}",
                    "verdict": verdict,
                    "payload": payload,
                    "source_text": "Synthetic event for boundary testing; not production authority.",
                }
            },
        )
        return result["receipt"]

    def approve_pair(self) -> None:
        spec_receipt = self.capture(
            "SPEC-FLOW", "SPEC-FLOW", "approval", "user_workflow", "approved", {}
        )
        self.mutate("approve", "SPEC-FLOW", receipt=spec_receipt)
        self.mutate("plan-bind", "PLAN-FLOW", spec_id="SPEC-FLOW")
        plan_receipt = self.capture(
            "PLAN-FLOW", "PLAN-FLOW", "approval", "user_workflow", "approved", {}
        )
        self.mutate("approve", "PLAN-FLOW", receipt=plan_receipt)

    def context_ticket(self, task: str) -> str:
        pages = list(self.client.contextual_pages("PLAN-FLOW", task, 65536))
        return pages[-1]["context_ticket"]

    def task_receipts(self, task_id: str) -> tuple[str, str]:
        task = self.client.call(
            "read", {"artifact_id": "PLAN-FLOW", "symbol": task_id, "mode": "exact"}
        )["record"]
        spec = self.client.call("identity", {"artifact_id": "SPEC-FLOW"})
        snapshot = self.client.call("snapshot", {"artifact_id": "PLAN-FLOW"})
        payload = {
            "input_sha256": snapshot["sha256"],
            "spec_sha256": spec["normative_sha256"],
            "task_sha256": canonical_hash(task),
        }
        commands = []
        for definition in task["verification"]:
            commands.append(
                {
                    "definition_sha256": canonical_hash(definition),
                    "exit": 0,
                    "tests": [
                        {"name": name, "status": "pass"}
                        for name in definition["required_tests"]
                    ],
                    "stdout_sha256": hashlib.sha256(b"fixture PASS").hexdigest(),
                    "stderr_sha256": hashlib.sha256(b"").hexdigest(),
                }
            )
        verification = self.capture(
            "PLAN-FLOW",
            task_id,
            "verification",
            "verification_runner",
            "passed",
            {**payload, "commands": commands},
        )
        review = self.capture(
            "PLAN-FLOW",
            task_id,
            "spec_review",
            "review_workflow",
            "passed",
            {**payload, "assessment": "Synthetic specification review fixture."},
        )
        return verification, review

    def review_task(self, task_id: str) -> None:
        verification, review = self.task_receipts(task_id)
        self.mutate(
            "task-review",
            "PLAN-FLOW",
            task=task_id,
            verification_receipt=verification,
            review_receipt=review,
        )

    def accept_scope(self, scope_id: str, task_ids: list[str]) -> None:
        plan = self.client.call("identity", {"artifact_id": "PLAN-FLOW"})
        spec = self.client.call("identity", {"artifact_id": "SPEC-FLOW"})
        snapshot = self.client.call("snapshot", {"artifact_id": "PLAN-FLOW"})
        task_hashes = {}
        for task_id in task_ids:
            task = self.client.call(
                "read", {"artifact_id": "PLAN-FLOW", "symbol": task_id, "mode": "exact"}
            )["record"]
            task_hashes[task_id] = canonical_hash(task)
        receipt = self.capture(
            "PLAN-FLOW",
            scope_id,
            "quality_review",
            "review_workflow",
            "passed",
            {
                "input_sha256": snapshot["sha256"],
                "spec_sha256": spec["normative_sha256"],
                "base_input_sha256": snapshot["sha256"],
                "task_hashes": task_hashes,
                "assessment": "Synthetic combined-scope review fixture.",
            },
        )
        self.mutate("accept-scope", plan["artifact_id"], scope=scope_id, receipt=receipt)


class ArtifactAuthoringTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.installation_owner, cls.installation = build_installation()

    @classmethod
    def tearDownClass(cls) -> None:
        if cls.installation_owner is not None:
            cls.installation_owner.cleanup()

    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory(prefix="ca-artifact-authoring-")
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name) / "repo"
        self.root.mkdir()
        self.harness = WorkflowHarness(self.root, self.installation)

    def test_producers_create_and_read_canonical_html_pair(self) -> None:
        self.harness.create_pair()
        for artifact_id in ("SPEC-FLOW", "PLAN-FLOW"):
            result = self.harness.client.call(
                "validate", {"artifact_id": artifact_id, "gate": "ready"}, permit_invalid=True
            )
            self.assertTrue(result["valid"], result)
        criterion = self.harness.client.call(
            "read", {"artifact_id": "SPEC-FLOW", "symbol": "AC-001", "mode": "exact"}
        )
        task = self.harness.client.call(
            "read", {"artifact_id": "PLAN-FLOW", "symbol": "T-001", "mode": "exact"}
        )
        self.assertEqual(task["record"]["criterion_refs"], ["SPEC-FLOW#AC-001"])
        self.assertEqual(criterion["record"]["verification"]["planned_target"], "test_environment_overrides")
        self.assertTrue((self.root / ".codearbiter/specs/flow.html").is_file())
        self.assertTrue((self.root / ".codearbiter/plans/flow.html").is_file())
        self.assertEqual(list((self.root / ".codearbiter").rglob("*.md")), [])

    def test_incomplete_draft_is_named_without_inventing_contract_fields(self) -> None:
        self.harness.client.call(
            "create",
            {
                "operation_id": "fixture-incomplete-spec",
                "artifact_id": "SPEC-INCOMPLETE",
                "kind": "spec",
                "slug": "incomplete",
                "title": "Incomplete draft",
                "summary": "Missing intent and criteria on purpose.",
            },
        )
        result = self.harness.client.call(
            "validate",
            {"artifact_id": "SPEC-INCOMPLETE", "gate": "ready"},
            permit_invalid=True,
        )
        self.assertFalse(result["valid"])
        self.assertIn("INTENT", json.dumps(result).upper())
        self.assertNotIn("placeholder", (self.root / ".codearbiter/specs/incomplete.html").read_text())

    def test_missing_payload_fails_closed_without_markdown_fallback(self) -> None:
        missing = self.root / "missing-installation"
        missing.mkdir()
        client = ArtifactClient(self.root, missing)
        with self.assertRaises(ArtifactError) as caught:
            client.call("capabilities")
        self.assertEqual(caught.exception.code, "CAPABILITY_MISSING")
        self.assertEqual(list((self.root / ".codearbiter").rglob("*.md")), [])


if __name__ == "__main__":
    unittest.main(verbosity=2)
