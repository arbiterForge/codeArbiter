"""CI20-01: offline, immutable-source critical-path capture regression tests."""
from __future__ import annotations

import copy
import gzip
import json
from pathlib import Path
import shutil
import sys
import tempfile
import unittest

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO / "tools"))
import ci_critical_path as ci  # noqa: E402

FIXTURES = REPO / "docs/reports/ci20-01"
OLD = FIXTURES / "39088746696"
MAIN = FIXTURES / "39345028289"


def inputs(directory: Path):
    run = json.loads(ci.unpack((directory / "run.json.gz").read_bytes()))
    pages = json.loads(ci.unpack((directory / "jobs-pages.json.gz").read_bytes()))
    workflows = {ci.WORKFLOW: ci.unpack((directory / "ci.yml.gz").read_bytes()).decode("utf-8")}
    if (directory / "ci-native-platform.yml.gz").exists():
        workflows[ci.NESTED] = ci.unpack((directory / "ci-native-platform.yml.gz").read_bytes()).decode("utf-8")
    return run, pages, workflows


class FrozenBenchmarkTest(unittest.TestCase):
    def test_historical_pr_run_replays_exact_duration_and_complete_matrix(self):
        result = ci.replay(OLD)
        self.assertEqual(result["head_sha"], "16983f5017b39e35de2f90994e30fcd60730e82c")
        self.assertEqual((result["jobs"], result["actual_run_seconds"],
                          result["queue_free_replay_seconds"]), (113, 3583.0, 1271.0))
        self.assertEqual((result["total_runner_seconds"], result["macos_runner_seconds"]),
                         (17282.0, 4619.0))
        self.assertEqual(result["job_conclusions"], {"success": 113})
        self.assertTrue(any(job["scope"] == "native-reusable" for job in result["source_to_job_map"]))
        self.assertTrue(any(job["job_id"] == "artifact-platform" for job in result["source_to_job_map"]))
        self.assertEqual(len(result["queue_free_chain"]), 8)

    def test_current_main_is_independently_replayed_not_assumed_equivalent(self):
        result = ci.replay(MAIN)
        self.assertEqual(result["head_sha"], "849a3cf6fa6f4fdf3256cd3095c92499e9c4ec77")
        self.assertEqual((result["jobs"], result["actual_run_seconds"],
                          result["queue_free_replay_seconds"]), (83, 2829.0, 2732.0))
        self.assertEqual((result["total_runner_seconds"], result["macos_runner_seconds"]),
                         (21507.0, 5553.0))
        self.assertEqual(result["job_conclusions"], {"success": 74, "skipped": 9})
        names = {job["job_id"]: job for job in result["source_to_job_map"]}
        self.assertEqual(names["artifact-engine"]["observed_instances"], 6)
        self.assertEqual(names["artifact-authority"]["observed_instances"], 12)
        self.assertEqual(names["artifact-package-cold"]["observed_instances"], 18)
        self.assertEqual(names["hooks"]["observed_instances"], 5)
        self.assertFalse(any(job["scope"] == "native-reusable" for job in result["source_to_job_map"]))

    def test_reports_are_deterministic_and_exactly_bound_to_captured_input_hashes(self):
        for fixture in (OLD, MAIN):
            with self.subTest(run=fixture.name):
                a = ci.replay(fixture)
                b = ci.replay(fixture)
                self.assertEqual(a, b)
                self.assertEqual(a, json.loads(ci.unpack((fixture / "replay.json.gz").read_bytes())))
                manifest = json.loads((fixture / "manifest.json").read_text(encoding="utf-8"))
                for filename, digest in manifest["files"].items():
                    self.assertEqual(ci.hash_bytes((fixture / filename).read_bytes()), digest)

    def test_required_vs_awaited_gate_mismatch_is_exposed_not_called_advisory(self):
        result = ci.replay(MAIN)
        self.assertIn("ca-pi-latest", result["gate_awaited_not_in_required_results"])
        self.assertIn("codex-host-latest", result["gate_registration_contradiction"])
        self.assertEqual(set(result["gate_registration_contradiction"]),
                         {"codex-host-latest", "coverage-union", "coverage-union-merge",
                          "coverage-union-pi", "coverage-union-pi-merge"})
        self.assertTrue(set(result["gate_required_results"]).issubset(result["gate_needs"]))

    def test_preserves_skips_as_skips_and_counts_macos_by_actual_labels(self):
        result = ci.replay(MAIN)
        self.assertEqual(result["job_conclusions"]["skipped"], 9)
        self.assertGreater(result["macos_runner_seconds"], 0)
        self.assertLess(result["macos_runner_seconds"], result["total_runner_seconds"])
        self.assertEqual(result["interpretation"].startswith("Zero-queue"), True)


class NegativeEvidenceTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.old = inputs(OLD)

    def test_fewer_pages_or_duplicate_jobs_fail(self):
        run, pages, workflows = self.old
        self.assertEqual(len(pages), 2)
        with self.assertRaises(ValueError):
            ci.analyze(run, pages[:1], workflows)
        bad = copy.deepcopy(pages)
        bad[1]["jobs"][0]["id"] = bad[0]["jobs"][0]["id"]
        with self.assertRaises(ValueError):
            ci.analyze(run, bad, workflows)

    def test_partial_changed_page_total_is_not_silently_used(self):
        run, pages, workflows = self.old
        bad = copy.deepcopy(pages)
        bad[1]["total_count"] += 1
        with self.assertRaises(ValueError):
            ci.analyze(run, bad, workflows)

    def test_incorrect_commit_run_or_status_is_refused(self):
        run, pages, workflows = self.old
        for key, value in (("head_sha", "0" * 40), ("run_id", 123456),
                           ("status", "in_progress"), ("conclusion", "failure")):
            altered = copy.deepcopy(pages)
            altered[0]["jobs"][0][key] = value
            with self.subTest(key=key), self.assertRaises(ValueError):
                ci.analyze(run, altered, workflows)

    def test_successful_run_with_failed_or_cancelled_job_is_not_a_success_baseline(self):
        run, pages, workflows = self.old
        for conclusion in ("failure", "cancelled"):
            changed = copy.deepcopy(pages)
            changed[0]["jobs"][0]["conclusion"] = conclusion
            with self.subTest(conclusion=conclusion), self.assertRaises(ValueError):
                ci.analyze(run, changed, workflows)

    def test_changed_or_ambiguous_job_name_is_not_mapped_from_guesswork(self):
        run, pages, workflows = self.old
        altered = copy.deepcopy(pages)
        altered[0]["jobs"][0]["name"] = "UNKNOWN WORKFLOW JOB"
        with self.assertRaises(ValueError):
            ci.analyze(run, altered, workflows)
        with self.assertRaises(ValueError):
            ci.identify("repeat", {"one": {"name": "repeat", "uses": ""},
                                   "two": {"name": "repeat", "uses": ""}}, {})

    def test_job_cannot_start_before_required_predecessor(self):
        run, pages, workflows = self.old
        bad = copy.deepcopy(pages)
        target = next(job for page in bad for job in page["jobs"]
                      if "Structured artifact package assembly" in job["name"])
        target["started_at"] = run["created_at"]
        with self.assertRaises(ValueError):
            ci.analyze(run, bad, workflows)

    def test_missing_reusable_source_or_final_gate_is_refused(self):
        run, pages, workflows = self.old
        with self.assertRaises(ValueError):
            ci.analyze(run, pages, {ci.WORKFLOW: workflows[ci.WORKFLOW]})
        damaged = dict(workflows)
        damaged[ci.WORKFLOW] = damaged[ci.WORKFLOW].replace("\n  ci-passed:\n", "\n  gone-gate:\n")
        with self.assertRaises(ValueError):
            ci.analyze(run, pages, damaged)

    def test_changed_source_or_run_bytes_cannot_pass_manifest(self):
        with tempfile.TemporaryDirectory() as temporary:
            destination = Path(temporary) / "copy"
            shutil.copytree(OLD, destination)
            run = destination / "run.json.gz"
            run.write_bytes(run.read_bytes() + b" ")
            with self.assertRaises(ValueError):
                ci.replay(destination)
        with tempfile.TemporaryDirectory() as temporary:
            destination = Path(temporary) / "copy"
            shutil.copytree(OLD, destination)
            workflow = destination / "ci-native-platform.yml.gz"
            workflow.write_bytes(workflow.read_bytes() + b"\n# mutated")
            with self.assertRaises(ValueError):
                ci.replay(destination)

    def test_duplicate_yaml_job_names_and_unknown_dependencies_fail(self):
        minimum = ("jobs:\n  check:\n    name: check\n    needs: unknown\n")
        with self.assertRaises(ValueError):
            ci.parse_jobs(minimum)
        repeated = ("jobs:\n  check:\n    name: first\n  check:\n    name: second\n")
        with self.assertRaises(ValueError):
            ci.parse_jobs(repeated)

    def test_nonterminal_or_wrong_workflow_run_is_refused(self):
        run, pages, workflows = self.old
        for key, value in (("status", "in_progress"), ("name", "release"), ("path", "other.yml")):
            changed = dict(run, **{key: value})
            with self.subTest(key=key), self.assertRaises(ValueError):
                ci.analyze(changed, pages, workflows)


if __name__ == "__main__":
    unittest.main(verbosity=2)

class CurrentSourceReconciliationTest(unittest.TestCase):
    def test_post_baseline_current_main_inventory_is_exact_and_complete(self):
        folder = FIXTURES
        inventory = json.loads(ci.unpack((folder / "current-main-obligations.json.gz").read_bytes()).decode("utf-8"))
        self.assertEqual(inventory["inspected_current_main"], "9bf8b69ec21114f829f8745606d8da25a8f89a15")
        self.assertEqual(inventory["preceding_successful_main_run"]["head_sha"],
                         "849a3cf6fa6f4fdf3256cd3095c92499e9c4ec77")
        self.assertTrue(inventory["preceding_successful_main_run"]
                        ["selection_not_automatically_equivalent_to_new_source"])
        source = ci.unpack((folder / "current-main-ci.yml.gz").read_bytes())
        self.assertEqual(ci.hash_bytes(source), inventory["archived_ci_yaml_sha256"])
        self.assertEqual(source, (REPO / ".github/workflows/ci.yml").read_bytes())
        parsed = ci.parse_jobs(source.decode("utf-8"))
        self.assertEqual(inventory["root_job_count"], 42)
        self.assertEqual(len(parsed), 42)
        self.assertEqual(set(inventory["owners"]), set(parsed))
        for name, entry in parsed.items():
            self.assertEqual(inventory["owners"][name]["name"], entry["name"])
            actual = inventory["owners"][name]["needs"]
            actual = [actual] if isinstance(actual, str) else actual
            self.assertEqual(actual, entry["needs"])
        self.assertEqual(len(inventory["native_platforms"]), 6)
        self.assertEqual(len(inventory["authority_matrix"]), 12)
        self.assertEqual(len(inventory["cold_package_matrix"]), 18)
        new_guard = inventory["owners"]["control-bytes"]
        self.assertTrue(any("check_control_bytes.py" in step.get("run", "")
                            for step in new_guard["steps"]))
        self.assertFalse(inventory["exact_run_at_inspected_main_completed"])

    def test_current_source_obligations_are_pinned_not_grafted_from_old_pr(self):
        inventory = json.loads(ci.unpack((FIXTURES / "current-main-obligations.json.gz").read_bytes()).decode("utf-8"))
        self.assertIn(".github/scripts/test_suite_hermeticity.py", inventory["source_sha256"])
        self.assertIn(".github/scripts/test_smarts_engine_contract.py", inventory["source_sha256"])
        self.assertIn(".github/scripts/test_ship_set_inputs.py", inventory["source_sha256"])
        self.assertIn(".github/scripts/check_control_bytes.py", inventory["source_sha256"])
        for filename, sha256 in inventory["source_sha256"].items():
            self.assertEqual(ci.hash_bytes((REPO / filename).read_bytes()), sha256,
                             filename)
        self.assertEqual(inventory["gate_needs"], inventory["owners"]["ci-passed"]["needs"])
        self.assertEqual(len(inventory["gate_required_results"]), 35)
        self.assertEqual(len(inventory["gate_needs"]), 41)
        self.assertEqual(set(inventory["registration_contradictions_against_only_one_advisory_comment"]),
                         {"codex-host-latest", "coverage-union", "coverage-union-merge",
                          "coverage-union-pi", "coverage-union-pi-merge"})

class CaptureRoundTripTest(unittest.TestCase):
    def test_capture_preserves_all_api_fields_and_replays_without_network(self):
        from unittest import mock
        run, pages, workflows = inputs(OLD)

        def fake_api(url: str):
            if url.endswith("/actions/runs/39088746696"):
                return copy.deepcopy(run)
            if "/jobs?per_page=100&page=" in url:
                index = int(url.rsplit("page=", 1)[1]) - 1
                return copy.deepcopy(pages[index])
            raise AssertionError("unexpected capture URL: " + url)

        def fake_workflow(repo: str, source: str, path: str):
            self.assertEqual(repo, ci.REPO)
            self.assertEqual(source, run["head_sha"])
            return workflows[path].encode("utf-8")

        with tempfile.TemporaryDirectory() as temporary:
            directory = Path(temporary) / "evidence"
            with mock.patch.object(ci, "gh_json", side_effect=fake_api), \
                 mock.patch.object(ci, "fetch_workflow", side_effect=fake_workflow):
                output = ci.capture(39088746696, directory)
            self.assertEqual(output, ci.replay(directory))
            self.assertEqual(json.loads(ci.unpack(
                (directory / "run.json.gz").read_bytes())), run)
            self.assertEqual(json.loads(ci.unpack(
                (directory / "jobs-pages.json.gz").read_bytes())), pages)
            self.assertEqual((directory / "ci-native-platform.yml.gz").is_file(), True)
            self.assertEqual((directory / "replay.json.gz").is_file(), True)
            with self.assertRaises(ValueError):
                ci.capture(39088746696, directory)
