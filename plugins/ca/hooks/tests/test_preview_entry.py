import io
import json
import os
import subprocess
import sys
import tempfile
import unittest
from contextlib import redirect_stdout

# Ensure hooks/ is importable
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import preview  # noqa: E402 — the thin entry hook for /ca:preview (#179)


def _git(args, cwd):
    r = subprocess.run(
        ["git"] + args, cwd=cwd, capture_output=True, text=True,
        encoding="utf-8", errors="replace", timeout=60,
    )
    if r.returncode != 0:
        raise RuntimeError(f"git {' '.join(args)} failed: {r.stderr}")
    return r


class TestPreviewEntry(unittest.TestCase):
    """preview.py: thin entry hook wrapping _previewlib.collect_diff /
    scan_secrets. Proves the field-access/serialization glue (ChangedFile.kinds,
    SecretFinding._asdict()) formerly embedded as inline `python -c` prose in
    commands/preview.md is now import-covered."""

    # A literal the shared SECRET_RE genuinely matches: keyword=quoted-value,
    # value length >= 4. Built via string formatting (not a literal
    # `api_key = "..."` line in this file's own source) for the same reason
    # .github/scripts/test_preview_lib.py does: the repo's own commit-time
    # secret gate (H-10b) scans the literal diff text, not just runtime
    # values, so a directly-matching literal here would itself trip the gate.
    SECRET_VALUE = "DUMMY-not-a-real-key"
    SECRET_LINE = 'api_key = "%s"' % SECRET_VALUE

    def setUp(self):
        self._saved_cwd = os.getcwd()
        self.tmp = tempfile.TemporaryDirectory()
        self.root = self.tmp.name
        _git(["init", "-q"], self.root)
        _git(["config", "user.email", "test@example.com"], self.root)
        _git(["config", "user.name", "Test"], self.root)
        with open(os.path.join(self.root, "committed.txt"), "w", encoding="utf-8") as f:
            f.write("hello\n")
        _git(["add", "committed.txt"], self.root)
        _git(["commit", "-q", "-m", "init"], self.root)
        os.chdir(self.root)

    def tearDown(self):
        os.chdir(self._saved_cwd)
        self.tmp.cleanup()

    def _run(self, argv):
        buf = io.StringIO()
        with redirect_stdout(buf):
            rc = preview.main(argv)
        self.assertEqual(rc, 0)
        return json.loads(buf.getvalue().strip())

    def test_diff_mode_matches_direct_collect_diff_call(self):
        with open(os.path.join(self.root, "new_untracked.txt"), "w", encoding="utf-8") as f:
            f.write("data\n")
        import _previewlib

        expected = {p: sorted(cf.kinds) for p, cf in _previewlib.collect_diff().items()}
        result = self._run(["diff"])
        self.assertEqual(result, expected)
        self.assertIn("new_untracked.txt", result)
        self.assertEqual(result["new_untracked.txt"], ["untracked"])

    def test_diff_mode_empty_on_clean_repo(self):
        result = self._run(["diff"])
        self.assertEqual(result, {})

    def test_secrets_mode_matches_direct_scan_secrets_call(self):
        with open(os.path.join(self.root, "config.py"), "w", encoding="utf-8") as f:
            f.write(self.SECRET_LINE + "\n")
        import _previewlib

        expected = [f._asdict() for f in _previewlib.scan_secrets()]
        result = self._run(["secrets"])
        self.assertEqual(result, expected)
        self.assertTrue(result)
        self.assertNotIn(self.SECRET_VALUE, json.dumps(result))

    def test_secrets_mode_empty_on_clean_repo(self):
        result = self._run(["secrets"])
        self.assertEqual(result, [])

    def test_rejects_unknown_mode(self):
        with self.assertRaises(SystemExit):
            preview.main(["bogus"])


if __name__ == "__main__":
    unittest.main()
