"""Integration tests for the H-13 anti-slop reminder in post-write-edit.py.

Drives the actual hook file over stdin in a git-initialized, arbiter-enabled
temp repo, proving the scope gate (community docs in, framework bodies out) that
is the #60 fix.
"""
import json
import os
import subprocess
import sys
import tempfile
import unittest

HOOK = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "post-write-edit.py")
EM = "—"


class TestH13SlopReminder(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.root = self._tmp.name
        subprocess.run(["git", "init", "-q"], cwd=self.root, check=True)
        os.makedirs(os.path.join(self.root, ".codearbiter"))
        with open(os.path.join(self.root, ".codearbiter", "CONTEXT.md"),
                  "w", encoding="utf-8") as f:
            f.write("---\narbiter: enabled\n---\n# ctx\n")

    def tearDown(self):
        self._tmp.cleanup()

    def _stderr(self, rel_path, content):
        abspath = os.path.join(self.root, rel_path.replace("/", os.sep))
        os.makedirs(os.path.dirname(abspath), exist_ok=True)
        payload = {"hook_event_name": "PostToolUse", "cwd": self.root,
                   "tool_name": "Write",
                   "tool_input": {"file_path": abspath, "content": content}}
        proc = subprocess.run([sys.executable, HOOK], input=json.dumps(payload),
                              capture_output=True, text=True, cwd=self.root,
                              encoding="utf-8")
        return proc.stderr

    def test_reminds_on_user_facing_doc_with_separator_dash(self):
        err = self._stderr("README.md", f"The gate blocks {EM} the human resolves.\n")
        self.assertIn("H-13", err)

    def test_silent_on_clean_user_facing_doc(self):
        err = self._stderr("README.md", "Plain prose. No separator dashes here.\n")
        self.assertNotIn("H-13", err)

    def test_silent_on_framework_body_even_with_dash(self):
        # A command body under plugins/ is out of anti-slop scope by design.
        err = self._stderr("plugins/ca/commands/chore.md",
                           f"Routing {EM} the orchestrator decides.\n")
        self.assertNotIn("H-13", err)


if __name__ == "__main__":
    unittest.main()
