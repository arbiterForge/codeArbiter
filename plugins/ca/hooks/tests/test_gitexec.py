"""Direct unit tests for _gitexec._trusted_environment_path (coverage-003)."""

import os
import stat
import sys
import tempfile
import unittest
from unittest import mock


HOOKS = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if HOOKS not in sys.path:
    sys.path.insert(0, HOOKS)

import _gitexec


ENV_NAME = "CODEARBITER_TEST_EXECUTABLE_PATH"


class TrustedEnvironmentPathTests(unittest.TestCase):
    def test_missing_variable_returns_none(self):
        with mock.patch.dict(os.environ, {}, clear=False):
            os.environ.pop(ENV_NAME, None)
            self.assertIsNone(_gitexec._trusted_environment_path(ENV_NAME))

    def test_empty_variable_returns_none(self):
        with mock.patch.dict(os.environ, {ENV_NAME: ""}):
            self.assertIsNone(_gitexec._trusted_environment_path(ENV_NAME))

    def test_valid_absolute_existing_executable_passes(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = os.path.join(tmp, "tool.exe")
            with open(path, "w", encoding="utf-8") as f:
                f.write("#!/bin/sh\n")
            os.chmod(path, os.stat(path).st_mode | stat.S_IEXEC)
            with mock.patch.dict(os.environ, {ENV_NAME: path}):
                result = _gitexec._trusted_environment_path(ENV_NAME)
            self.assertEqual(result, os.path.realpath(path))

    def test_relative_path_rejected(self):
        with mock.patch.dict(os.environ, {ENV_NAME: os.path.join("relative", "tool")}):
            with self.assertRaises(RuntimeError):
                _gitexec._trusted_environment_path(ENV_NAME)

    def test_nonexistent_absolute_path_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            missing = os.path.join(tmp, "does-not-exist")
            with mock.patch.dict(os.environ, {ENV_NAME: missing}):
                with self.assertRaises(RuntimeError):
                    _gitexec._trusted_environment_path(ENV_NAME)

    def test_directory_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            with mock.patch.dict(os.environ, {ENV_NAME: tmp}):
                with self.assertRaises(RuntimeError):
                    _gitexec._trusted_environment_path(ENV_NAME)

    def test_symlink_resolves_to_real_target(self):
        with tempfile.TemporaryDirectory() as tmp:
            target = os.path.join(tmp, "real-tool")
            with open(target, "w", encoding="utf-8") as f:
                f.write("#!/bin/sh\n")
            link = os.path.join(tmp, "linked-tool")
            try:
                os.symlink(target, link)
            except (OSError, NotImplementedError):
                self.skipTest("symlinks are not supported/permitted on this platform")
            with mock.patch.dict(os.environ, {ENV_NAME: link}):
                result = _gitexec._trusted_environment_path(ENV_NAME)
            self.assertEqual(result, os.path.realpath(target))

    def test_git_executable_falls_back_when_unset(self):
        with mock.patch.dict(os.environ, {}, clear=False):
            os.environ.pop(_gitexec.GIT_ENV, None)
            self.assertEqual(_gitexec.git_executable(), "git")


if __name__ == "__main__":
    unittest.main()
