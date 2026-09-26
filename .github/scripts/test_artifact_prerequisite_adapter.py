#!/usr/bin/env python3
"""Regression tests for host-owned structured-artifact prerequisite capture."""

import importlib.util
import hashlib
import json
import os
import stat
import subprocess
import sys
import tempfile
import time
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest import mock

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
    def __init__(self, root, artifact_id="PLAN-EXAMPLE"):
        self.root = root
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
        if operation == "evidence-context":
            context = {
                "format": "codearbiter.evidence-context/0.1.0", "activity": "prerequisite",
                "subject": {"artifact_id": self.identity["artifact_id"], "normative_sha256": self.identity["normative_sha256"], "record_id": request["record_id"]},
                "input_sha256": "9" * 64, "prompt_sha256": request["prompt_sha256"],
                "record": dict(self.record),
            }
            packed = lambda value: json.dumps(value, ensure_ascii=True, sort_keys=True, separators=(",", ":")).encode()
            context["record_sha256"] = hashlib.sha256(packed(context["record"])).hexdigest()
            raw = packed(context)
            digest = hashlib.sha256(raw).hexdigest()
            relative = Path(".codearbiter/.artifacts/evidence-contexts") / f"{digest}.json"
            target = self.root / relative
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(raw)
            return {"context_ref": relative.as_posix(), "context_sha256": digest}
        if operation == "capture-observation":
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
        self.client = _FakeClient(self.root)

    def tearDown(self):
        self.temp.cleanup()

    def hook_fixture(self):
        routes = importlib.import_module("_artifactpromptlib")
        replies = importlib.import_module("_replylib")
        for module in (routes, replies):
            self.addCleanup(setattr, module, "REGISTRY_PARENT", module.REGISTRY_PARENT)
            module.REGISTRY_PARENT = self.root
        self.adapter._artifactpromptlib = routes
        self.adapter._replylib = replies
        return replies

    def hook(self, prompt):
        with mock.patch.object(self.adapter._artifactlib, "ArtifactClient", return_value=self.client):
            return self.adapter.consume_from_hook(
                root=self.root, plugin_root=self.root, prompt=prompt,
                host="claude", session_id="session-lenient",
            )

    def test_short_code_and_padding_from_hook_satisfy_the_prerequisite(self):
        replies = self.hook_fixture()
        armed = self.arm(now=int(time.time()))
        self.assertEqual(armed["short_reply"], f"satisfy-prerequisite {armed['code']}")
        self.assertIn("workflow prerequisite recorded", self.hook(f"\u00a0Satisfy-Prerequisite {armed['code'].lower()}.\n"))
        source = next((self.root / ".codearbiter/.artifacts/authority-sources").glob("*.json"))
        self.assertEqual(json.loads(source.read_text(encoding="utf-8"))["source_text"], armed["reply"])
        self.assertIn("matches no armed request", replies.expand(armed["short_reply"])["notice"])

    def test_hook_misses_are_visible_and_confer_nothing(self):
        self.hook_fixture()
        armed = self.arm(now=int(time.time()))
        before = list(self.client.calls)
        self.assertIn("matches no armed request", self.hook("satisfy-prerequisite ZZZZ"))
        self.assertIn("belongs to PLAN-EXAMPLE GATE-APPROVAL",
                      self.hook(f"satisfy-prerequisite PLAN-OTHER GATE-APPROVAL {armed['code']}"))
        self.assertIn("Send only the reply line", self.hook(armed["reply"] + " please"))
        self.assertEqual(self.hook("yes"), "")
        self.assertEqual(self.client.calls, before)

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
            ["capture-observation", "prerequisite"],
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
                client = _FakeClient(self.root, f"PLAN-NONCE-{length}")
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
                client = _FakeClient(self.root, "PLAN-INVALID-NONCE")
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
        other = _FakeClient(self.root, "PLAN-OTHER")
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

    def hold_transition_lock(self):
        code = """
import sys
from pathlib import Path
sys.path.insert(0, sys.argv[1])
import _prerequisitelib
with _prerequisitelib._pending_transition_lock(Path(sys.argv[2]), sys.argv[3]):
    print("READY", flush=True)
    sys.stdin.read(1)
"""
        process = subprocess.Popen(
            [sys.executable, "-c", code, str(CORE_PYSRC), str(self.root), "PLAN-EXAMPLE"],
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
        )

        def stop_process():
            if process.poll() is None:
                process.kill()
                process.wait(timeout=5)

        self.addCleanup(stop_process)
        ready = process.stdout.readline().strip()
        if ready != "READY":
            stderr = process.stderr.read()
            self.fail(f"lock holder failed before readiness: {ready!r} {stderr!r}")
        return process

    def release_transition_lock(self, process):
        process.stdin.write("x")
        process.stdin.flush()
        process.stdin.close()
        returncode = process.wait(timeout=5)
        stderr = process.stderr.read()
        process.stdout.close()
        process.stderr.close()
        self.assertEqual(returncode, 0, stderr)

    def test_transition_lock_key_uses_filesystem_identity_for_case_aliases(self):
        identity = SimpleNamespace(st_dev=41, st_ino=73)
        with mock.patch.object(self.adapter.os, "stat", return_value=identity):
            mixed_case = self.adapter._repository_lock_key(Path("/Users/example/Repo"))
            lower_case = self.adapter._repository_lock_key(Path("/Users/example/repo"))

        self.assertEqual(mixed_case, lower_case)
        self.assertEqual(mixed_case, b"stat:41:73")

    def test_transition_lock_root_is_per_user_real_and_private(self):
        with tempfile.TemporaryDirectory() as temporary:
            with mock.patch.object(
                self.adapter.tempfile, "gettempdir", return_value=temporary
            ):
                lock_root = self.adapter._pending_lock_root()

            self.assertEqual(lock_root.parent, Path(temporary).resolve())
            self.assertRegex(lock_root.name, r"^codearbiter-prerequisite-locks-")
            info = lock_root.lstat()
            self.assertTrue(stat.S_ISDIR(info.st_mode))
            self.assertFalse(stat.S_ISLNK(info.st_mode))
            self.assertFalse(getattr(info, "st_file_attributes", 0) & 0x400)
            if hasattr(os, "getuid"):
                self.assertEqual(info.st_uid, os.getuid())
                self.assertEqual(stat.S_IMODE(info.st_mode) & 0o077, 0)

    @unittest.skipIf(hasattr(os, "getuid"), "Windows fallback check")
    def test_transition_lock_root_does_not_require_profile_environment(self):
        with tempfile.TemporaryDirectory() as temporary:
            with (
                mock.patch.object(
                    self.adapter.tempfile, "gettempdir", return_value=temporary
                ),
                mock.patch.object(
                    Path, "home", side_effect=RuntimeError("profile unavailable")
                ),
            ):
                lock_root = self.adapter._pending_lock_root()

        self.assertRegex(lock_root.name, r"^codearbiter-prerequisite-locks-temp-")

    def test_transition_lock_rejects_precreated_non_directory_root(self):
        with tempfile.TemporaryDirectory() as temporary:
            with mock.patch.object(
                self.adapter.tempfile, "gettempdir", return_value=temporary
            ):
                lock_root = (
                    Path(temporary).resolve()
                    / self.adapter._pending_lock_directory_name()
                )
                lock_root.write_text("hostile", encoding="utf-8")
                with self.assertRaisesRegex(RuntimeError, "PREREQUISITE_BUSY"):
                    with self.adapter._pending_transition_lock(
                        self.root, "PLAN-EXAMPLE"
                    ):
                        self.fail("unsafe lock root was accepted")

    def test_transition_lock_rejects_symlink_lock_root(self):
        fake = SimpleNamespace(
            st_mode=stat.S_IFLNK | 0o777,
            st_uid=os.getuid() if hasattr(os, "getuid") else 0,
            st_file_attributes=0,
        )
        with tempfile.TemporaryDirectory() as temporary:
            with (
                mock.patch.object(
                    self.adapter.tempfile, "gettempdir", return_value=temporary
                ),
                mock.patch.object(Path, "lstat", return_value=fake),
            ):
                with self.assertRaisesRegex(RuntimeError, "PREREQUISITE_BUSY"):
                    self.adapter._pending_lock_root()

    @unittest.skipUnless(hasattr(os, "getuid"), "POSIX ownership check")
    def test_transition_lock_rejects_foreign_owner(self):
        fake = SimpleNamespace(
            st_mode=stat.S_IFDIR | 0o700,
            st_uid=os.getuid() + 1,
            st_file_attributes=0,
        )
        with tempfile.TemporaryDirectory() as temporary:
            with (
                mock.patch.object(
                    self.adapter.tempfile, "gettempdir", return_value=temporary
                ),
                mock.patch.object(Path, "lstat", return_value=fake),
            ):
                with self.assertRaisesRegex(RuntimeError, "PREREQUISITE_BUSY"):
                    self.adapter._pending_lock_root()

    def test_concurrent_confirmation_serializes_the_complete_transition(self):
        armed = self.arm()
        holder = self.hold_transition_lock()
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
            self.release_transition_lock(holder)

        result = self.consume(armed["reply"])
        self.assertTrue(result["satisfied"])
        operations = [name for name, _ in self.client.calls]
        self.assertEqual(operations.count("capture-observation"), 1)
        self.assertEqual(operations.count("prerequisite"), 1)

    def test_capture_failure_keeps_confirmed_event_stable_for_retry(self):
        armed = self.arm()
        self.client.failure = "capture-observation"
        with self.assertRaisesRegex(RuntimeError, "capture-observation failed"):
            self.consume(armed["reply"])
        pending = self.root / armed["pending"]
        confirmed = pending.read_bytes()
        confirmed_value = json.loads(confirmed)
        event_bytes = self.adapter._canonical(confirmed_value["event"])
        first_capture = [
            request for name, request in self.client.calls if name == "capture-observation"
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
            request for name, request in self.client.calls if name == "capture-observation"
        ]
        self.assertEqual(capture_requests, first_capture * 2)
        self.assertEqual(self.adapter._canonical(confirmed_value["event"]), event_bytes)
        self.assertEqual(result["receipt"], self.client.capture_result["receipt"])

    def test_partial_temporary_publication_never_poisons_digest_path(self):
        armed = self.arm()
        original_write = self.adapter._artifactauthoritylib._publish_immutable
        interrupted = False

        def fail_source_temporary(root, relative, data):
            nonlocal interrupted
            if (
                not interrupted
                and relative.parent == self.adapter._artifactauthoritylib.SOURCE_DIR
            ):
                interrupted = True
                target = root / relative
                target.parent.mkdir(parents=True, exist_ok=True)
                target.with_name("." + target.name + ".partial").write_bytes(b"{")
                raise OSError("simulated interruption before atomic publication")
            return original_write(root, relative, data)

        self.adapter._artifactauthoritylib._publish_immutable = fail_source_temporary
        try:
            with self.assertRaisesRegex(OSError, "simulated interruption"):
                self.consume(armed["reply"])
        finally:
            self.adapter._artifactauthoritylib._publish_immutable = original_write

        pending = json.loads((self.root / armed["pending"]).read_text("utf-8"))
        self.assertEqual(pending["state"], "CONFIRMED")

        result = self.consume(armed["reply"])
        self.assertTrue(result["satisfied"])
        self.assertEqual(
            json.loads((self.root / result["authority_source"]).read_text("utf-8"))["source_text"],
            armed["reply"],
        )

    def test_tampered_confirmed_event_cannot_widen_authority(self):
        armed = self.arm()
        self.client.failure = "capture-observation"
        with self.assertRaisesRegex(RuntimeError, "capture-observation failed"):
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

        holder = self.hold_transition_lock()
        try:
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
        finally:
            self.release_transition_lock(holder)


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
            ("capture-observation", "CONFIRMED"),
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
                self.assertEqual(authority_source.is_file(), expected_state == "CAPTURED")
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
                self.assertEqual(authority_source.is_file(), expected_state == "CAPTURED")
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
