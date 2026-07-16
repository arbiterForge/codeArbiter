#!/usr/bin/env python3
"""Task 11 tests for the three-host relative performance benchmark."""

import importlib.util
import json
import pathlib
import subprocess
import sys
import unittest


ROOT = pathlib.Path(__file__).resolve().parents[2]
BENCHMARK = ROOT / ".github" / "scripts" / "pi_benchmark.py"


def load_benchmark():
    spec = importlib.util.spec_from_file_location("pi_benchmark", BENCHMARK)
    if spec is None or spec.loader is None:
        raise AssertionError("pi benchmark module is unavailable")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class PiBenchmarkTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.benchmark = load_benchmark()

    def test_relative_limit_uses_slower_host_plus_larger_margin(self):
        self.assertEqual(self.benchmark.promotion_limit(20.0, 30.0), 40.0)
        self.assertEqual(self.benchmark.promotion_limit(80.0, 60.0), 100.0)

    def test_pi_p95_must_fit_relative_limit(self):
        self.assertTrue(self.benchmark.benchmark_passes(39.9, 20.0, 30.0))
        self.assertFalse(self.benchmark.benchmark_passes(40.1, 20.0, 30.0))

    def test_percentiles_are_deterministic_and_require_the_full_corpus(self):
        values = [float(value) for value in range(1, 101)]
        self.assertEqual(self.benchmark.percentile(values, 50), 50.0)
        self.assertEqual(self.benchmark.percentile(values, 95), 95.0)
        with self.assertRaisesRegex(ValueError, "exactly 100"):
            self.benchmark.summarize_samples([1.0] * 99)

    def test_corpus_covers_read_exec_write_without_sensitive_fields(self):
        corpus = self.benchmark.canonical_corpus()
        self.assertEqual([event["kind"] for event in corpus], ["read", "exec", "write"])
        serialized = json.dumps(corpus, sort_keys=True).lower()
        for forbidden in ("prompt", "provider", "auth", "token", "secret", "environment"):
            self.assertNotIn(forbidden, serialized)

    def test_pi_measurement_runs_the_production_typescript_tool_boundary(self):
        benchmark_source = BENCHMARK.read_text(encoding="utf-8")
        boundary = ROOT / "plugins" / "ca-pi" / "tools" / "test" / "benchmark-boundary.ts"
        self.assertIn("benchmark-boundary.ts", benchmark_source)
        self.assertTrue(boundary.is_file())
        source = boundary.read_text(encoding="utf-8")
        self.assertIn('from "../src/tool-guard.ts"', source)
        self.assertIn("wrapBuiltins", source)
        self.assertIn("bridgeCallCount", source)
        self.assertIn("nativeCallCount", source)

    def test_pi_record_does_not_load_the_generated_python_host_adapter(self):
        original = self.benchmark.HOST_HOOKS["pi"]
        self.benchmark.HOST_HOOKS["pi"] = ROOT / "does-not-exist"
        try:
            record = self.benchmark._measure_host("pi", 100)
        finally:
            self.benchmark.HOST_HOOKS["pi"] = original
        self.assertEqual(record["host"], "pi")

    def test_measurements_use_exact_public_shape_and_100_warm_events(self):
        records = self.benchmark.run_benchmark(samples=100)
        self.assertEqual([record["host"] for record in records], ["claude", "codex", "pi"])
        expected = {
            "platform", "host", "sampleCount", "startupMs", "coreP50Ms",
            "adapterP50Ms", "adapterP95Ms",
        }
        for record in records:
            self.assertEqual(set(record), expected)
            self.assertEqual(record["sampleCount"], 100)
            for key in expected - {"platform", "host", "sampleCount"}:
                self.assertGreaterEqual(record[key], 0.0)

    def test_cli_emits_only_three_bounded_json_records(self):
        completed = subprocess.run(
            [sys.executable, str(BENCHMARK), "--samples", "100"],
            cwd=ROOT,
            check=False,
            capture_output=True,
            text=True,
            encoding="utf-8",
            timeout=30,
        )
        self.assertEqual(completed.returncode, 0, completed.stderr)
        records = [json.loads(line) for line in completed.stdout.splitlines() if line]
        self.assertEqual(len(records), 3)
        self.assertEqual({record["host"] for record in records}, {"claude", "codex", "pi"})
        self.assertLess(len(completed.stdout.encode("utf-8")), 4096)
        self.assertNotIn(str(ROOT), completed.stdout)


if __name__ == "__main__":
    unittest.main()
