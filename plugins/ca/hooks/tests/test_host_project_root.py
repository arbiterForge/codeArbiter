"""Tests for hostapi.Host.project_root (base/Claude host) — #260.

Covers:
  * CLAUDE_PROJECT_DIR still wins first, byte-identical to pre-#260 behavior
    (the base host backs the `ca` plugin — Claude Code — so this is the
    byte-identity guarantee the #260 remediation must not regress).
  * The payload-cwd leg (reachable only when CLAUDE_PROJECT_DIR is unset) now
    climbs to the git TOPLEVEL from that cwd rather than returning it
    verbatim (reliability-005's base-host half — CodexHost is covered
    separately in .github/scripts/test_codex_adapter.py::TestCodexProjectRoot).
  * hostapi.git_toplevel() itself: repo -> toplevel, subdir -> toplevel,
    non-repo -> None.

stdlib unittest only; no subprocess for the Host method itself (git_toplevel
shells out internally, so a real git init is used where the climb matters).
"""
import os
import subprocess
import sys
import tempfile
import unittest

_HOOKS_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if _HOOKS_DIR not in sys.path:
    sys.path.insert(0, _HOOKS_DIR)

import hostapi  # noqa: E402


def _git_available():
    try:
        r = subprocess.run(["git", "--version"], capture_output=True, timeout=10)
        return r.returncode == 0
    except Exception:  # noqa: BLE001
        return False


class GitToplevelTests(unittest.TestCase):
    """hostapi.git_toplevel(cwd) — the shared climb helper both Host.project_root
    implementations route their payload-cwd leg through."""

    def setUp(self):
        if not _git_available():
            self.skipTest("git unavailable")

    def test_repo_root_resolves_itself(self):
        with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as top:
            repo = os.path.join(top, "repo")
            os.makedirs(repo)
            r = subprocess.run(["git", "init", "-q"], cwd=repo,
                               capture_output=True, timeout=30)
            if r.returncode != 0:
                self.skipTest("git init failed")
            got = hostapi.git_toplevel(repo)
            self.assertEqual(os.path.realpath(got), os.path.realpath(repo))

    def test_subdir_climbs_to_toplevel(self):
        with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as top:
            repo = os.path.join(top, "repo")
            sub = os.path.join(repo, "a", "b")
            os.makedirs(sub)
            r = subprocess.run(["git", "init", "-q"], cwd=repo,
                               capture_output=True, timeout=30)
            if r.returncode != 0:
                self.skipTest("git init failed")
            got = hostapi.git_toplevel(sub)
            self.assertEqual(os.path.realpath(got), os.path.realpath(repo))

    def test_non_repo_returns_none(self):
        with tempfile.TemporaryDirectory() as plain:
            self.assertIsNone(hostapi.git_toplevel(plain))

    def test_no_cwd_arg_uses_process_cwd(self):
        cwd = os.getcwd()
        try:
            with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as top:
                repo = os.path.join(top, "repo")
                os.makedirs(repo)
                r = subprocess.run(["git", "init", "-q"], cwd=repo,
                                   capture_output=True, timeout=30)
                if r.returncode != 0:
                    self.skipTest("git init failed")
                os.chdir(repo)
                got = hostapi.git_toplevel()
                self.assertEqual(os.path.realpath(got), os.path.realpath(repo))
        finally:
            os.chdir(cwd)


class BaseHostProjectRootTests(unittest.TestCase):
    """hostapi.Host.project_root — CLAUDE_PROJECT_DIR-first, then the
    (now climbing) payload-cwd leg, then git-toplevel-from-cwd, then cwd."""

    def setUp(self):
        self.host = hostapi.Host()
        self._env = os.environ.get("CLAUDE_PROJECT_DIR")
        self._cwd = os.getcwd()

    def tearDown(self):
        os.chdir(self._cwd)
        if self._env is None:
            os.environ.pop("CLAUDE_PROJECT_DIR", None)
        else:
            os.environ["CLAUDE_PROJECT_DIR"] = self._env

    def test_claude_project_dir_wins_over_a_payload_cwd(self):
        # Byte-identity guarantee (#260): CLAUDE_PROJECT_DIR must still win
        # first even when a payload IS given — no Claude call site passes one
        # today, but the seam must not silently invert precedence the moment
        # one does.
        with tempfile.TemporaryDirectory() as env_dir, \
                tempfile.TemporaryDirectory() as payload_dir:
            os.environ["CLAUDE_PROJECT_DIR"] = env_dir
            got = self.host.project_root({"cwd": payload_dir})
            self.assertEqual(os.path.realpath(got), os.path.realpath(env_dir))

    def test_claude_project_dir_wins_with_no_payload(self):
        with tempfile.TemporaryDirectory() as env_dir:
            os.environ["CLAUDE_PROJECT_DIR"] = env_dir
            self.assertEqual(os.path.realpath(self.host.project_root()),
                             os.path.realpath(env_dir))

    def test_payload_cwd_subdir_climbs_to_repo_root_when_env_unset(self):
        # reliability-005 (#260): even on the base Host, a payload cwd naming
        # a repo SUBDIRECTORY resolves the repo root, not the subdir verbatim.
        if not _git_available():
            self.skipTest("git unavailable")
        os.environ.pop("CLAUDE_PROJECT_DIR", None)
        with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as top:
            repo = os.path.join(top, "repo")
            sub = os.path.join(repo, "sub")
            os.makedirs(sub)
            r = subprocess.run(["git", "init", "-q"], cwd=repo,
                               capture_output=True, timeout=30)
            if r.returncode != 0:
                self.skipTest("git init failed")
            got = self.host.project_root({"cwd": sub})
            self.assertEqual(os.path.realpath(got), os.path.realpath(repo))

    def test_payload_cwd_non_repo_falls_back_to_cwd_verbatim(self):
        os.environ.pop("CLAUDE_PROJECT_DIR", None)
        with tempfile.TemporaryDirectory() as payload_dir:
            got = self.host.project_root({"cwd": payload_dir})
            self.assertEqual(os.path.realpath(got), os.path.realpath(payload_dir))


def _init_repo(root, branch="main"):
    os.makedirs(root)
    r = subprocess.run(["git", "init", "-q", "-b", branch], cwd=root,
                       capture_output=True, timeout=30)
    if r.returncode != 0:
        return False
    subprocess.run(["git", "config", "user.email", "h@example.com"], cwd=root,
                   capture_output=True, timeout=30)
    subprocess.run(["git", "config", "user.name", "h"], cwd=root,
                   capture_output=True, timeout=30)
    with open(os.path.join(root, "seed.txt"), "w", encoding="utf-8") as f:
        f.write("seed\n")
    subprocess.run(["git", "add", "seed.txt"], cwd=root, capture_output=True, timeout=30)
    r = subprocess.run(["git", "commit", "-q", "-m", "seed"], cwd=root,
                       capture_output=True, timeout=30)
    return r.returncode == 0


class GitWorktreeMainRootTests(unittest.TestCase):
    """hostapi.git_worktree_main_root(root) — #604's escalation from a linked
    worktree's own checkout to the MAIN checkout that owns the shared `.git`
    directory. Used by Host.marker_root() (below), NOT by Host.project_root()
    itself — see both docstrings for why the split matters."""

    def setUp(self):
        if not _git_available():
            self.skipTest("git unavailable")

    def test_linked_worktree_resolves_to_main_checkout(self):
        with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as top:
            main_checkout = os.path.join(top, "main-checkout")
            if not _init_repo(main_checkout, branch="main"):
                self.skipTest("git init/commit failed")
            wt_dir = os.path.join(top, "linked-worktree")
            r = subprocess.run(
                ["git", "worktree", "add", "-b", "feat/x", wt_dir], cwd=main_checkout,
                capture_output=True, text=True, timeout=30)
            if r.returncode != 0:
                self.skipTest(f"git worktree add failed: {r.stderr}")
            got = hostapi.git_worktree_main_root(wt_dir)
            self.assertIsNotNone(got)
            self.assertEqual(os.path.realpath(got), os.path.realpath(main_checkout))

    def test_ordinary_repo_returns_none(self):
        # An ordinary checkout's `.git` is a DIRECTORY -- nothing to escalate.
        with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as top:
            repo = os.path.join(top, "repo")
            if not _init_repo(repo):
                self.skipTest("git init failed")
            self.assertIsNone(hostapi.git_worktree_main_root(repo))

    def test_non_repo_path_returns_none(self):
        with tempfile.TemporaryDirectory() as plain:
            self.assertIsNone(hostapi.git_worktree_main_root(plain))

    def test_submodule_style_gitfile_is_not_mistaken_for_a_worktree(self):
        # A submodule's `.git` is ALSO a FILE, but its `gitdir:` pointer names
        # `.git/modules/<name>`, never `.git/worktrees/<name>` -- must return
        # None, not climb to some unrelated "main root".
        with tempfile.TemporaryDirectory() as top:
            fake_submodule = os.path.join(top, "sub")
            os.makedirs(fake_submodule)
            with open(os.path.join(fake_submodule, ".git"), "w", encoding="utf-8") as f:
                f.write(f"gitdir: {top}/.git/modules/sub\n")
            self.assertIsNone(hostapi.git_worktree_main_root(fake_submodule))


class MarkerRootTests(unittest.TestCase):
    """hostapi.Host.marker_root — #604: agrees with project_root() everywhere
    EXCEPT a linked worktree with no CLAUDE_PROJECT_DIR, where it climbs to
    the main checkout instead of the worktree's own (gitignored-markers)
    checkout — the root security-pass.py/migration-pass.py now write to, and
    the H-09b/H-10b/H-14 guard now agrees with (see test_security_pass.py /
    test_repo_resolution.py for the end-to-end proof)."""

    def setUp(self):
        self.host = hostapi.Host()
        self._env = os.environ.get("CLAUDE_PROJECT_DIR")
        self._cwd = os.getcwd()
        if not _git_available():
            self.skipTest("git unavailable")

    def tearDown(self):
        os.chdir(self._cwd)
        if self._env is None:
            os.environ.pop("CLAUDE_PROJECT_DIR", None)
        else:
            os.environ["CLAUDE_PROJECT_DIR"] = self._env

    def test_ordinary_repo_matches_project_root(self):
        os.environ.pop("CLAUDE_PROJECT_DIR", None)
        with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as top:
            repo = os.path.join(top, "repo")
            if not _init_repo(repo):
                self.skipTest("git init failed")
            os.chdir(repo)
            self.assertEqual(
                os.path.realpath(self.host.marker_root()),
                os.path.realpath(self.host.project_root()))

    def test_claude_project_dir_still_wins_first(self):
        # Byte-identity with project_root()'s own leg 1 -- marker_root() must
        # not invent a second, different env-var precedence.
        with tempfile.TemporaryDirectory() as env_dir:
            os.environ["CLAUDE_PROJECT_DIR"] = env_dir
            self.assertEqual(os.path.realpath(self.host.marker_root()),
                             os.path.realpath(env_dir))

    def test_linked_worktree_cwd_escalates_to_main_checkout_when_env_unset(self):
        # The #604 case: security-pass.py invoked bare via Bash (no
        # CLAUDE_PROJECT_DIR in that shell), cwd inside a linked worktree --
        # marker_root() must name the MAIN checkout, not the worktree.
        os.environ.pop("CLAUDE_PROJECT_DIR", None)
        with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as top:
            main_checkout = os.path.join(top, "main-checkout")
            if not _init_repo(main_checkout, branch="main"):
                self.skipTest("git init/commit failed")
            wt_dir = os.path.join(top, "linked-worktree")
            r = subprocess.run(
                ["git", "worktree", "add", "-b", "feat/y", wt_dir], cwd=main_checkout,
                capture_output=True, text=True, timeout=30)
            if r.returncode != 0:
                self.skipTest(f"git worktree add failed: {r.stderr}")
            os.chdir(wt_dir)
            # project_root() stays worktree-local (the diff-scan contract) --
            # marker_root() alone climbs.
            self.assertEqual(os.path.realpath(self.host.project_root()),
                             os.path.realpath(wt_dir))
            self.assertEqual(os.path.realpath(self.host.marker_root()),
                             os.path.realpath(main_checkout))


if __name__ == "__main__":
    unittest.main()
