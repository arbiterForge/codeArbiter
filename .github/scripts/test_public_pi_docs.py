#!/usr/bin/env python3
"""Structural contract for the public Pi documentation surface.

The checks stay stdlib-only and derive catalog counts from generated payloads so
documentation cannot pass by repeating a stale literal in several files.
"""

from __future__ import annotations

import json
import re
import unittest
from pathlib import Path


REPO = Path(__file__).resolve().parents[2]


def read(relative: str) -> str:
    return (REPO / relative).read_text(encoding="utf-8")


def entry_skill_count(plugin: str) -> int:
    skills = REPO / "plugins" / plugin / "skills"
    return sum((child / "SKILL.md").is_file() for child in skills.iterdir())


class PublicHostVocabularyTest(unittest.TestCase):
    def test_readme_names_three_governance_hosts_and_four_sibling_plugins(self):
        readme = read("README.md")
        for host in ("Claude Code", "Codex CLI", "Pi"):
            self.assertIn(host, readme)
        for plugin in ("ca", "ca-codex", "ca-pi", "ca-sandbox"):
            self.assertRegex(readme, rf"(?<![\w-]){re.escape(plugin)}(?![\w-])")
        self.assertIn("four sibling plugins", readme.lower())
        self.assertIn("three governance hosts", readme.lower())

    def test_canonical_project_docs_use_pi_vocabulary(self):
        for path in (
            ".codearbiter/CONTEXT.md",
            ".codearbiter/tech-stack.md",
            ".codearbiter/coding-standards.md",
            "docs/architecture.md",
            "docs/hooks.md",
        ):
            with self.subTest(path=path):
                text = read(path)
                self.assertIn("ca-pi", text)
                self.assertIn("Pi", text)


class PiInstallRunbookTest(unittest.TestCase):
    def test_missing_python_failure_direction_is_not_documented_as_silent(self):
        text = read("README.md")
        prerequisite = text.split("**Prerequisites:**", 1)[1].split("\n\n", 1)[0].lower()
        self.assertIn("blocks mutating calls", prerequisite)
        self.assertIn("interpreter breadcrumb", prerequisite)
        self.assertNotIn("silently don't run", prerequisite)

    def test_install_is_pinned_git_only_and_names_supported_versions(self):
        text = read("docs/pi-parity-testing.md")
        self.assertIn("pi install git:github.com/arbiterForge/codeArbiter@ca-pi-v", text)
        self.assertIn("Pi 0.80.5", text)
        self.assertIn("Pi 0.80.10", text)
        self.assertIn("Git-only", text)
        self.assertNotIn("npm publish", text)

    def test_runbook_covers_required_live_checks_and_safe_evidence(self):
        text = read("docs/pi-parity-testing.md")
        for item in (
            "isolated home",
            "dummy local provider",
            "package origin",
            "project trust",
            "activation",
            "aliases",
            "final mutation",
            "subagents",
            "cancellation",
            "status",
            "compaction",
            "farm preview",
            "shared-state continuity",
            "uninstall",
            "result codes and timings only",
        ):
            with self.subTest(item=item):
                self.assertIn(item, text.lower())

    def test_module_identity_claim_is_scoped_to_self_consistency(self):
        combined = read("docs/pi-parity-testing.md") + read("docs/parity.md")
        self.assertIn("self-consistency", combined)
        self.assertIn("not publisher authenticity", combined)
        self.assertIn("pi list", combined)
        self.assertIn("pi config", combined)


class PiCatalogAndParityTest(unittest.TestCase):
    def test_public_docs_state_the_complete_pi_live_behavior_contract(self):
        shared = {
            "footer": r"rich footer",
            "governance": r"governance row.{0,180}enabled.{0,180}(?:affirmatively )?trusted",
            "rate-window": r"rate-window telemetry is omitted|rate windows omitted",
            "execute": r"execute mode asks|execute permission asks|governed mutation.{0,100}ask once",
            "plan": r"plan mode is read-only",
            "jobs": r"never restored from pi session entries",
            "cleanup": r"unverified cleanup",
            "parent-only": r"parent-interactive only",
        }
        catalog_and_cold = {
            "catalog": r"plugins/ca-pi/skills\.md",
            "cold-result": r"missing_prerequisite",
            "cold-remediation": r"npm --prefix plugins/ca-pi/tools ci --ignore-scripts",
        }
        expected = {
            "README.md": {**shared, **catalog_and_cold},
            "docs/pi-parity-testing.md": {**shared, **catalog_and_cold},
            "docs/parity.md": {**shared, **catalog_and_cold},
            "site/src/content/docs/getting-started/compatibility.md": {
                **shared,
                **catalog_and_cold,
            },
            "site/src/content/docs/hooks.md": shared,
        }
        contradictions = {
            "legacy-status": r"no statusline;\s*`ctx\.ui\.setstatus`|not a footer replacement",
            "degraded-footer": r"\| pi complete footer \| degraded \|",
            "invented-rate-window": r"rate-window telemetry (?:is )?(?:available|fabricated)",
            "persistent-jobs": r"persistent background jobs|jobs (?:are|can be|may be) restored from pi session entries",
            "writable-plan": r"plan mode (?:allows|permits) (?:source|configuration|external) (?:writes|mutations)",
            "silent-mutation": r"execute mode (?:allows|performs) governed mutations without (?:asking|confirmation)",
        }
        for path, facts in expected.items():
            text = re.sub(r"\s+", " ", read(path).lower())
            for fact, pattern in facts.items():
                with self.subTest(path=path, fact=fact):
                    self.assertRegex(text, pattern)
            for contradiction, pattern in contradictions.items():
                with self.subTest(path=path, contradiction=contradiction):
                    self.assertNotRegex(text, pattern)

    def test_public_catalog_counts_match_generated_payloads(self):
        readme = read("README.md")
        runbook = read("docs/pi-parity-testing.md")
        counts = {
            "ca": len(list((REPO / "plugins/ca/commands").glob("*.md"))),
            "ca-codex": entry_skill_count("ca-codex"),
            "ca-pi": entry_skill_count("ca-pi"),
        }
        for plugin, count in counts.items():
            with self.subTest(plugin=plugin):
                marker = f"{plugin}: {count}"
                self.assertIn(marker, readme)
                self.assertIn(marker, runbook)
        for link in (
            "./plugins/ca/COMMANDS.md",
            "./plugins/ca-codex/COMMANDS.md",
            "./plugins/ca-pi/COMMANDS.md",
        ):
            self.assertIn(link, readme)

    def test_every_pi_exception_has_status_and_evidence(self):
        parity = read("docs/parity.md")
        match = re.search(
            r"<!-- PI-EXCEPTIONS:START -->(.*?)<!-- PI-EXCEPTIONS:END -->",
            parity,
            flags=re.DOTALL,
        )
        self.assertIsNotNone(match, "docs/parity.md lacks the Pi exception ledger")
        rows = [line for line in match.group(1).splitlines() if line.startswith("|")]
        self.assertGreaterEqual(len(rows), 3, "expected header plus at least one exception")
        for row in rows[2:]:
            cells = [cell.strip() for cell in row.strip("|").split("|")]
            self.assertGreaterEqual(len(cells), 4, row)
            self.assertIn(cells[1], {"SUPPORTED", "DEGRADED", "HOST-IMPOSSIBLE", "PREVIEW"})
            self.assertRegex(cells[3], r"`[^`]+`|\[[^]]+\]\([^)]+\)")


class ReleaseShapeTest(unittest.TestCase):
    def test_release_docs_keep_preview_and_future_work_explicit(self):
        combined = "\n".join(
            read(path)
            for path in (
                "README.md",
                "CHANGELOG.md",
                "plugins/ca-pi/CHANGELOG.md",
                "docs/pi-parity-testing.md",
                "docs/parity.md",
            )
        )
        self.assertIn("--farm", combined)
        self.assertRegex(combined, r"(?is)--farm.{0,160}preview")
        self.assertRegex(combined, r"(?is)npm packaging.{0,160}future spike")
        self.assertRegex(combined, r"(?is)embedded farm worker.{0,160}future spike")
        self.assertIn("ca-pi-v*", combined)
        self.assertIn("no npm release", combined.lower())

    def test_pi_manifest_is_private_and_versions_are_synchronized(self):
        nested = json.loads(read("plugins/ca-pi/package.json"))
        root = json.loads(read("package.json"))
        self.assertTrue(nested["private"])
        self.assertTrue(root["private"])
        self.assertEqual(nested["version"], root["version"])

    def test_pi_license_is_covered_by_consistency_checker(self):
        checker = read(".github/scripts/check_license_consistency.py")
        self.assertIn("plugins/ca-pi/package.json", checker)


if __name__ == "__main__":
    unittest.main()
