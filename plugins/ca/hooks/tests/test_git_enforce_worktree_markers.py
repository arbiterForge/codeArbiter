"""Issue #695: git-enforce.py must resolve gate markers through marker_root
(escalating from a linked worktree to the main checkout).

When a developer or agent works in a linked git worktree, gate passes
(security-pass.py, migration-pass.py) write markers into the main repository's
`.codearbiter/.markers/` directory because `.codearbiter/.markers/` is gitignored.
git-enforce.py must read gate markers from `_marker_root(root)` so that pre-commit
validations in linked worktrees find the recorded gate passes.
"""
import os
import sys
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

    def test_marker_root_plain_repo_returns_root(self):
        with mock.patch.object(self.mod, "git_worktree_main_root", return_value=None):
            self.assertEqual(self.mod._marker_root("/repo/plain"), "/repo/plain")

    def test_marker_root_linked_worktree_escalates_to_main_root(self):
        with mock.patch.object(self.mod, "git_worktree_main_root", return_value="/repo/main"):
            self.assertEqual(self.mod._marker_root("/repo/worktree-1"), "/repo/main")

    def test_pre_commit_reads_security_marker_from_main_root_in_worktree(self):
        worktree_root = "/repo/worktree-1"
        main_root = "/repo/main"

        fake_added = ['const test_secret_token = "dummy_synthetic_testing_token";\n']
        secret_line = fake_added[0]
        digest = _hooklib.line_digest(secret_line)

        with mock.patch.object(self.mod, "current_branch", return_value="feature/test"), \
             mock.patch.object(self.mod, "cached_added_lines", return_value=fake_added), \
             mock.patch.object(self.mod, "cached_names", return_value=set()), \
             mock.patch.object(self.mod, "git_worktree_main_root", return_value=main_root), \
             mock.patch.object(self.mod, "marker_fresh", return_value=True) as mock_fresh, \
             mock.patch.object(self.mod, "_marker_set", return_value={digest}) as mock_set:

            # Should not raise / block
            self.mod.pre_commit(worktree_root)

            # Assert marker_fresh was checked against main_root path
            expected_marker = os.path.join(main_root, ".codearbiter", ".markers", "security-gate-passed")
            mock_fresh.assert_called_once_with(expected_marker, _hooklib.MARKER_FRESHNESS_MINUTES)
            mock_set.assert_called_once_with(main_root, "security-gate-passed")

    def test_pre_commit_reads_migration_marker_from_main_root_in_worktree(self):
        worktree_root = "/repo/worktree-1"
        main_root = "/repo/main"

        migration_file = "migrations/0001_init.sql"
        file_content = "CREATE TABLE users (id INT PRIMARY KEY);\n"
        mig_digest = _hooklib.content_digest(file_content)

        with mock.patch.object(self.mod, "current_branch", return_value="feature/test"), \
             mock.patch.object(self.mod, "cached_added_lines", return_value=[]), \
             mock.patch.object(self.mod, "cached_names", return_value={migration_file}), \
             mock.patch.object(self.mod, "is_migration_path", return_value=True) as mock_is_mig, \
             mock.patch.object(self.mod, "read_worktree", return_value=file_content), \
             mock.patch.object(self.mod, "git_worktree_main_root", return_value=main_root), \
             mock.patch.object(self.mod, "_marker_set", return_value={mig_digest}) as mock_set:

            # Should not raise / block
            self.mod.pre_commit(worktree_root)

            # Assert is_migration_path used worktree_root
            mock_is_mig.assert_called_once_with(migration_file, worktree_root)
            # Assert marker set was loaded from main_root
            mock_set.assert_called_once_with(main_root, "migration-gate-passed")


if __name__ == "__main__":
    unittest.main()
