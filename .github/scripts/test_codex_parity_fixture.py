#!/usr/bin/env python3
"""Unit tests for tools/codex-parity-fixture.py — the Codex/Claude live-parity
test-fixture scaffolder.

Run: python .github/scripts/test_codex_parity_fixture.py

Covers: successful fixture creation in normal and --bare modes (expected
files/commit present), rejection of an existing target path, and the
hardened non-zero-exit git-failure and filesystem-failure paths (FINDING 4).

Stdlib only.
"""
import contextlib
import importlib.util
import io
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

REPO_ROOT = Path(__file__).resolve().parents[2]
_TOOL = REPO_ROOT / "tools" / "codex-parity-fixture.py"

_spec = importlib.util.spec_from_file_location("codex_parity_fixture", _TOOL)
F = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(F)


def _run_main(argv):
    out, err = io.StringIO(), io.StringIO()
    with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
        rc = F.main(argv)
    return rc, out.getvalue(), err.getvalue()


def _git(args, cwd):
    return subprocess.run(["git"] + args, cwd=cwd, capture_output=True,
                          text=True, timeout=30)


class TestSuccessfulCreation(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()

    def tearDown(self):
        self._tmp.cleanup()

    def test_normal_mode_creates_expected_files_and_commit(self):
        target = os.path.join(self._tmp.name, "fixture")
        rc, out, err = _run_main([target])
        self.assertEqual(rc, 0, err)
        for rel in (".codearbiter/CONTEXT.md", ".codearbiter/overrides.log",
                    ".codearbiter/decisions/0001-sample-decision.md",
                    ".codearbiter/security-controls.md",
                    ".codearbiter/tech-stack.md", "src/hello.txt"):
            self.assertTrue(os.path.isfile(os.path.join(target, *rel.split("/"))),
                            rel)
        self.assertTrue(os.path.isdir(os.path.join(target, ".codearbiter", ".markers")))
        self.assertTrue(os.path.isdir(os.path.join(target, ".git")))
        log = _git(["log", "--oneline"], target)
        self.assertEqual(log.returncode, 0)
        self.assertIn("seed: codex/claude parity fixture", log.stdout)
        self.assertNotIn("(bare)", log.stdout)

    def test_bare_mode_creates_only_baseline_file(self):
        target = os.path.join(self._tmp.name, "bare-fixture")
        rc, out, err = _run_main([target, "--bare"])
        self.assertEqual(rc, 0, err)
        self.assertTrue(os.path.isfile(os.path.join(target, "src", "hello.txt")))
        self.assertFalse(os.path.isdir(os.path.join(target, ".codearbiter")))
        self.assertTrue(os.path.isdir(os.path.join(target, ".git")))
        log = _git(["log", "--oneline"], target)
        self.assertEqual(log.returncode, 0)
        self.assertIn("(bare)", log.stdout)


class TestExistingTargetRejected(unittest.TestCase):
    def test_refuses_to_clobber_existing_path(self):
        with tempfile.TemporaryDirectory() as tmp:
            target = os.path.join(tmp, "already-here")
            os.makedirs(target)
            rc, out, err = _run_main([target])
            self.assertNotEqual(rc, 0)
            self.assertIn("refusing to clobber", err)
            # Nothing was written into the existing (empty) dir.
            self.assertEqual(os.listdir(target), [])


class TestUsageErrors(unittest.TestCase):
    def test_no_args_is_a_clear_nonzero_error(self):
        rc, out, err = _run_main([])
        self.assertNotEqual(rc, 0)
        self.assertIn("usage", err)

    def test_too_many_args_is_a_clear_nonzero_error(self):
        rc, out, err = _run_main(["a", "b"])
        self.assertNotEqual(rc, 0)
        self.assertIn("usage", err)


class TestGitFailurePath(unittest.TestCase):
    """FINDING 4: every git subprocess call's return code must be checked —
    a git failure must exit non-zero with a clear stderr message, never
    silently continue as if the fixture were seeded."""

    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()

    def tearDown(self):
        self._tmp.cleanup()

    def _patched_run(self, fail_verb):
        real_run = F._run

        def fake_run(args, cwd):
            if fail_verb in args:
                class _Fail:
                    returncode = 1
                    stdout = ""
                    stderr = f"simulated failure for {' '.join(args)}\n"
                return _Fail()
            return real_run(args, cwd)
        return fake_run

    def test_git_init_failure_is_nonzero_with_clear_message(self):
        target = os.path.join(self._tmp.name, "init-fails")
        with mock.patch.object(F, "_run", side_effect=self._patched_run("init")):
            rc, out, err = _run_main([target])
        self.assertNotEqual(rc, 0)
        self.assertIn("git init failed", err)
        # Files were written (pre-git step), but the fixture is not
        # considered successfully seeded — the caller sees a hard failure.
        self.assertTrue(os.path.isfile(os.path.join(target, "src", "hello.txt")))

    def test_git_add_failure_is_nonzero_with_clear_message(self):
        target = os.path.join(self._tmp.name, "add-fails")
        with mock.patch.object(F, "_run", side_effect=self._patched_run("add")):
            rc, out, err = _run_main([target])
        self.assertNotEqual(rc, 0)
        self.assertIn("git add failed", err)

    def test_git_commit_failure_is_nonzero_with_clear_message(self):
        target = os.path.join(self._tmp.name, "commit-fails")
        with mock.patch.object(F, "_run", side_effect=self._patched_run("commit")):
            rc, out, err = _run_main([target])
        self.assertNotEqual(rc, 0)
        self.assertIn("git commit failed", err)


class TestFilesystemFailurePath(unittest.TestCase):
    """FINDING 4: fixture dir/file creation errors (e.g. permission denied)
    must produce a clean non-zero exit, not a raw traceback."""

    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()

    def tearDown(self):
        self._tmp.cleanup()

    def test_unwritable_target_parent_is_a_clean_nonzero_error(self):
        target = os.path.join(self._tmp.name, "unwritable-parent", "fixture")
        real_makedirs = os.makedirs

        def boom_makedirs(path, *a, **kw):
            if os.path.normpath(path) == os.path.normpath(target):
                raise OSError("simulated permission denied")
            return real_makedirs(path, *a, **kw)

        with mock.patch.object(os, "makedirs", side_effect=boom_makedirs):
            rc, out, err = _run_main([target])
        self.assertNotEqual(rc, 0)
        self.assertIn("failed to create fixture files", err)
        self.assertNotIn("Traceback", err)

    def test_unwritable_file_write_is_a_clean_nonzero_error(self):
        target = os.path.join(self._tmp.name, "unwritable-file")
        real_open = open

        def boom_open(path, mode="r", *a, **kw):
            if "w" in mode and os.path.basename(path) == "hello.txt":
                raise OSError("simulated write failure")
            return real_open(path, mode, *a, **kw)

        with mock.patch("builtins.open", side_effect=boom_open):
            rc, out, err = _run_main([target])
        self.assertNotEqual(rc, 0)
        self.assertIn("failed to create fixture files", err)
        self.assertNotIn("Traceback", err)


if __name__ == "__main__":
    unittest.main()
