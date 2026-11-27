#!/usr/bin/env python3
"""Real-process contract for the concurrent unittest suite runner."""
from __future__ import annotations

import contextlib
import importlib.util
import io
import os
from pathlib import Path
import sys
import tempfile
import textwrap
import time
import unittest
from unittest import mock

HERE = Path(__file__).resolve().parent
SPEC = importlib.util.spec_from_file_location("run_concurrent_suites", HERE / "run_concurrent_suites.py")
runner = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(runner)

PASSING = """
import unittest
class T(unittest.TestCase):
    def test_one(self):
        pass
    def test_two(self):
        pass
if __name__ == "__main__":
    unittest.main()
"""
FAILING = """
import unittest
class T(unittest.TestCase):
    def test_one(self):
        self.fail("deliberate")
if __name__ == "__main__":
    unittest.main()
"""
EMPTY = """
import unittest
if __name__ == "__main__":
    unittest.main()
"""
SILENT = "print('no unittest here')\n"
SKIPPED = """
import unittest
class T(unittest.TestCase):
    def test_one(self):
        pass
    @unittest.skip("not here")
    def test_two(self):
        pass
if __name__ == "__main__":
    unittest.main()
"""
# Each suite publishes its own marker and then waits for its partner's. Only a
# concurrent run lets both finish before the short timeout.
RENDEZVOUS = """
import os, time, unittest
from pathlib import Path
class T(unittest.TestCase):
    def test_meets_partner(self):
        root = Path(os.environ["RENDEZVOUS_DIR"])
        (root / "{own}").write_text("here")
        deadline = time.monotonic() + 20
        while not (root / "{other}").exists():
            self.assertLess(time.monotonic(), deadline, "partner never ran concurrently")
            time.sleep(0.05)
if __name__ == "__main__":
    unittest.main()
"""
SLEEPER = "import time\ntime.sleep(60)\n"


class ConcurrentSuitesTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)

    def tearDown(self):
        self.temp.cleanup()

    def suite(self, name: str, body: str) -> str:
        path = self.root / name
        path.write_text(textwrap.dedent(body), encoding="utf-8")
        return str(path)

    def run_main(self, argv, env=None):
        out = io.StringIO()
        with mock.patch.dict(os.environ, env or {}), contextlib.redirect_stdout(out):
            code = runner.main(argv)
        return code, out.getvalue()

    def test_every_passing_suite_is_reported_and_the_run_passes(self):
        first = self.suite("first.py", PASSING)
        second = self.suite("second.py", SKIPPED)
        code, out = self.run_main([first, second])
        self.assertEqual(code, 0, out)
        self.assertIn(f"::group::{first} (ok)", out)
        self.assertIn(f"::group::{second} (ok)", out)
        self.assertIn("Ran 2 tests", out)
        self.assertIn("2 of 2 passed", out)

    def test_one_failing_suite_fails_the_run_and_is_named(self):
        good = self.suite("good.py", PASSING)
        bad = self.suite("bad.py", FAILING)
        code, out = self.run_main([good, bad])
        self.assertEqual(code, 1, out)
        self.assertIn(f"concurrent suites FAILED: {bad}: exited 1", out)
        self.assertNotIn(f"FAILED: {good}", out)
        self.assertIn("deliberate", out)
        self.assertIn("1 of 2 passed", out)

    def test_a_suite_that_runs_no_tests_fails(self):
        empty = self.suite("empty.py", EMPTY)
        code, out = self.run_main([empty])
        self.assertEqual(code, 1, out)
        self.assertIn("ran no tests", out)

    def test_a_zero_exit_without_a_unittest_verdict_fails(self):
        silent = self.suite("silent.py", SILENT)
        code, out = self.run_main([silent])
        self.assertEqual(code, 1, out)
        self.assertIn("ran no tests", out)
        self.assertIn("did not report OK", out)

    def test_suites_really_run_concurrently(self):
        left = self.suite("left.py", RENDEZVOUS.format(own="left", other="right"))
        right = self.suite("right.py", RENDEZVOUS.format(own="right", other="left"))
        with mock.patch.object(runner, "TIMEOUT_SECONDS", 30):
            code, out = self.run_main([left, right], {"RENDEZVOUS_DIR": str(self.root)})
        self.assertEqual(code, 0, out)

    def test_a_hung_suite_is_terminated_and_fails_with_its_output(self):
        hung = self.suite("hung.py", SLEEPER)
        started = time.monotonic()
        with mock.patch.object(runner, "TIMEOUT_SECONDS", 1):
            code, out = self.run_main([hung])
        self.assertLess(time.monotonic() - started, 30, "the hung suite was not killed")
        self.assertEqual(code, 1, out)
        self.assertIn("suite timed out and was terminated", out)
        self.assertIn("exited -1", out)

    def test_interpreter_env_applies_to_following_suites_only(self):
        first = self.suite("first.py", PASSING)
        second = self.suite("second.py", PASSING)
        with mock.patch.dict(os.environ, {"LOCKED_PY": "/locked/python"}):
            pairs = runner.parse([first, "--interpreter-env", "LOCKED_PY", second])
        self.assertEqual(pairs, [(sys.executable, first), ("/locked/python", second)])

    def test_the_named_interpreter_actually_runs_the_suite(self):
        probe = self.suite("probe.py", """
            import os, sys, unittest
            class T(unittest.TestCase):
                def test_interpreter(self):
                    self.assertEqual(os.environ.get("PROBE_MARK"), "set")
            if __name__ == "__main__":
                unittest.main()
        """)
        wrapper = self.root / ("wrapper.cmd" if os.name == "nt" else "wrapper.sh")
        if os.name == "nt":
            wrapper.write_text(f'@set PROBE_MARK=set\r\n@"{sys.executable}" %*\r\n', encoding="utf-8")
        else:
            wrapper.write_text(f'#!/bin/sh\nPROBE_MARK=set exec "{sys.executable}" "$@"\n', encoding="utf-8")
            wrapper.chmod(0o755)
        code, out = self.run_main(["--interpreter-env", "LOCKED_PY", probe], {"LOCKED_PY": str(wrapper)})
        self.assertEqual(code, 0, out)
        code, out = self.run_main([probe])
        self.assertEqual(code, 1, out)

    def test_invalid_invocations_are_refused_before_running_anything(self):
        real = self.suite("real.py", PASSING)
        os.environ.pop("UNSET_INTERPRETER_FOR_TEST", None)
        cases = {
            "empty": [],
            "duplicate": [real, real],
            "missing": [str(self.root / "absent.py")],
            "dangling flag": [real, "--interpreter-env"],
            "unset interpreter": ["--interpreter-env", "UNSET_INTERPRETER_FOR_TEST", real],
        }
        for label, argv in cases.items():
            with self.subTest(label), mock.patch.object(runner, "run") as run:
                code, out = self.run_main(argv)
                self.assertEqual(code, 2, out)
                run.assert_not_called()


    def test_each_real_unittest_run_requires_a_positive_successful_summary(self):
        # Real unittest TestResults deliberately do not set the child's exit code.
        cases = [(("pass", "fail"), 1), (("fail", "pass"), 1),
                 (("empty", "pass"), 1), (("pass", "empty"), 1),
                 (("pass", "pass"), 0), (("pass", "skip"), 0),
                 (("pass", "expected"), 0)]
        for order, expected in cases:
            with self.subTest(order=order):
                script = self.suite("two-runs.py", """
                    import unittest
                    class Passing(unittest.TestCase):
                        def test_one(self):
                            pass
                    class Failing(unittest.TestCase):
                        def test_one(self):
                            self.fail("deliberate child unittest failure")
                    class Skipped(unittest.TestCase):
                        @unittest.skip("deliberate supported skip")
                        def test_one(self):
                            pass
                    class ExpectedFailure(unittest.TestCase):
                        @unittest.expectedFailure
                        def test_one(self):
                            self.fail("deliberate expected failure")
                    kinds = {"pass": Passing, "fail": Failing,
                             "skip": Skipped, "expected": ExpectedFailure}
                    for kind in ORDER:
                        suite = unittest.TestSuite()
                        if kind != "empty":
                            suite.addTest(kinds[kind]("test_one"))
                        unittest.TextTestRunner().run(suite)
                """.replace("ORDER", repr(order)))
                observed = []
                actual_run = runner.run
                def observe(interpreter, path):
                    value = actual_run(interpreter, path)
                    observed.append(value)
                    return value
                with mock.patch.object(runner, "run", side_effect=observe):
                    code, output = self.run_main([script])
                self.assertEqual(len(observed), 1)
                child_code, child_output = observed[0]
                self.assertEqual(child_code, 0, child_output)
                self.assertEqual(child_output.count("Ran "), 2, child_output)
                print("C05 actual child observation:", order, "child exit", child_code,
                      "aggregate", code, "expected", expected)
                # Retain child diagnostics without presenting fixture verdicts
                # as this test module's own canonical unittest summaries.
                print("\n".join("C05 child> " + line for line in child_output.splitlines()))
                self.assertEqual(code, expected, output)
                self.assertIn("0 of 1 passed" if expected else "1 of 1 passed", output)


    def test_invalid_timeout_or_unavailable_interpreter_refuses_before_launch(self):
        real = self.suite("preflight.py", PASSING)
        missing = str(self.root / "unavailable-interpreter")
        self.assertFalse(Path(missing).exists())
        cases = [("zero", 0, None), ("negative", -1, None),
                 ("nan", float("nan"), None), ("infinity", float("inf"), None),
                 ("negative infinity", float("-inf"), None),
                 ("missing interpreter", 30, missing)]
        for label, timeout, interpreter in cases:
            with self.subTest(case=label):
                argv = [real] if interpreter is None else [
                    "--interpreter-env", "C05_UNAVAILABLE_INTERPRETER", real]
                env = {} if interpreter is None else {
                    "C05_UNAVAILABLE_INTERPRETER": interpreter}
                # This is an inert interception, never fake successful output.
                # Invalid timeout values must never reach a real child process.
                with mock.patch.object(runner, "TIMEOUT_SECONDS", timeout), \
                     mock.patch.object(runner, "run", return_value=(
                         1, "testlaunchintercept:nochildexecuted")) as launch:
                    code, output = self.run_main(argv, env)
                print("C05 preflight observation:", label, "return", code,
                      "intercepted run calls", launch.call_count)
                self.assertEqual((code, launch.call_count), (2, 0), output)


if __name__ == "__main__":
    unittest.main()
