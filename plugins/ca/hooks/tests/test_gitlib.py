"""Filesystem-level tests for the shared git-context helper."""

import json
import os
import sys
import tempfile
import unittest
from unittest import mock


HOOKS = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if HOOKS not in sys.path:
    sys.path.insert(0, HOOKS)

import _gitlib
import statusline


class HeadBranchTests(unittest.TestCase):
    def test_normal_checkout_reads_branch_from_git_directory(self):
        with tempfile.TemporaryDirectory() as root:
            git_dir = os.path.join(root, ".git")
            os.makedirs(git_dir)
            with open(os.path.join(git_dir, "HEAD"), "w", encoding="utf-8") as f:
                f.write("ref: refs/heads/main\n")

            self.assertEqual(_gitlib.head_branch(root), "main")

    def test_linked_worktree_resolves_relative_gitdir_pointer(self):
        with tempfile.TemporaryDirectory() as parent:
            root = os.path.join(parent, "topic-worktree")
            git_dir = os.path.join(parent, "common", ".git", "worktrees", "topic")
            os.makedirs(root)
            os.makedirs(git_dir)
            relative_git_dir = os.path.relpath(git_dir, root)
            with open(os.path.join(root, ".git"), "w", encoding="utf-8") as f:
                f.write(f"gitdir: {relative_git_dir}\n")
            with open(os.path.join(git_dir, "HEAD"), "w", encoding="utf-8") as f:
                f.write("ref: refs/heads/feature/topic\n")
            with open(os.path.join(git_dir, "commondir"), "w", encoding="utf-8") as f:
                f.write("../..\n")

            self.assertEqual(_gitlib.head_branch(root), "feature/topic")

    def test_detached_head_returns_short_commit_id(self):
        with tempfile.TemporaryDirectory() as root:
            git_dir = os.path.join(root, ".git")
            os.makedirs(git_dir)
            with open(os.path.join(git_dir, "HEAD"), "w", encoding="utf-8") as f:
                f.write("0123456789abcdef0123456789abcdef01234567\n")

            self.assertEqual(_gitlib.head_branch(root), "0123456")

    def test_detached_head_accepts_full_sha1_or_sha256_only(self):
        for oid in ("a1" * 20, "b2" * 32):
            with self.subTest(length=len(oid)), tempfile.TemporaryDirectory() as root:
                git_dir = os.path.join(root, ".git")
                os.makedirs(git_dir)
                with open(os.path.join(git_dir, "HEAD"), "w", encoding="utf-8") as f:
                    f.write(oid + "\n")
                self.assertEqual(_gitlib.head_branch(root), oid[:7])

    def test_malformed_detached_head_fails_soft(self):
        for head in ("012345", "g" * 40, "0" * 39, "0" * 41):
            with self.subTest(head=head), tempfile.TemporaryDirectory() as root:
                git_dir = os.path.join(root, ".git")
                os.makedirs(git_dir)
                with open(os.path.join(git_dir, "HEAD"), "w", encoding="utf-8") as f:
                    f.write(head + "\n")
                self.assertIsNone(_gitlib.head_branch(root))

        with tempfile.TemporaryDirectory() as root:
            git_dir = os.path.join(root, ".git")
            os.makedirs(git_dir)
            with open(os.path.join(git_dir, "HEAD"), "wb") as f:
                f.write(b"\xff" * 40 + b"\n")
            self.assertIsNone(_gitlib.head_branch(root))

    def test_symbolic_ref_must_be_nonempty_and_safe(self):
        invalid = (
            "ref: \n",
            "ref: refs/heads/has space\n",
            "ref: refs/heads/control\x01name\n",
            "ref: refs/heads/two..dots\n",
        )
        for head in invalid:
            with self.subTest(head=repr(head)), tempfile.TemporaryDirectory() as root:
                git_dir = os.path.join(root, ".git")
                os.makedirs(git_dir)
                with open(os.path.join(git_dir, "HEAD"), "w", encoding="utf-8") as f:
                    f.write(head)
                self.assertIsNone(_gitlib.head_branch(root))

    def test_gitdir_pointer_requires_space_after_colon(self):
        with tempfile.TemporaryDirectory() as parent:
            root = os.path.join(parent, "worktree")
            git_dir = os.path.join(parent, "metadata")
            os.makedirs(root)
            os.makedirs(git_dir)
            with open(os.path.join(git_dir, "HEAD"), "w", encoding="utf-8") as f:
                f.write("ref: refs/heads/must-not-resolve\n")
            with open(os.path.join(root, ".git"), "w", encoding="utf-8") as f:
                f.write(f"gitdir:{git_dir}\n")

            self.assertIsNone(_gitlib.head_branch(root))

    def test_linked_worktree_resolves_absolute_gitdir_pointer(self):
        with tempfile.TemporaryDirectory() as parent:
            root = os.path.join(parent, "worktree")
            git_dir = os.path.join(parent, "metadata")
            os.makedirs(root)
            os.makedirs(git_dir)
            with open(os.path.join(git_dir, "HEAD"), "w", encoding="utf-8") as f:
                f.write("ref: refs/heads/absolute-pointer\n")
            with open(os.path.join(root, ".git"), "w", encoding="utf-8") as f:
                f.write(f"gitdir: {git_dir}\n")

            self.assertEqual(_gitlib.head_branch(root), "absolute-pointer")

    def test_malformed_or_missing_git_metadata_fails_soft(self):
        cases = ("not a gitdir pointer\n", "gitdir:\n", "gitdir: missing\n")
        for contents in cases:
            with self.subTest(contents=contents), tempfile.TemporaryDirectory() as root:
                with open(os.path.join(root, ".git"), "w", encoding="utf-8") as f:
                    f.write(contents)
                self.assertIsNone(_gitlib.head_branch(root))

        with tempfile.TemporaryDirectory() as root:
            self.assertIsNone(_gitlib.head_branch(root))


class ProjectRootTests(unittest.TestCase):
    def test_linked_worktree_git_pointer_marks_project_root(self):
        with tempfile.TemporaryDirectory() as parent:
            root = os.path.join(parent, "worktree")
            nested = os.path.join(root, "src", "pkg")
            os.makedirs(nested)
            with open(os.path.join(root, ".git"), "w", encoding="utf-8") as f:
                f.write("gitdir: ../common/.git/worktrees/topic\n")

            self.assertEqual(_gitlib.project_root({"cwd": nested}), root)


class GitDirtyTests(unittest.TestCase):
    def test_slow_git_is_bounded_by_explicit_latency_budget(self):
        timed_out = _gitlib.subprocess.TimeoutExpired(
            ["git", "status"], _gitlib.DIRTY_CHECK_TIMEOUT_SECONDS)
        with mock.patch.object(
                _gitlib.subprocess, "run", side_effect=timed_out) as run:
            self.assertFalse(_gitlib.git_dirty("repo"))

        self.assertEqual(run.call_args.kwargs["timeout"],
                         _gitlib.DIRTY_CHECK_TIMEOUT_SECONDS)
        self.assertLessEqual(_gitlib.DIRTY_CHECK_TIMEOUT_SECONDS, 0.1)

    def test_git_failure_fails_soft_even_if_stdout_is_present(self):
        failed = _gitlib.subprocess.CompletedProcess(
            ["git", "status"], returncode=128, stdout="fatal output\n", stderr="")
        with mock.patch.object(_gitlib.subprocess, "run", return_value=failed):
            self.assertFalse(_gitlib.git_dirty("repo"))

    def test_tracked_and_untracked_changes_remain_dirty(self):
        with tempfile.TemporaryDirectory() as root:
            subprocess = _gitlib.subprocess
            subprocess.run(["git", "init", "-q", root], check=True)
            tracked = os.path.join(root, "tracked.txt")
            with open(tracked, "w", encoding="utf-8") as f:
                f.write("initial\n")
            subprocess.run(["git", "-C", root, "add", "tracked.txt"], check=True)
            subprocess.run(
                ["git", "-C", root, "-c", "user.name=Test", "-c",
                 "user.email=test@example.invalid", "commit", "-qm", "initial"],
                check=True)

            # This test exercises dirty-state semantics with a real repository.
            # The production budget is covered separately above and is too tight
            # to serve as an integration-test deadline on a contended CI runner.
            with mock.patch.object(
                    _gitlib, "DIRTY_CHECK_TIMEOUT_SECONDS", 5.0):
                with open(tracked, "a", encoding="utf-8") as f:
                    f.write("changed\n")
                self.assertTrue(_gitlib.git_dirty(root))

                subprocess.run(
                    ["git", "-C", root, "restore", "tracked.txt"], check=True)
                with open(
                        os.path.join(root, "untracked.txt"),
                        "w", encoding="utf-8") as f:
                    f.write("new\n")
                self.assertTrue(_gitlib.git_dirty(root))


class StatuslineLinkedWorktreeTests(unittest.TestCase):
    def test_render_reports_linked_worktree_branch_instead_of_no_git(self):
        with tempfile.TemporaryDirectory() as parent:
            root = os.path.join(parent, "worktree")
            nested = os.path.join(root, "src")
            git_dir = os.path.join(parent, "common", ".git", "worktrees", "topic")
            os.makedirs(nested)
            os.makedirs(git_dir)
            with open(os.path.join(root, ".git"), "w", encoding="utf-8") as f:
                f.write(f"gitdir: {os.path.relpath(git_dir, root)}\n")
            with open(os.path.join(git_dir, "HEAD"), "w", encoding="utf-8") as f:
                f.write("ref: refs/heads/feature/rendered\n")

            rendered = statusline.render(json.dumps({"cwd": nested}))

            self.assertNotIn("no git", rendered)
            self.assertIn("feature/rendered", rendered)


if __name__ == "__main__":
    unittest.main()
