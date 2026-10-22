#!/usr/bin/env python3
"""tools/go_test_parallel.py must run every discovered Go test exactly once and fail closed.

Each case builds a throwaway module, so these exercise the real compiler, test
binary listing, test2json stream and exit codes rather than a mocked runner.
"""
from __future__ import annotations

import contextlib
import importlib.util
import io
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest
import unittest.mock

REPO = Path(__file__).resolve().parents[2]
RUNNER = REPO / "tools/go_test_parallel.py"


def load_runner():
    spec = importlib.util.spec_from_file_location("go_test_parallel", RUNNER)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@unittest.skipIf(shutil.which("go") is None, "requires a Go toolchain")
class RealModule(unittest.TestCase):
    def module(self, files: dict[str, str]) -> Path:
        root = Path(self.enterContext(tempfile.TemporaryDirectory(prefix="go-parallel-")))
        (root / "go.mod").write_text("module example.test/parallel\n\ngo 1.21\n", encoding="utf-8")
        for name, body in files.items():
            path = root / name
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(body, encoding="utf-8")
        return root

    def run_runner(self, root: Path, *extra: str) -> subprocess.CompletedProcess[str]:
        hints = root / "hints.json"
        hints.write_text(json.dumps({"format": "codearbiter.go-test-timings/1", "tests": {}}), encoding="utf-8")
        env = dict(os.environ, GOFLAGS="", GOTOOLCHAIN="local", GOWORK="off")
        return subprocess.run([sys.executable, str(RUNNER), "--module", str(root), "--jobs", "3",
                               "--hints", str(hints), *extra], env=env, capture_output=True,
                              text=True, encoding="utf-8", errors="replace", timeout=600)

    PASSING = {
        "a/a_test.go": 'package a\nimport "testing"\n'
                       'func TestOne(t *testing.T) { t.Setenv("PARALLEL_ENV", "1") }\n'
                       'func TestTwo(t *testing.T) { t.Run("sub", func(t *testing.T) {}) }\n'
                       'func TestSkip(t *testing.T) { t.Skip("platform") }\n',
        "a/fuzz_test.go": 'package a\nimport "testing"\nfunc FuzzSeed(f *testing.F) { f.Add(1); f.Fuzz(func(t *testing.T, n int) {}) }\n',
        "b/b_test.go": 'package b\nimport "testing"\nfunc TestB(t *testing.T) {}\n',
        "c/c.go": "package c\n",
    }

    def test_complete_population_passes_and_counts_every_test(self):
        result = self.run_runner(self.module(self.PASSING))
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertIn("5 top-level tests in 2 packages", result.stdout)
        self.assertIn("4 passed, 1 skipped, all complete", result.stdout)

    def test_a_failing_test_fails_the_run(self):
        files = dict(self.PASSING)
        files["b/b_test.go"] = 'package b\nimport "testing"\nfunc TestB(t *testing.T) { t.Fatal("broken") }\n'
        result = self.run_runner(self.module(files))
        self.assertEqual(result.returncode, 1, result.stdout)
        self.assertIn("not passed: ['TestB']", result.stdout)
        self.assertIn("broken", result.stdout)

    def test_a_failing_subtest_fails_its_parent(self):
        files = dict(self.PASSING)
        files["a/a_test.go"] = files["a/a_test.go"].replace(
            't.Run("sub", func(t *testing.T) {})', 't.Run("sub", func(t *testing.T) { t.Error("sub broke") })')
        result = self.run_runner(self.module(files))
        self.assertEqual(result.returncode, 1, result.stdout)
        self.assertIn("TestTwo", result.stdout)

    def test_a_process_that_exits_early_cannot_pass_unreported_tests(self):
        files = dict(self.PASSING)
        files["b/b_test.go"] = ('package b\nimport ("os"; "testing")\n'
                                'func TestA(t *testing.T) { os.Exit(0) }\nfunc TestB(t *testing.T) {}\n')
        result = self.run_runner(self.module(files))
        self.assertEqual(result.returncode, 1, result.stdout)
        self.assertRegex(result.stdout, r"not passed: \[.*'TestB'")

    def test_a_nonzero_exit_after_passing_tests_fails_the_run(self):
        files = dict(self.PASSING)
        # Listing stays clean; only the real run exits non-zero after its tests pass.
        files["b/main_test.go"] = ('package b\nimport ("flag"; "os"; "testing")\n'
                                   'func TestMain(m *testing.M) { code := m.Run()\n'
                                   '  if flag.Lookup("test.list").Value.String() == "" { code = 3 }\n  os.Exit(code) }\n')
        result = self.run_runner(self.module(files))
        self.assertEqual(result.returncode, 1, result.stdout)
        self.assertRegex(result.stdout, r"FAIL example\.test/parallel/b ")

    def test_a_test_reported_twice_fails_the_run(self):
        files = dict(self.PASSING)
        # Listing stays unique; the real run executes the population twice.
        files["b/main_test.go"] = ('package b\nimport ("flag"; "os"; "testing")\n'
                                   'func TestMain(m *testing.M) { code := m.Run()\n'
                                   '  if flag.Lookup("test.list").Value.String() == "" { code = m.Run() }\n  os.Exit(code) }\n')
        result = self.run_runner(self.module(files))
        self.assertEqual(result.returncode, 1, result.stdout)
        self.assertIn("not passed: ['TestB']", result.stdout)

    def test_a_discovery_failure_fails_cleanly(self):
        files = dict(self.PASSING)
        files["b/main_test.go"] = 'package b\nimport ("os"; "testing")\nfunc TestMain(m *testing.M) { os.Exit(4) }\n'
        result = self.run_runner(self.module(files))
        self.assertEqual(result.returncode, 1, result.stdout)
        self.assertIn("FAILED before running tests", result.stdout)
        self.assertNotIn("Traceback", result.stderr)

    def test_a_chunking_defect_cannot_drop_a_discovered_test(self):
        runner = load_runner()
        root = self.module(self.PASSING)
        original = runner.chunk

        def lossy(package, names, hints, workers):
            return original(package, [n for n in names if n != "TestB"] or names[:0], hints, workers)
        argv = ["go_test_parallel.py", "--module", str(root), "--jobs", "2", "--hints", str(root / "absent.json")]
        with unittest.mock.patch.object(runner, "chunk", lossy), unittest.mock.patch.object(sys, "argv", argv), \
                unittest.mock.patch.dict(os.environ, {"GOFLAGS": "", "GOWORK": "off"}), \
                contextlib.redirect_stdout(io.StringIO()) as output:
            self.assertEqual(runner.main(), 1)
        self.assertIn("listed tests without a result", output.getvalue())
        self.assertIn("TestB", output.getvalue())

    def test_a_compile_failure_fails_the_run(self):
        files = dict(self.PASSING)
        files["b/b_test.go"] = 'package b\nimport "testing"\nfunc TestB(t *testing.T) { undefined() }\n'
        self.assertNotEqual(self.run_runner(self.module(files)).returncode, 0)

    def test_build_flags_reach_the_compiler(self):
        files = {"a/a_test.go": 'package a\nimport "testing"\nfunc TestTag(t *testing.T) { if !tagged { t.Fatal("untagged") } }\n',
                 "a/on.go": "//go:build marker\n\npackage a\nconst tagged = true\n",
                 "a/off.go": "//go:build !marker\n\npackage a\nconst tagged = false\n"}
        root = self.module(files)
        self.assertEqual(self.run_runner(root).returncode, 1)
        tagged = self.run_runner(root, "--build-flag=-tags=marker")
        self.assertEqual(tagged.returncode, 0, tagged.stdout + tagged.stderr)


class Chunking(unittest.TestCase):
    def test_chunks_are_disjoint_complete_and_hint_balanced(self):
        runner = load_runner()
        names = [f"Test{i}" for i in range(9)]
        hints = {"pkg.Test0": 60.0, "pkg.Test1": 50.0, "pkg.Test2": 40.0}
        chunks = runner.chunk("pkg", names, hints, 3)
        flat = [name for members, _ in chunks for name in members]
        self.assertEqual(sorted(flat), sorted(names))
        self.assertEqual(len(flat), len(set(flat)))
        self.assertEqual(len(chunks), 3)
        heavy = [members for members, _ in chunks if {"Test0", "Test1", "Test2"} & set(members)]
        self.assertEqual(len(heavy), 3, "the three heavy tests must land in different chunks")

    def test_stale_hints_never_remove_tests(self):
        runner = load_runner()
        chunks = runner.chunk("pkg", ["TestNew"], {"pkg.TestGone": 99.0}, 4)
        self.assertEqual(chunks[0][0], ["TestNew"])

    def test_malformed_hints_are_refused(self):
        runner = load_runner()
        with tempfile.TemporaryDirectory() as raw:
            path = Path(raw) / "hints.json"
            for document in ({"format": "other", "tests": {}},
                             {"format": "codearbiter.go-test-timings/1", "tests": {"x": -1}},
                             {"format": "codearbiter.go-test-timings/1", "tests": {"x": float("inf")}}):
                path.write_text(json.dumps(document), encoding="utf-8")
                with self.subTest(document=document), self.assertRaises(ValueError):
                    runner.load_hints(path)


if __name__ == "__main__":
    unittest.main(verbosity=2)
