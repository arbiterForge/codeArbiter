#!/usr/bin/env python3
"""Behavioral entry, resume, review and atomic-acceptance fixtures."""

from __future__ import annotations

from pathlib import Path
import tempfile
import unittest

from test_artifact_authoring import (
    ArtifactError,
    WorkflowHarness,
    build_installation,
)


class ArtifactWorkflowTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.installation_owner, cls.installation = build_installation()

    @classmethod
    def tearDownClass(cls) -> None:
        if cls.installation_owner is not None:
            cls.installation_owner.cleanup()

    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory(prefix="ca-artifact-workflow-")
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name) / "repo"
        self.root.mkdir()
        self.harness = WorkflowHarness(self.root, self.installation)
        self.harness.create_pair()

    def test_draft_or_missing_approval_cannot_dispatch(self) -> None:
        with self.assertRaises(ArtifactError) as caught:
            self.harness.client.call("eligible", {"artifact_id": "PLAN-FLOW"})
        self.assertEqual(caught.exception.code, "DRAFT_BINDING")

    def test_approved_pair_dispatches_with_complete_context_and_resumes_in_progress(self) -> None:
        self.harness.approve_pair()
        eligible = self.harness.client.call("eligible", {"artifact_id": "PLAN-FLOW"})
        self.assertEqual(eligible["next_task"], "T-001")
        ticket = self.harness.context_ticket("T-001")
        self.harness.mutate("task-start", "PLAN-FLOW", task="T-001", context_ticket=ticket)
        resumed = self.harness.client.call("eligible", {"artifact_id": "PLAN-FLOW"})
        self.assertEqual(resumed["tasks"][0]["state"], "IN_PROGRESS")
        self.assertFalse(resumed["tasks"][0]["eligible"])

    def test_stale_context_blocks_before_dispatch_side_effect(self) -> None:
        self.harness.approve_pair()
        ticket = self.harness.context_ticket("T-001")
        self.harness.mutate(
            "apply",
            "SPEC-FLOW",
            changes=[
                {
                    "op": "header.update",
                    "fields": {"summary": "Changed after bounded context delivery."},
                }
            ],
        )
        before = self.harness.client.call("identity", {"artifact_id": "PLAN-FLOW"})
        with self.assertRaises(ArtifactError) as caught:
            self.harness.mutate(
                "task-start", "PLAN-FLOW", task="T-001", context_ticket=ticket
            )
        self.assertEqual(caught.exception.code, "STALE_SPEC")
        after = self.harness.client.call("identity", {"artifact_id": "PLAN-FLOW"})
        self.assertEqual(after, before)

    def test_changed_worktree_rejects_review_evidence(self) -> None:
        self.harness.approve_pair()
        ticket = self.harness.context_ticket("T-001")
        self.harness.mutate("task-start", "PLAN-FLOW", task="T-001", context_ticket=ticket)
        verification, review = self.harness.task_receipts("T-001")
        (self.root / "src").mkdir()
        (self.root / "src/config.py").write_text("changed = True\n", encoding="utf-8")
        with self.assertRaises(ArtifactError) as caught:
            self.harness.mutate(
                "task-review",
                "PLAN-FLOW",
                task="T-001",
                verification_receipt=verification,
                review_receipt=review,
            )
        self.assertEqual(caught.exception.code, "STALE_EVIDENCE")
        eligible = self.harness.client.call("eligible", {"artifact_id": "PLAN-FLOW"})
        self.assertEqual(eligible["tasks"][0]["state"], "IN_PROGRESS")

    def test_review_checkpoint_survives_resume_and_scope_acceptance_is_atomic(self) -> None:
        self.harness.approve_pair()
        ticket = self.harness.context_ticket("T-001")
        self.harness.mutate("task-start", "PLAN-FLOW", task="T-001", context_ticket=ticket)
        self.harness.review_task("T-001")

        resumed = WorkflowHarness(self.root, self.installation)
        checkpoint = resumed.client.call("eligible", {"artifact_id": "PLAN-FLOW"})
        self.assertEqual(checkpoint["tasks"][0]["state"], "REVIEW")
        self.assertFalse(checkpoint["all_accepted_and_current"])

        resumed.accept_scope("CP-01", ["T-001"])
        accepted = resumed.client.call("eligible", {"artifact_id": "PLAN-FLOW"})
        self.assertEqual(accepted["tasks"][0]["state"], "ACCEPTED")
        self.assertTrue(accepted["all_accepted_and_current"])


if __name__ == "__main__":
    unittest.main(verbosity=2)
