#!/usr/bin/env python3
"""Behavioral producer fixtures for the typed spec/plan authoring path.

The receipts in this file are synthetic workflow events. They exercise the
existing authority boundary but do not approve this package or any real plan.
"""

from __future__ import annotations

import hashlib
import contextlib
import io
import json
import os
from pathlib import Path
import re
import subprocess
import shutil
import sys
import tempfile
import unittest
from unittest import mock


REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO / "core" / "pysrc"))

import _artifactlib  # noqa: E402
import _artifactauthoritylib  # noqa: E402
import _intentlib  # noqa: E402
from _artifactlib import ArtifactClient, ArtifactError  # noqa: E402


FEATURE_COMMAND = REPO / "core" / "surface" / "commands" / "feature.md"
SPRINT_PROCEDURE = REPO / "core" / "surface" / "SPRINT.md"
BRAINSTORMING_SKILL = REPO / "core" / "surface" / "skills" / "brainstorming" / "SKILL.md"
ARTIFACTS_INCLUDE = REPO / "core" / "surface" / "includes" / "artifacts.md"
WRITING_PLANS_SKILL = REPO / "core" / "surface" / "skills" / "writing-plans" / "SKILL.md"
TDD_SKILL = REPO / "core" / "surface" / "skills" / "tdd" / "SKILL.md"


def physical_test_directory(path: str | Path) -> Path:
    """Return the physical spelling of an existing test-owned directory.

    Hosted macOS and Windows runners can expose their temporary directory below
    a symlink, junction, or short-name alias. Production correctly rejects those
    spellings, so fixtures resolve only the temporary directories they own.
    """
    return Path(os.path.realpath(Path(path).absolute())).resolve(strict=True)


class PhysicalTestDirectoryTest(unittest.TestCase):
    def test_resolves_a_test_owned_linked_ancestor(self) -> None:
        with tempfile.TemporaryDirectory(prefix="ca-artifact-physical-root-") as temporary:
            base = Path(temporary)
            physical = base / "physical"
            linked = base / "linked"
            physical.mkdir()
            if os.name == "nt":
                made = subprocess.run(
                    ["cmd", "/d", "/c", "mklink", "/J", str(linked), str(physical)],
                    text=True,
                    capture_output=True,
                )
                if made.returncode != 0:
                    self.skipTest(f"junction creation unavailable: {made.stderr.strip()}")
            else:
                linked.symlink_to(physical, target_is_directory=True)
            self.assertTrue(os.path.samefile(physical_test_directory(linked), physical))


class AuthoringRouteContractTest(unittest.TestCase):
    @staticmethod
    def _contract(text: str) -> dict[str, object]:
        normalized = " ".join(text.split()).lower()
        default_off = any(
            marker in normalized
            for marker in (
                "legacy markdown remains the default",
                "default legacy workflows remain unchanged",
                "keep existing markdown workflows as the default",
                "normal host packages still ship no such payload",
                "default rollout remains disabled",
                "remains markdown by default",
            )
        )
        html_default = any(
            marker in normalized
            for marker in (
                "new full-lane specs use the installed structured-artifact engine",
                "new full-lane sprint specs use the installed structured-artifact engine",
                "new full feature and sprint spec/plan pairs default to canonical `.html`",
            )
        )
        return {
            "default_format": (
                "conflict"
                if default_off and html_default
                else "md"
                if default_off
                else "html"
                if html_default
                else "unspecified"
            ),
            "capability_before_write": (
                "before writing" in normalized and "must not fall back to markdown" in normalized
            ),
            "existing_markdown": (
                "existing `.md`" in normalized
                and ("legacy path" in normalized or "remains markdown" in normalized)
            ),
            "html_farm": (
                "disabled"
                if "`--farm`" in text
                and ("disabled" in text or "blocked" in text or "must block" in text)
                else "unspecified"
            ),
            "pilot_only_language": "pilot" in normalized,
        }

    def test_composed_authoring_instructions_define_one_default_contract(self) -> None:
        sources = {
            "feature": FEATURE_COMMAND.read_text(encoding="utf-8"),
            "sprint": SPRINT_PROCEDURE.read_text(encoding="utf-8"),
            "brainstorming": BRAINSTORMING_SKILL.read_text(encoding="utf-8"),
            "artifacts-include": ARTIFACTS_INCLUDE.read_text(encoding="utf-8"),
        }
        # The include owns the detailed format/capability contract; route
        # callers delegate to it rather than copying every condition and
        # accidentally recreating the old artifact-approval preflight.
        expected = {
            "default_format": "html", "capability_before_write": True,
            "existing_markdown": True, "html_farm": "disabled",
            "pilot_only_language": False,
        }
        self.assertEqual(self._contract(sources["artifacts-include"]), expected)
        self.assertEqual(self._contract(sources["feature"]), expected)
        for name in ("sprint", "brainstorming"):
            source = sources[name]
            self.assertIn("includes/artifacts.md", source, name)
            self.assertIn("`_select_authoring_route`", source, name)
            self.assertEqual(self._contract(source + sources["artifacts-include"]), expected)
            self.assertNotIn("html_requested", source, name)
            self.assertNotIn("pilot", source.lower(), name)
            self.assertNotIn("Markdown by default", source, name)
        self.assertIn("HTML `--farm` dispatch remains disabled", sources["sprint"])
        self.assertIn("includes/artifacts.md", sources["brainstorming"])

    def test_html_is_the_full_lane_default_without_markdown_fallback(self) -> None:
        include = ARTIFACTS_INCLUDE.read_text(encoding="utf-8")
        feature = FEATURE_COMMAND.read_text(encoding="utf-8")
        sprint = SPRINT_PROCEDURE.read_text(encoding="utf-8")
        brainstorming = BRAINSTORMING_SKILL.read_text(encoding="utf-8")
        for source in (feature, include):
            self.assertIn(".html", source)
            self.assertIn("before writing", source)
            self.assertIn("must not fall back to Markdown", source)
        for source in (sprint, brainstorming):
            self.assertIn("includes/artifacts.md", source)
            self.assertIn("`_select_authoring_route`", source)
            self.assertEqual(self._contract(source + include), self._contract(include))
        for source in (feature, sprint, brainstorming, include):
            self.assertNotIn("pilot", source.lower())
            self.assertNotIn("html_requested", source)
        self.assertIn("must not fall back to Markdown", include)

    def test_feature_small_lane_remains_inline_and_does_not_create_an_artifact(self) -> None:
        feature = FEATURE_COMMAND.read_text(encoding="utf-8")

        self.assertIn("Small-lane behavior is unchanged", feature)
        self.assertIn("does not create a spec artifact", feature)
        self.assertIn("state the mini-spec inline", feature)

    def test_plan_creation_uses_engine_without_artifact_approval(self) -> None:
        writing_plans = WRITING_PLANS_SKILL.read_text(encoding="utf-8")

        self.assertIn("`_preflight_plan_authoring`", writing_plans)
        self.assertIn("includes/artifacts.md", writing_plans)
        self.assertIn("`draft_preview`", writing_plans)
        self.assertIn("`plan-bind`", writing_plans)
        self.assertIn("artifact ID and normative digest", writing_plans)
        self.assertIn("checks that identity", writing_plans)
        self.assertNotIn("_preflight_plan_verification", writing_plans)
        self.assertNotIn("arm-sprint", writing_plans)
        self.assertIn("not a compulsory two-to-five-minute limit", writing_plans)
        self.assertIn("without extra artifact approvals", writing_plans)

    def test_tdd_reads_typed_obligations_without_parsing_rendered_html(self) -> None:
        tdd = TDD_SKILL.read_text(encoding="utf-8")

        self.assertIn("includes/artifacts.md", tdd)
        self.assertIn("typed criterion records", tdd)
        self.assertIn("selected", tdd)
        self.assertIn("spec/plan identities", tdd)
        self.assertIn("Retain the existing feature criteria", " ".join(tdd.split()))





class InstalledFixtureCopyTest(unittest.TestCase):
    def exercise(self, supplied):
        with tempfile.TemporaryDirectory(prefix="ca-fixture-copy-") as temporary:
            source_repo = physical_test_directory(temporary)
            source_plugin = source_repo / "plugins/ca-codex"
            stale = source_plugin / "helpers/artifacts"
            stale.mkdir(parents=True)
            (stale / "stale-binary").write_bytes(b"must not reach this fixture")
            (source_plugin / "hooks").mkdir()
            (source_plugin / "hooks/prompt-submit.py").write_bytes(b"retained source resource")
            payload = source_repo / "supplied-payload"
            payload.mkdir()
            (payload / "release.json").write_bytes(b"fresh test payload")
            environment = dict(os.environ)
            environment.pop("ARTIFACT_TEST_INSTALLATION", None)
            if supplied:
                environment["ARTIFACT_TEST_INSTALLATION"] = str(payload)
            def build(command, **kwargs):
                output = Path(command[command.index("--output") + 1])
                output.mkdir(parents=True, exist_ok=True)
                (output / "release.json").write_bytes(b"fresh test payload")
            with mock.patch.object(sys.modules[__name__], "REPO", source_repo):
                with mock.patch.dict(os.environ, environment, clear=True):
                    with mock.patch.object(subprocess, "run", side_effect=build) as builder:
                        owner, installed = build_installation()
                        try:
                            self.assertEqual({p.name for p in installed.iterdir()}, {"release.json"})
                            self.assertEqual((installed / "release.json").read_bytes(), b"fresh test payload")
                            self.assertEqual((installed.parent.parent / "hooks/prompt-submit.py").read_bytes(), b"retained source resource")
                            self.assertEqual((stale / "stale-binary").read_bytes(), b"must not reach this fixture")
                            self.assertEqual(builder.call_count, 0 if supplied else 1)
                        finally:
                            owner.cleanup()

    def test_fixture_copy_excludes_stale_payload_before_using_supplied_artifacts(self):
        self.exercise(supplied=True)

    def test_fixture_copy_excludes_stale_payload_before_building_artifacts(self):
        self.exercise(supplied=False)

class HostWorkflowAdmissionTest(unittest.TestCase):
    """Explicit historical authority inventory, not native authoring admission."""
    """Installed resources are prerequisites, not live-host authority evidence."""

    def setUp(self):
        self.owner = tempfile.TemporaryDirectory(prefix="ca-admission-")
        self.addCleanup(self.owner.cleanup)
        self.base = physical_test_directory(self.owner.name)
        self.root = self.base / "consumer"
        self.root.mkdir()
        self.plugin = self.base / "installed"

    def client(self, host="ca-codex"):
        shutil.copytree(REPO / "plugins" / host, self.plugin,
                        ignore=shutil.ignore_patterns("node_modules", "__pycache__"))
        payload = self.plugin / "helpers" / "artifacts"
        payload.mkdir(parents=True, exist_ok=True)
        return ArtifactClient(self.root, payload)

    def select(self, client, workflow="feature"):
        with mock.patch.object(client, "call", return_value={
                "host_default_enabled": True, "repository_operations_available": True}):
            return _artifactlib._select_authoring_route(
                self.root, "fresh", workflow=workflow, lane="full", client=client)

    def assert_missing_resources(self, client):
        before = sorted(str(p.relative_to(self.root)) for p in self.root.rglob("*"))
        status = client.workflow_preflight()
        self.assertFalse(status["resources_available"])
        self.assertTrue(status["missing"])
        self.assertFalse(status["live_host_verified"])
        self.assertEqual(before, sorted(str(p.relative_to(self.root)) for p in self.root.rglob("*")))

    def registry(self):
        return json.loads((self.plugin / "hooks/hooks.json").read_text(encoding="utf-8"))

    def save_registry(self, value):
        (self.plugin / "hooks/hooks.json").write_text(json.dumps(value), encoding="utf-8")

    def test_admission_accepts_current_codex_resources_without_conveying_authority(self):
        client = self.client()
        self.assertEqual(self.select(client)["format"], "html")
        self.assertEqual(list(self.root.iterdir()), [])
        status = client.workflow_preflight()
        self.assertEqual(status["evidence_kind"], "installed-resource-preflight")
        self.assertTrue(status["resources_available"])
        self.assertFalse(status["live_host_verified"])

    def test_admission_accepts_merged_claude_authority_resources(self):
        client = self.client("ca")
        self.assertEqual(self.select(client, "sprint")["format"], "html")
        self.assertEqual(client.workflow_preflight()["host"], "claude")

    def test_pi_native_authoring_does_not_require_legacy_authority(self):
        client = self.client("ca-pi")
        self.assert_missing_resources(client)
        self.assertEqual(self.select(client)["format"], "html")
        self.assertEqual(list(self.root.iterdir()), [])

    def test_admission_identifies_scoped_pi_package_without_enabling_workflow(self):
        client = self.client("ca-pi")
        manifest = self.plugin / "package.json"
        original = json.loads(manifest.read_bytes())
        status = client.workflow_preflight()
        self.assertEqual(status["host"], "pi")
        self.assertEqual(status["adapter_version"], original["version"])
        self.assertEqual(status["missing"], ["Pi production prompt, verification and review authority"])
        self.assertFalse(status["resources_available"])
        self.assertFalse(status["live_host_verified"])
        self.assert_missing_resources(client)
        for wrong_name in ("ca-pi", "@arbiterforge/unrelated"):
            with self.subTest(name=wrong_name):
                manifest.write_text(json.dumps({**original, "name": wrong_name}), encoding="utf-8")
                status = client.workflow_preflight()
                self.assertIsNone(status["host"])
                self.assertEqual(status["missing"], ["matching installed host identity"])
                self.assertFalse(status["resources_available"])
                self.assert_missing_resources(client)

    def test_admission_refuses_missing_producers_and_host_helpers(self):
        client = self.client()
        for name in ("_approvallib.py", "_prerequisitelib.py", "_sprintapprovallib.py",
                     "_reconciliationlib.py", "_artifactauthoritylib.py", "_gitexec.py",
                     "artifact-authority.py", "artifact-authority-hook.py", "prompt-submit.py"):
            path = self.plugin / "hooks" / name
            original = path.read_bytes()
            path.unlink()
            with self.subTest(resource=name):
                self.assert_missing_resources(client)
            path.write_bytes(original)
        self.assertEqual(self.select(client)["format"], "html")

    def test_admission_rechecks_resources_after_initial_success(self):
        client = self.client()
        self.select(client)
        (self.plugin / "hooks/_prerequisitelib.py").write_bytes(b"")
        self.assert_missing_resources(client)

    def test_admission_requires_every_authority_event(self):
        client = self.client()
        original = self.registry()
        for event in ("UserPromptSubmit", "PreToolUse", "PostToolUse", "SubagentStart", "SubagentStop"):
            value = json.loads(json.dumps(original))
            del value["hooks"][event]
            self.save_registry(value)
            with self.subTest(event=event):
                self.assert_missing_resources(client)

    def test_admission_requires_native_codex_refusal_and_steering_seams(self):
        client = self.client()
        original = self.registry()
        for event in ("PreToolUse", "PostToolUse"):
            for tool in ("collaborationspawn_agent", "multi_agent_v1send_input",
                         "multi_agent_v1resume_agent", "multi_agent_v1close_agent"):
                with self.subTest(event=event, tool=tool):
                    value = json.loads(json.dumps(original))
                    for group in value["hooks"][event]:
                        if any("artifact-authority-hook.py" in entry.get("command", "")
                               for entry in group["hooks"]):
                            group["matcher"] = "|".join(
                                name for name in group.get("matcher", "").split("|") if name != tool)
                    self.save_registry(value)
                    self.assert_missing_resources(client)

    def test_admission_requires_claude_failure_event_and_reviewer_charter(self):
        client = self.client("ca")
        original = self.registry()
        value = json.loads(json.dumps(original))
        del value["hooks"]["PostToolUseFailure"]
        self.save_registry(value)
        self.assert_missing_resources(client)
        self.save_registry(original)
        (self.plugin / "agents/authority-reviewer.md").unlink()
        self.assert_missing_resources(client)

    def test_admission_rejects_wrong_matchers_redirected_commands_and_async_hooks(self):
        client = self.client()
        original = self.registry()
        for mutation in ("matcher", "command", "async"):
            value = json.loads(json.dumps(original))
            for group in value["hooks"]["PostToolUse"]:
                for entry in group["hooks"]:
                    if "artifact-authority-hook.py" not in entry["command"]:
                        continue
                    if mutation == "matcher":
                        group["matcher"] = "Read"
                    elif mutation == "async":
                        entry["async"] = True
                    else:
                        entry["command"] = 'python3 "/elsewhere/artifact-authority-hook.py"'
                        entry["commandWindows"] = 'python "C:/elsewhere/artifact-authority-hook.py"'
            self.save_registry(value)
            with self.subTest(mutation=mutation):
                self.assert_missing_resources(client)

    def test_admission_rejects_malformed_duplicate_and_oversized_registry(self):
        client = self.client()
        path = self.plugin / "hooks/hooks.json"
        for raw in (b"[]", b'{"hooks":{},"hooks":{}}', b" " * 65537):
            path.write_bytes(raw)
            self.assert_missing_resources(client)

    def test_admission_rejects_unknown_ambiguous_or_missing_host_identity(self):
        client = self.client()
        manifest = self.plugin / ".codex-plugin/plugin.json"
        original = manifest.read_bytes()
        value = json.loads(original)
        value["name"] = "unknown"
        manifest.write_text(json.dumps(value), encoding="utf-8")
        self.assert_missing_resources(client)
        manifest.unlink()
        self.assert_missing_resources(client)
        manifest.write_bytes(original)
        duplicate = self.plugin / ".claude-plugin/plugin.json"
        duplicate.parent.mkdir()
        duplicate.write_text('{"name":"ca","version":"1.0.0"}', encoding="utf-8")
        self.assert_missing_resources(client)

    def test_admission_does_not_follow_environment_or_project_host_claims(self):
        client = self.client("ca-pi")
        (self.root / ".claude-plugin").mkdir()
        (self.root / ".claude-plugin/plugin.json").write_text('{"name":"ca"}', encoding="utf-8")
        with mock.patch.dict(os.environ, {"PLUGIN_ROOT": str(REPO / "plugins/ca-codex"),
                                         "CLAUDE_PLUGIN_ROOT": str(REPO / "plugins/ca")}):
            self.assert_missing_resources(client)

    def test_admission_preserves_small_lane_and_existing_markdown_on_pi(self):
        client = self.client("ca-pi")
        self.assertEqual(_artifactlib._select_authoring_route(
            self.root, "fresh", workflow="feature", lane="small")["mode"], "inline")
        spec = self.root / ".codearbiter/specs/fresh.md"
        spec.parent.mkdir(parents=True)
        spec.write_bytes(b"existing markdown\n")
        self.assertEqual(self.select(client)["format"], "md")
        self.assertEqual(spec.read_bytes(), b"existing markdown\n")

    def test_admission_rejects_nonstring_registered_commands(self):
        client = self.client()
        original = self.registry()
        for malformed in (None, [], {}, 42):
            value = json.loads(json.dumps(original))
            for entry in value["hooks"]["SubagentStop"][0]["hooks"]:
                entry["command"] = malformed
                entry["commandWindows"] = malformed
            self.save_registry(value)
            self.assert_missing_resources(client)

    def test_admission_checks_the_platform_specific_hook_command(self):
        client = self.client()
        value = self.registry()
        del value["hooks"]["SubagentStop"][0]["hooks"][0]["commandWindows"]
        self.save_registry(value)
        with mock.patch.object(_artifactlib.platform, "system", return_value="Windows"):
            self.assert_missing_resources(client)
        with mock.patch.object(_artifactlib.platform, "system", return_value="Linux"):
            self.assertEqual(self.select(client)["format"], "html")

    def test_admission_rejects_linked_helper_ancestors(self):
        client = self.client()
        hooks = self.plugin / "hooks"
        physical = self.plugin / "real-hooks"
        hooks.rename(physical)
        if os.name == "nt":
            made = subprocess.run(["cmd", "/d", "/c", "mklink", "/J", str(hooks), str(physical)],
                                  text=True, capture_output=True, timeout=10)
            if made.returncode:
                self.skipTest("test-owned junction creation is unavailable")
        else:
            hooks.symlink_to(physical, target_is_directory=True)
        try:
            self.assert_missing_resources(client)
        finally:
            if os.name == "nt":
                hooks.rmdir()
            else:
                hooks.unlink()

    def test_admission_rejects_nonregular_required_resource(self):
        client = self.client()
        path = self.plugin / "hooks/_approvallib.py"
        path.unlink()
        path.mkdir()
        self.assert_missing_resources(client)

    def test_plan_authoring_needs_native_identity_not_future_reviewers(self):
        client = self.client()
        spec = self.root / ".codearbiter/specs/fresh.html"
        spec.parent.mkdir(parents=True)
        spec.write_bytes(b"mocked structural spec; no authority is claimed")
        route = self.select(client)
        (self.plugin / "hooks/_approvallib.py").unlink()
        identity = {"artifact_id": "SPEC-FIXTURE", "kind": "spec", "path": ".codearbiter/specs/fresh.html",
                    "normative_sha256": "a" * 64, "model_sha256": "b" * 64}
        calls = []
        def native(operation, request=None, **kwargs):
            calls.append(operation)
            if operation == "capabilities":
                return {"host_default_enabled": True, "repository_operations_available": True}
            if operation == "identity":
                return identity
            self.assertEqual(operation, "validate")
            self.assertEqual(request["gate"], "structural")
            return {**identity, "valid": True}
        with mock.patch.object(client, "call", side_effect=native), mock.patch.object(
                client, "workflow_preflight", side_effect=AssertionError("authoring requested authority inventory")):
            target = _artifactlib._preflight_plan_authoring(
                route, client, spec_artifact_id="SPEC-FIXTURE", spec_normative_sha256="a" * 64)
        self.assertEqual(calls, ["capabilities", "identity", "validate"])
        self.assertEqual(target, self.root / ".codearbiter/plans/fresh.html")
        self.assertFalse(target.exists())

    def test_authoring_does_not_load_host_authority_registry(self):
        client = self.client()
        with mock.patch.object(client, "workflow_preflight", side_effect=AssertionError("unneeded authority scan")):
            self.assertEqual(self.select(client)["format"], "html")
        self.assertEqual(list(self.root.iterdir()), [])

    def test_admission_rejects_bare_engine_installation(self):
        payload = self.base / "bare-engine"
        payload.mkdir()
        self.assert_missing_resources(ArtifactClient(self.root, payload))

class AuthoringRouteSelectionTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.installation_owner, cls.installation = build_installation()

    @classmethod
    def tearDownClass(cls) -> None:
        if cls.installation_owner is not None:
            cls.installation_owner.cleanup()

    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory(prefix="ca-artifact-route-")
        self.addCleanup(self.temporary.cleanup)
        self.root = physical_test_directory(self.temporary.name) / "repo"
        self.root.mkdir()

    def _snapshot(self) -> dict[str, bytes]:
        return {
            path.relative_to(self.root).as_posix(): path.read_bytes()
            for path in self.root.rglob("*")
            if path.is_file()
        }

    def _select(
        self,
        workflow: str,
        lane: str,
        client: object | None = None,
        *,
        html_requested: bool = False,
    ) -> dict:
        selector = getattr(_artifactlib, "_select_authoring_route", None)
        self.assertIsNotNone(selector, "private authoring route selector is missing")
        return selector(
            self.root,
            "flow",
            workflow=workflow,
            lane=lane,
            client=client,
            html_requested=html_requested,
        )

    def test_full_feature_and_sprint_default_to_html_after_capability_probe(self) -> None:
        client = ArtifactClient(self.root, self.installation)
        for workflow in ("feature", "sprint"):
            with self.subTest(workflow=workflow):
                before = self._snapshot()

                selected = self._select(workflow, "full", client)

                self.assertEqual(selected["mode"], "artifact")
                self.assertEqual(selected["workflow"], workflow)
                self.assertEqual(selected["format"], "html")
                self.assertEqual(selected["state"], "absent")
                self.assertEqual(
                    selected["spec_path"], self.root / ".codearbiter/specs/flow.html"
                )
                self.assertEqual(
                    selected["plan_path"], self.root / ".codearbiter/plans/flow.html"
                )
                self.assertEqual(self._snapshot(), before)

    def test_legacy_html_requested_flag_does_not_change_the_html_default(self) -> None:
        client = ArtifactClient(self.root, self.installation)
        before = self._snapshot()

        selected = self._select(
            "feature", "full", client, html_requested=False
        )

        self.assertEqual(selected["format"], "html")
        self.assertEqual(
            selected["spec_path"], self.root / ".codearbiter/specs/flow.html"
        )
        self.assertEqual(self._snapshot(), before)

    def test_forged_client_is_rejected_before_authoring_capability_call(self) -> None:
        class ForgedClient:
            def __init__(self, root: Path):
                self.root = root
                self.calls = 0

            def call(self, operation: str) -> dict:
                self.calls += 1
                return {"protocol": "codearbiter.artifact-api/0.1.0"}

        client = ForgedClient(self.root)

        with self.assertRaises(ArtifactError) as caught:
            self._select("feature", "full", client)

        self.assertEqual(caught.exception.code, "CAPABILITY_MISSING")
        self.assertEqual(client.calls, 0)

    def test_real_client_for_another_root_is_rejected_before_capability_call(self) -> None:
        other_root = self.root.parent / "other"
        other_root.mkdir()
        client = ArtifactClient(other_root, self.installation)

        with mock.patch.object(
            client,
            "call",
            side_effect=AssertionError("wrong-root client must not be called"),
        ):
            with self.assertRaises(ArtifactError) as caught:
                self._select("sprint", "full", client)

        self.assertEqual(caught.exception.code, "CAPABILITY_MISSING")

    def test_small_lane_stays_inline_without_resolving_or_writing_artifacts(self) -> None:
        before = self._snapshot()
        with mock.patch.object(
            _artifactlib,
            "_resolve_workflow_pair",
            side_effect=AssertionError("small lane must not resolve an artifact pair"),
        ):
            selected = self._select("feature", "small")

        self.assertEqual(
            selected,
            {
                "workflow": "feature",
                "lane": "small",
                "mode": "inline",
                "slug": "flow",
                "spec_path": None,
                "plan_path": None,
            },
        )
        self.assertEqual(self._snapshot(), before)

    def test_existing_pair_selection_delegates_to_exact_format_resolver(self) -> None:
        spec = self.root / ".codearbiter/specs/flow.md"
        plan = self.root / ".codearbiter/plans/flow.md"
        spec.parent.mkdir(parents=True)
        plan.parent.mkdir(parents=True)
        spec.write_bytes(b"spec\r\n")
        plan.write_bytes(b"plan\x00")
        before = self._snapshot()
        client = ArtifactClient(self.root, self.installation)
        original = _artifactlib._resolve_workflow_pair
        with mock.patch.object(
            _artifactlib, "_resolve_workflow_pair", wraps=original
        ) as resolver:
            selected = self._select("feature", "full", client)

        resolver.assert_called_once_with(self.root, "flow")
        self.assertEqual(selected["format"], "md")
        self.assertEqual(selected["state"], "pair")
        self.assertEqual(self._snapshot(), before)

    def test_missing_or_invalid_capability_fails_before_authoring_writes(self) -> None:
        missing_installation = self.root / "missing-installation"
        missing_installation.mkdir()
        invalid_installation = self.root / "invalid-installation"
        invalid_installation.mkdir()
        (invalid_installation / "release.json").write_text("{}", encoding="utf-8")
        cases = (
            ArtifactClient(self.root, missing_installation),
            ArtifactClient(self.root, invalid_installation),
        )
        for client in cases:
            with self.subTest(client=type(client).__name__):
                before = self._snapshot()
                with self.assertRaises(ArtifactError):
                    self._select("sprint", "full", client)
                self.assertEqual(self._snapshot(), before)

    def test_disabled_or_read_only_capability_fails_before_authoring_writes(self) -> None:
        client = ArtifactClient(self.root, self.installation)
        cases = (
            {"repository_operations_available": False, "host_default_enabled": True},
            {"repository_operations_available": True, "host_default_enabled": False},
        )
        for capabilities in cases:
            with self.subTest(capabilities=capabilities):
                before = self._snapshot()
                with mock.patch.object(client, "call", return_value=capabilities):
                    with self.assertRaises(ArtifactError) as caught:
                        self._select("sprint", "full", client)
                self.assertEqual(caught.exception.code, "CAPABILITY_MISSING")
                self.assertEqual(self._snapshot(), before)

    def test_selection_rechecks_namespace_after_capability_probe(self) -> None:
        shadow = self.root / ".codearbiter/specs/flow.md"
        installation = self.root / "synthetic-installation"
        installation.mkdir()
        client = ArtifactClient(self.root, installation)

        def inject(operation: str) -> dict:
            self.assertEqual(operation, "capabilities")
            shadow.parent.mkdir(parents=True, exist_ok=True)
            shadow.write_text("# adversarial legacy shadow\n", encoding="utf-8")
            return {
                "protocol": "codearbiter.artifact-api/0.1.0",
                "repository_operations_available": True,
                "host_default_enabled": True,
            }

        with mock.patch.object(client, "call", side_effect=inject):
            with self.assertRaises(ArtifactError) as caught:
                self._select("feature", "full", client)

        self.assertIn(caught.exception.code, {"STALE_ROUTE", "AMBIGUOUS_ARTIFACT"})
        self.assertEqual(
            self._snapshot(), {".codearbiter/specs/flow.md": shadow.read_bytes()}
        )
        self.assertFalse((self.root / ".codearbiter/plans/flow.html").exists())


def canonical_hash(value: object) -> str:
    raw = json.dumps(
        value,
        ensure_ascii=False,
        allow_nan=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    return hashlib.sha256(raw).hexdigest()


def refusal_only_model_container(rendered: bytes, mutate) -> bytes:
    """Construct inert adverse state input for an owned disposable CLI fixture.

    This helper preserves the symbol graph and writes no files, events,
    observations or receipts. The caller uses the actual engine's explicit
    repair renderer to materialize this source-only refusal fixture. A claimed
    approval/state in this data has no authority and must never be reused in a
    live repository or as approval, review or qualification proof.
    """
    start = b'<script id="ca-artifact-model" type="application/json">\n'
    data = json.loads(rendered.split(start, 1)[1].split(b"\n</script>", 1)[0])
    mutate(data)
    normative = {key: data[key] for key in (
        "format_version", "kind", "schema_version", "artifact_id", "normative",
    )}
    model = {key: value for key, value in data.items() if key != "integrity"}
    data["integrity"] = {
        "normative_sha256": canonical_hash(normative),
        "model_sha256": canonical_hash(model),
        "symbol_count": data["integrity"]["symbol_count"],
    }
    return start + json.dumps(data, ensure_ascii=False).encode() + b"\n</script>"


def spec_normative() -> dict:
    return {
        "title": "Configuration precedence",
        "summary": "Select present validated values without treating false as absent.",
        "baseline": {"repository": None, "commit": None, "observed_date": "2026-09-16"},
        "sections": [],
        "sources": [],
        "retired_symbols": [],
        "intent": {
            "id": "INTENT-01",
            "problem": "Configuration precedence is ambiguous.",
            "caller": "Application initialization",
            "outcome": "Deterministic effective configuration",
            "source_refs": [],
        },
        "approach": {
            "id": "APPROACH-01",
            "choice": "Resolve validated values in explicit order.",
            "tradeoff": "Validation remains a separate boundary.",
            "binding_decision_refs": [],
        },
        "constraints": [],
        "scope": [{"id": "SCOPE-01", "statement": "Resolve present values."}],
        "non_goals": [{"id": "NON-GOAL-01", "statement": "Parse raw configuration."}],
        "decisions": [],
        "governs": ["src/*.py"],
        "open_decisions": [],
        "criteria": [
            {
                "id": "AC-001",
                "title": "Select the environment value",
                "kind": "behavior",
                "obligation": "must",
                "intent_refs": ["SCOPE-01"],
                "statement": "When both sources are valid, select the environment value.",
                "preconditions": ["Both values are validated."],
                "trigger": "Resolve a supported key.",
                "guarantees": ["The effective value equals the environment value."],
                "scenarios": [
                    {
                        "id": "SCN-AC-001",
                        "given": "Environment=false and file=true.",
                        "when": "Resolve the key.",
                        "then": "The effective value is false.",
                    }
                ],
                "verification": {
                    "id": "VER-AC-001",
                    "method": "automated",
                    "planned_target": "test_environment_overrides",
                    "oracle": "Assert the effective value is false.",
                    "negative_control": "A file-first resolver returns true.",
                    "evidence_state": "planned",
                },
                "source_refs": [],
                "constraint_refs": [],
                "applicability": {
                    "mode": "conditional",
                    "rationale": "Both sources are present.",
                },
            }
        ],
    }


def plan_normative(spec_id: str, spec_hash: str) -> dict:
    verification = {
        "availability": "proposed",
        "cwd": ".",
        "argv": ["python", "-m", "unittest", "-v", "tests.test_config"],
        "expected_exit": 0,
        "assertion": "The named test runs and passes.",
        "required_tests": ["test_environment_overrides"],
    }
    task = {
        "id": "T-001",
        "title": "Implement configuration precedence",
        "checkpoint": "CP-01",
        "execution_scope": "CP-01",
        "depends_on": [],
        "paths": [{"path": "src/config.py", "action": "modify"}],
        "criterion_refs": [f"{spec_id}#AC-001"],
        "steps": ["Write the negative test.", "Implement the contract."],
        "verification": [verification],
        "done_when": ["The named test passes."],
        "rollback": "Revert the implementation change.",
        "source_refs": [],
    }
    return {
        "title": "Configuration precedence implementation",
        "summary": "Implement and verify the approved precedence contract.",
        "baseline": {"repository": None, "commit": None, "observed_date": "2026-09-16"},
        "sections": [],
        "sources": [],
        "retired_symbols": [],
        "spec_ref": {
            "artifact_id": spec_id,
            "normative_sha256": spec_hash,
            "binding_mode": "draft_preview",
        },
        "tasks": [task],
        "checkpoints": [
            {
                "id": "CP-01",
                "title": "Complete implementation",
                "tasks": ["T-001"],
                "exit": "The combined scope is verified and reviewed.",
                "depends_on": [],
            }
        ],
        "prerequisites": [],
        "criterion_dispositions": [],
    }


def build_installation(
    owner: unittest.TestCase | None = None,
) -> tuple[tempfile.TemporaryDirectory | None, Path]:
    """Give producer tests actual installed host resources, not an admission bypass."""
    temporary = tempfile.TemporaryDirectory(prefix="ca-artifact-authoring-install-")
    if owner is not None:
        owner.addCleanup(temporary.cleanup)
    base = physical_test_directory(temporary.name)
    plugin = base / "ca-codex"
    source_plugin = REPO / "plugins" / "ca-codex"
    def source_only(directory, names):
        ignored = set(shutil.ignore_patterns("__pycache__", "node_modules")(directory, names))
        if Path(directory) == source_plugin / "helpers":
            ignored.add("artifacts")
        return ignored
    # A developer checkout may already contain a native payload. Never copy
    # it into this fresh fixture: the supplied/build branch owns those bytes.
    shutil.copytree(source_plugin, plugin, ignore=source_only)
    installation = plugin / "helpers" / "artifacts"
    supplied = os.environ.get("ARTIFACT_TEST_INSTALLATION")
    if supplied:
        source = Path(supplied).resolve()
        if not source.is_dir():
            raise AssertionError(f"ARTIFACT_TEST_INSTALLATION is not a directory: {source}")
        shutil.copytree(source, installation)
    else:
        subprocess.run(
            [sys.executable, str(REPO / "tools" / "build-artifacts.py"), "--output", str(installation)],
            cwd=REPO, text=True, capture_output=True, check=True,
        )
    return temporary, installation

class WorkflowHarness:
    def __init__(self, root: Path, installation: Path):
        self.root = root
        self.client = ArtifactClient(root, installation)
        self.sequence = 0

    def operation_id(self, purpose: str) -> str:
        self.sequence += 1
        return f"fixture-{purpose}-{self.sequence:04d}"

    def mutate(self, operation: str, artifact_id: str, **request: object) -> dict:
        identity = self.client.call("identity", {"artifact_id": artifact_id})
        return self.client.call(
            operation,
            {
                "artifact_id": artifact_id,
                "operation_id": self.operation_id(operation),
                "expected": {
                    "revision": identity["revision"],
                    "model_sha256": identity["model_sha256"],
                },
                **request,
            },
        )

    def create_pair(self) -> tuple[dict, dict]:
        spec_identity = self.create_spec()
        return spec_identity, self.create_plan(
            "SPEC-FLOW", spec_identity["normative_sha256"]
        )

    def create_spec(
        self, artifact_id: str = "SPEC-FLOW", slug: str = "flow"
    ) -> dict:
        spec = spec_normative()
        self.client.call(
            "create",
            {
                "operation_id": self.operation_id("create-spec"),
                "artifact_id": artifact_id,
                "kind": "spec",
                "slug": slug,
                "title": spec["title"],
                "summary": spec["summary"],
                "normative": spec,
            },
        )
        return self.client.call("identity", {"artifact_id": artifact_id})

    def create_plan(
        self,
        spec_id: str,
        spec_hash: str,
        artifact_id: str = "PLAN-FLOW",
        slug: str = "flow",
    ) -> dict:
        plan = plan_normative(spec_id, spec_hash)
        self.client.call(
            "create",
            {
                "operation_id": self.operation_id("create-plan"),
                "artifact_id": artifact_id,
                "kind": "plan",
                "slug": slug,
                "title": plan["title"],
                "summary": plan["summary"],
                "spec_id": spec_id,
                "normative": plan,
            },
        )
        return self.client.call("identity", {"artifact_id": artifact_id})

    def capture(
        self,
        artifact_id: str,
        record_id: str,
        kind: str,
        authority_kind: str,
        verdict: str,
        payload: dict,
    ) -> str:
        identity = self.client.call("identity", {"artifact_id": artifact_id})
        source_text = f"Synthetic event for boundary testing; not production authority: {self.operation_id('event')}"
        event = {
                "kind": kind,
                "authority_kind": authority_kind,
                "subject": {
                    "artifact_id": artifact_id,
                    "normative_sha256": identity["normative_sha256"],
                    "record_id": record_id,
                },
                "actor": "synthetic behavioral fixture",
                "origin": "isolated observed fixture",
                "verdict": verdict,
                "payload": payload,
                "source_text": source_text,
            }
        if kind in {"approval", "prerequisite", "reconciliation", "farm_authorization"}:
            return _artifactauthoritylib.capture_user_prompt(
                self.root, self.client, event, host="test", session_id="fixture"
            )["receipt"]
        context_result = self.client.call("evidence-context", {
            "artifact_id": artifact_id, "record_id": record_id, "activity": kind,
        })
        context_raw = (self.root / context_result["context_ref"]).read_bytes()
        context = json.loads(context_raw)
        if kind == "verification":
            bindings = []
            executable = str(Path(sys.executable).resolve())
            executable_sha = hashlib.sha256(Path(executable).read_bytes()).hexdigest()
            for row in context["commands"]:
                bindings.append({
                    "definition_sha256": row["definition_sha256"],
                    "argv": [executable, *row["definition"]["argv"][1:]],
                    "cwd": str(self.root), "cwd_filesystem_id": "fixture:cwd",
                    "workspace_root": str(self.root), "workspace_filesystem_id": "fixture:root",
                    "git_common_dir": str(self.root), "git_common_filesystem_id": "fixture:git",
                    "executable_sha256": executable_sha,
                })
            workspace = {"root": str(self.root), "filesystem_id": "fixture:root", "git_common_dir": str(self.root), "git_common_filesystem_id": "fixture:git", "head": "fixture", "status_sha256": hashlib.sha256(b"").hexdigest(), "content_sha256": hashlib.sha256(b"").hexdigest()}
            profile, run_id = "declared-command/0.1.0", "fixture-verifier"
            producer = {"environment_sha256": hashlib.sha256(b"fixture environment").hexdigest(), "command_bindings": bindings, "workspace_before": [workspace], "workspace_after": [workspace], "commands": payload["commands"]}
        else:
            profile, run_id = "codex-review/0.1.0", "fixture-reviewer"
            contract_sha, coverage = _artifactauthoritylib._review_binding(context)
            producer = {
                "launch": {"parent_session_id": "fixture-parent", "parent_turn_id": "fixture-turn", "tool_use_id": "fixture-tool", "post_confirmed": True, "agent_id": run_id, "agent_type": "default", "task_name": "fixture-authority", "fork_turns": "none"},
                "decision": {"format": "codearbiter.review-decision/0.1.0", "request_id": hashlib.sha256(b"fixture request").hexdigest(), "target_sha256": context["input_sha256"], "contract_sha256": contract_sha, "decision": "pass", "coverage": coverage, "findings": [], "assessment": payload["assessment"]},
            }
        canonical = lambda value: json.dumps(value, ensure_ascii=True, allow_nan=False, sort_keys=True, separators=(",", ":")).encode("ascii")
        observation = {
            "format": "codearbiter.observation/0.2.0", "kind": kind,
            "subject": event["subject"], "context_ref": context_result["context_ref"],
            "context_sha256": context_result["context_sha256"],
            "payload_sha256": hashlib.sha256(canonical(payload)).hexdigest(),
            "producer_profile": profile, "producer_run_id": run_id,
            "producer_result": producer,
            "producer_result_sha256": hashlib.sha256(canonical(producer)).hexdigest(),
        }
        observation_raw = canonical(observation)
        observation_sha = hashlib.sha256(observation_raw).hexdigest()
        observation_ref = f".codearbiter/.artifacts/observations/{observation_sha}.json"
        observation_target = self.root / observation_ref
        observation_target.parent.mkdir(parents=True, exist_ok=True)
        observation_target.write_bytes(observation_raw)
        event.update(format="codearbiter.workflow-event/0.2.0", observation_ref=observation_ref, observation_sha256=observation_sha)
        raw = json.dumps(
            event,
            ensure_ascii=True,
            allow_nan=False,
            sort_keys=True,
            separators=(",", ":"),
        ).encode("ascii")
        digest = hashlib.sha256(raw).hexdigest()
        source_ref = f".codearbiter/.artifacts/authority-sources/{digest}.json"
        target = self.root / source_ref
        target.parent.mkdir(parents=True, exist_ok=True)
        try:
            with target.open("xb") as stream:
                stream.write(raw)
        except FileExistsError:
            if target.read_bytes() != raw:
                raise AssertionError("fixture authority-source digest collision")
        result = self.client.call(
            "capture-observation",
            {"source_ref": source_ref, "source_sha256": digest},
        )
        return result["receipt"]

    def approve_pair(self) -> None:
        self.approve_spec("SPEC-FLOW")
        self.mutate("plan-bind", "PLAN-FLOW", spec_id="SPEC-FLOW")
        plan_receipt = self.capture(
            "PLAN-FLOW", "PLAN-FLOW", "approval", "user_workflow", "approved", {}
        )
        self.mutate("approve", "PLAN-FLOW", receipt=plan_receipt)

    def approve_spec(self, artifact_id: str) -> None:
        spec_receipt = self.capture(
            artifact_id, artifact_id, "approval", "user_workflow", "approved", {}
        )
        self.mutate("approve", artifact_id, receipt=spec_receipt)

    def context_ticket(self, task: str) -> str:
        pages = list(self.client.contextual_pages("PLAN-FLOW", task, 65536))
        return pages[-1]["context_ticket"]

    def task_receipts(
        self, task_id: str, spec_artifact_id: str = "SPEC-FLOW"
    ) -> tuple[str, str]:
        task = self.client.call(
            "read", {"artifact_id": "PLAN-FLOW", "symbol": task_id, "mode": "exact"}
        )["record"]
        spec = self.client.call("identity", {"artifact_id": spec_artifact_id})
        snapshot = self.client.call("snapshot", {"artifact_id": "PLAN-FLOW"})
        payload = {
            "input_sha256": snapshot["sha256"],
            "spec_sha256": spec["normative_sha256"],
            "task_sha256": canonical_hash(task),
        }
        commands = []
        for definition in task["verification"]:
            commands.append(
                {
                    "definition_sha256": canonical_hash(definition),
                    "exit": 0,
                    "tests": [
                        {"name": name, "status": "pass"}
                        for name in definition["required_tests"]
                    ],
                    "stdout_sha256": hashlib.sha256(b"fixture PASS").hexdigest(),
                    "stderr_sha256": hashlib.sha256(b"").hexdigest(),
                }
            )
        verification = self.capture(
            "PLAN-FLOW",
            task_id,
            "verification",
            "verification_runner",
            "passed",
            {**payload, "commands": commands},
        )
        review = self.capture(
            "PLAN-FLOW",
            task_id,
            "spec_review",
            "review_workflow",
            "passed",
            {**payload, "assessment": "Synthetic specification review fixture."},
        )
        return verification, review

    def review_task(
        self, task_id: str, spec_artifact_id: str = "SPEC-FLOW"
    ) -> None:
        verification, review = self.task_receipts(task_id, spec_artifact_id)
        self.mutate(
            "task-review",
            "PLAN-FLOW",
            task=task_id,
            verification_receipt=verification,
            review_receipt=review,
        )

    def accept_scope(
        self,
        scope_id: str,
        task_ids: list[str],
        spec_artifact_id: str = "SPEC-FLOW",
    ) -> None:
        plan = self.client.call("identity", {"artifact_id": "PLAN-FLOW"})
        spec = self.client.call("identity", {"artifact_id": spec_artifact_id})
        snapshot = self.client.call("snapshot", {"artifact_id": "PLAN-FLOW"})
        task_hashes = {}
        for task_id in task_ids:
            task = self.client.call(
                "read", {"artifact_id": "PLAN-FLOW", "symbol": task_id, "mode": "exact"}
            )["record"]
            task_hashes[task_id] = canonical_hash(task)
        receipt = self.capture(
            "PLAN-FLOW",
            scope_id,
            "quality_review",
            "review_workflow",
            "passed",
            {
                "input_sha256": snapshot["sha256"],
                "spec_sha256": spec["normative_sha256"],
                "base_input_sha256": snapshot["sha256"],
                "task_hashes": task_hashes,
                "assessment": "Synthetic combined-scope review fixture.",
            },
        )
        self.mutate("accept-scope", plan["artifact_id"], scope=scope_id, receipt=receipt)


class ArtifactAuthoringTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.installation_owner, cls.installation = build_installation()

    @classmethod
    def tearDownClass(cls) -> None:
        if cls.installation_owner is not None:
            cls.installation_owner.cleanup()

    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory(prefix="ca-artifact-authoring-")
        self.addCleanup(self.temporary.cleanup)
        self.root = physical_test_directory(self.temporary.name) / "repo"
        self.root.mkdir()
        self.harness = WorkflowHarness(self.root, self.installation)

    def test_installed_bootstrap_example_reads_native_task_context(self) -> None:
        self.harness.create_pair()
        plugin = self.installation.parent.parent
        guide = plugin / "includes/artifacts.md"
        examples = re.findall(r"```python\n(.*?)\n```", guide.read_text(encoding="utf-8"), re.S)
        self.assertEqual(len(examples), 1, "installed guide needs one runnable Python bootstrap")
        before = {p.relative_to(self.root): p.read_bytes()
                  for p in (self.root / ".codearbiter").rglob("*") if p.is_file()}
        def run_example(*arguments: str) -> dict:
            result = subprocess.run(
                [sys.executable, "-I", "-B", "-", str(plugin), "PLAN-FLOW", "T-001", *arguments],
                input=examples[0], cwd=self.root, capture_output=True, text=True,
                encoding="utf-8", timeout=30,
            )
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            return json.loads(result.stdout)

        packet = run_example()
        request_schema = run_example("--schema")
        self.assertEqual(request_schema["type"], "object")
        self.assertFalse(request_schema["additionalProperties"])
        self.assertEqual(set(request_schema["required"]),
                         {"protocol", "artifact_id", "task", "model_sha256"})
        self.assertNotIn("task_id", request_schema["properties"])
        self.assertEqual(packet["task"]["id"], "T-001")
        self.assertEqual(packet["task"]["verification"][0]["argv"],
                         ["python", "-m", "unittest", "-v", "tests.test_config"])
        self.assertEqual([criterion["ref"] for criterion in packet["criteria"]],
                         ["SPEC-FLOW#AC-001"])
        self.assertEqual(packet["criteria"][0]["verification"]["planned_target"],
                         "test_environment_overrides")
        self.assertTrue(packet["binding_current"])
        self.assertFalse(packet["context_complete"])
        self.assertFalse(packet["evidence_assessed"])
        self.assertLess(len(json.dumps(packet).encode("utf-8")), 65536)
        self.assertEqual(before, {p.relative_to(self.root): p.read_bytes()
                                 for p in (self.root / ".codearbiter").rglob("*") if p.is_file()})

    def test_intent_cli_accepts_ready_spec_from_native_engine(self) -> None:
        self.harness.create_spec()
        result = self.harness.client.call(
            "validate", {"artifact_id": "SPEC-FLOW", "gate": "ready"}, permit_invalid=True
        )
        self.assertTrue(result["valid"], result)
        spec = self.root / ".codearbiter/specs/flow.html"
        before = spec.read_bytes()
        out, err = io.StringIO(), io.StringIO()
        # Only fixture installation discovery is redirected; validation and
        # identity reads cross the real bridge into the native engine.
        with (
            mock.patch.object(_artifactlib, "helper_installation", return_value=self.installation),
            contextlib.redirect_stdout(out), contextlib.redirect_stderr(err),
        ):
            code = _intentlib.main(["uncovered-intent", str(spec)])
        self.assertEqual(code, 0, err.getvalue())
        self.assertEqual(out.getvalue(), "")
        self.assertEqual(err.getvalue(), "")
        self.assertEqual(spec.read_bytes(), before)

    def test_installed_intent_cli_accepts_native_empty_diagnostics(self) -> None:
        self.harness.create_spec()
        ready = self.harness.client.call(
            "validate", {"artifact_id": "SPEC-FLOW", "gate": "ready"}, permit_invalid=True
        )
        self.assertTrue(ready["valid"], ready)
        self.assertIn(ready.get("diagnostics"), (None, []))
        spec = self.root / ".codearbiter/specs/flow.html"
        before = spec.read_bytes()
        helper = self.installation.parent.parent / "hooks/_intentlib.py"
        result = subprocess.run(
            [sys.executable, str(helper), "uncovered-intent", str(spec)],
            cwd=self.root, capture_output=True, text=True, encoding="utf-8", timeout=30,
        )
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertEqual(result.stdout, "")
        self.assertEqual(spec.read_bytes(), before)
        identity = self.harness.client.call("identity", {"artifact_id": "SPEC-FLOW"})
        self.assertEqual(identity["authority"]["state"], "draft")
        self.assertFalse(identity["authority"]["authority_verified"])

    def test_installed_intent_cli_reports_incomplete_native_draft(self) -> None:
        self.harness.client.call(
            "create",
            {"operation_id": "fixture-intent-incomplete", "artifact_id": "SPEC-INCOMPLETE",
             "kind": "spec", "slug": "incomplete", "title": "Incomplete fixture",
             "summary": "No criterion is fabricated for this negative control."},
        )
        spec = self.root / ".codearbiter/specs/incomplete.html"
        before = spec.read_bytes()
        helper = self.installation.parent.parent / "hooks/_intentlib.py"
        result = subprocess.run(
            [sys.executable, str(helper), "uncovered-intent", str(spec)],
            cwd=self.root, capture_output=True, text=True, encoding="utf-8", timeout=30,
        )
        self.assertEqual(result.returncode, 1, result.stdout + result.stderr)
        self.assertIn("[INVALID-HTML-SPEC]", result.stdout)
        self.assertEqual(spec.read_bytes(), before)

    def test_smarts_rationale_round_trips_through_existing_records(self) -> None:
        # The SMARTS design-rationale convention (includes/smarts/core.md) is
        # written and read through existing mutation and read operations only:
        # approach + a bound decision + one SEC-SMARTS section, no schema change.
        created = self.harness.create_spec()
        blocks = [
            {"type": "paragraph", "text": "Alternatives: a file-first resolver was considered and rejected.", "refs": []},
            {"type": "paragraph", "text": "Decisive lenses: Reliable and Testable.", "refs": []},
            {"type": "list", "items": [
                "Weak: none material.",
                "Unknown: cold-start latency; missing observation is a startup measurement; not decision-critical.",
            ], "refs": []},
            {"type": "paragraph", "text": "Load-bearing assumption: values are validated before resolution.", "refs": []},
            {"type": "paragraph", "text": "Non-SMARTS considerations: none material.", "refs": []},
            {"type": "paragraph", "text": "Priority evidence: the approved spec ranks correctness first.", "refs": []},
        ]
        decision = {"id": "DEC-01", "topic": "Resolution order",
                    "choice": "Environment values take precedence over file values.",
                    "rationale": "The SMARTS comparison found the file-first order Weak on Reliable.",
                    "authority": "proposed"}
        self.harness.mutate("apply", "SPEC-FLOW", changes=[
            {"op": "record.add", "collection": "decisions", "record": decision},
            {"op": "record.update", "symbol": "APPROACH-01", "fields": {"binding_decision_refs": ["DEC-01"]}},
            {"op": "record.add", "collection": "sections",
             "record": {"id": "SEC-SMARTS", "title": "SMARTS design rationale", "blocks": blocks}},
        ])
        ready = self.harness.client.call("validate", {"artifact_id": "SPEC-FLOW", "gate": "ready"},
                                         permit_invalid=True)
        self.assertTrue(ready["valid"], ready)
        # The unchanged installed engine schema accepts the convention at the
        # ready gate; nothing beyond existing collections is written.
        after = self.harness.client.call("identity", {"artifact_id": "SPEC-FLOW"})
        self.assertNotEqual(after["normative_sha256"], created["normative_sha256"])
        read = lambda symbol: self.harness.client.call(
            "read", {"artifact_id": "SPEC-FLOW", "symbol": symbol, "mode": "exact"})["record"]
        section = read("SEC-SMARTS")
        self.assertEqual(section["title"], "SMARTS design rationale")
        self.assertEqual(section["blocks"], blocks)
        self.assertEqual(read("APPROACH-01")["binding_decision_refs"], ["DEC-01"])
        self.assertEqual(read("DEC-01"), decision)

    def test_producers_create_and_read_canonical_html_pair(self) -> None:
        self.harness.create_pair()
        for artifact_id in ("SPEC-FLOW", "PLAN-FLOW"):
            result = self.harness.client.call(
                "validate", {"artifact_id": artifact_id, "gate": "ready"}, permit_invalid=True
            )
            self.assertTrue(result["valid"], result)
        criterion = self.harness.client.call(
            "read", {"artifact_id": "SPEC-FLOW", "symbol": "AC-001", "mode": "exact"}
        )
        task = self.harness.client.call(
            "read", {"artifact_id": "PLAN-FLOW", "symbol": "T-001", "mode": "exact"}
        )
        self.assertEqual(task["record"]["criterion_refs"], ["SPEC-FLOW#AC-001"])
        self.assertEqual(criterion["record"]["verification"]["planned_target"], "test_environment_overrides")
        self.assertTrue((self.root / ".codearbiter/specs/flow.html").is_file())
        self.assertTrue((self.root / ".codearbiter/plans/flow.html").is_file())
        self.assertEqual(list((self.root / ".codearbiter").rglob("*.md")), [])

    def test_incomplete_draft_is_named_without_inventing_contract_fields(self) -> None:
        self.harness.client.call(
            "create",
            {
                "operation_id": "fixture-incomplete-spec",
                "artifact_id": "SPEC-INCOMPLETE",
                "kind": "spec",
                "slug": "incomplete",
                "title": "Incomplete draft",
                "summary": "Missing intent and criteria on purpose.",
            },
        )
        result = self.harness.client.call(
            "validate",
            {"artifact_id": "SPEC-INCOMPLETE", "gate": "ready"},
            permit_invalid=True,
        )
        self.assertFalse(result["valid"])
        self.assertIn("INTENT", json.dumps(result).upper())
        self.assertNotIn("placeholder", (self.root / ".codearbiter/specs/incomplete.html").read_text())
        identity = self.harness.client.call("identity", {"artifact_id": "SPEC-INCOMPLETE"})
        route = _artifactlib._select_authoring_route(
            self.root, "incomplete", workflow="feature", lane="full", client=self.harness.client)
        self.assertEqual(self._plan_preflight(route, identity["artifact_id"], identity["normative_sha256"]),
                         self.root / ".codearbiter/plans/incomplete.html")
        self.assertFalse((self.root / ".codearbiter/plans/incomplete.html").exists())

    def test_authoring_and_progress_need_no_authority_producers(self) -> None:
        helpers = [self.installation.parent.parent / "hooks" / name for name in
                   ("_approvallib.py", "_prerequisitelib.py", "_artifactauthoritylib.py")]
        originals = {p: p.read_bytes() for p in helpers}
        try:
            for p in helpers:
                p.unlink()
            spec = self.harness.create_spec()
            route = _artifactlib._select_authoring_route(
                self.root, "flow", workflow="feature", lane="full", client=self.harness.client)
            target = self._plan_preflight(route, spec["artifact_id"], spec["normative_sha256"])
            self.assertFalse(target.exists())
            self.harness.create_plan(spec["artifact_id"], spec["normative_sha256"])
            self.harness.mutate("task-start", "PLAN-FLOW", task="T-001")
            self.harness.mutate("task-review", "PLAN-FLOW", task="T-001")
            # An ordinary failed command is recordable without importing the
            # missing approval/reviewer producers. It cannot become ACCEPTED.
            self.harness.mutate("task-check", "PLAN-FLOW", task="T-001", check={
                "argv": ["python", "-m", "unittest", "-v", "tests.test_config"],
                "cwd": ".", "command_index": 0, "outcome": "fail",
                "exit_code": 1, "summary": "A fixture assertion was reported failing.",
                "source": "Synthetic fixture command-output reference.",
                "origin": "agent_report",
            })
            plan_identity = self.harness.client.call("identity", {"artifact_id": "PLAN-FLOW"})
            packet = self.harness.client.call("task-context", {
                "artifact_id": "PLAN-FLOW", "task": "T-001",
                "model_sha256": plan_identity["model_sha256"],
            })
            self.assertEqual(packet["task"]["id"], "T-001")
            self.assertEqual(packet["assessment"], "advisory")
            self.assertFalse(packet["evidence_assessed"])
            self.assertFalse(packet["context_complete"])
            self.assertEqual(packet["reported_checks"][-1]["reported_outcome"], "fail")
            self.assertFalse(packet["checks_are_verified"])
            self.assertFalse(packet["reported_checks"][-1]["named_tests_verified"])
            self.assertEqual(packet["reported_checks"][-1]["worktree_freshness"], "unassessed")
            advice = self.harness.client.call("eligible", {"artifact_id": "PLAN-FLOW"})
            self.assertEqual(advice["assessment"], "advisory")
            self.assertFalse(advice["evidence_assessed"])
            self.assertFalse(any((self.root / ".codearbiter/.artifacts/receipts").glob("*.json")))
            self.assertEqual(list((self.root / ".codearbiter").rglob("*.md")), [])
        finally:
            for p, data in originals.items():
                p.write_bytes(data)

    def test_missing_payload_fails_closed_without_markdown_fallback(self) -> None:
        missing = self.root / "missing-installation"
        missing.mkdir()
        client = ArtifactClient(self.root, missing)
        with self.assertRaises(ArtifactError) as caught:
            client.call("capabilities")
        self.assertEqual(caught.exception.code, "CAPABILITY_MISSING")
        self.assertEqual(list((self.root / ".codearbiter").rglob("*.md")), [])

    def _plan_preflight(
        self, route: dict, artifact_id: str, normative_sha256: str
    ) -> Path:
        preflight = getattr(_artifactlib, "_preflight_plan_authoring", None)
        self.assertIsNotNone(preflight, "private plan-authoring preflight is missing")
        return preflight(
            route,
            self.harness.client,
            spec_artifact_id=artifact_id,
            spec_normative_sha256=normative_sha256,
        )

    def test_plan_preflight_requires_exact_approved_spec_and_binds_exact_html_pair(self) -> None:
        spec = self.harness.create_spec()
        self.harness.approve_spec("SPEC-FLOW")
        approved = self.harness.client.call("identity", {"artifact_id": "SPEC-FLOW"})
        route = _artifactlib._select_authoring_route(
            self.root,
            "flow",
            workflow="feature",
            lane="full",
            client=self.harness.client,
        )

        target = self._plan_preflight(
            route, approved["artifact_id"], approved["normative_sha256"]
        )

        self.assertEqual(target, self.root / ".codearbiter/plans/flow.html")
        self.assertFalse(target.exists())
        self.assertEqual(list((self.root / ".codearbiter").rglob("*.md")), [])
        self.harness.create_plan(spec["artifact_id"], spec["normative_sha256"])
        self.harness.mutate("plan-bind", "PLAN-FLOW", spec_id="SPEC-FLOW")
        pages = list(self.harness.client.contextual_pages("PLAN-FLOW", "T-001", 65536))
        records = {
            item["key"]: item["record"]
            for page in pages
            for item in page["items"]
        }
        binding = records["PLAN-FLOW#@context"]["spec_ref"]
        self.assertEqual(binding["artifact_id"], approved["artifact_id"])
        self.assertEqual(binding["normative_sha256"], approved["normative_sha256"])
        self.assertEqual(binding["binding_mode"], "approved_source")
        self.assertEqual(list((self.root / ".codearbiter").rglob("*.md")), [])

    def test_plan_preflight_accepts_draft_but_rejects_wrong_identity_and_digest(self) -> None:
        spec = self.harness.create_spec()
        route = _artifactlib._select_authoring_route(
            self.root,
            "flow",
            workflow="sprint",
            lane="full",
            client=self.harness.client,
        )
        self.assertEqual(self._plan_preflight(route, spec["artifact_id"], spec["normative_sha256"]),
                         self.root / ".codearbiter/plans/flow.html")

        self.harness.approve_spec("SPEC-FLOW")
        other = self.harness.create_spec("SPEC-OTHER", "other")
        self.harness.approve_spec("SPEC-OTHER")
        with self.assertRaises(ArtifactError):
            self._plan_preflight(route, other["artifact_id"], other["normative_sha256"])
        with self.assertRaises(ArtifactError):
            self._plan_preflight(route, spec["artifact_id"], "0" * 64)
        self.assertEqual(list((self.root / ".codearbiter").rglob("*.md")), [])
        self.assertFalse((self.root / ".codearbiter/plans/flow.html").exists())

    def test_plan_preflight_rejects_forged_client_before_any_call(self) -> None:
        spec = self.harness.create_spec()
        self.harness.approve_spec("SPEC-FLOW")
        route = _artifactlib._select_authoring_route(
            self.root,
            "flow",
            workflow="feature",
            lane="full",
            client=self.harness.client,
        )

        class ForgedClient:
            def __init__(self, root: Path):
                self.root = root
                self.calls = 0

            def call(self, operation: str, request: dict, **kwargs: object) -> dict:
                self.calls += 1
                if operation == "identity":
                    return {
                        "artifact_id": spec["artifact_id"],
                        "kind": "spec",
                        "path": ".codearbiter/specs/flow.html",
                        "normative_sha256": spec["normative_sha256"],
                    }
                return {
                    "valid": True,
                    "artifact_id": spec["artifact_id"],
                    "normative_sha256": spec["normative_sha256"],
                    "authority": {
                        "state": "approved",
                        "authority_verified": True,
                    },
                }

        forged = ForgedClient(self.root)
        preflight = _artifactlib._preflight_plan_authoring

        with self.assertRaises(ArtifactError) as caught:
            preflight(
                route,
                forged,
                spec_artifact_id=spec["artifact_id"],
                spec_normative_sha256=spec["normative_sha256"],
            )

        self.assertEqual(caught.exception.code, "CAPABILITY_MISSING")
        self.assertEqual(forged.calls, 0)

        other_root = self.root.parent / "other-plan-root"
        other_root.mkdir()
        wrong_root = ArtifactClient(other_root, self.installation)
        with mock.patch.object(
            wrong_root,
            "call",
            side_effect=AssertionError("wrong-root client must not be called"),
        ):
            with self.assertRaises(ArtifactError) as wrong_root_error:
                preflight(
                    route,
                    wrong_root,
                    spec_artifact_id=spec["artifact_id"],
                    spec_normative_sha256=spec["normative_sha256"],
                )
        self.assertEqual(wrong_root_error.exception.code, "CAPABILITY_MISSING")

    def test_real_plan_bind_accepts_draft_but_rejects_wrong_spec_binding(self) -> None:
        unapproved = self.harness.create_spec()
        self.harness.create_plan(
            unapproved["artifact_id"], unapproved["normative_sha256"]
        )
        self.harness.mutate("plan-bind", "PLAN-FLOW", spec_id="SPEC-FLOW")
        report = self.harness.client.call("validate", {"artifact_id": "PLAN-FLOW", "gate": "structural"})
        self.assertTrue(report["valid"])
        self.assertFalse(report["authority"]["authority_verified"])

        self.harness.approve_spec("SPEC-FLOW")
        other = self.harness.create_spec("SPEC-OTHER", "other")
        self.harness.approve_spec("SPEC-OTHER")
        with self.assertRaises(ArtifactError):
            self.harness.mutate("plan-bind", "PLAN-FLOW", spec_id="SPEC-OTHER")
        self.assertEqual(list((self.root / ".codearbiter").rglob("*.md")), [])

    def test_plan_preflight_rechecks_namespace_after_identity_or_validation(self) -> None:
        self.harness.create_spec()
        self.harness.approve_spec("SPEC-FLOW")
        identity = self.harness.client.call("identity", {"artifact_id": "SPEC-FLOW"})
        approved = self.harness.client.call(
            "validate",
            {"artifact_id": "SPEC-FLOW", "gate": "approved"},
            permit_invalid=True,
        )

        capability = self.harness.client.call("capabilities")
        for trigger in ("capabilities", "identity", "validate"):
            with self.subTest(trigger=trigger):
                shadow = self.root / ".codearbiter/specs/flow.md"
                shadow.unlink(missing_ok=True)
                route = _artifactlib._select_authoring_route(
                    self.root,
                    "flow",
                    workflow="feature",
                    lane="full",
                    client=self.harness.client,
                )

                def frozen_call(
                    operation: str,
                    request: dict | None = None,
                    **kwargs: object,
                ) -> dict:
                    if operation == trigger:
                        shadow.write_text(
                            "# adversarial legacy shadow\n", encoding="utf-8"
                        )
                    if operation == "capabilities":
                        return capability
                    if operation == "identity":
                        return identity
                    if operation == "validate":
                        self.assertEqual(request["gate"], "structural")
                        return approved
                    raise AssertionError(f"unexpected operation: {operation}")

                with mock.patch.object(
                    self.harness.client, "call", side_effect=frozen_call
                ):
                    with self.assertRaises(ArtifactError) as caught:
                        _artifactlib._preflight_plan_authoring(
                            route,
                            self.harness.client,
                            spec_artifact_id=identity["artifact_id"],
                            spec_normative_sha256=identity["normative_sha256"],
                        )

                self.assertIn(
                    caught.exception.code, {"STALE_ROUTE", "AMBIGUOUS_ARTIFACT"}
                )
                self.assertTrue(shadow.is_file())
                self.assertFalse((self.root / ".codearbiter/plans/flow.html").exists())


if __name__ == "__main__":
    unittest.main(verbosity=2)
