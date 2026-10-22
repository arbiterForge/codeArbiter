#!/usr/bin/env python3
"""Fail-closed CI20 matrix graph, tested-native input and shard regression contracts."""
from __future__ import annotations

import copy
import hashlib
import json
from pathlib import Path
import tempfile
import unittest
from unittest import mock

import ci20_native_binding as binding
import run_artifact_authority_shard as authority
from test_ci_impact import workflow_jobs

REPO = Path(__file__).resolve().parents[2]
SIX = sorted(binding.PLATFORMS)
STAGES = sorted(binding.REQUIRED_STAGES)
OWNERS = {
    "artifact-native-build": (
        "Build native qualified candidate",
    ),
    "artifact-native-default": (
        "Test artifact engine", "Vet artifact engine",
        "Race-test Linux persistence paths",
        "Verify generated artifact types", "Verify artifact public-surface baseline",
        "Verify artifact consumer inventory closure",
        "Verify SMARTS engine contract by exact test name",
        "Verify ship-set evidence-input behavior",
        "Verify named native storage and recovery contract",
        "Verify the finite context Go test bridge", "Verify named context document Go cases",
        "Reject missing and nonisolated installed context candidates",
        "Verify context workflow with the pinned Go toolchain",
    ),
    "artifact-native-coverage": (
        "Exercise the actual CLI with native statement instrumentation",
        "Collect native unit and executable statement coverage",
        "Preserve the native statement profiles",
    ),
    "artifact-native-bridges": (
        "Create locked reference-validation environment",
        "Verify protected greenfield population with the candidate",
        "Check out the fixed pre-assistive compatibility source",
        "Build the schema 0.3.1 compatibility client",
        "Verify two-client upgrade, complete restore and forward recovery",
        "Generate review examples with the native candidate",
        "Test host-owned bridges, reply capture and cross-kind conformance",
        "Test debug handoff model against the locked reference interpreter",
    ),
    "artifact-engine": (
        "Bind the candidate to this exact-host native result",
        "Preserve the exact native candidate and qualification receipt",
    ),
}


def successful_needs():
    result = {key: {"result": "success"} for key in binding.REQUIRED_STAGES}
    result["changes"]["outputs"] = {"artifacts": "true"}
    return result


class GateContract(unittest.TestCase):
    def test_complete_green_runs_qualify_and_every_failure_refuses(self):
        binding.require_stages(json.dumps(successful_needs()))
        for key in binding.REQUIRED_STAGES:
            for status in ("failure", "skipped", "cancelled", "pending", "", None):
                modified = successful_needs()
                modified[key]["result"] = status
                with self.subTest(group=key, status=status), self.assertRaises(ValueError):
                    binding.require_stages(json.dumps(modified))

    def test_missing_extra_partial_and_duplicate_need_are_refused(self):
        for key in binding.REQUIRED_STAGES:
            needs = successful_needs()
            del needs[key]
            with self.assertRaises(ValueError):
                binding.require_stages(json.dumps(needs))
        needs = successful_needs()
        needs["undeclared"] = {"result": "success"}
        with self.assertRaises(ValueError):
            binding.require_stages(json.dumps(needs))
        for raw in ('null', '{}', '[]', '{', '{"changes":{},"changes":{}}',
                    "x" * 65537):
            with self.assertRaises(ValueError):
                binding.require_stages(raw)
        needs = successful_needs()
        needs["changes"]["outputs"]["artifacts"] = "false"
        with self.assertRaises(ValueError):
            binding.require_stages(json.dumps(needs))


class GenuineNativeCandidateContract(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(prefix="ci20-tested-native-contract-")
        self.addCleanup(self.tmp.cleanup)
        self.path = Path(self.tmp.name)
        self.candidate = self.path / "candidate"
        self.candidate.mkdir()
        self.binary = self.candidate / "ca-artifact-windows-amd64.exe"
        # A synthetic manifest for refusal tests; never used as native proof.
        self.binary.write_bytes(b"synthetic tested-input-fixture")
        self.manifest = {
            "format": "codearbiter.artifact-release/0.1.0",
            "version": "0.1.0",
            "protocol": "codearbiter.artifact-api/0.1.0",
            "schema_version": "0.3.2",
            "binaries": {"windows/amd64": {
                "file": self.binary.name,
                "sha256": hashlib.sha256(self.binary.read_bytes()).hexdigest(),
                "native_tested": True}},
        }
        self.write_manifest()
        self.record_path = self.path / "ci20-native-tested.json"
        self.identity = {
            "format": binding.FORMAT,
            "source_commit": "a" * 40,
            "run_id": "234",
            "run_attempt": "1",
            "workflow": binding.WORKFLOW,
            "producer_job": binding.PRODUCER,
            "platform": "windows/amd64",
            "toolchain": "go1.27.1",
            "module_sha256": "b" * 64,
            "go_sha256": "c" * 64,
        }
        patched = mock.patch.object(binding, "ci_identity", return_value=self.identity)
        patched.start()
        self.addCleanup(patched.stop)

    def write_manifest(self):
        (self.candidate / "release.json").write_text(
            json.dumps(self.manifest), encoding="utf-8")

    def stamp(self):
        with mock.patch.dict(binding.os.environ, GITHUB_JOB=binding.PRODUCER):
            return binding.stamp(self.candidate, self.record_path, "windows/amd64")

    def test_only_original_native_builder_can_stamp(self):
        with mock.patch.dict(binding.os.environ, GITHUB_JOB="artifact-engine"):
            with self.assertRaises(ValueError):
                self.stamp_called_directly()
        self.stamp()
        with self.assertRaises(FileExistsError):
            self.stamp()

    def stamp_called_directly(self):
        binding.stamp(self.candidate, self.record_path, "windows/amd64")

    def test_verification_never_qualifies_or_modifies_manifest(self):
        stamped = self.stamp()
        before = (self.candidate / "release.json").read_bytes()
        for owner in binding.CONSUMERS:
            with mock.patch.dict(binding.os.environ, GITHUB_JOB=owner):
                self.assertEqual(binding.verify(
                    self.candidate, self.record_path, "windows/amd64"), stamped)
        self.assertEqual((self.candidate / "release.json").read_bytes(), before)
        with mock.patch.dict(binding.os.environ, GITHUB_JOB="artifact-browser"):
            with self.assertRaises(ValueError):
                binding.verify(self.candidate, self.record_path, "windows/amd64")

    def test_unqualified_forged_and_changed_bytes_refuse(self):
        self.stamp()
        self.manifest["binaries"]["windows/amd64"]["native_tested"] = False
        self.write_manifest()
        with mock.patch.dict(binding.os.environ, GITHUB_JOB="artifact-engine"):
            with self.assertRaises(ValueError):
                binding.verify(self.candidate, self.record_path, "windows/amd64")
        self.manifest["binaries"]["windows/amd64"]["native_tested"] = True
        self.write_manifest()
        self.binary.write_bytes(b"modified")
        with mock.patch.dict(binding.os.environ, GITHUB_JOB="artifact-engine"):
            with self.assertRaises(ValueError):
                binding.verify(self.candidate, self.record_path, "windows/amd64")

    def test_source_tool_run_attempt_and_unexpected_inputs_refuse(self):
        stamped = self.stamp()
        for field in stamped:
            if field == "run_attempt":
                continue
            self.record_path.write_text(json.dumps({**stamped, field: "changed"}))
            with mock.patch.dict(binding.os.environ, GITHUB_JOB="artifact-engine"):
                with self.subTest(field=field), self.assertRaises(ValueError):
                    binding.verify(self.candidate, self.record_path, "windows/amd64")
        self.record_path.write_text(json.dumps(stamped))
        self.identity["run_attempt"] = "2"
        with mock.patch.dict(binding.os.environ, GITHUB_JOB="artifact-engine"):
            binding.verify(self.candidate, self.record_path, "windows/amd64")
        self.record_path.write_text(json.dumps({**stamped, "run_attempt": "3"}))
        with mock.patch.dict(binding.os.environ, GITHUB_JOB="artifact-engine"):
            with self.assertRaises(ValueError):
                binding.verify(self.candidate, self.record_path, "windows/amd64")
        extra = self.candidate / "unexpected"
        extra.write_text("not a supported tested-candidate file")
        with self.assertRaises(ValueError):
            binding.candidate_identity(self.candidate, "windows/amd64")


class ShardContract(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.cases = authority.discover()
        cls.weights = authority.load_weights()

    def test_dynamic_discovery_disjoint_nonempty_complete_and_class_atomic(self):
        shards, estimates = authority.partition(self.cases, 4, self.weights)
        expected = sorted(case.id() for case in self.cases)
        self.assertEqual(sorted(case.id() for shard in shards for case in shard), expected)
        self.assertTrue(all(shards))
        self.assertEqual(len(expected), len(set(expected)))
        owners = {}
        for index, shard in enumerate(shards):
            for case in shard:
                key = authority.class_id(case)
                self.assertEqual(owners.setdefault(key, index), index)
        self.assertTrue(all(value > 0 for value in estimates))
        reversed_parts, _ = authority.partition(list(reversed(self.cases)), 4, self.weights)
        self.assertEqual([[c.id() for c in part] for part in shards],
                         [[c.id() for c in part] for part in reversed_parts])

    def test_unknown_future_classes_are_included_not_filtered_by_history(self):
        added_type = type("NewTestClass", (unittest.TestCase,),
                          {"test_new_case": lambda self: None})
        extra = added_type("test_new_case")
        parts, _ = authority.partition(self.cases + [extra], 4, self.weights)
        self.assertIn(extra.id(), [case.id() for part in parts for case in part])
        self.assertNotIn(authority.class_id(extra), self.weights)

    def test_concurrent_shard_results_must_prove_the_whole_population(self):
        expected = ["a.T.test_1", "a.T.test_2", "b.U.test_3"]
        good = [{"plan_sha256": "p", "selected_ids": ["a.T.test_1", "a.T.test_2"], "passed": True},
                {"plan_sha256": "p", "selected_ids": ["b.U.test_3"], "passed": True}]
        self.assertEqual(authority.coverage_problems([0, 0], good, expected), [])
        cases = {
            "child exit": ([0, 1], good, "shard 1 exited 1"),
            "missing observation": ([0, 0], [good[0], None], "shard 1 wrote no observation"),
            "plan disagreement": ([0, 0], [good[0], dict(good[1], plan_sha256="q")], "disagree"),
            "dropped test": ([0, 0], [good[0], dict(good[1], selected_ids=[])], "exactly once"),
            "repeated test": ([0, 0], [good[0], dict(good[1], selected_ids=["b.U.test_3", "a.T.test_1"])],
                              "exactly once"),
            "unpassed shard": ([0, 0], [good[0], dict(good[1], passed=False)], "did not pass"),
        }
        for label, (codes, reports, problem) in cases.items():
            with self.subTest(label=label):
                self.assertTrue(any(problem in found for found in authority.coverage_problems(codes, reports, expected)))
        self.assertEqual(authority.coverage_problems([0, 0], good, expected, "p"), [])
        self.assertTrue(any("disagree" in found for found in authority.coverage_problems([0, 0], good, expected, "q")))

    def test_split_jobs_cover_every_partition_exactly_once(self):
        for count, groups in ((4, 1), (8, 2), (8, 3), (5, 5)):
            with self.subTest(count=count, groups=groups):
                covered = [index for group in range(groups)
                           for index in authority.group_indexes(count, groups, group)]
                self.assertEqual(sorted(covered), list(range(count)))
                self.assertTrue(all(authority.group_indexes(count, groups, group) for group in range(groups)))
        for count, groups, group in ((4, 0, 0), (4, 5, 0), (8, 2, 2), (8, 2, -1)):
            with self.subTest(count=count, groups=groups, group=group), self.assertRaises(ValueError):
                authority.group_indexes(count, groups, group)


class WorkflowContract(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.ci = (REPO / ".github/workflows/ci.yml").read_text(encoding="utf-8")
        cls.jobs = workflow_jobs(cls.ci)

    def test_named_validation_steps_have_one_owner_and_six_actual_platforms(self):
        for owner, steps in OWNERS.items():
            text = self.jobs[owner]
            for name in steps:
                self.assertEqual(sum(f"      - name: {name}\n" in body
                                     for body in self.jobs.values()), 1, name)
                self.assertIn(f"      - name: {name}\n", text)
            for platform in SIX:
                self.assertIn("expected_platform: " + platform, text, owner)
            self.assertIn("fail-fast: false", text)
            self.assertNotIn("continue-on-error:", text)
        self.assertNotIn("--skip-tests", self.jobs["artifact-native-build"])
        self.assertIn("python tools/build-artifacts.py --output", self.jobs["artifact-native-build"])

    def test_full_coverage_and_platform_specific_checks_stay_required(self):
        self.assertIn("python tools/go_test_parallel.py --module core/artifacts --timeout 20m", self.jobs["artifact-native-default"])
        self.assertIn("go vet -buildvcs=false ./...", self.jobs["artifact-native-default"])
        self.assertIn("python tools/go_test_parallel.py --module core/artifacts --build-flag=-race", self.jobs["artifact-native-default"])
        self.assertIn("test_smarts_engine_contract.py", self.jobs["artifact-native-default"])
        self.assertIn("test_ship_set_inputs.py", self.jobs["artifact-native-default"])
        self.assertIn("test_artifact_cli.py --coverage-output", self.jobs["artifact-native-coverage"])
        self.assertIn("tools/artifact-coverage.py collect", self.jobs["artifact-native-coverage"])
        self.assertIn("artifact-statements-", self.jobs["artifact-native-coverage"])
        coverage = self.jobs["artifact-coverage"]
        self.assertIn("needs: [changes, artifact-native-coverage]", coverage)
        self.assertIn('"70"', coverage)
        self.assertIn("--require-integration", coverage)

    def test_tested_candidate_is_shared_and_gated_but_only_native_issuer_qualifies(self):
        for owner in ("artifact-native-bridges", "artifact-authority", "artifact-engine"):
            text = self.jobs[owner]
            self.assertIn("ci20_native_binding.py verify", text)
            self.assertIn("ci20-native-tested-", text)
            self.assertNotIn("tools/build-artifacts.py --output", text)
        self.assertIn("ci20_native_binding.py stamp", self.jobs["artifact-native-build"])
        final = self.jobs["artifact-engine"]
        self.assertIn("NATIVE_RESULTS: ${{ toJSON(needs) }}", final)
        self.assertIn("ci20_native_binding.py gate", final)
        self.assertLess(final.index("ci20_native_binding.py gate"),
                        final.index("--qualify-existing"))
        self.assertLess(final.index("ci20_native_binding.py verify"),
                        final.index("--qualify-existing"))
        self.assertIn("ci20-native-context-", final)
        self.assertIn("--context-native-observation", final)
        for group in binding.REQUIRED_STAGES:
            self.assertIn(group, final.split("    needs:", 1)[1].splitlines()[0])
        self.assertNotIn("CA_ARTIFACT_QUALIFICATION_JOB", final)

    def test_all_four_shards_per_platform_and_gate_registrations(self):
        authority_job = self.jobs["artifact-authority"]
        self.assertIn("actions/setup-node@949feb2413d6458794dcd2491c4babbbce0c15c1", authority_job)
        self.assertIn("node-version: 22.19.0", authority_job)
        for platform in SIX:
            self.assertEqual(authority_job.count("expected_platform: " + platform), 1)
        self.assertIn("AUTHORITY_SHARD: all", authority_job)
        self.assertIn('AUTHORITY_SHARD_COUNT: "4"', authority_job)
        self.assertNotIn("matrix.shard", authority_job)
        self.assertNotIn("upload-artifact", authority_job)
        aggregate = self.jobs["ci-passed"]
        for owner in OWNERS:
            self.assertIn("\n      - " + owner + "\n", aggregate)
            self.assertIn("needs['" + owner + "'].result", aggregate)
        self.assertIn("\n      - artifact-authority\n", aggregate)
        self.assertIn("needs['artifact-authority'].result", aggregate)
        self.assertIn("name: artifact-native-${{ matrix.os }}", self.jobs["artifact-engine"])
        self.assertIn("needs: [changes, artifact-package-assembly]", self.jobs["artifact-package-cold"])
        # Consumers reuse the module-tested candidate; no untested early build or
        # provisional byte-correspondence job remains in the graph.
        self.assertNotIn("artifact-ci-build", self.ci)
        self.assertNotIn("ci20_correspondence.py", self.ci)

    def test_early_ci_executes_new_proofs(self):
        self.assertIn("run: python .github/scripts/test_ci20_native_pipeline.py",
                      self.jobs["ci-impact"])



class HostedCheckPaginationContract(unittest.TestCase):
    def test_complete_multi_page_population_and_partial_response(self):
        import verify_pi_support as checker
        from types import SimpleNamespace
        sha = "a" * 40
        pages = [
            {"total_count": 101, "check_runs": [{"id": index + 1} for index in range(100)]},
            {"total_count": 101, "check_runs": [{"id": 101}]},
        ]
        def read(all_pages):
            with mock.patch.object(checker.shutil, "which", return_value="gh"), \
                    mock.patch.object(checker.subprocess, "run", return_value=SimpleNamespace(
                        returncode=0, stdout=json.dumps(all_pages))), \
                    mock.patch.object(checker, "_hosted_checks_match", return_value=True) as matching:
                accepted = checker._load_hosted_checks(REPO, sha)
                if accepted:
                    self.assertEqual(len(matching.call_args.args[0]), 101)
                return accepted
        self.assertTrue(read(pages))
        self.assertFalse(read(pages[:1]))
        duplicated = copy.deepcopy(pages)
        duplicated[1]["check_runs"][0]["id"] = 1
        self.assertFalse(read(duplicated))
        inconsistent = copy.deepcopy(pages)
        inconsistent[1]["total_count"] = 102
        self.assertFalse(read(inconsistent))


if __name__ == "__main__":
    unittest.main(verbosity=2)
