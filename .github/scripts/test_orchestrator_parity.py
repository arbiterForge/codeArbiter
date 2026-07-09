#!/usr/bin/env python3
"""Unit tests for check_orchestrator_parity — the ORCHESTRATOR.md drift guard.

Run: python .github/scripts/test_orchestrator_parity.py

Covers the pure comparison helpers against literal strings (so drift detection
is provable without mutating real files) AND the live repo (the guard must
pass on HEAD: plugins/ca/ORCHESTRATOR.md and plugins/ca-codex/ORCHESTRATOR.md
are byte-identical today).
"""
import unittest
from pathlib import Path

import check_orchestrator_parity as G

REPO_ROOT = Path(__file__).resolve().parents[2]


class DiffersTest(unittest.TestCase):
    def test_identical_texts(self):
        self.assertFalse(G.differs("same\ntext\n", "same\ntext\n"))

    def test_diverged_texts(self):
        self.assertTrue(G.differs("a\nb\n", "a\nc\n"))


class FirstDiffLineTest(unittest.TestCase):
    def test_identical_returns_none(self):
        self.assertIsNone(G.first_diff_line("a\nb\nc\n", "a\nb\nc\n"))

    def test_reports_first_diverging_line(self):
        self.assertEqual(G.first_diff_line("a\nb\nc\n", "a\nX\nc\n"), 2)

    def test_reports_line_past_shorter_text(self):
        self.assertEqual(G.first_diff_line("a\nb\n", "a\nb\nc\n"), 3)


class ReadTextTest(unittest.TestCase):
    def test_missing_file_returns_none(self):
        self.assertIsNone(G.read_text(str(REPO_ROOT / "no-such-file-262.md")))


class RunAllTest(unittest.TestCase):
    def test_missing_surfaces_are_findings_not_exceptions(self):
        findings = G.run_all(str(REPO_ROOT / "no-such-dir-262"))
        self.assertTrue(any("ca" in f and "missing or unreadable" in f for f in findings))
        self.assertTrue(any("ca-codex" in f and "missing or unreadable" in f for f in findings))

    def test_diverged_pair_is_a_finding(self):
        ca_text = G.read_text(str(REPO_ROOT / G.CA_ORCHESTRATOR))
        self.assertIsNotNone(ca_text, "plugins/ca/ORCHESTRATOR.md must exist for this test")
        self.assertTrue(G.differs(ca_text, ca_text + "\nDRIFTED\n"))

    def test_live_repo_is_currently_in_parity(self):
        # The guard's own contract: on HEAD, the two files are byte-identical.
        findings = G.run_all(str(REPO_ROOT))
        self.assertEqual(findings, [])


if __name__ == "__main__":
    unittest.main()
