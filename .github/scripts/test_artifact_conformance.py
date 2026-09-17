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
from test_artifact_authoring import WorkflowHarness

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
    },
    "test_artifact_authoring.py": {
        "test_producers_create_and_read_canonical_html_pair",
        "test_incomplete_draft_is_named_without_inventing_contract_fields",
        "test_missing_payload_fails_closed_without_markdown_fallback",
        "test_resolves_a_test_owned_linked_ancestor",
    },
    "test_artifact_workflow.py": {
        "test_draft_or_missing_approval_cannot_dispatch",
        "test_approved_pair_dispatches_with_complete_context_and_resumes_in_progress",
        "test_stale_context_blocks_before_dispatch_side_effect",
        "test_changed_worktree_rejects_review_evidence",
        "test_review_checkpoint_survives_resume_and_scope_acceptance_is_atomic",
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
        "test_native_cold_install_operates_without_source_tree",
        "test_unqualified_binary_is_rejected_before_install", "test_install_target_is_create_only",
        "test_linked_installation_parent_cannot_escape",
        "test_release_packaging_stages_package_owned_native_payloads",
        "test_production_binary_has_no_network_capable_dependencies",
        "test_release_packaging_rejects_missing_duplicate_and_mismatched_candidates",
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
        INSTALLATION = Path(INSTALLATION_OWNER.name) / "payload"
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
            root = Path(temporary)
            client = ArtifactClient(root, INSTALLATION)
            capabilities = client.call("capabilities")
            self.assertFalse(capabilities["host_default_enabled"])
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
            root = Path(temporary)
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
                result = self.run_checked(
                    [sys.executable, str(REPO / ".github/scripts" / script)],
                    env=environment,
                )
                output = result.stderr + result.stdout
                matches = re.findall(r"(?m)^(test_[a-z0-9_]+) \([^\r\n]+\) \.\.\. (ok|skipped .+)$", output)
                names = [name for name, _ in matches]
                self.assertEqual(len(names), len(set(names)), f"duplicate test result in {script}")
                self.assertEqual(set(names), expected, f"unexpected suite membership in {script}")
                self.assertIn(f"Ran {len(expected)} tests", output)
                for name, status in matches:
                    if name == "test_unix_parent_swap_after_validation_cannot_redirect_creation" and platform.system() == "Windows":
                        self.assertTrue(status.startswith("skipped "), (name, status))
                    else:
                        self.assertEqual(status, "ok", (name, status))
                self.assertEqual(candidate_identity(), CANDIDATE_IDENTITY)


if __name__ == "__main__":
    unittest.main(verbosity=2)
