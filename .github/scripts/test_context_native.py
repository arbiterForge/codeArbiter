#!/usr/bin/env python3
# codeArbiter — run the declared context representation Go case through the
# finite test-owned bridge, binding executable and module bytes to its output.

import base64
import hashlib
import json
import os
from pathlib import Path
import shutil
import unittest

import _contextverificationlib as bridge


OBSERVED_CASES = []


MODULE = Path(__file__).resolve().parents[2] / "core" / "artifacts"
SOURCE = MODULE / "internal" / "repository" / "catalog_test.go"
SUBTESTS = (
    "html_spec_plan_identity",
    "unknown_representation_rejected",
    "inactive_optional_malformed_is_isolated",
    "legacy_duplicate_remains_error",
)
DOCUMENT_SOURCE = MODULE / "internal" / "contextdocument" / "contract_test.go"
DOCUMENT_SUBTESTS = (
    "valid_typed_five_documents",
    "unknown_document_and_payload",
    "unrecognized_fields_and_normative_claim",
    "command_state_and_invocation",
    "document_entry_scope",
    "canonical_schema_and_disabled_kind",
)
MARKDOWN_SOURCE = MODULE / "internal" / "contextdocument" / "markdown_test.go"
MARKDOWN_SUBTESTS = (
    "legacy_context_lf_unknown_section",
    "legacy_context_crlf_roundtrip",
    "legacy_code_map_real_bullet",
    "inert_tech_stack_command",
    "known_coding_and_security_lines",
    "mixed_unowned_eol_preserved",
    "duplicate_known_headings_rejected",
    "ambiguous_map_anchor_rejected",
    "unsupported_and_malformed_unchanged",
    "generated_comment_is_syntax_only",
    "created_template_field_markers",
    "invalid_field_markers_rejected",
    "non_sh_fence_does_not_create_command",
    "candidate_span_update_preserves_unowned_bytes",
    "partial_title_and_indented_marker_rejected",
    "four_tick_unknown_fence_preserved",
    "mixed_legacy_and_managed_identity_rejected",
    "two_managed_singular_identities_rejected",
    "independent_fact_claims_same_field_allowed",
)
RENDER_SOURCE = MODULE / "internal" / "contextdocument" / "render_test.go"
RENDER_SUBTESTS = (
    "legacy_exact_bytes_and_determinism",
    "bounded_map_role_and_limits",
    "duplicate_singular_identity_rejected",
    "command_state_and_root_cwd",
    "managed_declaration_stays_inert_and_preserves_human_bytes",
    "missing_template_is_parseable_and_present_empty_rejects",
    "selection_cannot_forge_span_or_ownership",
)


MUTATION_SOURCE = MODULE / "internal" / "contextdocument" / "operations_test.go"

MUTATION_SUBTESTS = (
    "membership_python_parity_all_seven",
    "approved_field_update_preserves_human_neighbors",
    "stale_document_and_provenance_pair_do_not_mutate",
    "provenance_only_update_refuses_without_mutation",
    "conflicting_document_provenance_identity_rejected",
    "v2_text_and_array_compatibility",
    "changed_source_evidence_and_membership_fail_closed",
    "current_membership_evidence_allows_scoped_update",
    "sensitive_content_evidence_is_refused",
    "new_human_file_blocks_missing_creation",
    "missing_authority_and_hash_only_do_not_admit",
    "explicit_creation_and_adoption_are_distinct",
    "factual_claim_uses_existing_v2_field_ownership",
    "unowned_or_unsupported_provenance_is_preserved",
    "operation_id_reuse_with_different_request_rejected",
    "replay_returns_historical_outcome_after_source_change",
)


RECOVERY_SOURCE = MODULE / "internal" / "contextdocument" / "recovery_test.go"

RECOVERY_SUBTESTS = (
    "interruptions_before_and_after_each_replacement",
    "lost_response_replay_and_duplicate_operation_ids",
    "divergent_human_edits_preserve_pending_transaction",
    "symlink_target_fails_before_context_mutation",
    "case_alias_preserves_human_file",
    "case_colliding_transaction_paths_rejected_before_journal",
    "unsupported_journal_blocks_context_write_without_replacement",
)


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def run_go_case(**bindings):
    """Retain the actual bounded streams in the outer runner's stdout capture."""
    try:
        observation = bridge.run_go_case(**bindings)
    except bridge.VerificationError as error:
        retain_go_output(bindings, error.raw_stdout, error.raw_stderr, error.exit_code)
        raise
    retain_go_output(bindings, observation.raw_stdout, observation.raw_stderr,
                     observation.exit_code)
    OBSERVED_CASES.append({
        "name": observation.test_name,
        "subtests": list(observation.subtests),
        "source_sha256": observation.source_sha256,
        "stdout_sha256": hashlib.sha256(observation.raw_stdout).hexdigest(),
        "stderr_sha256": hashlib.sha256(observation.raw_stderr).hexdigest(),
        "exit_code": observation.exit_code,
    })
    return observation


def retain_go_output(bindings, stdout, stderr, exit_code):
    # Base64 preserves original bytes through Windows text-mode log collectors.
    # This is a source-test observation, never a native authority receipt.
    print(json.dumps({
        "kind": "context-go-source-observation",
        "case": bindings["case"],
        "go_sha256": bindings["expected_go_sha256"],
        "source_sha256": bindings["expected_source_sha256"],
        "module_sha256": bindings["expected_module_sha256"],
        "exit_code": exit_code,
        "stdout_base64": base64.b64encode(stdout).decode("ascii"),
        "stderr_base64": base64.b64encode(stderr).decode("ascii"),
    }, sort_keys=True))


class ContextNativeVerification(unittest.TestCase):
    def shortDescription(self):
        return None

    def test_context_representation_boundary_runs_real_go_case(self):
        go_name = shutil.which("go")
        self.assertIsNotNone(go_name, "pinned local Go executable is required")
        go = Path(go_name).resolve(strict=True)
        observation = run_go_case(
            case="TestContextRepresentationBoundary",
            go_executable=go,
            module_root=MODULE,
            source_file=SOURCE,
            expected_go_sha256=sha256(go),
            expected_source_sha256=sha256(SOURCE),
            expected_module_sha256=bridge.hash_go_module(MODULE),
            expected_subtests=SUBTESTS,
        )
        self.assertEqual(observation.test_name, "TestContextRepresentationBoundary")
        self.assertEqual(observation.subtests, SUBTESTS)
        self.assertEqual(observation.exit_code, 0)
        self.assertTrue(observation.raw_stdout)
        self.assertEqual(observation.go_sha256, sha256(go))
        self.assertEqual(observation.source_sha256, sha256(SOURCE))
        self.assertEqual(observation.module_sha256, bridge.hash_go_module(MODULE))
        self.assertFalse(observation.live_qualified)

    def test_context_document_contract_runs_real_go_case(self):
        go_name = shutil.which("go")
        self.assertIsNotNone(go_name, "pinned local Go executable is required")
        go = Path(go_name).resolve(strict=True)
        observation = run_go_case(
            case="TestContextDocumentContract",
            go_executable=go,
            module_root=MODULE,
            source_file=DOCUMENT_SOURCE,
            expected_go_sha256=sha256(go),
            expected_source_sha256=sha256(DOCUMENT_SOURCE),
            expected_module_sha256=bridge.hash_go_module(MODULE),
            expected_subtests=DOCUMENT_SUBTESTS,
        )
        self.assertEqual(observation.test_name, "TestContextDocumentContract")
        self.assertEqual(observation.subtests, DOCUMENT_SUBTESTS)
        self.assertEqual(observation.exit_code, 0)
        self.assertTrue(observation.raw_stdout)
        self.assertEqual(observation.go_sha256, sha256(go))
        self.assertEqual(observation.source_sha256, sha256(DOCUMENT_SOURCE))
        self.assertEqual(observation.module_sha256, bridge.hash_go_module(MODULE))
        self.assertFalse(observation.live_qualified)


    def test_context_markdown_preservation_runs_real_go_case(self):
        go_name = shutil.which("go")
        self.assertIsNotNone(go_name, "pinned local Go executable is required")
        go = Path(go_name).resolve(strict=True)
        observation = run_go_case(
            case="TestContextMarkdownPreservation",
            go_executable=go,
            module_root=MODULE,
            source_file=MARKDOWN_SOURCE,
            expected_go_sha256=sha256(go),
            expected_source_sha256=sha256(MARKDOWN_SOURCE),
            expected_module_sha256=bridge.hash_go_module(MODULE),
            expected_subtests=MARKDOWN_SUBTESTS,
        )
        self.assertEqual(observation.test_name, "TestContextMarkdownPreservation")
        self.assertEqual(observation.subtests, MARKDOWN_SUBTESTS)
        self.assertEqual(observation.exit_code, 0)
        self.assertTrue(observation.raw_stdout)
        self.assertEqual(observation.go_sha256, sha256(go))
        self.assertEqual(observation.source_sha256, sha256(MARKDOWN_SOURCE))
        self.assertEqual(observation.module_sha256, bridge.hash_go_module(MODULE))
        self.assertFalse(observation.live_qualified)


    def test_context_bounded_render_runs_real_go_case(self):
        go_name = shutil.which("go")
        self.assertIsNotNone(go_name, "pinned local Go executable is required")
        go = Path(go_name).resolve(strict=True)
        observation = run_go_case(
            case="TestContextBoundedRender",
            go_executable=go,
            module_root=MODULE,
            source_file=RENDER_SOURCE,
            expected_go_sha256=sha256(go),
            expected_source_sha256=sha256(RENDER_SOURCE),
            expected_module_sha256=bridge.hash_go_module(MODULE),
            expected_subtests=RENDER_SUBTESTS,
        )
        self.assertEqual(observation.test_name, "TestContextBoundedRender")
        self.assertEqual(observation.subtests, RENDER_SUBTESTS)
        self.assertEqual(observation.exit_code, 0)
        self.assertTrue(observation.raw_stdout)
        self.assertEqual(observation.go_sha256, sha256(go))
        self.assertEqual(observation.source_sha256, sha256(RENDER_SOURCE))
        self.assertEqual(observation.module_sha256, bridge.hash_go_module(MODULE))
        self.assertFalse(observation.live_qualified)


    def test_context_mutation_admission_runs_real_go_case(self):
        go_name = shutil.which("go")
        self.assertIsNotNone(go_name, "pinned local Go executable is required")
        go = Path(go_name).resolve(strict=True)
        observation = run_go_case(
            case="TestContextMutationAdmission",
            go_executable=go,
            module_root=MODULE,
            source_file=MUTATION_SOURCE,
            expected_go_sha256=sha256(go),
            expected_source_sha256=sha256(MUTATION_SOURCE),
            expected_module_sha256=bridge.hash_go_module(MODULE),
            expected_subtests=MUTATION_SUBTESTS,
        )
        self.assertEqual(observation.test_name, "TestContextMutationAdmission")
        self.assertEqual(observation.subtests, MUTATION_SUBTESTS)
        self.assertEqual(observation.exit_code, 0)
        self.assertTrue(observation.raw_stdout)
        self.assertEqual(observation.go_sha256, sha256(go))
        self.assertEqual(observation.source_sha256, sha256(MUTATION_SOURCE))
        self.assertEqual(observation.module_sha256, bridge.hash_go_module(MODULE))
        self.assertFalse(observation.live_qualified)


    def test_context_recovery_and_paths_runs_real_go_case(self):
        go_name = shutil.which("go")
        self.assertIsNotNone(go_name, "pinned local Go executable is required")
        go = Path(go_name).resolve(strict=True)
        observation = run_go_case(
            case="TestContextRecoveryAndPaths",
            go_executable=go,
            module_root=MODULE,
            source_file=RECOVERY_SOURCE,
            expected_go_sha256=sha256(go),
            expected_source_sha256=sha256(RECOVERY_SOURCE),
            expected_module_sha256=bridge.hash_go_module(MODULE),
            expected_subtests=RECOVERY_SUBTESTS,
        )
        self.assertEqual(observation.test_name, "TestContextRecoveryAndPaths")
        self.assertEqual(observation.subtests, RECOVERY_SUBTESTS)
        self.assertEqual(observation.exit_code, 0)
        self.assertTrue(observation.raw_stdout)
        self.assertEqual(observation.go_sha256, sha256(go))
        self.assertEqual(observation.source_sha256, sha256(RECOVERY_SOURCE))
        self.assertEqual(observation.module_sha256, bridge.hash_go_module(MODULE))
        self.assertFalse(observation.live_qualified)


if __name__ == "__main__":
    suite = unittest.defaultTestLoader.loadTestsFromTestCase(ContextNativeVerification)
    result = unittest.TextTestRunner(verbosity=2).run(suite)
    if (result.wasSuccessful() and not result.skipped and result.testsRun == 6
            and os.environ.get("CONTEXT_NATIVE_OBSERVATION_OUTPUT")):
        destination = Path(os.environ["CONTEXT_NATIVE_OBSERVATION_OUTPUT"])
        if (not destination.is_absolute() or destination.exists()
                or not destination.parent.is_dir() or destination.parent.is_symlink()
                or len(OBSERVED_CASES) != 6
                or len({case["name"] for case in OBSERVED_CASES}) != 6):
            raise SystemExit("context native observation output is incomplete or unsafe")
        go_name = shutil.which("go")
        if go_name is None:
            raise SystemExit("context native observation lost the Go executable")
        record = {
            "format": "codearbiter.context-native-observation/0.1.0",
            "module_sha256": bridge.hash_go_module(MODULE),
            "go_sha256": sha256(Path(go_name).resolve(strict=True)),
            "cases": sorted(OBSERVED_CASES, key=lambda item: item["name"]),
        }
        with destination.open("x", encoding="utf-8", newline="\n") as stream:
            stream.write(json.dumps(record, sort_keys=True, separators=(",", ":")) + "\n")
    raise SystemExit(not result.wasSuccessful() or bool(result.skipped) or result.testsRun != 6)
