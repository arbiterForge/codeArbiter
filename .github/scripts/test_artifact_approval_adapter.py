#!/usr/bin/env python3
"""Regression tests for host-owned structured-artifact approval capture."""

import hashlib
import importlib
import json
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

HERE = Path(__file__).resolve().parent
REPO = HERE.parent.parent
CORE_PYSRC = REPO / "core" / "pysrc"
sys.path.insert(0, str(CORE_PYSRC))


class _FakeClient:
    def __init__(self):
        self.identity = {
            "artifact_id": "SPEC-EXAMPLE",
            "kind": "spec",
            "revision": 7,
            "model_sha256": "1" * 64,
            "normative_sha256": "2" * 64,
        }
        self.calls = []
        self.failure = None
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
                "valid": True,
                "gate": "ready",
                "authority": {
                    "state": "draft",
                    "authority_verified": False,
                },
            }
        if operation == "capture":
            return dict(self.capture_result)
        if operation == "approve":
            return {"artifact_id": "SPEC-EXAMPLE", "revision": 8}
        raise AssertionError(operation)


class ApprovalAdapterTest(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        (self.root / ".codearbiter").mkdir()
        self.client = _FakeClient()
        self.adapter = importlib.import_module("_approvallib")

    def tearDown(self):
        self.temp.cleanup()

    def test_exact_host_prompt_captures_and_approves_current_identity(self):
        armed = self.adapter.arm_user_approval(
            self.root, self.client, "SPEC-EXAMPLE", token="fixed-token-1"
        )
        self.assertEqual(
            armed["reply"], "approve SPEC-EXAMPLE fixed-token-1"
        )

        result = self.adapter.consume_user_approval(
            self.root,
            self.client,
            armed["reply"],
            host="codex",
            session_id="session-1",
        )

        self.assertTrue(result["approved"])
        source = self.root / result["authority_source"]
        event = json.loads(source.read_text(encoding="utf-8"))
        self.assertEqual(event["source_text"], armed["reply"])
        self.assertEqual(event["origin"], "codex:UserPromptSubmit:session-1")
        self.assertEqual(event["subject"]["normative_sha256"], "2" * 64)
        self.assertEqual([name for name, _ in self.client.calls][-2:], ["capture", "approve"])
        self.assertFalse((self.root / ".codearbiter" / ".markers" / "pending-user-approval.json").exists())

    def test_plain_yes_wrong_token_and_unrelated_prompt_confer_no_authority(self):
        self.adapter.arm_user_approval(
            self.root, self.client, "SPEC-EXAMPLE", token="fixed-token-1"
        )
        before = list(self.client.calls)
        for prompt in ("yes", "approve SPEC-EXAMPLE wrong", "please continue"):
            result = self.adapter.consume_user_approval(
                self.root, self.client, prompt, host="codex", session_id="session-1"
            )
            self.assertFalse(result["matched"])
        self.assertEqual(self.client.calls, before)

    def test_stale_artifact_blocks_before_authority_source_or_capture(self):
        armed = self.adapter.arm_user_approval(
            self.root, self.client, "SPEC-EXAMPLE", token="fixed-token-1"
        )
        self.client.identity["model_sha256"] = "9" * 64

        with self.assertRaisesRegex(RuntimeError, "STALE_APPROVAL"):
            self.adapter.consume_user_approval(
                self.root,
                self.client,
                armed["reply"],
                host="codex",
                session_id="session-1",
            )

        source_dir = self.root / ".codearbiter" / ".artifacts" / "authority-sources"
        self.assertFalse(source_dir.exists())
        self.assertNotIn("capture", [name for name, _ in self.client.calls])

    def test_pending_request_blocks_rearm_until_exact_artifact_is_cancelled(self):
        self.adapter.arm_user_approval(
            self.root, self.client, "SPEC-EXAMPLE", token="fixed-token-1"
        )
        with self.assertRaisesRegex(RuntimeError, "PENDING_APPROVAL"):
            self.adapter.arm_user_approval(
                self.root, self.client, "SPEC-EXAMPLE", token="fixed-token-2"
            )
        with self.assertRaisesRegex(RuntimeError, "PENDING_APPROVAL_MISMATCH"):
            self.adapter.cancel_user_approval(self.root, "SPEC-OTHER")

        result = self.adapter.cancel_user_approval(self.root, "SPEC-EXAMPLE")

        self.assertEqual(result, {"artifact_id": "SPEC-EXAMPLE", "cancelled": True})
        self.assertFalse(
            (self.root / ".codearbiter" / ".markers" / "pending-user-approval.json").exists()
        )
        self.assertNotIn("capture", [name for name, _ in self.client.calls])

    def test_malformed_pending_values_and_host_context_fail_closed(self):
        armed = self.adapter.arm_user_approval(
            self.root, self.client, "SPEC-EXAMPLE", token="fixed-token-1"
        )
        pending_path = (
            self.root / ".codearbiter" / ".markers" / "pending-user-approval.json"
        )
        pending = json.loads(pending_path.read_text(encoding="utf-8"))
        pending["token_sha256"] = 7
        pending_path.write_text(json.dumps(pending), encoding="utf-8")
        with self.assertRaisesRegex(RuntimeError, "INVALID_PENDING_APPROVAL"):
            self.adapter.consume_user_approval(
                self.root,
                self.client,
                armed["reply"],
                host="codex",
                session_id="session-1",
            )

        pending["token_sha256"] = hashlib.sha256(b"fixed-token-1").hexdigest()
        pending_path.write_text(json.dumps(pending), encoding="utf-8")
        with self.assertRaisesRegex(RuntimeError, "INVALID_HOST_CONTEXT"):
            self.adapter.consume_user_approval(
                self.root,
                self.client,
                armed["reply"],
                host="codex",
                session_id="bad session",
            )
        self.assertNotIn("capture", [name for name, _ in self.client.calls])

    def test_capture_and_approve_failures_never_report_success_and_remain_retryable(self):
        armed = self.adapter.arm_user_approval(
            self.root, self.client, "SPEC-EXAMPLE", token="fixed-token-1"
        )
        pending = self.root / self.adapter.PENDING

        self.client.capture_result = {}
        with self.assertRaisesRegex(RuntimeError, "INVALID_RECEIPT"):
            self.adapter.consume_user_approval(
                self.root,
                self.client,
                armed["reply"],
                host="codex",
                session_id="session-1",
            )
        self.assertTrue(pending.exists())
        self.assertNotIn("approve", [name for name, _ in self.client.calls])

        self.client.capture_result = {
            "receipt": ".codearbiter/.artifacts/receipts/" + "3" * 64 + ".json"
        }
        self.client.failure = "approve"
        with self.assertRaisesRegex(RuntimeError, "approve failed"):
            self.adapter.consume_user_approval(
                self.root,
                self.client,
                armed["reply"],
                host="codex",
                session_id="session-1",
            )
        self.assertTrue(pending.exists())

        self.client.failure = None
        result = self.adapter.consume_user_approval(
            self.root,
            self.client,
            armed["reply"],
            host="codex",
            session_id="session-1",
        )
        self.assertTrue(result["approved"])
        self.assertFalse(pending.exists())

    def test_hook_contains_oserror_without_hiding_an_explicit_approval_failure(self):
        armed = self.adapter.arm_user_approval(
            self.root, self.client, "SPEC-EXAMPLE"
        )
        with mock.patch.object(
            self.adapter._artifactlib,
            "ArtifactClient",
            side_effect=OSError("helper startup failed"),
        ):
            unrelated = self.adapter.consume_from_hook(
                root=self.root,
                plugin_root=self.root,
                prompt="continue with unrelated work",
                host="codex",
                session_id="session-1",
            )
            result = self.adapter.consume_from_hook(
                root=self.root,
                plugin_root=self.root,
                prompt=armed["reply"],
                host="codex",
                session_id="session-1",
            )

        self.assertEqual(unrelated, "")
        self.assertEqual(
            result,
            "codeArbiter: approval capture failed: helper startup failed",
        )
        self.assertTrue((self.root / self.adapter.PENDING).exists())


if __name__ == "__main__":
    unittest.main()
