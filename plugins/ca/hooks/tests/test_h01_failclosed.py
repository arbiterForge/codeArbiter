"""reliability-001 (#189): H-01's protected-branch checks (pre-bash.py and
git-enforce.py) must fail CLOSED when git itself cannot answer — a spawn
failure or a timeout must BLOCK a commit/push, not silently ALLOW it because
`current_branch`/`head_on_protected_tip` collapsed the error into "" / False
(indistinguishable from "legitimately not on a protected branch/tip").

Git is made unreadable by stripping PATH from the subprocess environment, so
`git` itself is never found — a real, deterministic spawn failure
(FileNotFoundError) on every platform, not a mock. Contrast with the existing
happy-path tests in test_pre_bash_activation.py / test_git_hooks.py, which
prove the ALLOW/BLOCK verdicts when git *can* answer; these prove the
ambiguous case now resolves CLOSED instead of open.
"""
import json
import os
import subprocess
import sys
import tempfile
import unittest

HOOKS = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PRE_BASH = os.path.join(HOOKS, "pre-bash.py")
ENFORCE = os.path.join(HOOKS, "git-enforce.py")


def _sh(args, cwd, env=None, **kw):
    return subprocess.run(args, cwd=cwd, capture_output=True, text=True,
                          encoding="utf-8", errors="replace", timeout=60,
                          env=env, **kw)


def _git(args, cwd):
    r = _sh(["git"] + args, cwd, env=os.environ.copy())
    if r.returncode != 0:
        raise RuntimeError(f"git {' '.join(args)} failed: {r.stderr}")
    return r


class _GitUnreadableFixture(unittest.TestCase):
    ARBITER = "---\narbiter: enabled\nstage: 2\n---\n<!--INITIALIZED-->\n"

    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.root = os.path.join(self._tmp.name, "repo")
        os.makedirs(self.root)
        _git(["init", "-q", "-b", "feat/work"], self.root)
        _git(["config", "user.email", "h@example.com"], self.root)
        _git(["config", "user.name", "harness"], self.root)
        os.makedirs(os.path.join(self.root, ".codearbiter"))
        with open(os.path.join(self.root, ".codearbiter", "CONTEXT.md"), "w",
                  encoding="utf-8") as f:
            f.write(self.ARBITER)
        with open(os.path.join(self.root, "notes.txt"), "w", encoding="utf-8") as f:
            f.write("hello\n")
        _git(["add", "notes.txt"], self.root)

    def tearDown(self):
        self._tmp.cleanup()

    def _no_git_env(self):
        """An env with no PATH (and no PATHEXT resolution) — `git` cannot be
        spawned, only the python interpreter itself (invoked by absolute
        sys.executable, which needs no PATH lookup)."""
        env = {k: v for k, v in os.environ.items()
               if k.upper() not in ("PATH", "PATHEXT")}
        env["CLAUDE_PROJECT_DIR"] = self.root
        return env


class TestPreBashH01FailsClosed(_GitUnreadableFixture):
    def run_bash(self, command, env=None):
        payload = json.dumps({"tool_name": "Bash", "tool_input": {"command": command}})
        return _sh([sys.executable, PRE_BASH], self.root, input=payload,
                   env=env or self._no_git_env())

    def test_commit_with_unreadable_git_fails_closed(self):
        res = self.run_bash('git commit -m "x"')
        self.assertEqual(res.returncode, 2, res.stderr)
        self.assertIn("H-01", res.stderr)

    def test_bare_push_with_unreadable_git_fails_closed(self):
        res = self.run_bash("git push")
        self.assertEqual(res.returncode, 2, res.stderr)
        self.assertIn("H-01", res.stderr)

    def test_commit_with_readable_git_on_feature_branch_still_allowed(self):
        # Control: with git readable (real env), a feature-branch commit is not
        # blocked by H-01 — proves the fail-closed fix didn't over-block.
        res = self.run_bash('git commit -m "x"', env={**os.environ,
                                                       "CLAUDE_PROJECT_DIR": self.root})
        self.assertNotIn("H-01", res.stderr)


class TestGitEnforceH01FailsClosed(_GitUnreadableFixture):
    def test_pre_commit_with_unreadable_git_fails_closed(self):
        res = _sh([sys.executable, ENFORCE, "pre-commit"], self.root,
                  env=self._no_git_env())
        self.assertEqual(res.returncode, 1, res.stderr)
        self.assertIn("H-01", res.stderr)

    def test_pre_commit_with_readable_git_on_feature_branch_still_allowed(self):
        res = _sh([sys.executable, ENFORCE, "pre-commit"], self.root,
                  env={**os.environ, "CLAUDE_PROJECT_DIR": self.root})
        self.assertEqual(res.returncode, 0, res.stderr)


if __name__ == "__main__":
    unittest.main()
