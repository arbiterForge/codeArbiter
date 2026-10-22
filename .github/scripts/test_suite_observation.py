#!/usr/bin/env python3
"""Regression tests for the guarded per-module hook-suite observation."""
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


class PerModuleObservationTests(unittest.TestCase):
    def exercise(self, case: str = "good", repeat: int = 1):
        """Run the guard class with a stub child; `case` damages exactly one module."""
        module = load_guard()
        modules = module.hook_modules()
        self.assertGreater(len(modules), 1)
        target = modules[len(modules) // 2]
        calls = []
        results = []

        def child(command, home):
            calls.append(command)
            damaged = command[-1] == f"{target}.py"
            if damaged and case == "write":
                (home / "unexpected").write_text("bad", encoding="utf-8")
            if damaged and case == "modify":
                (home / ".claude/settings.json").write_text("{}", encoding="utf-8")
            if damaged and case == "delete":
                (home / ".claude/settings.json").unlink()
            if damaged and case == "directory":
                (home / "unexpected").mkdir()
            if damaged and case == "timeout":
                raise subprocess.TimeoutExpired(command, 900)
            warning = "ResourceWarning: seeded leak\n" if damaged and case == "warning" else ""
            ran = "Ran 0 tests in 0.000s\n" if damaged and case == "empty" else "Ran 2 tests in 0.010s\n"
            return subprocess.CompletedProcess(
                command, 1 if damaged and case == "failure" else 0, "", warning + ran,
            )

        with mock.patch.object(module, "run_suite", side_effect=child):
            for _ in range(repeat):
                suite = unittest.defaultTestLoader.loadTestsFromTestCase(
                    module.TestTheSuiteLeaksNoHandlesOrProcesses
                )
                results.append(unittest.TextTestRunner(stream=io.StringIO()).run(suite))
        return modules, calls, results

    def assert_bad_observation(self, case: str):
        modules, calls, results = self.exercise(case)
        self.assertEqual(len(calls), len(modules))
        self.assertFalse(results[0].wasSuccessful(), case)

    def test_each_module_runs_once_and_the_assertions_share_it(self):
        modules, calls, results = self.exercise()
        self.assertEqual(sorted(command[-1] for command in calls), sorted(f"{m}.py" for m in modules))
        self.assertEqual(results[0].testsRun, 3)
        self.assertTrue(results[0].wasSuccessful())

    def test_warning_configuration_and_discovery_are_explicit(self):
        modules, calls, _ = self.exercise()
        first = sorted(calls, key=lambda command: command[-1])[0]
        self.assertEqual(
            first,
            [
                sys.executable, "-W", "always::ResourceWarning", "-m", "unittest",
                "discover", "-s", "plugins/ca/hooks/tests", "-p", f"{sorted(modules)[0]}.py",
            ],
        )

    def test_new_suite_run_does_not_reuse_old_result(self):
        modules, calls, results = self.exercise(repeat=2)
        self.assertEqual(len(calls), 2 * len(modules))
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

    def test_module_that_runs_no_tests_fails(self):
        self.assert_bad_observation("empty")


if __name__ == "__main__":
    unittest.main(verbosity=2)
