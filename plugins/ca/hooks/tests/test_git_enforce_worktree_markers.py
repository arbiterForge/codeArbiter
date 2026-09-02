"""Issue #695: git-enforce.py must resolve gate markers through marker_root
(escalating from a linked worktree to the main checkout).

When a developer or agent works in a linked git worktree, gate passes
(security-pass.py, migration-pass.py) write markers into the main repository's
`.codearbiter/.markers/` directory because `.codearbiter/.markers/` is gitignored.
git-enforce.py must read gate markers from `_marker_root(root)` so that pre-commit
validations in linked worktrees find the recorded gate passes.
"""
import os
import subprocess
import sys
import tempfile
import unittest
from unittest import mock

HOOKS = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, HOOKS)
import hostapi  # noqa: E402
import _hooklib  # noqa: E402

import importlib.util as _ilu


def _load_git_enforce():
    path = os.path.join(HOOKS, "git-enforce.py")
    spec = _ilu.spec_from_file_location("git_enforce_worktree_test", path)
    mod = _ilu.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


class GitEnforceWorktreeMarkerTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.mod = _load_git_enforce()


    def _linked_roots(self, temporary):
        main_root = os.path.join(temporary, "main")
        worktree_root = os.path.join(temporary, "linked")
        subprocess.run(["git", "init", "-q", "-b", "main", main_root], check=True, timeout=30)
        subprocess.run(["git", "-C", main_root, "config", "user.email", "test@example.com"],
                       check=True, timeout=30)
        subprocess.run(["git", "-C", main_root, "config", "user.name", "Test"],
                       check=True, timeout=30)
        with open(os.path.join(main_root, "seed.txt"), "w", encoding="utf-8") as handle:
            handle.write("seed\n")
        context_dir = os.path.join(main_root, ".codearbiter")
        os.makedirs(context_dir)
        with open(os.path.join(context_dir, "CONTEXT.md"), "w", encoding="utf-8") as handle:
            handle.write("---\narbiter: enabled\nstage: 2\n---\n<!--INITIALIZED-->\n")
        subprocess.run(
            ["git", "-C", main_root, "add", "seed.txt", ".codearbiter/CONTEXT.md"],
            check=True, timeout=30)
        subprocess.run(
            ["git", "-C", main_root, "-c", "core.hooksPath=",
             "-c", "commit.gpgSign=false", "commit", "-qm", "seed"],
            check=True, timeout=30)
        subprocess.run(
            ["git", "-C", main_root, "worktree", "add", "-q", "-b", "test-linked",
             worktree_root], check=True, timeout=30)
        return os.path.realpath(main_root).replace("\\", "/"), worktree_root

    def test_linked_root_fixture_canonicalizes_symlink_parent(self):
        with tempfile.TemporaryDirectory() as temporary:
            real_parent = os.path.join(temporary, "real-parent")
            alias_parent = os.path.join(temporary, "alias-parent")
            os.makedirs(real_parent)
            try:
                os.symlink(real_parent, alias_parent, target_is_directory=True)
            except (OSError, NotImplementedError) as error:
                self.skipTest(f"directory symlink unavailable: {error}")

            main_root, _worktree_root = self._linked_roots(alias_parent)

            expected = os.path.realpath(os.path.join(real_parent, "main")).replace("\\", "/")
            self.assertEqual(main_root, expected)

    def test_plain_repo_keeps_security_marker_under_operation_root(self):
        with tempfile.TemporaryDirectory() as plain_root:
            fake_added = ['const test_secret_token ' + '= "dummy_synthetic_testing_token";\n']
            digest = _hooklib.line_digest(fake_added[0])
            with mock.patch.object(self.mod, "current_branch", return_value="feature/test"), \
                 mock.patch.object(self.mod, "cached_added_lines", return_value=fake_added), \
                 mock.patch.object(self.mod, "cached_names", return_value=set()), \
                 mock.patch.object(self.mod, "marker_fresh", return_value=True) as mock_fresh, \
                 mock.patch.object(self.mod, "_marker_set", return_value={digest}) as mock_set:
                self.mod.pre_commit(plain_root)

            expected_marker = os.path.join(plain_root, ".codearbiter", ".markers", "security-gate-passed")
            mock_fresh.assert_called_once_with(expected_marker, _hooklib.MARKER_FRESHNESS_MINUTES)
            mock_set.assert_called_once_with(plain_root, "security-gate-passed")

    def test_plain_repo_keeps_migration_marker_and_file_reads_under_operation_root(self):
        with tempfile.TemporaryDirectory() as plain_root:
            migration_file = "migrations/0001_init.sql"
            file_content = "CREATE TABLE users (id INT PRIMARY KEY);\n"
            digest = _hooklib.content_digest(file_content)
            with mock.patch.object(self.mod, "current_branch", return_value="feature/test") as mock_branch, \
                 mock.patch.object(self.mod, "cached_added_lines", return_value=[]) as mock_added, \
                 mock.patch.object(self.mod, "cached_names", return_value={migration_file}) as mock_names, \
                 mock.patch.object(self.mod, "is_migration_path", return_value=True) as mock_is_mig, \
                 mock.patch.object(self.mod, "read_worktree", return_value=file_content) as mock_read, \
                 mock.patch.object(self.mod, "_marker_set", return_value={digest}) as mock_set:
                self.mod.pre_commit(plain_root)

            mock_branch.assert_called_once_with(plain_root)
            mock_added.assert_called_once_with(plain_root)
            mock_names.assert_called_once_with(plain_root)
            mock_is_mig.assert_called_once_with(migration_file, plain_root)
            mock_read.assert_called_once_with(plain_root, migration_file)
            mock_set.assert_called_once_with(plain_root, "migration-gate-passed")

    def test_linked_detached_head_check_stays_under_operation_root(self):
        with tempfile.TemporaryDirectory() as temporary:
            _main_root, worktree_root = self._linked_roots(temporary)
            with mock.patch.object(self.mod, "current_branch", return_value="") as mock_branch, \
                 mock.patch.object(self.mod, "head_on_protected_tip", return_value=False) as mock_tip, \
                 mock.patch.object(self.mod, "cached_added_lines", return_value=[]) as mock_added, \
                 mock.patch.object(self.mod, "cached_names", return_value=set()) as mock_names:
                self.mod.pre_commit(worktree_root)

            mock_branch.assert_called_once_with(worktree_root)
            mock_tip.assert_called_once_with(worktree_root)
            mock_added.assert_called_once_with(worktree_root)
            mock_names.assert_called_once_with(worktree_root)

    def test_pre_commit_reads_security_marker_from_main_root_in_worktree(self):
        with tempfile.TemporaryDirectory() as temporary:
            main_root, worktree_root = self._linked_roots(temporary)
            fake_added = ['const test_secret_token ' + '= "dummy_synthetic_testing_token";\n']
            digest = _hooklib.line_digest(fake_added[0])

            with mock.patch.object(self.mod, "current_branch", return_value="feature/test") as mock_branch, \
                 mock.patch.object(self.mod, "cached_added_lines", return_value=fake_added) as mock_added, \
                 mock.patch.object(self.mod, "cached_names", return_value=set()) as mock_names, \
                 mock.patch.object(self.mod, "marker_fresh", return_value=True) as mock_fresh, \
                 mock.patch.object(self.mod, "_marker_set", return_value={digest}) as mock_set:
                self.mod.pre_commit(worktree_root)

            expected_marker = os.path.join(main_root, ".codearbiter", ".markers", "security-gate-passed")
            mock_branch.assert_called_once_with(worktree_root)
            mock_added.assert_called_once_with(worktree_root)
            mock_names.assert_called_once_with(worktree_root)
            mock_fresh.assert_called_once_with(expected_marker, _hooklib.MARKER_FRESHNESS_MINUTES)
            mock_set.assert_called_once_with(main_root, "security-gate-passed")

    def test_pre_commit_reads_migration_marker_from_main_root_in_worktree(self):
        with tempfile.TemporaryDirectory() as temporary:
            main_root, worktree_root = self._linked_roots(temporary)
            migration_file = "migrations/0001_init.sql"
            file_content = "CREATE TABLE users (id INT PRIMARY KEY);\n"
            mig_digest = _hooklib.content_digest(file_content)

            with mock.patch.object(self.mod, "current_branch", return_value="feature/test") as mock_branch, \
                 mock.patch.object(self.mod, "cached_added_lines", return_value=[]) as mock_added, \
                 mock.patch.object(self.mod, "cached_names", return_value={migration_file}) as mock_names, \
                 mock.patch.object(self.mod, "is_migration_path", return_value=True) as mock_is_mig, \
                 mock.patch.object(self.mod, "read_worktree", return_value=file_content) as mock_read, \
                 mock.patch.object(self.mod, "_marker_set", return_value={mig_digest}) as mock_set:
                self.mod.pre_commit(worktree_root)

            mock_branch.assert_called_once_with(worktree_root)
            mock_added.assert_called_once_with(worktree_root)
            mock_names.assert_called_once_with(worktree_root)
            mock_is_mig.assert_called_once_with(migration_file, worktree_root)
            mock_read.assert_called_once_with(worktree_root, migration_file)
            mock_set.assert_called_once_with(main_root, "migration-gate-passed")


if __name__ == "__main__":
    unittest.main()
