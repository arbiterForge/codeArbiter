#!/usr/bin/env python3
"""Public documentation contract for the supported governance hosts."""

import pathlib
import re
import unittest


ROOT = pathlib.Path(__file__).resolve().parents[2]


class PublicCodexDocsTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.readme = (ROOT / "README.md").read_text(encoding="utf-8")

    def test_the_codex_support_claim_separates_continuous_from_manual(self):
        """Issue #408 AC-2, closed by SCOPING the claim rather than satisfying it.

        Proving a hook FIRES needs a turn, a turn needs a model, and a provider
        credential cannot be a required check on fork PRs. So that half is manual
        — which is a legitimate answer, but only while the manifest says so. A
        claim that reads as continuous while resting on one manual afternoon is
        the defect #408 was filed about, and it is invisible once written.

        Pinned here so the distinction cannot quietly erode back into an
        unqualified promise.
        """
        import json
        manifest = json.loads(
            (ROOT / "plugins" / "ca-codex" / ".codex-plugin" / "plugin.json")
            .read_text(encoding="utf-8"))
        description = manifest["description"]

        # It must name the manual half explicitly, and point at the record.
        self.assertRegex(
            description, r"(?i)by hand|manual",
            "the ca-codex description does not disclose that live hook firing is "
            "verified manually - #408 AC-2 was closed on that disclosure")
        self.assertIn(
            "docs/codex-parity-testing.md", description,
            "the description claims manual verification but does not name the runbook "
            "that records it")

        # ...and the runbook must actually carry a baseline to be the record.
        runbook = (ROOT / "docs" / "codex-parity-testing.md").read_text(encoding="utf-8")
        self.assertIn(
            "<!-- CODEX-LIVE-BASELINE -->", runbook,
            "the runbook has no machine-findable baseline marker, so 'verified per "
            "release' has nothing to point at")
        baseline = runbook.split("<!-- CODEX-LIVE-BASELINE -->", 1)[1]
        self.assertRegex(
            baseline[:400], r"Codex CLI \d+\.\d+\.\d+",
            "the recorded baseline names no Codex version")
        self.assertRegex(
            baseline[:400], r"ca-codex[^0-9]{0,12}\d+\.\d+\.\d+",
            "the recorded baseline names no ca-codex version, so staleness cannot be judged")

    def test_readme_announces_all_hosts_and_shared_parity(self):
        self.assertIn(
            "Shared enforcement and project-context parity across Claude Code, Codex CLI, and Pi",
            self.readme,
        )
        opening = self.readme.split("## See it catch something", 1)[0]
        self.assertNotIn("codeArbiter is a native Claude Code plugin", opening)
        self.assertIn("ca-codex", opening)
        self.assertIn("ca-pi", opening)
        self.assertIn(".codearbiter/", opening)

    def test_readme_contains_codex_install_and_verification_path(self):
        for text in (
            "codex plugin marketplace add arbiterForge/codeArbiter",
            "codex plugin add ca-codex@codearbiter",
            "$ca-init",
            "$ca-doctor",
            "/hooks",
            "available now",
            "v2.8.13",
            "ca-codex 0.2.4",
        ):
            self.assertIn(text, self.readme)
        self.assertNotIn("available after the Codex-support release", self.readme)

    def test_readme_links_catalog_and_evidence(self):
        self.assertIn("plugins/ca-codex/COMMANDS.md", self.readme)
        self.assertIn("getting-started/claude-code-and-codex", self.readme)
        self.assertRegex(self.readme, re.compile(r"Codex CLI\s+0\.144\.1"))


if __name__ == "__main__":
    unittest.main()
