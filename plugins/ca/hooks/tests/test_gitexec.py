"""Direct unit tests for _gitexec._trusted_environment_path (coverage-003)."""

import importlib.util
import hashlib
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

    def test_root_bound_git_env_can_preserve_only_the_active_index(self):
        selectors = {"GIT_INDEX_FILE": "C:/repo/.git/alternate-index",
                     "GIT_DIR": "C:/foreign/.git", "GIT_WORK_TREE": "C:/foreign"}
        with mock.patch.dict(os.environ, selectors, clear=False):
            sanitized = _gitexec.root_bound_git_env(preserve_index=True)
        self.assertEqual(sanitized.get("GIT_INDEX_FILE"), selectors["GIT_INDEX_FILE"])
        self.assertNotIn("GIT_DIR", sanitized)
        self.assertNotIn("GIT_WORK_TREE", sanitized)

    def test_read_index_text_refuses_oversize_before_reading_blob(self):
        oid = b"1" * 40
        indexed = subprocess.CompletedProcess(
            [], 0, b"100644 " + oid + b" 0\tmigrations/large.sql\0", b"")
        sized = subprocess.CompletedProcess([], 0, b"1000001\n", b"")
        with mock.patch.object(_gitexec.subprocess, "run",
                               side_effect=[indexed, sized]) as run:
            actual = _gitexec.read_index_text("C:/repo", "migrations/large.sql")
        self.assertIsNone(actual)
        self.assertEqual(run.call_count, 2)
        self.assertIn("-s", run.call_args_list[1].args[0])

    def test_read_index_blob_identity_refuses_oversize_before_streaming_blob(self):
        oid = b"3" * 40
        indexed = subprocess.CompletedProcess(
            [], 0, b"100644 " + oid + b" 0\tassets/large.bin\0", b"")
        sized = subprocess.CompletedProcess([], 0, b"5\n", b"")
        with (mock.patch.object(_gitexec.subprocess, "run",
                               side_effect=[indexed, sized]) as run,
              mock.patch.object(_gitexec.subprocess, "Popen") as popen):
            actual = _gitexec.read_index_blob_identity(
                "C:/repo", "assets/large.bin", max_bytes=4)
        self.assertIsNone(actual)
        self.assertEqual(run.call_count, 2)
        popen.assert_not_called()

    def test_blob_sha256_enforces_cat_file_deadline(self):
        sized = subprocess.CompletedProcess([], 0, b"4\n", b"")
        with mock.patch.object(
                _gitexec.subprocess, "run",
                side_effect=[sized, subprocess.TimeoutExpired("git cat-file", 10)]) as run:
            actual = _gitexec._blob_sha256(
                "C:/repo", "4" * 40, 100, _gitexec.root_bound_git_env())
        self.assertIsNone(actual)
        self.assertEqual(run.call_count, 2)

    def test_binary_candidate_refuses_more_than_32_staged_files(self):
        paths = [f"assets/{index:02d}.bin" for index in range(33)]
        numstat = subprocess.CompletedProcess(
            [], 0, b"".join(b"-\t-\t" + path.encode() + b"\0" for path in paths), b"")
        with (mock.patch.object(_gitexec.subprocess, "run", return_value=numstat),
              mock.patch.object(_gitexec, "staged_changes",
                                return_value={path: "A" for path in paths}),
              mock.patch.object(_gitexec, "_index_blob_inventory") as inventory):
            actual = _gitexec.binary_candidate_binding("C:/repo")
        self.assertIsNone(actual)
        inventory.assert_not_called()

    def test_batch_blob_digests_enforces_file_and_aggregate_byte_limits(self):
        one = "1" * 40
        oversized = subprocess.CompletedProcess(
            [], 0,
            f"{one} blob {_gitexec.MAX_SECURITY_BINARY_BYTES + 1}\n".encode(), b"")
        with mock.patch.object(_gitexec.subprocess, "run", return_value=oversized) as run:
            self.assertIsNone(_gitexec._batch_blob_digests("C:/repo", [one], {}))
        self.assertEqual(run.call_count, 1)

        oids = [str(index) * 40 for index in (1, 2, 3)]
        size = _gitexec.MAX_SECURITY_BINARY_TOTAL_BYTES // 3 + 1
        rows = b"".join(f"{oid} blob {size}\n".encode() for oid in oids)
        aggregate = subprocess.CompletedProcess([], 0, rows, b"")
        with mock.patch.object(_gitexec.subprocess, "run", return_value=aggregate) as run:
            self.assertIsNone(_gitexec._batch_blob_digests("C:/repo", oids, {}))
        self.assertEqual(run.call_count, 1)

    def test_batch_blob_digests_refuses_timeouts_and_malformed_output_in_both_phases(self):
        oid = "1" * 40
        checked = subprocess.CompletedProcess([], 0, f"{oid} blob 4\n".encode(), b"")
        malformed_check = subprocess.CompletedProcess([], 0, b"not-a-batch-check-row\n", b"")
        malformed_batch = subprocess.CompletedProcess([], 0, b"", b"")
        scenarios = (
            [subprocess.TimeoutExpired("git cat-file --batch-check", 10)],
            [malformed_check],
            [checked, subprocess.TimeoutExpired("git cat-file --batch", 30)],
            [checked, malformed_batch],
        )
        for side_effect in scenarios:
            with self.subTest(side_effect=side_effect), mock.patch.object(
                    _gitexec.subprocess, "run", side_effect=side_effect):
                self.assertIsNone(_gitexec._batch_blob_digests(
                    "C:/repo", [oid], {}))

    def test_read_head_blob_digest_hashes_bounded_blob_bytes_with_sha256(self):
        oid = b"1" * 40
        content = b"CREATE TABLE exact_preimage (id int);\n"
        indexed = subprocess.CompletedProcess(
            [], 0, b"100644 blob " + oid + b"\tmigrations/exact.sql\0", b"")
        sized = subprocess.CompletedProcess([], 0, str(len(content)).encode() + b"\n", b"")
        blob = subprocess.CompletedProcess([], 0, content, b"")
        with mock.patch.object(_gitexec.subprocess, "run",
                               side_effect=[indexed, sized, blob]) as run:
            actual = _gitexec.read_head_blob_digest(
                "C:/repo", "migrations/exact.sql")
        self.assertEqual(actual, hashlib.sha256(content).hexdigest())
        self.assertNotEqual(actual, oid.decode())
        self.assertEqual(run.call_count, 3)

    def test_read_head_blob_digest_refuses_oversize_before_reading_blob(self):
        oid = b"2" * 40
        indexed = subprocess.CompletedProcess(
            [], 0, b"100644 blob " + oid + b"\tmigrations/large.sql\0", b"")
        sized = subprocess.CompletedProcess([], 0, b"1000001\n", b"")
        with mock.patch.object(_gitexec.subprocess, "run",
                               side_effect=[indexed, sized]) as run:
            actual = _gitexec.read_head_blob_digest(
                "C:/repo", "migrations/large.sql")
        self.assertIsNone(actual)
        self.assertEqual(run.call_count, 2)

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
