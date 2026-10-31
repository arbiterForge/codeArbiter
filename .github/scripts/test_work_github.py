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
    def __init__(self, fail_create=False, fail_patch=False, fail_patch_without_apply=False):
        self.calls = []
        self.fail_create = fail_create
        self.fail_patch = fail_patch
        self.fail_patch_without_apply = fail_patch_without_apply
        self.issue_state = "open"
        self.assignee = "human"
        self.patches = []

    def request(self, method, path, body, token):
        self.calls.append((method, path))
        if path == "/repos/arbiterForge/disposable":
            return 200, {"default_branch": "main"}
        if path.endswith("/pulls/3"):
            return 200, {"merged_at": "2026-10-31T12:00:00Z", "merge_commit_sha": self.merge_sha,
                         "base": {"ref": "main", "repo": {"full_name": "arbiterForge/disposable"}}}
        if path.endswith("/pulls/3/files?per_page=100&page=1"):
            return 200, [{"filename": ".codearbiter/work/" + self.work_id + ".html", "status": "modified"}]
        if "/contents/.codearbiter/work/" in path:
            return 200, {"encoding": "base64", "content": base64.b64encode(self.merged_work).decode("ascii")}
        if method == "POST":
            if self.fail_create:
                raise TimeoutError("lost response")
            return 201, {"number": 7, "html_url": "https://github.com/arbiterForge/disposable/issues/7"}
        if method == "PATCH":
            self.patches.append(body)
            if self.fail_patch_without_apply:
                raise TimeoutError("status result unknown")
            self.issue_state = body["state"]
            if self.fail_patch:
                raise TimeoutError("lost status response")
            return 200, {"number": 7, "state": self.issue_state}
        return 200, {"number": 7, "html_url": "https://github.com/arbiterForge/disposable/issues/7",
                    "body": "Track one outcome\n\n<!-- codearbiter-work: " + self.work_id + " -->",
                    "state": self.issue_state, "assignee": self.assignee,
                    "node_id": "I_fixture12345678"}


class FakeProjectGithub(FakeGithub):
    def __init__(self, *, fail_add_after_apply=False, fail_field_after_apply=False,
                 partial_errors=False, oversized_cursor=False, wrong_issue=False,
                 wrong_content=False, legacy_ids=False):
        super().__init__()
        self.project_id = "UHJvamVjdFYyOjEyMzQ=" if legacy_ids else "PVT_fixture12345678"
        self.issue_id = "SXNzdWU6MTIzNA==" if legacy_ids else "I_fixture12345678"
        self.field_id = "RmllbGQ6MTIzNA==" if legacy_ids else "PVTSSF_fixture12345678"
        self.added_item_id = "SXRlbToxMjM0" if legacy_ids else "PVTI_fixture12345678"
        self.item_id = None
        self.adds = 0
        self.fail_add_after_apply = fail_add_after_apply
        self.field_option_id = None
        self.field_updates = 0
        self.fail_field_after_apply = fail_field_after_apply
        self.partial_errors = partial_errors
        self.oversized_cursor = oversized_cursor
        self.wrong_issue = wrong_issue
        self.wrong_content = wrong_content

    def request(self, method, path, body, token):
        status, result = super().request(method, path, body, token)
        if path.endswith("/issues/7") and type(result) is dict:
            result["node_id"] = self.issue_id
        return status, result

    def graphql(self, query, variables, token):
        if "owner: user(" in query or "owner: organization(" in query:
            self.calls.append(("GRAPHQL", "project-lookup"))
            assert token == "fixture-token"
            kind = "users" if "owner: user(" in query else "orgs"
            return {"data": {"owner": {"projectV2": {
                "id": self.project_id,
                "url": f"https://github.com/{kind}/{variables['login']}/projects/{variables['number']}"}}}}
        action = ("add" if "addProjectV2ItemById" in query else
                  "field-update" if "updateProjectV2ItemFieldValue" in query else
                  "field-read" if "fieldValues(" in query else
                  "fields" if "fields(first:" in query else "read")
        self.calls.append(("GRAPHQL", action))
        assert token == "fixture-token"
        assert variables["project"] == self.project_id
        if "issue" in variables:
            assert variables["issue"] == self.issue_id
        if action == "field-update":
            self.field_updates += 1
            self.field_option_id = variables["option"]
            if self.fail_field_after_apply:
                raise TimeoutError("Project field updated but response lost")
            return {"data": {"updateProjectV2ItemFieldValue": {"projectV2Item": {"id": self.item_id}}}}
        if action == "field-read":
            assert variables["item"] == self.item_id
            assert variables["field"] == self.field_id
            nodes = [] if self.field_option_id is None else [
                {"__typename": "ProjectV2ItemFieldSingleSelectValue", "optionId": self.field_option_id,
                 "field": {"id": self.field_id}}]
            return {"data": {
                "project": {"id": self.project_id},
                "issue": {"id": self.issue_id},
                "field": {"__typename": "ProjectV2SingleSelectField", "id": self.field_id,
                          "dataType": "SINGLE_SELECT", "project": {"id": self.project_id},
                          "options": [{"id": "f75ad846"}, {"id": "b1234567"}, {"id": "x"}]},
                "item": {"id": self.item_id, "project": {"id": self.project_id},
                         "content": {"id": self.issue_id},
                         "fieldValues": {"nodes": nodes,
                                         "pageInfo": {"hasNextPage": False, "endCursor": None}}}}}
        if action == "fields":
            return {"data": {"project": {"__typename": "ProjectV2", "id": self.project_id,
                    "fields": {"nodes": [
                        {"__typename": "ProjectV2SingleSelectField", "id": self.field_id,
                         "name": "Status", "options": [
                             {"id": "f75ad846", "name": "In Progress"},
                             {"id": "b1234567", "name": "Done"}]},
                        {"__typename": "ProjectV2Field", "id": "PVTF_fixture12345678"}],
                        "pageInfo": {"hasNextPage": False, "endCursor": None}}}}}
        if "addProjectV2ItemById" in query:
            self.adds += 1
            self.item_id = self.added_item_id
            if self.fail_add_after_apply:
                raise TimeoutError("Project item created but response lost")
            return {"data": {"addProjectV2ItemById": {"item": {"id": self.item_id}}}}
        result = {"data": {
            "project": {"id": self.project_id, "__typename": "ProjectV2"},
            "issue": {"id": "I_wrongfixture1234" if self.wrong_issue else self.issue_id,
                      "projectItems": {
                "nodes": [] if self.item_id is None else [
                    {"id": self.item_id, "project": {"id": self.project_id},
                     "content": {"id": "I_wrongfixture1234" if self.wrong_content else self.issue_id}}],
                "pageInfo": {"hasNextPage": self.oversized_cursor,
                             "endCursor": "x" * 513 if self.oversized_cursor else None}}}}}
        if self.partial_errors:
            result["errors"] = [{"message": "Field access denied"}]
        return result


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

    def test_observed_open_pull_is_bound_to_canonical_work_without_changing_checks(self):
        class PullTransport(FakeGithub):
            def request(self, method, path, body, token):
                self.calls.append((method, path))
                if path == "/repos/arbiterForge/disposable/pulls/12":
                    return 200, {"number": 12, "state": "open", "merged_at": None,
                        "html_url": "https://github.com/arbiterForge/disposable/pull/12",
                        "head": {"sha": "a" * 40},
                        "base": {"repo": {"full_name": "arbiterForge/disposable"}}}
                if path.endswith("/pulls/12/files?per_page=100&page=1"):
                    return 200, [{"filename": ".codearbiter/work/" + self.work_id + ".html", "status": "added"}]
                if path.endswith("?ref=" + "a" * 40):
                    raw = (self.root / ".codearbiter/work" / (self.work_id + ".html")).read_bytes()
                    return 200, {"encoding": "base64", "content": base64.b64encode(raw).decode("ascii")}
                raise AssertionError(path)

        transport = PullTransport()
        transport.root, transport.work_id = self.root, self.work_id
        observed = _workgithub.observe_pull(self.root, self.client, self.work_id, 12,
            transport, lambda _: "fixture-token", credential_ref="GH_TOKEN",
            operation_id="github-observe-pull-001")
        self.assertEqual(observed["delivery_observation"]["state"], "open")
        self.assertEqual(observed["check_status"], "unknown")
        self.assertEqual([call[0] for call in transport.calls], ["GET", "GET", "GET"])

    def test_observed_pull_rejects_unrelated_work_identity(self):
        class UnrelatedPull(FakeGithub):
            def request(self, method, path, body, token):
                self.calls.append((method, path))
                if path.endswith("/pulls/12"):
                    return 200, {"number": 12, "state": "open", "merged_at": None,
                        "html_url": "https://github.com/arbiterForge/disposable/pull/12",
                        "head": {"sha": "a" * 40},
                        "base": {"repo": {"full_name": "arbiterForge/disposable"}}}
                if path.endswith("/pulls/12/files?per_page=100&page=1"):
                    return 200, [{"filename": ".codearbiter/work/" + self.work_id + ".html", "status": "added"}]
                return 200, {"encoding": "base64", "content": base64.b64encode(b"not this work").decode("ascii")}

        transport = UnrelatedPull()
        transport.work_id = self.work_id
        with self.assertRaises(_workgithub.WorkSyncError) as raised:
            _workgithub.observe_pull(self.root, self.client, self.work_id, 12,
                transport, lambda _: "fixture-token", credential_ref="GH_TOKEN",
                operation_id="github-observe-pull-002")
        self.assertEqual(raised.exception.code, "PULL_BINDING_UNVERIFIED")
        self.assertNotIn("delivery_observation", self.client.call("work-get", {"work_id": self.work_id}))

    def test_observed_pull_rejects_a_pr_that_did_not_change_selected_work(self):
        class UnrelatedFiles(FakeGithub):
            def request(self, method, path, body, token):
                self.calls.append((method, path))
                if path.endswith("/pulls/12"):
                    return 200, {"number": 12, "state": "open", "merged_at": None,
                        "html_url": "https://github.com/arbiterForge/disposable/pull/12",
                        "head": {"sha": "a" * 40},
                        "base": {"repo": {"full_name": "arbiterForge/disposable"}}}
                return 200, [{"filename": "README.md", "status": "modified"}]

        transport = UnrelatedFiles()
        with self.assertRaises(_workgithub.WorkSyncError) as raised:
            _workgithub.observe_pull(self.root, self.client, self.work_id, 12,
                transport, lambda _: "fixture-token", credential_ref="GH_TOKEN",
                operation_id="github-observe-pull-003")
        self.assertEqual(raised.exception.code, "PULL_BINDING_UNVERIFIED")
        self.assertEqual(len(transport.calls), 2)

    def test_existing_correlated_issue_can_be_adopted_without_post(self):
        transport = FakeGithub()
        transport.work_id = self.work_id
        adopted = _workgithub.adopt_issue(self.root, self.client, self.work_id, 7,
                                          transport, lambda _: "fixture-token",
                                          operation_id="github-adopt-001")
        self.assertEqual(transport.calls, [("GET", "/repos/arbiterForge/disposable/issues/7")])
        self.assertEqual(adopted["provider_effect"]["remote_issue_number"], 7)
        self.assertEqual(adopted["provider_effect"]["status"], "synchronized")
        with self.assertRaises(_workgithub.WorkSyncError):
            _workgithub.adopt_issue(self.root, self.client, self.work_id, 7,
                                    transport, lambda _: "fixture-token",
                                    operation_id="github-adopt-002")
        self.assertEqual(len(transport.calls), 1)

    def test_adoption_refuses_ambiguous_work_markers(self):
        class AmbiguousIssue(FakeGithub):
            def request(self, method, path, body, token):
                status, result = super().request(method, path, body, token)
                if method == "GET" and path.endswith("/issues/7"):
                    result["body"] += "\n<!-- codearbiter-work: WORK-" + "F" * 32 + " -->"
                return status, result

        transport = AmbiguousIssue()
        transport.work_id = self.work_id
        with self.assertRaises(_workgithub.WorkSyncError) as raised:
            _workgithub.adopt_issue(self.root, self.client, self.work_id, 7,
                                    transport, lambda _: "fixture-token",
                                    operation_id="github-adopt-ambiguous-001")
        self.assertEqual(raised.exception.code, "REMOTE_BINDING_UNVERIFIED")
        self.assertEqual(self.client.call("work-get", {"work_id": self.work_id})["provider_effect"]["status"], "pending")

    def test_status_update_preserves_remote_assignee_and_binds_readback(self):
        transport = FakeGithub()
        transport.work_id = self.work_id
        created = _workgithub.sync(self.root, self.client, self.work_id, transport, lambda _: "fixture-token")
        config = self.client.call("work-provider-get", {})
        self.client.call("work-effect-stage", {"operation_id": "github-stage-status-001",
            "work_id": self.work_id, "binding_generation": config["binding_generation"],
            "kind": "status_update", "desired_state": "closed",
            "expected": {"revision": created["revision"], "model_sha256": created["model_sha256"]}})
        updated = _workgithub.sync(self.root, self.client, self.work_id, transport, lambda _: "fixture-token")
        self.assertEqual(transport.patches, [{"state": "closed"}])
        self.assertEqual(transport.assignee, "human")
        self.assertEqual(updated["provider_effect"]["remote_state"], "closed")
        self.assertEqual(updated["provider_effect"]["status"], "synchronized")

    def test_remote_status_change_refuses_stale_update_before_claim(self):
        transport = FakeGithub()
        transport.work_id = self.work_id
        created = _workgithub.sync(self.root, self.client, self.work_id, transport, lambda _: "fixture-token")
        config = self.client.call("work-provider-get", {})
        self.client.call("work-effect-stage", {"operation_id": "github-stage-status-002",
            "work_id": self.work_id, "binding_generation": config["binding_generation"],
            "kind": "status_update", "desired_state": "closed",
            "expected": {"revision": created["revision"], "model_sha256": created["model_sha256"]}})
        transport.issue_state = "closed"  # a human changed the issue after our last observation
        with self.assertRaises(_workgithub.WorkSyncError) as raised:
            _workgithub.sync(self.root, self.client, self.work_id, transport, lambda _: "fixture-token")
        self.assertEqual(raised.exception.code, "REMOTE_CONFLICT")
        self.assertEqual(transport.patches, [])
        self.assertEqual(self.client.call("work-get", {"work_id": self.work_id})["provider_effect"]["status"],
                         "conflict")

    def test_lost_status_response_reconciles_without_second_patch(self):
        transport = FakeGithub(fail_patch=True)
        transport.work_id = self.work_id
        created = _workgithub.sync(self.root, self.client, self.work_id, transport, lambda _: "fixture-token")
        config = self.client.call("work-provider-get", {})
        self.client.call("work-effect-stage", {"operation_id": "github-stage-status-003",
            "work_id": self.work_id, "binding_generation": config["binding_generation"],
            "kind": "status_update", "desired_state": "closed",
            "expected": {"revision": created["revision"], "model_sha256": created["model_sha256"]}})
        with self.assertRaises(_workgithub.WorkSyncError) as raised:
            _workgithub.sync(self.root, self.client, self.work_id, transport, lambda _: "fixture-token")
        self.assertEqual(raised.exception.code, "OUTCOME_UNKNOWN")
        self.assertEqual(self.client.call("work-get", {"work_id": self.work_id})["provider_effect"]["status"],
                         "outcome_unknown")
        with self.assertRaises(_workgithub.WorkSyncError):
            _workgithub.sync(self.root, self.client, self.work_id, transport, lambda _: "fixture-token")
        result = _workgithub.reconcile_status(self.root, self.client, self.work_id, transport,
                                              lambda _: "fixture-token")
        self.assertEqual(result["provider_effect"]["status"], "synchronized")
        self.assertEqual(transport.patches, [{"state": "closed"}])

    def test_uncertain_status_mismatch_needs_explicit_remote_acceptance(self):
        transport = FakeGithub(fail_patch_without_apply=True)
        transport.work_id = self.work_id
        created = _workgithub.sync(self.root, self.client, self.work_id, transport, lambda _: "fixture-token")
        config = self.client.call("work-provider-get", {})
        self.client.call("work-effect-stage", {"operation_id": "github-stage-status-004",
            "work_id": self.work_id, "binding_generation": config["binding_generation"],
            "kind": "status_update", "desired_state": "closed",
            "expected": {"revision": created["revision"], "model_sha256": created["model_sha256"]}})
        with self.assertRaises(_workgithub.WorkSyncError):
            _workgithub.sync(self.root, self.client, self.work_id, transport, lambda _: "fixture-token")
        with self.assertRaises(_workgithub.WorkSyncError) as raised:
            _workgithub.reconcile_status(self.root, self.client, self.work_id, transport,
                                         lambda _: "fixture-token")
        self.assertEqual(raised.exception.code, "OUTCOME_UNKNOWN")
        self.assertEqual(self.client.call("work-get", {"work_id": self.work_id})["provider_effect"]["status"],
                         "outcome_unknown")
        accepted = _workgithub.reconcile_status(self.root, self.client, self.work_id, transport,
                                                lambda _: "fixture-token", accept_remote=True)
        self.assertEqual(accepted["provider_effect"]["status"], "conflict")
        restaged = self.client.call("work-effect-stage", {"operation_id": "github-restage-status-004",
            "work_id": self.work_id, "binding_generation": config["binding_generation"],
            "kind": "status_update", "desired_state": "closed",
            "expected": {"revision": accepted["revision"], "model_sha256": accepted["model_sha256"]}})
        self.assertEqual(restaged["provider_effect"]["status"], "pending")
        self.assertEqual(transport.patches, [{"state": "closed"}])

    def test_status_update_rejects_pull_request_as_issue(self):
        class PullIssue(FakeGithub):
            def request(self, method, path, body, token):
                status, result = super().request(method, path, body, token)
                if method == "GET" and path.endswith("/issues/7"):
                    result["pull_request"] = {"url": "https://api.github.com/ignored"}
                return status, result

        transport = PullIssue()
        transport.work_id = self.work_id
        with self.assertRaises(_workgithub.WorkSyncError) as raised:
            _workgithub.sync(self.root, self.client, self.work_id, transport, lambda _: "fixture-token")
        self.assertEqual(raised.exception.code, "OUTCOME_UNKNOWN")
        self.assertEqual(transport.patches, [])

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
        self.assertEqual([path for _, path in transport.calls[:4]],
                         ["/repos/arbiterForge/disposable/pulls/3", "/repos/arbiterForge/disposable",
                          "/repos/arbiterForge/disposable/pulls/3/files?per_page=100&page=1",
                          "/repos/arbiterForge/disposable/contents/.codearbiter/work/" + self.work_id + ".html?ref=" + sha])

    def test_contingent_effect_rejects_unrelated_merge_with_preexisting_work(self):
        old = self.client.call("work-provider-get", {})
        current = self.client.call("work-get", {"work_id": self.work_id})
        new = self.client.call("work-provider-configure", {
            "operation_id": "github-fixture-configure-unrelated", "repository": "arbiterForge/disposable",
            "credential_ref": "GH_TOKEN", "effect_timing": "after_merge",
            "expected_config_sha256": old["binding_generation"]})
        self.client.call("work-effect-stage", {"operation_id": "github-fixture-stage-unrelated",
            "work_id": self.work_id, "binding_generation": new["binding_generation"],
            "expected": {"revision": current["revision"], "model_sha256": current["model_sha256"]}})
        sha = self._commit_pending_effect()

        class UnrelatedMerge(FakeGithub):
            def request(self, method, path, body, token):
                if path.endswith("/pulls/3/files?per_page=100&page=1"):
                    self.calls.append((method, path))
                    return 200, [{"filename": "README.md", "status": "modified"}]
                return super().request(method, path, body, token)

        transport = UnrelatedMerge()
        transport.work_id = self.work_id
        transport.merge_sha = sha
        transport.merged_work = (self.root / ".codearbiter/work" / (self.work_id + ".html")).read_bytes()
        with self.assertRaises(_workgithub.WorkSyncError) as raised:
            _workgithub.sync(self.root, self.client, self.work_id, transport,
                             lambda _: "fixture-token", pull_number=3)
        self.assertEqual(raised.exception.code, "MERGE_UNVERIFIED")
        self.assertFalse(any(method == "POST" for method, _ in transport.calls))
        self.assertEqual(self.client.call("work-get", {"work_id": self.work_id})["provider_effect"]["status"], "pending")

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

    def test_contingent_effect_rejects_local_title_after_merge(self):
        old = self.client.call("work-provider-get", {})
        current = self.client.call("work-get", {"work_id": self.work_id})
        new = self.client.call("work-provider-configure", {
            "operation_id": "github-fixture-configure-late-edit", "repository": "arbiterForge/disposable",
            "credential_ref": "GH_TOKEN", "effect_timing": "after_merge",
            "expected_config_sha256": old["binding_generation"]})
        self.client.call("work-effect-stage", {"operation_id": "github-fixture-stage-late-edit",
            "work_id": self.work_id, "binding_generation": new["binding_generation"],
            "expected": {"revision": current["revision"], "model_sha256": current["model_sha256"]}})
        sha = self._commit_pending_effect()
        transport = FakeGithub()
        transport.work_id = self.work_id
        transport.merge_sha = sha
        transport.merged_work = (self.root / ".codearbiter/work" / (self.work_id + ".html")).read_bytes()
        selected = self.client.call("work-get", {"work_id": self.work_id})
        self.client.call("work-update", {"operation_id": "github-fixture-rename-late-edit",
            "work_id": self.work_id, "action": "rename", "title": "Unmerged title",
            "expected": {"revision": selected["revision"], "model_sha256": selected["model_sha256"]}})
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

    def _project_ready(self, transport):
        transport.work_id = self.work_id
        issue = _workgithub.sync(self.root, self.client, self.work_id, transport,
                                 lambda _: "fixture-token")
        config = self.client.call("work-project-configure", {
            "operation_id": "github-project-config-001",
            "project_node_id": transport.project_id})
        staged = self.client.call("work-project-stage", {
            "operation_id": "github-project-stage-001", "work_id": self.work_id,
            "binding_generation": config["binding_generation"],
            "expected": {"revision": issue["revision"], "model_sha256": issue["model_sha256"]}})
        return config, staged

    def test_project_url_discovery_resolves_user_and_org_boards_without_writing(self):
        class DiscoveryTransport:
            def __init__(self):
                self.calls = []

            def graphql(self, query, variables, token):
                self.calls.append((query, variables))
                assert token == "fixture-token"
                owner = "user" if "owner: user(" in query else "organization"
                return {"data": {"owner": {"projectV2": {
                    "id": "PVT_fixture12345678",
                    "url": f"https://github.com/{'users' if owner == 'user' else 'orgs'}/{variables['login']}/projects/{variables['number']}"}}}}

        transport = DiscoveryTransport()
        project_binding = self.root / ".codearbiter/work/project-provider.json"
        self.assertFalse(project_binding.exists())
        for url in ("https://github.com/users/SUaDtL/projects/1",
                    "https://github.com/orgs/arbiterForge/projects/12"):
            result = _workgithub.discover_project(self.root, self.client, url,
                                                  transport, lambda _: "fixture-token")
            self.assertEqual(result, {"project_node_id": "PVT_fixture12345678", "project_url": url})
        self.assertEqual(len(transport.calls), 2)
        self.assertFalse(project_binding.exists())

    def test_project_url_discovery_rejects_redirects_and_mismatched_readback(self):
        class DiscoveryTransport:
            def graphql(self, query, variables, token):
                return {"data": {"owner": {"projectV2": {
                    "id": "PVT_fixture12345678", "url": "https://github.com/users/other/projects/1"}}}}

        transport = DiscoveryTransport()
        for url in ("http://github.com/users/SUaDtL/projects/1",
                    "https://github.com.evil.test/users/SUaDtL/projects/1",
                    "https://github.com/users/SUaDtL/projects/1?x=1"):
            with self.subTest(url=url), self.assertRaises(_workgithub.WorkSyncError):
                _workgithub.discover_project(self.root, self.client, url,
                                             transport, lambda _: "fixture-token")
        with self.assertRaises(_workgithub.WorkSyncError) as raised:
            _workgithub.discover_project(self.root, self.client,
                "https://github.com/users/SUaDtL/projects/1", transport,
                lambda _: "fixture-token")
        self.assertEqual(raised.exception.code, "REMOTE_BINDING_UNVERIFIED")

    def test_project_add_readback_keeps_bound_issue(self):
        transport = FakeProjectGithub()
        self._project_ready(transport)
        result = _workgithub.sync_project(self.root, self.client, self.work_id, transport,
                                          lambda _: "fixture-token")
        self.assertEqual(result["project_effect"]["status"], "synchronized")
        self.assertEqual(result["project_effect"]["remote_item_id"], "PVTI_fixture12345678")
        self.assertEqual(result["provider_effect"]["remote_issue_number"], 7)
        self.assertEqual(transport.adds, 1)

    def test_project_lost_add_response_reconciles_without_duplicate_issue_or_item(self):
        transport = FakeProjectGithub(fail_add_after_apply=True)
        self._project_ready(transport)
        with self.assertRaises(_workgithub.WorkSyncError) as raised:
            _workgithub.sync_project(self.root, self.client, self.work_id, transport,
                                     lambda _: "fixture-token")
        self.assertEqual(raised.exception.code, "OUTCOME_UNKNOWN")
        unknown = self.client.call("work-get", {"work_id": self.work_id})
        self.assertEqual(unknown["project_effect"]["status"], "outcome_unknown")
        self.assertEqual(unknown["provider_effect"]["status"], "synchronized")
        with self.assertRaises(_workgithub.WorkSyncError):
            _workgithub.sync_project(self.root, self.client, self.work_id, transport,
                                     lambda _: "fixture-token")
        recovered = _workgithub.reconcile_project(self.root, self.client, self.work_id,
                                                  transport, lambda _: "fixture-token")
        self.assertEqual(recovered["project_effect"]["status"], "synchronized")
        self.assertEqual(recovered["provider_effect"]["remote_issue_number"], 7)
        self.assertEqual(transport.adds, 1)
        self.assertEqual(sum(method == "POST" for method, _ in transport.calls), 1)

    def _project_attached(self, transport):
        self._project_ready(transport)
        return _workgithub.sync_project(self.root, self.client, self.work_id, transport,
                                        lambda _: "fixture-token")

    def _stage_project_option(self, attached, expected_option_id, *, field_id="PVTSSF_fixture12345678",
                              desired_option_id="f75ad846"):
        config = self.client.call("work-project-get", {})
        return self.client.call("work-project-stage-field", {
            "operation_id": "github-project-field-stage-001", "work_id": self.work_id,
            "binding_generation": config["binding_generation"], "field_id": field_id,
            "desired_option_id": desired_option_id, "expected_remote_option_id": expected_option_id,
            "expected": {"revision": attached["revision"], "model_sha256": attached["model_sha256"]}})

    def test_project_single_select_update_reads_back_without_touching_issue(self):
        transport = FakeProjectGithub()
        attached = self._project_attached(transport)
        self._stage_project_option(attached, None)
        result = _workgithub.sync_project_field(self.root, self.client, self.work_id,
                                                transport, lambda _: "fixture-token")
        self.assertEqual(result["project_effect"]["status"], "synchronized")
        self.assertEqual(result["project_effect"]["observed_option_id"], "f75ad846")
        self.assertEqual(result["provider_effect"]["remote_issue_number"], 7)
        self.assertEqual(transport.field_updates, 1)

    def test_project_discovers_fields_and_stages_from_automatic_read(self):
        transport = FakeProjectGithub()
        self._project_attached(transport)
        fields = _workgithub.project_fields(self.root, self.client, self.work_id,
                                            transport, lambda _: "fixture-token")
        self.assertEqual(fields["fields"], [{"field_id": transport.field_id,
            "name": "Status", "options": [{"option_id": "f75ad846", "name": "In Progress"},
                                           {"option_id": "b1234567", "name": "Done"}]}])
        transport.field_option_id = "b1234567"
        staged = _workgithub.stage_project_field(self.root, self.client, self.work_id,
            transport.field_id, "f75ad846", "auto-field-stage-001", transport,
            lambda _: "fixture-token")
        self.assertEqual(staged["project_effect"]["expected_remote_option_id"], "b1234567")
        result = _workgithub.sync_project_field(self.root, self.client, self.work_id,
                                                transport, lambda _: "fixture-token")
        self.assertEqual(result["project_effect"]["observed_option_id"], "f75ad846")
        self.assertEqual(transport.field_updates, 1)

    def test_project_legacy_global_node_ids_and_short_option_id(self):
        transport = FakeProjectGithub(legacy_ids=True)
        attached = self._project_attached(transport)
        self.assertEqual(attached["project_effect"]["remote_item_id"], transport.added_item_id)
        self._stage_project_option(attached, None, field_id=transport.field_id, desired_option_id="x")
        result = _workgithub.sync_project_field(self.root, self.client, self.work_id,
                                                transport, lambda _: "fixture-token")
        self.assertEqual(result["project_effect"]["observed_option_id"], "x")
        self.assertEqual(transport.field_updates, 1)

    def test_project_single_select_drift_conflicts_before_send(self):
        transport = FakeProjectGithub()
        attached = self._project_attached(transport)
        self._stage_project_option(attached, None)
        transport.field_option_id = "b1234567"
        with self.assertRaises(_workgithub.WorkSyncError) as raised:
            _workgithub.sync_project_field(self.root, self.client, self.work_id,
                                           transport, lambda _: "fixture-token")
        self.assertEqual(raised.exception.code, "REMOTE_CONFLICT")
        current = self.client.call("work-get", {"work_id": self.work_id})
        self.assertEqual(current["project_effect"]["status"], "conflict")
        self.assertEqual(current["project_effect"]["observed_option_id"], "b1234567")
        self.assertEqual(transport.field_updates, 0)

    def test_project_single_select_lost_response_reconciles_without_resend(self):
        transport = FakeProjectGithub(fail_field_after_apply=True)
        attached = self._project_attached(transport)
        self._stage_project_option(attached, None)
        with self.assertRaises(_workgithub.WorkSyncError) as raised:
            _workgithub.sync_project_field(self.root, self.client, self.work_id,
                                           transport, lambda _: "fixture-token")
        self.assertEqual(raised.exception.code, "OUTCOME_UNKNOWN")
        self.assertEqual(self.client.call("work-get", {"work_id": self.work_id})["project_effect"]["status"],
                         "outcome_unknown")
        recovered = _workgithub.reconcile_project_field(self.root, self.client, self.work_id,
                                                         transport, lambda _: "fixture-token")
        self.assertEqual(recovered["project_effect"]["status"], "synchronized")
        self.assertEqual(transport.field_updates, 1)

    def test_project_partial_graphql_error_refuses_before_claim(self):
        transport = FakeProjectGithub(partial_errors=True)
        self._project_ready(transport)
        with self.assertRaises(_workgithub.WorkSyncError) as raised:
            _workgithub.sync_project(self.root, self.client, self.work_id,
                                     transport, lambda _: "fixture-token")
        self.assertEqual(raised.exception.code, "INVALID_REMOTE_RESPONSE")
        self.assertEqual(self.client.call("work-get", {"work_id": self.work_id})["project_effect"]["status"],
                         "pending")

    def test_project_long_cursor_refuses_before_claim(self):
        transport = FakeProjectGithub(oversized_cursor=True)
        self._project_ready(transport)
        with self.assertRaises(_workgithub.WorkSyncError) as raised:
            _workgithub.sync_project(self.root, self.client, self.work_id,
                                     transport, lambda _: "fixture-token")
        self.assertEqual(raised.exception.code, "INVALID_REMOTE_RESPONSE")
        self.assertEqual(self.client.call("work-get", {"work_id": self.work_id})["project_effect"]["status"],
                         "pending")

    def test_project_wrong_issue_readback_refuses_before_claim(self):
        transport = FakeProjectGithub(wrong_issue=True)
        self._project_ready(transport)
        with self.assertRaises(_workgithub.WorkSyncError) as raised:
            _workgithub.sync_project(self.root, self.client, self.work_id,
                                     transport, lambda _: "fixture-token")
        self.assertEqual(raised.exception.code, "PROJECT_BINDING_UNVERIFIED")
        self.assertEqual(self.client.call("work-get", {"work_id": self.work_id})["project_effect"]["status"],
                         "pending")

    def test_project_wrong_item_content_refuses_before_claim(self):
        transport = FakeProjectGithub(wrong_content=True)
        self._project_ready(transport)
        transport.item_id = transport.added_item_id
        with self.assertRaises(_workgithub.WorkSyncError) as raised:
            _workgithub.sync_project(self.root, self.client, self.work_id,
                                     transport, lambda _: "fixture-token")
        self.assertEqual(raised.exception.code, "PROJECT_BINDING_UNVERIFIED")
        self.assertEqual(transport.adds, 0)

    def test_project_generation_change_refuses_before_remote_add(self):
        transport = FakeProjectGithub()
        config, _ = self._project_ready(transport)
        self.client.call("work-project-configure", {
            "operation_id": "github-project-config-changed",
            "project_node_id": "PVT_otherfixture1234",
            "expected_config_sha256": config["binding_generation"]})
        with self.assertRaises(_workgithub.WorkSyncError) as raised:
            _workgithub.sync_project(self.root, self.client, self.work_id,
                                     transport, lambda _: "fixture-token")
        self.assertEqual(raised.exception.code, "PROJECT_BINDING_CHANGED")
        self.assertEqual(transport.adds, 0)

    def test_transport_refuses_unlisted_token_destinations(self):
        transport = _workgithub.GithubTransport()
        for method, path in (("POST", "/repos/arbiterForge/disposable/hooks"),
                             ("PATCH", "/repos/arbiterForge/disposable/issues/7/comments"),
                             ("GET", "/repos/arbiterForge/disposable/issues/7?token=x")):
            with self.subTest(method=method, path=path), self.assertRaises(_workgithub.WorkSyncError) as raised:
                transport.request(method, path, None, "fixture-token")
            self.assertEqual(raised.exception.code, "UNSUPPORTED_REQUEST")

    def test_transport_refuses_unbounded_project_graphql_variables(self):
        transport = _workgithub.GithubTransport()
        base = {"project": "PVT_fixture12345678", "issue": "I_fixture12345678",
                "after": None}
        for query, variables in (
            ("query { viewer { login } }", base),
            (_workgithub._PROJECT_READ, {**base, "after": "x" * 513}),
            (_workgithub._PROJECT_READ, {**base, "project": "https://example.invalid"}),
            (_workgithub._PROJECT_READ, {**base, "issue": ["I_fixture12345678"]}),
            (_workgithub._PROJECT_USER_LOOKUP, {"login": "bad/owner", "number": 1}),
            (_workgithub._PROJECT_ORG_LOOKUP, {"login": "arbiterForge", "number": 0}),
        ):
            with self.subTest(query=query[:20], variables=variables), self.assertRaises(_workgithub.WorkSyncError) as raised:
                transport.graphql(query, variables, "fixture-token")
            self.assertEqual(raised.exception.code, "UNSUPPORTED_REQUEST")

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
    unittest.main(verbosity=2)
