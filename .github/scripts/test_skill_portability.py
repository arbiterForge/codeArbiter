#!/usr/bin/env python3
"""Unit tests for check_skill_portability (A-6.1, T-68a/b).

Run: python .github/scripts/test_skill_portability.py
"""
import os
import sys
import tempfile
import unittest
from pathlib import Path

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[1]
sys.path.insert(0, str(HERE))

import check_skill_portability as G  # noqa: E402


class MatchingRuleTest(unittest.TestCase):
    """A-6.1 requires the guard to STATE its matching rule in its own
    docstring, and the rule to distinguish executes-or-reads from
    mentions. Both are asserted, because a rule stated only in a commit
    message is a rule the next reader cannot check the code against."""

    def test_matching_rule_is_stated_in_the_docstring(self):
        doc = G.__doc__ or ""
        self.assertIn("FLAGGED", doc)
        self.assertIn("PERMITTED", doc)
        self.assertIn("EXECUTES-OR-READS", doc)
        for prefix in ("${CLAUDE_PLUGIN_ROOT}", "${CLAUDE_PROJECT_DIR}"):
            self.assertIn(prefix, doc, f"{prefix} not named as permitted")

    def test_matching_rule_flags_a_bare_repo_path(self):
        hits = G.scan_file("x.md", "Run `.github/scripts/thing.py` before tagging.\n")
        self.assertEqual([h[1] for h in hits], [".github/scripts/thing.py"])

    def test_matching_rule_permits_a_resolved_prefix(self):
        for line in (
            "Run `${CLAUDE_PLUGIN_ROOT}/hooks/thing.py` before tagging.\n",
            "Run `{{PLUGIN_ROOT}}/hooks/thing.py` before tagging.\n",
            "Read `${CLAUDE_PROJECT_DIR}/.codearbiter/CONTEXT.md` first.\n",
            "Run `python3 ${CLAUDE_PLUGIN_ROOT}/hooks/thing.py arg` now.\n",
        ):
            with self.subTest(line=line.strip()):
                self.assertEqual(G.scan_file("x.md", line), [])

    def test_matching_rule_permits_a_scan_target_pattern(self):
        # A scout describing WHERE TO SEARCH in the consumer's repo is not
        # naming a file to run. Flagging it would forbid every scan list.
        line = "Scan `src/`, `lib/`, and `tools/build.js` for entry points.\n"
        self.assertEqual(G.scan_file("x.md", line), [])

    def test_matching_rule_permits_a_conditional_ci_reference(self):
        # A skill may truthfully say this repo's CI enforces something
        # without instructing a consumer to run it.
        line = ("`.github/scripts/check_adr_identity.py` enforces this "
                "in CI; if it disagrees, the report is wrong.\n")
        self.assertEqual(G.scan_file("x.md", line), [])

    def test_matching_rule_flags_a_readable_markdown_artifact(self):
        # CodeRabbit MAJOR, confirmed. The stated rule is EXECUTES-OR-READS,
        # but `.md` was absent from the suffix list, so a skill telling a
        # consumer to READ one of this repo's own docs passed — the guard's
        # documented rule was wider than its behaviour.
        hits = G.scan_file(
            "x.md", "Read `core/surface/skills/release/SKILL.md` for the contract.\n")
        self.assertEqual([h[1] for h in hits],
                         ["core/surface/skills/release/SKILL.md"])

    def test_matching_rule_sees_through_a_dot_slash_prefix(self):
        # CodeRabbit MAJOR, confirmed. The repo-root test is a literal
        # prefix match, so `./tools/farm.js` — the same instruction — slipped
        # past on two characters.
        for line, want in (
            ("Run `./tools/farm.js` to dispatch.", "tools/farm.js"),
            ("Run `././.github/scripts/thing.py` now.", ".github/scripts/thing.py"),
        ):
            with self.subTest(line=line):
                self.assertEqual([h[1] for h in G.scan_file("x.md", line + "\n")],
                                 [want])

    def test_matching_rule_ignores_a_directory_without_an_artifact_suffix(self):
        # `plugins/ca/` is a location, not something to execute.
        self.assertEqual(G.scan_file("x.md", "Payload lives under `plugins/ca/`.\n"), [])

    def test_matching_rule_ignores_a_non_repo_root(self):
        # A consumer's own paths are theirs, not this repo's.
        self.assertEqual(G.scan_file("x.md", "Edit `src/index.js` next.\n"), [])

    def test_matching_rule_ignores_prose_outside_backticks(self):
        # Only code spans are instructions; prose naming a path in passing
        # is a mention.
        self.assertEqual(
            G.scan_file("x.md", "The tools/farm.js dispatcher lives here.\n"), [])


class LiveRepoTest(unittest.TestCase):
    """The guard against the real shipped skills, both directions."""

    def test_the_shipped_skills_are_clean(self):
        findings = G.scan()
        self.assertEqual(
            findings, {},
            "a shipped skill names a this-repo path a consumer will not "
            f"have: {findings}")

    def test_the_guard_can_still_fail(self):
        # A guard that only ever passes proves nothing. Exercised against a
        # synthetic tree rather than by mutating a real skill, so the check
        # cannot leave the repo dirty.
        with tempfile.TemporaryDirectory() as tmp:
            skills = Path(tmp) / "skills" / "example"
            skills.mkdir(parents=True)
            (skills / "SKILL.md").write_text(
                "Dispatch `tools/farm.js` to start the run.\n", encoding="utf-8")
            findings = G.scan(root=Path(tmp) / "skills")
        self.assertTrue(findings, "the guard failed to flag a bare repo path")

    def test_main_exits_0_on_the_live_repo(self):
        self.assertEqual(G.main(), 0)


if __name__ == "__main__":
    unittest.main(verbosity=2)
