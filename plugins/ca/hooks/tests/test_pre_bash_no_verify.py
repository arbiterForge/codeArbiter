"""appsec-002 (#175): pre-bash.py must block a literal --no-verify / -n flag on
`git commit` / `git push` — that spelling skips the .git/hooks git-enforce
backstop entirely (COMMIT_RE/PUSH_RE match the literal `git` verb; nothing
inspected the flag list for a verify-skip). The deeper shell-indirection
residual (`g=git; $g commit --no-verify`) is out of scope for this guard and is
documented as an accepted residual elsewhere — this covers only the literal
spelling.

Stdlib only; hook JSON piped to pre-bash.py on stdin in a throwaway
arbiter-enabled git repo (mirrors test_pre_bash_activation.py).
"""
import json
import os
import subprocess
import sys
import tempfile
import unittest

HOOKS = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PRE_BASH = os.path.join(HOOKS, "pre-bash.py")


def _sh(args, cwd, **kw):
    env = {**os.environ, "CLAUDE_PROJECT_DIR": cwd}
    return subprocess.run(args, cwd=cwd, capture_output=True, text=True,
                          encoding="utf-8", errors="replace", timeout=60,
                          env=env, **kw)


def _git(args, cwd):
    r = _sh(["git"] + args, cwd)
    if r.returncode != 0:
        raise RuntimeError(f"git {' '.join(args)} failed: {r.stderr}")
    return r


class _PreBashFixture(unittest.TestCase):
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

    def tearDown(self):
        self._tmp.cleanup()

    def run_bash(self, command):
        payload = json.dumps({"tool_name": "Bash", "tool_input": {"command": command}})
        return _sh([sys.executable, PRE_BASH], self.root, input=payload)

    def assertBlocked(self, res, tag):
        self.assertEqual(res.returncode, 2,
                         f"expected BLOCK (exit 2); got {res.returncode} / {res.stderr[:200]!r}")
        self.assertIn(tag, res.stderr)

    def assertAllowed(self, res):
        self.assertEqual(res.returncode, 0,
                         f"expected ALLOW (exit 0); got {res.returncode} / {res.stderr[:200]!r}")


class TestNoVerifyCommit(_PreBashFixture):
    def test_commit_with_long_no_verify_is_blocked(self):
        self.assertBlocked(self.run_bash("git commit --no-verify -m x"), "H-20")

    def test_commit_with_short_n_is_blocked(self):
        self.assertBlocked(self.run_bash("git commit -n -m x"), "H-20")

    def test_normal_commit_is_unaffected(self):
        self.assertAllowed(self.run_bash("git commit -m x"))

    def test_commit_message_mentioning_no_verify_is_not_blocked_on_h20(self):
        # A commit message QUOTING --no-verify (not passed as a real flag) must
        # not be misclassified — ambiguity here would over-block legitimate
        # commit messages describing this very fix.
        res = self.run_bash('git commit -m "docs: explain --no-verify guard"')
        self.assertNotIn("H-20", res.stderr)

    # -- bundled short-flag cluster (security-reviewer HIGH, first pass) -----

    def test_commit_bundled_nm_cluster_is_blocked(self):
        # `-nm "x"` bundles `-n` (no-verify) with `-m x` — the everyday way
        # `-n` actually gets typed alongside a message flag. An exact-token
        # check against "-n" alone misses this cluster spelling entirely.
        self.assertBlocked(self.run_bash('git commit -nm "x"'), "H-20")

    def test_commit_bundled_vn_cluster_is_blocked(self):
        # `-v` (verbose) does not consume a value, so scanning continues to
        # the trailing `n` in the same cluster -> no-verify.
        self.assertBlocked(self.run_bash("git commit -vn -m x"), "H-20")

    def test_commit_bundled_mn_cluster_is_not_blocked(self):
        # `-mn "x"` is `-m` (message, ARGUMENT-TAKING) immediately followed by
        # "n" -> "n" is the flag's VALUE (message text "n"), not a further
        # `-n`/no-verify flag. Must NOT block on H-20.
        res = self.run_bash('git commit -mn "x"')
        self.assertNotIn("H-20", res.stderr)

    # -- attached-value cluster (security-reviewer HIGH, second pass) --------
    # A `re.fullmatch(r"-[A-Za-z]+", tok)` gate previously skipped the WHOLE
    # token whenever any character after the dashes wasn't a letter — so a
    # leading `-n` immediately followed by an attached value (`=x`, `123`, …)
    # was never even inspected. Proven live against a real .git/hooks/pre-commit:
    # -nm=x, -nm123, -vnm=y all committed with the hook skipped.

    def test_commit_nm_equals_value_cluster_is_blocked(self):
        # -nm=x: walk hits 'n' before 'm' (and before the '=') -> no-verify.
        self.assertBlocked(self.run_bash("git commit -nm=x"), "H-20")

    def test_commit_nm_digit_value_cluster_is_blocked(self):
        # -nm123: walk hits 'n' before 'm' (and before the digits) -> no-verify.
        self.assertBlocked(self.run_bash("git commit -nm123"), "H-20")

    def test_commit_vnm_equals_value_cluster_is_blocked(self):
        # -vnm=y: 'v' has no special meaning, walk continues to 'n' -> no-verify.
        self.assertBlocked(self.run_bash("git commit -vnm=y"), "H-20")

    def test_commit_mn_equals_value_cluster_is_not_blocked(self):
        # -mn=x: 'm' (argument-taking) is hit FIRST -> the rest ("n=x") is the
        # message value, not a further -n flag. Must NOT block on H-20.
        res = self.run_bash("git commit -mn=x")
        self.assertNotIn("H-20", res.stderr)

    def test_commit_Sn_cluster_is_not_blocked(self):
        # -Sn: 'S' (--gpg-sign, argument-taking) is hit FIRST -> "n" is its
        # value (the signing key id), not a further -n flag.
        res = self.run_bash("git commit -Sn -m x")
        self.assertNotIn("H-20", res.stderr)


class TestNoVerifyPush(_PreBashFixture):
    def test_push_with_long_no_verify_is_blocked(self):
        self.assertBlocked(self.run_bash("git push --no-verify"), "H-20")

    def test_push_with_long_no_verify_and_remote_is_blocked(self):
        self.assertBlocked(self.run_bash("git push --no-verify origin feat/work"), "H-20")

    def test_normal_push_is_unaffected(self):
        # No remote configured in the fixture, but the guard runs before any
        # network operation — this only proves H-20 does not fire.
        res = self.run_bash("git push origin feat/work")
        self.assertNotIn("H-20", res.stderr)


if __name__ == "__main__":
    unittest.main()
