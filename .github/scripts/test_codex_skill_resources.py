#!/usr/bin/env python3
"""Tests for the offline Codex skill-resource characterization fixture.

Run: python .github/scripts/test_codex_skill_resources.py
"""

import importlib.util
import base64
import gc
import hashlib
import io
import json
import os
import shutil
import stat
import subprocess
import sys
import tempfile
import textwrap
import time
import unittest
import warnings
import zipfile
from unittest import mock
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[2]
CHECKER = REPO_ROOT / ".github" / "scripts" / "check_codex_skill_resources.py"
FIXTURE = REPO_ROOT / ".github" / "fixtures" / "codex-skill-resources"


def load_checker():
    spec = importlib.util.spec_from_file_location("check_codex_skill_resources", CHECKER)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


class CheckerPresentMixin:
    def setUp(self):
        self.assertTrue(
            CHECKER.exists(),
            "check_codex_skill_resources.py is missing; the fixture has no validator",
        )
        self.checker = load_checker()


class FixtureContractTest(CheckerPresentMixin, unittest.TestCase):
    """The tracked fixture proves direct, contained resource resolution offline."""

    def validate_copy(self, mutate=None):
        with tempfile.TemporaryDirectory() as temporary:
            copied = Path(temporary) / "fixture"
            shutil.copytree(FIXTURE, copied)
            if mutate is not None:
                mutate(copied)
            return self.checker.validate_fixture(copied, repository=Path(temporary))

    def test_tracked_fixture_is_valid_and_hash_is_repeatable(self):
        """Deleting or changing a tracked resource must invalidate its proof hash."""
        self.assertTrue(FIXTURE.is_dir(), "the tracked fixture is missing")
        first = self.checker.validate_fixture(FIXTURE)
        second = self.checker.validate_fixture(FIXTURE)
        self.assertEqual(first["errors"], [], first["errors"])
        self.assertEqual(first["fixture_sha256"], second["fixture_sha256"])
        self.assertEqual(len(first["fixture_sha256"]), 64)

    def test_durable_report_records_the_post_acceptance_handoff(self):
        """The completed evidence report must not route readers back to ADR authoring."""
        report = (
            REPO_ROOT / "docs/reports/codex-skill-resource-resolution.md"
        ).read_text(encoding="utf-8")
        self.assertNotIn("next governed step is ADR-0031\nauthoring", report)
        self.assertIn("ADR-0031 was accepted", report)
        self.assertIn("pre-ingestion declaration", report)

    def test_link_escape_is_rejected_before_a_host_can_follow_it(self):
        """A link above the plugin root would make a shipped route uncontained."""
        result = self.validate_copy(
            lambda root: (root / "skills" / "probe" / "SKILL.md").write_text(
                "# probe\nnonce: skill-probe-nonce\n[escape](../../../../outside.md)\n",
                encoding="utf-8",
            )
        )
        self.assertTrue(any("escapes fixture root" in error for error in result["errors"]), result)

    def test_missing_link_target_is_rejected(self):
        """A route to a non-existent charter is unresolved, not an optional hint."""
        result = self.validate_copy(lambda root: (root / "agents" / "probe.md").unlink())
        self.assertTrue(any("does not exist" in error for error in result["errors"]), result)

    def test_entry_skill_must_link_to_the_expected_nested_routine(self):
        """Removing a relative read would make the three-resource probe vacuous."""
        result = self.validate_copy(
            lambda root: (root / "skills" / "probe" / "SKILL.md").write_text(
                "# probe\nnonce: skill-probe-nonce-7f4d\n", encoding="utf-8"
            )
        )
        self.assertTrue(any("outgoing link set" in error for error in result["errors"]), result)

    def test_resource_must_not_carry_an_extra_contained_link(self):
        """A fourth direct read would invalidate the deterministic three-read contract."""
        result = self.validate_copy(
            lambda root: (root / "skills" / "probe" / "SKILL.md").write_text(
                "# probe\nnonce: skill-probe-nonce-7f4d\n"
                "[routine](../../routines/nested.md)\n"
                "[extra](../../agents/probe.md)\n",
                encoding="utf-8",
            )
        )
        self.assertTrue(any("outgoing link set" in error for error in result["errors"]), result)

    def test_duplicate_resource_nonce_is_rejected(self):
        """Two reads returning one token cannot prove all three resources resolved."""
        def mutate(root):
            agent = root / "agents" / "probe.md"
            agent.write_text(
                "# probe agent\nnonce: skill-probe-nonce-7f4d\n", encoding="utf-8"
            )

        result = self.validate_copy(mutate)
        self.assertTrue(any("duplicate nonce" in error for error in result["errors"]), result)

    def test_required_supported_matrix_is_exact(self):
        """Dropping or substituting a supported runtime cell must stop ADR evidence."""
        def mutate(root):
            matrix_path = root / "matrix.json"
            matrix = json.loads(matrix_path.read_text(encoding="utf-8"))
            matrix["required_cells"] = matrix["required_cells"][:-1]
            matrix_path.write_text(json.dumps(matrix), encoding="utf-8")

        result = self.validate_copy(mutate)
        self.assertTrue(any("required matrix cells" in error for error in result["errors"]), result)

    def test_wrong_supported_version_is_rejected(self):
        """A nearby release cannot silently replace a version that ADR evidence pins."""
        def mutate(root):
            matrix_path = root / "matrix.json"
            matrix = json.loads(matrix_path.read_text(encoding="utf-8"))
            matrix["required_cells"][0]["version"] = "0.144.0"
            matrix_path.write_text(json.dumps(matrix), encoding="utf-8")

        result = self.validate_copy(mutate)
        self.assertTrue(any("required matrix cells" in error for error in result["errors"]), result)

    def test_matrix_requires_nonempty_provenance_and_integrity(self):
        """An unverifiable executable is not evidence for a backend contract."""
        def mutate(root):
            matrix_path = root / "matrix.json"
            matrix = json.loads(matrix_path.read_text(encoding="utf-8"))
            matrix["required_cells"][0]["provenance"] = ""
            matrix["required_cells"][1].pop("integrity")
            matrix_path.write_text(json.dumps(matrix), encoding="utf-8")

        result = self.validate_copy(mutate)
        self.assertTrue(any("provenance" in error for error in result["errors"]), result)
        self.assertTrue(any("integrity" in error for error in result["errors"]), result)

    def test_receipt_validation_fails_closed_when_matrix_fields_are_missing(self):
        """Materialized receipts must not turn malformed matrix data into an exception."""
        validated = self.checker.validate_fixture(FIXTURE)
        receipt = json.loads(
            (
                REPO_ROOT
                / "docs/reports/evidence/codex-skill-resource-resolution/cli-0.143.0.json"
            ).read_text(encoding="utf-8")
        )
        for field in ("surface", "version", "integrity"):
            with self.subTest(field=field):
                expected = dict(validated["matrix"]["required_cells"][0])
                expected.pop(field)
                errors = self.checker._receipt_errors(
                    receipt,
                    expected,
                    validated["fixture_sha256"],
                    validated["evidence_contract_sha256"],
                    "test receipt",
                )
                self.assertTrue(any(field in error for error in errors), errors)

    def test_durable_receipt_requires_plan_evidence_fields(self):
        """A pin-only JSON object cannot masquerade as a complete backend receipt."""
        validated = self.checker.validate_fixture(FIXTURE)
        expected = validated["matrix"]["required_cells"][0]
        receipt_path = (
            REPO_ROOT
            / "docs/reports/evidence/codex-skill-resource-resolution/cli-0.143.0.json"
        )
        complete = json.loads(receipt_path.read_text(encoding="utf-8"))
        required = (
            "authentication_mode",
            "environment",
            "installed_plugin_root",
            "entry_path",
            "resource_reads",
            "requested_sandbox",
            "effective_sandbox",
            "requested_approval_policy",
            "effective_approval_policy",
            "network_policy",
            "errors",
            "errors_sha256",
            "operation_transcript_sha256",
            "stdout_sha256",
            "stderr_sha256",
            "skill_invocation_evidence",
        )

        for field in required:
            with self.subTest(field=field):
                receipt = dict(complete)
                receipt.pop(field)
                errors = self.checker._receipt_errors(
                    receipt,
                    expected,
                    validated["fixture_sha256"],
                    validated["evidence_contract_sha256"],
                    "test receipt",
                )
                self.assertTrue(any(field in error for error in errors), errors)

    def test_durable_receipt_rejects_plan_evidence_drift(self):
        """Present-but-weakened isolation, path, policy, and host proof fails closed."""
        validated = self.checker.validate_fixture(FIXTURE)
        expected = validated["matrix"]["required_cells"][0]
        complete = json.loads(
            (
                REPO_ROOT
                / "docs/reports/evidence/codex-skill-resource-resolution/cli-0.143.0.json"
            ).read_text(encoding="utf-8")
        )
        mutations = (
            ("authentication_mode", lambda receipt: receipt.__setitem__("authentication_mode", "api-key")),
            (
                "environment.execution_environment",
                lambda receipt: receipt["environment"].__setitem__(
                    "execution_environment", "shared-home"
                ),
            ),
            (
                "installed_plugin_root",
                lambda receipt: receipt.__setitem__("installed_plugin_root", r"C:\outside"),
            ),
            ("entry_path", lambda receipt: receipt.__setitem__("entry_path", r"C:\outside\SKILL.md")),
            (
                "resource_reads",
                lambda receipt: receipt["resource_reads"][0].__setitem__("extra", "not allowed"),
            ),
            (
                "resource_reads",
                lambda receipt: receipt["resource_reads"][0].__setitem__("nonce", "wrong"),
            ),
            ("requested_sandbox", lambda receipt: receipt.__setitem__("requested_sandbox", "workspace-write")),
            (
                "effective_approval_policy",
                lambda receipt: receipt.__setitem__("effective_approval_policy", "on-request"),
            ),
            ("network_policy", lambda receipt: receipt.__setitem__("network_policy", "unrestricted")),
            ("errors", lambda receipt: receipt.__setitem__("errors", ["hidden failure"])),
            (
                "operation_transcript_sha256",
                lambda receipt: receipt.__setitem__("operation_transcript_sha256", "0"),
            ),
            (
                "skill_invocation_evidence",
                lambda receipt: receipt["skill_invocation_evidence"].__setitem__(
                    "source", "unverified"
                ),
            ),
        )

        for marker, mutate in mutations:
            with self.subTest(marker=marker):
                receipt = json.loads(json.dumps(complete))
                mutate(receipt)
                errors = self.checker._receipt_errors(
                    receipt,
                    expected,
                    validated["fixture_sha256"],
                    validated["evidence_contract_sha256"],
                    "test receipt",
                )
                if errors == ["test receipt contains untrusted fields"]:
                    self.assertEqual(marker, "resource_reads")
                else:
                    self.assertTrue(any(marker in error for error in errors), errors)

        relocated = json.loads(json.dumps(complete))
        old_home = relocated["environment"]["codex_home"]
        new_home = r"C:\outside-home"
        relocated["environment"]["codex_home"] = new_home
        for field in ("installed_plugin_root", "entry_path"):
            relocated[field] = relocated[field].replace(old_home, new_home)
        for read in relocated["resource_reads"]:
            read["path"] = read["path"].replace(old_home, new_home)
        relocated["skill_invocation_evidence"]["path"] = relocated[
            "skill_invocation_evidence"
        ]["path"].replace(old_home, new_home)
        relocated_errors = self.checker._receipt_errors(
            relocated,
            expected,
            validated["fixture_sha256"],
            validated["evidence_contract_sha256"],
            "test receipt",
        )
        self.assertTrue(
            any("environment.codex_home" in error for error in relocated_errors),
            relocated_errors,
        )

        app_expected = validated["matrix"]["required_cells"][2]
        app_complete = json.loads(
            (
                REPO_ROOT
                / "docs/reports/evidence/codex-skill-resource-resolution/app-server-0.143.0.json"
            ).read_text(encoding="utf-8")
        )
        for field in ("selected_skill", "selected_skill_path"):
            with self.subTest(app_server_field=field):
                receipt = dict(app_complete)
                receipt.pop(field)
                errors = self.checker._receipt_errors(
                    receipt,
                    app_expected,
                    validated["fixture_sha256"],
                    validated["evidence_contract_sha256"],
                    "test receipt",
                )
                self.assertTrue(any(field in error for error in errors), errors)

    def test_durable_receipt_rejects_unknown_and_secret_bearing_fields(self):
        """Unreviewed receipt fields cannot bypass schema or secret boundaries."""
        validated = self.checker.validate_fixture(FIXTURE)
        expected = validated["matrix"]["required_cells"][0]
        complete = json.loads(
            (
                REPO_ROOT
                / "docs/reports/evidence/codex-skill-resource-resolution/cli-0.143.0.json"
            ).read_text(encoding="utf-8")
        )
        receipt = dict(complete)
        receipt["extra"] = "benign"
        errors = self.checker._receipt_errors(
            receipt,
            expected,
            validated["fixture_sha256"],
            validated["evidence_contract_sha256"],
            "test receipt",
        )
        self.assertEqual(errors, ["test receipt contains untrusted fields"])

    def test_durable_receipt_opaque_unknown_field_fails_before_echo_or_hash(self):
        """Unknown receipt members are untrusted even when no secret regex recognizes them."""
        validated = self.checker.validate_fixture(FIXTURE)
        matrix = validated["matrix"]
        opaque = "AbCdEfGhIjKlMnOpQrStUvWxYz0123456789AaBbCcDdEeFf"
        with tempfile.TemporaryDirectory() as temporary:
            repository = Path(temporary)
            report_path = repository / matrix["durable_record"]["report"]
            report_path.parent.mkdir(parents=True)
            shutil.copy2(REPO_ROOT / matrix["durable_record"]["report"], report_path)
            receipt_directory = repository / matrix["durable_record"]["receipt_directory"]
            shutil.copytree(
                REPO_ROOT / matrix["durable_record"]["receipt_directory"],
                receipt_directory,
            )
            changed = receipt_directory / "cli-0.143.0.json"
            receipt = json.loads(changed.read_text(encoding="utf-8"))
            receipt[opaque] = False
            changed.write_text(json.dumps(receipt, sort_keys=True), encoding="utf-8")

            with mock.patch.object(
                self.checker, "sha256_file", wraps=self.checker.sha256_file,
            ) as digest_calls:
                evidence = self.checker.validate_durable_artifacts(
                    repository, matrix, validated["fixture_sha256"]
                )

        serialized = json.dumps(evidence, sort_keys=True)
        hashed_paths = [Path(call.args[0]) for call in digest_calls.call_args_list]
        self.assertFalse(evidence["complete"], evidence)
        self.assertNotIn(changed, hashed_paths)
        self.assertNotIn(opaque, serialized)
        self.assertNotIn(self.checker._sha256_text(opaque), serialized)
        self.assertTrue(
            any("untrusted fields" in error for error in evidence["errors"]), evidence
        )

    def test_durable_receipt_secret_key_is_rejected_without_echo_or_digest(self):
        """A credential-shaped member name never reaches durable diagnostics."""
        validated = self.checker.validate_fixture(FIXTURE)
        expected = validated["matrix"]["required_cells"][0]
        complete = json.loads(
            (
                REPO_ROOT
                / "docs/reports/evidence/codex-skill-resource-resolution/cli-0.143.0.json"
            ).read_text(encoding="utf-8")
        )
        secret_key = "sk-secret-keyname-123456"
        complete[secret_key] = False
        errors = self.checker._receipt_errors(
            complete,
            expected,
            validated["fixture_sha256"],
            validated["evidence_contract_sha256"],
            "test receipt",
        )
        serialized = json.dumps(errors, sort_keys=True)
        self.assertEqual(errors, ["test receipt contains secret-bearing output"])
        self.assertNotIn(secret_key, serialized)
        self.assertNotIn(self.checker._sha256_text(secret_key), serialized)

    def test_durable_report_rejects_stale_receipt_hash(self):
        """Changing receipt bytes invalidates the source-backed report binding."""
        validated = self.checker.validate_fixture(FIXTURE)
        matrix = validated["matrix"]
        with tempfile.TemporaryDirectory() as temporary:
            repository = Path(temporary)
            report_path = repository / matrix["durable_record"]["report"]
            report_path.parent.mkdir(parents=True)
            shutil.copy2(
                REPO_ROOT / matrix["durable_record"]["report"], report_path
            )
            receipt_directory = repository / matrix["durable_record"]["receipt_directory"]
            shutil.copytree(
                REPO_ROOT / matrix["durable_record"]["receipt_directory"],
                receipt_directory,
            )
            changed = receipt_directory / "cli-0.143.0.json"
            changed.write_text(changed.read_text(encoding="utf-8") + "\n", encoding="utf-8")

            evidence = self.checker.validate_durable_artifacts(
                repository, matrix, validated["fixture_sha256"]
            )

        self.assertFalse(evidence["complete"], evidence)
        self.assertTrue(
            any("cli-0.143.0.json SHA-256" in error for error in evidence["errors"]),
            evidence,
        )

    def test_durable_receipt_hashes_must_match_canonical_facts(self):
        """Rebinding a fabricated evidence hash in the report cannot make it canonical."""
        validated = self.checker.validate_fixture(FIXTURE)
        matrix = validated["matrix"]
        for field in (
            "operation_transcript_sha256", "stdout_sha256", "stderr_sha256",
        ):
            with self.subTest(field=field), tempfile.TemporaryDirectory() as temporary:
                repository = Path(temporary)
                report_path = repository / matrix["durable_record"]["report"]
                report_path.parent.mkdir(parents=True)
                shutil.copy2(REPO_ROOT / matrix["durable_record"]["report"], report_path)
                receipt_directory = repository / matrix["durable_record"]["receipt_directory"]
                shutil.copytree(
                    REPO_ROOT / matrix["durable_record"]["receipt_directory"],
                    receipt_directory,
                )
                receipt_path = receipt_directory / "cli-0.143.0.json"
                old_digest = self.checker.sha256_file(receipt_path)
                receipt = json.loads(receipt_path.read_text(encoding="utf-8"))
                receipt[field] = "0" * 64
                receipt_path.write_text(
                    json.dumps(receipt, indent=2, sort_keys=True) + "\n", encoding="utf-8"
                )
                new_digest = self.checker.sha256_file(receipt_path)
                report_path.write_text(
                    report_path.read_text(encoding="utf-8").replace(old_digest, new_digest),
                    encoding="utf-8",
                )

                evidence = self.checker.validate_durable_artifacts(
                    repository, matrix, validated["fixture_sha256"]
                )

            self.assertFalse(evidence["complete"], evidence)
            self.assertTrue(any(field in error for error in evidence["errors"]), evidence)

    def test_durable_receipt_rejects_opaque_auth_root_suffix(self):
        """The recorded one-use auth root has a bounded timestamp grammar, not a free suffix."""
        validated = self.checker.validate_fixture(FIXTURE)
        expected = validated["matrix"]["required_cells"][0]
        receipt = json.loads(
            (
                REPO_ROOT
                / "docs/reports/evidence/codex-skill-resource-resolution/cli-0.143.0.json"
            ).read_text(encoding="utf-8")
        )
        old_home = receipt["environment"]["codex_home"]
        new_home = (
            old_home.rsplit("\\", 1)[0]
            + r"\cli-0143-auth-AbCdEfGhIjKlMnOpQrStUvWxYz0123456789AaBbCcDdEeFf"
        )
        receipt["environment"]["codex_home"] = new_home
        for field in ("installed_plugin_root", "entry_path"):
            receipt[field] = receipt[field].replace(old_home, new_home)
        for read in receipt["resource_reads"]:
            read["path"] = read["path"].replace(old_home, new_home)
        receipt["skill_invocation_evidence"]["path"] = receipt[
            "skill_invocation_evidence"
        ]["path"].replace(old_home, new_home)

        errors = self.checker._receipt_errors(
            receipt,
            expected,
            validated["fixture_sha256"],
            validated["evidence_contract_sha256"],
            "test receipt",
        )

        self.assertTrue(any("one-use OS-temporary auth root" in error for error in errors), errors)

    def test_matrix_rejects_malformed_or_wrong_pinned_integrity(self):
        """A syntactically plausible or truncated package digest is not pinned evidence."""
        def mutate(root):
            matrix_path = root / "matrix.json"
            matrix = json.loads(matrix_path.read_text(encoding="utf-8"))
            matrix["required_cells"][0]["integrity"] = "sha512-not-base64"
            matrix["required_cells"][1]["integrity"] = "sha512-" + base64.b64encode(
                b"0" * 64
            ).decode("ascii")
            matrix_path.write_text(json.dumps(matrix), encoding="utf-8")

        result = self.validate_copy(mutate)
        self.assertTrue(any("integrity format" in error for error in result["errors"]), result)
        self.assertTrue(any("does not match pinned integrity" in error for error in result["errors"]), result)

    def test_matrix_rejects_desktop_claims(self):
        """Stage 1 backend evidence cannot be relabeled as desktop-shell proof."""
        def mutate(root):
            matrix_path = root / "matrix.json"
            matrix = json.loads(matrix_path.read_text(encoding="utf-8"))
            matrix["required_cells"][0]["surface"] = "desktop"
            matrix["required_cells"][0]["desktop_shell_proven"] = True
            matrix_path.write_text(json.dumps(matrix), encoding="utf-8")

        result = self.validate_copy(mutate)
        self.assertTrue(any("desktop" in error for error in result["errors"]), result)

    def test_durable_record_must_bind_the_exact_fixture_hash(self):
        """A report copied from another fixture must not be accepted as this fixture's evidence."""
        validated = self.checker.validate_fixture(FIXTURE)
        record = {
            "report": "docs/reports/codex-skill-resource-resolution.md",
            "receipt_directory": "docs/reports/evidence/codex-skill-resource-resolution",
            "fixture_sha256": "0" * 64,
        }
        errors = self.checker.validate_durable_record(
            record, validated["matrix"], validated["fixture_sha256"]
        )
        self.assertTrue(any("fixture_sha256" in error for error in errors), errors)

    def test_durable_record_path_drift_is_rejected(self):
        """A receipt reference that no longer names the planned durable record is unsafe."""
        validated = self.checker.validate_fixture(FIXTURE)
        record = {
            "report": "docs/reports/another.md",
            "receipt_directory": "docs/reports/evidence/codex-skill-resource-resolution",
            "fixture_sha256": validated["fixture_sha256"],
        }
        errors = self.checker.validate_durable_record(
            record, validated["matrix"], validated["fixture_sha256"]
        )
        self.assertTrue(any("report" in error for error in errors), errors)

    def test_fixture_only_mode_recognizes_complete_durable_artifacts(self):
        """The tracked report and four receipts complete the fixture evidence binding."""
        validated = self.checker.validate_fixture(FIXTURE)
        evidence = validated["durable_evidence"]
        self.assertEqual(evidence["state"], "complete")
        self.assertTrue(evidence["complete"])
        self.assertEqual(evidence["errors"], [])

    def test_present_receipt_artifact_must_bind_cell_and_fixture(self):
        """Once evidence appears, a wrong cell/hash makes the partial evidence fail closed."""
        validated = self.checker.validate_fixture(FIXTURE)
        with tempfile.TemporaryDirectory() as temporary:
            repository = Path(temporary)
            record_dir = repository / "docs" / "reports" / "evidence" / "codex-skill-resource-resolution"
            record_dir.mkdir(parents=True)
            (record_dir / "cli-0.143.0.json").write_text(
                json.dumps({
                    "surface": "cli",
                    "version": "0.145.0",
                    "fixture_sha256": validated["fixture_sha256"],
                    "provenance": "npm:@openai/codex@0.143.0",
                    "integrity": "sha512-6h53sNtESIYncWVwU7zEjdVajwcad/0H94MOrgGqhwBMa9RRUDVG6DU9E9euC7yRdtrsKDAkJkz/m5moZ6MU3A==",
                    "native_executable_sha256": "5728e3ddf1480103bad235560e95cf7764ea3069f06029f9b2f39eb74a8066f6"
                }),
                encoding="utf-8",
            )
            evidence = self.checker.validate_durable_artifacts(
                repository, validated["matrix"], validated["fixture_sha256"]
            )
        self.assertEqual(evidence["state"], "invalid")
        self.assertTrue(any("does not match expected cell" in error for error in evidence["errors"]), evidence)

    def test_receipt_must_bind_separate_matrix_evidence_contract_hash(self):
        """Payload bytes alone cannot silently inherit a different required-cell contract."""
        validated = self.checker.validate_fixture(FIXTURE)
        cell = validated["matrix"]["required_cells"][0]
        receipt = dict(cell)
        receipt.update({
            "fixture_sha256": validated["fixture_sha256"],
            "evidence_contract_sha256": "0" * 64,
        })
        errors = self.checker._receipt_errors(
            receipt,
            cell,
            validated["fixture_sha256"],
            validated["evidence_contract_sha256"],
            "test receipt",
        )
        self.assertTrue(any("matrix contract hash" in error for error in errors), errors)

    def test_failed_receipt_cannot_complete_durable_evidence(self):
        """Matching hashes cannot promote a failed required cell into durable completion."""
        validated = self.checker.validate_fixture(FIXTURE)
        cell = validated["matrix"]["required_cells"][0]
        receipt = dict(cell)
        receipt.update({
            "verdict": "FAIL",
            "fixture_sha256": validated["fixture_sha256"],
            "evidence_contract_sha256": validated["evidence_contract_sha256"],
        })

        errors = self.checker._receipt_errors(
            receipt,
            cell,
            validated["fixture_sha256"],
            validated["evidence_contract_sha256"],
            "test receipt",
        )

        self.assertTrue(any("verdict" in error for error in errors), errors)

    def test_backend_receipt_cannot_claim_desktop_shell_proof(self):
        """A backend pass must not be relabeled as evidence for the desktop shell."""
        validated = self.checker.validate_fixture(FIXTURE)
        cell = validated["matrix"]["required_cells"][0]
        receipt = dict(cell)
        receipt.update({
            "verdict": "PASS",
            "evidence_class": "supported",
            "desktop_shell_proven": True,
            "fixture_sha256": validated["fixture_sha256"],
            "evidence_contract_sha256": validated["evidence_contract_sha256"],
        })

        errors = self.checker._receipt_errors(
            receipt,
            cell,
            validated["fixture_sha256"],
            validated["evidence_contract_sha256"],
            "test receipt",
        )

        self.assertTrue(any("desktop_shell_proven" in error for error in errors), errors)

    def test_advisory_receipt_cannot_satisfy_a_required_cell(self):
        """Advisory drift remains separate even when every required-cell hash matches."""
        validated = self.checker.validate_fixture(FIXTURE)
        cell = validated["matrix"]["required_cells"][0]
        receipt = dict(cell)
        receipt.update({
            "verdict": "PASS",
            "evidence_class": "advisory",
            "desktop_shell_proven": False,
            "fixture_sha256": validated["fixture_sha256"],
            "evidence_contract_sha256": validated["evidence_contract_sha256"],
        })

        errors = self.checker._receipt_errors(
            receipt,
            cell,
            validated["fixture_sha256"],
            validated["evidence_contract_sha256"],
            "test receipt",
        )

        self.assertTrue(any("evidence_class" in error for error in errors), errors)

    def test_artifact_presence_derives_complete_without_matrix_status_rewrite(self):
        """Adding all durable artifacts completes evidence without changing fixture metadata."""
        validated = self.checker.validate_fixture(FIXTURE)
        matrix = validated["matrix"]
        with tempfile.TemporaryDirectory() as temporary:
            repository = Path(temporary)
            report = repository / matrix["durable_record"]["report"]
            report.parent.mkdir(parents=True)
            report.write_text(
                f"fixture_sha256: {validated['fixture_sha256']}\n", encoding="utf-8"
            )
            receipt_directory = repository / matrix["durable_record"]["receipt_directory"]
            receipt_directory.mkdir(parents=True)
            receipt_hashes = []
            for cell in matrix["required_cells"]:
                filename = matrix["durable_record"]["receipt_filename_template"].format(
                    surface=cell["surface"], version=cell["version"]
                )
                shutil.copy2(
                    REPO_ROOT / matrix["durable_record"]["receipt_directory"] / filename,
                    receipt_directory / filename,
                )
                receipt_hashes.append(
                    self.checker.sha256_file(receipt_directory / filename)
                )
            evidence = self.checker.validate_durable_artifacts(
                repository, matrix, validated["fixture_sha256"]
            )
            report.write_text(
                report.read_text(encoding="utf-8")
                + f"evidence_contract_sha256: {validated['evidence_contract_sha256']}\n",
                encoding="utf-8",
            )
            report.write_text(
                report.read_text(encoding="utf-8")
                + "\n".join(receipt_hashes)
                + "\n",
                encoding="utf-8",
            )
            complete_evidence = self.checker.validate_durable_artifacts(
                repository, matrix, validated["fixture_sha256"]
            )
        self.assertEqual(matrix["durable_record"]["status"], "pending")
        self.assertEqual(evidence["state"], "invalid", evidence)
        self.assertTrue(any("evidence contract" in error for error in evidence["errors"]), evidence)
        self.assertEqual(complete_evidence["state"], "complete", complete_evidence)
        self.assertTrue(complete_evidence["complete"])
        self.assertEqual(complete_evidence["errors"], [])

    def test_fixture_hash_changes_when_a_resource_changes(self):
        """The hash is a content binding, not merely a directory identifier."""
        baseline = self.checker.validate_fixture(FIXTURE)["fixture_sha256"]
        result = self.validate_copy(
            lambda root: (root / "routines" / "nested.md").write_text(
                "# nested\nnonce: nested-routine-nonce-changed\n[agent](../agents/probe.md)\n",
                encoding="utf-8",
            )
        )
        self.assertNotEqual(baseline, result["fixture_sha256"])

    def test_matrix_evidence_changes_do_not_reidentify_installable_payload(self):
        """Adding durable evidence metadata must not invalidate payload-bound receipts."""
        baseline = self.checker.validate_fixture(FIXTURE)

        def mutate(root):
            matrix_path = root / "matrix.json"
            matrix = json.loads(matrix_path.read_text(encoding="utf-8"))
            matrix["durable_record"]["status"] = "complete"
            matrix_path.write_text(json.dumps(matrix), encoding="utf-8")

        changed = self.validate_copy(mutate)
        self.assertEqual(changed["fixture_sha256"], baseline["fixture_sha256"])
        self.assertNotEqual(
            changed["evidence_contract_sha256"], baseline["evidence_contract_sha256"]
        )
        self.assertEqual(changed["durable_evidence"]["state"], "pending")
        self.assertEqual(changed["durable_evidence"]["errors"], [])


class LiveObservationContractTest(CheckerPresentMixin, unittest.TestCase):
    """Live evidence is accepted only when it proves the exact contained reads."""

    def setUp(self):
        super().setUp()
        self.plugin_root = Path(tempfile.gettempdir()).resolve() / "installed-probe"
        self.observation = {
            "entry_path": str(self.plugin_root / "skills" / "probe" / "SKILL.md"),
            "resource_reads": [
                {
                    "path": str(self.plugin_root / "skills" / "probe" / "SKILL.md"),
                    "nonce": "skill-probe-nonce-7f4d",
                },
                {
                    "path": str(self.plugin_root / "routines" / "nested.md"),
                    "nonce": "nested-routine-nonce-2ca1",
                },
                {
                    "path": str(self.plugin_root / "agents" / "probe.md"),
                    "nonce": "agent-probe-nonce-91be",
                },
            ],
            "requested_sandbox": "read-only",
            "effective_sandbox": "read-only",
            "requested_approval_policy": "never",
            "effective_approval_policy": "never",
        }

    def read_events(self, *, command="Get-Content", failed_index=None):
        events = []
        for index, relative in enumerate(self.checker.RESOURCE_FILES):
            path = self.plugin_root / relative
            nonce = self.checker.EXPECTED_NONCES[relative]
            events.append({
                "type": "item.completed",
                "item": {
                    "type": "command_execution",
                    "command": f'{command} -LiteralPath "{path}"',
                    "exit_code": 1 if index == failed_index else 0,
                    "status": "failed" if index == failed_index else "completed",
                    "aggregated_output": nonce,
                },
            })
        return events

    def errors(self, observation=None, transcript=None, events=None):
        if transcript is None:
            transcript = "\n".join(
                "read -- " + str(self.plugin_root / relative)
                for relative in self.checker.RESOURCE_FILES
            )
        if events is None:
            events = self.read_events()
        return self.checker.validate_live_observation(
            observation or self.observation,
            self.plugin_root,
            transcript,
            events,
        )

    def test_exact_three_contained_reads_are_accepted(self):
        """Rejecting a complete direct-read observation would block valid evidence."""
        self.assertEqual(self.errors(), [])

    def test_live_observation_requires_exact_top_level_and_read_members(self):
        for label, mutate in (
            ("top-level", lambda observation: observation.update(extra="must-not-pass")),
            (
                "resource read",
                lambda observation: observation["resource_reads"][0].update(
                    api_key="must-not-pass"
                ),
            ),
        ):
            with self.subTest(label=label):
                observation = json.loads(json.dumps(self.observation))
                mutate(observation)
                errors = self.errors(observation)
                self.assertTrue(any("exact fields" in error for error in errors), errors)

    def test_relative_entry_path_is_rejected(self):
        """A host-relative path cannot establish a stable selected-skill source."""
        observation = dict(self.observation, entry_path="skills/probe/SKILL.md")
        self.assertTrue(any("entry_path must be absolute" in error for error in self.errors(observation)))

    def test_resource_path_escape_is_rejected(self):
        """A nonce read outside the installed plugin is not compatible resolution."""
        observation = json.loads(json.dumps(self.observation))
        observation["resource_reads"][2]["path"] = str(self.plugin_root.parent / "probe.md")
        self.assertTrue(any("contained" in error for error in self.errors(observation)))

    def test_missing_or_duplicate_nonce_is_rejected(self):
        """Repeating one resource cannot stand in for all three distinct direct reads."""
        observation = json.loads(json.dumps(self.observation))
        observation["resource_reads"][2]["nonce"] = observation["resource_reads"][1]["nonce"]
        errors = self.errors(observation)
        self.assertTrue(any("three distinct nonces" in error for error in errors), errors)

    def test_search_or_glob_transcript_is_rejected(self):
        """A fallback cache scan cannot be promoted to direct resource resolution."""
        errors = self.errors(transcript="Get-ChildItem -Recurse *.md")
        self.assertTrue(any("search/glob" in error for error in errors), errors)

    def test_operation_transcript_must_name_every_direct_read(self):
        """A final nonce summary alone cannot prove the nested resources were read."""
        echoed = self.read_events()
        for event in echoed:
            event["item"]["command"] = "Write-Output " + event["item"]["command"]
        errors = self.errors(
            transcript="\n".join(read["path"] for read in self.observation["resource_reads"]),
            events=echoed,
        )
        self.assertTrue(any("successful direct-read event" in error for error in errors), errors)

    def test_failed_read_event_cannot_satisfy_a_path(self):
        """A command mentioning the exact path with a non-zero exit is not a read proof."""
        errors = self.errors(events=self.read_events(failed_index=1))
        self.assertTrue(any("successful direct-read event" in error for error in errors), errors)

    def test_successful_read_event_must_capture_the_expected_nonce(self):
        """Exit zero with empty output cannot prove the fixture content was read."""
        events = self.read_events()
        events[1]["item"]["aggregated_output"] = ""
        errors = self.errors(events=events)
        self.assertTrue(any("nonce output" in error for error in errors), errors)

    def test_effective_policy_drift_is_rejected(self):
        """A full-access pass cannot satisfy the required read-only/never cell."""
        observation = dict(self.observation, effective_sandbox="danger-full-access")
        errors = self.errors(observation)
        self.assertTrue(any("effective sandbox" in error for error in errors), errors)


class LiveReceiptContractTest(LiveObservationContractTest):
    """Receipts bind runtime bytes and keep advisory failure separate."""

    def build(
        self, binary, expected, observation=None, stdout="events", stderr="", advisory=False,
        operation_events=None, operation_transcript=None,
    ):
        return self.checker.build_live_receipt(
            surface="cli",
            version="0.149.0" if advisory else "0.143.0",
            expected=expected,
            fixture_hash="f" * 64,
            evidence_contract_hash="e" * 64,
            executable=binary,
            installed_plugin_root=self.plugin_root,
            observation=self.observation if observation is None else observation,
            operation_transcript=(
                "\n".join(
                    "read -- " + str(self.plugin_root / relative)
                    for relative in self.checker.RESOURCE_FILES
                )
                if operation_transcript is None else operation_transcript
            ),
            operation_events=(
                self.read_events() if operation_events is None else operation_events
            ),
            stdout=stdout,
            stderr=stderr,
            network_policy="model-api-only; tool-network-disabled",
            advisory=advisory,
        )

    def test_passing_receipt_binds_backend_integrity_and_policies(self):
        """Dropping provenance or policy fields would make a PASS non-reproducible."""
        with tempfile.TemporaryDirectory() as temporary:
            binary = Path(temporary) / "codex"
            binary.write_bytes(b"fake-codex")
            expected = {
                "provenance": "test:codex@0.143.0",
                "integrity": "sha512-test",
                "native_executable_sha256": self.checker.sha256_file(binary),
            }
            receipt = self.build(binary, expected)
        self.assertEqual(receipt["verdict"], "PASS", receipt)
        self.assertEqual(receipt["surface"], "cli")
        self.assertFalse(receipt["desktop_shell_proven"])
        self.assertEqual(receipt["provenance"], "test:codex@0.143.0")
        self.assertEqual(receipt["evidence_contract_sha256"], "e" * 64)
        self.assertEqual(receipt["network_policy"], "model-api-only; tool-network-disabled")
        self.assertEqual(receipt["requested_sandbox"], "read-only")
        self.assertEqual(receipt["effective_approval_policy"], "never")
        self.assertTrue(receipt["environment"]["os_identity"])
        self.assertEqual(receipt["environment"]["execution_environment"], "isolated-clean-home")
        self.assertEqual(receipt["errors"], [])

    def test_untrusted_live_observation_is_not_persisted_or_hashed(self):
        secret = "api_key=must-not-pass"
        observation = json.loads(json.dumps(self.observation))
        observation["resource_reads"][0]["api_key"] = "must-not-pass"
        with tempfile.TemporaryDirectory() as temporary:
            binary = Path(temporary) / "codex"
            binary.write_bytes(b"fake-codex")
            expected = {
                "provenance": "test:codex@0.143.0",
                "integrity": "sha512-test",
                "native_executable_sha256": self.checker.sha256_file(binary),
            }
            receipt = self.build(
                binary, expected, observation=observation, stdout=secret
            )
        serialized = json.dumps(receipt, sort_keys=True)
        self.assertEqual(receipt["verdict"], "FAIL", receipt)
        self.assertIsNone(receipt["entry_path"])
        self.assertEqual(receipt["resource_reads"], [])
        self.assertIsNone(receipt["operation_transcript_sha256"])
        self.assertIsNone(receipt["stdout_sha256"])
        self.assertEqual(receipt["stderr_sha256"], self.checker._sha256_text(""))
        self.assertNotIn(secret, serialized)
        self.assertNotIn(self.checker._sha256_text(secret), serialized)
        self.assertEqual(receipt["errors"], ["live evidence contains untrusted output"])

    def test_ignored_protocol_payload_cannot_affect_durable_evidence_hashes(self):
        """Hashing complete protocol streams would preserve an unreviewed payload derivative."""
        with tempfile.TemporaryDirectory() as temporary:
            binary = Path(temporary) / "codex"
            binary.write_bytes(b"fake-codex")
            expected = {
                "provenance": "test:codex@0.143.0",
                "integrity": "sha512-test",
                "native_executable_sha256": self.checker.sha256_file(binary),
            }
            receipts = []
            raw_hashes = set()
            for payload in (
                "AbCdEfGhIjKlMnOpQrStUvWxYz0123456789AaBbCcDdEeFf",
                "ZyXwVuTsRqPoNmLkJiHgFeDcBa9876543210FfEeDdCcBbAa",
            ):
                events = self.read_events() + [
                    {"type": "unreviewed/event", "payload": payload}
                ]
                transcript = json.dumps(events, sort_keys=True)
                stdout = json.dumps({"messages": events}, sort_keys=True)
                receipts.append(
                    self.build(
                        binary,
                        expected,
                        stdout=stdout,
                        operation_events=events,
                        operation_transcript=transcript,
                    )
                )
                raw_hashes.update({
                    self.checker._sha256_text(payload),
                    self.checker._sha256_text(transcript),
                    self.checker._sha256_text(stdout),
                })

        for receipt in receipts:
            self.assertEqual(receipt["verdict"], "PASS", receipt)
            self.assertEqual(len(receipt["operation_transcript_sha256"]), 64)
            self.assertEqual(len(receipt["stdout_sha256"]), 64)
            self.assertTrue(raw_hashes.isdisjoint(json.dumps(receipt).split('"')))
        self.assertEqual(
            receipts[0]["operation_transcript_sha256"],
            receipts[1]["operation_transcript_sha256"],
        )
        self.assertEqual(receipts[0]["stdout_sha256"], receipts[1]["stdout_sha256"])

    def test_receipt_error_augmentation_discards_untrusted_diagnostics(self):
        """A later protocol diagnostic cannot undo the receipt builder's sanitization."""
        secret = "api_key=must-not-pass"
        with tempfile.TemporaryDirectory() as temporary:
            binary = Path(temporary) / "codex"
            binary.write_bytes(b"fake-codex")
            expected = {
                "provenance": "test:codex@0.143.0",
                "integrity": "sha512-test",
                "native_executable_sha256": self.checker.sha256_file(binary),
            }
            receipt = self.build(binary, expected)
        self.checker._add_receipt_errors(
            receipt,
            [f"turn/completed status must be completed, got {secret!r}"],
            secret,
            "",
        )

        serialized = json.dumps(receipt, sort_keys=True)
        self.assertEqual(receipt["verdict"], "FAIL", receipt)
        self.assertEqual(receipt["errors"], ["live evidence contains untrusted output"])
        self.assertIsNone(receipt["operation_transcript_sha256"])
        self.assertIsNone(receipt["stdout_sha256"])
        self.assertIsNone(receipt["stderr_sha256"])
        self.assertNotIn(secret, serialized)
        self.assertNotIn(self.checker._sha256_text(secret), serialized)

    def test_wrong_native_executable_hash_fails_closed(self):
        """A different native executable cannot inherit a supported cell's verdict."""
        with tempfile.TemporaryDirectory() as temporary:
            binary = Path(temporary) / "codex"
            binary.write_bytes(b"unexpected-codex")
            expected = {
                "provenance": "test:codex@0.143.0",
                "integrity": "sha512-test",
                "native_executable_sha256": "0" * 64,
            }
            receipt = self.build(binary, expected)
        self.assertEqual(receipt["verdict"], "FAIL")
        self.assertTrue(any("executable hash" in error for error in receipt["errors"]), receipt)

    def test_advisory_policy_rejection_preserves_separate_failure_hashes(self):
        """Latest drift must remain evidence without becoming a supported-cell pass."""
        with tempfile.TemporaryDirectory() as temporary:
            binary = Path(temporary) / "codex"
            binary.write_bytes(b"advisory-codex")
            expected = {
                "provenance": "test:codex@0.149.0",
                "integrity": "sha512-advisory",
                "native_executable_sha256": self.checker.sha256_file(binary),
            }
            receipt = self.build(
                binary,
                expected,
                observation={},
                stdout="read-only sandbox policy rejected the file read",
                stderr="operation blocked by policy",
                advisory=True,
            )
        self.assertEqual(receipt["verdict"], "FAIL")
        self.assertEqual(receipt["evidence_class"], "advisory")
        self.assertEqual(receipt["failure"]["classification"], "read-only-policy-rejection")
        self.assertEqual(len(receipt["failure"]["stdout_sha256"]), 64)
        self.assertEqual(len(receipt["failure"]["stderr_sha256"]), 64)
        self.assertNotEqual(
            receipt["failure"]["stdout_sha256"], receipt["failure"]["stderr_sha256"]
        )

    def test_missing_model_authentication_is_classified_without_persisting_output(self):
        """A clean-home 401 must be distinguishable from a resource-contract failure."""
        classification = self.checker._failure_classification(
            "unexpected status 401 Unauthorized: Missing bearer or basic authentication in header",
            "",
        )

        self.assertEqual(classification, "authentication-required")


class MarketplacePreparationTest(CheckerPresentMixin, unittest.TestCase):
    """The isolated fixture marketplace uses Codex's supported catalog location."""

    def test_marketplace_catalog_is_written_to_agents_plugin_root(self):
        """Writing the catalog under .codex-plugin makes pinned Codex reject the root."""
        with tempfile.TemporaryDirectory() as temporary:
            marketplace = self.checker._prepare_marketplace(Path(temporary), FIXTURE)

            catalog = marketplace / ".agents" / "plugins" / "marketplace.json"
            self.assertTrue(catalog.is_file(), "Codex marketplace catalog is missing")


class FakeCodexMixin:
    def write_fake_codex(self, root):
        script = root / "fake_codex.py"
        script.write_text(
            textwrap.dedent(
                r'''
                import json
                import os
                import shutil
                import sys
                from pathlib import Path

                args = sys.argv[1:]
                home = Path(os.environ["CODEX_HOME"])
                scenario = os.environ.get("CA_TEST_CODEX_SCENARIO", "pass")
                home.mkdir(parents=True, exist_ok=True)
                log_path = Path(
                    os.environ.get("CA_TEST_CODEX_LOG_PATH", home / "fake-command-log.jsonl")
                )
                log_path.parent.mkdir(parents=True, exist_ok=True)
                with log_path.open("a", encoding="utf-8") as log:
                    log.write(json.dumps(args) + "\n")
                if args == ["--version"]:
                    print("codex-cli " + os.environ.get("CA_TEST_CODEX_VERSION", "0.143.0"))
                    raise SystemExit(0)
                if args == ["login", "status"]:
                    if scenario == "api-key-auth":
                        print("Logged in using an API key")
                    elif scenario == "unknown-auth":
                        print("Logged in")
                    elif scenario == "logged-out":
                        print("Not logged in", file=sys.stderr)
                        raise SystemExit(1)
                    else:
                        print("Logged in using ChatGPT")
                        print("DO-NOT-PERSIST-LOGIN-STATUS")
                    raise SystemExit(0)
                if args[:3] == ["plugin", "marketplace", "add"]:
                    (home / "fake-marketplace-path.txt").write_text(args[3], encoding="utf-8")
                    print(json.dumps({"name": "codex-skill-resource-characterization"}))
                    raise SystemExit(0)
                if args[:2] == ["plugin", "add"]:
                    marketplace = Path((home / "fake-marketplace-path.txt").read_text(encoding="utf-8"))
                    destination = home / "plugins" / "cache" / "local-characterization" / "codex-skill-resource-probe" / "0.0.1"
                    shutil.copytree(marketplace / "plugin", destination)
                    if scenario == "plugin-config-required":
                        (home / "config.toml").write_text(
                            '[plugins."codex-skill-resource-probe"]\nenabled = true\n',
                            encoding="utf-8",
                        )
                    print(json.dumps({"installedPath": str(destination.resolve())}))
                    raise SystemExit(0)
                if args and args[0] == "exec":
                    if scenario == "explicit-read-prompt-required":
                        prompt = args[-1]
                        required_fragments = (
                            "exactly three Get-Content -LiteralPath commands",
                            "first directly read the selected entry SKILL.md",
                            "then follow each of its two relative links",
                            "Do not run any other command",
                        )
                        if not all(fragment in prompt for fragment in required_fragments):
                            print("probe prompt does not require the exact direct-read sequence", file=sys.stderr)
                            raise SystemExit(14)
                    if scenario == "valid-output-schema-required":
                        schema_path = Path(args[args.index("--output-schema") + 1])
                        schema = json.loads(schema_path.read_text(encoding="utf-8"))
                        resource_reads = schema.get("properties", {}).get("resource_reads", {})
                        items = resource_reads.get("items", {})
                        properties = items.get("properties", {})
                        if not (
                            resource_reads.get("type") == "array"
                            and items.get("type") == "object"
                            and set(items.get("required", [])) == {"path", "nonce"}
                            and properties.get("path") == {"type": "string"}
                            and properties.get("nonce") == {"type": "string"}
                            and items.get("additionalProperties") is False
                        ):
                            print("resource_reads array schema missing valid items", file=sys.stderr)
                            raise SystemExit(13)
                    if scenario == "plugin-config-required":
                        if "--ignore-user-config" in args:
                            print(
                                "installed plugin configuration hidden by --ignore-user-config",
                                file=sys.stderr,
                            )
                            raise SystemExit(8)
                        if not (home / "config.toml").is_file():
                            print("installed plugin configuration missing", file=sys.stderr)
                            raise SystemExit(9)
                    if scenario == "policy-arguments-required":
                        sandbox = (
                            args[args.index("--sandbox") + 1]
                            if "--sandbox" in args and args.index("--sandbox") + 1 < len(args)
                            else None
                        )
                        config_values = [
                            args[index + 1]
                            for index, value in enumerate(args[:-1])
                            if value == "--config"
                        ]
                        if sandbox != "read-only":
                            print("required read-only sandbox argument missing", file=sys.stderr)
                            raise SystemExit(10)
                        if 'approval_policy="never"' not in config_values:
                            print("required never approval argument missing", file=sys.stderr)
                            raise SystemExit(11)
                        if 'web_search="disabled"' not in config_values:
                            print("required disabled web-search argument missing", file=sys.stderr)
                            raise SystemExit(12)
                    if scenario == "policy-rejection":
                        print("read-only sandbox policy rejected the file read")
                        print("operation blocked by policy", file=sys.stderr)
                        raise SystemExit(7)
                    destination = home / "plugins" / "cache" / "local-characterization" / "codex-skill-resource-probe" / "0.0.1"
                    if scenario == "outside-plugin-root":
                        outside_destination = home.parent / "outside-plugin-root"
                        shutil.copytree(destination, outside_destination)
                        destination = outside_destination
                    paths = [
                        destination / "skills" / "probe" / "SKILL.md",
                        destination / "routines" / "nested.md",
                        destination / "agents" / "probe.md",
                    ]
                    nonces = [
                        "skill-probe-nonce-7f4d",
                        "nested-routine-nonce-2ca1",
                        "agent-probe-nonce-91be",
                    ]
                    observation = {
                        "entry_path": str(paths[0].resolve()),
                        "resource_reads": [
                            {"path": str(path.resolve()), "nonce": nonce}
                            for path, nonce in zip(paths, nonces)
                        ],
                        "requested_sandbox": "read-only",
                        "effective_sandbox": "read-only",
                        "requested_approval_policy": "never",
                        "effective_approval_policy": "never",
                    }
                    output = Path(args[args.index("--output-last-message") + 1])
                    output.write_text(json.dumps(observation), encoding="utf-8")
                    if scenario not in {
                        "missing-skill-event", "real-jsonl-no-skill-event",
                        "cat-read-no-skill-event", "type-read-no-skill-event",
                        "powershell-wrapper-no-skill-event",
                        "conflicting-command-argv-no-skill-event",
                        "conflicting-command-line-no-skill-event",
                        "conflicting-command-snake-line-no-skill-event",
                    }:
                        invoked_name = (
                            "another-plugin:probe"
                            if scenario == "wrong-skill-event"
                            else "codex-skill-resource-probe:probe"
                        )
                        print(json.dumps({
                            "type": "skill.invoked", "status": "completed",
                            "skill": {"name": invoked_name, "path": str(paths[0].resolve())},
                        }))
                    if scenario in {
                        "additional-skill-event", "additional-failed-skill-event",
                        "additional-malformed-skill-event", "duplicate-skill-event",
                    }:
                        if scenario == "additional-malformed-skill-event":
                            extra_skill = "not-an-object"
                            extra_status = "completed"
                        else:
                            extra_skill = {
                                "name": (
                                    "codex-skill-resource-probe:probe"
                                    if scenario == "duplicate-skill-event"
                                    else "another-plugin:unrelated"
                                ),
                                "path": str(paths[0].resolve()),
                            }
                            extra_status = (
                                "failed" if scenario == "additional-failed-skill-event" else "completed"
                            )
                        print(json.dumps({
                            "type": "skill.invoked", "status": extra_status,
                            "skill": extra_skill,
                        }))
                    command = "rg --files " + str(destination) if scenario == "search" else ""
                    for index, path in enumerate(paths):
                        if scenario == "cat-read-no-skill-event":
                            operation = 'cat -- "' + str(path) + '"'
                        elif scenario == "type-read-no-skill-event":
                            operation = 'type "' + str(path) + '"'
                        elif scenario == "powershell-wrapper-no-skill-event":
                            powershell = Path(os.environ.get("SystemRoot", r"C:\WINDOWS")) / "System32" / "WindowsPowerShell" / "v1.0" / "powershell.exe"
                            operation = '"' + str(powershell) + '" -Command "Get-Content -LiteralPath \'' + str(path) + '\'"'
                        else:
                            operation = command if index == 0 and command else 'Get-Content -LiteralPath "' + str(path) + '"'
                        item = {
                            "type": "command_execution", "command": operation,
                            "exit_code": 0, "status": "completed",
                            "aggregated_output": nonces[index],
                        }
                        if scenario == "conflicting-command-argv-no-skill-event":
                            item["command"] = "whoami"
                            item["argv"] = ["Get-Content", "-LiteralPath", str(path)]
                        elif scenario == "conflicting-command-line-no-skill-event":
                            item["commandLine"] = "whoami"
                        elif scenario == "conflicting-command-snake-line-no-skill-event":
                            item["command_line"] = "whoami"
                        print(json.dumps({"type": "item.completed", "item": item}))
                    if scenario == "fourth-command":
                        print(json.dumps({
                            "type": "item.completed",
                            "item": {
                                "type": "command_execution",
                                "command": 'Get-Content -LiteralPath "' + str(paths[0]) + '"',
                                "exit_code": 0,
                                "status": "completed",
                                "aggregated_output": nonces[0],
                            },
                        }))
                    print(json.dumps({"type": "agent.message", "message": json.dumps(observation)}))
                    raise SystemExit(0)
                if args and args[0] == "app-server":
                    destination = home / "plugins" / "cache" / "local-characterization" / "codex-skill-resource-probe" / "0.0.1"
                    paths = [
                        destination / "skills" / "probe" / "SKILL.md",
                        destination / "routines" / "nested.md",
                        destination / "agents" / "probe.md",
                    ]
                    nonces = [
                        "skill-probe-nonce-7f4d",
                        "nested-routine-nonce-2ca1",
                        "agent-probe-nonce-91be",
                    ]
                    for line in sys.stdin:
                        request = json.loads(line)
                        method = request.get("method")
                        request_id = request.get("id")
                        if method == "initialize":
                            codex_home = str(home.resolve())
                            if scenario == "wrong-home":
                                codex_home = str((home.parent / "wrong-home").resolve())
                            response = {"id": request_id, "result": {
                                "codexHome": codex_home,
                                "platformFamily": "windows" if os.name == "nt" else "unix",
                                "platformOs": "windows" if os.name == "nt" else "linux",
                                "userAgent": "fake-codex/0.143.0",
                            }}
                            print(json.dumps(response), flush=True)
                        elif method == "initialized":
                            continue
                        elif method == "skills/list":
                            cwd = request["params"]["cwds"][0]
                            listed_skills = [] if scenario == "missing-skill" else [{
                                "name": "codex-skill-resource-probe:probe",
                                "path": str(paths[0].resolve()),
                                "description": "probe",
                                "enabled": True,
                                "scope": "user",
                            }]
                            response = {"id": request_id, "result": {"data": [{
                                "cwd": cwd,
                                "errors": [],
                                "skills": listed_skills,
                            }]}}
                            print(json.dumps(response), flush=True)
                        elif method == "thread/start":
                            sandbox = {"type": "readOnly", "networkAccess": False}
                            if scenario == "string-sandbox":
                                sandbox = "read-only"
                            elif scenario == "missing-network-policy":
                                sandbox = {"type": "readOnly"}
                            response = {"id": request_id, "result": {
                                "thread": {"id": "thread-1"},
                                "approvalPolicy": "never",
                                "sandbox": sandbox,
                            }}
                            print(json.dumps(response), flush=True)
                        elif method == "turn/start":
                            skill_inputs = [item for item in request["params"]["input"] if item.get("type") == "skill"]
                            expected_skill = {
                                "type": "skill",
                                "name": "codex-skill-resource-probe:probe",
                                "path": str(paths[0].resolve()),
                            }
                            if skill_inputs != [expected_skill]:
                                print(json.dumps({"id": request_id, "error": {"message": "wrong typed skill input"}}), flush=True)
                                continue
                            if scenario == "structured-resource-prompt-required":
                                text_inputs = [
                                    item.get("text", "")
                                    for item in request["params"]["input"]
                                    if item.get("type") == "text"
                                ]
                                prompt = "\n".join(text_inputs)
                                required_fragments = (
                                    "resource_reads must be an array of exactly three objects",
                                    "each object must contain only path and nonce strings",
                                    "entry_path must be the selected absolute SKILL.md path",
                                )
                                if not all(fragment in prompt for fragment in required_fragments):
                                    print(json.dumps({"id": request_id, "error": {"message": "ambiguous observation shape"}}), flush=True)
                                    raise SystemExit(15)
                            print(json.dumps({"id": request_id, "result": {"turn": {"id": "turn-1"}}}), flush=True)
                            for index, path in enumerate(paths):
                                command = "rg --files " + str(destination) if scenario == "search" and index == 0 else 'Get-Content -LiteralPath "' + str(path) + '"'
                                print(json.dumps({
                                    "method": "item/completed",
                                    "params": {
                                        "threadId": "thread-1", "turnId": "turn-1", "completedAtMs": index,
                                        "item": {
                                            "type": "commandExecution", "id": "cmd-" + str(index),
                                            "command": command, "exitCode": 0, "status": "completed",
                                            "aggregatedOutput": nonces[index],
                                        },
                                    },
                                }), flush=True)
                            observation = {
                                "entry_path": str(paths[0].resolve()),
                                "resource_reads": [
                                    {"path": str(path.resolve()), "nonce": nonce}
                                    for path, nonce in zip(paths, nonces)
                                ],
                            }
                            print(json.dumps({
                                "method": "item/completed",
                                "params": {
                                    "threadId": "thread-1", "turnId": "turn-1", "completedAtMs": 4,
                                    "item": {"type": "agentMessage", "id": "message-1", "text": json.dumps(observation)},
                                },
                            }), flush=True)
                            print(json.dumps({
                                "method": "turn/completed",
                                "params": {"threadId": "thread-1", "turn": {
                                    "id": "turn-1",
                                    "status": "failed" if scenario == "failed-turn" else "completed",
                                }},
                            }), flush=True)
                    raise SystemExit(0)
                raise SystemExit("unexpected fake codex invocation: " + repr(args))
                '''
            ).lstrip(),
            encoding="utf-8",
        )
        return script


class CliLiveHarnessTest(FakeCodexMixin, CheckerPresentMixin, unittest.TestCase):
    """The CLI harness installs through native commands and validates real output."""

    def run_fake(self, scenario="pass", advisory=False):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            fake = self.write_fake_codex(root)
            command_log = root / "commands.jsonl"
            expected = {
                "surface": "cli",
                "version": "0.149.0" if advisory else "0.143.0",
                "provenance": "test:codex",
                "integrity": "sha512-test",
                "native_executable_sha256": self.checker.sha256_file(fake),
            }
            receipt = self.checker.run_cli_live(
                executable=fake,
                version=expected["version"],
                expected=expected,
                fixture_root=FIXTURE,
                repository=REPO_ROOT,
                advisory=advisory,
                extra_environment={
                    "CA_TEST_CODEX_SCENARIO": scenario,
                    "CA_TEST_CODEX_VERSION": expected["version"],
                    "CA_TEST_CODEX_LOG_PATH": str(command_log),
                },
            )

            commands = [json.loads(line) for line in command_log.read_text(encoding="utf-8").splitlines()]
            self.assertNotIn(["login", "status"], commands)
            self.assertNotIn("authentication_mode", receipt)
            return receipt

    def run_authenticated_fake(
        self, scenario="pass", expected_hash=None, expect_no_sibling_profile=False
    ):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            fake = self.write_fake_codex(root)
            authenticated_home = root / "authenticated-codex-home"
            authenticated_home.mkdir()
            sentinel = authenticated_home / "credential-sentinel"
            sentinel.write_text("controller-owned", encoding="utf-8")
            expected = {
                "surface": "cli",
                "version": "0.143.0",
                "provenance": "test:codex",
                "integrity": "sha512-test",
                "native_executable_sha256": (
                    expected_hash if expected_hash is not None else self.checker.sha256_file(fake)
                ),
            }
            try:
                receipt = self.checker.run_cli_live(
                    executable=fake,
                    version="0.143.0",
                    expected=expected,
                    fixture_root=FIXTURE,
                    repository=REPO_ROOT,
                    authenticated_codex_home=authenticated_home,
                    extra_environment={
                        "CA_TEST_CODEX_SCENARIO": scenario,
                        "CA_TEST_CODEX_VERSION": "0.143.0",
                    },
                )
            except TypeError as error:
                self.fail(f"CLI live runner rejected the approved authenticated-home interface: {error}")
            command_log = authenticated_home / "fake-command-log.jsonl"
            commands = [
                json.loads(line)
                for line in command_log.read_text(encoding="utf-8").splitlines()
            ] if command_log.is_file() else []
            self.assertTrue(authenticated_home.is_dir(), "checker deleted controller-owned auth home")
            self.assertEqual(sentinel.read_text(encoding="utf-8"), "controller-owned")
            if expect_no_sibling_profile:
                self.assertFalse(
                    (authenticated_home.parent / "profile").exists(),
                    "checker left its generated profile beside the controller-owned auth home",
                )
            return receipt, commands

    def test_fake_cli_pass_emits_bound_backend_receipt(self):
        """Changing install/invoke/parse behavior must break a complete fake-host pass."""
        receipt = self.run_fake()
        self.assertEqual(receipt["verdict"], "PASS", receipt)
        self.assertEqual(receipt["surface"], "cli")
        self.assertFalse(receipt["desktop_shell_proven"])
        self.assertEqual(receipt["version"], "0.143.0")
        self.assertEqual(len(receipt["resource_reads"]), 3)

    def test_authenticated_cli_verifies_chatgpt_and_records_only_non_secret_mode(self):
        """Skipping status verification or retaining its output would taint durable evidence."""
        receipt, commands = self.run_authenticated_fake()
        self.assertEqual(receipt["verdict"], "PASS", receipt)
        self.assertEqual(receipt["authentication_mode"], "chatgpt")
        self.assertEqual(commands[0], ["login", "status"])
        self.assertNotIn("DO-NOT-PERSIST-LOGIN-STATUS", json.dumps(receipt, sort_keys=True))

    def test_authenticated_cli_rejects_non_chatgpt_status_before_plugin_or_model_activity(self):
        """API-key, unknown, or logged-out status must fail before producing evidence."""
        for scenario in ("api-key-auth", "unknown-auth", "logged-out"):
            with self.subTest(scenario=scenario):
                receipt, commands = self.run_authenticated_fake(scenario)
                self.assertEqual(receipt["verdict"], "FAIL", receipt)
                self.assertNotIn("authentication_mode", receipt)
                self.assertEqual(commands, [["login", "status"]])
                self.assertTrue(any("ChatGPT" in error for error in receipt["errors"]), receipt)

    def test_authenticated_cli_rejects_wrong_binary_hash_before_first_invocation(self):
        """A substituted executable must never receive the authenticated environment."""
        receipt, commands = self.run_authenticated_fake(expected_hash="0" * 64)
        self.assertEqual(receipt["verdict"], "FAIL", receipt)
        self.assertEqual(commands, [])
        self.assertNotIn("authentication_mode", receipt)
        self.assertTrue(any("executable hash" in error for error in receipt["errors"]), receipt)

    def test_authenticated_cli_leaves_no_generated_sibling_profile(self):
        """Runner-owned profile state must be cleaned without deleting the supplied auth home."""
        receipt, _ = self.run_authenticated_fake(expect_no_sibling_profile=True)
        self.assertEqual(receipt["verdict"], "PASS", receipt)

    def test_live_cli_keeps_installed_plugin_config_visible_to_exec(self):
        """The isolated config written by plugin add must remain visible to model execution."""
        receipt = self.run_fake("plugin-config-required")
        self.assertEqual(receipt["verdict"], "PASS", receipt)

    def test_authenticated_live_cli_keeps_installed_plugin_config_visible_to_exec(self):
        """Required authenticated cells must preserve their newly installed plugin config."""
        receipt, commands = self.run_authenticated_fake("plugin-config-required")
        self.assertEqual(receipt["verdict"], "PASS", receipt)
        exec_commands = [command for command in commands if command[:1] == ["exec"]]
        self.assertEqual(len(exec_commands), 1, commands)
        self.assertNotIn("--ignore-user-config", exec_commands[0])

    def test_live_cli_pass_requires_exact_policy_arguments(self):
        """Claimed read-only and never policies must match the actual exec arguments."""
        receipt = self.run_fake("policy-arguments-required")
        self.assertEqual(receipt["verdict"], "PASS", receipt)

    def test_cli_output_schema_defines_resource_read_items(self):
        """The model API rejects array schemas that omit their item-object contract."""
        receipt = self.run_fake("valid-output-schema-required")
        self.assertEqual(receipt["verdict"], "PASS", receipt)

    def test_cli_prompt_requires_exact_three_direct_get_content_reads(self):
        """The model must be told to execute the auditable read sequence, not merely follow links."""
        receipt = self.run_fake("explicit-read-prompt-required")
        self.assertEqual(receipt["verdict"], "PASS", receipt)

    def test_cli_accepts_real_item_completed_reads_as_dispatch_evidence(self):
        """Exact 0.143.0 has no skill event, so its successful entry read must bind dispatch."""
        receipt = self.run_fake("real-jsonl-no-skill-event")
        self.assertEqual(receipt["verdict"], "PASS", receipt)
        self.assertEqual(
            receipt["skill_invocation_evidence"]["source"],
            "direct-entry-read",
        )

    def test_cli_accepts_exact_0143_quoted_powershell_read_events(self):
        """Windows 0.143 wraps each Get-Content command in one quoted -Command body."""
        receipt = self.run_fake("powershell-wrapper-no-skill-event")
        self.assertEqual(receipt["verdict"], "PASS", receipt)
        self.assertEqual(
            receipt["skill_invocation_evidence"]["source"],
            "direct-entry-read",
        )

    def test_cli_rejects_conflicting_command_representations(self):
        """A safe secondary representation cannot mask a contradictory executed command."""
        scenarios = (
            "conflicting-command-argv-no-skill-event",
            "conflicting-command-line-no-skill-event",
            "conflicting-command-snake-line-no-skill-event",
        )
        for scenario in scenarios:
            with self.subTest(scenario=scenario):
                receipt = self.run_fake(scenario)
                self.assertEqual(receipt["verdict"], "FAIL", receipt)
                self.assertIsNone(receipt["skill_invocation_evidence"], receipt)

    def test_cli_no_event_dispatch_rejects_cat_and_type_read_sequences(self):
        """Only the exact Get-Content -LiteralPath sequence can prove CLI dispatch."""
        for scenario in ("cat-read-no-skill-event", "type-read-no-skill-event"):
            with self.subTest(scenario=scenario):
                receipt = self.run_fake(scenario)
                self.assertEqual(receipt["verdict"], "FAIL", receipt)
                self.assertIsNone(receipt["skill_invocation_evidence"], receipt)

    def test_cli_rejects_a_fourth_completed_command_event(self):
        """Three valid reads cannot hide one additional executed command."""
        receipt = self.run_fake("fourth-command")
        self.assertEqual(receipt["verdict"], "FAIL", receipt)
        self.assertTrue(
            any("exactly three completed command events" in error for error in receipt["errors"]),
            receipt,
        )

    def test_live_cli_rejects_installed_root_outside_isolated_plugins_directory(self):
        """A host-reported skill outside isolated CODEX_HOME/plugins must fail closed."""
        receipt = self.run_fake("outside-plugin-root")
        self.assertEqual(receipt["verdict"], "FAIL", receipt)
        self.assertTrue(
            any("outside isolated CODEX_HOME/plugins" in error for error in receipt["errors"]),
            receipt,
        )

    def test_fake_cli_search_fallback_fails_closed(self):
        """A successful model response does not hide a cache-search command."""
        receipt = self.run_fake("search")
        self.assertEqual(receipt["verdict"], "FAIL")
        self.assertTrue(any("search/glob" in error for error in receipt["errors"]), receipt)

    def test_advisory_cli_failure_records_drift_without_a_false_pass(self):
        """A policy rejection is classified and hashed even without model output JSON."""
        receipt = self.run_fake("policy-rejection", advisory=True)
        self.assertEqual(receipt["verdict"], "FAIL")
        self.assertEqual(receipt["evidence_class"], "advisory")
        self.assertEqual(receipt["failure"]["classification"], "read-only-policy-rejection")

    def test_cli_rejects_a_contradictory_namespaced_skill_invocation_event(self):
        """A host event naming another skill cannot be overridden by valid file reads."""
        receipt = self.run_fake("wrong-skill-event")
        self.assertEqual(receipt["verdict"], "FAIL")
        self.assertTrue(
            any("skill invocation evidence" in error for error in receipt["errors"]),
            receipt,
        )

    def test_cli_rejects_any_additional_skill_invocation_event(self):
        """One valid probe event cannot hide another wrong, failed, malformed, or duplicate event."""
        scenarios = (
            "additional-skill-event",
            "additional-failed-skill-event",
            "additional-malformed-skill-event",
            "duplicate-skill-event",
        )
        for scenario in scenarios:
            with self.subTest(scenario=scenario):
                receipt = self.run_fake(scenario)
                self.assertEqual(receipt["verdict"], "FAIL")
                self.assertTrue(
                    any("complete skill invocation event set" in error for error in receipt["errors"]),
                    receipt,
                )


class AppServerLiveHarnessTest(FakeCodexMixin, CheckerPresentMixin, unittest.TestCase):
    """The app-server harness validates discovery and typed skill dispatch over stdio."""

    def run_fake(self, scenario="pass"):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            fake = self.write_fake_codex(root)
            command_log = root / "commands.jsonl"
            expected = {
                "surface": "app-server",
                "version": "0.143.0",
                "provenance": "test:codex",
                "integrity": "sha512-test",
                "native_executable_sha256": self.checker.sha256_file(fake),
            }
            receipt = self.checker.run_app_server_live(
                executable=fake,
                version="0.143.0",
                expected=expected,
                fixture_root=FIXTURE,
                repository=REPO_ROOT,
                extra_environment={
                    "CA_TEST_CODEX_SCENARIO": scenario,
                    "CA_TEST_CODEX_VERSION": "0.143.0",
                    "CA_TEST_CODEX_LOG_PATH": str(command_log),
                },
            )

            commands = [json.loads(line) for line in command_log.read_text(encoding="utf-8").splitlines()]
            self.assertNotIn(["login", "status"], commands)
            self.assertNotIn("authentication_mode", receipt)
            return receipt

    def run_authenticated_fake(
        self, scenario="pass", expected_hash=None, expect_no_sibling_profile=False
    ):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            fake = self.write_fake_codex(root)
            authenticated_home = root / "authenticated-codex-home"
            authenticated_home.mkdir()
            sentinel = authenticated_home / "credential-sentinel"
            sentinel.write_text("controller-owned", encoding="utf-8")
            expected = {
                "surface": "app-server",
                "version": "0.143.0",
                "provenance": "test:codex",
                "integrity": "sha512-test",
                "native_executable_sha256": (
                    expected_hash if expected_hash is not None else self.checker.sha256_file(fake)
                ),
            }
            receipt = self.checker.run_app_server_live(
                executable=fake,
                version="0.143.0",
                expected=expected,
                fixture_root=FIXTURE,
                repository=REPO_ROOT,
                authenticated_codex_home=authenticated_home,
                extra_environment={
                    "CA_TEST_CODEX_SCENARIO": scenario,
                    "CA_TEST_CODEX_VERSION": "0.143.0",
                },
            )
            commands = [
                json.loads(line)
                for line in (authenticated_home / "fake-command-log.jsonl")
                .read_text(encoding="utf-8")
                .splitlines()
            ] if (authenticated_home / "fake-command-log.jsonl").is_file() else []
            self.assertEqual(sentinel.read_text(encoding="utf-8"), "controller-owned")
            if expect_no_sibling_profile:
                self.assertFalse(
                    (authenticated_home.parent / "profile").exists(),
                    "checker left its generated profile beside the controller-owned auth home",
                )
            return receipt, commands

    def test_authenticated_app_server_uses_exact_home_and_records_chatgpt_mode(self):
        """App-server must not silently create a credential-free replacement home."""
        receipt, commands = self.run_authenticated_fake()
        self.assertEqual(receipt["verdict"], "PASS", receipt)
        self.assertEqual(receipt["authentication_mode"], "chatgpt")
        self.assertEqual(commands[0], ["login", "status"])
        self.assertNotIn("DO-NOT-PERSIST-LOGIN-STATUS", json.dumps(receipt, sort_keys=True))

    def test_authenticated_app_server_rejects_non_chatgpt_status_before_protocol_activity(self):
        """Every rejected auth mode must stop before plugin or app-server activity."""
        for scenario in ("api-key-auth", "unknown-auth", "logged-out"):
            with self.subTest(scenario=scenario):
                receipt, commands = self.run_authenticated_fake(scenario)
                self.assertEqual(receipt["verdict"], "FAIL", receipt)
                self.assertNotIn("authentication_mode", receipt)
                self.assertEqual(commands, [["login", "status"]])
                self.assertTrue(any("ChatGPT" in error for error in receipt["errors"]), receipt)

    def test_authenticated_app_server_rejects_wrong_binary_hash_before_first_invocation(self):
        """App-server cannot expose fresh OAuth state before pin verification."""
        receipt, commands = self.run_authenticated_fake(expected_hash="0" * 64)
        self.assertEqual(receipt["verdict"], "FAIL", receipt)
        self.assertEqual(commands, [])
        self.assertNotIn("authentication_mode", receipt)
        self.assertTrue(any("executable hash" in error for error in receipt["errors"]), receipt)

    def test_authenticated_app_server_leaves_no_generated_sibling_profile(self):
        """App-server isolation state must be owned and removed by the runner."""
        receipt, _ = self.run_authenticated_fake(expect_no_sibling_profile=True)
        self.assertEqual(receipt["verdict"], "PASS", receipt)

    def test_fake_app_server_pass_binds_discovery_dispatch_and_reads(self):
        """Breaking initialize, skills/list, typed dispatch, or direct reads must fail."""
        receipt = self.run_fake()
        self.assertEqual(receipt["verdict"], "PASS", receipt)
        self.assertEqual(receipt["surface"], "app-server")
        self.assertEqual(receipt["selected_skill"], "codex-skill-resource-probe:probe")
        self.assertEqual(receipt["effective_sandbox"], "read-only")
        self.assertEqual(receipt["effective_approval_policy"], "never")
        self.assertFalse(receipt["desktop_shell_proven"])

    def test_app_server_prompt_requires_path_nonce_object_shape(self):
        """The untyped app-server turn must state the exact validated observation shape."""
        receipt = self.run_fake("structured-resource-prompt-required")
        self.assertEqual(receipt["verdict"], "PASS", receipt)

    def test_app_server_rejects_wrong_initialized_codex_home(self):
        """A server attached to another profile is not an isolated characterization cell."""
        receipt = self.run_fake("wrong-home")
        self.assertEqual(receipt["verdict"], "FAIL")
        self.assertTrue(any("initialize.codexHome" in error for error in receipt["errors"]), receipt)

    def test_app_server_rejects_search_operation_despite_valid_final_message(self):
        """A valid nonce summary cannot conceal forbidden cache enumeration."""
        receipt = self.run_fake("search")
        self.assertEqual(receipt["verdict"], "FAIL")
        self.assertTrue(any("search/glob" in error for error in receipt["errors"]), receipt)

    def test_app_server_requires_structured_sandbox_with_network_disabled(self):
        """A string sandbox label cannot prove tool network was disabled."""
        for scenario in ("string-sandbox", "missing-network-policy"):
            with self.subTest(scenario=scenario):
                receipt = self.run_fake(scenario)
                self.assertEqual(receipt["verdict"], "FAIL")
                self.assertTrue(
                    any("sandbox object" in error for error in receipt["errors"]), receipt
                )

    def test_app_server_requires_successful_turn_completion(self):
        """A failed turn carrying a plausible final message remains failed evidence."""
        receipt = self.run_fake("failed-turn")
        self.assertEqual(receipt["verdict"], "FAIL")
        self.assertTrue(any("turn/completed status" in error for error in receipt["errors"]), receipt)

    def test_app_server_closes_all_subprocess_pipes(self):
        """Leaked stdio handles would accumulate across the four required cells."""
        with warnings.catch_warnings(record=True) as caught:
            warnings.simplefilter("always", ResourceWarning)
            self.run_fake()
            gc.collect()
        resource_warnings = [item for item in caught if item.category is ResourceWarning]
        self.assertEqual(resource_warnings, [], resource_warnings)

    def test_synthetic_protocol_diagnostic_is_bound_by_error_hash(self):
        """An internal protocol error must not affect classification outside hashed evidence."""
        receipt = self.run_fake("missing-skill")
        self.assertEqual(receipt["verdict"], "FAIL")
        expected_errors_hash = self.checker._sha256_text(
            json.dumps(receipt["errors"], separators=(",", ":"), sort_keys=True)
        )
        self.assertEqual(receipt["errors_sha256"], expected_errors_hash)
        self.assertEqual(receipt["failure"]["errors_sha256"], expected_errors_hash)
        self.assertEqual(receipt["stderr_sha256"], self.checker._sha256_text(""))


class CommandInterfaceTest(FakeCodexMixin, CheckerPresentMixin, unittest.TestCase):
    def test_reference_definition_escape_branch_is_disjoint(self):
        """Escaped characters and ordinary target characters must not overlap."""
        self.assertIn(r"[^\s\\]", self.checker.REFERENCE_DEFINITION.pattern)
        self.assertNotIn(r"[^\s]", self.checker.REFERENCE_DEFINITION.pattern)

    def test_parser_accepts_authenticated_home_for_live_backend_only(self):
        """Removing the opt-in seam would force live-cache reuse or API-key authentication."""
        parser = self.checker.build_parser()
        try:
            args = parser.parse_args([
                "--live", "--surface", "cli", "--codex-version", "0.143.0",
                "--authenticated-codex-home", "C:/Temp/fresh-codex-home",
            ])
        except SystemExit as error:
            self.fail(f"parser rejected the approved authenticated-home switch: {error}")
        self.assertEqual(args.authenticated_codex_home, "C:/Temp/fresh-codex-home")

    def test_authenticated_home_is_rejected_outside_live_mode(self):
        """Fixture validation must never consume or imply an authenticated profile."""
        error_output = io.StringIO()
        with mock.patch("sys.stderr", error_output), self.assertRaises(SystemExit):
            self.checker.main([
                "--fixtures-only",
                "--authenticated-codex-home", str(Path(tempfile.gettempdir()) / "codex-home"),
            ])
        self.assertIn(
            "live/candidate switches cannot be combined with --fixtures-only",
            error_output.getvalue(),
        )

    def test_live_cli_main_emits_json_and_returns_success_only_for_pass(self):
        """The CLI entry point must preserve the receipt verdict as its exit status."""
        with tempfile.TemporaryDirectory() as temporary:
            fake = self.write_fake_codex(Path(temporary))
            original = self.checker.PINNED_RELEASES["0.143.0"]
            self.checker.PINNED_RELEASES["0.143.0"] = {
                "provenance": "test:codex@0.143.0",
                "integrity": "sha512-test",
                "native_executable_sha256": self.checker.sha256_file(fake),
            }
            previous_scenario = os.environ.get("CA_TEST_CODEX_SCENARIO")
            previous_version = os.environ.get("CA_TEST_CODEX_VERSION")
            os.environ["CA_TEST_CODEX_SCENARIO"] = "pass"
            os.environ["CA_TEST_CODEX_VERSION"] = "0.143.0"
            try:
                output = io.StringIO()
                with mock.patch.dict(
                    os.environ,
                    {"CA_TEST_CODEX_SCENARIO": "pass", "CA_TEST_CODEX_VERSION": "0.143.0"},
                ), mock.patch("sys.stdout", output):
                    code = self.checker.main([
                        "--live", "--surface", "cli", "--codex-version", "0.143.0",
                        "--codex-binary", str(fake), "--json",
                    ])
                receipt = json.loads(output.getvalue())
            finally:
                self.checker.PINNED_RELEASES["0.143.0"] = original
                if previous_scenario is None:
                    os.environ.pop("CA_TEST_CODEX_SCENARIO", None)
                else:
                    os.environ["CA_TEST_CODEX_SCENARIO"] = previous_scenario
                if previous_version is None:
                    os.environ.pop("CA_TEST_CODEX_VERSION", None)
                else:
                    os.environ["CA_TEST_CODEX_VERSION"] = previous_version
        self.assertEqual(code, 0)
        self.assertEqual(receipt["verdict"], "PASS", receipt)

class StaticCandidatePackageContractTest(CheckerPresentMixin, unittest.TestCase):
    """The release contract rejects malformed shipped package shape, not just bad links."""

    def setUp(self):
        super().setUp()
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.package = Path(self.temporary.name) / "ca-codex"
        shutil.copytree(REPO_ROOT / "plugins" / "ca-codex", self.package)

    def run_contract(self):
        output = io.StringIO()
        with mock.patch("sys.stdout", output):
            status = self.checker.main([
                "--candidate-contract-only",
                "--candidate-package", str(self.package),
                "--json",
            ])
        return status, json.loads(output.getvalue())

    def assert_contract_rejects(self, expected_error):
        status, result = self.run_contract()
        self.assertEqual(status, 1, result)
        self.assertEqual(result["verdict"], "FAIL", result)
        self.assertTrue(
            any(expected_error in error for error in result["errors"]),
            result,
        )

    def test_rejects_missing_plugin_manifest(self):
        (self.package / ".codex-plugin" / "plugin.json").unlink()
        self.assert_contract_rejects("plugin manifest")

    def test_rejects_wrong_manifest_name(self):
        manifest_path = self.package / ".codex-plugin" / "plugin.json"
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        manifest["name"] = "not-ca-codex"
        manifest_path.write_text(json.dumps(manifest), encoding="utf-8", newline="\n")
        self.assert_contract_rejects("manifest name")

    def test_rejects_non_semver_manifest_version(self):
        manifest_path = self.package / ".codex-plugin" / "plugin.json"
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        manifest["version"] = "0_bad"
        manifest_path.write_text(json.dumps(manifest), encoding="utf-8", newline="\n")
        self.assert_contract_rejects("manifest version")

    def test_rejects_duplicate_manifest_members(self):
        manifest_path = self.package / ".codex-plugin" / "plugin.json"
        manifest_path.write_text(
            '{"name":"ca-codex","name":"other","version":"0.7.5"}\n',
            encoding="utf-8", newline="\n",
        )
        self.assert_contract_rejects("duplicate")

    def test_rejects_missing_skill_frontmatter(self):
        skill = self.package / "skills" / "ca-add-dep" / "SKILL.md"
        text = skill.read_text(encoding="utf-8")
        skill.write_text(text.split("---\n", 2)[-1], encoding="utf-8", newline="\n")
        self.assert_contract_rejects("front matter")

    def test_rejects_skill_name_that_disagrees_with_its_path(self):
        skill = self.package / "skills" / "ca-add-dep" / "SKILL.md"
        skill.write_text(
            skill.read_text(encoding="utf-8").replace(
                "name: ca-add-dep", "name: ca-not-the-path", 1
            ),
            encoding="utf-8", newline="\n",
        )
        self.assert_contract_rejects("front matter name")

    def test_rejects_duplicate_front_matter_fields(self):
        skill = self.package / "skills" / "ca-add-dep" / "SKILL.md"
        skill.write_text(
            skill.read_text(encoding="utf-8").replace(
                "name: ca-add-dep\n", "name: ca-add-dep\nname: ca-add-dep\n", 1
            ),
            encoding="utf-8", newline="\n",
        )
        self.assert_contract_rejects("duplicate front matter")

    def test_rejects_malformed_quoted_front_matter_scalar(self):
        skill = self.package / "skills" / "ca-add-dep" / "SKILL.md"
        skill.write_text(
            skill.read_text(encoding="utf-8").replace(
                "name: ca-add-dep", 'name: "ca-add-dep', 1
            ),
            encoding="utf-8", newline="\n",
        )
        self.assert_contract_rejects("quoted front matter")

    def test_rejects_agent_without_classification(self):
        agent = self.package / "agents" / "dependency-reviewer.md"
        agent.write_text(
            agent.read_text(encoding="utf-8").replace(
                "classification: reviewer\n", "", 1
            ),
            encoding="utf-8", newline="\n",
        )
        self.assert_contract_rejects("classification")

    def test_rejects_missing_hook_target(self):
        (self.package / "hooks" / "session-start.py").unlink()
        self.assert_contract_rejects("hook target")

    def test_rejects_non_native_hook_root_vocabulary(self):
        hooks = self.package / "hooks" / "hooks.json"
        hooks.write_text(
            hooks.read_text(encoding="utf-8").replace(
                "${PLUGIN_ROOT}", "${CLAUDE_PLUGIN_ROOT}", 1
            ),
            encoding="utf-8", newline="\n",
        )
        self.assert_contract_rejects("PLUGIN_ROOT")

    def test_rejects_hook_command_with_appended_shell_payload(self):
        hooks = self.package / "hooks" / "hooks.json"
        hooks.write_text(
            hooks.read_text(encoding="utf-8").replace(
                'python3 \\"${PLUGIN_ROOT}/hooks/session-start.py\\"',
                'python3 \\"${PLUGIN_ROOT}/hooks/session-start.py\\" && external-command',
                1,
            ),
            encoding="utf-8", newline="\n",
        )
        self.assert_contract_rejects("hook command grammar")

    def test_rejects_hook_command_with_prefixed_external_executable(self):
        hooks = self.package / "hooks" / "hooks.json"
        hooks.write_text(
            hooks.read_text(encoding="utf-8").replace(
                'python3 \\"${PLUGIN_ROOT}/hooks/session-start.py\\"',
                'external-command python3 \\"${PLUGIN_ROOT}/hooks/session-start.py\\"',
                1,
            ),
            encoding="utf-8", newline="\n",
        )
        self.assert_contract_rejects("hook command grammar")

    def test_rejects_unknown_hook_schema_field(self):
        hooks_path = self.package / "hooks" / "hooks.json"
        hooks = json.loads(hooks_path.read_text(encoding="utf-8"))
        hooks["unexpected"] = True
        hooks_path.write_text(json.dumps(hooks), encoding="utf-8", newline="\n")
        self.assert_contract_rejects("hook manifest schema")

    def test_rejects_duplicate_hook_manifest_members(self):
        hooks_path = self.package / "hooks" / "hooks.json"
        text = hooks_path.read_text(encoding="utf-8")
        hooks_path.write_text(
            text.replace('{\n  "hooks":', '{\n  "hooks": {},\n  "hooks":', 1),
            encoding="utf-8", newline="\n",
        )
        self.assert_contract_rejects("duplicate")

    def test_rejects_missing_security_hook_events(self):
        hooks_path = self.package / "hooks" / "hooks.json"
        for event in ("PreToolUse", "PostToolUse"):
            with self.subTest(event=event):
                hooks = json.loads(hooks_path.read_text(encoding="utf-8"))
                del hooks["hooks"][event]
                hooks_path.write_text(json.dumps(hooks), encoding="utf-8", newline="\n")
                self.assert_contract_rejects("hook inventory")
                shutil.copy2(REPO_ROOT / "plugins" / "ca-codex" / "hooks" / "hooks.json", hooks_path)

    def test_rejects_changed_security_hook_matcher(self):
        hooks_path = self.package / "hooks" / "hooks.json"
        hooks = json.loads(hooks_path.read_text(encoding="utf-8"))
        hooks["hooks"]["PreToolUse"][0]["matcher"] = "NeverMatches"
        hooks_path.write_text(json.dumps(hooks), encoding="utf-8", newline="\n")
        self.assert_contract_rejects("hook inventory")

    def test_rejects_security_hook_rerouted_to_another_shipped_target(self):
        hooks_path = self.package / "hooks" / "hooks.json"
        hooks = json.loads(hooks_path.read_text(encoding="utf-8"))
        entry = hooks["hooks"]["PostToolUse"][0]["hooks"][0]
        entry["command"] = 'python3 "${PLUGIN_ROOT}/hooks/session-start.py"'
        entry["commandWindows"] = 'python "${PLUGIN_ROOT}/hooks/session-start.py"'
        hooks_path.write_text(json.dumps(hooks), encoding="utf-8", newline="\n")
        self.assert_contract_rejects("hook inventory")


class CandidateResourceContractSafetyTest(CheckerPresentMixin, unittest.TestCase):
    def write_zip(self, entries, *, name="candidate.zip", compression=zipfile.ZIP_STORED):
        path = Path(self.temporary.name) / name
        with zipfile.ZipFile(path, "w", compression=compression) as archive:
            for name, value in entries:
                if isinstance(value, zipfile.ZipInfo):
                    archive.writestr(value, "../outside.md")
                else:
                    archive.writestr(name, value)
        return path

    def setUp(self):
        super().setUp()
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.base = [
            ("plugins/ca-codex/skills/probe.md", "[Agent](../agents/probe.md)\n"),
            ("plugins/ca-codex/agents/probe.md", "# Agent\n"),
        ]

    def test_rejects_candidate_archive_resource_exhaustion_before_reading_entries(self):
        """ARC-01: hostile ZIP metadata or expansion must fail before full entry reads."""
        archive_bytes = self.write_zip(
            [
                (f"plugins/ca-codex/agents/archive-{index}.bin", os.urandom(1800 * 1024))
                for index in range(5)
            ],
            name="archive-bytes.zip",
        )
        entry_count = self.write_zip(
            [
                (f"plugins/ca-codex/agents/entry-{index:04d}.md", "# entry\n")
                for index in range(1025)
            ],
            name="entry-count.zip",
        )
        per_entry = self.write_zip(
            [("plugins/ca-codex/agents/oversized.bin", b"x" * (2 * 1024 * 1024 + 1))],
            name="per-entry.zip",
        )
        moderately_compressible = b"".join(
            os.urandom(32 * 1024) * 8 for _ in range(8)
        )
        total_expansion = self.write_zip(
            [
                (f"plugins/ca-codex/agents/total-{index:02d}.bin", moderately_compressible)
                for index in range(17)
            ],
            name="total-expansion.zip",
            compression=zipfile.ZIP_DEFLATED,
        )
        high_ratio = self.write_zip(
            [("plugins/ca-codex/agents/high-ratio.bin", b"z" * (1024 * 1024))],
            name="high-ratio.zip",
            compression=zipfile.ZIP_DEFLATED,
        )

        self.assertGreater(archive_bytes.stat().st_size, 8 * 1024 * 1024)
        with zipfile.ZipFile(entry_count) as archive:
            self.assertEqual(len(archive.infolist()), 1025)
        self.assertEqual(len(moderately_compressible), 2 * 1024 * 1024)
        self.assertGreater(17 * len(moderately_compressible), 32 * 1024 * 1024)
        with zipfile.ZipFile(high_ratio) as archive:
            ratio_entry = archive.infolist()[0]
            self.assertGreater(ratio_entry.file_size / ratio_entry.compress_size, 100)

        for label, path in {
            "archive bytes": archive_bytes,
            "entry count": entry_count,
            "per-entry expansion": per_entry,
            "total expansion": total_expansion,
            "compression ratio": high_ratio,
        }.items():
            with self.subTest(label=label), self.assertRaises(ValueError):
                self.checker._candidate_package_files(path)

    def test_rejects_candidate_directory_resource_exhaustion_before_file_reads(self):
        limits = {
            "max_archive_bytes": 8,
            "max_entries": 2,
            "max_entry_uncompressed_bytes": 2,
            "max_total_uncompressed_bytes": 3,
            "max_compression_ratio": 100,
        }
        cases = {
            "entry count": (b"a", b"b", b"c"),
            "per entry": (b"abc",),
            "total bytes": (b"ab", b"cd"),
        }
        for label, contents in cases.items():
            with self.subTest(label=label), tempfile.TemporaryDirectory() as temporary:
                package = Path(temporary) / "ca-codex"
                package.mkdir()
                for index, content in enumerate(contents):
                    (package / f"file-{index}.md").write_bytes(content)
                with mock.patch.object(
                    self.checker, "_candidate_archive_limits", return_value=limits
                ), self.assertRaises(ValueError):
                    self.checker._candidate_package_files(package)

    def test_rejects_too_many_empty_candidate_directories_before_descent(self):
        limits = {
            "max_archive_bytes": 8,
            "max_entries": 2,
            "max_entry_uncompressed_bytes": 2,
            "max_total_uncompressed_bytes": 3,
            "max_compression_ratio": 100,
        }
        with tempfile.TemporaryDirectory() as temporary:
            package = Path(temporary) / "ca-codex"
            package.mkdir()
            for index in range(3):
                (package / f"empty-{index}").mkdir()
            with mock.patch.object(
                self.checker, "_candidate_archive_limits", return_value=limits
            ), self.assertRaisesRegex(ValueError, "entry-count"):
                self.checker._candidate_package_files(package)

    def test_rejects_windows_ambiguous_archive_paths(self):
        for label, additions in {
            "case collision": [
                ("plugins/ca-codex/skills/Probe.md", "# collision\n"),
            ],
            "unicode collision": [
                ("plugins/ca-codex/agents/é.md", "# composed\n"),
                ("plugins/ca-codex/agents/e\u0301.md", "# decomposed\n"),
            ],
            "casefold then NFC collision": [
                ("plugins/ca-codex/agents/\u0124\u0331.md", "# upper\n"),
                ("plugins/ca-codex/agents/\u0125\u0331.md", "# lower\n"),
            ],
            "trailing dot": [("plugins/ca-codex/agents/alias.md.", "# alias\n")],
            "trailing space": [("plugins/ca-codex/agents/alias.md ", "# alias\n")],
            "ADS colon": [("plugins/ca-codex/agents/probe.md:evil.md", "# ads\n")],
            "reserved name": [("plugins/ca-codex/agents/CON.md", "# reserved\n")],
            "reserved name before spaced extension": [
                ("plugins/ca-codex/agents/CON .md", "# reserved\n")
            ],
            "superscript COM reserved name": [
                ("plugins/ca-codex/agents/COM\u00b9.md", "# reserved\n")
            ],
            "superscript LPT reserved name": [
                ("plugins/ca-codex/agents/LPT\u00b3.md", "# reserved\n")
            ],
            "file directory collision": [
                ("plugins/ca-codex/agents/collision", "file\n"),
                ("plugins/ca-codex/agents/collision/child.md", "# child\n"),
            ],
            "explicit directory case collision": [
                ("plugins/ca-codex/Agents/", b""),
                ("plugins/ca-codex/agents/", b""),
            ],
            "explicit directory unicode collision": [
                ("plugins/ca-codex/agents/é/", b""),
                ("plugins/ca-codex/agents/e\u0301/", b""),
            ],
            "explicit directory file collision": [
                ("plugins/ca-codex/agents/probe.md/", b""),
            ],
        }.items():
            with self.subTest(label=label):
                with self.assertRaises(ValueError):
                    self.checker.candidate_resource_contract(
                        self.write_zip(self.base + additions)
                    )

    def test_rejects_zip_symlinks_and_outside_prefix_files(self):
        link = zipfile.ZipInfo("plugins/ca-codex/agents/link.md")
        link.create_system = 3
        link.external_attr = (stat.S_IFLNK | 0o777) << 16
        trailing_link = zipfile.ZipInfo("plugins/ca-codex/agents/link/")
        trailing_link.create_system = 3
        trailing_link.external_attr = (stat.S_IFLNK | 0o777) << 16
        for label, additions in {
            "symlink": [("ignored", link)],
            "trailing slash symlink": [("ignored", trailing_link)],
            "parent outside": [("../evil.md", "secret\n")],
            "absolute outside": [("/evil.md", "secret\n")],
            "sibling outside": [("plugins/ca/evil.md", "secret\n")],
        }.items():
            with self.subTest(label=label):
                with self.assertRaises(ValueError):
                    self.checker.candidate_resource_contract(
                        self.write_zip(self.base + additions)
                    )

    def test_rejects_directory_symlink_before_reading_outside_bytes(self):
        package = Path(self.temporary.name) / "package"
        (package / "skills").mkdir(parents=True)
        (package / "agents").mkdir()
        (package / "skills" / "probe.md").write_text(
            "[Agent](../agents/probe.md)\n", encoding="utf-8"
        )
        outside = Path(self.temporary.name) / "outside.md"
        outside.write_text("# outside\n", encoding="utf-8")
        try:
            (package / "agents" / "probe.md").symlink_to(outside)
        except OSError as error:
            self.skipTest(f"filesystem symlink unavailable: {error}")
        with self.assertRaises(ValueError):
            self.checker.candidate_resource_contract(package)

    def test_rejects_candidate_and_nested_package_root_symlinks(self):
        target = Path(self.temporary.name) / "target"
        (target / "skills").mkdir(parents=True)
        (target / "agents").mkdir()
        (target / "skills" / "probe.md").write_text(
            "[Agent](../agents/probe.md)\n", encoding="utf-8"
        )
        (target / "agents" / "probe.md").write_text("# Agent\n", encoding="utf-8")
        argument_link = Path(self.temporary.name) / "argument-link"
        repository = Path(self.temporary.name) / "repository"
        (repository / "plugins").mkdir(parents=True)
        nested_link = repository / "plugins" / "ca-codex"
        try:
            argument_link.symlink_to(target, target_is_directory=True)
            nested_link.symlink_to(target, target_is_directory=True)
        except OSError as error:
            self.skipTest(f"directory symlink unavailable: {error}")
        for path in (argument_link, repository):
            with self.subTest(path=path), self.assertRaises(ValueError):
                self.checker.candidate_resource_contract(path)

    def test_markdown_contexts_exclude_literals_and_include_shortcut_references(self):
        path = self.write_zip([
            (
                "plugins/ca-codex/skills/probe.md",
                "`['project']['version']`\n\n"
                "\\[Escaped](../agents/ignored.md)\n\n"
                "\\[Escaped reference][Ignored]\n\n"
                "![Image](../agents/ignored.md)\n\n"
                "![Reference image][Ignored]\n\n"
                "<!-- [Comment](../agents/ignored.md) -->\n\n"
                "```markdown\n[Fenced](../agents/ignored.md)\n```\n\n"
                "    [Indented](../agents/ignored.md)\n\n"
                "[Agent]\n\n[Agent]: ../agents/probe.md 'route'\n"
                "[Ignored]: ../agents/ignored.md\n",
            ),
            ("plugins/ca-codex/agents/probe.md", "# Agent\n"),
        ])
        contract = self.checker.candidate_resource_contract(path)
        self.assertEqual(contract["relative_reads"], [{
            "source_path": "skills/probe.md",
            "reference": "../agents/probe.md",
            "resolved_path": "agents/probe.md",
        }])

    def test_actual_codex_package_passes_candidate_contract_preflight(self):
        contract = self.checker.candidate_resource_contract(REPO_ROOT / "plugins" / "ca-codex")
        self.assertTrue(contract["selected_paths"])
        self.assertRegex(contract["sha256"], r"^[0-9a-f]{64}$")

    def test_template_destinations_are_contained_but_not_concrete_reads(self):
        contained = self.write_zip([(
            "plugins/ca-codex/skills/probe.md",
            "[Agent template](../agents/<name>.md)\n",
        )])
        contract = self.checker.candidate_resource_contract(contained)
        self.assertEqual(contract["relative_reads"], [])

        escaped = self.write_zip([(
            "plugins/ca-codex/skills/probe.md",
            "[Escaping template](../../../<name>.md)\n",
        )])
        with self.assertRaisesRegex(ValueError, "escaped"):
            self.checker.candidate_resource_contract(escaped)

    def test_template_destinations_reject_unknown_embedded_and_unrouted_placeholders(self):
        cases = (
            ("unknown", "../agents/<nam>.md"),
            ("embedded", "../agents/prefix-<name>.md"),
            ("unrouted", "../includes/<name>.md"),
        )
        for label, target in cases:
            with self.subTest(label=label):
                package = self.write_zip([(
                    "plugins/ca-codex/skills/probe.md",
                    f"[Unsupported template]({target})\n",
                )])
                with self.assertRaisesRegex(ValueError, "unsupported template"):
                    self.checker.candidate_resource_contract(package)

    def test_symbolic_markdown_template_link_is_not_a_runtime_read(self):
        sources = {
            "inline": "[Agent template](../agents/<name>.md)\n",
            "inline title": "[Agent template](../agents/<name>.md 'route')\n",
            "escaped image marker": "\\![Agent template](../agents/<name>.md)\n",
            "full reference": (
                "[Agent template][Template]\n\n"
                "[Template]: ../agents/<name>.md\n"
            ),
            "collapsed reference": (
                "[Template][]\n\n[Template]: ../agents/<name>.md\n"
            ),
        }
        for label, source in sources.items():
            with self.subTest(label=label):
                path = self.write_zip([
                    ("plugins/ca-codex/skills/probe.md", source),
                    ("plugins/ca-codex/agents/probe.md", "# Agent\n"),
                ], name=f"symbolic-{label.replace(' ', '-')}.zip")
                self.assertEqual(
                    self.checker.candidate_resource_contract(path)["relative_reads"],
                    [],
                )

    def test_symbolic_markdown_template_link_cannot_escape_candidate(self):
        sources = {
            "relative inline": "[Agent template](../../../../<name>.md)\n",
            "root inline": "[Agent template](/agents/<name>.md)\n",
            "relative reference": (
                "[Agent template][Template]\n\n"
                "[Template]: ../../../../<name>.md\n"
            ),
        }
        for label, source in sources.items():
            with self.subTest(label=label):
                path = self.write_zip([
                    ("plugins/ca-codex/skills/probe.md", source),
                ], name=f"symbolic-escape-{label.replace(' ', '-')}.zip")
                with self.assertRaisesRegex(
                    ValueError, "candidate resource link is escaped"
                ):
                    self.checker.candidate_resource_contract(path)

    def test_symbolic_markdown_template_survives_path_normalization(self):
        sources = {
            "inline": "[Agent template](../agents/<name>/../probe.md)\n",
            "reference": (
                "[Agent template][Template]\n\n"
                "[Template]: ../agents/<name>/../probe.md\n"
            ),
        }
        for label, source in sources.items():
            with self.subTest(label=label):
                path = self.write_zip([
                    ("plugins/ca-codex/skills/probe.md", source),
                    ("plugins/ca-codex/agents/probe.md", "# Agent\n"),
                ], name=f"symbolic-normalization-{label}.zip")
                with self.assertRaisesRegex(
                    ValueError, "normalization removes a symbolic segment"
                ):
                    self.checker.candidate_resource_contract(path)

    def test_symbolic_markdown_link_scan_is_bounded_near_entry_limit(self):
        source = "[Template](../agents/<name>.md)\n" * 30_000
        started = time.perf_counter()
        links = self.checker._markdown_resource_links(source)
        elapsed = time.perf_counter() - started
        self.assertEqual(len(links), 30_000)
        self.assertLess(
            elapsed,
            5.0,
            f"symbolic Markdown link scan took {elapsed:.2f}s near the entry limit",
        )

    def test_dense_symbolic_target_is_bounded_near_entry_limit(self):
        target = "../agents/" + "<a>" * 64_000 + ".md"
        path = self.write_zip([
            ("plugins/ca-codex/skills/probe.md", f"[Template]({target})\n"),
        ], name="dense-symbolic-target.zip")
        started = time.perf_counter()
        with self.assertRaisesRegex(ValueError, "unsupported template"):
            self.checker.candidate_resource_contract(path)
        elapsed = time.perf_counter() - started
        self.assertLess(
            elapsed,
            5.0,
            f"dense symbolic target validation took {elapsed:.2f}s near the entry limit",
        )

    def test_symbolic_targets_remain_inert_only_in_supported_markdown_contexts(self):
        inert_sources = {
            "non-markdown route": "[Route](../agents/<name>.json)\n",
            "inline code": "`[Template](../agents/<name>.md)`\n",
            "fenced code": "```md\n[Template](../agents/<name>.md)\n```\n",
            "comment": "<!-- [Template](../agents/<name>.md) -->\n",
            "raw html": '<span title="[Template](../agents/<name>.md)">x</span>\n',
        }
        for label, source in inert_sources.items():
            with self.subTest(label=label):
                path = self.write_zip([
                    ("plugins/ca-codex/skills/probe.md", source),
                ], name=f"symbolic-context-{label.replace(' ', '-')}.zip")
                self.assertEqual(
                    self.checker.candidate_resource_contract(path)["relative_reads"],
                    [],
                )

        invalid = self.write_zip([
            (
                "plugins/ca-codex/skills/probe.md",
                "[Template][Route]\n\n[Route]: ../agents/<name>@.md\n",
            ),
        ], name="invalid-symbolic-target.zip")
        with self.assertRaisesRegex(ValueError, "invalid symbolic target"):
            self.checker.candidate_resource_contract(invalid)

    def test_characterizes_malformed_title_and_unresolved_concrete_markdown(self):
        malformed_title = self.write_zip([
            (
                "plugins/ca-codex/skills/probe.md",
                "[Agent](../agents/probe.md unsupported-title)\n",
            ),
            ("plugins/ca-codex/agents/probe.md", "# Agent\n"),
        ], name="malformed-inline-title.zip")
        with self.assertRaisesRegex(ValueError, "unsupported inline link title"):
            self.checker.candidate_resource_contract(malformed_title)

        unresolved = self.write_zip([
            (
                "plugins/ca-codex/skills/probe.md",
                "[Missing](../agents/missing.md)\n",
            ),
        ], name="unresolved-concrete-markdown.zip")
        with self.assertRaisesRegex(ValueError, "escaped or unresolved"):
            self.checker.candidate_resource_contract(unresolved)

    def test_deep_balanced_destination_is_included_and_nonpunctuation_escape_rejected(self):
        balanced = self.write_zip([
            ("plugins/ca-codex/skills/probe.md", "[Deep](../agents/a((b)).md)\n"),
            ("plugins/ca-codex/agents/a((b)).md", "# Deep\n"),
        ])
        self.assertEqual(
            self.checker.candidate_resource_contract(balanced)["relative_reads"],
            [{
                "source_path": "skills/probe.md",
                "reference": "../agents/a((b)).md",
                "resolved_path": "agents/a((b)).md",
            }],
        )
        escaped = self.write_zip([
            ("plugins/ca-codex/skills/probe.md", "[Bad](../agents/\\probe.md)\n"),
            ("plugins/ca-codex/agents/probe.md", "# Agent\n"),
        ])
        with self.assertRaises(ValueError):
            self.checker.candidate_resource_contract(escaped)

    def test_markdown_escape_code_container_reference_and_empty_destination_edges(self):
        expected = [{
            "source_path": "skills/probe.md",
            "reference": "../agents/a.md",
            "resolved_path": "agents/a.md",
        }]
        recognized = {
            "escaped image marker": "\\![Real](../agents/a.md)\n",
            "even backslash shortcut": "\\\\[ID]\n\n[ID]: ../agents/a.md\n",
            "unmatched code delimiter": "`` [Real](../agents/a.md) ```\n",
        }
        for label, source in recognized.items():
            with self.subTest(label=label):
                path = self.write_zip([
                    ("plugins/ca-codex/skills/probe.md", source),
                    ("plugins/ca-codex/agents/a.md", "# Agent\n"),
                ])
                self.assertEqual(
                    self.checker.candidate_resource_contract(path)["relative_reads"],
                    expected,
                )

        unbalanced = self.write_zip([
            (
                "plugins/ca-codex/skills/probe.md",
                "[ID]\n\n[ID]: ../agents/a(b.md\n",
            ),
            ("plugins/ca-codex/agents/a(b.md", "# Agent\n"),
        ])
        with self.assertRaises(ValueError):
            self.checker.candidate_resource_contract(unbalanced)

        literal = self.write_zip([
            (
                "plugins/ca-codex/skills/probe.md",
                ">     [Fake](../agents/missing.md)\n\n[Self]()\n",
            ),
        ])
        self.assertEqual(
            self.checker.candidate_resource_contract(literal)["relative_reads"], []
        )

    def test_markdown_blockquote_fences_html_attributes_and_angle_references(self):
        literal = self.write_zip([
            (
                "plugins/ca-codex/skills/probe.md",
                "> ~~~md\n> [Tilde](../agents/missing.md)\n> ~~~\n\n"
                "> ```md\n> [Backtick](../agents/missing.md)\n> ```\n\n"
                "- ~~~md\n  [List](../agents/missing.md)\n  ~~~\n\n"
                '<span title="> [ID]">x</span>\n\n'
                "[ID]: ../agents/a.md\n",
            ),
            ("plugins/ca-codex/agents/a.md", "# Agent\n"),
        ])
        self.assertEqual(
            self.checker.candidate_resource_contract(literal)["relative_reads"], []
        )

        malformed_html = self.write_zip([
            (
                "plugins/ca-codex/skills/probe.md",
                "<span [Real](../agents/a.md)>\n",
            ),
            ("plugins/ca-codex/agents/a.md", "# Agent\n"),
        ])
        self.assertEqual(
            self.checker.candidate_resource_contract(malformed_html)["relative_reads"],
            [{
                "source_path": "skills/probe.md",
                "reference": "../agents/a.md",
                "resolved_path": "agents/a.md",
            }],
        )

        missing_attribute_space = self.write_zip([
            (
                "plugins/ca-codex/skills/probe.md",
                '<span title="[Real](../agents/a.md)"foo=bar>\n',
            ),
            ("plugins/ca-codex/agents/a.md", "# Agent\n"),
        ])
        self.assertEqual(
            self.checker.candidate_resource_contract(missing_attribute_space)["relative_reads"],
            [{
                "source_path": "skills/probe.md",
                "reference": "../agents/a.md",
                "resolved_path": "agents/a.md",
            }],
        )

        angle = self.write_zip([
            (
                "plugins/ca-codex/skills/probe.md",
                "[ID]\n\n[ID]: <../agents/a(b.md>\n",
            ),
            ("plugins/ca-codex/agents/a(b.md", "# Agent\n"),
        ])
        self.assertEqual(
            self.checker.candidate_resource_contract(angle)["relative_reads"],
            [{
                "source_path": "skills/probe.md",
                "reference": "../agents/a(b.md",
                "resolved_path": "agents/a(b.md",
            }],
        )

    @unittest.skipUnless(hasattr(os, "mkfifo"), "FIFO creation is unavailable")
    def test_rejects_nonregular_directory_candidate_node(self):
        package = Path(self.temporary.name) / "nonregular"
        (package / "skills").mkdir(parents=True)
        (package / "skills" / "probe.md").write_text("# Probe\n", encoding="utf-8")
        os.mkfifo(package / "unexpected-pipe")
        with self.assertRaises(ValueError):
            self.checker.candidate_resource_contract(package)


class AuthenticatedCodexHomeValidationTest(CheckerPresentMixin, unittest.TestCase):
    """Only disposable, controller-owned homes may cross the authentication boundary."""

    def validate(self, value, surface="cli", version="0.143.0", advisory=False):
        validator = getattr(self.checker, "validated_authenticated_codex_home", None)
        self.assertIsNotNone(validator, "authenticated-home validator is missing")
        return validator(
            value, REPO_ROOT, surface=surface, version=version, advisory=advisory
        )

    def test_accepts_existing_absolute_directory_below_os_temp(self):
        """Rejecting a fresh temp home would make the approved OAuth path unusable."""
        with tempfile.TemporaryDirectory() as temporary:
            home = (
                Path(temporary)
                / "codearbiter-stage1-oauth"
                / "cli-0143-auth-20260822T1928Z"
            )
            home.mkdir(parents=True)
            with mock.patch.object(
                self.checker.tempfile, "gettempdir", return_value=temporary
            ):
                self.assertEqual(self.validate(str(home)), home.resolve())

    def test_rejects_unbounded_or_wrong_cell_authenticated_home(self):
        """A live receipt cannot emit an unreviewed auth-root value before durable import."""
        opaque = "AbCdEfGhIjKlMnOpQrStUvWxYz0123456789AaBbCcDdEeFf"
        with tempfile.TemporaryDirectory() as temporary, mock.patch.object(
            self.checker.tempfile, "gettempdir", return_value=temporary
        ):
            root = Path(temporary) / "codearbiter-stage1-oauth"
            cases = (
                root / f"cli-0143-auth-{opaque}",
                root / "app-server-0143-auth-20260822T1928Z",
                Path(temporary) / "arbitrary-parent" / "cli-0143-auth-20260822T1928Z",
            )
            for home in cases:
                home.mkdir(parents=True)
                with self.subTest(home=home), self.assertRaises(ValueError):
                    self.validate(str(home))

    def test_rejects_authenticated_home_for_another_requested_version(self):
        """An authenticated root for one pinned release cannot be reused by another."""
        with tempfile.TemporaryDirectory() as temporary, mock.patch.object(
            self.checker.tempfile, "gettempdir", return_value=temporary
        ):
            home = (
                Path(temporary)
                / "codearbiter-stage1-oauth"
                / "cli-0145-auth-20260822T1928Z"
            )
            home.mkdir(parents=True)
            with self.assertRaises(ValueError):
                self.validate(str(home), version="0.143.0")

    def test_rejects_required_cell_home_for_advisory_probe(self):
        """An advisory probe cannot reuse a required-cell authenticated root."""
        with tempfile.TemporaryDirectory() as temporary, mock.patch.object(
            self.checker.tempfile, "gettempdir", return_value=temporary
        ):
            home = (
                Path(temporary)
                / "codearbiter-stage1-oauth"
                / "cli-0143-auth-20260822T1928Z"
            )
            home.mkdir(parents=True)
            with self.assertRaises(ValueError):
                self.validate(str(home), advisory=True)

    def test_accepts_exact_advisory_authenticated_home(self):
        """The approved advisory cell retains its usable bounded auth-root path."""
        with tempfile.TemporaryDirectory() as temporary, mock.patch.object(
            self.checker.tempfile, "gettempdir", return_value=temporary
        ):
            home = (
                Path(temporary)
                / "codearbiter-stage1-oauth"
                / "advisory-0149-auth-20260822T1928Z"
            )
            home.mkdir(parents=True)
            self.assertEqual(
                self.validate(str(home), version="0.149.0", advisory=True),
                home.resolve(),
            )

    def test_rejects_relative_missing_repository_and_non_temp_directories(self):
        """A loose path check could expose project files or persistent user state."""
        with tempfile.TemporaryDirectory() as temporary:
            missing = Path(temporary) / "missing"
            cases = (
                "relative-codex-home",
                str(missing),
                str(REPO_ROOT),
                str(Path.home()),
                tempfile.gettempdir(),
            )
            for value in cases:
                with self.subTest(value=value), self.assertRaises(ValueError):
                    self.validate(value)


class EnvironmentIsolationTest(CheckerPresentMixin, unittest.TestCase):
    """Live probes do not inherit a repository user's profile or credentials."""

    def test_isolated_environment_rehomes_profile_and_strips_credentials(self):
        """Inheriting HOME or an API key would reuse live user state in a proof cell."""
        with tempfile.TemporaryDirectory() as temporary, mock.patch.dict(
            os.environ,
            {
                "HOME": "C:/live-profile",
                "USERPROFILE": "C:/live-profile",
                "OPENAI_API_KEY": "must-not-pass",
                "WORKSPACE_TOKEN": "must-not-pass",
            },
        ):
            codex_home = Path(temporary) / "codex-home"
            codex_home.mkdir()
            environment = self.checker._isolated_environment(codex_home)
        self.assertNotIn("OPENAI_API_KEY", environment)
        self.assertNotIn("WORKSPACE_TOKEN", environment)
        self.assertEqual(Path(environment["HOME"]).parent, Path(temporary))
        self.assertEqual(environment["HOME"], environment["USERPROFILE"])
        self.assertEqual(environment["CODEX_HOME"], str(codex_home.resolve()))

    def test_explicit_credential_like_extra_environment_is_rejected(self):
        """A test override must not become a backdoor for passing durable credentials."""
        with tempfile.TemporaryDirectory() as temporary:
            codex_home = Path(temporary) / "codex-home"
            codex_home.mkdir()
            with self.assertRaisesRegex(ValueError, "credential-like"):
                self.checker._isolated_environment(
                    codex_home, {"CA_TEST_API_KEY": "not-allowed"}
                )

    def test_reported_version_requires_an_exact_codex_cli_line(self):
        """A substring match must not let 10.143.0 satisfy the 0.143.0 cell."""
        self.assertEqual(
            self.checker.reported_codex_version("codex-cli 0.143.0\n"), "0.143.0"
        )
        self.assertNotEqual(
            self.checker.reported_codex_version("codex-cli 10.143.0\n"), "0.143.0"
        )


if __name__ == "__main__":
    unittest.main()
