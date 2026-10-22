#!/usr/bin/env python3
"""Negative controls for the read-only CI20-01 baseline collector."""
from __future__ import annotations

import copy
import importlib.util
import json
import subprocess
import sys
import tempfile
from pathlib import Path
import unittest
from unittest.mock import patch

HERE = Path(__file__).resolve().parent
spec = importlib.util.spec_from_file_location("ci20_baseline", HERE / "ci20_baseline.py")
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)
inventory_spec = importlib.util.spec_from_file_location(
    "ci20_inventory", HERE / "ci20_inventory.py")
inventory = importlib.util.module_from_spec(inventory_spec)
inventory_spec.loader.exec_module(inventory)


def fixture():
    workflow = {"jobs": {
        "select": {"name": "Impact selection"},
        "build": {"name": "Build <${{ matrix.os }}>", "needs": "select"},
        "gate": {"name": "Merge readiness", "needs": ["select", "build"]},
    }}
    workflow["jobs"]["ci-passed"] = workflow["jobs"].pop("gate")
    jobs = [
        {"id": 1, "name": "Impact selection", "started_at": "2026-10-20T00:00:00Z",
         "completed_at": "2026-10-20T00:00:10Z"},
        {"id": 2, "name": "Build <windows>", "started_at": "2026-10-20T00:00:20Z",
         "completed_at": "2026-10-20T00:01:20Z"},
        {"id": 3, "name": "Build <linux>", "started_at": "2026-10-20T00:00:15Z",
         "completed_at": "2026-10-20T00:00:45Z"},
        {"id": 4, "name": "Merge readiness", "started_at": "2026-10-20T00:01:25Z",
         "completed_at": "2026-10-20T00:01:30Z"},
    ]
    return workflow, jobs


class BaselineTest(unittest.TestCase):
    def test_matrix_needs_and_real_durations(self):
        workflow, jobs = fixture()
        owners = module.identify_jobs(workflow, jobs)
        self.assertEqual(len(owners["build"]), 2)
        result = module.replay(workflow, owners)
        self.assertEqual(result["queue_free_seconds"], 75)
        self.assertEqual(result["group_finish_seconds"]["build"], 70)

    def test_unknown_ambiguous_and_missing_jobs_refuse(self):
        workflow, jobs = fixture()
        with self.assertRaises(ValueError):
            module.identify_jobs(workflow, jobs + [{**jobs[0], "name": "Unexpected"}])
        with self.assertRaises(ValueError):
            module.replay(workflow, module.identify_jobs(workflow, jobs[:-1]))
        workflow["jobs"]["duplicate"] = {"name": "Impact selection"}
        with self.assertRaises(ValueError):
            module.identify_jobs(workflow, jobs)

    def test_cycles_and_unknown_dependencies_refuse(self):
        workflow, jobs = fixture()
        workflow["jobs"]["select"]["needs"] = "ci-passed"
        with self.assertRaises(ValueError):
            module.replay(workflow, module.identify_jobs(workflow, jobs))
        workflow["jobs"]["select"]["needs"] = "nonexistent"
        with self.assertRaises(ValueError):
            module.dependencies(workflow)

    def test_skipped_matrix_name_is_still_identified(self):
        workflow, jobs = fixture()
        jobs[1]["name"] = "Build <${{ matrix.os }}>"
        self.assertEqual(len(module.identify_jobs(workflow, jobs)["build"]), 2)

    def test_timestamp_and_runner_accounting(self):
        self.assertEqual(module.seconds("2026-10-20T00:00:00Z",
                                        "2026-10-20T00:00:01Z"), 1.0)

    def test_counts_all_conclusions_including_unknowns_and_null(self):
        cases = [{"conclusion": "success"}, {"conclusion": "skipped"},
                 {"conclusion": "timed_out"}, {"conclusion": None},
                 {"conclusion": "neutral"}, {}]
        counts = module.count_conclusions(cases)
        self.assertEqual(sum(counts.values()), len(cases))
        self.assertEqual(counts["timed_out"], 1)
        self.assertEqual(counts["None"], 2)
        self.assertEqual(counts["neutral"], 1)

    def test_protection_contexts_and_checks_only_fallback(self):
        target = "[GATE ] | [REPO] | Merge readiness"
        self.assertEqual(inventory.required_contexts({
            "required_status_checks": {"checks": [{"context": target, "app_id": 15368}]}
        }), [target])
        self.assertEqual(inventory.required_contexts({
            "required_status_checks": {
                "contexts": [target], "checks": [{"context": target, "app_id": 15368},
                                                  {"context": "additional check"}]}
        }), [target, "additional check"])
        for response in ({}, {"required_status_checks": {"contexts": []}},
                         {"required_status_checks": {"checks": [{"context": ""}]}},
                         {"required_status_checks": {"checks": [None]}}):
            with self.subTest(response=response), self.assertRaises(SystemExit):
                inventory.required_contexts(response)

    def test_optimized_inventory_still_rejects_wrong_checkout(self):
        with tempfile.TemporaryDirectory(prefix="ci20-inventory-opt-") as temp:
            baseline=Path(temp)/"stale.json"
            destination=Path(temp)/"output.json"
            baseline.write_text(json.dumps({"source_commit": "f" * 40}), encoding="utf-8")
            completed=subprocess.run(
                [sys.executable, "-O", str(HERE/"ci20_inventory.py"),
                 "--baseline", str(baseline), "--output", str(destination)],
                cwd=HERE.parent, capture_output=True, text=True, timeout=20)
            self.assertNotEqual(completed.returncode, 0)
            self.assertIn("differs from baseline", completed.stderr)
            self.assertFalse(destination.exists())

    def test_wrong_source_refuses_before_job_retrieval(self):
        with patch.object(module, "command", return_value="a" * 40), \
             patch.object(module, "api", return_value={"head_sha": "b" * 40}):
            with self.assertRaises(ValueError):
                module.collect("arbiterForge/codeArbiter", 123, HERE.parent)


if __name__ == "__main__":
    unittest.main(verbosity=2)
