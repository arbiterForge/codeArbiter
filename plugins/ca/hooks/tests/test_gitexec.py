"""Direct unit tests for _gitexec._trusted_environment_path (coverage-003)."""

import importlib.util
import os
from pathlib import Path
import stat
import subprocess
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
    def test_read_only_callers_preserve_protected_config_and_strip_repository_selectors(self):
        core = Path(HOOKS).parents[2] / "core" / "pysrc"
        callers = []
        for name in ("_contextmergelib", "_tribunalinventorylib"):
            spec = importlib.util.spec_from_file_location(name + "_config_test", core / (name + ".py"))
            module = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(module)
            callers.append((name, module._git))
        with tempfile.TemporaryDirectory() as temporary:
            fixture = Path(temporary)
            root = fixture / "repo"
            root.mkdir()
            task_home = fixture / "home"
            task_home.mkdir()
            (task_home / ".gitconfig").write_text("[safe]\n\tdirectory = *\n", encoding="utf-8")
            protected = fixture / "protected.gitconfig"
            protected.write_text("[safe]\n\tdirectory =\n", encoding="utf-8")
            env = {key: value for key, value in os.environ.items() if not key.startswith("GIT_")}
            env.update(HOME=str(task_home), USERPROFILE=str(task_home),
                       XDG_CONFIG_HOME=str(fixture / "xdg"),
                       GIT_CONFIG_SYSTEM=os.devnull, GIT_CONFIG_GLOBAL=os.devnull)
            subprocess.run([_gitexec.git_executable(), "init", "-q", str(root)],
                           env=env, capture_output=True, check=True, shell=False)
            selectors = {key: str(fixture / "foreign") for key in
                         ("GIT_DIR", "GIT_WORK_TREE", "GIT_COMMON_DIR", "GIT_INDEX_FILE",
                          "GIT_OBJECT_DIRECTORY", "GIT_ALTERNATE_OBJECT_DIRECTORIES")}
            configurations = {
                "global": {"GIT_CONFIG_GLOBAL": str(protected), "GIT_CONFIG_NOSYSTEM": "1"},
                "system": {"GIT_CONFIG_SYSTEM": str(protected)},
                "command": {"GIT_CONFIG_COUNT": "1", "GIT_CONFIG_KEY_0": "safe.directory",
                            "GIT_CONFIG_VALUE_0": ""},
            }
            for source, configuration in configurations.items():
                with mock.patch.dict(os.environ, {**env, **configuration, **selectors}, clear=True):
                    direct = subprocess.run(
                        [_gitexec.git_executable(), "config", "--get-all", "safe.directory"],
                        cwd=root, env=_gitexec.root_bound_git_env(), capture_output=True,
                        check=True, shell=False)
                    self.assertEqual(direct.stdout, b"\n")
                    for name, caller in callers:
                        with self.subTest(source=source, caller=name):
                            actual_root = caller(root, "rev-parse", "--show-toplevel")
                            self.assertEqual(Path(actual_root.decode().strip()).resolve(), root.resolve())
                            self.assertEqual(caller(root, "config", "--get-all", "safe.directory"),
                                             direct.stdout)

    def test_root_bound_git_env_preserves_command_scope_safe_directory_config(self):
        command_scope_config = {
            "GIT_CONFIG_COUNT": "1",
            "GIT_CONFIG_KEY_0": "safe.directory",
            "GIT_CONFIG_VALUE_0": "C:/governed/repository",
        }
        hostile_selectors = {
            "GIT_DIR": "C:/foreign/.git",
            "GIT_WORK_TREE": "C:/foreign",
            "GIT_COMMON_DIR": "C:/foreign/.git",
        }

        with mock.patch.dict(
                os.environ, {**command_scope_config, **hostile_selectors}, clear=False):
            sanitized = _gitexec.root_bound_git_env()

        for name in hostile_selectors:
            self.assertNotIn(name, sanitized)
        for name, value in command_scope_config.items():
            self.assertEqual(sanitized.get(name), value)

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
