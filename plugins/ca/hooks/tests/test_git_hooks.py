"""Behavioral coverage for the git-level enforcement backstop (#161).

pre-bash.py gates git operations by matching the literal Bash command string, so
shell indirection (`g=git; c=commit; $g $c`) walks straight past it. _githooks.py
installs .git/hooks/pre-commit and pre-push that run git-enforce.py at the git
operation itself, where spelling no longer matters. These tests prove:

  * install() writes ours-hooks, is idempotent, and NEVER clobbers a foreign hook
  * git-enforce.py blocks a commit onto main — including via VARIABLE INDIRECTION,
    the exact bypass #161 is about — and allows a feature-branch commit
  * it blocks a crypto commit lacking a security-gate marker (H-09b)
  * pre-push blocks a protected-branch push (H-01), allows a feature fast-forward
  * a non-arbiter repo is a no-op

Stdlib only; a real throwaway git repo per test (git hooks only fire against a
real repo).
"""
import os
import subprocess
import sys
import tempfile
import unittest

HOOKS = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
ENFORCE = os.path.join(HOOKS, "git-enforce.py")

sys.path.insert(0, HOOKS)
import _githooks  # noqa: E402


def _sh(args, cwd, **kw):
    return subprocess.run(args, cwd=cwd, capture_output=True, text=True,
                          encoding="utf-8", errors="replace", timeout=60, **kw)


def _git(args, cwd, check=True):
    r = _sh(["git"] + args, cwd)
    if check and r.returncode != 0:
        raise RuntimeError(f"git {' '.join(args)} failed: {r.stderr}")
    return r


class _GitFixture(unittest.TestCase):
    ARBITER = "---\narbiter: enabled\nstage: 2\n---\n<!--INITIALIZED-->\n"

    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.root = os.path.join(self._tmp.name, "repo")
        os.makedirs(self.root)
        _git(["init", "-q", "-b", "main"], self.root)
        _git(["config", "user.email", "h@example.com"], self.root)
        _git(["config", "user.name", "harness"], self.root)
        os.makedirs(os.path.join(self.root, ".codearbiter"))
        self._write(os.path.join(self.root, ".codearbiter", "CONTEXT.md"), self.ARBITER)

    def tearDown(self):
        self._tmp.cleanup()

    def _write(self, path, text):
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "w", encoding="utf-8") as f:
            f.write(text)

    def _disable_arbiter(self):
        self._write(os.path.join(self.root, ".codearbiter", "CONTEXT.md"),
                    "# ctx\nno frontmatter\n")

    def enforce(self, phase, stdin=""):
        return _sh([sys.executable, ENFORCE, phase], self.root, input=stdin)


class TestInstall(_GitFixture):
    def _hooks_dir(self):
        return os.path.join(self.root, ".git", "hooks")

    def test_install_writes_both_hooks(self):
        _githooks.install(self.root)
        for phase in ("pre-commit", "pre-push"):
            dest = os.path.join(self._hooks_dir(), phase)
            self.assertTrue(os.path.isfile(dest))
            with open(dest, encoding="utf-8") as f:
                self.assertIn(_githooks.SENTINEL, f.read())
            self.assertTrue(os.access(dest, os.X_OK))

    def test_install_is_idempotent(self):
        _githooks.install(self.root)
        second = _githooks.install(self.root)
        self.assertEqual(second, [])  # already current -> no churn

    def test_foreign_hook_is_preserved(self):
        dest = os.path.join(self._hooks_dir(), "pre-commit")
        os.makedirs(self._hooks_dir(), exist_ok=True)
        self._write(dest, "#!/bin/sh\necho husky\n")
        _githooks.install(self.root)
        with open(dest, encoding="utf-8") as f:
            body = f.read()
        self.assertIn("husky", body)
        self.assertNotIn(_githooks.SENTINEL, body)

    def test_uninstall_removes_only_ours(self):
        _githooks.install(self.root)
        _githooks.uninstall(self.root)
        self.assertFalse(os.path.isfile(os.path.join(self._hooks_dir(), "pre-commit")))


class TestPreCommitEnforce(_GitFixture):
    def _stage(self, name, content):
        self._write(os.path.join(self.root, name), content)
        _git(["add", name], self.root)

    def test_direct_commit_to_main_is_blocked(self):
        self._stage("f.txt", "x\n")
        res = self.enforce("pre-commit")
        self.assertEqual(res.returncode, 1, res.stderr)
        self.assertIn("H-01", res.stderr)

    def test_variable_indirection_commit_is_blocked_at_git_layer(self):
        # The #161 bypass: build `git commit` from shell vars. pre-bash never sees
        # a git token, but the git hook fires on the real operation. Run a REAL
        # indirected commit with our hook installed and assert it aborts.
        _githooks.install(self.root)
        self._stage("f.txt", "x\n")
        res = _sh(["sh", "-c", "g=git; c=commit; $g $c -m sneaky"], self.root)
        self.assertNotEqual(res.returncode, 0, "indirected commit should have been blocked")
        self.assertIn("H-01", res.stderr + res.stdout)
        # nothing committed
        log = _git(["rev-list", "--all", "--count"], self.root, check=False)
        self.assertEqual(log.stdout.strip(), "0")

    def test_feature_branch_commit_is_allowed(self):
        _git(["checkout", "-q", "-b", "feat/x"], self.root)
        self._stage("f.txt", "x\n")
        res = self.enforce("pre-commit")
        self.assertEqual(res.returncode, 0, res.stderr)

    def test_crypto_commit_without_marker_is_blocked(self):
        _git(["checkout", "-q", "-b", "feat/c"], self.root)
        self._stage("c.js", 'const h = crypto.createHash("md5");\n')
        res = self.enforce("pre-commit")
        self.assertEqual(res.returncode, 1, res.stderr)
        self.assertIn("H-09b", res.stderr)

    def test_dormant_repo_is_noop(self):
        self._disable_arbiter()
        self._stage("f.txt", "x\n")
        res = self.enforce("pre-commit")
        self.assertEqual(res.returncode, 0, res.stderr)


class TestPrePushEnforce(_GitFixture):
    def test_push_to_protected_branch_is_blocked(self):
        line = "refs/heads/feat/x abc123 refs/heads/main def456\n"
        res = self.enforce("pre-push", stdin=line)
        self.assertEqual(res.returncode, 1, res.stderr)
        self.assertIn("H-01", res.stderr)

    def test_feature_fast_forward_push_is_allowed(self):
        _git(["checkout", "-q", "-b", "feat/x"], self.root)
        self._write(os.path.join(self.root, "f.txt"), "x\n")
        _git(["add", "f.txt"], self.root)
        _git(["commit", "-q", "-m", "ok", "--no-verify"], self.root)
        sha = _git(["rev-parse", "HEAD"], self.root).stdout.strip()
        zero = "0" * 40
        line = f"refs/heads/feat/x {sha} refs/heads/feat/x {zero}\n"  # create -> no force
        res = self.enforce("pre-push", stdin=line)
        self.assertEqual(res.returncode, 0, res.stderr)


if __name__ == "__main__":
    unittest.main()
