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


if __name__ == "__main__":
    unittest.main()
