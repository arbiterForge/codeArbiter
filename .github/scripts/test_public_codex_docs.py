#!/usr/bin/env python3
"""Public documentation contract for the supported governance hosts."""

import pathlib
import re
import unittest


ROOT = pathlib.Path(__file__).resolve().parents[2]


class PublicCodexDocsTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        """Load the repository README once for the public documentation checks."""
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
        """The README presents one product and all supported host adapters."""
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
        """The README keeps the current Codex install and verification route."""
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
        """The README links the command catalog and pinned support evidence."""
        self.assertIn("plugins/ca-codex/COMMANDS.md", self.readme)
        self.assertIn("getting-started/claude-code-and-codex", self.readme)
        self.assertRegex(self.readme, re.compile(r"Codex CLI\s+0\.144\.1"))

    def test_project_context_assigns_kernel_and_adapter_ownership(self):
        """Project context assigns canonical source and adapter ownership."""
        context = (ROOT / ".codearbiter" / "CONTEXT.md").read_text(encoding="utf-8")
        tech_stack = (ROOT / ".codearbiter" / "tech-stack.md").read_text(encoding="utf-8")

        self.assertIn("canonical governance kernel", context)
        self.assertIn("Claude Code adapter", context)
        self.assertIn("Codex adapter", context)
        self.assertIn("Pi adapter", context)
        self.assertNotIn("— the kernel.", context)
        self.assertNotIn("Beta until live-Codex verification", context)

        for path in (
            "core/pysrc/",
            "core/surface/",
            "plugins/ca/",
            "plugins/ca-codex/",
            "plugins/ca-pi/",
        ):
            with self.subTest(path=path):
                self.assertIn(path, tech_stack)
        self.assertIn("canonical shared source", tech_stack)
        self.assertIn("source candidate", tech_stack)
        self.assertNotIn("Host dispatch loads those resources", tech_stack)

    def test_contributor_and_security_guides_describe_the_multi_host_product(self):
        """Contributor, security, and install prose matches the host topology."""
        contributing = (ROOT / "CONTRIBUTING.md").read_text(encoding="utf-8")
        security = (ROOT / "SECURITY.md").read_text(encoding="utf-8")
        enforcement = (
            ROOT / "site" / "src" / "content" / "docs" / "enforcement.md"
        ).read_text(encoding="utf-8")

        self.assertNotIn("codeArbiter is a Claude Code plugin", contributing)
        self.assertNotIn("**both** plugins", contributing)
        self.assertIn("three governance adapters", contributing)
        self.assertIn("affected adapter's SemVer", contributing)
        self.assertIn("Claude Code can leave", contributing)
        self.assertIn("Codex reports", contributing)
        self.assertIn("Pi blocks", contributing)
        self.assertIn("shipped adapter-payload change", contributing)

        self.assertNotIn("codeArbiter is a Claude Code plugin", security)
        self.assertNotIn("ships from a single plugin", security)
        self.assertIn("host and adapter version", security)
        self.assertIn("Older adapter releases", security)
        self.assertIn("GitHub Releases API", security)
        self.assertIn("Git common directory", security)
        self.assertIn("~/.codearbiter/", security)
        self.assertIn("marketplace release", security)
        self.assertIn("matching npm release", security)
        self.assertNotIn("with no network calls", security)
        for host in ("Claude Code", "Codex", "Pi"):
            with self.subTest(host=host):
                self.assertIn(host, security)

        self.assertIn("All three governance adapters", enforcement)
        self.assertNotIn("Both plugins vendor the same guard core", enforcement)

        for path in (
            "site/src/content/docs/overview.md",
            "site/src/content/docs/getting-started/install.md",
        ):
            with self.subTest(path=path):
                text = (ROOT / path).read_text(encoding="utf-8")
                self.assertIn("one governance product", text)
                self.assertNotIn("codeArbiter ships four sibling plugins", text)
                self.assertNotIn("The same marketplace", text)

        overview = (
            ROOT / "site" / "src" / "content" / "docs" / "overview.md"
        ).read_text(encoding="utf-8")
        install = (
            ROOT / "site" / "src" / "content" / "docs" / "getting-started" / "install.md"
        ).read_text(encoding="utf-8")
        for text in (overview, install):
            self.assertIn("Claude Code marketplace", text)
            self.assertIn("Codex marketplace", text)
            self.assertIn("pinned Git", text)

        for path in (
            "site/src/content/docs/getting-started/pi.md",
            "site/src/content/docs/guides/uninstalling.md",
        ):
            with self.subTest(pi_distribution_path=path):
                text = (ROOT / path).read_text(encoding="utf-8")
                self.assertNotIn("Git-only", text)
                self.assertNotIn("no npm release", text)
                self.assertIn("npm is the convenience channel", text)

    def test_contributor_marketplace_example_uses_the_current_repository(self):
        """The local marketplace command resolves after entering the clone."""
        contributing = (ROOT / "CONTRIBUTING.md").read_text(encoding="utf-8")
        self.assertIn("/plugin marketplace add .", contributing)
        self.assertNotIn("/plugin marketplace add ./codeArbiter", contributing)

    def test_pi_uninstall_channels_are_separate_copyable_alternatives(self):
        """Pi uninstall guidance never combines both package channels."""
        uninstall = (
            ROOT / "site" / "src" / "content" / "docs" / "guides" / "uninstalling.md"
        ).read_text(encoding="utf-8")
        self.assertRegex(
            uninstall,
            re.compile(
                r"(?s)```sh\s+pi remove npm:@arbiterforge/ca-pi\s+```"
                r"\s+```sh\s+pi remove git:github\.com/arbiterForge/codeArbiter@"
                r"ca-pi-v<version>\s+```"
            ),
        )

    def test_active_codex_role_docs_name_packaged_resource_charters(self):
        """Active Codex prose names packaged charters without overclaiming release."""
        paths = (
            "docs/architecture.md",
            "docs/parity.md",
            "site/src/content/docs/overview.md",
            "site/src/content/docs/concepts/persona-and-context.md",
            "site/src/content/docs/glossary.md",
            "site/src/content/docs/getting-started/claude-code-and-codex.md",
            "site/src/curated/commands/checkpoint.md",
            "site/src/curated/commands/pr.md",
            "site/src/curated/commands/review.md",
            "site/src/curated/commands/tribunal.md",
        )
        for path in paths:
            with self.subTest(path=path):
                text = (ROOT / path).read_text(encoding="utf-8")
                self.assertRegex(text, re.compile(r"(?is)packaged.{0,80}resource charter"))
                self.assertNotIn("does not vendor custom agent definitions", text)

        charter_files = sorted(
            path.name
            for path in (ROOT / "plugins" / "ca-codex" / "agents").glob("*.md")
            if path.name != "INDEX.md"
        )
        self.assertEqual(19, len(charter_files))

        parity = (ROOT / "docs" / "parity.md").read_text(encoding="utf-8")
        self.assertRegex(
            parity,
            re.compile(r"(?m)^\| Codex packaged agents \| DEGRADED \|"),
        )
        self.assertIn("plugins/ca-codex/agents/", parity)
        self.assertNotIn("plugins/ca-codex/resources/agents/", parity)
        self.assertIn("source candidate", parity)

        public_role_docs = (
            "site/src/content/docs/overview.md",
            "site/src/content/docs/concepts/persona-and-context.md",
            "site/src/content/docs/glossary.md",
            "site/src/content/docs/getting-started/claude-code-and-codex.md",
            "site/src/curated/commands/checkpoint.md",
            "site/src/curated/commands/pr.md",
            "site/src/curated/commands/review.md",
            "site/src/curated/commands/tribunal.md",
        )
        for path in public_role_docs:
            with self.subTest(candidate_path=path):
                text = (ROOT / path).read_text(encoding="utf-8")
                self.assertRegex(text, re.compile(r"(?is)source candidate.{0,160}packaged.{0,80}resource charter"))
                self.assertNotIn("Current Codex releases load", text)
                self.assertNotIn("On current Codex hosts", text)


if __name__ == "__main__":
    unittest.main()
