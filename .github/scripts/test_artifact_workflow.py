#!/usr/bin/env python3
"""Behavioral entry, resume, review and atomic-acceptance fixtures."""

from __future__ import annotations

import hashlib
import json
import platform
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from test_artifact_authoring import (
    ArtifactError,
    WorkflowHarness,
    build_installation,
    canonical_hash,
    plan_normative,
    physical_test_directory,
    spec_normative,
)
import _artifactlib
import _artifactauthoritylib


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

    def test_authority_capture_is_bound_to_host_owned_source_bytes(self) -> None:
        source = " ".join(
            (REPO / "core/surface/includes/artifacts.md")
            .read_text(encoding="utf-8")
            .split()
        )
        self.assertIn("arm the exact current artifact", source)
        self.assertIn("require that exact reply", source)
        self.assertIn("records the full armed reply as the host-observed policy-owned source", source)
        self.assertIn("An ordinary `yes`, a changed artifact, a wrong or expired code", source)
        self.assertIn("but nothing else in the message", source)
        self.assertIn("pass it unchanged as the entire AskUserQuestion input", source)
        self.assertIn("`capture` events remain readable for inventory but are inspection-only", source)
        self.assertIn("Current authority requires `capture-observation`", source)
        self.assertIn("still-present policy source", source)
        self.assertIn("0.1.0 remains readable for inspection", source)
        self.assertIn("fresh 0.2.0 attestation", source)
        self.assertIn("cooperative same-user attestation model", source)
        self.assertFalse(hasattr(_artifactlib.ArtifactClient, "capture_workflow_event"))

    def test_execution_surfaces_share_the_enabled_default_format_contract(self) -> None:
        sources = tuple(
            " ".join(path.read_text(encoding="utf-8").split())
            for path in (EXECUTING_SKILL, SUBAGENT_SKILL)
        )
        for source in sources:
            self.assertIn("New full-lane workflows default to HTML", source)
            self.assertIn("Existing authoritative Markdown pairs", source)
            self.assertIn("fail closed", source)
            self.assertIn("HTML `--farm` dispatch remains disabled", source)
            self.assertNotIn("pilot", source.lower())

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


class ArtifactProductionPilotTest(unittest.TestCase):
    """Rollback drill over exact bytes from one real codeArbiter workflow pair.

    The typed model and line dispositions are deliberately fixture-only. This
    proves cutover safety; it does not claim semantic adoption or authority.
    """

    SLUG = "reaudit-ra03-read-only-review-aggregation"
    SPEC_ID = "SPEC-PRODUCTION-PILOT"
    PLAN_ID = "PLAN-PRODUCTION-PILOT"

    @classmethod
    def setUpClass(cls) -> None:
        cls.installation_owner, cls.installation = build_installation()

    @classmethod
    def tearDownClass(cls) -> None:
        if cls.installation_owner is not None:
            cls.installation_owner.cleanup()

    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory(prefix="ca-artifact-pilot-")
        self.addCleanup(self.temporary.cleanup)
        self.root = physical_test_directory(self.temporary.name) / "repo"
        (self.root / ".codearbiter/specs").mkdir(parents=True)
        (self.root / ".codearbiter/plans").mkdir(parents=True)
        self.sources = {
            "spec": REPO / ".codearbiter/specs" / f"{self.SLUG}.md",
            "plan": REPO / ".codearbiter/plans" / f"{self.SLUG}.md",
        }
        self.paths = {
            kind: self.root / ".codearbiter" / f"{kind}s" / f"{self.SLUG}.md"
            for kind in ("spec", "plan")
        }
        self.original = {
            kind: source.read_bytes() for kind, source in self.sources.items()
        }
        for kind, path in self.paths.items():
            path.write_bytes(self.original[kind])

    def _request(self) -> dict[str, object]:
        def item(kind: str, artifact_id: str, normative: dict, target: str) -> dict:
            return {
                "source_path": f".codearbiter/{kind}s/{self.SLUG}.md",
                "artifact_id": artifact_id,
                "slug": self.SLUG,
                "normative": normative,
                "mappings": [{
                    "start_line": 1,
                    "end_line": len(self.original[kind].decode("utf-8").splitlines()),
                    "target": target,
                    "disposition": "historical",
                    "reason": "Safety-only pilot mapping; no semantic adoption or authority transfer.",
                }],
            }

        return {
            "spec": item("spec", self.SPEC_ID, spec_normative(), "INTENT-01"),
            "plan": item(
                "plan",
                self.PLAN_ID,
                plan_normative(self.SPEC_ID, "0" * 64),
                "T-001",
            ),
        }

    def test_production_pair_cutover_survives_recreation_and_rolls_back_exactly(self) -> None:
        attributes = (REPO / ".gitattributes").read_text(encoding="utf-8")
        for kind in ("spec", "plan"):
            self.assertIn(
                f"/.codearbiter/{kind}s/{self.SLUG}.md text eol=lf",
                attributes,
            )
        before = {kind: hashlib.sha256(raw).hexdigest() for kind, raw in self.original.items()}
        evidence = json.loads(
            (REPO / "docs/artifacts/DEFAULT-ROLLOUT-PILOT.json").read_text(
                encoding="utf-8"
            )
        )
        self.assertEqual(evidence["selected_pair"]["slug"], self.SLUG)
        self.assertEqual(
            set(evidence),
            {
                "format",
                "observed_at_utc",
                "status",
                "scope",
                "selected_pair",
                "local_unverified_observation",
                "cases",
                "related_current_evidence",
                "limitations",
            },
        )
        self.assertEqual(evidence["format"], "codearbiter.default-rollout-pilot/0.1.0")
        self.assertRegex(evidence["observed_at_utc"], r"^2026-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z$")
        self.assertEqual(evidence["status"], "local_candidate_pass_hosted_exact_head_pending")
        self.assertEqual(
            evidence["scope"],
            {
                "repository": "arbiterForge/codeArbiter",
                "base_commit": "1281de39d4877f8935f8f424a0b15f32955fb568",
                "execution": "exact production bytes copied into a disposable isolated repository root",
                "authoritative_repository_mutated": False,
            },
        )
        self.assertEqual(set(evidence["selected_pair"]), {"slug", "spec", "plan"})
        self.assertEqual(
            {
                kind: evidence["selected_pair"][kind]["sha256"]
                for kind in ("spec", "plan")
            },
            before,
        )
        for kind, lines in (("spec", 34), ("plan", 131)):
            self.assertEqual(
                set(evidence["selected_pair"][kind]), {"path", "sha256", "lines"}
            )
            self.assertEqual(
                evidence["selected_pair"][kind]["path"],
                f".codearbiter/{kind}s/{self.SLUG}.md",
            )
            self.assertEqual(evidence["selected_pair"][kind]["lines"], lines)
        observation = evidence["local_unverified_observation"]
        self.assertEqual(
            set(observation),
            {
                "authority",
                "platform",
                "binary_sha256",
                "release_manifest_sha256",
                "module_tests_passed_before_candidate_build",
                "upstream_host_qualified_by_local_build",
            },
        )
        self.assertEqual(observation["authority"], "local_unverified_not_ci_qualification")
        self.assertTrue(observation["module_tests_passed_before_candidate_build"])
        self.assertFalse(observation["upstream_host_qualified_by_local_build"])
        if platform.system() == "Windows" and platform.machine().lower() == "amd64":
            manifest_bytes = (self.installation / "release.json").read_bytes()
            manifest = json.loads(manifest_bytes)
            entry = manifest["binaries"]["windows/amd64"]
            self.assertEqual(observation["platform"], "windows/amd64")
            # This receipt describes the historical local pilot, not each later
            # candidate binary. Keep its recorded hashes well formed while the
            # current installation is verified against its own release manifest.
            self.assertRegex(observation["release_manifest_sha256"], r"^[0-9a-f]{64}$")
            self.assertRegex(observation["binary_sha256"], r"^[0-9a-f]{64}$")
            self.assertEqual(
                entry["sha256"],
                hashlib.sha256((self.installation / entry["file"]).read_bytes()).hexdigest(),
            )
        expected_cases = {
            "upgrade-inertness": "test_capability_upgrade_does_not_reinterpret_legacy_pair",
            "explicit-cutover": self._testMethodName,
            "interruption-recreation": self._testMethodName,
            "downgrade-refusal": self._testMethodName,
            "exact-byte-rollback": self._testMethodName,
            "dispatch-stop": self._testMethodName,
        }
        self.assertEqual(
            {case["id"]: case["test"] for case in evidence["cases"]}, expected_cases
        )
        for case in evidence["cases"]:
            self.assertEqual(set(case), {"id", "test", "result", "proof"})
            self.assertEqual(case["result"], "local_pass_hosted_pending")
            self.assertIsInstance(case["proof"], str)
            self.assertGreater(len(case["proof"]), 40)
        self.assertEqual(
            evidence["related_current_evidence"],
            {
                "normal_html_lifecycle": ".github/scripts/test_artifact_installed_host.py",
                "native_browser_review": "docs/artifacts/browser-qualification.json",
                "historical_pilot_not_current_evidence": "docs/artifacts/T024-PILOT-EVIDENCE.json",
            },
        )
        self.assertEqual(len(evidence["limitations"]), 6)
        self.assertTrue(all(isinstance(item, str) and item for item in evidence["limitations"]))
        client = _artifactlib.ArtifactClient(self.root, self.installation)
        request = self._request()
        preview = client.call("migration-preview", request)
        self.assertFalse(preview["semantic_mapping_verified"])
        self.assertFalse(preview["old_approval_transferred"])
        self.assertEqual(
            {kind: self.paths[kind].read_bytes() for kind in self.paths}, self.original
        )
        self.assertFalse(
            (self.root / ".codearbiter/specs" / f"{self.SLUG}.html").exists()
        )
        self.assertFalse(
            (self.root / ".codearbiter/plans" / f"{self.SLUG}.html").exists()
        )

        request.update({
            "operation_id": "pilot-cutover-001",
            "preview_sha256": preview["preview_sha256"],
            "review": {
                "actor": "automated safety pilot",
                "origin": ".github/scripts/test_artifact_workflow.py",
                "source_text": "Fixture-only complete line disposition; not semantic or implementation approval.",
            },
        })
        applied = client.call("migration-apply", request)
        self.assertEqual(applied["state"], "draft")
        self.assertFalse(applied["old_approvals_transferred"])
        self.assertEqual(
            _artifactlib._resolve_workflow_pair(self.root, self.SLUG)["format"],
            "html",
        )
        self.assertTrue(all(not path.exists() for path in self.paths.values()))

        journal_path = (
            self.root
            / ".codearbiter/.artifacts/transactions/pilot-cutover-001.json"
        )
        cutover = json.loads(journal_path.read_text(encoding="utf-8"))
        plan_html_entry = next(
            entry for entry in cutover["entries"] if entry["path"].endswith("/" + self.SLUG + ".html")
            and "/plans/" in entry["path"]
        )
        plan_md_entry = next(
            entry for entry in cutover["entries"] if entry["path"].endswith("/" + self.SLUG + ".md")
            and "/plans/" in entry["path"]
        )
        plan_html_path = self.root / plan_html_entry["path"]
        plan_stage_path = self.root / plan_html_entry["stage"]
        plan_stage_path.write_bytes(plan_html_path.read_bytes())
        plan_html_path.unlink()
        self.paths["plan"].write_bytes(
            (self.root / plan_md_entry["backup"]).read_bytes()
        )
        cutover["state"] = "prepared"
        journal_path.write_bytes(
            json.dumps(
                cutover,
                ensure_ascii=True,
                allow_nan=False,
                sort_keys=True,
                separators=(",", ":"),
            ).encode("utf-8")
        )

        recreated = _artifactlib.ArtifactClient(self.root, self.installation)
        with self.assertRaises(ArtifactError) as mixed:
            _artifactlib._resolve_workflow_pair(self.root, self.SLUG)
        self.assertEqual(mixed.exception.code, "AMBIGUOUS_ARTIFACT")
        with self.assertRaises(ArtifactError) as pending:
            recreated.call("identity", {"artifact_id": self.SPEC_ID})
        self.assertEqual(pending.exception.code, "RECOVERY_REQUIRED")
        dispatch_reached = False
        try:
            selected = _artifactlib._resolve_workflow_pair(self.root, self.SLUG)
            _artifactlib._preflight_current_acceptance(
                selected,
                recreated,
                spec_artifact_id=self.SPEC_ID,
                plan_artifact_id=self.PLAN_ID,
            )
            dispatch_reached = True
        except ArtifactError as stopped:
            self.assertIn(stopped.code, {"AMBIGUOUS_ARTIFACT", "RECOVERY_REQUIRED"})
        self.assertFalse(dispatch_reached)

        recovered = recreated.call(
            "recover", {"operation_id": "pilot-cutover-001", "mode": "complete"}
        )
        self.assertEqual(recovered["state"], "committed")
        self.assertFalse(recovered["replay"])
        self.assertEqual(
            _artifactlib._resolve_workflow_pair(self.root, self.SLUG)["format"],
            "html",
        )
        self.assertTrue(all(not path.exists() for path in self.paths.values()))

        replayed = recreated.call("migration-apply", request)
        self.assertEqual(
            {key: value for key, value in replayed.items() if key != "transaction"},
            {key: value for key, value in applied.items() if key != "transaction"},
        )
        self.assertFalse(applied["transaction"]["replay"])
        self.assertTrue(replayed["transaction"]["replay"])
        self.assertEqual(
            {key: value for key, value in replayed["transaction"].items() if key != "replay"},
            {key: value for key, value in applied["transaction"].items() if key != "replay"},
        )
        for artifact_id in (self.SPEC_ID, self.PLAN_ID):
            identity = recreated.call("identity", {"artifact_id": artifact_id})
            self.assertEqual(identity["artifact_id"], artifact_id)
        with self.assertRaises(ArtifactError) as draft:
            _artifactlib._preflight_current_acceptance(
                _artifactlib._resolve_workflow_pair(self.root, self.SLUG),
                recreated,
                spec_artifact_id=self.SPEC_ID,
                plan_artifact_id=self.PLAN_ID,
            )
        self.assertIn(draft.exception.code, {"AUTHORITY_UNVERIFIED", "DRAFT_BINDING"})

        missing_installation = self.root.parent / "downgraded-without-payload"
        missing_installation.mkdir()
        downgraded = _artifactlib.ArtifactClient(self.root, missing_installation)
        with self.assertRaises(ArtifactError) as unavailable:
            downgraded.call("capabilities")
        self.assertEqual(unavailable.exception.code, "CAPABILITY_MISSING")
        selected = _artifactlib._resolve_workflow_pair(self.root, self.SLUG)
        self.assertEqual(selected["format"], "html")
        self.assertTrue(all(not path.exists() for path in self.paths.values()))

        rolled_back = recreated.call("migration-rollback", {
            "operation_id": "pilot-rollback-001",
            "cutover_operation_id": "pilot-cutover-001",
        })
        self.assertTrue(rolled_back["refresh_required"])
        selected = _artifactlib._resolve_workflow_pair(self.root, self.SLUG)
        self.assertEqual((selected["format"], selected["state"]), ("md", "pair"))
        self.assertEqual(
            {
                kind: hashlib.sha256(path.read_bytes()).hexdigest()
                for kind, path in self.paths.items()
            },
            before,
        )
        self.assertTrue(
            all(
                self.paths[kind].read_bytes() == self.original[kind]
                for kind in self.paths
            )
        )
        self.assertFalse((self.root / ".codearbiter/specs" / f"{self.SLUG}.html").exists())
        self.assertFalse((self.root / ".codearbiter/plans" / f"{self.SLUG}.html").exists())
        cutover = json.loads(journal_path.read_text(encoding="utf-8"))
        rollback_path = (
            self.root
            / ".codearbiter/.artifacts/transactions/pilot-rollback-001.json"
        )
        rollback = json.loads(rollback_path.read_text(encoding="utf-8"))
        for journal, operation_id in (
            (cutover, "pilot-cutover-001"),
            (rollback, "pilot-rollback-001"),
        ):
            self.assertEqual(
                set(journal),
                {"format", "operation_id", "request_sha256", "state", "entries", "result"},
            )
            self.assertEqual(journal["format"], "codearbiter.transaction/0.2.0")
            self.assertEqual(journal["operation_id"], operation_id)
            self.assertEqual(journal["state"], "committed")
            self.assertRegex(journal["request_sha256"], r"^[0-9a-f]{64}$")
            self.assertEqual(len(journal["entries"]), 4)
        self.assertEqual(cutover["result"]["preview_sha256"], preview["preview_sha256"])
        cutover_entries = {entry["path"]: entry for entry in cutover["entries"]}
        rollback_entries = {entry["path"]: entry for entry in rollback["entries"]}
        self.assertEqual(set(cutover_entries), set(rollback_entries))
        for kind in ("spec", "plan"):
            md_path = f".codearbiter/{kind}s/{self.SLUG}.md"
            html_path = f".codearbiter/{kind}s/{self.SLUG}.html"
            md_entry = cutover_entries[md_path]
            html_entry = cutover_entries[html_path]
            self.assertEqual(md_entry["before_sha256"], before[kind])
            self.assertIsNone(md_entry["after_sha256"])
            self.assertIsNone(html_entry["before_sha256"])
            self.assertRegex(html_entry["after_sha256"], r"^[0-9a-f]{64}$")
            self.assertEqual(
                hashlib.sha256((self.root / md_entry["backup"]).read_bytes()).hexdigest(),
                before[kind],
            )
            self.assertEqual(
                rollback_entries[md_path]["after_sha256"], md_entry["before_sha256"]
            )
            self.assertEqual(
                rollback_entries[html_path]["before_sha256"], html_entry["after_sha256"]
            )


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

    def test_current_acceptance_gate_refuses_missing_host_authority_source(self) -> None:
        self._accept_first_scope()
        receipts = self.root / ".codearbiter" / ".artifacts" / "receipts"
        quality_receipts = [
            json.loads(path.read_text(encoding="utf-8"))
            for path in receipts.glob("*.json")
            if json.loads(path.read_text(encoding="utf-8")).get("kind")
            == "quality_review"
        ]
        self.assertEqual(len(quality_receipts), 1)
        source = self.root / quality_receipts[0]["authority_source_ref"]
        source.unlink()
        before = self._snapshot()

        with self.assertRaises(ArtifactError) as caught:
            self._acceptance_gate()

        self.assertIn(
            caught.exception.code,
            {"AUTHORITY_UNVERIFIED", "ACCEPTANCE_REQUIRED"},
        )
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
        cases = (
            ("prerequisite", "verification_runner", "satisfied"),
            ("reconciliation", "review_workflow", "reconciled"),
        )
        for kind, authority_kind, verdict in cases:
            with self.subTest(kind=kind, authority_kind=authority_kind):
                before = self._snapshot()
                with self.assertRaises(_artifactauthoritylib.AuthorityError) as caught:
                    self.harness.capture(
                        "PLAN-FLOW",
                        "T-001",
                        kind,
                        authority_kind,
                        verdict,
                        {},
                    )
                self.assertEqual(caught.exception.code, "INVALID_PROMPT_EVENT")
                after = self._snapshot()
                for path, contents in before.items():
                    self.assertEqual(after.get(path), contents, path)
                self.assertEqual(set(after), set(before))

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
