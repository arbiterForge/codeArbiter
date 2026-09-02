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
from unittest import mock

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

    def test_ambient_repository_selectors_cannot_rebind_toplevel(self):
        with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as top:
            target = os.path.join(top, "target")
            foreign = os.path.join(top, "foreign")
            os.makedirs(target)
            os.makedirs(foreign)
            for root in (target, foreign):
                initialized = subprocess.run(
                    ["git", "init", "-q", "-b", "main"], cwd=root,
                    capture_output=True, text=True, timeout=30)
                self.assertEqual(initialized.returncode, 0, initialized.stderr)
            hostile = {
                "GIT_DIR": os.path.join(foreign, ".git"),
                "GIT_WORK_TREE": foreign,
                "GIT_COMMON_DIR": os.path.join(foreign, ".git"),
                "GIT_CONFIG_COUNT": "1",
                "GIT_CONFIG_KEY_0": "safe.directory",
                "GIT_CONFIG_VALUE_0": "*",
            }

            with mock.patch.dict(os.environ, hostile, clear=False):
                got = hostapi.git_toplevel(target)

            self.assertEqual(os.path.realpath(got), os.path.realpath(target))


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
                       capture_output=True, text=True, timeout=30)
    if r.returncode != 0:
        return False
    for args in (["config", "user.email", "h@example.com"],
                 ["config", "user.name", "h"]):
        configured = subprocess.run(
            ["git"] + args, cwd=root, capture_output=True, text=True, timeout=30)
        if configured.returncode != 0:
            raise RuntimeError(
                f"git {' '.join(args)} failed: {configured.stderr or configured.stdout}")
    with open(os.path.join(root, "seed.txt"), "w", encoding="utf-8") as f:
        f.write("seed\n")
    context_dir = os.path.join(root, ".codearbiter")
    os.makedirs(context_dir)
    with open(os.path.join(context_dir, "CONTEXT.md"), "w", encoding="utf-8") as f:
        f.write("---\narbiter: enabled\nstage: 2\n---\n<!--INITIALIZED-->\n")
    staged = subprocess.run(
        ["git", "add", "seed.txt", ".codearbiter/CONTEXT.md"], cwd=root,
        capture_output=True, text=True, timeout=30)
    if staged.returncode != 0:
        raise RuntimeError(f"git add failed: {staged.stderr or staged.stdout}")
    committed = subprocess.run(
        ["git", "-c", "core.hooksPath=", "-c", "commit.gpgSign=false",
         "commit", "-q", "-m", "seed"], cwd=root,
        capture_output=True, text=True, timeout=30)
    if committed.returncode != 0:
        raise RuntimeError(
            f"hermetic git seed commit failed: {committed.stderr or committed.stdout}")
    return True


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

    def test_relative_linked_worktree_pointer_resolves_to_main_checkout(self):
        with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as top:
            main_checkout = os.path.join(top, "main-checkout")
            if not _init_repo(main_checkout, branch="main"):
                self.skipTest("git init/commit failed")
            wt_dir = os.path.join(top, "linked-worktree")
            r = subprocess.run(
                ["git", "worktree", "add", "--relative-paths", "-b", "feat/relative", wt_dir],
                cwd=main_checkout, capture_output=True, text=True, timeout=30)
            if r.returncode != 0:
                self.skipTest(f"git worktree relative paths unavailable: {r.stderr}")

            with open(os.path.join(wt_dir, ".git"), encoding="utf-8") as f:
                self.assertFalse(os.path.isabs(f.read().split(":", 1)[1].strip()))
            got = hostapi.git_worktree_main_root(wt_dir)
            self.assertIsNotNone(got)
            self.assertEqual(os.path.realpath(got), os.path.realpath(main_checkout))
            with mock.patch.dict(os.environ, {"CLAUDE_PROJECT_DIR": wt_dir}):
                marker_root = hostapi.Host().marker_root()
            self.assertEqual(os.path.realpath(marker_root), os.path.realpath(main_checkout))

    def test_enabled_context_may_differ_between_main_and_linked_branches(self):
        with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as top:
            main_checkout = os.path.join(top, "main-checkout")
            self.assertTrue(_init_repo(main_checkout, branch="main"))
            linked = os.path.join(top, "linked-worktree")
            added = subprocess.run(
                ["git", "worktree", "add", "-q", "-b", "feat/context", linked],
                cwd=main_checkout, capture_output=True, text=True, timeout=30)
            self.assertEqual(added.returncode, 0, added.stderr)
            with open(os.path.join(linked, ".codearbiter", "CONTEXT.md"),
                      "w", encoding="utf-8") as f:
                f.write("---\nstage: 3\narbiter: enabled\n---\nlinked branch body\n")

            got = hostapi.git_worktree_main_root(linked)
            self.assertIsNotNone(got)
            self.assertEqual(os.path.realpath(got), os.path.realpath(main_checkout))

    def test_utf8_bom_enabled_context_keeps_default_layout_escalation(self):
        with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as top:
            main_checkout = os.path.join(top, "main-checkout")
            self.assertTrue(_init_repo(main_checkout, branch="main"))
            linked = os.path.join(top, "linked-worktree")
            added = subprocess.run(
                ["git", "worktree", "add", "-q", "-b", "feat/bom", linked],
                cwd=main_checkout, capture_output=True, text=True, timeout=30)
            self.assertEqual(added.returncode, 0, added.stderr)
            bom_context = "---\narbiter: enabled\nstage: 2\n---\nBOM context\n"
            for checkout in (main_checkout, linked):
                with open(os.path.join(checkout, ".codearbiter", "CONTEXT.md"),
                          "w", encoding="utf-8-sig") as f:
                    f.write(bom_context)

            got = hostapi.git_worktree_main_root(linked)
            self.assertIsNotNone(got)
            self.assertEqual(os.path.realpath(got), os.path.realpath(main_checkout))

    @unittest.skipIf(os.name == "nt", "ordinary symlink creation is not portable on Windows")
    def test_linked_worktree_symlink_alias_uses_gits_confirmed_common_dir(self):
        with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as top:
            main_checkout = os.path.join(top, "main-checkout")
            if not _init_repo(main_checkout, branch="main"):
                self.skipTest("git init/commit failed")
            wt_dir = os.path.join(top, "linked-worktree")
            r = subprocess.run(
                ["git", "worktree", "add", "-b", "feat/alias", wt_dir],
                cwd=main_checkout, capture_output=True, text=True, timeout=30)
            if r.returncode != 0:
                self.skipTest(f"git worktree add failed: {r.stderr}")
            alias = os.path.join(top, "linked-alias")
            os.symlink(wt_dir, alias, target_is_directory=True)

            got = hostapi.git_worktree_main_root(alias)
            self.assertIsNotNone(got)
            self.assertEqual(os.path.realpath(got), os.path.realpath(main_checkout))

    def test_ambient_git_repository_selectors_cannot_rebind_marker_root(self):
        with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as top:
            target_main = os.path.join(top, "target-main")
            foreign_main = os.path.join(top, "foreign-main")
            self.assertTrue(_init_repo(target_main, branch="main"))
            self.assertTrue(_init_repo(foreign_main, branch="main"))
            target_linked = os.path.join(top, "target-linked")
            foreign_linked = os.path.join(top, "foreign-linked")
            for main, linked, branch in (
                    (target_main, target_linked, "feat/target"),
                    (foreign_main, foreign_linked, "feat/foreign")):
                r = subprocess.run(
                    ["git", "worktree", "add", "-q", "-b", branch, linked],
                    cwd=main, capture_output=True, text=True, timeout=30)
                self.assertEqual(r.returncode, 0, r.stderr or r.stdout)
            foreign_admin = subprocess.run(
                ["git", "-C", foreign_linked, "rev-parse", "--path-format=absolute",
                 "--git-dir"], capture_output=True, text=True, timeout=30, check=True,
            ).stdout.strip()
            hostile_env = {
                "GIT_DIR": foreign_admin,
                "GIT_WORK_TREE": foreign_linked,
                "GIT_COMMON_DIR": os.path.join(foreign_main, ".git"),
                "GIT_CONFIG_COUNT": "1",
                "GIT_CONFIG_KEY_0": "core.worktree",
                "GIT_CONFIG_VALUE_0": foreign_linked,
            }

            with mock.patch.dict(os.environ, hostile_env, clear=False):
                sanitized = hostapi._root_bound_git_env()
                got = hostapi.git_worktree_main_root(target_linked)

            for name in ("GIT_DIR", "GIT_WORK_TREE", "GIT_COMMON_DIR"):
                self.assertNotIn(name, sanitized)
            for name in ("GIT_CONFIG_COUNT", "GIT_CONFIG_KEY_0", "GIT_CONFIG_VALUE_0"):
                self.assertEqual(sanitized.get(name), hostile_env[name])
            self.assertIsNotNone(got)
            self.assertEqual(os.path.realpath(got), os.path.realpath(target_main))

    def test_separate_git_dir_named_dot_git_does_not_impersonate_default_layout(self):
        with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as top:
            primary = os.path.join(top, "primary")
            separate_git_dir = os.path.join(top, "storage", ".git")
            linked = os.path.join(top, "linked")
            os.makedirs(os.path.dirname(separate_git_dir))
            initialized = subprocess.run(
                ["git", "init", "-q", "-b", "main", "--separate-git-dir",
                 separate_git_dir, primary],
                capture_output=True, text=True, timeout=30)
            self.assertEqual(initialized.returncode, 0, initialized.stderr)
            for args in (["config", "user.email", "h@example.com"],
                         ["config", "user.name", "h"]):
                configured = subprocess.run(
                    ["git", "-C", primary] + args,
                    capture_output=True, text=True, timeout=30)
                self.assertEqual(configured.returncode, 0, configured.stderr)
            context_dir = os.path.join(primary, ".codearbiter")
            os.makedirs(context_dir)
            with open(os.path.join(context_dir, "CONTEXT.md"), "w", encoding="utf-8") as f:
                f.write("---\narbiter: enabled\nstage: 2\n---\n<!--INITIALIZED-->\n")
            staged = subprocess.run(
                ["git", "-C", primary, "add", ".codearbiter/CONTEXT.md"],
                capture_output=True, text=True, timeout=30)
            self.assertEqual(staged.returncode, 0, staged.stderr)
            seeded = subprocess.run(
                ["git", "-C", primary, "-c", "core.hooksPath=", "-c",
                 "commit.gpgSign=false", "commit", "--allow-empty", "-q", "-m", "seed"],
                capture_output=True, text=True, timeout=30)
            self.assertEqual(seeded.returncode, 0, seeded.stderr)
            added = subprocess.run(
                ["git", "-C", primary, "worktree", "add", "-q", "-b",
                 "feat/separate", linked],
                capture_output=True, text=True, timeout=30)
            self.assertEqual(added.returncode, 0, added.stderr)
            actual = subprocess.run(
                ["git", "-C", linked, "rev-parse", "--show-toplevel"],
                capture_output=True, text=True, timeout=30)
            self.assertEqual(actual.returncode, 0, actual.stderr)

            self.assertIsNone(hostapi.git_worktree_main_root(linked))
            storage_context = os.path.join(os.path.dirname(separate_git_dir), ".codearbiter")
            os.makedirs(storage_context)
            with open(os.path.join(storage_context, "CONTEXT.md"), "w", encoding="utf-8") as f:
                f.write("---\narbiter: disabled\n---\n")
            self.assertIsNone(hostapi.git_worktree_main_root(linked))

    def test_relative_pointer_requires_the_referenced_worktree_admin_dir(self):
        with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as top:
            main_checkout = os.path.join(top, "main-checkout")
            linked = os.path.join(top, "linked-worktree")
            os.makedirs(os.path.join(main_checkout, ".git"))
            os.makedirs(linked)
            with open(os.path.join(linked, ".git"), "w", encoding="utf-8") as f:
                f.write("gitdir: ../main-checkout/.git/worktrees/invented\n")

            self.assertIsNone(hostapi.git_worktree_main_root(linked))

    def test_relative_pointer_requires_admin_backpointer_to_this_checkout(self):
        with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as top:
            main_checkout = os.path.join(top, "main-checkout")
            linked = os.path.join(top, "linked-worktree")
            other = os.path.join(top, "other-worktree")
            admin = os.path.join(main_checkout, ".git", "worktrees", "linked")
            os.makedirs(admin)
            os.makedirs(linked)
            os.makedirs(other)
            with open(os.path.join(linked, ".git"), "w", encoding="utf-8") as f:
                f.write("gitdir: ../main-checkout/.git/worktrees/linked\n")
            with open(os.path.join(admin, "gitdir"), "w", encoding="utf-8") as f:
                f.write(os.path.join(other, ".git") + "\n")

            self.assertIsNone(hostapi.git_worktree_main_root(linked))

    def test_shaped_decoy_admin_is_rejected_when_git_rejects_the_worktree(self):
        with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as top:
            main_checkout = os.path.join(top, "decoy-main")
            linked = os.path.join(top, "linked-worktree")
            admin = os.path.join(main_checkout, ".git", "worktrees", "slot")
            os.makedirs(admin)
            os.makedirs(linked)
            worktree_meta = os.path.join(linked, ".git")
            with open(worktree_meta, "w", encoding="utf-8") as f:
                f.write("gitdir: ../decoy-main/.git/worktrees/slot\n")
            with open(os.path.join(admin, "gitdir"), "w", encoding="utf-8") as f:
                f.write(worktree_meta + "\n")

            actual_git = subprocess.run(
                ["git", "-C", linked, "rev-parse", "--show-toplevel"],
                capture_output=True, text=True, timeout=30)
            self.assertNotEqual(actual_git.returncode, 0)
            self.assertIsNone(hostapi.git_worktree_main_root(linked))

    def test_drive_relative_pointer_is_not_treated_as_checkout_relative(self):
        with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as top:
            linked = os.path.join(top, "linked-worktree")
            os.makedirs(linked)
            raw_gitdir = "C:relative/.git/worktrees/invented"
            resolved = os.path.abspath(os.path.join(linked, raw_gitdir))
            marker = os.path.normpath(os.path.join(".git", "worktrees"))
            marker_at = os.path.normcase(resolved).find(os.path.normcase(marker))
            if marker_at != -1:
                os.makedirs(resolved[:marker_at + len(".git")], exist_ok=True)
            with open(os.path.join(linked, ".git"), "w", encoding="utf-8") as f:
                f.write(f"gitdir: {raw_gitdir}\n")

            self.assertIsNone(hostapi.git_worktree_main_root(linked))

    @unittest.skipIf(os.name == "nt", "backslash is a native separator on Windows")
    def test_foreign_relative_backslashes_are_not_translated_on_posix(self):
        with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as top:
            decoy = os.path.join(top, "decoy")
            linked = os.path.join(top, "linked-worktree")
            os.makedirs(os.path.join(decoy, ".git"))
            os.makedirs(linked)
            with open(os.path.join(linked, ".git"), "w", encoding="utf-8") as f:
                f.write("gitdir: ..\\decoy\\.git\\worktrees\\invented\n")

            self.assertIsNone(hostapi.git_worktree_main_root(linked))

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

    @unittest.skipIf(os.name == "nt", "foreign Windows paths are native on Windows")
    def test_foreign_windows_gitdir_is_not_a_usable_posix_main_root(self):
        with tempfile.TemporaryDirectory() as top:
            linked = os.path.join(top, "linked")
            os.makedirs(linked)
            with open(os.path.join(linked, ".git"), "w", encoding="utf-8") as f:
                f.write(
                    "gitdir: C:/Users/operator/repo/.git/worktrees/linked\n")

            self.assertIsNone(hostapi.git_worktree_main_root(linked))

    @unittest.skipUnless(os.name == "nt", "foreign POSIX paths are native on POSIX")
    def test_foreign_posix_gitdir_is_not_a_usable_windows_main_root(self):
        with tempfile.TemporaryDirectory() as top:
            linked = os.path.join(top, "linked")
            os.makedirs(linked)
            with open(os.path.join(linked, ".git"), "w", encoding="utf-8") as f:
                f.write("gitdir: /home/operator/repo/.git/worktrees/linked\n")

            self.assertIsNone(hostapi.git_worktree_main_root(linked))


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
