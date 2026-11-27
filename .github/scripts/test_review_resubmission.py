#!/usr/bin/env python3
"""HW08 adapter fixtures; captured event shapes are not live host qualification."""
import json
import os
import importlib.util
import contextlib
import io
from pathlib import Path
import unittest
import tempfile
from types import SimpleNamespace
from unittest import mock

import test_artifact_authority_adapter as fixtures


class ReviewResubmissionTest(unittest.TestCase):
    def setUp(self):
        fixtures.AuthorityAdapterTest.setUp(self)
        self.addCleanup(fixtures.AuthorityAdapterTest.tearDown, self)
    _setup_claude = fixtures.ClaudeAuthorityAdapterTest._setup_claude
    _native_events = fixtures.CodexNativeV2HookTest._native_events
    _append = fixtures.CodexNativeV2HookTest._append
    PARENT = fixtures.CodexNativeV2HookTest.PARENT
    RUNTIME = "0.162.0-alpha.17.2"

    def _arm(self, host="codex", profile="native", suffix="original", activity="spec_review"):
        self.client.context["activity"] = activity
        self.client.context.pop("commands", None)
        if host == "claude":
            self._setup_claude()
        return self.adapter.arm_request(self.root, self.client, "PLAN-EXAMPLE", "T-001", activity,
            request_nonce="review-correction-" + suffix, host=host,
            codex_review_profile=profile if host == "codex" else None)

    def _running(self, armed, host="codex", suffix="original"):
        if host == "codex":
            events, native = self._native_events(armed, suffix)
            self.adapter.observe_codex_hook(self.root, events["pre"])
            self._append(events, native)
            for key in ("post", "start"):
                self.adapter.observe_codex_hook(self.root, events[key])
            return events["stop"]
        pre = fixtures.claude_fixture("agent-pretooluse.json", tool_input=armed["launch_envelope"], tool_use_id="call-" + suffix)
        self.adapter.observe_claude_hook(self.root, pre)
        child = "fresh-child-" + suffix
        self.adapter.observe_claude_hook(self.root, fixtures.claude_fixture("agent-posttooluse.json",
            session_id=pre["session_id"], prompt_id=pre["prompt_id"], tool_use_id=pre["tool_use_id"],
            tool_input=pre["tool_input"], tool_response={"agentId": child, "resolvedModel": "opus"}))
        self.adapter.observe_claude_hook(self.root, fixtures.claude_fixture("subagentstart.json", agent_id=child, agent_type=fixtures.REVIEWER))
        return fixtures.claude_fixture("subagentstop-first.json", agent_id=child, agent_type=fixtures.REVIEWER,
            background_tasks=[{"id": child, "agent_type": fixtures.REVIEWER}])

    def _observe(self, host, event):
        return (self.adapter.observe_codex_hook if host == "codex" else self.adapter.observe_claude_hook)(self.root, event)

    def _decision(self, armed, **changes):
        value = {"format": self.adapter.DECISION_FORMAT, "request_id": armed["request_id"],
            "target_sha256": self.client.context["input_sha256"], "contract_sha256": armed["review_contract_sha256"],
            "decision": "pass", "coverage": armed["required_coverage"], "findings": [],
            "assessment": "Source fixture independently checked the current frozen criteria."}
        value.update(changes)
        return json.dumps(value)

    def _rejected(self, host="codex", suffix="original", decision=None):
        armed = self._arm(host, suffix=suffix)
        stop = self._running(armed, host, suffix)
        stop["last_assistant_message"] = "malformed first report" if decision is None else self._decision(armed, **decision)
        with self.assertRaises(self.adapter.AuthorityError):
            self._observe(host, stop)
        self.assertEqual(self.adapter._load(self.root, armed["request_id"])["state"], "REJECTED")
        return armed, stop

    def _resubmit(self, prior, operation="corrected-operation-0001", correction="report-correction", **kwargs):
        return self.adapter.resubmit_review(self.root, self.client, prior["request_id"], operation_id=operation,
            correction=correction, **kwargs)

    def test_malformed_first_report_gets_fresh_linked_capture_without_mutating_original(self):
        for host in ("codex", "claude"):
            with self.subTest(host=host):
                prior, stop = self._rejected(host, host)
                original = Path(prior["request_path"]).read_bytes()
                fresh = self._resubmit(prior, "corrected-operation-" + host)
                self.assertNotEqual(fresh["request_id"], prior["request_id"])
                self.assertFalse(fresh["authority_restored"])
                self.assertTrue(fresh["requires_fresh_launch"])
                self.assertEqual(fresh["prior_request_id"], prior["request_id"])
                self.assertEqual(Path(prior["request_path"]).read_bytes(), original)
                with self.assertRaises(self.adapter.AuthorityError):
                    self.adapter.publish_request(self.root, self.client, fresh["request_id"])
                stop["last_assistant_message"] = self._decision(fresh)
                try:
                    self._observe(host, stop)  # later stop of the original child is not fresh evidence
                except self.adapter.AuthorityError:
                    pass
                self.assertEqual(self.adapter._load(self.root, fresh["request_id"])["state"], "ARMED")
                new_stop = self._running(fresh, host, host + "-fresh")
                self.assertNotEqual(new_stop["agent_id"], stop["agent_id"])
                new_stop["last_assistant_message"] = self._decision(fresh)
                self._observe(host, new_stop)
                published = self.adapter.publish_request(self.root, self.client, fresh["request_id"])
                self.assertIn("receipt", published)
                self.assertEqual(Path(prior["request_path"]).read_bytes(), original)
                self.assertEqual(self._resubmit(prior, "corrected-operation-" + host)["request_id"], fresh["request_id"])
                replay = self._resubmit(prior, "corrected-operation-" + host)
                self.assertTrue(replay["transport_replay"])
                self.assertFalse(replay["requires_fresh_launch"])
                self.assertNotIn("launch_envelope", replay)

    def test_exact_retry_after_each_persisted_boundary_never_creates_another_successor(self):
        for boundary in ("intent", "arm", "link"):
            with self.subTest(boundary=boundary):
                prior, _ = self._rejected(suffix=boundary)
                publish = self.adapter._publish_immutable
                arm = self.adapter.arm_request
                raised = False
                def fail_publish(root, relative, raw):
                    nonlocal raised
                    publish(root, relative, raw)
                    if not raised and self.adapter.REVIEW_RESUBMISSION_DIR in relative.parents and ((boundary == "intent") == relative.name.endswith(".intent.json")):
                        raised = True
                        raise OSError("lost response after immutable " + boundary)
                def fail_arm(*args, **kwargs):
                    nonlocal raised
                    result = arm(*args, **kwargs)
                    raised = True
                    raise OSError("lost response after fresh arm")
                target = mock.patch.object(self.adapter, "arm_request", side_effect=fail_arm) if boundary == "arm" else mock.patch.object(self.adapter, "_publish_immutable", side_effect=fail_publish)
                with target, self.assertRaisesRegex(OSError, "lost response"):
                    self._resubmit(prior, "interrupted-operation-" + boundary)
                self.assertTrue(raised)
                with mock.patch.object(self.adapter, "arm_request", wraps=arm) as capture:
                    resumed = self._resubmit(prior, "interrupted-operation-" + boundary)
                    again = self._resubmit(prior, "interrupted-operation-" + boundary)
                self.assertEqual(resumed["request_id"], again["request_id"])
                self.assertEqual(capture.call_count, 1 if boundary == "intent" else 0)
                self.assertTrue(resumed["transport_replay"])

    def test_context_drift_after_intent_refuses_new_capture_under_same_operation(self):
        prior, _ = self._rejected()
        publish = self.adapter._publish_immutable
        def fail_after_intent(root, relative, raw):
            publish(root, relative, raw)
            raise OSError("interrupted after intent")
        with mock.patch.object(self.adapter, "_publish_immutable", side_effect=fail_after_intent), self.assertRaises(OSError):
            self._resubmit(prior)
        self.client.context["input_sha256"] = "8" * 64
        with self.assertRaisesRegex(self.adapter.AuthorityError, "STALE_AUTHORITY_REQUEST"):
            self._resubmit(prior)
        fresh = self._resubmit(prior, "new-correction-after-drift", "target-correction")
        self.assertEqual(self.adapter._load(self.root, fresh["request_id"])["context"]["input_sha256"], "8" * 64)

    def test_changed_target_and_contract_are_captured_fresh_and_stale_child_cannot_pass(self):
        prior, _ = self._rejected()
        self.client.context["input_sha256"] = "8" * 64
        self.client.context["task"]["criterion_refs"].append("AC-NEW")
        fresh = self._resubmit(prior, correction="target-correction")
        self.assertIn("AC-NEW", fresh["required_coverage"])
        stop = self._running(fresh, suffix="changed-target")
        stop["last_assistant_message"] = self._decision(fresh, target_sha256="3" * 64)
        with self.assertRaisesRegex(self.adapter.AuthorityError, "INVALID_REVIEW_DECISION"):
            self._observe("codex", stop)
        self.assertEqual(self.adapter._load(self.root, fresh["request_id"])["state"], "REJECTED")

    def test_denied_unknown_and_arbitrary_terminal_failure_cannot_be_cleared(self):
        for mode in ("authorization-denied", "explicit-stop", "unknown-failure", "uncorrelated-launch-result", "invalid-first-native-review-post"):
            with self.subTest(mode=mode):
                prior, _ = self._rejected(suffix=mode)
                request = self.adapter._load(self.root, prior["request_id"])
                request["recovery"] = {"mode": mode, "rerun_permitted": False}
                self.adapter._save(self.root, request)
                original = Path(prior["request_path"]).read_bytes()
                with self.assertRaisesRegex(self.adapter.AuthorityError, "RESUBMISSION_UNAVAILABLE"):
                    self._resubmit(prior, "denied-operation-" + mode)
                self.assertEqual(Path(prior["request_path"]).read_bytes(), original)

    def test_changes_requested_and_block_are_never_success_by_resubmitting(self):
        for suffix, decision in (("changes", {"decision": "changes_requested"}), ("block", {"findings": [{"severity": "BLOCK", "code": "SOURCE", "message": "Criterion missing"}]})):
            prior, _ = self._rejected(suffix=suffix, decision=decision)
            fresh = self._resubmit(prior, "findings-correction-" + suffix, "target-correction")
            for request in (prior, fresh):
                with self.assertRaises(self.adapter.AuthorityError):
                    self.adapter.publish_request(self.root, self.client, request["request_id"])
            self.assertEqual(self.adapter._load(self.root, prior["request_id"])["state"], "REJECTED")
            self.assertEqual(self.adapter._load(self.root, fresh["request_id"])["state"], "ARMED")

    def test_changed_operation_input_and_missing_linked_successor_refuse_rearming(self):
        prior, _ = self._rejected()
        fresh = self._resubmit(prior)
        with self.assertRaisesRegex(self.adapter.AuthorityError, "INVALID_RESUBMISSION"):
            self._resubmit(prior, correction="target-correction")
        (self.adapter._spool_root(self.root) / self.adapter._request_path(fresh["request_id"])).unlink()
        with mock.patch.object(self.adapter, "arm_request") as arm, self.assertRaisesRegex(self.adapter.AuthorityError, "successor disappeared"):
            self._resubmit(prior)
        arm.assert_not_called()

    def test_corrupt_intent_cannot_link_an_existing_request_as_its_own_successor(self):
        prior, _ = self._rejected()
        publish = self.adapter._publish_immutable
        def interrupt(root, relative, raw):
            publish(root, relative, raw)
            raise OSError("intent response lost")
        with mock.patch.object(self.adapter, "_publish_immutable", side_effect=interrupt), self.assertRaises(OSError):
            self._resubmit(prior)
        intent_path = next((self.adapter._spool_root(self.root) / self.adapter.REVIEW_RESUBMISSION_DIR).glob("*.intent.json"))
        intent = json.loads(intent_path.read_bytes())
        intent["successor_request_id"] = prior["request_id"]
        intent_path.write_bytes(self.adapter._canonical(intent))
        with self.assertRaisesRegex(self.adapter.AuthorityError, "INVALID_RESUBMISSION"):
            self._resubmit(prior)

    def test_safe_path_and_size_failures_never_become_a_fresh_empty_lineage(self):
        prior, _ = self._rejected()
        fresh = self._resubmit(prior)
        link = Path(fresh["lineage_path"])
        original = link.read_bytes()
        link.write_bytes(b"x" * (self.adapter.MAX_RESUBMISSION + 1))
        with self.assertRaisesRegex(self.adapter.AuthorityError, "INVALID_RESUBMISSION"):
            self._resubmit(prior)
        link.write_bytes(original)
        target = link.with_suffix(".retained")
        link.rename(target)
        try:
            try:
                link.symlink_to(target)
            except OSError as exc:
                self.skipTest("symlink fixture unavailable: " + str(exc))
            with self.assertRaisesRegex(self.adapter.AuthorityError, "INVALID_RESUBMISSION"):
                self._resubmit(prior)
            self.assertEqual(target.read_bytes(), original)
        finally:
            link.unlink(missing_ok=True)
            target.rename(link)

    def test_completion_resubmission_requires_explicit_current_selection(self):
        fixtures.CompletionReviewTransportTest._fixture(self)
        prior = fixtures.CompletionReviewTransportTest._arm_completion(self, "native")
        stop = self._running(prior, suffix="completion")
        stop["last_assistant_message"] = "malformed completion report"
        with self.assertRaises(self.adapter.AuthorityError):
            self._observe("codex", stop)
        with self.assertRaisesRegex(self.adapter.AuthorityError, "explicit current receipt"):
            self._resubmit(prior)
        fresh = self._resubmit(prior, completion_receipts=[self.receipt_ref], supporting_files=[str(self.material)])
        self.assertNotEqual(prior["request_id"], fresh["request_id"])
        calls = [request for operation, request in self.client.calls if operation == "evidence-context"]
        selected = [request["completion_selection"] for request in calls if "completion_selection" in request]
        self.assertEqual(selected[-1], {"verification_receipts": [self.receipt_ref], "supporting_files": [str(self.material)]})

    def test_arm_state_saved_before_registry_failure_resumes_without_another_arm(self):
        prior, _ = self._rejected()
        with mock.patch.object(self.adapter, "_register_request", side_effect=OSError("interrupted after state save")), self.assertRaises(OSError):
            self._resubmit(prior)
        with mock.patch.object(self.adapter, "arm_request") as arm:
            fresh = self._resubmit(prior)
        arm.assert_not_called()
        self.assertEqual(self.adapter._registered_request(fresh["request_id"])[1]["state"], "ARMED")

    def test_write_failure_before_each_immutable_publish_retains_one_successor(self):
        for boundary in ("intent", "link"):
            with self.subTest(boundary=boundary):
                prior, _ = self._rejected(suffix="before-" + boundary)
                publish = self.adapter._publish_immutable
                def interrupt(root, relative, raw):
                    if self.adapter.REVIEW_RESUBMISSION_DIR in relative.parents and ((boundary == "intent") == relative.name.endswith(".intent.json")):
                        raise OSError("interrupted before " + boundary)
                    return publish(root, relative, raw)
                with mock.patch.object(self.adapter, "_publish_immutable", side_effect=interrupt), self.assertRaises(OSError):
                    self._resubmit(prior, "before-publish-" + boundary)
                fresh = self._resubmit(prior, "before-publish-" + boundary)
                self.assertEqual(self._resubmit(prior, "before-publish-" + boundary)["request_id"], fresh["request_id"])

    def test_steered_successor_cannot_pass_or_relabel_its_later_stop(self):
        prior, _ = self._rejected("claude", "steered-source")
        fresh = self._resubmit(prior)
        stop = self._running(fresh, "claude", "steered-successor")
        request = self.adapter._load(self.root, fresh["request_id"])
        self.adapter.observe_claude_hook(self.root, {"hook_event_name": "PreToolUse", "tool_name": "SendMessage",
            "session_id": request["launch"]["parent_session_id"]})
        stop["last_assistant_message"] = self._decision(fresh)
        self.adapter.observe_claude_hook(self.root, stop)
        with self.assertRaises(self.adapter.AuthorityError):
            self.adapter.publish_request(self.root, self.client, fresh["request_id"])
        self.assertEqual(self.adapter._load(self.root, fresh["request_id"])["state"], "REJECTED")

    def test_pristine_abandonment_and_corroborated_interruption_get_new_requests_only(self):
        abandoned = self._arm(suffix="abandonment")
        self.adapter.recover_request(self.root, abandoned["request_id"], "abandoned")
        fresh = self._resubmit(abandoned, "abandonment-correction", "operational-recovery")
        self.assertEqual(fresh["state"], "ARMED")
        failed = self._arm(suffix="interruption")
        self._running(failed, suffix="interruption")
        self.adapter.recover_request(self.root, failed["request_id"], "failed")
        resumed = self._resubmit(failed, "interruption-correction", "operational-recovery")
        self.assertEqual(resumed["state"], "ARMED")
        self.assertNotEqual(failed["request_id"], resumed["request_id"])
        unknown = self._arm(suffix="uncorroborated")
        events, _ = self._native_events(unknown, "uncorroborated")
        self.adapter.observe_codex_hook(self.root, events["pre"])
        self.adapter.recover_request(self.root, unknown["request_id"], "failed")
        with self.assertRaisesRegex(self.adapter.AuthorityError, "RESUBMISSION_UNAVAILABLE"):
            self._resubmit(unknown, "uncorroborated-correction", "operational-recovery")

    def test_retained_successor_link_without_intent_cannot_reconstruct_history(self):
        prior, _ = self._rejected()
        fresh = self._resubmit(prior)
        link = Path(fresh["lineage_path"])
        intent = link.with_name(link.stem + ".intent.json")
        intent.unlink()
        with self.assertRaisesRegex(self.adapter.AuthorityError, "INVALID_RESUBMISSION"):
            self._resubmit(prior)
        self.assertFalse(intent.exists())

    def test_actual_cli_routes_stable_correction_without_accepting_authority_inputs(self):
        prior, _ = self._rejected()
        path = fixtures.CORE_PYSRC / "artifact-authority.py"
        spec = importlib.util.spec_from_file_location("review_resubmission_cli", path)
        cli = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(cli)
        output = io.StringIO()
        with (mock.patch.object(cli._artifactlib, "helper_installation", return_value=self.root / "fixture-install"),
              mock.patch.object(cli._artifactlib, "ArtifactClient", return_value=self.client),
              contextlib.redirect_stdout(output)):
            self.assertEqual(cli.main(["resubmit-review", "--root", str(self.root), "--request-id", prior["request_id"],
                "--operation-id", "cli-corrected-operation", "--correction", "report-correction"]), 0)
        result = json.loads(output.getvalue())
        self.assertEqual(result["prior_request_id"], prior["request_id"])
        self.assertTrue(result["requires_fresh_launch"])
        self.assertFalse(result["authority_restored"])
        with contextlib.redirect_stderr(io.StringIO()), self.assertRaises(SystemExit):
            cli.main(["resubmit-review", "--root", str(self.root), "--request-id", prior["request_id"],
                "--operation-id", "cli-corrected-operation", "--correction", "report-correction", "--verdict", "pass"])

    def test_linked_and_unreadable_lineage_stay_unavailable(self):
        prior, _ = self._rejected()
        fresh = self._resubmit(prior)
        link = Path(fresh["lineage_path"])
        alias = link.with_suffix(".alias")
        original = link.read_bytes()
        try:
            os.link(link, alias)
            with self.assertRaisesRegex(self.adapter.AuthorityError, "INVALID_RESUBMISSION"):
                self._resubmit(prior)
            self.assertEqual(alias.read_bytes(), original)
        finally:
            alias.unlink(missing_ok=True)
        old_lstat = Path.lstat
        def unreadable(path):
            if path == link:
                raise PermissionError("injected metadata read refusal")
            return old_lstat(path)
        with mock.patch.object(Path, "lstat", unreadable), self.assertRaisesRegex(self.adapter.AuthorityError, "INVALID_RESUBMISSION"):
            self._resubmit(prior)
        self.assertEqual(link.read_bytes(), original)

    def test_contract_change_after_intent_requires_a_new_correction_operation(self):
        prior, _ = self._rejected()
        publish = self.adapter._publish_immutable
        def interrupt(root, relative, raw):
            publish(root, relative, raw)
            raise OSError("intent response lost")
        with mock.patch.object(self.adapter, "_publish_immutable", side_effect=interrupt), self.assertRaises(OSError):
            self._resubmit(prior)
        binding = self.adapter._review_binding
        def changed(context):
            _, coverage = binding(context)
            return "f" * 64, coverage
        with mock.patch.object(self.adapter, "_review_binding", side_effect=changed), self.assertRaisesRegex(self.adapter.AuthorityError, "STALE_AUTHORITY_REQUEST"):
            self._resubmit(prior)

    def test_completed_and_active_requests_are_not_corrections(self):
        prior = self._arm()
        with self.assertRaisesRegex(self.adapter.AuthorityError, "INVALID_RESUBMISSION"):
            self._resubmit(prior)
        stop = self._running(prior)
        stop["last_assistant_message"] = self._decision(prior)
        self._observe("codex", stop)
        with self.assertRaisesRegex(self.adapter.AuthorityError, "INVALID_RESUBMISSION"):
            self._resubmit(prior)


class NativeEngineResubmissionTest(unittest.TestCase):
    """Real native capture with source-derived host events, not live user consent."""
    @classmethod
    def setUpClass(cls):
        fixtures.ClaudeEndToEndTest.setUpClass.__func__(cls)

    @classmethod
    def tearDownClass(cls):
        fixtures.ClaudeEndToEndTest.tearDownClass.__func__(cls)

    setUp = fixtures.ClaudeEndToEndTest.setUp
    tearDown = fixtures.ClaudeEndToEndTest.tearDown
    _setup_claude = fixtures.ClaudeAuthorityAdapterTest._setup_claude
    _running = ReviewResubmissionTest._running
    _observe = ReviewResubmissionTest._observe
    _append = ReviewResubmissionTest._append

    def _native_events(self, armed, suffix):
        # Host trace metadata is outside the target's source input roots.
        trace = tempfile.TemporaryDirectory(prefix="ca-review-native-trace-")
        self.addCleanup(trace.cleanup)
        fixture = SimpleNamespace(root=Path(trace.name).resolve(), sequence=getattr(self, "sequence", 0),
            PARENT=ReviewResubmissionTest.PARENT, RUNTIME=ReviewResubmissionTest.RUNTIME)
        result = fixtures.CodexNativeV2HookTest._native_events(fixture, armed, suffix)
        self.sequence = fixture.sequence
        return result

    def _decision(self, armed):
        request = self.adapter._load(self.root, armed["request_id"])
        return json.dumps({"format": self.adapter.DECISION_FORMAT, "request_id": armed["request_id"],
            "target_sha256": request["context"]["input_sha256"], "contract_sha256": armed["review_contract_sha256"],
            "decision": "pass", "coverage": armed["required_coverage"], "findings": [],
            "assessment": "Source-derived independent review fixture over the real engine's frozen target."})

    def _flow(self, host):
        bridge = self.host.load_bridge(self.plugin)
        workflow = self.host.Workflow(bridge, self.root, self.installation, "resubmit", "claude", self.plugin)
        self.client = workflow.client
        spec = self.host.spec_normative()
        self.client.call("create", {"operation_id": "resubmit-spec", "artifact_id": "SPEC-FLOW", "kind": "spec",
            "slug": "flow", "title": spec["title"], "summary": spec["summary"], "normative": spec})
        workflow.approve("SPEC-FLOW")
        spec_hash = self.client.call("identity", {"artifact_id": "SPEC-FLOW"})["normative_sha256"]
        plan = self.host.plan_normative(spec_hash)
        self.client.call("create", {"operation_id": "resubmit-plan", "artifact_id": "PLAN-FLOW", "kind": "plan", "slug": "flow",
            "title": plan["title"], "summary": plan["summary"], "spec_id": "SPEC-FLOW", "normative": plan})
        workflow.mutate("plan-bind", "PLAN-FLOW", spec_id="SPEC-FLOW")
        workflow.approve("PLAN-FLOW")
        workflow.satisfy_prerequisite("PLAN-FLOW", "GATE-APPROVAL")
        workflow.mutate("task-start", "PLAN-FLOW", task="T-001", context_ticket=workflow.ticket())
        prior = self.adapter.arm_request(self.root, self.client, "PLAN-FLOW", "T-001", "spec_review", host=host,
            codex_review_profile="native" if host == "codex" else None)
        stop = self._running(prior, host, "real-native-original")
        stop["last_assistant_message"] = "malformed first report"
        with self.assertRaises(self.adapter.AuthorityError):
            self._observe(host, stop)
        original = Path(prior["request_path"]).read_bytes()
        fresh = self.adapter.resubmit_review(self.root, self.client, prior["request_id"],
            operation_id="real-native-corrected-operation", correction="report-correction")
        current = self._running(fresh, host, "real-native-successor")
        current["last_assistant_message"] = self._decision(fresh)
        self._observe(host, current)
        result = self.adapter.publish_request(self.root, self.client, fresh["request_id"])
        self.assertTrue((self.root / result["receipt"]).is_file())
        self.assertEqual(Path(prior["request_path"]).read_bytes(), original)
        self.assertNotEqual(current["agent_id"], stop["agent_id"])
        replay = self.adapter.resubmit_review(self.root, self.client, prior["request_id"],
            operation_id="real-native-corrected-operation", correction="report-correction")
        self.assertEqual(replay["request_id"], fresh["request_id"])
        self.assertEqual(replay["state"], "CAPTURED")
        self.assertFalse(replay["requires_fresh_launch"])

    def test_codex_protocol_successor_is_accepted_by_real_native_engine(self):
        self._flow("codex")

    def test_claude_successor_is_accepted_by_real_native_engine(self):
        self._flow("claude")


if __name__ == "__main__":
    unittest.main()
