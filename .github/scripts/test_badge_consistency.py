#!/usr/bin/env python3
"""Unit tests for the README badge, core-lane, and catalog guard.

Run: python .github/scripts/test_badge_consistency.py

Covers the pure parsers against literal strings (so drift detection is provable
without mutating real files) AND the live repo (the guard must pass on HEAD).
The guard is the mechanical backstop for the release skill's surface-sync step
(AC-A8/AC-A10): the README version badge, core-lane/skill/agent badges, grouped
core chooser, and complete generated catalog must all match canonical source.
"""
import unittest
from pathlib import Path

import check_badge_consistency as G

REPO_ROOT = Path(__file__).resolve().parents[2]


class ParsersTest(unittest.TestCase):
    def test_version_badge(self):
        self.assertEqual(
            G.parse_version_badge('<img alt="version 2.5.0" '
                                  'src="https://img.shields.io/badge/version-2.5.0-2b7489">'),
            "2.5.0",
        )

    def test_count_badges(self):
        text = (
            '<img alt="core lanes" src="https://img.shields.io/badge/core_lanes-18-555">\n'
            '<img alt="skills" src="https://img.shields.io/badge/skills-20-555">\n'
            '<img alt="agents" src="https://img.shields.io/badge/agents-15-555">\n'
        )
        self.assertEqual(G.parse_count_badges(text), {"core_lanes": 18, "skills": 20, "agents": 15})

    def test_raw_command_count_marketing_is_detected(self):
        text = (
            '<img alt="commands" src="https://img.shields.io/badge/commands-38-555">\n'
            "<summary><b>The full catalog</b>: 38 commands</summary>\n"
            "├── commands/   (38)   skills/   (20)   agents/   (15)\n"
        )
        self.assertEqual(G.parse_raw_command_count_claims(text), ["38", "38", "38"])

    def test_core_lane_slugs_are_scoped_to_the_marked_chooser(self):
        text = (
            "`/ca:debug` appears elsewhere.\n"
            "<!-- core-lane-chooser:start -->\n"
            "| `/ca:feature` | desc |\n| `/ca:task` | desc |\n"
            "<!-- core-lane-chooser:end -->\n"
        )
        self.assertEqual(G.parse_readme_core_slugs(text), {"feature", "task"})

    def test_catalog_slugs_from_table(self):
        text = "| `/ca:feature` | desc |\n| <kbd>/ca:task</kbd> | desc |\n| not a row |\n"
        self.assertEqual(G.parse_ca_slugs(text), {"feature", "task"})


class DriftDetectionTest(unittest.TestCase):
    """The guard must FAIL on each independent kind of drift."""

    def _facts(self):
        # A self-consistent fact set; each test perturbs exactly one field.
        return dict(
            readme_version="2.5.0",
            plugin_version="2.5.0",
            badge_counts={"core_lanes": 1, "skills": 1, "agents": 1},
            raw_command_count_claims=[],
            real_counts={"core_lanes": 1, "skills": 1, "agents": 1},
            catalog_slugs={"feature", "task"},
            cmd_file_slugs={"feature", "task"},
            readme_core_slugs={"feature"},
            registry_core_slugs={"feature"},
        )

    def test_clean_facts_pass(self):
        self.assertEqual(G.consistency_errors(**self._facts()), [])

    def test_version_badge_drift_fails(self):
        f = self._facts(); f["readme_version"] = "2.4.6"
        self.assertTrue(any("version" in e.lower() for e in G.consistency_errors(**f)))

    def test_count_badge_drift_fails(self):
        f = self._facts(); f["badge_counts"]["core_lanes"] = 2
        self.assertTrue(any("core lanes" in e.lower() for e in G.consistency_errors(**f)))

    def test_raw_command_count_marketing_fails(self):
        f = self._facts(); f["raw_command_count_claims"] = ["38"]
        self.assertTrue(any("raw command-count" in e.lower() for e in G.consistency_errors(**f)))

    def test_missing_readme_core_lane_fails(self):
        f = self._facts(); f["readme_core_slugs"] = set()
        self.assertTrue(any("feature" in e for e in G.consistency_errors(**f)))

    def test_catalog_file_mismatch_fails(self):
        f = self._facts(); f["catalog_slugs"] = {"feature"}
        self.assertTrue(G.consistency_errors(**f))


class LiveRepoTest(unittest.TestCase):
    def test_head_is_consistent(self):
        errors = G.check(REPO_ROOT)
        self.assertEqual(errors, [], "badge/count/catalog drift on HEAD:\n" + "\n".join(errors))


if __name__ == "__main__":
    unittest.main(verbosity=2)
