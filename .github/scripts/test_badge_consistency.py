#!/usr/bin/env python3
"""Unit tests for check_badge_consistency — the README badge/count/catalog guard.

Run: python .github/scripts/test_badge_consistency.py

Covers the pure parsers against literal strings (so drift detection is provable
without mutating real files) AND the live repo (the guard must pass on HEAD).
The guard is the mechanical backstop for the release skill's surface-sync step
(AC-A8/AC-A10): the README version badge, the command/skill/agent count badges,
their prose echoes, and the README full-catalog table must all match the repo.
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
            '<img alt="commands" src="https://img.shields.io/badge/commands-37-555">\n'
            '<img alt="skills" src="https://img.shields.io/badge/skills-20-555">\n'
            '<img alt="agents" src="https://img.shields.io/badge/agents-15-555">\n'
        )
        self.assertEqual(G.parse_count_badges(text), {"commands": 37, "skills": 20, "agents": 15})

    def test_prose_counts(self):
        text = "<summary><b>The full catalog</b>: 37 commands</summary>\n├── commands/   (37)   skills/   (20)   agents/   (15)\n"
        self.assertEqual(sorted(G.parse_prose_command_counts(text)), [37, 37])

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
            badge_counts={"commands": 2, "skills": 1, "agents": 1},
            prose_counts=[2],
            real_counts={"commands": 2, "skills": 1, "agents": 1},
            catalog_slugs={"feature", "task"},
            cmd_file_slugs={"feature", "task"},
            readme_table_slugs={"feature", "task"},
        )

    def test_clean_facts_pass(self):
        self.assertEqual(G.consistency_errors(**self._facts()), [])

    def test_version_badge_drift_fails(self):
        f = self._facts(); f["readme_version"] = "2.4.6"
        self.assertTrue(any("version" in e.lower() for e in G.consistency_errors(**f)))

    def test_count_badge_drift_fails(self):
        f = self._facts(); f["badge_counts"]["commands"] = 1
        self.assertTrue(any("command" in e.lower() for e in G.consistency_errors(**f)))

    def test_prose_count_drift_fails(self):
        f = self._facts(); f["prose_counts"] = [1]
        self.assertTrue(G.consistency_errors(**f))

    def test_missing_catalog_row_fails(self):
        # A command file with no README-table row — the exact /ca:task bug.
        f = self._facts(); f["readme_table_slugs"] = {"feature"}
        self.assertTrue(any("task" in e for e in G.consistency_errors(**f)))

    def test_catalog_file_mismatch_fails(self):
        f = self._facts(); f["catalog_slugs"] = {"feature"}
        self.assertTrue(G.consistency_errors(**f))


class LiveRepoTest(unittest.TestCase):
    def test_head_is_consistent(self):
        errors = G.check(REPO_ROOT)
        self.assertEqual(errors, [], "badge/count/catalog drift on HEAD:\n" + "\n".join(errors))


if __name__ == "__main__":
    unittest.main(verbosity=2)
