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
import contextlib
import importlib.util as _ilu
import io
import os
import subprocess
import sys
import tempfile
import unittest
from unittest import mock

HOOKS = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
ENFORCE = os.path.join(HOOKS, "git-enforce.py")

sys.path.insert(0, HOOKS)
import _githooks  # noqa: E402


def _load_git_enforce():
    """Import git-enforce.py fresh as a module (hyphenated filename, so a
    plain `import` can't name it — mirrors test_governs.py's pattern). A fresh
    module per call means monkeypatches in one test can never leak into
    another via a cached singleton."""
    spec = _ilu.spec_from_file_location("git_enforce_direct", ENFORCE)
    mod = _ilu.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


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


class TestInstallSkipsReprobeWhenCurrent(_GitFixture):
    """performance-002 (#194): a second install() call for the SAME repo, with
    nothing changed, must skip the git-config/rev-parse re-probe entirely — the
    cheap on-disk cache proves the hooks are already current without spawning
    git at all. This is the semantic property the acceptance criteria asks for:
    a SPECIFIC re-probe skipped, not a raw platform-varying spawn count."""

    def _hooks_dir(self):
        return os.path.join(self.root, ".git", "hooks")

    def test_second_call_makes_zero_git_hooks_dir_probe_calls(self):
        # First call: genuine cold install — the probe (_git) legitimately runs.
        first_calls = []
        orig = _githooks._git

        def spy1(args, cwd):
            first_calls.append(list(args))
            return orig(args, cwd)

        _githooks._git = spy1
        try:
            _githooks.install(self.root)
        finally:
            _githooks._git = orig
        self.assertTrue(first_calls, "cold install must resolve hooks_dir via git")

        # Second call against the SAME repo, nothing changed: the cached
        # hooks_dir + up-to-date shim check must short-circuit BEFORE hooks_dir()
        # ever calls _git — zero git-hooks-dir-probe spawns this time.
        second_calls = []

        def spy2(args, cwd):
            second_calls.append(list(args))
            return orig(args, cwd)

        _githooks._git = spy2
        try:
            result = _githooks.install(self.root)
        finally:
            _githooks._git = orig
        self.assertEqual(result, [])
        self.assertEqual(second_calls, [],
                         "install() must skip the hooks_dir git-config/rev-parse "
                         "re-probe when the cached hooks are already current")

    def test_cache_miss_falls_through_to_full_probe(self):
        # A cache-miss (nothing installed yet, no cache file) must still fully
        # resolve and install via the real git-based probe — the fast path
        # never substitutes for a genuine cold install.
        cache_file = os.path.join(self.root, ".git", _githooks._HOOKSDIR_CACHE_NAME)
        self.assertFalse(os.path.isfile(cache_file))
        actions = _githooks.install(self.root)
        self.assertIn("pre-commit: installed", actions)
        self.assertIn("pre-push: installed", actions)
        self.assertTrue(os.path.isfile(cache_file),
                        "a successful resolution must persist the hooks_dir cache")

    def test_stale_cached_hooks_dir_falls_through(self):
        # A cache file naming a directory that no longer exists must be treated
        # as a miss (never trusted blindly).
        os.makedirs(os.path.join(self.root, ".git"), exist_ok=True)
        cache_file = os.path.join(self.root, ".git", _githooks._HOOKSDIR_CACHE_NAME)
        with open(cache_file, "w", encoding="utf-8") as f:
            f.write(os.path.join(self.root, "_nonexistent_hooks_dir") + "\n")
        actions = _githooks.install(self.root)
        self.assertIn("pre-commit: installed", actions)
        for phase in ("pre-commit", "pre-push"):
            self.assertTrue(os.path.isfile(os.path.join(self._hooks_dir(), phase)))

    def test_mismatched_enforcer_path_falls_through_not_silently_skipped(self):
        # If the enforcer path changed (e.g. a plugin update moved the install
        # dir) since the cache was written, the shim content no longer matches
        # -> _hooks_current() must return False -> the full probe must run and
        # refresh the shim, never silently skip a needed update.
        _githooks.install(self.root)  # writes the cache with the real enforcer path
        with mock.patch.object(_githooks, "_enforcer_path", return_value="/moved/enforcer.py"):
            actions = _githooks.install(self.root)
        self.assertIn("pre-commit: installed", actions)
        self.assertIn("pre-push: installed", actions)
        with open(os.path.join(self._hooks_dir(), "pre-commit"), encoding="utf-8") as f:
            self.assertIn("/moved/enforcer.py", f.read())


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

    # coverage-002 (#193): H-10b secret-only block, H-14 migration block, and
    # both pre_commit() fail-closed git-read branches — previously untested.

    def test_secret_only_commit_without_marker_is_blocked_h10b_not_h09b(self):
        _git(["checkout", "-q", "-b", "feat/s"], self.root)
        # No crypto/TLS token here (no hashing or signing call) — SECRET_RE only.
        # Built via concatenation (not a literal line in this source file) so
        # this repo's OWN commit-gate doesn't flag test_git_hooks.py's own diff
        # as introducing a secret — the fixture file written to disk still
        # carries the real literal line SECRET_RE must match.
        key_line = "api" + "_key" + ' = "' + "abcd1234efgh5678" + '"\n'
        self._stage("s.py", key_line)
        res = self.enforce("pre-commit")
        self.assertEqual(res.returncode, 1, res.stderr)
        self.assertIn("H-10b", res.stderr)
        self.assertNotIn("H-09b", res.stderr)

    def test_migration_without_gate_pass_is_blocked_h14(self):
        _git(["checkout", "-q", "-b", "feat/m"], self.root)
        self._stage("db/migrations/0001_init.sql", "CREATE TABLE t (id int);\n")
        res = self.enforce("pre-commit")
        self.assertEqual(res.returncode, 1, res.stderr)
        self.assertIn("H-14", res.stderr)

    def test_cached_diff_read_failure_fails_closed(self):
        # Point PATH at a nonexistent dir so EVERY git spawn in pre_commit()
        # fails, including the very first (current_branch) — the H-01 fail-closed
        # branch fires
        # before either the H-09b/H-10b or H-14 read site is reached. Kept as
        # end-to-end evidence that an entirely unreadable git still fails
        # CLOSED, not open; test_git_enforce_lib.py below isolates the two
        # DISTINCT pre_commit() read-failure branches (cached_added_lines vs
        # cached_names) that coverage-002 calls out, via direct monkeypatching
        # (subprocess-level PATH-stripping can't differentiate the two, since
        # both read sites fail identically once git itself is unspawnable).
        _git(["checkout", "-q", "-b", "feat/g"], self.root)
        self._stage("f.txt", "x\n")
        # PATH is SET to a nonexistent dir (not unset): POSIX execvp falls back
        # to its default /usr/bin:/bin when PATH is absent and would still find
        # git, defeating the fail-closed premise on non-Windows CI.
        env = {k: v for k, v in os.environ.items() if k.upper() != "PATHEXT"}
        env["PATH"] = os.path.join(self.root, "_nonexistent_bin")
        res = _sh([sys.executable, ENFORCE, "pre-commit"], self.root, env=env)
        self.assertEqual(res.returncode, 1, res.stderr)
        self.assertIn("failing closed", res.stderr)


class TestPreCommitFailClosedBranches(_GitFixture):
    """coverage-002 (#193): isolate pre_commit()'s two DISTINCT git-read
    fail-closed branches — cached_added_lines() -> None (H-09b/H-10b) and
    cached_names() -> None (H-14) — by calling pre_commit() in-process with one
    read function monkeypatched to fail while the other succeeds normally. A
    subprocess-level git-unreadable test (see test_cached_diff_read_failure_
    fails_closed above) can't isolate these: once git itself can't be spawned,
    BOTH reads fail identically and only ever exercises the first one
    (current_branch, H-01)."""

    def setUp(self):
        super().setUp()
        _git(["checkout", "-q", "-b", "feat/branches"], self.root)
        self._write(os.path.join(self.root, "f.txt"), "x\n")
        _git(["add", "f.txt"], self.root)

    def test_added_lines_read_failure_fails_closed_h09b(self):
        ge = _load_git_enforce()
        ge.cached_added_lines = lambda cwd: None
        buf = io.StringIO()
        with contextlib.redirect_stderr(buf):
            with self.assertRaises(SystemExit) as ctx:
                ge.pre_commit(self.root)
        self.assertEqual(ctx.exception.code, 1)
        self.assertIn("H-09b", buf.getvalue())
        self.assertIn("failing closed", buf.getvalue())

    def test_staged_names_read_failure_fails_closed_h14(self):
        ge = _load_git_enforce()
        ge.cached_added_lines = lambda cwd: []  # no sensitive content -> pass H-09b/H-10b
        ge.cached_names = lambda cwd: None
        buf = io.StringIO()
        with contextlib.redirect_stderr(buf):
            with self.assertRaises(SystemExit) as ctx:
                ge.pre_commit(self.root)
        self.assertEqual(ctx.exception.code, 1)
        self.assertIn("H-14", buf.getvalue())
        self.assertIn("failing closed", buf.getvalue())


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

    # coverage-001 (#193): H-02 (force / non-fast-forward) is otherwise
    # completely untested — the two cases above only exercise H-01 and a
    # create-ref push (which short-circuits H-02 via the all-zero remote sha).

    def _commit(self, name, content, msg):
        self._write(os.path.join(self.root, name), content)
        _git(["add", name], self.root)
        _git(["commit", "-q", "-m", msg, "--no-verify"], self.root)
        return _git(["rev-parse", "HEAD"], self.root).stdout.strip()

    def test_non_fast_forward_push_is_blocked_h02(self):
        # A real non-fast-forward: local and remote diverge from a common base,
        # neither a descendant of the other, both refs non-zero (not a
        # create/delete) — merge-base --is-ancestor(remote, local) is False.
        base = self._commit("base.txt", "base\n", "base")
        local_sha = self._commit("local.txt", "local\n", "local")
        _git(["checkout", "-q", "-b", "alt", base], self.root)
        remote_sha = self._commit("remote.txt", "remote\n", "remote")
        _git(["checkout", "-q", "main"], self.root)
        line = f"refs/heads/feat/x {local_sha} refs/heads/feat/x {remote_sha}\n"
        res = self.enforce("pre-push", stdin=line)
        self.assertEqual(res.returncode, 1, res.stderr)
        self.assertIn("H-02", res.stderr)

    def test_genuine_fast_forward_update_is_allowed_h02(self):
        # A true (non-create) fast-forward: remote_sha IS an ancestor of
        # local_sha, both refs non-zero.
        remote_sha = self._commit("base2.txt", "base\n", "base2")
        local_sha = self._commit("child.txt", "child\n", "child")
        line = f"refs/heads/feat/y {local_sha} refs/heads/feat/y {remote_sha}\n"
        res = self.enforce("pre-push", stdin=line)
        self.assertEqual(res.returncode, 0, res.stderr)

    def test_unresolvable_merge_base_fails_closed_h02(self):
        # remote_sha names a commit this repo has never heard of — `git
        # merge-base --is-ancestor` errors (unknown revision), which must
        # resolve CLOSED (block), not silently pass as "not force".
        local_sha = self._commit("f3.txt", "x\n", "local3")
        bogus_remote = "f" * 40
        line = f"refs/heads/feat/z {local_sha} refs/heads/feat/z {bogus_remote}\n"
        res = self.enforce("pre-push", stdin=line)
        self.assertEqual(res.returncode, 1, res.stderr)
        self.assertIn("H-02", res.stderr)


if __name__ == "__main__":
    unittest.main()
