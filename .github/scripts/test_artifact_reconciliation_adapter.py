#!/usr/bin/env python3
"""Regression tests for exact-prompt task/scope reconciliation authority."""

import importlib
import importlib.util
import hashlib
import io
import json
import subprocess
from contextlib import redirect_stdout, redirect_stderr
from pathlib import Path
import sys
import tempfile
import threading
import unittest
from unittest import mock

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
        self.fail_after_reconciliation = False
        self.reconciliation_failure_code = None
        self.reconciled_requests = {}

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
            if self.reconciliation_failure_code:
                from _artifactlib import ArtifactError
                raise ArtifactError(self.reconciliation_failure_code, "fixture mutation did not commit")
            operation_id = request["operation_id"]
            previous = self.reconciled_requests.get(operation_id)
            if previous is not None:
                assert previous == request
                return {"revision": 4, "transaction": {"operation_id": operation_id, "state": "committed", "replay": True}}
            self.reconciled_requests[operation_id] = dict(request)
            self.identity["revision"] = 4
            if self.fail_after_reconciliation:
                self.fail_after_reconciliation = False
                raise OSError("response lost after commit")
            return {"revision": 4, "transaction": {"operation_id": operation_id, "state": "committed", "replay": False}}
        raise AssertionError(operation)


class FilesystemSnapshotClient(FakeClient):
    """Model a plan whose input root includes operational .codearbiter paths."""

    def __init__(self, root, input_root=".codearbiter"):
        super().__init__(root)
        self.input_root = input_root

    def call(self, operation, request=None, **kwargs):
        if operation == "snapshot":
            digest = hashlib.sha256()
            for path in sorted((self.root / self.input_root).rglob("*")):
                relative = path.relative_to(self.root)
                if (relative.parts[0] != ".git"
                        and relative.parts[:2] != (".codearbiter", ".artifacts")
                        and path.is_file()):
                    digest.update(path.relative_to(self.root).as_posix().encode())
                    digest.update(path.read_bytes())
            return {"sha256": digest.hexdigest()}
        return super().call(operation, request, **kwargs)


class ReconciliationTest(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        (self.root / ".codearbiter").mkdir()
        subprocess.run(["git", "init", "-q", str(self.root)], check=True)
        self.adapter = importlib.import_module("_reconciliationlib")
        self.routes = importlib.import_module("_artifactpromptlib")
        self.old_registry = self.routes.REGISTRY_PARENT
        self.routes.REGISTRY_PARENT = self.root
        self.replies = importlib.import_module("_replylib")
        self.old_codes = self.replies.REGISTRY_PARENT
        self.replies.REGISTRY_PARENT = self.root
        self.client = FakeClient(self.root)

    def tearDown(self):
        self.routes.REGISTRY_PARENT = self.old_registry
        self.replies.REGISTRY_PARENT = self.old_codes
        self.temp.cleanup()

    def hook(self, prompt):
        with mock.patch.object(self.adapter._artifactlib, "ArtifactClient", return_value=self.client):
            return self.adapter.consume_from_hook(
                root=self.root, plugin_root=self.root, prompt=prompt,
                host="claude", session_id="session-lenient",
            )

    def arm_task(self, token="fixed-reconcile-token"):
        return self.adapter.arm_reconciliation(
            self.root, self.client, "PLAN-EXAMPLE", "T-001", "task-reconcile",
            target_state="PENDING", reason="Interrupted verifier.",
            assessment="The prior attempt has no established completion.", token=token,
        )

    def test_arming_does_not_change_a_governed_codearbiter_input(self):
        (self.root / ".codearbiter/open-tasks.md").write_text("original\n", encoding="utf-8")
        self.client = FilesystemSnapshotClient(self.root)
        before = self.client.call("snapshot", {"artifact_id": "PLAN-EXAMPLE"})["sha256"]
        self.arm_task()
        after = self.client.call("snapshot", {"artifact_id": "PLAN-EXAMPLE"})["sha256"]
        self.assertEqual(before, after, "arming changed the governed plan input")

    def test_arming_does_not_change_a_whole_repository_input(self):
        (self.root / ".codearbiter/open-tasks.md").write_text("original\n", encoding="utf-8")
        self.client = FilesystemSnapshotClient(self.root, ".")
        with tempfile.TemporaryDirectory() as registry:
            self.routes.REGISTRY_PARENT = Path(registry)
            self.replies.REGISTRY_PARENT = Path(registry)
            before = self.client.call("snapshot", {"artifact_id": "PLAN-EXAMPLE"})["sha256"]
            self.arm_task()
            after = self.client.call("snapshot", {"artifact_id": "PLAN-EXAMPLE"})["sha256"]
        self.assertEqual(before, after, "arming changed the whole repository input")

    def test_genuine_governed_source_change_remains_stale(self):
        source = self.root / ".codearbiter/open-tasks.md"
        source.write_text("original\n", encoding="utf-8")
        self.client = FilesystemSnapshotClient(self.root)
        armed = self.arm_task()
        source.write_text("changed\n", encoding="utf-8")
        with self.assertRaisesRegex(RuntimeError, "target changed after arming"):
            self.adapter.consume_reconciliation(
                self.root, self.client, armed["reply"], host="codex", session_id="stale-source"
            )
        self.assertFalse(any(name == "task-reconcile" for name, _ in self.client.calls))

    def test_linked_worktrees_have_distinct_admin_reconciliation_state(self):
        source = self.root / ".codearbiter/open-tasks.md"
        source.write_text("shared\n", encoding="utf-8")
        subprocess.run(["git", "-C", str(self.root), "add", ".codearbiter/open-tasks.md"], check=True)
        subprocess.run([
            "git", "-C", str(self.root), "-c", "user.name=Fixture", "-c", "user.email=fixture@example.test",
            "commit", "-qm", "fixture",
        ], check=True)
        with tempfile.TemporaryDirectory() as sibling:
            linked = Path(sibling) / "linked"
            subprocess.run(["git", "-C", str(self.root), "worktree", "add", "-q", "--detach", str(linked)], check=True)
            first = self.arm_task(token="first-worktree-token")
            second = self.adapter.arm_reconciliation(
                linked, FakeClient(linked), "PLAN-EXAMPLE", "T-001", "task-reconcile",
                target_state="PENDING", reason="Interrupted verifier.",
                assessment="The prior attempt has no established completion.", token="second-worktree-token",
            )
            self.assertNotEqual(self.adapter._state_root(self.root), self.adapter._state_root(linked))
            self.assertTrue(self.adapter._pending_path(self.root, "PLAN-EXAMPLE").exists())
            self.assertTrue(self.adapter._pending_path(linked, "PLAN-EXAMPLE").exists())
            self.assertNotEqual(first["reply"], second["reply"])

    def test_legacy_armed_request_requires_exact_cancellation_before_rearming(self):
        armed = self.arm_task()
        legacy = self.root / self.adapter.LEGACY_PENDING_DIR / "PLAN-EXAMPLE.json"
        legacy.parent.mkdir(parents=True)
        self.adapter._pending_path(self.root, "PLAN-EXAMPLE").rename(legacy)
        with self.assertRaisesRegex(RuntimeError, "legacy reconciliation"):
            self.adapter.consume_reconciliation(
                self.root, self.client, armed["reply"], host="codex", session_id="legacy"
            )
        before_snapshots = len([name for name, _ in self.client.calls if name == "snapshot"])
        with self.assertRaisesRegex(RuntimeError, "PENDING_RECONCILIATION"):
            self.arm_task(token="replacement-token")
        self.assertEqual(before_snapshots, len([name for name, _ in self.client.calls if name == "snapshot"]))
        self.assertTrue(self.adapter.cancel_reconciliation(self.root, "PLAN-EXAMPLE", armed["reply"])["cancelled"])
        self.assertFalse(legacy.exists())

    def test_legacy_interrupted_attempt_replays_its_exact_request(self):
        armed = self.arm_task()
        self.client.fail_after_reconciliation = True
        with self.assertRaisesRegex(OSError, "response lost"):
            self.adapter.consume_reconciliation(
                self.root, self.client, armed["reply"], host="codex", session_id="before-upgrade"
            )
        pending = self.adapter._load(self.root, "PLAN-EXAMPLE")
        attempt = self.adapter._attempt_path(self.root, pending)
        legacy_pending = self.root / self.adapter.LEGACY_PENDING_DIR / "PLAN-EXAMPLE.json"
        legacy_attempt = self.root / self.adapter.LEGACY_ATTEMPT_DIR / attempt.name
        legacy_pending.parent.mkdir(parents=True)
        legacy_attempt.parent.mkdir(parents=True)
        self.adapter._pending_path(self.root, "PLAN-EXAMPLE").rename(legacy_pending)
        attempt.rename(legacy_attempt)
        self.assertTrue(self.adapter.recover_reconciliation(self.root, self.client, "PLAN-EXAMPLE")["committed"])
        self.assertFalse(legacy_pending.exists())
        self.assertFalse(legacy_attempt.exists())
        requests = [request for name, request in self.client.calls if name == "task-reconcile"]
        self.assertEqual(requests[0], requests[1])

    def test_dual_legacy_and_admin_pending_state_is_ambiguous(self):
        self.arm_task()
        legacy = self.root / self.adapter.LEGACY_PENDING_DIR / "PLAN-EXAMPLE.json"
        legacy.parent.mkdir(parents=True)
        legacy.write_bytes(self.adapter._pending_path(self.root, "PLAN-EXAMPLE").read_bytes())
        with self.assertRaisesRegex(RuntimeError, "ambiguous reconciliation state"):
            self.adapter._load(self.root, "PLAN-EXAMPLE")

    def test_legacy_pending_with_admin_attempt_cannot_be_cancelled_or_recovered(self):
        armed = self.arm_task()
        self.client.fail_after_reconciliation = True
        with self.assertRaisesRegex(OSError, "response lost"):
            self.adapter.consume_reconciliation(
                self.root, self.client, armed["reply"], host="codex", session_id="lost-response"
            )
        pending = self.adapter._load(self.root, "PLAN-EXAMPLE")
        admin_attempt = self.adapter._attempt_path(self.root, pending)
        legacy_pending = self.root / self.adapter.LEGACY_PENDING_DIR / "PLAN-EXAMPLE.json"
        legacy_pending.parent.mkdir(parents=True)
        self.adapter._pending_path(self.root, "PLAN-EXAMPLE").rename(legacy_pending)
        before = len([name for name, _ in self.client.calls if name == "task-reconcile"])
        with self.assertRaisesRegex(RuntimeError, "mixed reconciliation state"):
            self.adapter.cancel_reconciliation(self.root, "PLAN-EXAMPLE", armed["reply"])
        with self.assertRaisesRegex(RuntimeError, "mixed reconciliation state"):
            self.adapter.recover_reconciliation(self.root, self.client, "PLAN-EXAMPLE")
        self.assertEqual(before, len([name for name, _ in self.client.calls if name == "task-reconcile"]))
        self.assertTrue(legacy_pending.exists())
        self.assertTrue(admin_attempt.exists())

    def test_admin_pending_with_legacy_attempt_cannot_be_cancelled_or_recovered(self):
        armed = self.arm_task()
        self.client.fail_after_reconciliation = True
        with self.assertRaisesRegex(OSError, "response lost"):
            self.adapter.consume_reconciliation(
                self.root, self.client, armed["reply"], host="codex", session_id="lost-response"
            )
        pending = self.adapter._load(self.root, "PLAN-EXAMPLE")
        admin_pending = self.adapter._pending_path(self.root, "PLAN-EXAMPLE")
        admin_attempt = self.adapter._attempt_path(self.root, pending)
        legacy_attempt = self.root / self.adapter.LEGACY_ATTEMPT_DIR / admin_attempt.name
        legacy_attempt.parent.mkdir(parents=True)
        admin_attempt.rename(legacy_attempt)
        before = len([name for name, _ in self.client.calls if name == "task-reconcile"])
        with self.assertRaisesRegex(RuntimeError, "mixed reconciliation state"):
            self.adapter.cancel_reconciliation(self.root, "PLAN-EXAMPLE", armed["reply"])
        with self.assertRaisesRegex(RuntimeError, "mixed reconciliation state"):
            self.adapter.recover_reconciliation(self.root, self.client, "PLAN-EXAMPLE")
        self.assertEqual(before, len([name for name, _ in self.client.calls if name == "task-reconcile"]))
        self.assertTrue(admin_pending.exists())
        self.assertTrue(legacy_attempt.exists())

    def test_dual_attempt_locations_cannot_be_cancelled_or_recovered(self):
        armed = self.arm_task()
        self.client.fail_after_reconciliation = True
        with self.assertRaisesRegex(OSError, "response lost"):
            self.adapter.consume_reconciliation(
                self.root, self.client, armed["reply"], host="codex", session_id="lost-response"
            )
        pending = self.adapter._load(self.root, "PLAN-EXAMPLE")
        admin_attempt = self.adapter._attempt_path(self.root, pending)
        legacy_attempt = self.root / self.adapter.LEGACY_ATTEMPT_DIR / admin_attempt.name
        legacy_attempt.parent.mkdir(parents=True)
        legacy_attempt.write_bytes(admin_attempt.read_bytes())
        with self.assertRaisesRegex(RuntimeError, "mixed reconciliation state"):
            self.adapter.cancel_reconciliation(self.root, "PLAN-EXAMPLE", armed["reply"])
        with self.assertRaisesRegex(RuntimeError, "mixed reconciliation state"):
            self.adapter.recover_reconciliation(self.root, self.client, "PLAN-EXAMPLE")
        self.assertTrue(self.adapter._pending_path(self.root, "PLAN-EXAMPLE").exists())
        self.assertTrue(admin_attempt.exists())
        self.assertTrue(legacy_attempt.exists())

    def test_attempt_persistence_does_not_change_governed_snapshot(self):
        source = self.root / ".codearbiter/open-tasks.md"
        source.write_text("original\n", encoding="utf-8")
        self.client = FilesystemSnapshotClient(self.root)
        before = self.client.call("snapshot", {"artifact_id": "PLAN-EXAMPLE"})["sha256"]
        self.client.snapshot_sha = before
        armed = self.arm_task()
        self.client.fail_after_reconciliation = True
        with self.assertRaisesRegex(OSError, "response lost"):
            self.adapter.consume_reconciliation(
                self.root, self.client, armed["reply"], host="codex", session_id="lost-response"
            )
        pending = self.adapter._load(self.root, "PLAN-EXAMPLE")
        self.assertTrue(self.adapter._attempt_path(self.root, pending).exists())
        after = self.client.call("snapshot", {"artifact_id": "PLAN-EXAMPLE"})["sha256"]
        self.assertEqual(before, after, "attempt persistence changed the governed plan input")

    def test_unsafe_admin_attempt_directory_blocks_consumption(self):
        armed = self.arm_task()
        attempts = self.adapter._state_root(self.root) / self.adapter.ATTEMPT_DIR
        attempts.write_text("not a directory", encoding="utf-8")
        with self.assertRaisesRegex(RuntimeError, "directory is unsafe"):
            self.adapter.consume_reconciliation(
                self.root, self.client, armed["reply"], host="codex", session_id="unsafe-attempts"
            )
        self.assertFalse(any(name == "task-reconcile" for name, _ in self.client.calls))

    def test_unavailable_admin_spool_fails_closed_in_hook_and_cli(self):
        armed = self.arm_task()
        unavailable = self.adapter._artifactauthoritylib.AuthorityError("AUTHORITY_BUSY", "spool unavailable")
        with mock.patch.object(self.adapter._artifactauthoritylib, "_spool_root", side_effect=unavailable):
            notice = self.hook(armed["reply"])
        self.assertIn("Git admin reconciliation storage is unavailable or unsafe", notice)
        self.assertFalse(any(name == "task-reconcile" for name, _ in self.client.calls))

        cli = HERE.parent.parent / "core/pysrc/artifact-reconcile.py"
        with tempfile.TemporaryDirectory() as nongit:
            command = [sys.executable, str(cli), "--root", nongit, "--artifact-id", "PLAN-EXAMPLE", "--cancel-orphan"]
            result = subprocess.run(command, capture_output=True, text=True, check=False)
        self.assertEqual(result.returncode, 1)
        self.assertIn("Git admin reconciliation storage is unavailable or unsafe", result.stderr)
        self.assertNotIn("Traceback", result.stderr)

    def test_short_code_with_restated_state_reconciles_from_hook(self):
        armed = self.arm_task()
        self.assertEqual(armed["short_reply"], f"reconcile PENDING {armed['code']}")
        self.assertIn("reconciliation recorded", self.hook(f"  reconcile pending {armed['code'].lower()}."))
        source = next((self.root / ".codearbiter/.artifacts/authority-sources").glob("*.json"))
        self.assertEqual(json.loads(source.read_text(encoding="utf-8"))["source_text"], armed["reply"])

    def test_wrong_restated_state_or_extra_text_is_refused_visibly(self):
        armed = self.arm_task()
        before = list(self.client.calls)
        self.assertIn("PENDING", self.hook(f"reconcile BLOCKED {armed['code']}"))
        self.assertIn("send only the reply line", self.hook(armed["reply"] + " now"))
        self.assertEqual(self.hook("please continue"), "")
        self.assertEqual([n for n, _ in self.client.calls if n == "task-reconcile"],
                         [n for n, _ in before if n == "task-reconcile"])

    def test_documented_recovery_commands_are_directly_runnable(self):
        source = (HERE.parent.parent / "core/surface/includes/artifacts-attestation.md").read_text(encoding="utf-8")
        command = 'python "{{PLUGIN_ROOT}}/hooks/artifact-reconcile.py" --root "{{PROJECT_DIR}}" --artifact-id <plan-id>'
        self.assertIn(command + ' --cancel --prompt "<exact returned reply>"', source)
        self.assertIn(command + " --cancel-orphan", source)
        self.assertIn(command + " --recover", source)

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
        pending = self.adapter._pending_path(self.root, "PLAN-EXAMPLE")
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
                pending_path = self.adapter._pending_path(self.root, "PLAN-EXAMPLE")
                pending = json.loads(pending_path.read_text(encoding="utf-8"))
                pending[field] = value
                pending_path.write_text(json.dumps(pending), encoding="utf-8")
                with self.assertRaisesRegex(RuntimeError, "changed after arming"):
                    self.adapter.consume_reconciliation(
                        self.root, self.client, armed["reply"], host="codex", session_id="bound-session"
                    )

    def test_lost_response_retries_exact_mutation_without_new_capture(self):
        armed = self.adapter.arm_reconciliation(
            self.root, self.client, "PLAN-EXAMPLE", "T-001", "task-reconcile",
            target_state="PENDING", reason="Interrupted.", assessment="Reviewed.",
            token="retry-reconcile-token",
        )
        self.client.fail_after_reconciliation = True
        with self.assertRaisesRegex(OSError, "response lost"):
            self.adapter.consume_reconciliation(
                self.root, self.client, armed["reply"], host="codex", session_id="first-session"
            )
        captures = len([name for name, _ in self.client.calls if name == "capture-observation"])
        self.assertEqual(captures, 1)
        result = self.adapter.consume_reconciliation(
            self.root, self.client, armed["reply"], host="codex", session_id="second-session"
        )
        self.assertTrue(result["reconciled"])
        self.assertEqual(len(self.client.reconciled_requests), 1)
        self.assertEqual(len([name for name, _ in self.client.calls if name == "capture-observation"]), 1)

    def test_assistive_supersede_unanswered_reconciliation_without_approval_code(self):
        armed = self.arm_task()
        original = self.adapter._load(self.root, "PLAN-EXAMPLE")
        before = dict(self.client.identity)
        result = self.adapter.supersede_unanswered_reconciliation(
            self.root, "PLAN-EXAMPLE",
            reason="The user already authorized implementation; retire the redundant request.",
        )
        self.assertEqual(result["disposition"], "unanswered_prompt_superseded")
        self.assertTrue(result["superseded"])
        self.assertFalse(result["authority_granted"])
        self.assertFalse(result["mutation_attempted"])
        self.assertEqual(result["target_id"], "T-001")
        self.assertFalse(self.adapter._pending_path(self.root, "PLAN-EXAMPLE").exists())
        self.assertIsNone(self.routes.resolve("reconciliation", armed["reply"]))
        self.assertEqual(before, self.client.identity)
        self.assertFalse(any(name in {"task-reconcile", "capture-observation"}
                             for name, _ in self.client.calls))
        replacement = self.arm_task("after-supersession-token")
        self.assertNotEqual(armed["reply"], replacement["reply"])
        self.assertEqual(self.adapter._load(self.root, "PLAN-EXAMPLE")["operation"],
                         original["operation"])

    def test_assistive_supersession_validates_the_canonical_root(self):
        # macOS temporary roots commonly enter through the /var system alias.
        # The canonical physical directory must be checked, not rejected solely
        # because the host's system path prefix is an alias.  No pending
        # mutation is permitted and the request still needs its bound route.
        self.arm_task("canonical-root-supersede-token")
        original = self.adapter._artifactlib._trusted_directory
        inspected = []
        def verify(path, code):
            inspected.append(Path(path))
            return original(path, code)
        with mock.patch.object(self.adapter._artifactlib, "_trusted_directory", side_effect=verify):
            self.assertTrue(self.adapter.supersede_unanswered_reconciliation(
                self.root, "PLAN-EXAMPLE", reason="Retire unanswered prompt only.",
            )["superseded"])
        self.assertEqual(inspected, [self.root.resolve(strict=True)])
        self.assertFalse(self.adapter._pending_path(self.root, "PLAN-EXAMPLE").exists())

    def test_assistive_supersession_rejects_symlinked_selected_root(self):
        # A macOS parent directory alias is legitimate; the *repository root*
        # itself must not be a symlink to a different directory.
        armed = self.arm_task("symlink-root-token")
        linked = self.root.parent / (self.root.name + "-linked")
        try:
            linked.symlink_to(self.root, target_is_directory=True)
        except (NotImplementedError, OSError) as exc:
            self.skipTest(f"platform cannot create a symlink: {exc}")
        with self.assertRaisesRegex(RuntimeError, "root cannot be a linked"):
            self.adapter.supersede_unanswered_reconciliation(
                linked, "PLAN-EXAMPLE", reason="Only the canonical selected repo may retire this prompt.",
            )
        self.assertIsNotNone(self.adapter._load(self.root, "PLAN-EXAMPLE"))
        self.assertEqual(self.root.resolve(), self.routes.resolve("reconciliation", armed["reply"]))
        linked.unlink()

    def test_assistive_supersession_requires_a_bounded_reason_and_matching_id(self):
        self.arm_task()
        for reason in ("", "  ", "x" * 2049, 6, None):
            with self.subTest(reason=str(reason)[:30]):
                with self.assertRaisesRegex(RuntimeError, "nonblank supersession reason"):
                    self.adapter.supersede_unanswered_reconciliation(
                        self.root, "PLAN-EXAMPLE", reason=reason,
                    )
        with self.assertRaisesRegex(RuntimeError, "valid artifact"):
            self.adapter.supersede_unanswered_reconciliation(
                self.root, "../OTHER", reason="Retire the old request.",
            )
        self.assertTrue(self.adapter._pending_path(self.root, "PLAN-EXAMPLE").exists())
        self.assertIsNotNone(self.adapter._load(self.root, "PLAN-EXAMPLE"))

    def test_assistive_supersession_refuses_missing_or_different_route_binding(self):
        armed = self.arm_task()
        pending = self.adapter._load(self.root, "PLAN-EXAMPLE")
        self.routes.unregister(self.root, "reconciliation", "PLAN-EXAMPLE")
        with self.assertRaisesRegex(RuntimeError, "binding differ|route is unavailable"):
            self.adapter.supersede_unanswered_reconciliation(
                self.root, "PLAN-EXAMPLE", reason="Retire an idle request.",
            )
        self.assertEqual(self.adapter._load(self.root, "PLAN-EXAMPLE"), pending)
        self.routes.register(
            self.root, "reconciliation", "PLAN-EXAMPLE", "another unauthorized prompt",
            binding_sha256="f" * 64,
        )
        with self.assertRaisesRegex(RuntimeError, "binding differ"):
            self.adapter.supersede_unanswered_reconciliation(
                self.root, "PLAN-EXAMPLE", reason="Retire an idle request.",
            )
        self.assertEqual(self.adapter._load(self.root, "PLAN-EXAMPLE"), pending)
        self.assertIsNone(self.routes.resolve("reconciliation", armed["reply"]))

    def test_assistive_supersession_recovers_legacy_unanswered_marker_only(self):
        armed = self.arm_task()
        current = self.adapter._pending_path(self.root, "PLAN-EXAMPLE")
        legacy = self.root / self.adapter.LEGACY_PENDING_DIR / "PLAN-EXAMPLE.json"
        legacy.parent.mkdir(parents=True)
        current.rename(legacy)
        self.assertTrue(self.adapter.supersede_unanswered_reconciliation(
            self.root, "PLAN-EXAMPLE",
            reason="Historical confirmation prompt is not part of current progress.",
        )["superseded"])
        self.assertFalse(legacy.exists())
        self.assertIsNone(self.routes.resolve("reconciliation", armed["reply"]))
        self.assertEqual(self.client.identity["revision"], 3)

    def test_assistive_supersession_never_erases_in_flight_attempt(self):
        armed = self.arm_task()
        self.client.fail_after_reconciliation = True
        with self.assertRaisesRegex(OSError, "response lost"):
            self.adapter.consume_reconciliation(
                self.root, self.client, armed["reply"],
                host="codex", session_id="uncertain-after-submission",
            )
        pending = self.adapter._load(self.root, "PLAN-EXAMPLE")
        path = self.adapter._attempt_path(self.root, pending)
        self.assertTrue(path.is_file())
        with self.assertRaisesRegex(RuntimeError, "in-flight reconciliation"):
            self.adapter.supersede_unanswered_reconciliation(
                self.root, "PLAN-EXAMPLE", reason="No second approval ceremony.",
            )
        self.assertTrue(path.is_file())
        self.assertEqual(self.adapter._load(self.root, "PLAN-EXAMPLE"), pending)
        replay = self.adapter.recover_reconciliation(
            self.root, self.client, "PLAN-EXAMPLE",
        )
        self.assertTrue(replay["committed"])
        requests = [r for op, r in self.client.calls if op == "task-reconcile"]
        self.assertEqual(requests[0], requests[1])

    def test_assistive_supersession_does_not_hide_dual_marker_ambiguity(self):
        self.arm_task()
        pending = self.adapter._pending_path(self.root, "PLAN-EXAMPLE")
        legacy = self.root / self.adapter.LEGACY_PENDING_DIR / "PLAN-EXAMPLE.json"
        legacy.parent.mkdir(parents=True)
        legacy.write_bytes(pending.read_bytes())
        with self.assertRaisesRegex(RuntimeError, "ambiguous reconciliation state"):
            self.adapter.supersede_unanswered_reconciliation(
                self.root, "PLAN-EXAMPLE", reason="Retire unanswered marker.",
            )
        self.assertTrue(legacy.exists())
        self.assertTrue(pending.exists())

    def test_assistive_supersession_cli_is_code_free_and_refuses_mixed_actions(self):
        armed = self.arm_task("supersede-cli-token")
        specification = importlib.util.spec_from_file_location(
            "artifact_reconcile_supersede_cli",
            HERE.parent.parent / "core/pysrc/artifact-reconcile.py",
        )
        cli = importlib.util.module_from_spec(specification)
        specification.loader.exec_module(cli)
        base = ["--root", str(self.root), "--artifact-id", "PLAN-EXAMPLE"]
        for extra in (
            ["--supersede"],
            ["--supersede", "--reason", " "],
            ["--supersede", "--reason", "Retire.", "--cancel"],
            ["--supersede", "--reason", "Retire.", "--recover"],
            ["--supersede", "--reason", "Retire.", "--cancel-orphan"],
            ["--supersede", "--reason", "Retire.", "--prompt", armed["reply"]],
            ["--supersede", "--reason", "Retire.", "--target-id", "T-001"],
            ["--supersede", "--reason", "Retire.", "--operation", "task-reconcile"],
        ):
            with self.subTest(extra=extra), redirect_stderr(io.StringIO()):
                with self.assertRaises(SystemExit) as caught:
                    cli.main(base + extra)
                self.assertEqual(caught.exception.code, 2)
        self.assertIsNotNone(self.adapter._load(self.root, "PLAN-EXAMPLE"))
        with redirect_stdout(io.StringIO()) as output:
            self.assertEqual(cli.main(base + [
                "--supersede", "--reason",
                "Resume existing authorized work without requiring a new code.",
            ]), 0)
        result = json.loads(output.getvalue())
        self.assertEqual(result["disposition"], "unanswered_prompt_superseded")
        self.assertFalse(result["authority_granted"])
        self.assertNotIn("reply", result)
        self.assertIsNone(self.routes.resolve("reconciliation", armed["reply"]))
        self.assertFalse(any(name in {"task-reconcile", "capture-observation"}
                             for name, _ in self.client.calls))

    def test_pending_request_can_be_cancelled_and_rearmed_before_mutation(self):
        armed = self.adapter.arm_reconciliation(
            self.root, self.client, "PLAN-EXAMPLE", "T-001", "task-reconcile",
            target_state="PENDING", reason="Interrupted.", assessment="Reviewed.",
            token="cancel-reconcile-token",
        )
        self.adapter.cancel_reconciliation(self.root, "PLAN-EXAMPLE", armed["reply"])
        replacement = self.adapter.arm_reconciliation(
            self.root, self.client, "PLAN-EXAMPLE", "T-001", "task-reconcile",
            target_state="BLOCKED", reason="New assessment.", assessment="Reassessed.",
            token="replacement-token",
        )
        self.assertIsNone(self.routes.resolve("reconciliation", armed["reply"]))
        self.assertEqual(self.root.resolve(), self.routes.resolve("reconciliation", replacement["reply"]))

    def test_uncertain_mutation_cannot_be_cancelled(self):
        armed = self.adapter.arm_reconciliation(
            self.root, self.client, "PLAN-EXAMPLE", "T-001", "task-reconcile",
            target_state="PENDING", reason="Interrupted.", assessment="Reviewed.",
            token="uncertain-reconcile-token",
        )
        self.client.fail_after_reconciliation = True
        with self.assertRaisesRegex(OSError, "response lost"):
            self.adapter.consume_reconciliation(
                self.root, self.client, armed["reply"], host="codex", session_id="session-1"
            )
        with self.assertRaisesRegex(RuntimeError, "in-flight"):
            self.adapter.cancel_reconciliation(self.root, "PLAN-EXAMPLE", armed["reply"])

    def test_recovery_clears_only_a_proven_uncommitted_attempt(self):
        armed = self.adapter.arm_reconciliation(
            self.root, self.client, "PLAN-EXAMPLE", "T-001", "task-reconcile",
            target_state="PENDING", reason="Interrupted.", assessment="Reviewed.",
            token="failed-reconcile-token",
        )
        self.client.reconciliation_failure_code = "REVISION_CONFLICT"
        with self.assertRaisesRegex(RuntimeError, "REVISION_CONFLICT"):
            self.adapter.consume_reconciliation(
                self.root, self.client, armed["reply"], host="codex", session_id="first-session"
            )
        pending = self.adapter._load(self.root, "PLAN-EXAMPLE")
        self.assertTrue((self.adapter._attempt_path(self.root, pending)).exists())
        result = self.adapter.recover_reconciliation(self.root, self.client, "PLAN-EXAMPLE")
        self.assertFalse(result["committed"])
        self.assertFalse((self.adapter._pending_path(self.root, "PLAN-EXAMPLE")).exists())
        self.assertFalse((self.adapter._attempt_path(self.root, pending)).exists())
        self.assertIsNone(self.routes.resolve("reconciliation", armed["reply"]))
        self.assertEqual(len([name for name, _ in self.client.calls if name == "capture-observation"]), 1)
        self.adapter.arm_reconciliation(
            self.root, self.client, "PLAN-EXAMPLE", "T-001", "task-reconcile",
            target_state="BLOCKED", reason="Reassessed.", assessment="Reviewed again.",
            token="replacement-reconcile-token",
        )

    def test_recovery_accepts_committed_replay_after_lost_response(self):
        armed = self.adapter.arm_reconciliation(
            self.root, self.client, "PLAN-EXAMPLE", "T-001", "task-reconcile",
            target_state="PENDING", reason="Interrupted.", assessment="Reviewed.",
            token="lost-recovery-token",
        )
        self.client.fail_after_reconciliation = True
        with self.assertRaisesRegex(OSError, "response lost"):
            self.adapter.consume_reconciliation(
                self.root, self.client, armed["reply"], host="codex", session_id="first-session"
            )
        result = self.adapter.recover_reconciliation(self.root, self.client, "PLAN-EXAMPLE")
        self.assertTrue(result["committed"])
        self.assertEqual(result["revision"], 4)
        self.assertEqual(len(self.client.reconciled_requests), 1)
        self.assertEqual(len([name for name, _ in self.client.calls if name == "capture-observation"]), 1)
        self.assertFalse((self.adapter._pending_path(self.root, "PLAN-EXAMPLE")).exists())

    def test_scope_recovery_replays_after_prompt_route_is_lost(self):
        self.client.record = {"id": "CP-01", "title": "Scope", "tasks": ["T-001"]}
        armed = self.adapter.arm_reconciliation(
            self.root, self.client, "PLAN-EXAMPLE", "CP-01", "scope-reconcile",
            assessment="Reviewed scope baseline.", token="orphaned-scope-token",
        )
        self.client.fail_after_reconciliation = True
        with self.assertRaisesRegex(OSError, "response lost"):
            self.adapter.consume_reconciliation(
                self.root, self.client, armed["reply"], host="codex", session_id="first-session"
            )
        pending = self.adapter._load(self.root, "PLAN-EXAMPLE")
        self.routes.unregister(self.root, "reconciliation", "PLAN-EXAMPLE")
        result = self.adapter.recover_reconciliation(self.root, self.client, "PLAN-EXAMPLE")
        self.assertTrue(result["committed"])
        mutations = [request for name, request in self.client.calls if name == "scope-reconcile"]
        self.assertEqual(len(mutations), 2)
        self.assertEqual(mutations[0], mutations[1])
        self.assertEqual(len(self.client.reconciled_requests), 1)
        self.assertEqual(len([name for name, _ in self.client.calls if name == "capture-observation"]), 1)
        self.assertFalse((self.adapter._pending_path(self.root, "PLAN-EXAMPLE")).exists())
        self.assertFalse((self.adapter._attempt_path(self.root, pending)).exists())

    def test_recovery_preserves_attempt_on_unclassified_engine_error(self):
        armed = self.adapter.arm_reconciliation(
            self.root, self.client, "PLAN-EXAMPLE", "T-001", "task-reconcile",
            target_state="PENDING", reason="Interrupted.", assessment="Reviewed.",
            token="unknown-recovery-token",
        )
        self.client.reconciliation_failure_code = "RECOVERY_REQUIRED"
        with self.assertRaisesRegex(RuntimeError, "RECOVERY_REQUIRED"):
            self.adapter.consume_reconciliation(
                self.root, self.client, armed["reply"], host="codex", session_id="first-session"
            )
        pending = self.adapter._load(self.root, "PLAN-EXAMPLE")
        with self.assertRaisesRegex(RuntimeError, "RECOVERY_REQUIRED"):
            self.adapter.recover_reconciliation(self.root, self.client, "PLAN-EXAMPLE")
        self.assertTrue((self.adapter._pending_path(self.root, "PLAN-EXAMPLE")).exists())
        self.assertTrue((self.adapter._attempt_path(self.root, pending)).exists())

    def test_recovery_preserves_attempt_on_malformed_success_response(self):
        armed = self.adapter.arm_reconciliation(
            self.root, self.client, "PLAN-EXAMPLE", "T-001", "task-reconcile",
            target_state="PENDING", reason="Interrupted.", assessment="Reviewed.",
            token="malformed-recovery-token",
        )
        self.client.reconciliation_failure_code = "REVISION_CONFLICT"
        with self.assertRaisesRegex(RuntimeError, "REVISION_CONFLICT"):
            self.adapter.consume_reconciliation(
                self.root, self.client, armed["reply"], host="codex", session_id="first-session"
            )
        pending = self.adapter._load(self.root, "PLAN-EXAMPLE")
        for response in (
            None,
            {"revision": 4},
            {"revision": 4, "transaction": {"operation_id": "wrong-operation", "state": "committed"}},
            {"revision": 4, "transaction": {"operation_id": self.adapter._operation_id(pending), "state": "rolled_back"}},
        ):
            with self.subTest(response=response):
                with mock.patch.object(self.client, "call", return_value=response):
                    with self.assertRaisesRegex(RuntimeError, "malformed"):
                        self.adapter.recover_reconciliation(self.root, self.client, "PLAN-EXAMPLE")
                self.assertTrue((self.adapter._pending_path(self.root, "PLAN-EXAMPLE")).exists())
                self.assertTrue((self.adapter._attempt_path(self.root, pending)).exists())

    def test_recovery_rejects_armed_request_without_attempt(self):
        armed = self.adapter.arm_reconciliation(
            self.root, self.client, "PLAN-EXAMPLE", "T-001", "task-reconcile",
            target_state="PENDING", reason="Interrupted.", assessment="Reviewed.",
            token="unattempted-recovery-token",
        )
        with self.assertRaisesRegex(RuntimeError, "no in-flight"):
            self.adapter.recover_reconciliation(self.root, self.client, "PLAN-EXAMPLE")
        self.assertEqual(self.root.resolve(), self.routes.resolve("reconciliation", armed["reply"]))

    def test_recovery_cli_replays_the_exact_stored_request(self):
        armed = self.adapter.arm_reconciliation(
            self.root, self.client, "PLAN-EXAMPLE", "T-001", "task-reconcile",
            target_state="PENDING", reason="Interrupted.", assessment="Reviewed.",
            token="cli-recovery-token",
        )
        self.client.reconciliation_failure_code = "OPERATION_ROLLED_BACK"
        with self.assertRaisesRegex(RuntimeError, "OPERATION_ROLLED_BACK"):
            self.adapter.consume_reconciliation(
                self.root, self.client, armed["reply"], host="codex", session_id="first-session"
            )
        specification = importlib.util.spec_from_file_location(
            "artifact_reconcile_recovery_cli", HERE.parent.parent / "core/pysrc/artifact-reconcile.py"
        )
        cli = importlib.util.module_from_spec(specification)
        specification.loader.exec_module(cli)
        with mock.patch.object(cli._artifactlib, "ArtifactClient", return_value=self.client):
            with redirect_stdout(io.StringIO()) as output:
                self.assertEqual(cli.main([
                    "--root", str(self.root), "--artifact-id", "PLAN-EXAMPLE", "--recover",
                ]), 0)
        self.assertFalse(json.loads(output.getvalue())["committed"])
        mutations = [request for name, request in self.client.calls if name == "task-reconcile"]
        self.assertEqual(len(mutations), 2)
        self.assertEqual(mutations[0], mutations[1])
        self.assertEqual(len([name for name, _ in self.client.calls if name == "capture-observation"]), 1)

    def test_recovery_cli_rejects_cancellation_and_arming_fields(self):
        self.adapter.arm_reconciliation(
            self.root, self.client, "PLAN-EXAMPLE", "T-001", "task-reconcile",
            target_state="PENDING", reason="Interrupted.", assessment="Reviewed.",
            token="reject-mixed-recovery-token",
        )
        specification = importlib.util.spec_from_file_location(
            "artifact_reconcile_recovery_args", HERE.parent.parent / "core/pysrc/artifact-reconcile.py"
        )
        cli = importlib.util.module_from_spec(specification)
        specification.loader.exec_module(cli)
        for extra in (
            ["--cancel", "--prompt", "arbitrary"],
            ["--cancel-orphan"],
            ["--target-id", "T-001"],
            ["--operation", "task-reconcile"],
        ):
            with self.subTest(extra=extra), redirect_stderr(io.StringIO()):
                with self.assertRaises(SystemExit) as exit_status:
                    cli.main(["--root", str(self.root), "--artifact-id", "PLAN-EXAMPLE", "--recover", *extra])
                self.assertEqual(exit_status.exception.code, 2)
        self.assertTrue((self.adapter._pending_path(self.root, "PLAN-EXAMPLE")).exists())

    def test_failed_attempt_publication_leaves_no_partial_record_and_can_cancel(self):
        armed = self.adapter.arm_reconciliation(
            self.root, self.client, "PLAN-EXAMPLE", "T-001", "task-reconcile",
            target_state="PENDING", reason="Interrupted.", assessment="Reviewed.",
            token="atomic-attempt-token",
        )
        with mock.patch.object(
            self.adapter._artifactauthoritylib, "capture_user_prompt",
            return_value={"receipt": ".codearbiter/.artifacts/receipts/" + "4" * 64 + ".json"},
        ):
            with mock.patch("os.link", side_effect=OSError("link unavailable")):
                with self.assertRaisesRegex(OSError, "link unavailable"):
                    self.adapter.consume_reconciliation(
                        self.root, self.client, armed["reply"], host="codex", session_id="session-1"
                    )
        pending = self.adapter._load(self.root, "PLAN-EXAMPLE")
        self.assertFalse((self.adapter._attempt_path(self.root, pending)).exists())
        self.assertTrue(self.adapter.cancel_reconciliation(self.root, "PLAN-EXAMPLE", armed["reply"])["cancelled"])

    def test_cancel_cannot_revoke_a_concurrently_dispatched_mutation(self):
        armed = self.adapter.arm_reconciliation(
            self.root, self.client, "PLAN-EXAMPLE", "T-001", "task-reconcile",
            target_state="PENDING", reason="Interrupted.", assessment="Reviewed.",
            token="concurrent-reconcile-token",
        )
        captured = threading.Event()
        release = threading.Event()
        cancel_started = threading.Event()
        cancel_done = threading.Event()
        outcomes = {}

        def capture(*_args, **_kwargs):
            captured.set()
            if not release.wait(5):
                raise AssertionError("test capture was never released")
            return {"receipt": ".codearbiter/.artifacts/receipts/" + "4" * 64 + ".json"}

        def consume():
            try:
                outcomes["consume"] = self.adapter.consume_reconciliation(
                    self.root, self.client, armed["reply"], host="codex", session_id="session-1"
                )
            except Exception as exc:
                outcomes["consume_error"] = exc

        def cancel():
            cancel_started.set()
            try:
                outcomes["cancel"] = self.adapter.cancel_reconciliation(
                    self.root, "PLAN-EXAMPLE", armed["reply"]
                )
            except Exception as exc:
                outcomes["cancel_error"] = exc
            finally:
                cancel_done.set()

        with mock.patch.object(self.adapter._artifactauthoritylib, "capture_user_prompt", side_effect=capture):
            consumer = threading.Thread(target=consume)
            canceller = threading.Thread(target=cancel)
            consumer.start()
            self.assertTrue(captured.wait(5))
            canceller.start()
            self.assertTrue(cancel_started.wait(5))
            self.assertFalse(cancel_done.wait(0.1), "cancellation overtook mutation dispatch")
            release.set()
            consumer.join(5)
            canceller.join(5)
        self.assertFalse(consumer.is_alive())
        self.assertFalse(canceller.is_alive())
        self.assertTrue(outcomes["consume"]["reconciled"])
        self.assertNotIn("cancel", outcomes)
        self.assertIsInstance(outcomes.get("cancel_error"), RuntimeError)

    def test_orphaned_pending_request_can_be_cancelled_without_a_route(self):
        armed = self.adapter.arm_reconciliation(
            self.root, self.client, "PLAN-EXAMPLE", "T-001", "task-reconcile",
            target_state="PENDING", reason="Interrupted.", assessment="Reviewed.",
            token="orphan-reconcile-token",
        )
        self.routes.unregister(self.root, "reconciliation", "PLAN-EXAMPLE")
        self.assertIsNone(self.routes.resolve("reconciliation", armed["reply"]))
        specification = importlib.util.spec_from_file_location(
            "artifact_reconcile_orphan_cli", HERE.parent.parent / "core/pysrc/artifact-reconcile.py"
        )
        cli = importlib.util.module_from_spec(specification)
        specification.loader.exec_module(cli)
        with redirect_stdout(io.StringIO()) as output:
            self.assertEqual(cli.main([
                "--root", str(self.root), "--artifact-id", "PLAN-EXAMPLE", "--cancel-orphan",
            ]), 0)
        self.assertTrue(json.loads(output.getvalue())["cancelled"])
        replacement = self.adapter.arm_reconciliation(
            self.root, self.client, "PLAN-EXAMPLE", "T-001", "task-reconcile",
            target_state="BLOCKED", reason="Reassessed.", assessment="Fresh review.",
            token="replacement-orphan-token",
        )
        self.assertEqual(self.root.resolve(), self.routes.resolve("reconciliation", replacement["reply"]))

    def test_failed_pending_publication_leaves_no_final_marker(self):
        with mock.patch("os.link", side_effect=OSError("pending link unavailable")):
            with self.assertRaisesRegex(OSError, "pending link unavailable"):
                self.adapter.arm_reconciliation(
                    self.root, self.client, "PLAN-EXAMPLE", "T-001", "task-reconcile",
                    target_state="PENDING", reason="Interrupted.", assessment="Reviewed.",
                    token="pending-atomic-token",
                )
        self.assertFalse((self.adapter._pending_path(self.root, "PLAN-EXAMPLE")).exists())

    def test_cancel_cli_requires_exact_prompt_and_rejects_arming_fields(self):
        armed = self.adapter.arm_reconciliation(
            self.root, self.client, "PLAN-EXAMPLE", "T-001", "task-reconcile",
            target_state="PENDING", reason="Interrupted.", assessment="Reviewed.",
            token="cli-cancel-token",
        )
        specification = importlib.util.spec_from_file_location(
            "artifact_reconcile_cli", HERE.parent.parent / "core/pysrc/artifact-reconcile.py"
        )
        cli = importlib.util.module_from_spec(specification)
        specification.loader.exec_module(cli)
        with redirect_stderr(io.StringIO()):
            with self.assertRaises(SystemExit) as exit_status:
                cli.main([
                    "--root", str(self.root), "--artifact-id", "PLAN-EXAMPLE",
                    "--cancel", "--prompt", armed["reply"], "--target-id", "T-001",
                ])
        self.assertEqual(exit_status.exception.code, 2)
        with redirect_stdout(io.StringIO()) as output:
            self.assertEqual(cli.main([
                "--root", str(self.root), "--artifact-id", "PLAN-EXAMPLE",
                "--cancel", "--prompt", armed["reply"],
            ]), 0)
        self.assertTrue(json.loads(output.getvalue())["cancelled"])


class NativeReconciliationTest(unittest.TestCase):
    """Disposable real-engine fixtures; their receipts confer no live authority."""

    @classmethod
    def setUpClass(cls):
        from test_artifact_authoring import build_installation
        cls.installation_owner, cls.installation = build_installation()

    @classmethod
    def tearDownClass(cls):
        if cls.installation_owner is not None:
            cls.installation_owner.cleanup()

    def setUp(self):
        from test_artifact_authoring import physical_test_directory, WorkflowHarness
        self.temp = tempfile.TemporaryDirectory(prefix="ca-reconciliation-native-")
        self.addCleanup(self.temp.cleanup)
        self.root = physical_test_directory(self.temp.name) / "repo"
        self.root.mkdir()
        subprocess.run(["git", "init", "-q", str(self.root)], check=True)
        (self.root / "src").mkdir()
        (self.root / "src/config.py").write_text("original\n", encoding="utf-8")
        self.workflow = WorkflowHarness(self.root, self.installation)
        self.client = self.workflow.client
        self.adapter = importlib.import_module("_reconciliationlib")
        for module_name in ("_artifactpromptlib", "_replylib"):
            module = importlib.import_module(module_name)
            self.addCleanup(setattr, module, "REGISTRY_PARENT", module.REGISTRY_PARENT)
            module.REGISTRY_PARENT = self.root.parent

    def create_plan(self, task_text="The task\u2019s named test passes.", scope_text="Complete implementation"):
        from test_artifact_authoring import plan_normative
        spec = self.workflow.create_spec()
        plan = plan_normative("SPEC-FLOW", spec["normative_sha256"])
        plan["tasks"][0]["done_when"] = [task_text]
        plan["checkpoints"][0]["title"] = scope_text
        self.client.call("create", {
            "operation_id": self.workflow.operation_id("create-plan"),
            "artifact_id": "PLAN-FLOW", "kind": "plan", "slug": "flow",
            "title": plan["title"], "summary": plan["summary"],
            "spec_id": "SPEC-FLOW", "normative": plan,
        })
        self.workflow.approve_pair()
        self.workflow.mutate(
            "task-start", "PLAN-FLOW", task="T-001",
            context_ticket=self.workflow.context_ticket("T-001"),
        )

    def arm_task(self):
        return self.adapter.arm_reconciliation(
            self.root, self.client, "PLAN-FLOW", "T-001", "task-reconcile",
            target_state="PENDING", reason="Interrupted synthetic verifier.",
            assessment="The fixture task has no established completion.",
            token="native-reconciliation-fixture",
        )

    def consume(self, reply):
        return self.adapter.consume_reconciliation(
            self.root, self.client, reply, host="codex", session_id="synthetic-native-fixture",
        )

    def captured_event_and_context(self):
        events = [
            json.loads(path.read_bytes())
            for path in (self.root / ".codearbiter/.artifacts/authority-sources").glob("*.json")
        ]
        event, = [item for item in events if item["kind"] == "reconciliation"]
        observation = json.loads((self.root / event["observation_ref"]).read_bytes())
        context = json.loads((self.root / observation["context_ref"]).read_bytes())
        return event, context

    def assert_native_task_reconciled(self, reply):
        result = self.consume(reply)
        self.assertTrue(result["reconciled"])
        self.assertTrue((self.root / result["receipt"]).is_file())
        event, context = self.captured_event_and_context()
        self.assertEqual(event["source_text"], reply)
        self.assertEqual(event["payload"]["task_sha256"], context["record_sha256"])
        self.assertEqual(self.client.call("eligible", {
            "artifact_id": "PLAN-FLOW",
        })["tasks"][0]["state"], "PENDING")

    def test_unicode_task_reconciliation_uses_engine_record_hash(self):
        self.create_plan()
        armed = self.arm_task()
        self.assert_native_task_reconciled(armed["reply"])

    def test_unicode_task_consumes_unchanged_legacy_ascii_pending_binding(self):
        self.create_plan()
        identity, snapshot, record = self.adapter._current(self.client, "PLAN-FLOW", "T-001")
        reply = "reconcile-task PLAN-FLOW T-001 PENDING legacy-native-fixture"
        canonical = lambda value: json.dumps(
            value, ensure_ascii=True, sort_keys=True, separators=(",", ":"),
        ).encode("utf-8")
        pending = {
            "format": "codearbiter.pending-reconciliation/0.1.0",
            "operation": "task-reconcile", "artifact_id": "PLAN-FLOW", "target_id": "T-001",
            "target_state": "PENDING", "reason": "Interrupted legacy fixture.",
            "assessment": "No established fixture completion.", "identity": identity,
            "input_sha256": snapshot["sha256"], "record": record,
            "record_sha256": hashlib.sha256(canonical(record)).hexdigest(),
            "prompt_sha256": hashlib.sha256(reply.encode()).hexdigest(),
        }
        raw = canonical(pending)
        path = self.adapter._pending_path(self.root, "PLAN-FLOW")
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(raw)
        binding = hashlib.sha256(raw).hexdigest()
        self.adapter._artifactpromptlib.register(
            self.root, "reconciliation", "PLAN-FLOW", reply, binding_sha256=binding,
        )
        self.assertIn(b"\\u2019", raw)
        self.assertEqual(self.adapter._load(self.root, "PLAN-FLOW"), pending)
        capture = self.adapter._artifactauthoritylib.capture_user_prompt

        def inspect_legacy_binding(*args, **kwargs):
            self.assertEqual(path.read_bytes(), raw)
            self.assertEqual(self.adapter._artifactpromptlib.binding(
                self.root, "reconciliation", "PLAN-FLOW",
            ), binding)
            return capture(*args, **kwargs)

        with mock.patch.object(
            self.adapter._artifactauthoritylib, "capture_user_prompt", side_effect=inspect_legacy_binding,
        ):
            self.assert_native_task_reconciled(reply)

    def test_unicode_task_marker_serialization_remains_ascii_canonical(self):
        self.create_plan()
        armed = self.arm_task()
        pending = self.adapter._load(self.root, "PLAN-FLOW")
        raw = self.adapter._pending_path(self.root, "PLAN-FLOW").read_bytes()
        canonical = lambda value: json.dumps(
            value, ensure_ascii=True, sort_keys=True, separators=(",", ":"),
        ).encode("utf-8")
        self.assertIn(b"\\u2019", raw)
        self.assertEqual(raw, canonical(pending))
        self.assertEqual(pending["record_sha256"], hashlib.sha256(canonical(pending["record"])).hexdigest())
        self.assertEqual(self.adapter._artifactpromptlib.binding(
            self.root, "reconciliation", "PLAN-FLOW",
        ), hashlib.sha256(raw).hexdigest())
        self.assertEqual(self.adapter._artifactpromptlib.resolve("reconciliation", armed["reply"]), self.root)

    def test_ascii_task_reconciliation_uses_native_capture(self):
        self.create_plan(task_text="The task's named test passes.")
        self.assert_native_task_reconciled(self.arm_task()["reply"])

    def test_unicode_scope_reconciliation_uses_native_capture_without_task_hash(self):
        self.create_plan(task_text="The task's named test passes.", scope_text="Scope\u2019s baseline")
        armed = self.adapter.arm_reconciliation(
            self.root, self.client, "PLAN-FLOW", "CP-01", "scope-reconcile",
            assessment="The synthetic scope baseline was inspected.", token="native-scope-fixture",
        )
        result = self.consume(armed["reply"])
        self.assertTrue(result["reconciled"])
        self.assertTrue((self.root / result["receipt"]).is_file())
        event, context = self.captured_event_and_context()
        self.assertEqual(context["record"]["title"], "Scope\u2019s baseline")
        self.assertNotIn("task_sha256", event["payload"])

    def test_unicode_task_input_drift_is_refused_before_native_capture(self):
        self.create_plan()
        armed = self.arm_task()
        (self.root / "src/config.py").write_text("changed\n", encoding="utf-8")
        with self.assertRaisesRegex(RuntimeError, "target changed after arming"):
            self.consume(armed["reply"])
        self.assertFalse(any(item["kind"] == "reconciliation" for item in (
            json.loads(path.read_bytes())
            for path in (self.root / ".codearbiter/.artifacts/authority-sources").glob("*.json")
        )))

    def test_unicode_task_record_drift_is_refused_before_native_capture(self):
        self.create_plan()
        armed = self.arm_task()
        call = self.client.call

        def changed_record(operation, request=None, **kwargs):
            result = call(operation, request, **kwargs)
            if operation == "read":
                result["record"]["done_when"] = ["Changed fixture contract."]
            return result

        with mock.patch.object(self.client, "call", side_effect=changed_record):
            with self.assertRaisesRegex(RuntimeError, "target changed after arming"):
                self.consume(armed["reply"])

    def test_unicode_task_prompt_drift_preserves_pending_and_route(self):
        self.create_plan()
        armed = self.arm_task()
        path = self.adapter._pending_path(self.root, "PLAN-FLOW")
        raw = path.read_bytes()
        self.assertFalse(self.consume(armed["reply"] + "x")["reconciled"])
        self.assertEqual(path.read_bytes(), raw)
        self.assertEqual(self.adapter._artifactpromptlib.resolve("reconciliation", armed["reply"]), self.root)


if __name__ == "__main__":
    unittest.main()
