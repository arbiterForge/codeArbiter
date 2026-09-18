#!/usr/bin/env python3
"""Behavioral producer fixtures for the typed spec/plan authoring path.

The receipts in this file are synthetic workflow events. They exercise the
existing authority boundary but do not approve this package or any real plan.
"""

from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest import mock


REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO / "core" / "pysrc"))

import _artifactlib  # noqa: E402
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
            "pilot_or_default_off_language": "pilot" in normalized or default_off,
        }

    def test_composed_authoring_instructions_define_one_default_contract(self) -> None:
        sources = {
            "feature": FEATURE_COMMAND,
            "sprint": SPRINT_PROCEDURE,
            "brainstorming": BRAINSTORMING_SKILL,
            "artifacts-include": ARTIFACTS_INCLUDE,
        }
        expected = {
            "default_format": "md",
            "capability_before_write": True,
            "existing_markdown": True,
            "html_farm": "disabled",
            "pilot_or_default_off_language": True,
        }

        observed = {
            name: self._contract(path.read_text(encoding="utf-8"))
            for name, path in sources.items()
        }

        self.assertEqual(observed, {name: expected for name in sources})

    def test_html_requires_explicit_pilot_without_markdown_fallback(self) -> None:
        feature = FEATURE_COMMAND.read_text(encoding="utf-8")
        sprint = SPRINT_PROCEDURE.read_text(encoding="utf-8")
        brainstorming = BRAINSTORMING_SKILL.read_text(encoding="utf-8")

        for source in (feature, sprint, brainstorming):
            self.assertIn("`_select_authoring_route`", source)
            self.assertIn("explicit", source.lower())
            self.assertIn("html_requested: true", source)
            self.assertIn(".html", source)
            self.assertIn("before writing", source)
            self.assertIn("must not fall back to Markdown", source)

        for source in (feature, sprint, brainstorming):
            self.assertIn("remains Markdown by default", " ".join(source.split()))

    def test_feature_small_lane_remains_inline_and_does_not_create_an_artifact(self) -> None:
        feature = FEATURE_COMMAND.read_text(encoding="utf-8")

        self.assertIn("Small-lane behavior is unchanged", feature)
        self.assertIn("does not create a spec artifact", feature)
        self.assertIn("state the mini-spec inline", feature)

    def test_plan_creation_uses_engine_and_binds_the_approved_html_spec(self) -> None:
        writing_plans = WRITING_PLANS_SKILL.read_text(encoding="utf-8")

        self.assertIn("`_preflight_plan_authoring`", writing_plans)
        self.assertIn("new full-lane HTML spec", writing_plans)
        self.assertIn("installed structured-artifact engine", writing_plans)
        self.assertIn("`.codearbiter/plans/<slug>.html`", writing_plans)
        self.assertIn("`draft_preview`", writing_plans)
        self.assertIn("`plan-bind`", writing_plans)
        self.assertIn("approved spec's exact artifact ID and normative digest", writing_plans)
        self.assertIn("must not create `.codearbiter/plans/<slug>.md`", writing_plans)

    def test_tdd_reads_typed_obligations_without_parsing_rendered_html(self) -> None:
        tdd = TDD_SKILL.read_text(encoding="utf-8")

        self.assertIn("installed structured-artifact engine", tdd)
        self.assertIn("typed `index`, `outline`, and symbol-scoped `read`", tdd)
        self.assertIn("exact artifact ID and criterion ID", tdd)
        self.assertIn("must not parse rendered HTML", tdd)
        self.assertIn("caller-supplied labels cannot manufacture obligations", tdd)


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

    def test_full_feature_and_sprint_default_to_markdown_without_writing(self) -> None:
        for workflow in ("feature", "sprint"):
            with self.subTest(workflow=workflow):
                before = self._snapshot()

                selected = self._select(workflow, "full")

                self.assertEqual(selected["mode"], "artifact")
                self.assertEqual(selected["workflow"], workflow)
                self.assertEqual(selected["format"], "md")
                self.assertEqual(selected["state"], "absent")
                self.assertEqual(
                    selected["spec_path"], self.root / ".codearbiter/specs/flow.md"
                )
                self.assertEqual(
                    selected["plan_path"], self.root / ".codearbiter/plans/flow.md"
                )
                self.assertEqual(self._snapshot(), before)

    def test_explicit_html_pilot_selects_html_after_capability_probe(self) -> None:
        client = ArtifactClient(self.root, self.installation)
        before = self._snapshot()

        selected = self._select(
            "feature", "full", client, html_requested=True
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
            self._select("feature", "full", client, html_requested=True)

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
                self._select("sprint", "full", client, html_requested=True)

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
                    self._select("sprint", "full", client, html_requested=True)
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
            return {"protocol": "codearbiter.artifact-api/0.1.0"}

        with mock.patch.object(client, "call", side_effect=inject):
            with self.assertRaises(ArtifactError) as caught:
                self._select("feature", "full", client, html_requested=True)

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
        "argv": ["python", "-m", "unittest", "tests.test_config"],
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
    supplied = os.environ.get("ARTIFACT_TEST_INSTALLATION")
    if supplied:
        installation = Path(supplied).resolve()
        if not installation.is_dir():
            raise AssertionError(f"ARTIFACT_TEST_INSTALLATION is not a directory: {installation}")
        return None, installation
    temporary = tempfile.TemporaryDirectory(prefix="ca-artifact-authoring-install-")
    if owner is not None:
        owner.addCleanup(temporary.cleanup)
    installation = physical_test_directory(temporary.name) / "payload"
    subprocess.run(
        [sys.executable, str(REPO / "tools" / "build-artifacts.py"), "--output", str(installation)],
        cwd=REPO,
        text=True,
        capture_output=True,
        check=True,
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
        event = {
                "format": "codearbiter.workflow-event/0.1.0",
                "kind": kind,
                "authority_kind": authority_kind,
                "subject": {
                    "artifact_id": artifact_id,
                    "normative_sha256": identity["normative_sha256"],
                    "record_id": record_id,
                },
                "actor": "synthetic behavioral fixture",
                "origin": f"isolated test {self.operation_id('event')}",
                "verdict": verdict,
                "payload": payload,
                "source_text": "Synthetic event for boundary testing; not production authority.",
            }
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
            "capture",
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

    def test_plan_preflight_rejects_unapproved_wrong_identity_and_wrong_digest(self) -> None:
        spec = self.harness.create_spec()
        route = _artifactlib._select_authoring_route(
            self.root,
            "flow",
            workflow="sprint",
            lane="full",
            client=self.harness.client,
        )
        with self.assertRaises(ArtifactError):
            self._plan_preflight(route, spec["artifact_id"], spec["normative_sha256"])

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

    def test_real_plan_bind_rejects_unapproved_or_wrong_spec_binding(self) -> None:
        unapproved = self.harness.create_spec()
        self.harness.create_plan(
            unapproved["artifact_id"], unapproved["normative_sha256"]
        )
        with self.assertRaises(ArtifactError):
            self.harness.mutate("plan-bind", "PLAN-FLOW", spec_id="SPEC-FLOW")

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

        for trigger in ("identity", "validate"):
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
                    if operation == "identity":
                        return identity
                    if operation == "validate":
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
