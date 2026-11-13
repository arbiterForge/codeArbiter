#!/usr/bin/env python3
"""R-07 / C-F08: every verifier wait has a deadline and a cleanup outcome.

Fake children cover: never emits its ready line, emits a partial line, exits
immediately, hangs during an install command, and leaves a grandchild that
would survive termination of its direct parent alone.
"""
from __future__ import annotations

import ctypes
import importlib.util
import os
import subprocess
import sys
import tempfile
import time
import unittest
from pathlib import Path
from unittest.mock import patch, Mock

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))


def load(name):
    spec = importlib.util.spec_from_file_location(name, HERE / f"{name}.py")
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


B = load("_boundedproc")
PY = sys.executable
HANG = "import time\nwhile True: time.sleep(0.2)\n"


def alive(pid: int) -> bool:
    if os.name == "nt":
        handle = ctypes.windll.kernel32.OpenProcess(0x1000, False, pid)  # QUERY_LIMITED
        if not handle:
            return False
        code = ctypes.c_ulong()
        ctypes.windll.kernel32.GetExitCodeProcess(handle, ctypes.byref(code))
        ctypes.windll.kernel32.CloseHandle(handle)
        return code.value == 259  # STILL_ACTIVE
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        return True
    # A reaped-but-zombie grandchild is not running work; check its state.
    try:
        state = Path(f"/proc/{pid}/stat").read_text().split()[2]
        return state != "Z"
    except OSError:
        return True


def wait_dead(pid: int, seconds: float = 5.0) -> bool:
    deadline = time.monotonic() + seconds
    while time.monotonic() < deadline:
        if not alive(pid):
            return True
        time.sleep(0.05)
    return False


def child(source: str, **kwargs):
    return B.start([PY, "-c", source], stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                   text=True, encoding="utf-8", **kwargs)


class ReadinessWaitTest(unittest.TestCase):
    def test_child_that_never_emits_a_ready_line_times_out_and_is_contained(self):
        process = child(HANG)
        started = time.monotonic()
        line, reason = B.readline(process, 1.0)
        self.assertIsNone(line)
        self.assertIn("no line within", reason)
        self.assertLess(time.monotonic() - started, 5)
        self.assertEqual(B.terminate_tree(process), "terminated")
        self.assertIsNotNone(process.poll())

    def test_partial_line_without_newline_is_still_bounded(self):
        process = child("import sys,time\nsys.stdout.write('{\"phase\":');sys.stdout.flush()\n" + HANG)
        line, _ = B.readline(process, 1.0)
        self.assertIsNone(line)
        self.assertEqual(B.terminate_tree(process), "terminated")

    def test_partial_line_then_exit_is_returned_for_validation(self):
        process = child("import sys\nsys.stdout.write('{\"phase\":')\n")
        line, reason = B.readline(process, 5.0)
        self.assertEqual((line, reason), ('{"phase":', ""))
        process.wait(5)

    def test_child_that_exits_immediately_reports_a_closed_stream(self):
        process = child("raise SystemExit(3)")
        line, reason = B.readline(process, 5.0)
        self.assertEqual(line, "")
        self.assertIn("closed", reason)
        self.assertEqual(process.wait(5), 3)


class BoundedRunTest(unittest.TestCase):
    def test_timeout_communication_does_not_duplicate_the_retained_prefix(self):
        process = Mock()
        process.communicate.side_effect = [
            subprocess.TimeoutExpired(['child'], 1, output=b'prefix'),
            ('prefix tail', ''),
        ]
        with patch.object(B, 'start', return_value=process), patch.object(B, 'terminate_tree', return_value='terminated'):
            result = B.run(['child'], timeout=1)
        self.assertEqual(result.stdout, 'prefix tail')
        self.assertTrue(result.timed_out)

    def test_install_that_hangs_times_out_with_partial_diagnostics(self):
        result = B.run([PY, "-c", "print('adding marketplace', flush=True)\n" + HANG], timeout=1.5)
        self.assertTrue(result.timed_out)
        self.assertIsNone(result.returncode)
        self.assertEqual(result.containment, "terminated")
        self.assertIn("adding marketplace", result.stdout)
        self.assertIn("containment=terminated", result.diagnostic("install", 1.5))

    def test_finished_child_is_exited_not_terminated(self):
        result = B.run([PY, "-c", "print('ok')"], timeout=30)
        self.assertEqual((result.returncode, result.timed_out, result.containment), (0, False, "exited"))

    def test_grandchild_surviving_its_parent_is_terminated_with_the_tree(self):
        # Killing only the direct child would leave this grandchild running;
        # the tree contract must take it down and confirm the outcome.
        with tempfile.TemporaryDirectory() as temporary:
            marker = Path(temporary) / "grandchild.pid"
            spawner = (
                "import subprocess,sys,time\n"
                f"g=subprocess.Popen([sys.executable,'-c',{HANG!r}])\n"
                f"open({str(marker)!r},'w').write(str(g.pid))\n"
                + HANG
            )
            process = child(spawner)
            deadline = time.monotonic() + 20
            while not marker.exists() or not marker.read_text():
                self.assertLess(time.monotonic(), deadline, "grandchild never started")
                time.sleep(0.05)
            grandchild = int(marker.read_text())
            self.assertTrue(alive(grandchild))
            self.assertEqual(B.terminate_tree(process), "terminated")
            self.assertTrue(wait_dead(grandchild), "grandchild survived tree termination")

    @unittest.skipUnless(os.name == "nt", "Windows taskkill availability path")
    def test_missing_taskkill_is_unconfirmed_not_terminated(self):
        process = child(HANG)
        with patch.object(B, "_taskkill", return_value=None):
            self.assertEqual(B.terminate_tree(process), "unconfirmed")


class CodexHostCommandDeadlineTest(unittest.TestCase):
    def test_hanging_codex_command_fails_with_timeout_and_containment(self):
        module = load("check_codex_host")
        started = time.monotonic()
        with tempfile.TemporaryDirectory() as home:
            done = module._run([PY, "-c", "print('installing', flush=True)\n" + HANG],
                               Path(home), timeout=1.5)
        self.assertLess(time.monotonic() - started, 20, "the deadline was not applied")
        self.assertNotEqual(done.returncode, 0)
        self.assertIn("timed out after 1.5s", done.stderr)
        self.assertIn("containment=terminated", done.stderr)
        self.assertIn("installing", done.stdout)

    def test_a_timed_out_marketplace_add_is_a_recorded_failure(self):
        module = load("check_codex_host")
        timed_out = subprocess.CompletedProcess(["codex"], 124, "partial",
                                                "marketplace add timed out after 1s; child containment=terminated")
        with tempfile.TemporaryDirectory() as home, \
                patch.object(module, "_run", return_value=timed_out):
            results = module.check_install(Path(home))
        self.assertEqual(results[0]["code"], "CODEX-HOST-MARKETPLACE")
        self.assertEqual(results[0]["status"], "fail")
        self.assertIn("containment=terminated", results[0]["detail"])


class PiBenchmarkReadinessDeadlineTest(unittest.TestCase):
    def session(self, source, ready=1.0, complete=1.0):
        module = load("pi_benchmark")
        return module._boundary_session([PY, "-c", source], HERE, ready_timeout=ready,
                                        complete_timeout=complete)

    def test_no_ready_line_is_a_bounded_failure_with_containment(self):
        with self.assertRaisesRegex(RuntimeError, "readiness.*containment=terminated"):
            self.session(HANG)

    def test_partial_ready_line_is_refused(self):
        with self.assertRaisesRegex(RuntimeError, "readiness"):
            self.session("import sys\nsys.stdout.write('{\"phase\":')\n")

    def test_immediate_exit_is_refused(self):
        with self.assertRaisesRegex(RuntimeError, "closed before"):
            self.session("raise SystemExit(2)")

    def test_hang_after_ready_is_bounded(self):
        with self.assertRaisesRegex(RuntimeError, "completion.*containment=terminated"):
            self.session("print('{\"phase\":\"ready\"}', flush=True)\n" + HANG)

    def test_well_behaved_boundary_completes(self):
        _, ready, remainder = self.session(
            "print('{\"phase\":\"ready\"}', flush=True)\nprint('{\"phase\":\"complete\"}')",
            ready=10, complete=10)
        self.assertEqual(ready, {"phase": "ready"})
        self.assertIn("complete", remainder)


if __name__ == "__main__":
    unittest.main()
