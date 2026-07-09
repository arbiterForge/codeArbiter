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


if __name__ == "__main__":
    unittest.main()
