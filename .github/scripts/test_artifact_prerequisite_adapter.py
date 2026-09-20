#!/usr/bin/env python3
"""Regression tests for host-owned structured-artifact prerequisite capture."""

import importlib.util
import json
import sys
import tempfile
import threading
import unittest
from pathlib import Path

from test_artifact_authoring import (
    WorkflowHarness,
    build_installation,
    physical_test_directory,
    plan_normative,
)

HERE = Path(__file__).resolve().parent
REPO = HERE.parent.parent
CORE_PYSRC = REPO / "core" / "pysrc"
ADAPTER_PATH = CORE_PYSRC / "_prerequisitelib.py"
sys.path.insert(0, str(CORE_PYSRC))
from _artifactlib import ArtifactError  # noqa: E402


class _FakeClient:
    def __init__(self, artifact_id="PLAN-EXAMPLE"):
        self.identity = {
            "artifact_id": artifact_id,
            "kind": "plan",
            "revision": 7,
            "model_sha256": "1" * 64,
            "normative_sha256": "2" * 64,
        }
        self.record = {
            "id": "GATE-APPROVAL",
            "title": "Owner execution approval",
            "requirement": "The owner explicitly authorizes execution of this approved plan.",
            "source_refs": [],
        }
        self.calls = []
        self.failure = None
        self.approved = True
        self.lose_prerequisite_response_once = False
        self._lost_response = False
        self.capture_result = {
            "receipt": ".codearbiter/.artifacts/receipts/" + "3" * 64 + ".json",
            "receipt_sha256": "3" * 64,
        }

    def call(self, operation, request=None, **_kwargs):
        request = dict(request or {})
        self.calls.append((operation, request))
        if operation == self.failure:
            raise RuntimeError(f"{operation} failed")
        if operation == "identity":
            return dict(self.identity)
        if operation == "validate":
            return {
                **self.identity,
                "valid": self.approved,
                "gate": "approved",
                "authority": {
                    "state": "approved" if self.approved else "unapproved",
                    "authority_verified": self.approved,
                },
            }
        if operation == "read":
            return {
                **self.identity,
                "mode": "exact",
                "context_complete": False,
                "record": dict(self.record),
            }
        if operation == "capture":
            return dict(self.capture_result)
        if operation == "prerequisite":
            if self.lose_prerequisite_response_once and not self._lost_response:
                self._lost_response = True
                raise RuntimeError("response lost after commit")
            return {
                "artifact_id": self.identity["artifact_id"],
                "revision": 8,
                "transaction": {"replayed": self._lost_response},
            }
        raise AssertionError(operation)


class PrerequisiteAdapterTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        if not ADAPTER_PATH.is_file():
            cls.adapter = None
            return
        spec = importlib.util.spec_from_file_location("_prerequisitelib", ADAPTER_PATH)
        cls.adapter = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(cls.adapter)

    def setUp(self):
        self.assertIsNotNone(
            self.adapter,
            "production prerequisite adapter is missing from core/pysrc",
        )
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        (self.root / ".codearbiter").mkdir()
        self.client = _FakeClient()

    def tearDown(self):
        self.temp.cleanup()

    def arm(self, *, confirmation_nonce="fixed-prerequisite-nonce", now=1000):
        return self.adapter.arm_user_prerequisite(
            self.root,
            self.client,
            "PLAN-EXAMPLE",
            "GATE-APPROVAL",
            confirmation_nonce=confirmation_nonce,
            now=now,
        )

    def consume(self, prompt, *, now=1001):
        return self.adapter.consume_user_prerequisite(
            self.root,
            self.client,
            prompt,
            host="codex",
            session_id="session-1",
            now=now,
        )

    def test_exact_host_prompt_captures_and_satisfies_current_prerequisite(self):
        armed = self.arm()
        self.assertEqual(
            armed["reply"],
            "satisfy-prerequisite PLAN-EXAMPLE GATE-APPROVAL fixed-prerequisite-nonce",
        )
        self.assertEqual(armed["requirement"], self.client.record["requirement"])

        result = self.consume(armed["reply"])

        self.assertTrue(result["satisfied"])
        source = self.root / result["authority_source"]
        event = json.loads(source.read_text(encoding="utf-8"))
        self.assertEqual(event["kind"], "prerequisite")
        self.assertEqual(event["authority_kind"], "user_workflow")
        self.assertEqual(event["verdict"], "satisfied")
        self.assertEqual(event["subject"], {
            "artifact_id": "PLAN-EXAMPLE",
            "normative_sha256": "2" * 64,
            "record_id": "GATE-APPROVAL",
        })
        self.assertEqual(event["source_text"], armed["reply"])
        self.assertEqual(event["origin"], "codex:UserPromptSubmit:session-1")
        self.assertEqual(
            [name for name, _ in self.client.calls][-2:],
            ["capture", "prerequisite"],
        )
        self.assertFalse((self.root / armed["pending"]).exists())

    def test_wrong_nonce_record_artifact_and_extra_text_confer_no_authority(self):
        armed = self.arm()
        before = list(self.client.calls)
        prompts = (
            "yes",
            "satisfy-prerequisite PLAN-EXAMPLE GATE-APPROVAL wrong-nonce-value",
            "satisfy-prerequisite PLAN-EXAMPLE GATE-BASELINE fixed-prerequisite-nonce",
            "satisfy-prerequisite PLAN-OTHER GATE-APPROVAL fixed-prerequisite-nonce",
            armed["reply"] + " please",
            armed["reply"] + "\nmore",
            " " + armed["reply"],
            armed["reply"] + " ",
            armed["reply"].replace(" ", "  ", 1),
            armed["reply"].replace(" ", "\t", 1),
        )
        for prompt in prompts:
            with self.subTest(prompt=prompt):
                result = self.consume(prompt)
                self.assertFalse(result["matched"])
                self.assertFalse(result["satisfied"])
        self.assertEqual(self.client.calls, before)
        self.assertTrue((self.root / armed["pending"]).exists())

    def test_nonce_length_boundaries_are_exact(self):
        for length in (12, 128):
            with self.subTest(length=length):
                client = _FakeClient(f"PLAN-NONCE-{length}")
                armed = self.adapter.arm_user_prerequisite(
                    self.root,
                    client,
                    client.identity["artifact_id"],
                    "GATE-APPROVAL",
                    confirmation_nonce="a" * length,
                    now=1000,
                )
                result = self.adapter.consume_user_prerequisite(
                    self.root,
                    client,
                    armed["reply"],
                    host="codex",
                    session_id=f"nonce-{length}",
                    now=1001,
                )
                self.assertTrue(result["satisfied"])
        for nonce in ("a" * 11, "a" * 129, "invalid.token"):
            with self.subTest(nonce=nonce):
                client = _FakeClient("PLAN-INVALID-NONCE")
                with self.assertRaisesRegex(RuntimeError, "INVALID_CONFIRMATION"):
                    self.adapter.arm_user_prerequisite(
                        self.root,
                        client,
                        "PLAN-INVALID-NONCE",
                        "GATE-APPROVAL",
                        confirmation_nonce=nonce,
                        now=1000,
                    )

    def test_stale_identity_and_approval_block_before_authority_publication(self):
        armed = self.arm()
        self.client.identity["normative_sha256"] = "9" * 64

        with self.assertRaisesRegex(RuntimeError, "STALE_PREREQUISITE"):
            self.consume(armed["reply"])

        source_dir = self.root / ".codearbiter" / ".artifacts" / "authority-sources"
        self.assertFalse(source_dir.exists())
        self.assertNotIn("capture", [name for name, _ in self.client.calls])
        self.assertTrue((self.root / armed["pending"]).exists())

    def test_revision_and_model_drift_block_with_same_normative_content(self):
        armed = self.arm()
        self.client.identity["revision"] += 1
        self.client.identity["model_sha256"] = "8" * 64

        with self.assertRaisesRegex(RuntimeError, "STALE_PREREQUISITE"):
            self.consume(armed["reply"])

        source_dir = self.root / ".codearbiter" / ".artifacts" / "authority-sources"
        self.assertFalse(source_dir.exists())
        self.assertNotIn("capture", [name for name, _ in self.client.calls])

    def test_revoked_approval_blocks_before_authority_publication(self):
        armed = self.arm()
        self.client.approved = False

        with self.assertRaisesRegex(RuntimeError, "AUTHORITY_UNVERIFIED"):
            self.consume(armed["reply"])

        source_dir = self.root / ".codearbiter" / ".artifacts" / "authority-sources"
        self.assertFalse(source_dir.exists())
        self.assertNotIn("capture", [name for name, _ in self.client.calls])
        self.assertTrue((self.root / armed["pending"]).exists())

    def test_expired_confirmation_conveys_no_authority(self):
        armed = self.arm(now=1000)
        with self.assertRaisesRegex(RuntimeError, "EXPIRED_PREREQUISITE"):
            self.consume(armed["reply"], now=1901)
        self.assertNotIn("capture", [name for name, _ in self.client.calls])
        source_dir = self.root / ".codearbiter" / ".artifacts" / "authority-sources"
        self.assertFalse(source_dir.exists())

    def test_multiple_plans_keep_independent_pending_requests(self):
        first = self.arm(confirmation_nonce="first-prerequisite-nonce")
        other = _FakeClient("PLAN-OTHER")
        other.record["id"] = "GATE-BASELINE"
        second = self.adapter.arm_user_prerequisite(
            self.root,
            other,
            "PLAN-OTHER",
            "GATE-BASELINE",
            confirmation_nonce="second-prerequisite-nonce",
            now=1000,
        )

        self.assertNotEqual(first["pending"], second["pending"])
        self.assertTrue((self.root / first["pending"]).exists())
        self.assertTrue((self.root / second["pending"]).exists())

        first_result = self.consume(first["reply"])
        self.assertTrue(first_result["satisfied"])
        self.assertFalse((self.root / first["pending"]).exists())
        self.assertTrue((self.root / second["pending"]).exists())

        second_result = self.adapter.consume_user_prerequisite(
            self.root,
            other,
            second["reply"],
            host="codex",
            session_id="session-2",
            now=1001,
        )
        self.assertTrue(second_result["satisfied"])

    def test_lost_mutation_response_retries_identical_operation(self):
        armed = self.arm()
        self.client.lose_prerequisite_response_once = True
        with self.assertRaisesRegex(RuntimeError, "response lost after commit"):
            self.consume(armed["reply"])
        pending = self.root / armed["pending"]
        self.assertTrue(pending.exists())

        result = self.consume(armed["reply"])

        requests = [request for name, request in self.client.calls if name == "prerequisite"]
        self.assertEqual(len(requests), 2)
        self.assertEqual(requests[0], requests[1])
        self.assertTrue(result["satisfied"])
        self.assertFalse(pending.exists())

    def test_concurrent_confirmation_serializes_the_complete_transition(self):
        class BlockingCaptureClient(_FakeClient):
            def __init__(self):
                super().__init__()
                self.capture_entered = threading.Event()
                self.release_capture = threading.Event()
                self.capture_count = 0
                self.capture_count_lock = threading.Lock()

            def call(self, operation, request=None, **kwargs):
                if operation == "capture":
                    with self.capture_count_lock:
                        self.capture_count += 1
                        first_capture = self.capture_count == 1
                    if first_capture:
                        self.capture_entered.set()
                        if not self.release_capture.wait(timeout=5):
                            raise RuntimeError("timed out waiting to release capture")
                return super().call(operation, request, **kwargs)

        self.client = BlockingCaptureClient()
        armed = self.arm()
        first_result = []
        first_error = []

        def consume_first():
            try:
                first_result.append(self.consume(armed["reply"]))
            except Exception as exc:  # pragma: no cover - asserted below
                first_error.append(exc)

        thread = threading.Thread(target=consume_first)
        thread.start()
        self.assertTrue(self.client.capture_entered.wait(timeout=5))
        try:
            with self.assertRaisesRegex(RuntimeError, "PREREQUISITE_BUSY"):
                self.adapter.consume_user_prerequisite(
                    self.root,
                    self.client,
                    armed["reply"],
                    host="codex",
                    session_id="session-2",
                    now=1001,
                )
        finally:
            self.client.release_capture.set()
            thread.join(timeout=5)

        self.assertFalse(thread.is_alive())
        self.assertEqual(first_error, [])
        self.assertTrue(first_result[0]["satisfied"])
        operations = [name for name, _ in self.client.calls]
        self.assertEqual(operations.count("capture"), 1)
        self.assertEqual(operations.count("prerequisite"), 1)

    def test_capture_failure_keeps_confirmed_event_stable_for_retry(self):
        armed = self.arm()
        self.client.failure = "capture"
        with self.assertRaisesRegex(RuntimeError, "capture failed"):
            self.consume(armed["reply"])
        pending = self.root / armed["pending"]
        confirmed = pending.read_bytes()
        confirmed_value = json.loads(confirmed)
        source = self.root / confirmed_value["authority_source"]
        source_bytes = source.read_bytes()
        first_capture = [
            request for name, request in self.client.calls if name == "capture"
        ]

        self.client.failure = None
        result = self.adapter.consume_user_prerequisite(
            self.root,
            self.client,
            armed["reply"],
            host="codex",
            session_id="different-session",
            now=1002,
        )

        event = json.loads((self.root / result["authority_source"]).read_text("utf-8"))
        self.assertEqual(event["origin"], "codex:UserPromptSubmit:session-1")
        capture_requests = [
            request for name, request in self.client.calls if name == "capture"
        ]
        self.assertEqual(capture_requests, first_capture * 2)
        self.assertEqual(source.read_bytes(), source_bytes)
        self.assertEqual(result["receipt"], self.client.capture_result["receipt"])

    def test_partial_temporary_publication_never_poisons_digest_path(self):
        armed = self.arm()
        original_write = self.adapter._write_new
        interrupted = False

        def fail_source_temporary(root, relative, data):
            nonlocal interrupted
            if (
                not interrupted
                and relative.parent == self.adapter.SOURCE_DIR
                and relative.name.startswith(".")
            ):
                interrupted = True
                target = root / relative
                target.parent.mkdir(parents=True, exist_ok=True)
                target.write_bytes(b"{")
                raise OSError("simulated interruption before atomic publication")
            return original_write(root, relative, data)

        self.adapter._write_new = fail_source_temporary
        try:
            with self.assertRaisesRegex(OSError, "simulated interruption"):
                self.consume(armed["reply"])
        finally:
            self.adapter._write_new = original_write

        pending = json.loads((self.root / armed["pending"]).read_text("utf-8"))
        digest_path = self.root / pending["authority_source"]
        self.assertFalse(digest_path.exists())

        result = self.consume(armed["reply"])
        self.assertTrue(result["satisfied"])
        self.assertEqual(
            json.loads(digest_path.read_text("utf-8"))["source_text"],
            armed["reply"],
        )

    def test_tampered_confirmed_event_cannot_widen_authority(self):
        armed = self.arm()
        self.client.failure = "capture"
        with self.assertRaisesRegex(RuntimeError, "capture failed"):
            self.consume(armed["reply"])
        pending_path = self.root / armed["pending"]
        pending = json.loads(pending_path.read_text("utf-8"))
        pending["event"]["authority_kind"] = "smarts_workflow"
        raw = self.adapter._canonical(pending["event"])
        digest = self.adapter._digest(raw)
        pending["authority_source"] = (
            f".codearbiter/.artifacts/authority-sources/{digest}.json"
        )
        pending_path.write_text(json.dumps(pending), encoding="utf-8")
        self.client.failure = None

        with self.assertRaisesRegex(RuntimeError, "INVALID_PENDING_PREREQUISITE"):
            self.consume(armed["reply"])

        self.assertNotIn("prerequisite", [name for name, _ in self.client.calls])

    def test_tampered_captured_mutation_request_is_rejected(self):
        armed = self.arm()
        self.client.failure = "prerequisite"
        with self.assertRaisesRegex(RuntimeError, "prerequisite failed"):
            self.consume(armed["reply"])
        pending_path = self.root / armed["pending"]
        pending = json.loads(pending_path.read_text("utf-8"))
        pending["mutation_request"]["prerequisite"] = "GATE-BASELINE"
        pending_path.write_text(json.dumps(pending), encoding="utf-8")
        self.client.failure = None

        with self.assertRaisesRegex(RuntimeError, "INVALID_PENDING_PREREQUISITE"):
            self.consume(armed["reply"])

    def test_cancel_requires_exact_plan_and_prerequisite(self):
        armed = self.arm()
        with self.assertRaisesRegex(RuntimeError, "PENDING_PREREQUISITE_MISMATCH"):
            self.adapter.cancel_user_prerequisite(
                self.root, "PLAN-EXAMPLE", "GATE-BASELINE"
            )

        result = self.adapter.cancel_user_prerequisite(
            self.root, "PLAN-EXAMPLE", "GATE-APPROVAL"
        )

        self.assertEqual(result, {
            "artifact_id": "PLAN-EXAMPLE",
            "prerequisite_id": "GATE-APPROVAL",
            "cancelled": True,
        })
        self.assertFalse((self.root / armed["pending"]).exists())

    def test_cancel_and_supersede_share_the_transition_lock(self):
        self.arm()

        with self.adapter._pending_transition_lock(self.root, "PLAN-EXAMPLE"):
            with self.assertRaisesRegex(RuntimeError, "PREREQUISITE_BUSY"):
                self.adapter.cancel_user_prerequisite(
                    self.root, "PLAN-EXAMPLE", "GATE-APPROVAL"
                )
            with self.assertRaisesRegex(RuntimeError, "PREREQUISITE_BUSY"):
                self.adapter.supersede_user_prerequisite(
                    self.root,
                    self.client,
                    "PLAN-EXAMPLE",
                    "GATE-APPROVAL",
                )


class PrerequisiteSurfaceTest(unittest.TestCase):
    def test_artifact_leaf_documents_production_prerequisite_route(self):
        text = (REPO / "core" / "surface" / "includes" / "artifacts.md").read_text(
            encoding="utf-8"
        )
        self.assertIn("_prerequisitelib.py\" arm", text)
        self.assertIn("--prerequisite-id <prerequisite-id>", text)
        self.assertIn("satisfy-prerequisite", text)
        self.assertIn("_prerequisitelib.py\" supersede", text)
        self.assertIn("Do not infer eligibility from one satisfied prerequisite", text)
        self.assertNotIn("--authority-kind", text)


class PrerequisiteProductionBoundaryTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.installation_owner, cls.installation = build_installation()
        spec = importlib.util.spec_from_file_location("_prerequisitelib_e2e", ADAPTER_PATH)
        cls.adapter = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(cls.adapter)

    @classmethod
    def tearDownClass(cls):
        if cls.installation_owner is not None:
            cls.installation_owner.cleanup()

    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="ca-prerequisite-production-")
        self.addCleanup(self.temp.cleanup)
        self.root = physical_test_directory(self.temp.name) / "repo"
        self.root.mkdir()
        self.workflow = WorkflowHarness(self.root, self.installation)

    def create_approved_plan(self, workflow=None, prerequisite_ids=("GATE-APPROVAL",)):
        workflow = workflow or self.workflow
        spec_identity = workflow.create_spec()
        plan = plan_normative("SPEC-FLOW", spec_identity["normative_sha256"])
        plan["prerequisites"] = [
            {
                "id": prerequisite_id,
                "title": f"Owner decision for {prerequisite_id}",
                "requirement": f"The owner explicitly satisfies {prerequisite_id}.",
                "source_refs": [],
            }
            for prerequisite_id in prerequisite_ids
        ]
        workflow.client.call("create", {
            "operation_id": workflow.operation_id("create-plan"),
            "artifact_id": "PLAN-FLOW",
            "kind": "plan",
            "slug": "flow",
            "title": plan["title"],
            "summary": plan["summary"],
            "spec_id": "SPEC-FLOW",
            "normative": plan,
        })
        workflow.approve_pair()
        return workflow.client.call("identity", {"artifact_id": "PLAN-FLOW"})

    def test_real_engine_moves_from_unsatisfied_to_eligible_through_adapter(self):
        self.create_approved_plan()
        with self.assertRaisesRegex(RuntimeError, "PREREQUISITE_UNSATISFIED"):
            self.workflow.client.call("eligible", {"artifact_id": "PLAN-FLOW"})

        approval_receipt = None
        for path in (self.root / ".codearbiter" / ".artifacts" / "receipts").glob("*.json"):
            receipt = json.loads(path.read_text(encoding="utf-8"))
            subject = receipt.get("subject") or {}
            if (
                receipt.get("kind") == "approval"
                and subject.get("artifact_id") == "PLAN-FLOW"
                and subject.get("record_id") == "PLAN-FLOW"
            ):
                approval_receipt = path.relative_to(self.root).as_posix()
                break
        self.assertIsNotNone(approval_receipt)
        identity = self.workflow.client.call("identity", {"artifact_id": "PLAN-FLOW"})
        with self.assertRaisesRegex(RuntimeError, "STALE_EVIDENCE"):
            self.workflow.client.call("prerequisite", {
                "artifact_id": "PLAN-FLOW",
                "operation_id": self.workflow.operation_id("wrong-receipt-kind"),
                "expected": {
                    "revision": identity["revision"],
                    "model_sha256": identity["model_sha256"],
                },
                "prerequisite": "GATE-APPROVAL",
                "receipt": approval_receipt,
            })

        armed = self.adapter.arm_user_prerequisite(
            self.root,
            self.workflow.client,
            "PLAN-FLOW",
            "GATE-APPROVAL",
            confirmation_nonce="production-boundary-nonce",
            now=1000,
        )
        result = self.adapter.consume_user_prerequisite(
            self.root,
            self.workflow.client,
            armed["reply"],
            host="codex",
            session_id="production-session",
            now=1001,
        )
        eligible = self.workflow.client.call("eligible", {"artifact_id": "PLAN-FLOW"})

        self.assertTrue(result["satisfied"])
        self.assertEqual(eligible["artifact_id"], "PLAN-FLOW")
        self.assertTrue(eligible["tasks"])

    def test_real_engine_supersedes_stale_confirmed_and_captured_requests(self):
        class FailOnceClient:
            def __init__(self, client, operation):
                self.client = client
                self.operation = operation
                self.failed = False

            def call(self, operation, request=None, **kwargs):
                if operation == self.operation and not self.failed:
                    self.failed = True
                    raise ArtifactError("INJECTED_FAILURE", "simulated lost boundary")
                return self.client.call(operation, request, **kwargs)

        for interrupted_operation, expected_state in (
            ("capture", "CONFIRMED"),
            ("prerequisite", "CAPTURED"),
        ):
            with self.subTest(state=expected_state):
                owner = tempfile.TemporaryDirectory(prefix="ca-prerequisite-supersede-")
                self.addCleanup(owner.cleanup)
                root = physical_test_directory(owner.name) / "repo"
                root.mkdir()
                workflow = WorkflowHarness(root, self.installation)
                self.create_approved_plan(workflow)
                client = FailOnceClient(workflow.client, interrupted_operation)
                armed = self.adapter.arm_user_prerequisite(
                    root,
                    client,
                    "PLAN-FLOW",
                    "GATE-APPROVAL",
                    confirmation_nonce=f"supersede-{expected_state.lower()}-nonce",
                    now=1000,
                )
                with self.assertRaisesRegex(RuntimeError, "simulated lost boundary"):
                    self.adapter.consume_user_prerequisite(
                        root,
                        client,
                        armed["reply"],
                        host="codex",
                        session_id="supersede-session",
                        now=1001,
                    )
                pending_path = root / armed["pending"]
                pending = json.loads(pending_path.read_text("utf-8"))
                self.assertEqual(pending["state"], expected_state)
                authority_source = root / pending["authority_source"]
                self.assertTrue(authority_source.is_file())
                if pending["receipt"] is not None:
                    self.assertTrue((root / pending["receipt"]).is_file())

                workflow.mutate(
                    "apply",
                    "PLAN-FLOW",
                    changes=[{
                        "op": "header.update",
                        "fields": {"summary": f"Concurrent drift after {expected_state}."},
                    }],
                )
                result = self.adapter.supersede_user_prerequisite(
                    root, workflow.client, "PLAN-FLOW", "GATE-APPROVAL"
                )

                self.assertTrue(result["superseded"])
                self.assertFalse(result["satisfied"])
                self.assertFalse(pending_path.exists())
                self.assertTrue(authority_source.is_file())
                if result["receipt"] is not None:
                    self.assertTrue((root / result["receipt"]).is_file())

    def test_real_engine_satisfies_same_plan_prerequisites_sequentially(self):
        prerequisite_ids = ("GATE-APPROVAL", "GATE-BASELINE")
        self.create_approved_plan(prerequisite_ids=prerequisite_ids)

        for index, prerequisite_id in enumerate(prerequisite_ids, start=1):
            armed = self.adapter.arm_user_prerequisite(
                self.root,
                self.workflow.client,
                "PLAN-FLOW",
                prerequisite_id,
                confirmation_nonce=f"sequential-prerequisite-nonce-{index}",
                now=1000 + index,
            )
            result = self.adapter.consume_user_prerequisite(
                self.root,
                self.workflow.client,
                armed["reply"],
                host="codex",
                session_id=f"sequential-{index}",
                now=1010 + index,
            )
            self.assertTrue(result["satisfied"])

        eligible = self.workflow.client.call("eligible", {"artifact_id": "PLAN-FLOW"})
        self.assertTrue(eligible["tasks"])


class ExternalInstallationLifecycleTest(unittest.TestCase):
    def test_production_boundary_teardown_leaves_external_installation_owned_by_caller(self):
        original_owner = getattr(PrerequisiteProductionBoundaryTest, "installation_owner", None)
        self.addCleanup(
            setattr,
            PrerequisiteProductionBoundaryTest,
            "installation_owner",
            original_owner,
        )
        PrerequisiteProductionBoundaryTest.installation_owner = None

        PrerequisiteProductionBoundaryTest.tearDownClass()


if __name__ == "__main__":
    unittest.main()
