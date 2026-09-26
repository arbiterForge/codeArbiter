#!/usr/bin/env python3
"""Regression tests for exact-prompt task/scope reconciliation authority."""

import importlib
import importlib.util
import hashlib
import io
import json
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


class ReconciliationTest(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        (self.root / ".codearbiter").mkdir()
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
        source = (HERE.parent.parent / "core/surface/includes/artifacts.md").read_text(encoding="utf-8")
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
        self.assertTrue((self.root / self.adapter._attempt(pending)).exists())
        result = self.adapter.recover_reconciliation(self.root, self.client, "PLAN-EXAMPLE")
        self.assertFalse(result["committed"])
        self.assertFalse((self.root / self.adapter._pending("PLAN-EXAMPLE")).exists())
        self.assertFalse((self.root / self.adapter._attempt(pending)).exists())
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
        self.assertFalse((self.root / self.adapter._pending("PLAN-EXAMPLE")).exists())

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
        self.assertFalse((self.root / self.adapter._pending("PLAN-EXAMPLE")).exists())
        self.assertFalse((self.root / self.adapter._attempt(pending)).exists())

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
        self.assertTrue((self.root / self.adapter._pending("PLAN-EXAMPLE")).exists())
        self.assertTrue((self.root / self.adapter._attempt(pending)).exists())

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
                self.assertTrue((self.root / self.adapter._pending("PLAN-EXAMPLE")).exists())
                self.assertTrue((self.root / self.adapter._attempt(pending)).exists())

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
        self.assertTrue((self.root / self.adapter._pending("PLAN-EXAMPLE")).exists())

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
        self.assertFalse((self.root / self.adapter._attempt(pending)).exists())
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
        self.assertFalse((self.root / self.adapter._pending("PLAN-EXAMPLE")).exists())

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


if __name__ == "__main__":
    unittest.main()
