#!/usr/bin/env python3
"""Regression tests for host-owned structured-artifact approval capture."""

import hashlib
import importlib
import json
import subprocess
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
    def __init__(self, root):
        self.root = root
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
        if operation == "evidence-context":
            context = {
                "format": "codearbiter.evidence-context/0.1.0",
                "activity": "approval",
                "subject": {"artifact_id": self.identity["artifact_id"], "normative_sha256": self.identity["normative_sha256"], "record_id": self.identity["artifact_id"]},
                "input_sha256": self.identity["normative_sha256"],
                "prompt_sha256": request["prompt_sha256"],
                "record": dict(self.identity),
            }
            raw_record = json.dumps(context["record"], ensure_ascii=True, sort_keys=True, separators=(",", ":")).encode()
            context["record_sha256"] = hashlib.sha256(raw_record).hexdigest()
            raw = json.dumps(context, ensure_ascii=True, sort_keys=True, separators=(",", ":")).encode()
            digest = hashlib.sha256(raw).hexdigest()
            relative = Path(".codearbiter/.artifacts/evidence-contexts") / f"{digest}.json"
            target = self.root / relative
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(raw)
            return {"context_ref": relative.as_posix(), "context_sha256": digest}
        if operation == "capture-observation":
            return dict(self.capture_result)
        if operation == "approve":
            return {"artifact_id": "SPEC-EXAMPLE", "revision": 8}
        raise AssertionError(operation)


class ApprovalAdapterTest(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        (self.root / ".codearbiter").mkdir()
        self.client = _FakeClient(self.root)
        self.adapter = importlib.import_module("_approvallib")
        self.routes = importlib.import_module("_artifactpromptlib")
        self.original_registry_parent = self.routes.REGISTRY_PARENT
        self.routes.REGISTRY_PARENT = self.root

    def tearDown(self):
        self.routes.REGISTRY_PARENT = self.original_registry_parent
        self.temp.cleanup()

    def test_cross_repository_hook_routes_exact_prompt_and_ambiguity_fails_closed(self):
        other = self.root / "other"
        other.mkdir()
        armed = self.adapter.arm_user_approval(
            self.root, self.client, "SPEC-EXAMPLE", token="fixed-token-route"
        )
        with mock.patch.object(self.adapter._artifactlib, "ArtifactClient", return_value=self.client):
            result = self.adapter.consume_from_hook(
                root=other, plugin_root=self.root, prompt=armed["reply"],
                host="codex", session_id="session-route",
            )
        self.assertIn("workflow approval recorded", result)
        self.assertFalse((self.root / self.adapter.PENDING).exists())

        first = self.root / "first"
        second = self.root / "second"
        first.mkdir()
        second.mkdir()
        prompt = "approve SPEC-COLLISION fixed-token-route"
        self.routes.register(first, "approval", "SPEC-COLLISION", prompt)
        self.routes.register(second, "approval", "SPEC-COLLISION", prompt)
        with self.assertRaisesRegex(RuntimeError, "multiple repositories"):
            self.routes.resolve("approval", prompt)

    def test_native_linked_worktree_identity_is_routable(self):
        repository = self.root / "repository"
        linked = self.root / "linked"
        subprocess.run(["git", "init", "--quiet", str(repository)], check=True)
        subprocess.run(["git", "-C", str(repository), "config", "user.email", "test@example.invalid"], check=True)
        subprocess.run(["git", "-C", str(repository), "config", "user.name", "Test"], check=True)
        (repository / "tracked.txt").write_text("x", encoding="utf-8")
        subprocess.run(["git", "-C", str(repository), "add", "tracked.txt"], check=True)
        subprocess.run(["git", "-C", str(repository), "commit", "--quiet", "-m", "fixture"], check=True)
        subprocess.run(["git", "-C", str(repository), "worktree", "add", "--quiet", "-b", "linked", str(linked)], check=True)
        prompt = "approve SPEC-LINKED fixed-token-linked"
        self.routes.register(linked, "approval", "SPEC-LINKED", prompt)
        self.assertEqual(self.routes.resolve("approval", prompt), linked.resolve())

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
        self.assertEqual([name for name, _ in self.client.calls][-2:], ["capture-observation", "approve"])
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

    def test_write_new_removes_partial_file_after_io_failure(self):
        real_close = self.adapter.os.close

        def close_then_fail(fd):
            real_close(fd)
            raise OSError("close failed")

        failures = (
            (
                "write",
                mock.patch.object(
                    self.adapter.os, "write", side_effect=OSError("write failed")
                ),
            ),
            (
                "fsync",
                mock.patch.object(
                    self.adapter.os, "fsync", side_effect=OSError("fsync failed")
                ),
            ),
            (
                "close",
                mock.patch.object(
                    self.adapter.os, "close", side_effect=close_then_fail
                ),
            ),
        )
        for operation, failure in failures:
            with self.subTest(operation=operation):
                relative = (
                    Path(".codearbiter")
                    / ".markers"
                    / f"write-new-{operation}-test.json"
                )
                path = self.root / relative
                with failure, self.assertRaisesRegex(OSError, f"{operation} failed"):
                    self.adapter._write_new(self.root, relative, b"partial")

                self.assertFalse(path.exists())
                self.adapter._write_new(self.root, relative, b"retry")
                self.assertEqual(path.read_bytes(), b"retry")
                path.unlink()


if __name__ == "__main__":
    unittest.main()
