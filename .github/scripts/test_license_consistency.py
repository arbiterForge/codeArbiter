#!/usr/bin/env python3
"""codeArbiter — unit tests for the license-consistency CI check.

Spec: .codearbiter/specs/license-consistency-check.md. Each test class maps to
one or more acceptance criteria:

  ManifestAgreementTest  AC-1, AC-2 — manifest licenses match the canonical; stale prior flagged
  LicenseFileTest        AC-3       — LICENSE text matches the canonical family
  ReadmeBadgeTest        AC-4       — README license badge matches the family
  ReadmeNoticeTest       AC-5       — README notice names the canonical license
  OfferingProseTest      AC-6       — retired commercial-offering phrases are forbidden
  ResolveFamilyTest      AC-7       — unknown canonical SPDX degrades to None (no crash)
  MalformedInputTest     AC-8       — missing file / non-string degrade to a finding, never raise
  LiveRepoTest           AC-9       — the real repo passes (post ca-sandbox fix)
  CiWiringTest           AC-10      — ci.yml runs the check and gates merge

Pure functions over synthetic input; stdlib only. Exit 0 = all pass.
"""

import os
import sys
import tempfile
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(os.path.dirname(HERE))
sys.path.insert(0, HERE)

import check_license_consistency as lic  # noqa: E402 — needs sys.path mutation

CANON = "AGPL-3.0-only"
CA = "plugins/ca/.claude-plugin/plugin.json"
SANDBOX = "plugins/ca-sandbox/.claude-plugin/plugin.json"


class ManifestAgreementTest(unittest.TestCase):
    """AC-1/AC-2: every manifest license equals the canonical; a prior license is a stale finding."""

    def test_all_agree_passes(self):
        self.assertEqual(
            lic.check_manifest_agreement(CANON, {CA: CANON, SANDBOX: CANON}), [])

    def test_prior_license_in_a_manifest_fails_naming_file(self):
        findings = lic.check_manifest_agreement(CANON, {CA: CANON, SANDBOX: "MIT"})
        self.assertTrue(any(SANDBOX in f and "MIT" in f for f in findings))

    def test_prior_license_flagged_as_stale(self):  # AC-2
        findings = lic.check_manifest_agreement(CANON, {CA: "MIT"})
        self.assertTrue(any("prior" in f.lower() for f in findings))

    def test_nonprior_mismatch_fails(self):
        findings = lic.check_manifest_agreement(CANON, {CA: CANON, SANDBOX: "BSD-3-Clause"})
        self.assertTrue(any("does not match" in f for f in findings))


class LicenseFileTest(unittest.TestCase):
    """AC-3: the LICENSE text carries every family-identifying token."""

    def test_agpl_text_passes(self):
        fam = lic.resolve_family(CANON)
        text = "                    GNU AFFERO GENERAL PUBLIC LICENSE\n                       Version 3, 19 November 2007\n"
        self.assertEqual(lic.check_license_file(fam, text), [])

    def test_wrong_license_text_fails(self):
        fam = lic.resolve_family(CANON)
        text = "MIT License\n\nPermission is hereby granted, free of charge, ...\n"
        self.assertTrue(any("AFFERO" in f or "Version 3" in f for f in lic.check_license_file(fam, text)))


class ReadmeBadgeTest(unittest.TestCase):
    """AC-4: the README license badge encodes the family."""

    def test_badge_present_passes(self):
        fam = lic.resolve_family(CANON)
        readme = '<img alt="license AGPL v3" src="https://img.shields.io/badge/license-AGPL_v3-3da639">'
        self.assertEqual(lic.check_readme_badge(fam, readme), [])

    def test_badge_absent_fails(self):
        fam = lic.resolve_family(CANON)
        readme = '<img alt="license MIT" src="https://img.shields.io/badge/license-MIT-555">'
        self.assertTrue(any("badge" in f.lower() for f in lic.check_readme_badge(fam, readme)))


class ReadmeNoticeTest(unittest.TestCase):
    """AC-5: the README notice names the canonical license, not only a prior one."""

    def test_notice_names_license_passes(self):
        fam = lic.resolve_family(CANON)
        readme = "codeArbiter is licensed under the GNU AGPLv3, a change from its earlier MIT license."
        self.assertEqual(lic.check_readme_notice(fam, readme), [])

    def test_notice_stale_fails(self):
        fam = lic.resolve_family(CANON)
        readme = "codeArbiter is licensed under the MIT license."
        self.assertTrue(lic.check_readme_notice(fam, readme))


class OfferingProseTest(unittest.TestCase):
    """AC-6: retired commercial-offering phrases are forbidden in the README."""

    def test_clean_prose_passes(self):
        readme = ("Copyright (C) 2026 SUaDtL, who reserves the right to dual-license under "
                  "separate proprietary terms; commercial licenses are not offered at this time.")
        self.assertEqual(lic.check_offering_prose(readme), [])

    def test_available_separately_fails(self):
        readme = "Proprietary and commercial licensing is available separately; see Dual-Licensing."
        self.assertTrue(any("available separately" in f for f in lic.check_offering_prose(readme)))

    def test_offers_the_same_code_fails(self):
        readme = "The holder retains ownership and offers the same code under separate proprietary terms."
        self.assertTrue(any("offers the same code" in f for f in lic.check_offering_prose(readme)))

    def test_non_string_degrades_to_no_finding(self):  # never raises
        self.assertEqual(lic.check_offering_prose(None), [])


class ResolveFamilyTest(unittest.TestCase):
    """AC-7: known SPDX resolves to a family dict; unknown degrades to None (no crash)."""

    def test_known_spdx_resolves(self):
        self.assertIsNotNone(lic.resolve_family("AGPL-3.0-only"))

    def test_unknown_spdx_returns_none(self):
        self.assertIsNone(lic.resolve_family("BSD-3-Clause"))


class MalformedInputTest(unittest.TestCase):
    """AC-8 (+ AC-7 via the aggregator): degrade to a finding, never raise."""

    def test_read_manifest_license_missing_file_returns_none(self):
        self.assertIsNone(lic.read_manifest_license("/no/such/dir/plugin.json"))

    def test_read_manifest_license_bad_json_returns_none(self):
        with tempfile.NamedTemporaryFile("w", suffix=".json", delete=False) as f:
            f.write("{ not json ")
            path = f.name
        try:
            self.assertIsNone(lic.read_manifest_license(path))
        finally:
            os.unlink(path)

    def test_evaluate_unknown_canonical_reports_not_raises(self):  # AC-7
        findings = lic.evaluate("BSD-3-Clause", {CA: "BSD-3-Clause"}, "", "")
        self.assertTrue(any("family" in f.lower() for f in findings))

    def test_run_all_missing_files_reports_not_raises(self):  # AC-8
        with tempfile.TemporaryDirectory() as d:
            findings = lic.run_all(d)
        self.assertTrue(findings)  # missing surfaces => findings, not an exception


class LiveRepoTest(unittest.TestCase):
    """AC-9: the real repository is consistent (after the ca-sandbox manifest fix)."""

    def test_repo_is_consistent(self):
        findings = lic.run_all(REPO)
        self.assertEqual(findings, [], "live repo license drift: " + "; ".join(findings))


class CiWiringTest(unittest.TestCase):
    """AC-10: ci.yml runs the check and includes it in the required-checks aggregation."""

    @classmethod
    def setUpClass(cls):
        with open(os.path.join(REPO, ".github", "workflows", "ci.yml"), encoding="utf-8") as fh:
            cls.ci = fh.read()

    def test_ci_invokes_the_check(self):
        self.assertIn("check_license_consistency.py", self.ci)

    def test_ci_job_is_in_required_aggregation(self):
        self.assertIn("license-consistency", self.ci)


if __name__ == "__main__":
    unittest.main()
