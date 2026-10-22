#!/usr/bin/env python3
"""Fail-closed CI20 matrix graph, tested-native input and shard regression contracts."""
from __future__ import annotations

import copy
import hashlib
import importlib.util
import json
import re
from pathlib import Path
import sys
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
        "Bind each candidate to its recorded native result",
        "Preserve the exact native candidate and qualification receipt (linux/amd64)",
        "Preserve the exact native candidate and qualification receipt (linux/arm64)",
        "Preserve the exact native candidate and qualification receipt (windows/amd64)",
        "Preserve the exact native candidate and qualification receipt (windows/arm64)",
        "Preserve the exact native candidate and qualification receipt (darwin/amd64)",
        "Preserve the exact native candidate and qualification receipt (darwin/arm64)",
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


class NativeCandidateFixture:
    """A synthetic stamped candidate; mixed into contract test cases."""

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


class GenuineNativeCandidateContract(NativeCandidateFixture, unittest.TestCase):
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
            self.assertNotIn("continue-on-error:", text)
            if owner == "artifact-engine":
                # The single issuer names each platform in its receipt steps.
                self.assertNotIn("strategy:", text)
                continue
            for platform in SIX:
                self.assertIn("expected_platform: " + platform, text, owner)
            self.assertIn("fail-fast: false", text)
        self.assertNotIn("--skip-tests", self.jobs["artifact-native-build"])
        self.assertIn("python tools/build-artifacts.py --output", self.jobs["artifact-native-build"])

    def test_full_coverage_and_platform_specific_checks_stay_required(self):
        # The tested build owns the complete module population and vet; a
        # second full run elsewhere in the same run is duplicate work.
        builder = (REPO / "tools/build-artifacts.py").read_text(encoding="utf-8")
        self.assertIn('str(repo / "tools/go_test_parallel.py"), "--module", str(module)', builder)
        self.assertIn('subprocess.run(["go", "vet", "./..."], cwd=module, env=env, check=True)', builder)
        self.assertIn("if not args.skip_tests:", builder)
        for owner, text in self.jobs.items():
            with self.subTest(job=owner):
                self.assertNotIn("--module core/artifacts --timeout", text)
                self.assertNotIn("go vet", text)
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
        for owner in ("artifact-native-bridges", "artifact-authority"):
            text = self.jobs[owner]
            self.assertIn("ci20_native_binding.py verify", text)
            self.assertIn("ci20-native-tested-", text)
            self.assertNotIn("tools/build-artifacts.py --output", text)
        self.assertIn("ci20_native_binding.py stamp", self.jobs["artifact-native-build"])
        final = self.jobs["artifact-engine"]
        self.assertNotIn("tools/build-artifacts.py --output", final)
        self.assertIn("NATIVE_RESULTS: ${{ toJSON(needs) }}", final)
        self.assertIn("ci20_native_binding.py gate", final)
        self.assertIn("pattern: ci20-native-*", final)
        self.assertLess(final.index("ci20_native_binding.py gate"),
                        final.index("pattern: ci20-native-*"))
        self.assertLess(final.index("pattern: ci20-native-*"),
                        final.index("ci20_native_binding.py qualify-recorded"))
        # The off-host issuer only checks the Go digest's shape; its soundness
        # rests on each native consumer verifying the stamp on every platform.
        for owner in ("artifact-native-bridges", "artifact-authority"):
            steps = re.findall(r"(?ms)^      - name: [^\n]*\n(?:(?!^      - ).)*", self.jobs[owner])
            verifies = [step for step in steps if "ci20_native_binding.py verify" in step]
            self.assertGreaterEqual(len(verifies), 1, owner)
            for step in verifies:
                self.assertNotIn("        if:", step, owner)
            self.assertNotIn("\n    if: matrix", self.jobs[owner])
        # The issuer passes each platform's recorded binding and context
        # observation to the protected emitter.
        source = (REPO / ".github/scripts/ci20_native_binding.py").read_text(encoding="utf-8")
        for argument in ('"--qualify-existing"', '"--native-binding"', '"--context-native-observation"'):
            self.assertIn(argument, source)
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
        for runner, platform in sorted(binding.RUNNERS.items()):
            self.assertIn("name: artifact-native-" + runner + "\n", self.jobs["artifact-engine"])
        self.assertIn("needs: [changes, artifact-package-assembly]", self.jobs["artifact-package-cold"])
        # Consumers reuse the module-tested candidate; no untested early build or
        # provisional byte-correspondence job remains in the graph.
        self.assertNotIn("artifact-ci-build", self.ci)
        self.assertNotIn("ci20_correspondence.py", self.ci)

    def test_early_ci_executes_new_proofs(self):
        self.assertIn("run: python .github/scripts/test_ci20_native_pipeline.py",
                      self.jobs["ci-impact"])



BUILDER_SPEC = importlib.util.spec_from_file_location("ci20_builder", REPO / "tools/build-artifacts.py")
BUILDER = importlib.util.module_from_spec(BUILDER_SPEC)
BUILDER_SPEC.loader.exec_module(BUILDER)


class RecordedQualificationContract(NativeCandidateFixture, unittest.TestCase):
    """CI20-04: one off-host issuer, bound to each platform's same-run stamp."""

    RUN = {"source_commit": "a" * 40, "run_id": "234", "run_attempt": "1"}

    def setUp(self):
        super().setUp()
        for name, value in (("run_identity", dict(self.RUN)), ("hash_go_module", "b" * 64)):
            patched = mock.patch.object(binding, name, return_value=value)
            patched.start()
            self.addCleanup(patched.stop)
        self.stamped = self.stamp()

    def recorded(self, job="artifact-engine", platform="windows/amd64"):
        with mock.patch.dict(binding.os.environ, GITHUB_JOB=job):
            return binding.recorded(self.candidate, self.record_path, platform)

    def test_only_the_issuer_accepts_an_exact_record(self):
        self.assertEqual(self.recorded(), self.stamped)
        for job in ("artifact-native-bridges", "artifact-authority", "artifact-native-build", ""):
            with self.subTest(job=job), self.assertRaises(ValueError):
                self.recorded(job=job)
        with self.assertRaises(ValueError):
            self.recorded(platform="darwin/arm64")

    def test_every_changed_missing_or_extra_field_refuses(self):
        for field in self.stamped:
            if field == "run_attempt":
                continue
            self.record_path.write_text(json.dumps({**self.stamped, field: "changed"}))
            with self.subTest(field=field), self.assertRaises(ValueError):
                self.recorded()
        for field in self.stamped:
            reduced = {key: value for key, value in self.stamped.items() if key != field}
            self.record_path.write_text(json.dumps(reduced))
            with self.subTest(missing=field), self.assertRaises(ValueError):
                self.recorded()
        self.record_path.write_text(json.dumps({**self.stamped, "native_proof": "PASS"}))
        with self.assertRaises(ValueError):
            self.recorded()

    def test_retry_reuses_only_an_earlier_attempt_of_this_run(self):
        with mock.patch.object(binding, "run_identity", return_value={**self.RUN, "run_attempt": "2"}):
            self.assertEqual(self.recorded()["run_attempt"], "1")
        self.record_path.write_text(json.dumps({**self.stamped, "run_attempt": "2"}))
        with self.assertRaises(ValueError):
            self.recorded()
        self.record_path.write_text(json.dumps(self.stamped))
        with mock.patch.object(binding, "run_identity", return_value={**self.RUN, "run_id": "235"}):
            with self.assertRaises(ValueError):
                self.recorded()

    def test_source_module_and_byte_drift_refuse(self):
        with mock.patch.object(binding, "run_identity", return_value={**self.RUN, "source_commit": "e" * 40}):
            with self.assertRaises(ValueError):
                self.recorded()
        with mock.patch.object(binding, "hash_go_module", return_value="d" * 64):
            with self.assertRaises(ValueError):
                self.recorded()
        self.binary.write_bytes(b"substituted after stamping")
        with self.assertRaises(ValueError):
            self.recorded()

    def records(self, root, runners):
        for runner in runners:
            for kind in ("tested", "context"):
                (root / f"ci20-native-{kind}-{runner}").mkdir()

    def test_issuer_requires_exactly_one_tested_and_context_record_per_platform(self):
        complete = sorted(binding.RUNNERS)
        cases = {
            "missing": complete[1:],
            "extra": [*complete, "macos-14"],
        }
        for label, runners in cases.items():
            with self.subTest(label), tempfile.TemporaryDirectory() as directory:
                root = Path(directory)
                self.records(root, runners)
                with mock.patch.object(binding.subprocess, "run") as run, \
                        mock.patch.dict(binding.os.environ, GITHUB_JOB="artifact-engine"):
                    with self.assertRaises(ValueError):
                        binding.qualify_recorded(root)
                    run.assert_not_called()
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            self.records(root, complete)
            (root / "ci20-native-context-macos-26").rmdir()
            with mock.patch.object(binding.subprocess, "run") as run, \
                    mock.patch.dict(binding.os.environ, GITHUB_JOB="artifact-engine"):
                with self.assertRaises(ValueError):
                    binding.qualify_recorded(root)
                run.assert_not_called()

    def test_issuer_qualifies_each_platform_with_its_own_records(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            self.records(root, binding.RUNNERS)
            with mock.patch.object(binding.subprocess, "run") as run, \
                    mock.patch.dict(binding.os.environ, GITHUB_JOB="artifact-bridges"):
                with self.assertRaises(ValueError):
                    binding.qualify_recorded(root)
                run.assert_not_called()
            with mock.patch.object(binding.subprocess, "run") as run, \
                    mock.patch.dict(binding.os.environ, GITHUB_JOB="artifact-engine"):
                receipts = binding.qualify_recorded(root)
        self.assertEqual(len(receipts), 6)
        seen = {}
        for call in run.call_args_list:
            command, environment = call.args[0], call.kwargs["env"]
            self.assertTrue(call.kwargs["check"])
            runner = Path(command[command.index("--qualify-existing") + 1]).parent.name.removeprefix(
                "ci20-native-tested-")
            seen[runner] = environment["EXPECTED_ARTIFACT_PLATFORM"]
            self.assertEqual(Path(command[command.index("--native-binding") + 1]),
                             root / f"ci20-native-tested-{runner}" / "ci20-native-tested.json")
            self.assertEqual(Path(command[command.index("--context-native-observation") + 1]),
                             root / f"ci20-native-context-{runner}" / "context-native-observation.json")
        self.assertEqual(seen, binding.RUNNERS)


class RecordedEmitterContract(NativeCandidateFixture, unittest.TestCase):
    """The protected emitter takes host identity from the stamp only when recorded."""

    def setUp(self):
        super().setUp()
        self.stamped = self.stamp()
        self.environment = {
            "GITHUB_ACTIONS": "true", "GITHUB_SHA": "a" * 40, "GITHUB_RUN_ID": "234",
            "GITHUB_WORKFLOW_REF": "arbiterForge/codeArbiter/.github/workflows/ci.yml@refs/heads/main",
            "GITHUB_JOB": "artifact-engine", "EXPECTED_ARTIFACT_PLATFORM": "windows/amd64",
        }
        self.module_sha256 = binding.hash_go_module(REPO / "core/artifacts")

    def observation(self, go_sha256):
        sys.path.insert(0, str(REPO / ".github/scripts"))
        try:
            import test_context_native as context
        finally:
            sys.path.remove(str(REPO / ".github/scripts"))
        sources = {
            "TestContextRepresentationBoundary": (context.SOURCE, context.SUBTESTS),
            "TestContextDocumentContract": (context.DOCUMENT_SOURCE, context.DOCUMENT_SUBTESTS),
            "TestContextMarkdownPreservation": (context.MARKDOWN_SOURCE, context.MARKDOWN_SUBTESTS),
            "TestContextBoundedRender": (context.RENDER_SOURCE, context.RENDER_SUBTESTS),
            "TestContextMutationAdmission": (context.MUTATION_SOURCE, context.MUTATION_SUBTESTS),
            "TestContextRecoveryAndPaths": (context.RECOVERY_SOURCE, context.RECOVERY_SUBTESTS),
        }
        record = {
            "format": "codearbiter.context-native-observation/0.1.0",
            "module_sha256": self.module_sha256, "go_sha256": go_sha256,
            "cases": [{"name": name, "subtests": list(subtests),
                       "source_sha256": hashlib.sha256(source.read_bytes()).hexdigest(),
                       "stdout_sha256": "1" * 64, "stderr_sha256": "2" * 64, "exit_code": 0}
                      for name, (source, subtests) in sources.items()],
        }
        path = self.path / "context-native-observation.json"
        path.write_text(json.dumps(record), encoding="utf-8")
        return path

    def emit(self, observation, recorded):
        def checked_output(args, **_kwargs):
            if args[:3] == ["git", "rev-parse", "HEAD"]:
                return "a" * 40 + "\n"
            raise AssertionError("an off-host issuer must not consult the local toolchain: %r" % (args,))
        destination = self.path / "receipt.json"
        if destination.exists():
            destination.unlink()
        with mock.patch.dict(BUILDER.os.environ, self.environment, clear=True), \
                mock.patch.object(BUILDER.subprocess, "check_output", side_effect=checked_output), \
                mock.patch.object(binding, "recorded", return_value=recorded) as check:
            BUILDER.write_qualification(self.candidate, destination, observation, self.record_path)
        check.assert_called_once_with(self.candidate, self.record_path, "windows/amd64")
        return json.loads(destination.read_text(encoding="utf-8"))

    def test_receipt_shape_is_unchanged_and_bound_to_the_recorded_go_tool(self):
        stamped = {**self.stamped, "module_sha256": self.module_sha256}
        receipt = self.emit(self.observation(stamped["go_sha256"]), stamped)
        self.assertEqual(set(receipt), {
            "format", "source_commit", "workflow", "run_id", "job", "platform",
            "binary_sha256", "version", "protocol", "schema_version", "native_tests",
            "context_native"})
        self.assertEqual((receipt["job"], receipt["platform"]), ("artifact-engine", "windows/amd64"))
        self.assertEqual(receipt["context_native"]["go_sha256"], stamped["go_sha256"])

    def test_context_from_another_go_tool_or_none_refuses(self):
        stamped = {**self.stamped, "module_sha256": self.module_sha256}
        with self.assertRaisesRegex(ValueError, "source/tool identity"):
            self.emit(self.observation("f" * 64), stamped)
        with self.assertRaisesRegex(SystemExit, "requires the native context observation"):
            self.emit(None, stamped)
        self.assertFalse((self.path / "receipt.json").exists())

    def test_host_path_still_requires_this_hosts_toolchain(self):
        def host(goos, goarch):
            def checked_output(args, **_kwargs):
                if args[:3] == ["git", "rev-parse", "HEAD"]:
                    return "a" * 40 + "\n"
                return {("go", "env", "GOOS"): goos, ("go", "env", "GOARCH"): goarch}[tuple(args)] + "\n"
            return checked_output
        destination = self.path / "host-receipt.json"
        with mock.patch.dict(BUILDER.os.environ, self.environment, clear=True), \
                mock.patch.object(BUILDER.subprocess, "check_output", side_effect=host("darwin", "arm64")):
            with self.assertRaisesRegex(SystemExit, "candidate platform does not match"):
                BUILDER.write_qualification(self.candidate, destination)
        self.assertFalse(destination.exists())
        with mock.patch.dict(BUILDER.os.environ, self.environment, clear=True), \
                mock.patch.object(BUILDER.subprocess, "check_output", side_effect=host("windows", "amd64")):
            BUILDER.write_qualification(self.candidate, destination)
        self.assertEqual(json.loads(destination.read_text(encoding="utf-8"))["platform"], "windows/amd64")

    def test_platform_other_than_the_candidate_refuses(self):
        self.environment["EXPECTED_ARTIFACT_PLATFORM"] = "darwin/arm64"
        stamped = {**self.stamped, "module_sha256": self.module_sha256}
        with self.assertRaisesRegex(SystemExit, "candidate platform does not match"):
            self.emit(self.observation(stamped["go_sha256"]), stamped)


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
