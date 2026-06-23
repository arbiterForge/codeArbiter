"""Integration tests for the H-15/H-16/H-17 advisory scope-touch reminders in
post-write-edit.py (#73).

Drives the real hook over stdin in a git-initialized, arbiter-enabled temp repo.
All three are advisory: they emit a REMINDER to stderr and never block (exit 0).
"""
import json
import os
import subprocess
import sys
import tempfile
import unittest

HOOK = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "post-write-edit.py")


class TestScopeReminders(unittest.TestCase):
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

    def _run(self, rel_path, content):
        abspath = os.path.join(self.root, rel_path.replace("/", os.sep))
        os.makedirs(os.path.dirname(abspath), exist_ok=True)
        payload = {"hook_event_name": "PostToolUse", "cwd": self.root,
                   "tool_name": "Write",
                   "tool_input": {"file_path": abspath, "content": content}}
        return subprocess.run([sys.executable, HOOK], input=json.dumps(payload),
                              capture_output=True, text=True, cwd=self.root,
                              encoding="utf-8")

    def test_ci_file_reminds_h15_nonblocking(self):
        proc = self._run(".github/workflows/ci.yml", "name: ci\non: push\n")
        self.assertIn("H-15", proc.stderr)
        self.assertEqual(proc.returncode, 0)

    def test_deploy_file_reminds_h16_nonblocking(self):
        proc = self._run("infra/main.tf", 'resource "aws_s3_bucket" "b" {}\n')
        self.assertIn("H-16", proc.stderr)
        self.assertEqual(proc.returncode, 0)

    def test_auth_pattern_reminds_h17_nonblocking(self):
        proc = self._run("src/auth.ts", "import jwt from 'x';\njwt.verify(t, k);\n")
        self.assertIn("H-17", proc.stderr)
        self.assertEqual(proc.returncode, 0)

    def test_clean_source_file_silent(self):
        proc = self._run("src/util.ts", "export const add = (a, b) => a + b;\n")
        for tag in ("H-15", "H-16", "H-17"):
            self.assertNotIn(tag, proc.stderr)
        self.assertEqual(proc.returncode, 0)

    def test_path_reminder_survives_divergent_root_form(self):
        """Regression (#125 CI): file_path and `git rev-parse --show-toplevel`
        can name the same repo via divergent-but-equivalent forms — a symlinked
        path on macOS (/var -> /private/var) or an 8.3 short name on Windows
        (RUNNER~1 -> runneradmin). Lexical os.path.relpath then returned a
        ..-prefixed path, so the `not rel.startswith("..")` guard silently
        dropped every path-scoped reminder (H-12/H-15/H-16/H-13). Reproduced
        with a symlinked root: the hook's cwd/file_path go through the link
        while git resolves to the real path."""
        real = os.path.realpath(self.root)
        link = real + "_lnk"
        try:
            os.symlink(real, link, target_is_directory=True)
        except OSError:
            self.skipTest("symlink creation not permitted on this host")
        self.addCleanup(lambda: os.path.lexists(link) and os.remove(link))
        rel = ".github/workflows/ci.yml"
        abspath = os.path.join(link, rel.replace("/", os.sep))
        os.makedirs(os.path.dirname(abspath), exist_ok=True)
        payload = {"hook_event_name": "PostToolUse", "cwd": link,
                   "tool_name": "Write",
                   "tool_input": {"file_path": abspath,
                                  "content": "name: ci\non: push\n"}}
        proc = subprocess.run([sys.executable, HOOK], input=json.dumps(payload),
                              capture_output=True, text=True, cwd=link,
                              encoding="utf-8")
        self.assertIn("H-15", proc.stderr)
        self.assertEqual(proc.returncode, 0)


if __name__ == "__main__":
    unittest.main()
