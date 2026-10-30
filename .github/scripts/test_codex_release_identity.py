#!/usr/bin/env python3
"""Codex distribution identity must be checked before privileged writes."""

from pathlib import Path
import contextlib
import importlib.util
import io
import os
import unittest
from unittest import mock

REPO = Path(__file__).resolve().parents[2]
MODULE_PATH = REPO / ".github/scripts/validate_codex_distribution_identity.py"
SPEC = importlib.util.spec_from_file_location("validate_codex_distribution_identity", MODULE_PATH)
IDENTITY = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(IDENTITY)


class CodexReleaseIdentityTest(unittest.TestCase):
    def test_release_contract_commands_fail_independently_on_windows(self):
        workflow = (REPO / ".github/workflows/ci.yml").read_text(encoding="utf-8")
        release_step = workflow.split("- name: Run hosted release-workflow contract tests", 1)[1]
        release_step = release_step.split("\n      - name:", 1)[0]
        identity_step = workflow.split("- name: Run Codex release identity contract tests", 1)[1]
        identity_step = identity_step.split("\n      - name:", 1)[0]
        self.assertIn("run: python .github/scripts/test_release_workflow.py", release_step)
        self.assertNotIn("test_codex_release_identity.py", release_step)
        self.assertIn("run: python .github/scripts/test_codex_release_identity.py", identity_step)

    def test_validator_comes_from_workflow_revision_not_release_source(self):
        workflow = (REPO / ".github/workflows/release.yml").read_text(encoding="utf-8")
        codex = workflow.split("\n  release-codex:\n", 1)[1].split("\n  release-", 1)[0]
        checkout = codex.split("- name: Checkout release-workflow validator", 1)[1]
        checkout = checkout.split("\n      - name:", 1)[0]
        self.assertIn("ref: ${{ github.workflow_sha }}", checkout)
        self.assertIn("path: .release-workflow", checkout)
        self.assertIn("sparse-checkout-cone-mode: false", checkout)
        self.assertIn("persist-credentials: false", checkout)
        validator = codex.split("- name: Validate Codex distribution identities", 1)[1]
        validator = validator.split("\n      - name:", 1)[0]
        self.assertIn("python3 .release-workflow/.github/scripts/validate_codex_distribution_identity.py", validator)

    def test_required_pair_preflight_precedes_publisher_token(self):
        workflow = (REPO / ".github/workflows/release.yml").read_text(encoding="utf-8")
        codex = workflow.split("\n  release-codex:\n", 1)[1].split("\n  release-", 1)[0]
        preflight = codex.index("- name: Validate Codex distribution identities")
        publisher = codex.index("- name: Mint Codex distribution publisher token")
        self.assertLess(preflight, publisher)
        step = codex[preflight:publisher]
        self.assertIn("validate_codex_distribution_identity.py", step)
        self.assertNotIn("PRIVATE_KEY", step)

    def test_verifier_token_is_required(self):
        workflow = (REPO / ".github/workflows/release.yml").read_text(encoding="utf-8")
        codex = workflow.split("\n  release-codex:\n", 1)[1].split("\n  release-", 1)[0]
        verifier = codex.split("- name: Mint Codex ruleset verifier token", 1)[1]
        verifier = verifier.split("- name:", 1)[0]
        self.assertNotIn("continue-on-error: true", verifier)

    def test_distinct_positive_ids_and_installations(self):
        valid = {"PUBLISHER_APP_ID": "12345", "PUBLISHER_INSTALLATION_ID": "56789",
                 "VERIFIER_APP_ID": "23456", "VERIFIER_INSTALLATION_ID": "67890"}
        IDENTITY.validate(valid)
        for changed in (
            {"VERIFIER_APP_ID": "12345"},
            {"PUBLISHER_APP_ID": "15368"},
            {"VERIFIER_APP_ID": "15368"},
            {"PUBLISHER_APP_ID": "0"},
            {"VERIFIER_APP_ID": "01"},
            {"PUBLISHER_INSTALLATION_ID": ""},
            {"VERIFIER_INSTALLATION_ID": "-1"},
        ):
            with self.subTest(changed=changed), self.assertRaises(ValueError):
                IDENTITY.validate({**valid, **changed})

    def test_failed_check_does_not_print_supplied_values(self):
        values = {"PUBLISHER_APP_ID": "SECRET-SENTINEL",
                  "PUBLISHER_INSTALLATION_ID": "56789",
                  "VERIFIER_APP_ID": "23456", "VERIFIER_INSTALLATION_ID": "67890"}
        output = io.StringIO()
        with mock.patch.dict(os.environ, values), contextlib.redirect_stderr(output):
            self.assertEqual(IDENTITY.main(), 1)
        self.assertNotIn("SECRET-SENTINEL", output.getvalue())


if __name__ == "__main__":
    unittest.main(verbosity=2)
