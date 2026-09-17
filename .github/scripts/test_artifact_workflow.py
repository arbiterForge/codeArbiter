#!/usr/bin/env python3
"""Behavioral entry, resume, review and atomic-acceptance fixtures."""

from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from test_artifact_authoring import (
    ArtifactError,
    WorkflowHarness,
    build_installation,
    canonical_hash,
    physical_test_directory,
)
import _artifactlib


REPO = Path(__file__).resolve().parents[2]
FEATURE_COMMAND = REPO / "core" / "surface" / "commands" / "feature.md"
SPRINT_PROCEDURE = REPO / "core" / "surface" / "SPRINT.md"
FINISHING_SKILL = (
    REPO
    / "core"
    / "surface"
    / "skills"
    / "finishing-a-development-branch"
    / "SKILL.md"
)
EXECUTING_SKILL = (
    REPO / "core" / "surface" / "skills" / "executing-plans" / "SKILL.md"
)
SUBAGENT_SKILL = (
    REPO
    / "core"
    / "surface"
    / "skills"
    / "subagent-driven-development"
    / "SKILL.md"
)
COMMIT_GATE_SKILL = (
    REPO / "core" / "surface" / "skills" / "commit-gate" / "SKILL.md"
)
WORKTREE_SKILL = (
    REPO / "core" / "surface" / "skills" / "using-git-worktrees" / "SKILL.md"
)


class ArtifactResumeRouteContractTest(unittest.TestCase):
    def test_feature_discovers_one_complete_exact_format_pair_before_resume(self) -> None:
        feature = FEATURE_COMMAND.read_text(encoding="utf-8")

        self.assertIn("complete same-extension spec/plan pair", feature)
        self.assertIn("select that exact pair as authoritative", feature)
        self.assertIn("mixed-extension or duplicate match is a STOP", feature)
        self.assertIn("A lone spec resumes in its exact format", feature)
        self.assertIn("next plan must use the same extension", feature)
        self.assertIn("must not create, rename, or convert its counterpart", feature)

    def test_resume_reads_state_only_through_the_selected_formats_authority(self) -> None:
        feature = FEATURE_COMMAND.read_text(encoding="utf-8")
        sprint = SPRINT_PROCEDURE.read_text(encoding="utf-8")

        for source in (feature, sprint):
            self.assertIn("HTML pair", source)
            self.assertIn("engine `identity`, `index`, and symbol-scoped `read`", source)
            self.assertIn("Markdown pair", source)
            self.assertIn("existing Markdown status ledger", source)
            self.assertIn("without creating or consulting a shadow artifact", source)

        for source in (
            feature,
            sprint,
            FINISHING_SKILL.read_text(encoding="utf-8"),
            WORKTREE_SKILL.read_text(encoding="utf-8"),
        ):
            self.assertIn("`_resolve_workflow_pair`", source)

    def test_finalization_uses_the_discovered_authoritative_plan(self) -> None:
        finishing = FINISHING_SKILL.read_text(encoding="utf-8")

        self.assertIn("discovered authoritative spec/plan pair", finishing)
        self.assertIn("exact selected `.md` or `.html` plan", finishing)
        self.assertIn("HTML plan state only through the installed engine", finishing)
        self.assertIn("must not create, convert, or consult a counterpart", finishing)

    def test_worktree_planning_preserves_the_selected_pairs_exact_format(self) -> None:
        worktree = WORKTREE_SKILL.read_text(encoding="utf-8")

        self.assertIn("discovered authoritative spec/plan pair", worktree)
        self.assertIn("exact selected plan", worktree)
        self.assertIn("HTML task and path records only through the installed engine", worktree)
        self.assertIn("must not create, convert, or consult a counterpart", worktree)


class ArtifactWorkflowResolverTest(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory(prefix="ca-artifact-resolver-")
        self.addCleanup(self.temporary.cleanup)
        self.root = physical_test_directory(self.temporary.name) / "repo"
        self.root.mkdir()

    def _snapshot(self) -> dict[str, bytes]:
        return {
            path.relative_to(self.root).as_posix(): path.read_bytes()
            for path in self.root.rglob("*")
            if path.is_file()
        }

    def _resolve(self, slug: str = "flow") -> dict[str, object]:
        resolver = getattr(_artifactlib, "_resolve_workflow_pair", None)
        self.assertIsNotNone(resolver, "private workflow resolver is missing")
        return resolver(self.root, slug)

    def _assert_read_only(self, before: dict[str, bytes]) -> None:
        self.assertEqual(self._snapshot(), before)

    def test_absent_pair_defaults_to_html_without_creating_paths(self) -> None:
        before = self._snapshot()

        selected = self._resolve()

        self.assertEqual(selected["format"], "html")
        self.assertEqual(selected["state"], "absent")
        self.assertEqual(selected["spec_path"], self.root / ".codearbiter/specs/flow.html")
        self.assertEqual(selected["plan_path"], self.root / ".codearbiter/plans/flow.html")
        self._assert_read_only(before)

    def test_complete_markdown_and_html_pairs_keep_exact_bytes_and_format(self) -> None:
        for extension in ("md", "html"):
            with self.subTest(extension=extension):
                root = self.root / extension
                root.mkdir()
                spec = root / f".codearbiter/specs/flow.{extension}"
                plan = root / f".codearbiter/plans/flow.{extension}"
                spec.parent.mkdir(parents=True)
                plan.parent.mkdir(parents=True)
                spec.write_bytes(f"spec-{extension}\r\n".encode())
                plan.write_bytes(f"plan-{extension}\x00".encode())
                before = {
                    path.relative_to(root).as_posix(): path.read_bytes()
                    for path in root.rglob("*")
                    if path.is_file()
                }

                resolver = getattr(_artifactlib, "_resolve_workflow_pair", None)
                self.assertIsNotNone(resolver, "private workflow resolver is missing")
                selected = resolver(root, "flow")

                self.assertEqual(selected["format"], extension)
                self.assertEqual(selected["state"], "pair")
                self.assertEqual(selected["spec_path"], spec)
                self.assertEqual(selected["plan_path"], plan)
                after = {
                    path.relative_to(root).as_posix(): path.read_bytes()
                    for path in root.rglob("*")
                    if path.is_file()
                }
                self.assertEqual(after, before)
                counterpart = "html" if extension == "md" else "md"
                self.assertFalse((root / f".codearbiter/specs/flow.{counterpart}").exists())
                self.assertFalse((root / f".codearbiter/plans/flow.{counterpart}").exists())

    def test_lone_markdown_and_html_specs_select_same_extension_future_plan(self) -> None:
        for extension in ("md", "html"):
            with self.subTest(extension=extension):
                root = self.root / extension
                root.mkdir()
                spec = root / f".codearbiter/specs/flow.{extension}"
                spec.parent.mkdir(parents=True)
                spec.write_bytes(f"only-{extension}\r\n".encode())
                original = spec.read_bytes()

                resolver = getattr(_artifactlib, "_resolve_workflow_pair", None)
                self.assertIsNotNone(resolver, "private workflow resolver is missing")
                selected = resolver(root, "flow")

                self.assertEqual(selected["format"], extension)
                self.assertEqual(selected["state"], "spec")
                self.assertEqual(selected["spec_path"], spec)
                self.assertEqual(
                    selected["plan_path"],
                    root / f".codearbiter/plans/flow.{extension}",
                )
                self.assertEqual(spec.read_bytes(), original)
                self.assertFalse(Path(selected["plan_path"]).exists())
                counterpart = "html" if extension == "md" else "md"
                self.assertFalse((root / f".codearbiter/specs/flow.{counterpart}").exists())

    def test_duplicate_specs_or_plans_stop_without_writes(self) -> None:
        cases = {
            "specs": (
                ".codearbiter/specs/flow.md",
                ".codearbiter/specs/flow.html",
            ),
            "plans": (
                ".codearbiter/specs/flow.md",
                ".codearbiter/plans/flow.md",
                ".codearbiter/plans/flow.html",
            ),
        }
        for name, paths in cases.items():
            with self.subTest(name=name):
                root = self.root / name
                root.mkdir()
                for index, relative in enumerate(paths):
                    path = root / relative
                    path.parent.mkdir(parents=True, exist_ok=True)
                    path.write_bytes(f"original-{index}".encode())
                before = {
                    path.relative_to(root).as_posix(): path.read_bytes()
                    for path in root.rglob("*")
                    if path.is_file()
                }
                resolver = getattr(_artifactlib, "_resolve_workflow_pair", None)
                self.assertIsNotNone(resolver, "private workflow resolver is missing")

                with self.assertRaises(ArtifactError) as caught:
                    resolver(root, "flow")

                self.assertEqual(caught.exception.code, "AMBIGUOUS_ARTIFACT")
                after = {
                    path.relative_to(root).as_posix(): path.read_bytes()
                    for path in root.rglob("*")
                    if path.is_file()
                }
                self.assertEqual(after, before)

    def test_plan_without_spec_and_mixed_pair_stop_without_writes(self) -> None:
        cases = {
            "orphan": (".codearbiter/plans/flow.md", "ORPHAN_PLAN"),
            "mixed": (
                (".codearbiter/specs/flow.md", ".codearbiter/plans/flow.html"),
                "AMBIGUOUS_ARTIFACT",
            ),
        }
        for name, definition in cases.items():
            with self.subTest(name=name):
                root = self.root / name
                root.mkdir()
                paths, expected = definition
                if isinstance(paths, str):
                    paths = (paths,)
                for index, relative in enumerate(paths):
                    path = root / relative
                    path.parent.mkdir(parents=True, exist_ok=True)
                    path.write_bytes(f"original-{index}".encode())
                before = {
                    path.relative_to(root).as_posix(): path.read_bytes()
                    for path in root.rglob("*")
                    if path.is_file()
                }
                resolver = getattr(_artifactlib, "_resolve_workflow_pair", None)
                self.assertIsNotNone(resolver, "private workflow resolver is missing")

                with self.assertRaises(ArtifactError) as caught:
                    resolver(root, "flow")

                self.assertEqual(caught.exception.code, expected)
                after = {
                    path.relative_to(root).as_posix(): path.read_bytes()
                    for path in root.rglob("*")
                    if path.is_file()
                }
                self.assertEqual(after, before)

    def test_root_and_slug_are_validated_before_canonical_path_resolution(self) -> None:
        resolver = getattr(_artifactlib, "_resolve_workflow_pair", None)
        self.assertIsNotNone(resolver, "private workflow resolver is missing")
        before = self._snapshot()

        with self.assertRaises(ArtifactError) as slug_error:
            resolver(self.root, "../escape")
        self.assertEqual(slug_error.exception.code, "INVALID_SLUG")

        with self.assertRaises(ArtifactError) as root_error:
            resolver(self.root / "missing", "flow")
        self.assertEqual(root_error.exception.code, "UNSAFE_ROOT")
        self._assert_read_only(before)

    def test_execution_consumers_use_engine_state_and_transitions(self) -> None:
        executing = " ".join(EXECUTING_SKILL.read_text(encoding="utf-8").split())
        subagent = " ".join(SUBAGENT_SKILL.read_text(encoding="utf-8").split())

        for source in (executing, subagent):
            self.assertIn("engine `eligible` response is authoritative", source)
            self.assertIn("`task-start`", source)
            self.assertIn("`task-review`", source)
            self.assertIn("`accept-scope`", source)
            self.assertIn("exact artifact identities and engine-written receipts", source)
            self.assertIn(
                "must not infer authority from rendered text, checkboxes, status words, "
                "digests, or caller-supplied labels",
                source,
            )
            self.assertIn("must not read or write a shadow Markdown ledger", source)

    def test_execution_surfaces_share_the_disabled_default_format_contract(self) -> None:
        sources = tuple(
            " ".join(path.read_text(encoding="utf-8").split())
            for path in (EXECUTING_SKILL, SUBAGENT_SKILL)
        )
        for source in sources:
            self.assertIn("Default rollout remains disabled", source)
            self.assertIn("explicitly requested typed-HTML pilot", source)
            self.assertIn("Existing authoritative Markdown pairs", source)
            self.assertIn("fail closed", source)
            self.assertIn("HTML `--farm` dispatch remains disabled", source)
            self.assertNotIn(
                "new full feature and sprint workflows use HTML by default", source
            )

    def test_execution_consumers_define_process_recreation_resume(self) -> None:
        executing = " ".join(EXECUTING_SKILL.read_text(encoding="utf-8").split())
        subagent = " ".join(SUBAGENT_SKILL.read_text(encoding="utf-8").split())

        for source in (executing, subagent):
            self.assertIn("After process recreation", source)
            self.assertIn("rediscover the same authoritative pair", source)
            self.assertIn("query `identity` and `eligible` again", source)
            self.assertIn("`task-reconcile`", source)
            self.assertIn("fresh complete context ticket", source)
            self.assertIn("REVIEW", source)
            self.assertIn("fresh evidence", source)

    def test_commit_and_finalization_require_current_engine_acceptance(self) -> None:
        commit_gate = " ".join(COMMIT_GATE_SKILL.read_text(encoding="utf-8").split())
        finishing = " ".join(FINISHING_SKILL.read_text(encoding="utf-8").split())

        for source in (commit_gate, finishing):
            self.assertIn("engine `identity` and `eligible`", source)
            self.assertIn("`all_accepted_and_current: true`", source)
            self.assertIn("exact spec and plan identities", source)
            self.assertIn("acceptance receipts", source)
            self.assertIn("must not parse rendered HTML", source)
            self.assertIn("must not consult a shadow Markdown ledger", source)

    def test_consumers_invoke_the_executable_current_acceptance_gate(self) -> None:
        for path in (
            EXECUTING_SKILL,
            SUBAGENT_SKILL,
            COMMIT_GATE_SKILL,
            FINISHING_SKILL,
        ):
            source = path.read_text(encoding="utf-8")
            self.assertIn("`_preflight_current_acceptance`", source, path.as_posix())


class ArtifactWorkflowTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.installation_owner, cls.installation = build_installation()

    @classmethod
    def tearDownClass(cls) -> None:
        if cls.installation_owner is not None:
            cls.installation_owner.cleanup()

    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory(prefix="ca-artifact-workflow-")
        self.addCleanup(self.temporary.cleanup)
        self.root = physical_test_directory(self.temporary.name) / "repo"
        self.root.mkdir()
        self.harness = WorkflowHarness(self.root, self.installation)
        self.harness.create_pair()

    def _acceptance_gate(
        self,
        selected: dict[str, object] | None = None,
        *,
        client: object | None = None,
        spec_artifact_id: str = "SPEC-FLOW",
        plan_artifact_id: str = "PLAN-FLOW",
    ) -> dict[str, object]:
        gate = getattr(_artifactlib, "_preflight_current_acceptance", None)
        self.assertIsNotNone(gate, "private current-acceptance preflight is missing")
        return gate(
            selected or _artifactlib._resolve_workflow_pair(self.root, "flow"),
            client or self.harness.client,
            spec_artifact_id=spec_artifact_id,
            plan_artifact_id=plan_artifact_id,
        )

    def _snapshot(self) -> dict[str, bytes]:
        return {
            path.relative_to(self.root).as_posix(): path.read_bytes()
            for path in self.root.rglob("*")
            if path.is_file()
        }

    def _accept_first_scope(self) -> None:
        self.harness.approve_pair()
        ticket = self.harness.context_ticket("T-001")
        self.harness.mutate(
            "task-start", "PLAN-FLOW", task="T-001", context_ticket=ticket
        )
        self.harness.review_task("T-001")
        self.harness.accept_scope("CP-01", ["T-001"])

    def test_current_acceptance_gate_refuses_draft_before_side_effects(self) -> None:
        before = self._snapshot()

        with self.assertRaises(ArtifactError) as caught:
            self._acceptance_gate()

        self.assertIn(caught.exception.code, {"AUTHORITY_UNVERIFIED", "DRAFT_BINDING"})
        self.assertEqual(self._snapshot(), before)

    def test_current_acceptance_gate_rejects_wrong_identity_and_client_root(self) -> None:
        self._accept_first_scope()
        other_root = self.root.parent / "other"
        other_root.mkdir()
        wrong_client = _artifactlib.ArtifactClient(other_root, self.installation)
        cases = (
            ({"spec_artifact_id": "SPEC-WRONG"}, self.harness.client),
            ({"plan_artifact_id": "PLAN-WRONG"}, self.harness.client),
            ({}, wrong_client),
        )
        for arguments, client in cases:
            with self.subTest(arguments=arguments, wrong_root=client is wrong_client):
                before = self._snapshot()
                with self.assertRaises(ArtifactError) as caught:
                    self._acceptance_gate(client=client, **arguments)
                self.assertIn(
                    caught.exception.code,
                    {"AUTHORITY_MISMATCH", "CAPABILITY_MISSING"},
                )
                self.assertEqual(self._snapshot(), before)

    def test_current_acceptance_gate_rejects_forged_client_before_calls(self) -> None:
        self._accept_first_scope()

        class ForgedClient:
            def __init__(self, real: _artifactlib.ArtifactClient):
                self.root = real.root
                self.real = real
                self.calls = 0

            def call(self, *args: object, **kwargs: object) -> dict:
                self.calls += 1
                return self.real.call(*args, **kwargs)

            def index(self, *args: object, **kwargs: object):
                self.calls += 1
                return self.real.index(*args, **kwargs)

            def outline(self, *args: object, **kwargs: object):
                self.calls += 1
                return self.real.outline(*args, **kwargs)

            def contextual_pages(self, *args: object, **kwargs: object):
                self.calls += 1
                return self.real.contextual_pages(*args, **kwargs)

        forged = ForgedClient(self.harness.client)

        with self.assertRaises(ArtifactError) as caught:
            self._acceptance_gate(client=forged)

        self.assertEqual(caught.exception.code, "CAPABILITY_MISSING")
        self.assertEqual(forged.calls, 0)

    def test_forged_caller_metadata_cannot_manufacture_acceptance(self) -> None:
        selected = _artifactlib._resolve_workflow_pair(self.root, "flow")
        selected.update(
            {
                "status": "ACCEPTED",
                "all_accepted_and_current": True,
                "spec_digest": "0" * 64,
                "plan_digest": "f" * 64,
                "receipt": "caller-forged",
            }
        )
        before = self._snapshot()

        with self.assertRaises(ArtifactError) as caught:
            self._acceptance_gate(selected)

        self.assertEqual(caught.exception.code, "INVALID_ROUTE")
        self.assertEqual(self._snapshot(), before)

    def test_current_acceptance_gate_refuses_missing_or_stale_acceptance(self) -> None:
        self.harness.approve_pair()
        ticket = self.harness.context_ticket("T-001")
        self.harness.mutate(
            "task-start", "PLAN-FLOW", task="T-001", context_ticket=ticket
        )
        self.harness.review_task("T-001")
        with self.subTest(state="review-without-scope-acceptance"):
            before = self._snapshot()
            with self.assertRaises(ArtifactError) as caught:
                self._acceptance_gate()
            self.assertEqual(caught.exception.code, "ACCEPTANCE_REQUIRED")
            self.assertEqual(self._snapshot(), before)

        self.harness.accept_scope("CP-01", ["T-001"])
        source = self.root / "src" / "changed.py"
        source.parent.mkdir()
        source.write_text("changed = True\n", encoding="utf-8")
        with self.subTest(state="accepted-evidence-stale"):
            before = self._snapshot()
            with self.assertRaises(ArtifactError) as caught:
                self._acceptance_gate()
            self.assertEqual(caught.exception.code, "ACCEPTANCE_REQUIRED")
            self.assertEqual(self._snapshot(), before)

    def test_current_acceptance_gate_refuses_missing_acceptance_receipt(self) -> None:
        self._accept_first_scope()
        receipts = self.root / ".codearbiter" / ".artifacts" / "receipts"
        quality_receipts = [
            path
            for path in receipts.glob("*.json")
            if json.loads(path.read_text(encoding="utf-8")).get("kind")
            == "quality_review"
        ]
        self.assertEqual(len(quality_receipts), 1)
        quality_receipts[0].unlink()
        before = self._snapshot()

        with self.assertRaises(ArtifactError):
            self._acceptance_gate()

        self.assertEqual(self._snapshot(), before)

    def test_current_acceptance_gate_refuses_a_plan_rebound_elsewhere(self) -> None:
        root = self.root.parent / "wrong-binding"
        root.mkdir()
        harness = WorkflowHarness(root, self.installation)
        harness.create_spec("SPEC-FLOW", "decoy")
        harness.approve_spec("SPEC-FLOW")
        other = harness.create_spec("SPEC-OTHER", "flow")
        harness.approve_spec("SPEC-OTHER")
        harness.create_plan(
            other["artifact_id"],
            other["normative_sha256"],
            artifact_id="PLAN-FLOW",
            slug="flow",
        )
        harness.mutate("plan-bind", "PLAN-FLOW", spec_id="SPEC-OTHER")
        plan_receipt = harness.capture(
            "PLAN-FLOW",
            "PLAN-FLOW",
            "approval",
            "user_workflow",
            "approved",
            {},
        )
        harness.mutate("approve", "PLAN-FLOW", receipt=plan_receipt)
        ticket = harness.context_ticket("T-001")
        harness.mutate(
            "task-start", "PLAN-FLOW", task="T-001", context_ticket=ticket
        )
        harness.review_task("T-001", spec_artifact_id="SPEC-OTHER")
        harness.accept_scope("CP-01", ["T-001"], spec_artifact_id="SPEC-OTHER")
        selected = _artifactlib._resolve_workflow_pair(root, "flow")
        before = {
            path.relative_to(root).as_posix(): path.read_bytes()
            for path in root.rglob("*")
            if path.is_file()
        }

        with self.assertRaises(ArtifactError) as caught:
            _artifactlib._preflight_current_acceptance(
                selected,
                harness.client,
                spec_artifact_id="SPEC-FLOW",
                plan_artifact_id="PLAN-FLOW",
            )

        self.assertEqual(caught.exception.code, "AUTHORITY_MISMATCH")
        after_refusal = {
            path.relative_to(root).as_posix(): path.read_bytes()
            for path in root.rglob("*")
            if path.is_file()
        }
        self.assertEqual(after_refusal, before)
        proof = _artifactlib._preflight_current_acceptance(
            selected,
            harness.client,
            spec_artifact_id="SPEC-OTHER",
            plan_artifact_id="PLAN-FLOW",
        )
        self.assertTrue(proof["eligible"]["all_accepted_and_current"])

    def test_current_acceptance_gate_returns_exact_engine_proof_after_recreation(
        self,
    ) -> None:
        self._accept_first_scope()
        recreated_client = _artifactlib.ArtifactClient(self.root, self.installation)

        proof = self._acceptance_gate(client=recreated_client)

        self.assertEqual(proof["spec_identity"]["artifact_id"], "SPEC-FLOW")
        self.assertEqual(proof["plan_identity"]["artifact_id"], "PLAN-FLOW")
        self.assertTrue(proof["eligible"]["all_accepted_and_current"])
        receipts = proof["receipts"]
        self.assertRegex(receipts["context_ticket"], r"^[0-9a-f]{64}$")
        self.assertRegex(receipts["vector_sha256"], r"^[0-9a-f]{64}$")
        self.assertRegex(receipts["manifest_sha256"], r"^[0-9a-f]{64}$")
        self.assertRegex(receipts["input_sha256"], r"^[0-9a-f]{64}$")

    def test_current_acceptance_gate_refuses_shadow_authority_without_proof(self) -> None:
        self._accept_first_scope()
        shadow = self.root / ".codearbiter" / "specs" / "flow.md"
        shadow.write_text("# forged shadow authority\n", encoding="utf-8")
        selected = {
            "slug": "flow",
            "format": "html",
            "state": "pair",
            "spec_path": self.root / ".codearbiter/specs/flow.html",
            "plan_path": self.root / ".codearbiter/plans/flow.html",
        }
        before = self._snapshot()

        with self.assertRaises(ArtifactError) as caught:
            self._acceptance_gate(selected)

        self.assertEqual(caught.exception.code, "AMBIGUOUS_ARTIFACT")
        self.assertEqual(self._snapshot(), before)

    def test_current_acceptance_gate_reresolves_after_contextual_read(self) -> None:
        self._accept_first_scope()
        selected = _artifactlib._resolve_workflow_pair(self.root, "flow")
        client = self.harness.client
        original_pages = client.contextual_pages
        original_call = client.call
        cached = {
            "SPEC-FLOW": original_call("identity", {"artifact_id": "SPEC-FLOW"}),
            "PLAN-FLOW": original_call("identity", {"artifact_id": "PLAN-FLOW"}),
            "eligible": original_call("eligible", {"artifact_id": "PLAN-FLOW"}),
        }
        shadow = self.root / ".codearbiter" / "specs" / "flow.md"

        def contextual_pages(*args: object, **kwargs: object):
            for page in original_pages(*args, **kwargs):
                yield page
                shadow.write_text("# late shadow authority\n", encoding="utf-8")

        def stable_call(operation: str, request: dict, **kwargs: object) -> dict:
            if shadow.exists() and operation == "identity":
                return cached[request["artifact_id"]]
            if shadow.exists() and operation == "eligible":
                return cached["eligible"]
            return original_call(operation, request, **kwargs)

        with mock.patch.object(client, "contextual_pages", contextual_pages), mock.patch.object(
            client, "call", stable_call
        ):
            with self.assertRaises(ArtifactError) as caught:
                self._acceptance_gate(selected)

        self.assertEqual(caught.exception.code, "AMBIGUOUS_ARTIFACT")

    def test_draft_or_missing_approval_cannot_dispatch(self) -> None:
        with self.assertRaises(ArtifactError) as caught:
            self.harness.client.call("eligible", {"artifact_id": "PLAN-FLOW"})
        self.assertEqual(caught.exception.code, "DRAFT_BINDING")

    def test_caller_labels_cannot_widen_task_state_authority(self) -> None:
        before = self._snapshot()
        cases = (
            ("prerequisite", "verification_runner", "satisfied"),
            ("reconciliation", "review_workflow", "reconciled"),
        )
        for kind, authority_kind, verdict in cases:
            with self.subTest(kind=kind, authority_kind=authority_kind):
                with self.assertRaises(ArtifactError) as caught:
                    self.harness.capture(
                        "PLAN-FLOW",
                        "T-001",
                        kind,
                        authority_kind,
                        verdict,
                        {},
                    )
                self.assertEqual(caught.exception.code, "AUTHORITY_UNVERIFIED")
                self.assertEqual(self._snapshot(), before)

    def test_approved_pair_dispatches_with_complete_context_and_resumes_in_progress(self) -> None:
        self.harness.approve_pair()
        eligible = self.harness.client.call("eligible", {"artifact_id": "PLAN-FLOW"})
        self.assertEqual(eligible["next_task"], "T-001")
        ticket = self.harness.context_ticket("T-001")
        self.harness.mutate("task-start", "PLAN-FLOW", task="T-001", context_ticket=ticket)
        resumed = self.harness.client.call("eligible", {"artifact_id": "PLAN-FLOW"})
        self.assertEqual(resumed["tasks"][0]["state"], "IN_PROGRESS")
        self.assertFalse(resumed["tasks"][0]["eligible"])

    def test_stale_context_blocks_before_dispatch_side_effect(self) -> None:
        self.harness.approve_pair()
        ticket = self.harness.context_ticket("T-001")
        self.harness.mutate(
            "apply",
            "SPEC-FLOW",
            changes=[
                {
                    "op": "header.update",
                    "fields": {"summary": "Changed after bounded context delivery."},
                }
            ],
        )
        before = self.harness.client.call("identity", {"artifact_id": "PLAN-FLOW"})
        with self.assertRaises(ArtifactError) as caught:
            self.harness.mutate(
                "task-start", "PLAN-FLOW", task="T-001", context_ticket=ticket
            )
        self.assertEqual(caught.exception.code, "STALE_SPEC")
        after = self.harness.client.call("identity", {"artifact_id": "PLAN-FLOW"})
        self.assertEqual(after, before)

    def test_changed_worktree_rejects_review_evidence(self) -> None:
        self.harness.approve_pair()
        ticket = self.harness.context_ticket("T-001")
        self.harness.mutate("task-start", "PLAN-FLOW", task="T-001", context_ticket=ticket)
        verification, review = self.harness.task_receipts("T-001")
        (self.root / "src").mkdir()
        (self.root / "src/config.py").write_text("changed = True\n", encoding="utf-8")
        with self.assertRaises(ArtifactError) as caught:
            self.harness.mutate(
                "task-review",
                "PLAN-FLOW",
                task="T-001",
                verification_receipt=verification,
                review_receipt=review,
            )
        self.assertEqual(caught.exception.code, "STALE_EVIDENCE")
        eligible = self.harness.client.call("eligible", {"artifact_id": "PLAN-FLOW"})
        self.assertEqual(eligible["tasks"][0]["state"], "IN_PROGRESS")

    def test_review_checkpoint_survives_resume_and_scope_acceptance_is_atomic(self) -> None:
        self.harness.approve_pair()
        ticket = self.harness.context_ticket("T-001")
        self.harness.mutate("task-start", "PLAN-FLOW", task="T-001", context_ticket=ticket)
        self.harness.review_task("T-001")

        resumed = WorkflowHarness(self.root, self.installation)
        checkpoint = resumed.client.call("eligible", {"artifact_id": "PLAN-FLOW"})
        self.assertEqual(checkpoint["tasks"][0]["state"], "REVIEW")
        self.assertFalse(checkpoint["all_accepted_and_current"])

        resumed.accept_scope("CP-01", ["T-001"])
        accepted = resumed.client.call("eligible", {"artifact_id": "PLAN-FLOW"})
        self.assertEqual(accepted["tasks"][0]["state"], "ACCEPTED")
        self.assertTrue(accepted["all_accepted_and_current"])

    def test_interrupted_task_reconciles_and_redispatches_after_process_recreation(
        self,
    ) -> None:
        self.harness.approve_pair()
        original_plan = self.harness.client.call(
            "identity", {"artifact_id": "PLAN-FLOW"}
        )
        ticket = self.harness.context_ticket("T-001")
        self.harness.mutate(
            "task-start", "PLAN-FLOW", task="T-001", context_ticket=ticket
        )

        resumed = WorkflowHarness(self.root, self.installation)
        interrupted = resumed.client.call("eligible", {"artifact_id": "PLAN-FLOW"})
        self.assertEqual(interrupted["tasks"][0]["state"], "IN_PROGRESS")
        task = resumed.client.call(
            "read", {"artifact_id": "PLAN-FLOW", "symbol": "T-001", "mode": "exact"}
        )["record"]
        snapshot = resumed.client.call("snapshot", {"artifact_id": "PLAN-FLOW"})
        reconciliation = resumed.capture(
            "PLAN-FLOW",
            "T-001",
            "reconciliation",
            "user_workflow",
            "reconciled",
            {
                "input_sha256": snapshot["sha256"],
                "task_sha256": canonical_hash(task),
                "target_state": "PENDING",
                "assessment": "Synthetic interrupted-task reconciliation fixture.",
            },
        )
        resumed.mutate(
            "task-reconcile",
            "PLAN-FLOW",
            task="T-001",
            receipt=reconciliation,
            state="PENDING",
            reason="Process ended before completion could be established.",
        )
        fresh_ticket = resumed.context_ticket("T-001")
        resumed.mutate(
            "task-start",
            "PLAN-FLOW",
            task="T-001",
            context_ticket=fresh_ticket,
        )
        resumed.review_task("T-001")

        final_process = WorkflowHarness(self.root, self.installation)
        review = final_process.client.call("eligible", {"artifact_id": "PLAN-FLOW"})
        self.assertEqual(review["tasks"][0]["state"], "REVIEW")
        final_process.accept_scope("CP-01", ["T-001"])
        accepted = final_process.client.call("eligible", {"artifact_id": "PLAN-FLOW"})
        current_plan = final_process.client.call(
            "identity", {"artifact_id": "PLAN-FLOW"}
        )
        self.assertEqual(current_plan["artifact_id"], original_plan["artifact_id"])
        self.assertEqual(
            current_plan["normative_sha256"], original_plan["normative_sha256"]
        )
        self.assertEqual(accepted["tasks"][0]["state"], "ACCEPTED")
        self.assertTrue(accepted["all_accepted_and_current"])


if __name__ == "__main__":
    unittest.main(verbosity=2)
