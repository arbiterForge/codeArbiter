#!/usr/bin/env python3
"""Regression tests for sharing one guarded child-suite observation."""
from __future__ import annotations

import importlib.util
import io
from pathlib import Path
import subprocess
import sys
import unittest
from unittest import mock


HERMETICITY_PATH = Path(__file__).with_name("test_suite_hermeticity.py")


def load_guard():
    """Load a fresh hermeticity module so class fixtures cannot leak between runs."""
    spec = importlib.util.spec_from_file_location(
        "hermeticity_under_test", HERMETICITY_PATH
    )
    if spec is None or spec.loader is None:
        raise RuntimeError(f"Could not load hermeticity guard from {HERMETICITY_PATH}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class SingleObservationTests(unittest.TestCase):
    def exercise(self, case: str = "good", repeat: int = 1):
        module = load_guard()
        calls = []
        results = []

        def child(command, home):
            calls.append(command)
            if case == "write":
                (home / "unexpected").write_text("bad", encoding="utf-8")
            if case == "modify":
                (home / ".claude/settings.json").write_text("{}", encoding="utf-8")
            if case == "delete":
                (home / ".claude/settings.json").unlink()
            if case == "directory":
                (home / "unexpected").mkdir()
            if case == "timeout":
                raise subprocess.TimeoutExpired(command, 900)
            warning = "ResourceWarning: seeded leak\n" if case == "warning" else ""
            return subprocess.CompletedProcess(
                command,
                1 if case == "failure" else 0,
                "",
                warning,
            )

        with mock.patch.object(module, "run_suite", side_effect=child):
            for _ in range(repeat):
                suite = unittest.defaultTestLoader.loadTestsFromTestCase(
                    module.TestTheSuiteLeaksNoHandlesOrProcesses
                )
                results.append(unittest.TextTestRunner(stream=io.StringIO()).run(suite))
        return calls, results

    def assert_bad_observation(self, case: str):
        calls, results = self.exercise(case)
        self.assertEqual(len(calls), 1)
        self.assertFalse(results[0].wasSuccessful())

    def test_two_assertions_share_one_execution(self):
        calls, results = self.exercise()
        self.assertEqual(len(calls), 1)
        self.assertEqual(results[0].testsRun, 2)
        self.assertTrue(results[0].wasSuccessful())

    def test_warning_configuration_and_discovery_are_explicit(self):
        calls, _ = self.exercise()
        self.assertEqual(
            calls[0],
            [
                sys.executable,
                "-W",
                "always::ResourceWarning",
                "-m",
                "unittest",
                "discover",
                "-s",
                "plugins/ca/hooks/tests",
                "-p",
                "test_*.py",
                "-t",
                ".",
            ],
        )

    def test_new_suite_run_does_not_reuse_old_result(self):
        calls, results = self.exercise(repeat=2)
        self.assertEqual(len(calls), 2)
        self.assertTrue(all(result.wasSuccessful() for result in results))

    def test_home_file_creation_fails(self):
        self.assert_bad_observation("write")

    def test_home_file_modification_fails(self):
        self.assert_bad_observation("modify")

    def test_home_file_deletion_fails(self):
        self.assert_bad_observation("delete")

    def test_empty_directory_creation_fails(self):
        self.assert_bad_observation("directory")

    def test_resource_warning_fails(self):
        self.assert_bad_observation("warning")

    def test_child_failure_fails(self):
        self.assert_bad_observation("failure")

    def test_child_timeout_fails(self):
        self.assert_bad_observation("timeout")


if __name__ == "__main__":
    unittest.main(verbosity=2)
