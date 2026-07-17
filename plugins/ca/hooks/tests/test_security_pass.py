"""Branch coverage for security-pass.py.

The guard-logic matrix (.github/scripts/test_hook_guards.py) exercises only the
happy path (case 6c: one sensitive line, committed repo). This file covers the
branches it doesn't: no-.codearbiter exit, empty-digest write, untracked-file
inclusion, the MAX_UNTRACKED_BYTES skip, and the unborn-branch (no HEAD) path.

Same subprocess style as the other guard tests: run security-pass.py via the
current interpreter, cwd'd into a throwaway repo, and read the marker it writes.
Stdlib only.
"""
import os
import subprocess
import sys
import tempfile
import unittest

HOOKS = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SECURITY_PASS = os.path.join(HOOKS, "security-pass.py")
CRYPTO_LINE = "const h = createHash('md5');\n"  # matches CRYPTO_RE


def _sh(args, cwd, **kw):
    return subprocess.run(args, cwd=cwd, capture_output=True, text=True,
                          encoding="utf-8", errors="replace", timeout=60, **kw)


def _git(args, cwd):
    r = _sh(["git"] + args, cwd)
    if r.returncode != 0:
        raise RuntimeError(f"git {' '.join(args)} failed: {r.stderr}")
    return r


class _Fixture(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.root = os.path.join(self._tmp.name, "repo")
        os.makedirs(self.root)
        _git(["init", "-q", "-b", "feat/work", self.root], self._tmp.name)
        _git(["config", "user.email", "h@example.com"], self.root)
        _git(["config", "user.name", "h"], self.root)

    def tearDown(self):
        self._tmp.cleanup()

    def _ca(self):
        os.makedirs(os.path.join(self.root, ".codearbiter"), exist_ok=True)

    def _write(self, rel, text):
        p = os.path.join(self.root, rel)
        os.makedirs(os.path.dirname(p), exist_ok=True)
        with open(p, "w", encoding="utf-8") as f:
            f.write(text)
        return p

    def run_pass(self):
        return _sh([sys.executable, SECURITY_PASS], self.root)

    def marker(self):
        p = os.path.join(self.root, ".codearbiter", ".markers", "security-gate-passed")
        if not os.path.isfile(p):
            return None
        with open(p, encoding="utf-8") as f:
            return f.read()


class TestSecurityPassBranches(_Fixture):
    def test_no_codearbiter_exits_1(self):
        # No .codearbiter/ dir -> refuse, exit 1, record nothing.
        res = self.run_pass()
        self.assertEqual(res.returncode, 1)
        self.assertIn("no .codearbiter", res.stderr.lower())

    def test_empty_digest_when_no_sensitive_lines(self):
        # A benign committed repo with a benign change -> marker written empty.
        self._ca()
        self._write("notes.txt", "hello\n")
        _git(["add", "notes.txt"], self.root)
        _git(["commit", "-q", "-m", "seed"], self.root)
        self._write("notes.txt", "hello\nworld\n")
        res = self.run_pass()
        self.assertEqual(res.returncode, 0)
        self.assertIn("0 sensitive line", res.stdout)
        self.assertEqual(self.marker(), "")  # empty digest set

    def test_untracked_sensitive_line_recorded(self):
        # An untracked file's sensitive line is in scope (commit-gate will stage it).
        self._ca()
        self._write("auth.js", CRYPTO_LINE)  # untracked, never added
        res = self.run_pass()
        self.assertEqual(res.returncode, 0)
        self.assertIn("1 sensitive line", res.stdout)
        self.assertTrue(self.marker().strip())

    def test_oversize_untracked_file_is_skipped(self):
        # An untracked blob over MAX_UNTRACKED_BYTES is not reviewable prose -> skip.
        self._ca()
        big = ("x" * 1_000_001) + "\n" + CRYPTO_LINE
        self._write("blob.js", big)
        res = self.run_pass()
        self.assertEqual(res.returncode, 0)
        self.assertIn("0 sensitive line", res.stdout)  # the md5 line was skipped with the blob

    def test_unborn_branch_records_staged_sensitive_line(self):
        # No commit yet (unborn HEAD): `git diff HEAD` fails, fall back to ls-files.
        self._ca()
        self._write("auth.js", CRYPTO_LINE)
        _git(["add", "auth.js"], self.root)  # tracked, but no HEAD exists
        res = self.run_pass()
        self.assertEqual(res.returncode, 0)
        self.assertIn("1 sensitive line", res.stdout)

    def test_diff_head_added_sensitive_line_recorded(self):
        # Committed repo, a new sensitive line in the worktree diff -> recorded.
        self._ca()
        self._write("auth.js", "const ok = 1;\n")
        _git(["add", "auth.js"], self.root)
        _git(["commit", "-q", "-m", "seed"], self.root)
        self._write("auth.js", "const ok = 1;\n" + CRYPTO_LINE)
        res = self.run_pass()
        self.assertEqual(res.returncode, 0)
        self.assertIn("1 sensitive line", res.stdout)

    def test_gate_events_log_untracked_contributes_no_digests(self):
        # #279: gate-events.log is the gate's own machine-written audit sink —
        # its REMIND text ("no MD5/SHA1/DES/3DES/RC2/RC4/Blowfish") matches
        # CRYPTO_RE just as well as a genuine algorithm choice would, so an
        # UNTRACKED gate-events.log full of such lines must contribute ZERO
        # digests to the marker (the untracked-file branch of candidate_lines).
        self._ca()
        self._write(".codearbiter/gate-events.log", CRYPTO_LINE * 3)
        res = self.run_pass()
        self.assertEqual(res.returncode, 0)
        self.assertIn("0 sensitive line", res.stdout)
        self.assertEqual(self.marker(), "")

    def test_gate_events_log_diff_contributes_no_digests(self):
        # #279: same exemption via the `git diff HEAD` branch — a COMMITTED
        # gate-events.log with a new, uncommitted REMIND line appended must
        # still contribute zero digests, proving the diff walk (not just the
        # untracked-file walk) is path-aware.
        self._ca()
        self._write(".codearbiter/gate-events.log", "seed\n")
        _git(["add", ".codearbiter/gate-events.log"], self.root)
        _git(["commit", "-q", "-m", "seed log"], self.root)
        self._write(".codearbiter/gate-events.log", "seed\n" + CRYPTO_LINE)
        res = self.run_pass()
        self.assertEqual(res.returncode, 0)
        self.assertIn("0 sensitive line", res.stdout)
        self.assertEqual(self.marker(), "")

    def test_gate_events_log_exemption_is_narrow(self):
        # #279 non-weakening proof: the SAME sensitive line, in a DIFFERENT
        # file, must still be recorded — only gate-events.log is exempt.
        self._ca()
        self._write(".codearbiter/overrides.log", CRYPTO_LINE)
        res = self.run_pass()
        self.assertEqual(res.returncode, 0)
        self.assertIn("1 sensitive line", res.stdout)
        self.assertTrue(self.marker().strip())

    def test_marker_write_leaves_no_temp_file(self):
        # migration-002: the marker is written atomically (temp + os.replace), so
        # after a successful run the .markers dir holds the marker and no .tmp.
        self._ca()
        self._write("auth.js", CRYPTO_LINE)
        res = self.run_pass()
        self.assertEqual(res.returncode, 0)
        markers_dir = os.path.join(self.root, ".codearbiter", ".markers")
        entries = sorted(os.listdir(markers_dir))
        self.assertEqual(entries, ["security-gate-passed"],
                         f"only the marker should remain, got {entries}")


if __name__ == "__main__":
    unittest.main()
