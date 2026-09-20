#!/usr/bin/env python3

import importlib.util
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


SCRIPT = Path(__file__).with_name("check_auto_release_candidate.py")
SPEC = importlib.util.spec_from_file_location("candidate_check", SCRIPT)
assert SPEC and SPEC.loader
candidate_check = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = candidate_check
SPEC.loader.exec_module(candidate_check)


class CandidateCheckTest(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.repo = Path(self.temp.name)
        self.git("init", "-b", "main")
        self.git("config", "user.name", "Test")
        self.git("config", "user.email", "test@example.invalid")
        (self.repo / ".codearbiter").mkdir()
        (self.repo / "plugins/ca/.claude-plugin").mkdir(parents=True)
        (self.repo / ".codearbiter/release-targets.md").write_text(
            "<!-- release-targets -->\n[ca]\nprefix: v\n"
            "manifest: plugins/ca/.claude-plugin/plugin.json\n"
            "changelog: CHANGELOG.md\npayload: plugins/ca/\n"
            "<!-- /release-targets -->\n",
            encoding="utf-8",
        )
        self.write_version("1.0.0")
        (self.repo / "CHANGELOG.md").write_text("# 1.0.0\n", encoding="utf-8")
        self.git("add", ".")
        self.git("commit", "-m", "release candidate")
        self.live = self.git("rev-parse", "HEAD")

    def tearDown(self):
        self.temp.cleanup()

    def git(self, *args):
        return subprocess.check_output(["git", *args], cwd=self.repo, text=True).strip()

    def write_version(self, value):
        (self.repo / "plugins/ca/.claude-plugin/plugin.json").write_text(
            json.dumps({"version": value}), encoding="utf-8"
        )

    def commit(self, message, path="README.md", content="later\n"):
        (self.repo / path).write_text(content, encoding="utf-8")
        self.git("add", ".")
        self.git("commit", "-m", message)
        return self.git("rev-parse", "HEAD")

    def test_exact_candidate_is_authorized(self):
        results = candidate_check.evaluate_candidate(self.repo, self.live, self.live)
        self.assertTrue(results[0].eligible)

    def test_later_payload_commit_cannot_consume_an_older_changelog(self):
        later = self.commit("payload drift", "plugins/ca/new.txt", "changed\n")
        with self.assertRaisesRegex(candidate_check.CandidateError, "not advanced"):
            candidate_check.evaluate_candidate(self.repo, later, self.live)

    def test_unchanged_payload_continuation_is_authorized(self):
        later = self.commit("ci-only correction", ".github-note", "fixed\n")
        results = candidate_check.evaluate_candidate(self.repo, later, self.live)
        self.assertTrue(results[0].eligible)

    def test_a_new_candidate_must_advance_the_changelog(self):
        later = self.commit("new candidate", "CHANGELOG.md", "# 1.0.0\n- fix\n")
        results = candidate_check.evaluate_candidate(self.repo, later, self.live)
        self.assertTrue(results[0].eligible)


if __name__ == "__main__":
    unittest.main()
