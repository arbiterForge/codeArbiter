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
