#!/usr/bin/env python3
"""Fixture transport checks for the selected GitHub work effect."""

import base64
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
import subprocess
import sys
import tempfile
from threading import Thread
import unittest
from unittest import mock

from test_artifact_authoring import build_installation

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "core/pysrc"))
import _artifactlib  # noqa: E402
import _workgithub  # noqa: E402


class FakeGithub:
    def __init__(self, fail_create=False):
        self.calls = []
        self.fail_create = fail_create

    def request(self, method, path, body, token):
        self.calls.append((method, path))
        if path == "/repos/arbiterForge/disposable":
            return 200, {"default_branch": "main"}
        if path.endswith("/pulls/3"):
            return 200, {"merged_at": "2026-10-31T12:00:00Z", "merge_commit_sha": self.merge_sha,
                         "base": {"ref": "main", "repo": {"full_name": "arbiterForge/disposable"}}}
        if "/contents/.codearbiter/work/" in path:
            return 200, {"encoding": "base64", "content": base64.b64encode(self.merged_work).decode("ascii")}
        if method == "POST":
            if self.fail_create:
                raise TimeoutError("lost response")
            return 201, {"number": 7, "html_url": "https://github.com/arbiterForge/disposable/issues/7"}
        return 200, {"number": 7, "html_url": "https://github.com/arbiterForge/disposable/issues/7",
                     "body": "Track one outcome\n\n<!-- codearbiter-work: " + self.work_id + " -->"}


class GithubWorkTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.owner, cls.installation = build_installation()

    @classmethod
    def tearDownClass(cls):
        cls.owner.cleanup()

    def _commit_pending_effect(self):
        subprocess.run(["git", "-C", str(self.root), "add", ".codearbiter/work/project.json",
                        ".codearbiter/work/provider.json", ".codearbiter/work/" + self.work_id + ".html"], check=True)
        subprocess.run(["git", "-C", str(self.root), "-c", "user.name=Fixture",
                        "-c", "user.email=fixture@example.invalid", "commit", "-qm", "fixture"], check=True)
        return subprocess.check_output(["git", "-C", str(self.root), "rev-parse", "HEAD"], text=True).strip()

    def setUp(self):
        temp = tempfile.TemporaryDirectory(prefix="ca-work-github-")
        self.addCleanup(temp.cleanup)
        self.root = Path(temp.name).resolve()
        subprocess.run(["git", "init", "--quiet", str(self.root)], check=True)
        subprocess.run(["git", "-C", str(self.root), "config", "core.autocrlf", "false"], check=True)
        subprocess.run(["git", "-C", str(self.root), "remote", "add", "origin",
                        "https://github.com/arbiterForge/disposable.git"], check=True)
        self.client = _artifactlib.ArtifactClient(self.root, self.installation)
        created = self.client.call("work-create", {"operation_id": "github-fixture-create-001",
            "title": "Track local result", "intent": "Track one outcome", "work_type": "fix"})
        self.work_id = created["work_id"]
        config = self.client.call("work-provider-configure", {
            "operation_id": "github-fixture-configure-001", "repository": "arbiterForge/disposable",
            "credential_ref": "GH_TOKEN", "effect_timing": "immediate"})
        self.client.call("work-effect-stage", {"operation_id": "github-fixture-stage-001",
            "work_id": self.work_id, "binding_generation": config["binding_generation"],
            "expected": {"revision": created["revision"], "model_sha256": created["model_sha256"]}})

    def test_lost_create_response_never_reposts(self):
        transport = FakeGithub(fail_create=True)
        transport.work_id = self.work_id
        with self.assertRaises(_workgithub.WorkSyncError):
            _workgithub.sync(self.root, self.client, self.work_id, transport, lambda _: "fixture-token")
        self.assertEqual(transport.calls, [("POST", "/repos/arbiterForge/disposable/issues")])
        state = self.client.call("work-get", {"work_id": self.work_id})["provider_effect"]
        self.assertEqual(state["status"], "outcome_unknown")
        with self.assertRaises(_workgithub.WorkSyncError):
            _workgithub.sync(self.root, self.client, self.work_id, transport, lambda _: "fixture-token")
        self.assertEqual(len(transport.calls), 1)

    def test_success_requires_readback_and_records_one_binding(self):
        transport = FakeGithub()
        transport.work_id = self.work_id
        result = _workgithub.sync(self.root, self.client, self.work_id, transport, lambda _: "fixture-token")
        self.assertEqual(result["provider_effect"]["status"], "synchronized")
        self.assertEqual([call[0] for call in transport.calls], ["POST", "GET"])
        with self.assertRaises(_workgithub.WorkSyncError):
            _workgithub.sync(self.root, self.client, self.work_id, transport, lambda _: "fixture-token")
        self.assertEqual(len(transport.calls), 2)

    def test_uncertain_create_reconciles_by_exact_readback_without_post(self):
        lost = FakeGithub(fail_create=True)
        lost.work_id = self.work_id
        with self.assertRaises(_workgithub.WorkSyncError):
            _workgithub.sync(self.root, self.client, self.work_id, lost, lambda _: "fixture-token")
        readback = FakeGithub()
        readback.work_id = self.work_id
        resolved = _workgithub.reconcile_issue(self.root, self.client, self.work_id, 7,
                                               readback, lambda _: "fixture-token")
        self.assertEqual(resolved["provider_effect"]["status"], "synchronized")
        self.assertEqual(readback.calls, [("GET", "/repos/arbiterForge/disposable/issues/7")])

    def test_unmatched_readback_keeps_create_unknown(self):
        class WrongIssue(FakeGithub):
            def request(self, method, path, body, token):
                status, result = super().request(method, path, body, token)
                if method == "GET":
                    result["body"] = "An unrelated issue"
                return status, result

        transport = WrongIssue()
        transport.work_id = self.work_id
        with self.assertRaises(_workgithub.WorkSyncError):
            _workgithub.sync(self.root, self.client, self.work_id, transport, lambda _: "fixture-token")
        self.assertEqual(self.client.call("work-get", {"work_id": self.work_id})["provider_effect"]["status"],
                         "outcome_unknown")
        self.assertEqual([call[0] for call in transport.calls], ["POST", "GET"])

    def test_missing_credential_refuses_before_claim(self):
        transport = FakeGithub()
        with self.assertRaises(_workgithub.WorkSyncError) as raised:
            _workgithub.sync(self.root, self.client, self.work_id, transport, lambda _: None)
        self.assertEqual(raised.exception.code, "CREDENTIAL_UNAVAILABLE")
        self.assertEqual(transport.calls, [])
        self.assertEqual(self.client.call("work-get", {"work_id": self.work_id})["provider_effect"]["status"],
                         "pending")

    def test_contingent_effect_waits_without_claim_or_send(self):
        old = self.client.call("work-provider-get", {})
        current = self.client.call("work-get", {"work_id": self.work_id})
        new = self.client.call("work-provider-configure", {
            "operation_id": "github-fixture-configure-002", "repository": "arbiterForge/disposable",
            "credential_ref": "GH_TOKEN", "effect_timing": "after_merge",
            "expected_config_sha256": old["binding_generation"]})
        self.client.call("work-effect-stage", {"operation_id": "github-fixture-stage-002",
            "work_id": self.work_id, "binding_generation": new["binding_generation"],
            "expected": {"revision": current["revision"], "model_sha256": current["model_sha256"]}})
        transport = FakeGithub()
        with self.assertRaises(_workgithub.WorkSyncError) as raised:
            _workgithub.sync(self.root, self.client, self.work_id, transport, lambda _: "fixture-token")
        self.assertEqual(raised.exception.code, "EFFECT_WAITING_FOR_MERGE")
        self.assertEqual(transport.calls, [])
        self.assertEqual(self.client.call("work-get", {"work_id": self.work_id})["provider_effect"]["status"],
                         "pending")

    def test_contingent_effect_sends_only_after_merged_work_readback(self):
        old = self.client.call("work-provider-get", {})
        current = self.client.call("work-get", {"work_id": self.work_id})
        new = self.client.call("work-provider-configure", {
            "operation_id": "github-fixture-configure-merge", "repository": "arbiterForge/disposable",
            "credential_ref": "GH_TOKEN", "effect_timing": "after_merge",
            "expected_config_sha256": old["binding_generation"]})
        self.client.call("work-effect-stage", {"operation_id": "github-fixture-stage-merge",
            "work_id": self.work_id, "binding_generation": new["binding_generation"],
            "expected": {"revision": current["revision"], "model_sha256": current["model_sha256"]}})
        sha = self._commit_pending_effect()
        transport = FakeGithub()
        transport.work_id = self.work_id
        transport.merge_sha = sha
        transport.merged_work = (self.root / ".codearbiter/work" / (self.work_id + ".html")).read_bytes()
        result = _workgithub.sync(self.root, self.client, self.work_id, transport,
                                  lambda _: "fixture-token", pull_number=3)
        self.assertEqual(result["provider_effect"]["status"], "synchronized")
        self.assertEqual(result["provider_effect"]["merge_pull_number"], 3)
        self.assertEqual(result["provider_effect"]["merge_commit_sha"], sha)
        self.assertEqual([path for _, path in transport.calls[:3]],
                         ["/repos/arbiterForge/disposable/pulls/3", "/repos/arbiterForge/disposable",
                          "/repos/arbiterForge/disposable/contents/.codearbiter/work/" + self.work_id + ".html?ref=" + sha])

    def test_contingent_effect_rejects_merged_snapshot_without_matching_intent(self):
        old = self.client.call("work-provider-get", {})
        current = self.client.call("work-get", {"work_id": self.work_id})
        new = self.client.call("work-provider-configure", {
            "operation_id": "github-fixture-configure-mismatch", "repository": "arbiterForge/disposable",
            "credential_ref": "GH_TOKEN", "effect_timing": "after_merge",
            "expected_config_sha256": old["binding_generation"]})
        self.client.call("work-effect-stage", {"operation_id": "github-fixture-stage-mismatch",
            "work_id": self.work_id, "binding_generation": new["binding_generation"],
            "expected": {"revision": current["revision"], "model_sha256": current["model_sha256"]}})
        sha = self._commit_pending_effect()
        transport = FakeGithub()
        transport.work_id = self.work_id
        transport.merge_sha = sha
        transport.merged_work = (self.root / ".codearbiter/work" / (self.work_id + ".html")).read_bytes().replace(
            b'"status": "pending"', b'"status": "synchronized"')
        with self.assertRaises(_workgithub.WorkSyncError) as raised:
            _workgithub.sync(self.root, self.client, self.work_id, transport,
                             lambda _: "fixture-token", pull_number=3)
        self.assertEqual(raised.exception.code, "MERGE_UNVERIFIED")
        self.assertFalse(any(method == "POST" for method, _ in transport.calls))
        self.assertEqual(self.client.call("work-get", {"work_id": self.work_id})["provider_effect"]["status"], "pending")

    def test_contingent_effect_rejects_open_pr_and_nondefault_base(self):
        old = self.client.call("work-provider-get", {})
        current = self.client.call("work-get", {"work_id": self.work_id})
        new = self.client.call("work-provider-configure", {
            "operation_id": "github-fixture-configure-boundaries", "repository": "arbiterForge/disposable",
            "credential_ref": "GH_TOKEN", "effect_timing": "after_merge",
            "expected_config_sha256": old["binding_generation"]})
        self.client.call("work-effect-stage", {"operation_id": "github-fixture-stage-boundaries",
            "work_id": self.work_id, "binding_generation": new["binding_generation"],
            "expected": {"revision": current["revision"], "model_sha256": current["model_sha256"]}})
        sha = self._commit_pending_effect()

        class WrongPull(FakeGithub):
            def request(self, method, path, body, token):
                status, value = super().request(method, path, body, token)
                if path.endswith("/pulls/3"):
                    value["merged_at"] = None if self.open_pr else "2026-10-31T12:00:00Z"
                    value["base"]["ref"] = "main" if self.open_pr else "release"
                return status, value

        for open_pr in (True, False):
            transport = WrongPull()
            transport.work_id = self.work_id
            transport.merge_sha = sha
            transport.open_pr = open_pr
            transport.merged_work = (self.root / ".codearbiter/work" / (self.work_id + ".html")).read_bytes()
            with self.subTest(open_pr=open_pr), self.assertRaises(_workgithub.WorkSyncError) as raised:
                _workgithub.sync(self.root, self.client, self.work_id, transport,
                                 lambda _: "fixture-token", pull_number=3)
            self.assertEqual(raised.exception.code, "MERGE_UNVERIFIED")
            self.assertFalse(any(method == "POST" for method, _ in transport.calls))
            self.assertEqual(self.client.call("work-get", {"work_id": self.work_id})["provider_effect"]["status"], "pending")

    def test_contingent_effect_rejects_unmerged_or_unrelated_snapshot(self):
        old = self.client.call("work-provider-get", {})
        current = self.client.call("work-get", {"work_id": self.work_id})
        new = self.client.call("work-provider-configure", {
            "operation_id": "github-fixture-configure-refuse", "repository": "arbiterForge/disposable",
            "credential_ref": "GH_TOKEN", "effect_timing": "after_merge",
            "expected_config_sha256": old["binding_generation"]})
        self.client.call("work-effect-stage", {"operation_id": "github-fixture-stage-refuse",
            "work_id": self.work_id, "binding_generation": new["binding_generation"],
            "expected": {"revision": current["revision"], "model_sha256": current["model_sha256"]}})
        transport = FakeGithub()
        transport.work_id = self.work_id
        transport.merge_sha = "0" * 40
        transport.merged_work = b"unrelated"
        with self.assertRaises(_workgithub.WorkSyncError) as raised:
            _workgithub.sync(self.root, self.client, self.work_id, transport,
                             lambda _: "fixture-token", pull_number=3)
        self.assertEqual(raised.exception.code, "MERGE_UNVERIFIED")
        self.assertFalse(any(method == "POST" for method, _ in transport.calls))
        self.assertEqual(self.client.call("work-get", {"work_id": self.work_id})["provider_effect"]["status"], "pending")

    def test_changed_origin_refuses_before_claim(self):
        subprocess.run(["git", "-C", str(self.root), "remote", "set-url", "origin",
                        "https://github.com/arbiterForge/other.git"], check=True)
        transport = FakeGithub()
        with self.assertRaises(_workgithub.WorkSyncError):
            _workgithub.sync(self.root, self.client, self.work_id, transport, lambda _: "fixture-token")
        self.assertEqual(transport.calls, [])
        state = self.client.call("work-get", {"work_id": self.work_id})["provider_effect"]
        self.assertEqual(state["status"], "pending")

    def test_changed_origin_after_claim_refuses_before_post(self):
        parent = self

        class ChangingClient:
            def call(self, operation, request):
                result = parent.client.call(operation, request)
                if operation == "work-effect-claim":
                    subprocess.run(["git", "-C", str(parent.root), "remote", "set-url", "origin",
                                    "https://github.com/arbiterForge/other.git"], check=True)
                return result

        transport = FakeGithub()
        transport.work_id = self.work_id
        with self.assertRaises(_workgithub.WorkSyncError) as raised:
            _workgithub.sync(self.root, ChangingClient(), self.work_id, transport,
                             lambda _: "fixture-token")
        self.assertEqual(raised.exception.code, "PROVIDER_BINDING_CHANGED")
        self.assertEqual(transport.calls, [])
        self.assertEqual(self.client.call("work-get", {"work_id": self.work_id})["provider_effect"]["status"],
                         "outcome_unknown")

    def test_real_transport_never_follows_token_bearing_redirect(self):
        received = []

        class Receiver(BaseHTTPRequestHandler):
            def do_GET(self):
                received.append(self.headers.get("Authorization"))
                self.send_response(200)
                self.end_headers()
            def log_message(self, *_):
                pass

        receiver = ThreadingHTTPServer(("127.0.0.1", 0), Receiver)
        class Redirect(BaseHTTPRequestHandler):
            def do_GET(self):
                self.send_response(302)
                self.send_header("Location", f"http://127.0.0.1:{receiver.server_port}/capture")
                self.end_headers()
            def log_message(self, *_):
                pass

        redirect = ThreadingHTTPServer(("127.0.0.1", 0), Redirect)
        threads = [Thread(target=server.serve_forever, daemon=True) for server in (receiver, redirect)]
        for thread in threads:
            thread.start()
        try:
            with mock.patch.object(_workgithub, "_BASE", f"http://127.0.0.1:{redirect.server_port}"):
                with self.assertRaises(_workgithub.WorkSyncError) as raised:
                    _workgithub.GithubTransport().request("GET", "/repos/arbiterForge/disposable",
                                                          None, "fixture-token")
            self.assertEqual(raised.exception.code, "GITHUB_HTTP")
            self.assertEqual(received, [])
        finally:
            for server in (redirect, receiver):
                server.shutdown()
                server.server_close()
            for thread in threads:
                thread.join(timeout=2)


if __name__ == "__main__":
    unittest.main()
