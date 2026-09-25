#!/usr/bin/env python3
"""Independent cross-kind reference and whole-workflow conformance checks."""
from __future__ import annotations

import json
import hashlib
import os
from pathlib import Path
import platform
import re
import subprocess
import sys
import tempfile
import unittest

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO / "core/pysrc"))
sys.path.insert(0, str(REPO / ".github/scripts"))
from _artifactlib import ArtifactClient, ArtifactError
from test_artifact_authoring import WorkflowHarness, physical_test_directory

INSTALLATION: Path | None = None
INSTALLATION_OWNER: tempfile.TemporaryDirectory | None = None
CANDIDATE_IDENTITY: tuple[str, str, str, int, int] | None = None

CURRENT_GOLDEN = {
    "spec": {
        "normative": "c14d6ac6673cb032ef42f1e3cd03e557eec10fba716bfd8831ae17d7cea83560",
        "model": "3c509e9042b40599b51c27c8881219c1ca99f49f55abf6e72292a8de6f2a3620",
        "html": "6432d7bb6241c6ae620bcda669698f9985ae4e57f949b2f5292de5e72771d043",
    },
    "plan": {
        "normative": "8cbb42800e1ce9ef86405decadbcf84bd6486515616d7cc3cce34d731f342830",
        "model": "cd0647912158fb02bd1681c116a4500b2f9bde6c91041d80467d71d1ebbc247e",
        "html": "977ee61b675d717a33519d07cb9a06b3f5b3195aad9c312e661d8b792b7b8626",
    },
}

EXPECTED_SUITES = {
    "test_artifact_bridge.py": {
        "test_real_cli_draft_and_index", "test_tampered_view_is_not_readable",
        "test_unknown_request_fields", "test_changed_installed_binary",
        "test_symlink_binary_rejected", "test_linked_or_reparse_installation_directory_rejected",
        "test_artifact_mutations_never_execute_content",
        "test_helper_child_receives_no_parent_environment",
        "test_darwin_staging_uses_only_the_verified_open_descriptor",
        "test_existing_html_mutation_revalidates_payload_before_writing",
        "test_legacy_markdown_route_remains_usable_with_missing_payload",
        "test_new_html_route_reports_actionable_capability_error_before_writing",
    },
    "test_artifact_authoring.py": {
        "test_installed_intent_cli_accepts_native_empty_diagnostics",
        "test_installed_intent_cli_reports_incomplete_native_draft",
        "test_fixture_copy_excludes_stale_payload_before_using_supplied_artifacts",
        "test_fixture_copy_excludes_stale_payload_before_building_artifacts",
        "test_admission_rechecks_namespace_after_host_resource_scan",
        "test_admission_rechecks_before_plan_identity_reads",
        "test_admission_accepts_current_codex_resources_without_conveying_authority",
        "test_admission_accepts_merged_claude_authority_resources",
        "test_admission_checks_the_platform_specific_hook_command",
        "test_admission_does_not_follow_environment_or_project_host_claims",
        "test_admission_preserves_small_lane_and_existing_markdown_on_pi",
        "test_admission_rechecks_resources_after_initial_success",
        "test_admission_refuses_missing_producers_and_host_helpers",
        "test_admission_refuses_pi_before_any_new_full_lane_artifact",
        "test_admission_rejects_bare_engine_installation",
        "test_admission_rejects_linked_helper_ancestors",
        "test_admission_rejects_malformed_duplicate_and_oversized_registry",
        "test_admission_rejects_nonregular_required_resource",
        "test_admission_rejects_nonstring_registered_commands",
        "test_admission_rejects_unknown_ambiguous_or_missing_host_identity",
        "test_admission_rejects_wrong_matchers_redirected_commands_and_async_hooks",
        "test_admission_requires_claude_failure_event_and_reviewer_charter",
        "test_admission_requires_every_authority_event",
        "test_producers_create_and_read_canonical_html_pair",
        "test_incomplete_draft_is_named_without_inventing_contract_fields",
        "test_missing_payload_fails_closed_without_markdown_fallback",
        "test_resolves_a_test_owned_linked_ancestor",
        "test_composed_authoring_instructions_define_one_default_contract",
        "test_existing_pair_selection_delegates_to_exact_format_resolver",
        "test_legacy_html_requested_flag_does_not_change_the_html_default",
        "test_feature_small_lane_remains_inline_and_does_not_create_an_artifact",
        "test_forged_client_is_rejected_before_authoring_capability_call",
        "test_full_feature_and_sprint_default_to_html_after_capability_probe",
        "test_html_is_the_full_lane_default_without_markdown_fallback",
        "test_disabled_or_read_only_capability_fails_before_authoring_writes",
        "test_missing_or_invalid_capability_fails_before_authoring_writes",
        "test_plan_creation_uses_engine_and_binds_the_approved_html_spec",
        "test_plan_preflight_rechecks_namespace_after_identity_or_validation",
        "test_plan_preflight_rejects_forged_client_before_any_call",
        "test_plan_preflight_rejects_unapproved_wrong_identity_and_wrong_digest",
        "test_plan_preflight_requires_exact_approved_spec_and_binds_exact_html_pair",
        "test_real_client_for_another_root_is_rejected_before_capability_call",
        "test_real_plan_bind_rejects_unapproved_or_wrong_spec_binding",
        "test_selection_rechecks_namespace_after_capability_probe",
        "test_small_lane_stays_inline_without_resolving_or_writing_artifacts",
        "test_tdd_reads_typed_obligations_without_parsing_rendered_html",
    },
    "test_artifact_workflow.py": {
        "test_draft_or_missing_approval_cannot_dispatch",
        "test_authority_capture_is_bound_to_host_owned_source_bytes",
        "test_approved_pair_dispatches_with_complete_context_and_resumes_in_progress",
        "test_stale_context_blocks_before_dispatch_side_effect",
        "test_changed_worktree_rejects_review_evidence",
        "test_review_checkpoint_survives_resume_and_scope_acceptance_is_atomic",
        "test_absent_pair_defaults_to_html_without_creating_paths",
        "test_caller_labels_cannot_widen_task_state_authority",
        "test_commit_and_finalization_require_current_engine_acceptance",
        "test_complete_markdown_and_html_pairs_keep_exact_bytes_and_format",
        "test_consumers_invoke_the_executable_current_acceptance_gate",
        "test_current_acceptance_gate_refuses_a_plan_rebound_elsewhere",
        "test_current_acceptance_gate_refuses_draft_before_side_effects",
        "test_current_acceptance_gate_refuses_missing_acceptance_receipt",
        "test_current_acceptance_gate_refuses_missing_host_authority_source",
        "test_current_acceptance_gate_refuses_missing_or_stale_acceptance",
        "test_current_acceptance_gate_refuses_shadow_authority_without_proof",
        "test_current_acceptance_gate_rejects_forged_client_before_calls",
        "test_current_acceptance_gate_rejects_wrong_identity_and_client_root",
        "test_current_acceptance_gate_reresolves_after_contextual_read",
        "test_current_acceptance_gate_returns_exact_engine_proof_after_recreation",
        "test_duplicate_specs_or_plans_stop_without_writes",
        "test_execution_consumers_define_process_recreation_resume",
        "test_execution_consumers_use_engine_state_and_transitions",
        "test_execution_surfaces_share_the_enabled_default_format_contract",
        "test_feature_discovers_one_complete_exact_format_pair_before_resume",
        "test_finalization_uses_the_discovered_authoritative_plan",
        "test_forged_caller_metadata_cannot_manufacture_acceptance",
        "test_interrupted_task_reconciles_and_redispatches_after_process_recreation",
        "test_lone_markdown_and_html_specs_select_same_extension_future_plan",
        "test_plan_without_spec_and_mixed_pair_stop_without_writes",
        "test_production_pair_cutover_survives_recreation_and_rolls_back_exactly",
        "test_resume_reads_state_only_through_the_selected_formats_authority",
        "test_root_and_slug_are_validated_before_canonical_path_resolution",
        "test_worktree_planning_preserves_the_selected_pairs_exact_format",
    },
    "test_artifact_farm.py": {
        "test_projection_binding_and_canary_preflight",
        "test_only_provider_enrichment_can_be_sealed_for_dispatch",
        "test_source_change_invalidates_canary_binding",
        "test_real_dispatcher_blocks_unbound_html_before_side_effects",
        "test_dispatcher_rejects_projection_bytes_other_than_the_parsed_bytes",
        "test_dispatcher_rejects_linked_plugin_installation_ancestors",
        "test_dispatcher_does_not_downgrade_after_html_and_binding_deleted",
    },
    "test_artifact_package.py": {
        "test_package_notices_require_complete_canonical_bytes",
        "test_installed_bridge_offline_guard_has_negative_controls",
        "test_installed_host_runtime_guard_and_failure_redaction",
        "test_installed_host_runtime_guard_accepts_only_exact_darwin_stage",
        "test_native_cold_install_operates_without_source_tree",
        "test_capability_upgrade_does_not_reinterpret_legacy_pair",
        "test_unqualified_binary_is_rejected_before_install", "test_install_target_is_create_only",
        "test_linked_installation_parent_cannot_escape",
        "test_release_packaging_stages_package_owned_native_payloads",
        "test_production_binary_has_no_network_capable_dependencies",
        "test_release_packaging_rejects_missing_duplicate_and_mismatched_candidates",
        "test_release_package_extraction_rejects_nonportable_member_names",
        "test_git_archive_modes_are_canonical_across_host_umasks",
        "test_git_archive_bytes_are_canonical_across_host_autocrlf",
        "test_release_packaging_is_create_only_and_rejects_linked_output",
        "test_release_packaging_does_not_invoke_go_or_any_child_process",
        "test_linked_ancestor_with_missing_descendant_cannot_mutate_external_tree",
        "test_unix_parent_swap_after_validation_cannot_redirect_creation",
        "test_staging_root_replacement_is_blocked_or_detected",
        "test_candidate_assertion_without_trusted_qualification_is_rejected",
        "test_magic_only_fake_is_rejected_even_with_matching_receipt",
        "test_qualification_receipt_requires_protected_exact_host_ci",
        "test_empty_or_malformed_artifact_version_is_rejected",
        "test_each_qualification_field_is_bound_to_trusted_context",
        "test_cold_execution_receipt_binds_each_host_to_the_native_promoted_bytes",
        "test_cold_execution_refuses_wrong_cell_context_and_is_create_only",
        "test_final_normal_packages_bind_exact_source_and_promoted_bytes",
        "test_final_package_build_refuses_wrong_source_or_promotion_before_output",
        "test_invalid_candidates_are_rejected_before_package_output_is_created",
        "test_npm_packer_receives_only_isolated_environment_and_redacts_failures",
        "test_promotion_receipt_binds_exact_payload_and_native_qualification_bytes",
        "test_promotion_receipt_is_create_only_with_the_stage",
        "test_promotion_receipt_rejects_context_host_file_set_and_byte_drift",
        "test_verified_promotion_snapshot_cannot_be_swapped_before_install",
    },
}


def candidate_identity() -> tuple[str, str, str, int, int]:
    if INSTALLATION is None:
        raise AssertionError("candidate installation is not initialized")
    manifest_bytes = (INSTALLATION / "release.json").read_bytes()
    manifest = json.loads(manifest_bytes)
    system = {"Linux": "linux", "Darwin": "darwin", "Windows": "windows"}[platform.system()]
    arch = {"x86_64": "amd64", "amd64": "amd64", "aarch64": "arm64", "arm64": "arm64"}[
        platform.machine().lower()
    ]
    entry = manifest["binaries"][f"{system}/{arch}"]
    binary = INSTALLATION / entry["file"]
    if binary.is_symlink() or not binary.is_file():
        raise AssertionError("candidate binary is not a regular non-link file")
    raw = binary.read_bytes()
    actual = hashlib.sha256(raw).hexdigest()
    if actual != entry["sha256"]:
        raise AssertionError("candidate binary differs from its manifest")
    stat = binary.stat()
    return hashlib.sha256(manifest_bytes).hexdigest(), entry["file"], actual, stat.st_size, stat.st_ino


def _utf16_key(value: str) -> bytes:
    return value.encode("utf-16-be")


def canonical_bytes(value: object) -> bytes:
    """Independent stdlib implementation of the declared safe-integer JSON profile."""
    if value is None:
        return b"null"
    if value is True:
        return b"true"
    if value is False:
        return b"false"
    if type(value) is int:
        if abs(value) > 9007199254740991:
            raise ValueError("integer outside safe range")
        return str(value).encode("ascii")
    if isinstance(value, str):
        return json.dumps(value, ensure_ascii=False, allow_nan=False,
                          separators=(",", ":")).encode("utf-8")
    if isinstance(value, list):
        return b"[" + b",".join(canonical_bytes(item) for item in value) + b"]"
    if isinstance(value, dict):
        if any(not isinstance(key, str) for key in value):
            raise ValueError("non-string object key")
        return b"{" + b",".join(
            canonical_bytes(key) + b":" + canonical_bytes(value[key])
            for key in sorted(value, key=_utf16_key)
        ) + b"}"
    raise ValueError(f"unsupported canonical value {type(value)!r}")


def embedded_model(html_bytes: bytes) -> dict:
    start = b'<script id="ca-artifact-model" type="application/json">\n'
    end = b"\n</script>"
    if html_bytes.count(start) != 1:
        raise AssertionError("current render must contain one model container")
    raw = html_bytes.split(start, 1)[1].split(end, 1)[0]
    pairs = []
    def strict_object(items):
        value = {}
        for key, item in items:
            if key in value:
                raise ValueError(f"duplicate key {key}")
            value[key] = item
        return value
    return json.loads(raw, object_pairs_hook=strict_object,
                      parse_constant=lambda value: (_ for _ in ()).throw(ValueError(value)))


def independent_identities(model: dict) -> tuple[str, str]:
    normative = {key: model[key] for key in (
        "format_version", "kind", "schema_version", "artifact_id", "normative"
    )}
    complete = {key: value for key, value in model.items() if key != "integrity"}
    return (hashlib.sha256(canonical_bytes(normative)).hexdigest(),
            hashlib.sha256(canonical_bytes(complete)).hexdigest())


def setUpModule() -> None:
    global INSTALLATION, INSTALLATION_OWNER, CANDIDATE_IDENTITY
    configured = os.environ.get("ARTIFACT_TEST_INSTALLATION")
    if configured:
        INSTALLATION = Path(configured).resolve(strict=True)
    else:
        INSTALLATION_OWNER = tempfile.TemporaryDirectory(prefix="ca-artifact-conformance-")
        unittest.addModuleCleanup(INSTALLATION_OWNER.cleanup)
        INSTALLATION = physical_test_directory(INSTALLATION_OWNER.name) / "payload"
        subprocess.run(
            [sys.executable, str(REPO / "tools/build-artifacts.py"),
             "--output", str(INSTALLATION)],
            cwd=REPO, check=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
            text=True, encoding="utf-8",
        )
    CANDIDATE_IDENTITY = candidate_identity()


class ArtifactConformanceTest(unittest.TestCase):
    def run_checked(self, argv: list[str], *, env: dict[str, str] | None = None,
                    cwd: Path = REPO) -> subprocess.CompletedProcess[str]:
        completed = subprocess.run(
            argv, cwd=cwd, env=env, capture_output=True, text=True, encoding="utf-8",
            errors="replace", check=False,
        )
        if completed.returncode != 0:
            self.fail(
                f"{argv!r} exited {completed.returncode}\n"
                f"stdout:\n{completed.stdout[-8000:]}\n"
                f"stderr:\n{completed.stderr[-8000:]}"
            )
        return completed

    def test_original_reference_contract_runs_without_skips(self) -> None:
        with tempfile.TemporaryDirectory(prefix="ca-reference-report-") as temporary:
            report = Path(temporary) / "report.json"
            self.run_checked([
                sys.executable,
                str(REPO / "docs/artifacts/design/original-review2/tools/run_review_tests.py"),
                "--report", str(report),
            ], env=dict(os.environ, PYTHONUTF8="1"))
            result = json.loads(report.read_text(encoding="utf-8"))
        self.assertEqual(result["tests_run"], 41)
        self.assertEqual(result["failures"], 0)
        self.assertEqual(result["errors"], 0)
        self.assertEqual(result["skipped"], 0)
        self.assertTrue(result["passed"])
        self.assertIn("NOT proposed Go/host/storage/farm", result["scope"])

    def test_independent_canonical_profile_has_discriminating_vectors(self) -> None:
        # UTF-16 order differs from Unicode code-point order for this pair.
        value = {"\ue000": 2, "\U00010000": 1, "control": "\b\n"}
        self.assertEqual(
            canonical_bytes(value),
            b'{"control":"\\b\\n","\xf0\x90\x80\x80":1,"\xee\x80\x80":2}',
        )
        with self.assertRaises(ValueError):
            canonical_bytes(9007199254740992)

    def test_named_runtime_conformance_oracle_passes_non_skipped(self) -> None:
        completed = self.run_checked([
            "go", "test", "-json", "./internal/conformance", "-run",
            "^(TestSpecPlanConformance)$", "-count=1",
        ], cwd=REPO / "core/artifacts")
        events = [json.loads(line) for line in completed.stdout.splitlines() if line.strip()]
        outcomes = [event for event in events
                    if event.get("Test") == "TestSpecPlanConformance"
                    and event.get("Action") in {"pass", "fail", "skip"}]
        self.assertEqual([event["Action"] for event in outcomes], ["pass"])

    def test_reviewed_pair_reproduction_uses_real_installed_protocol(self) -> None:
        self.assertIsNotNone(INSTALLATION)
        source = REPO / "core/artifacts/testdata/reference"
        spec = json.loads((source / "spec.json").read_text(encoding="utf-8"))
        plan = json.loads((source / "plan.json").read_text(encoding="utf-8"))
        self.assertEqual(spec["schema_version"], "0.2.0")
        self.assertEqual(plan["schema_version"], "0.2.0")

        with tempfile.TemporaryDirectory(prefix="ca-conformance-repo-") as temporary:
            root = physical_test_directory(temporary)
            client = ArtifactClient(root, INSTALLATION)
            capabilities = client.call("capabilities")
            self.assertTrue(capabilities["host_default_enabled"])
            self.assertFalse(capabilities["runtime_downloads"])
            client.call("create", {
                "operation_id": "conformance-spec-create",
                "artifact_id": spec["artifact_id"], "kind": "spec", "slug": spec["slug"],
                "title": spec["normative"]["title"],
                "summary": spec["normative"]["summary"],
                "normative": spec["normative"],
            })
            identity = client.call("identity", {"artifact_id": spec["artifact_id"]})
            plan["normative"]["spec_ref"] = {
                "artifact_id": spec["artifact_id"],
                "normative_sha256": identity["normative_sha256"],
                "binding_mode": "draft_preview",
            }
            client.call("create", {
                "operation_id": "conformance-plan-create",
                "artifact_id": plan["artifact_id"], "kind": "plan", "slug": plan["slug"],
                "title": plan["normative"]["title"],
                "summary": plan["normative"]["summary"],
                "spec_id": spec["artifact_id"], "normative": plan["normative"],
            })
            self.assertTrue(client.call("validate", {
                "artifact_id": spec["artifact_id"], "gate": "structural",
            })["valid"])
            self.assertTrue(client.call("validate", {
                "artifact_id": plan["artifact_id"], "gate": "structural",
            })["valid"])
            self.assertEqual(client.call("read", {
                "artifact_id": spec["artifact_id"], "symbol": "AC-001", "mode": "exact",
            })["record"]["id"], "AC-001")
            self.assertEqual(client.call("read", {
                "artifact_id": plan["artifact_id"], "symbol": "T-001", "mode": "exact",
            })["record"]["id"], "T-001")
            items = list(client.index())
            self.assertEqual({item["kind"] for item in items}, {"spec", "plan"})
            self.assertTrue(all(not item["authority"]["authority_verified"] for item in items))

            for name, path in {
                "spec": root / ".codearbiter/specs" / f"{spec['slug']}.html",
                "plan": root / ".codearbiter/plans" / f"{plan['slug']}.html",
            }.items():
                rendered = path.read_bytes()
                current = embedded_model(rendered)
                normative_hash, model_hash = independent_identities(current)
                self.assertEqual(current["integrity"]["normative_sha256"], normative_hash)
                self.assertEqual(current["integrity"]["model_sha256"], model_hash)
                observed = {
                    "normative": normative_hash,
                    "model": model_hash,
                    "html": hashlib.sha256(rendered).hexdigest(),
                }
                self.assertEqual(observed, CURRENT_GOLDEN[name])
                altered = rendered.replace(b"codeArbiter", b"codeArbitrer", 1)
                self.assertNotEqual(hashlib.sha256(altered).hexdigest(), CURRENT_GOLDEN[name]["html"])

            plan_path = root / ".codearbiter/plans" / f"{plan['slug']}.html"
            plan_path.write_bytes(plan_path.read_bytes() + b"<script>alert(1)</script>")
            with self.assertRaises(ArtifactError) as caught:
                list(client.index())
            self.assertEqual(caught.exception.code, "RENDER_DRIFT")

    def test_real_progress_transition_preserves_normative_identity(self) -> None:
        self.assertIsNotNone(INSTALLATION)
        with tempfile.TemporaryDirectory(prefix="ca-conformance-progress-") as temporary:
            root = physical_test_directory(temporary)
            harness = WorkflowHarness(root, INSTALLATION)
            harness.create_pair()
            harness.approve_pair()
            before = harness.client.call("identity", {"artifact_id": "PLAN-FLOW"})
            ticket = harness.context_ticket("T-001")
            harness.mutate("task-start", "PLAN-FLOW", task="T-001", context_ticket=ticket)
            after = harness.client.call("identity", {"artifact_id": "PLAN-FLOW"})
            eligible = harness.client.call("eligible", {"artifact_id": "PLAN-FLOW"})
            self.assertEqual(eligible["tasks"][0]["state"], "IN_PROGRESS")
            self.assertEqual(after["normative_sha256"], before["normative_sha256"])
            self.assertNotEqual(after["model_sha256"], before["model_sha256"])
            self.assertEqual(after["revision"], before["revision"] + 1)

    def test_adversarial_native_candidate_suites_run_as_one_snapshot(self) -> None:
        self.assertIsNotNone(INSTALLATION)
        environment = dict(os.environ, ARTIFACT_TEST_INSTALLATION=str(INSTALLATION))
        self.assertEqual(candidate_identity(), CANDIDATE_IDENTITY)
        for script, expected in EXPECTED_SUITES.items():
            with self.subTest(script=script):
                self.assertEqual(candidate_identity(), CANDIDATE_IDENTITY)
                print(f"conformance suite start: {script}", flush=True)
                result = self.run_checked(
                    [sys.executable, str(REPO / ".github/scripts" / script)],
                    env=environment,
                )
                output = result.stderr + result.stdout
                matches = re.findall(r"(?m)^(test_[a-z0-9_]+) \([^\r\n]+\) \.\.\. (ok|skipped .+)$", output)
                names = [name for name, _ in matches]
                self.assertEqual(len(names), len(set(names)), f"duplicate test result in {script}")
                self.assertEqual(set(names), expected, f"unexpected suite membership in {script}")
                print(f"conformance suite verified: {script} ({len(names)} cases)", flush=True)
                self.assertIn(f"Ran {len(expected)} tests", output)
                for name, status in matches:
                    if name == "test_unix_parent_swap_after_validation_cannot_redirect_creation" and platform.system() == "Windows":
                        self.assertTrue(status.startswith("skipped "), (name, status))
                    else:
                        self.assertEqual(status, "ok", (name, status))
                self.assertEqual(candidate_identity(), CANDIDATE_IDENTITY)


if __name__ == "__main__":
    unittest.main(verbosity=2)
