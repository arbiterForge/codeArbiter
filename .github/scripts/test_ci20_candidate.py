#!/usr/bin/env python3
"""Negative tests for provisional CI test inputs; never weaken ArtifactClient."""
from __future__ import annotations

import copy
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest import mock

import ci20_candidate as ci

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO / "core/pysrc"))
from _artifactlib import ArtifactClient, ArtifactError  # noqa: E402


def fixture_identity() -> dict[str, str]:
    return {
        "source_commit": "a" * 40, "run_id": "123", "run_attempt": "1",
        "workflow_ref": "arbiterForge/codeArbiter/.github/workflows/ci.yml@refs/pull/42/merge",
        "platform": "windows/amd64", "go_version": ci.GO_VERSION,
        "go_sha256": "b" * 64, "module_sha256": "c" * 64,
    }


class CandidateContractTest(unittest.TestCase):
    """The temporary format must not be mistaken for a tested installation."""

    def setUp(self):
        self.owner = tempfile.TemporaryDirectory(prefix="ci20-provisional-")
        self.addCleanup(self.owner.cleanup)
        self.root = Path(self.owner.name).resolve()
        self.out = self.root / "candidate"
        self.identity = fixture_identity()
        self.env = {"RUNNER_TEMP": str(self.root)}
        self.calls = []

    def fake_compiler(self, argv, **kwargs):
        self.calls.append((argv, kwargs))
        self.assertEqual(argv[:5], ["go", "build", "-trimpath",
                                     "-buildvcs=false", "-ldflags=-s -w"])
        self.assertEqual(argv[-1], "./cmd/ca-artifact")
        self.assertEqual(kwargs["cwd"], ci.MODULE)
        self.assertEqual(kwargs["env"]["CGO_ENABLED"], "0")
        self.assertEqual(kwargs["env"]["GOPROXY"], "off")
        self.assertEqual(kwargs["env"]["GOTOOLCHAIN"], "local")
        self.assertTrue(kwargs["check"])
        self.assertEqual(kwargs["timeout"], 300)
        Path(argv[-2]).write_bytes(b"MZ" + b"fake direct-test input")
        return subprocess.CompletedProcess(argv, 0)

    def build(self):
        with mock.patch.object(ci.subprocess, "run", side_effect=self.fake_compiler):
            return ci.build(self.out, self.identity, ambient=self.env)

    def test_provisional_build_and_verify_never_claim_native_tested(self):
        manifest = self.build()
        self.assertEqual(len(self.calls), 1)
        self.assertEqual({x.name for x in self.out.iterdir()},
                         {"ci-input.json", "ca-artifact-windows-amd64.exe"})
        self.assertNotIn("native_tested", manifest)
        self.assertNotIn("release.json", str(manifest))
        self.assertNotIn("qualification", str(manifest))
        self.assertEqual(manifest["state"], ci.STATE)
        self.assertEqual(manifest["format"], ci.FORMAT)
        self.assertEqual(ci.verify(self.out, self.identity).read_bytes(),
                         b"MZfake direct-test input")
        self.assertEqual(json.loads((self.out / "ci-input.json").read_text()), manifest)

    def test_ordinary_installed_artifact_client_refuses_provisional_input(self):
        self.build()
        with self.assertRaises(ArtifactError) as failure:
            ArtifactClient(self.root, self.out)._open_binary()
        self.assertIn(failure.exception.code, {"CAPABILITY_MISSING", "INVALID_INSTALLATION"})
        # Inventing an ordinary release.json with the provisional schema must
        # not turn it into an installed payload either.
        (self.out / "release.json").write_bytes((self.out / "ci-input.json").read_bytes())
        with self.assertRaises(ArtifactError):
            ArtifactClient(self.root, self.out)._open_binary()
        with self.assertRaises(ValueError):
            ci.verify(self.out, self.identity)

    def test_existing_ordinary_qualification_cannot_consume_provisional_input(self):
        self.build()
        import importlib.util
        spec = importlib.util.spec_from_file_location(
            "builder_ci20_test", REPO / "tools/build-artifacts.py")
        builder = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(builder)
        dest = self.root / "qualified.json"
        # Even inside the old authorized CI job, the provisional directory
        # has no release manifest and cannot satisfy qualification admission.
        with mock.patch.dict(os.environ, {
            "GITHUB_ACTIONS": "true", "GITHUB_JOB": "artifact-engine",
            "GITHUB_SHA": self.identity["source_commit"],
            "GITHUB_RUN_ID": self.identity["run_id"],
            "GITHUB_WORKFLOW_REF": self.identity["workflow_ref"],
            "EXPECTED_ARTIFACT_PLATFORM": self.identity["platform"],
        }):
            with mock.patch.object(builder.subprocess, "check_output",
                                   return_value=self.identity["source_commit"]):
                with self.assertRaisesRegex(FileNotFoundError, r"release\.json"):
                    builder.write_qualification(self.out, dest)
        self.assertFalse(dest.exists())

    def test_reject_changed_binary_even_if_record_still_says_success(self):
        self.build()
        (self.out / ci._filename(self.identity["platform"])).write_bytes(b"changed")
        with self.assertRaisesRegex(ValueError, "mismatch"):
            ci.verify(self.out, self.identity)

    def test_reject_cross_run_source_platform_tool_and_build_flag_substitution(self):
        record = self.build()
        for key in ("source_commit", "run_id", "workflow_ref", "platform",
                    "go_version", "go_sha256", "module_sha256"):
            changed = {**self.identity, key: "wrong"}
            with self.subTest(identity=key), self.assertRaises(ValueError):
                ci.verify(self.out, changed)
        for key in ("build_flags", "build_environment", "state", "format"):
            altered = copy.deepcopy(record)
            altered[key] = "forged"
            (self.out / "ci-input.json").write_text(json.dumps(altered))
            with self.subTest(record=key), self.assertRaises(ValueError):
                ci.verify(self.out, self.identity)
        (self.out / "ci-input.json").write_text(json.dumps(record))

    def test_reject_missing_duplicate_extra_and_non_finite_metadata(self):
        record = self.build()
        bad = [
            "{}", "[]", "null", "{", '{"state":"unqualified","state":"qualified"}',
            json.dumps({**record, "native_tested": True}),
            json.dumps({**record, "tests_passed": True}),
            json.dumps({**record, "extra": "value"}),
            json.dumps({**record, "binary": {**record["binary"], "size": float("nan")}}),
            " " * (ci.MAX_MANIFEST + 1),
        ]
        for raw in bad:
            (self.out / "ci-input.json").write_text(raw)
            with self.subTest(raw=raw[:45]), self.assertRaises((ValueError, TypeError)):
                ci.verify(self.out, self.identity)

    def test_future_attempt_refuses_but_earlier_producer_from_same_run_is_allowed(self):
        original = self.build()
        self.assertEqual(ci.verify(self.out, {**self.identity, "run_attempt": "2"}).name,
                         ci._filename(self.identity["platform"]))
        self.assertEqual(ci.verify(self.out, {**self.identity, "run_attempt": "5"}).name,
                         ci._filename(self.identity["platform"]))
        record = {**original, "producer_attempt": "6"}
        (self.out / "ci-input.json").write_text(json.dumps(record))
        with self.assertRaises(ValueError):
            ci.verify(self.out, {**self.identity, "run_attempt": "5"})
        for value in (0, -1, True, "", "01", None, "abc"):
            (self.out / "ci-input.json").write_text(json.dumps({
                **original, "producer_attempt": value}))
            with self.subTest(attempt=value), self.assertRaises(ValueError):
                ci.verify(self.out, self.identity)

    def test_reject_extra_release_payload_symlink_and_nonfile_bytes(self):
        self.build()
        extra = self.out / "release.json"
        extra.write_text("{}")
        with self.assertRaisesRegex(ValueError, "release or extra"):
            ci.verify(self.out, self.identity)
        extra.unlink()
        binary = self.out / ci._filename(self.identity["platform"])
        binary.unlink()
        binary.mkdir()
        with self.assertRaises(ValueError):
            ci.verify(self.out, self.identity)
        binary.rmdir()
        outside = self.root / "outside.exe"
        outside.write_bytes(b"not trusted")
        try:
            binary.symlink_to(outside)
        except OSError:
            self.skipTest("Windows policy disallows symlinks")
        with self.assertRaises(ValueError):
            ci.verify(self.out, self.identity)
        self.assertEqual(outside.read_bytes(), b"not trusted")

    def test_output_bound_and_overwrite_fail_without_compiler_execution(self):
        with mock.patch.object(ci.subprocess, "run", side_effect=self.fake_compiler):
            with self.assertRaises(ValueError):
                ci.build(self.root / "elsewhere" / "new", self.identity,
                         ambient=self.env)
            self.assertEqual(len(self.calls), 0)
        self.build()
        with mock.patch.object(ci.subprocess, "run", side_effect=self.fake_compiler):
            with self.assertRaises(ValueError):
                ci.build(self.out, self.identity, ambient=self.env)
        self.assertEqual(len(self.calls), 1)

    def test_midbuild_output_race_does_not_replace_existing_contents(self):
        def competitor(argv, **kwargs):
            self.fake_compiler(argv, **kwargs)
            self.out.mkdir()
            (self.out / "owned").write_text("preexisting", encoding="utf-8")
            return subprocess.CompletedProcess(argv, 0)
        with mock.patch.object(ci.subprocess, "run", side_effect=competitor):
            with self.assertRaises(ValueError):
                ci.build(self.out, self.identity, ambient=self.env)
        self.assertEqual((self.out / "owned").read_text(encoding="utf-8"), "preexisting")
        self.assertFalse((self.out / "ci-input.json").exists())

    def test_candidate_directory_link_is_never_admitted(self):
        self.build()
        alternate = self.root / "linked"
        try:
            alternate.symlink_to(self.out, target_is_directory=True)
        except OSError:
            self.skipTest("directory symlinks are not available")
        with self.assertRaises(ValueError):
            ci.verify(alternate, self.identity)

    def test_failing_compiler_never_publishes_candidate(self):
        with mock.patch.object(ci.subprocess, "run",
                               side_effect=subprocess.CalledProcessError(2, ["go", "build"])):
            with self.assertRaises(subprocess.CalledProcessError):
                ci.build(self.out, self.identity, ambient=self.env)
        self.assertFalse(self.out.exists())

    def test_cli_refuses_outside_github_and_never_has_qualify_operation(self):
        denied = subprocess.run(
            [sys.executable, str(REPO / ".github/scripts/ci20_candidate.py"),
             "qualify", "--candidate", str(self.out)],
            capture_output=True, text=True, timeout=15)
        self.assertNotEqual(denied.returncode, 0)
        self.assertIn("invalid choice", denied.stderr)
        run = subprocess.run(
            [sys.executable, str(REPO / ".github/scripts/ci20_candidate.py"),
             "verify", "--candidate", str(self.out)],
            env={k: v for k, v in os.environ.items() if not k.startswith("GITHUB_")},
            capture_output=True, text=True, timeout=15)
        self.assertNotEqual(run.returncode, 0)
        self.assertIn("requires the exact authorized CI test job", run.stderr)
        self.assertFalse(self.out.exists())


class WorkflowAdmissionClosureTest(unittest.TestCase):
    def test_producer_is_not_yet_selected_and_consumer_is_direct_only(self):
        self.assertEqual(ci.PRODUCER_JOB, "artifact-ci-build")
        self.assertEqual(ci.TEST_CONSUMERS, {"artifact-ci-direct-tests"})
        self.assertNotIn("artifact-engine", ci.TEST_CONSUMERS)
        self.assertNotIn("artifact-package-assembly", ci.TEST_CONSUMERS)

    def test_native_change_and_test_runner_reach_impact_and_artifacts(self):
        workflow = (REPO / ".github/workflows/ci.yml").read_text(encoding="utf-8")
        impact = workflow.split("            impact:\n", 1)[1].split(
            "            codex-resources:\n", 1)[0]
        native = workflow.split("            artifacts:\n", 1)[1].split(
            "      - name:", 1)[0]
        for path in (".github/scripts/ci20_candidate.py",
                     ".github/scripts/test_ci20_candidate.py",
                     ".github/scripts/ci20_direct_tests.py"):
            self.assertIn("'" + path + "'", impact)
            self.assertIn("'" + path + "'", native)
        selected = workflow.split("  ci-impact:\n", 1)[1].split(
            "  codex-resource-contract:\n", 1)[0]
        self.assertIn("run: python .github/scripts/test_ci20_candidate.py", selected)
        map_doc = json.loads((REPO / ".github/ci-impact-map.json").read_text(encoding="utf-8"))
        for path in (".github/scripts/ci20_candidate.py",
                     ".github/scripts/test_ci20_candidate.py",
                     ".github/scripts/ci20_direct_tests.py"):
            self.assertEqual(
                [edge["checks"] for edge in map_doc["edges"] if edge.get("glob") == path],
                [["artifact-engine"]])

class HostedGraphContractTest(unittest.TestCase):
    def test_native_matrix_labels_are_not_misclassified_as_secrets(self):
        workflow = (REPO / ".github/workflows/ci.yml").read_text(encoding="utf-8")
        producer = workflow.split("  artifact-ci-build:\n", 1)[1].split(
            "  artifact-ci-direct-tests:\n", 1)[0]
        consumer = workflow.split("  artifact-ci-direct-tests:\n", 1)[1].split(
            "  artifact-engine:\n", 1)[0]
        for job in (producer, consumer):
            self.assertNotIn("artifact_key:", job)
            self.assertNotIn("matrix.artifact_key", job)
            self.assertEqual(job.count("artifact_label:"), 6)
            self.assertIn("matrix.artifact_label", job)
        labels = ("ubuntu-24.04", "ubuntu-24.04-arm", "windows-2025",
                  "windows-11-arm", "macos-15-intel", "macos-26")
        for label in labels:
            self.assertEqual(producer.count("artifact_label: " + label + "\n"), 1)
            self.assertEqual(consumer.count("artifact_label: " + label + "\n"), 1)

    def test_provisional_lane_is_registered_with_protected_gate(self):
        workflow = (REPO / ".github/workflows/ci.yml").read_text(encoding="utf-8")
        producer = workflow.split("  artifact-ci-build:\n", 1)[1].split(
            "  artifact-ci-direct-tests:\n", 1)[0]
        consumer = workflow.split("  artifact-ci-direct-tests:\n", 1)[1].split(
            "  artifact-engine:\n", 1)[0]
        for platform in sorted(ci.PLATFORMS):
            self.assertEqual(producer.count("expected_platform: " + platform), 1)
            self.assertEqual(consumer.count("expected_platform: " + platform), 1)
        self.assertIn("ci20_candidate.py build", producer)
        self.assertIn("ci20_direct_tests.py --candidate", consumer)
        self.assertIn("needs: [changes, artifact-ci-build]", consumer)
        gate = workflow.split("  ci-passed:\n", 1)[1]
        for job in ("artifact-ci-build", "artifact-ci-direct-tests"):
            self.assertIn("      - " + job + "\n", gate)
            self.assertIn("needs['" + job + "'].result", gate)


class CiIdentityTest(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="ci20-native-go-")
        self.addCleanup(self.temp.cleanup)
        self.go = Path(self.temp.name) / "go.exe"
        self.go.write_bytes(b"go test binary")
        self.ambient = {
            "GITHUB_ACTIONS": "true",
            "GITHUB_REPOSITORY": ci.REPOSITORY,
            "GITHUB_JOB": ci.PRODUCER_JOB,
            "GITHUB_SHA": "a" * 40, "GITHUB_RUN_ID": "123",
            "GITHUB_RUN_ATTEMPT": "1",
            "GITHUB_WORKFLOW_REF":
                "arbiterForge/codeArbiter/.github/workflows/ci.yml@refs/pull/42/merge",
        }
        self.go_fields = {
            "GOOS": "windows", "GOARCH": "amd64", "GOHOSTOS": "windows",
            "GOHOSTARCH": "amd64", "GOVERSION": ci.GO_VERSION, "CGO_ENABLED": "0",
        }

    def read(self, role="build", *, env=None, go=None, checked="a" * 40):
        def command(argv, **_kwargs):
            if argv[0] == "git":
                return checked
            return json.dumps(self.go_fields if go is None else go)
        with mock.patch.object(ci.subprocess, "check_output", side_effect=command), \
                mock.patch.object(ci.subprocess, "run", return_value=None), \
                mock.patch.object(ci.shutil, "which", return_value=str(self.go)), \
                mock.patch.object(ci, "hash_go_module", return_value="c" * 64):
            return ci.ci_identity(role, ambient=self.ambient if env is None else env)

    def test_identity_binds_actual_source_native_tool_and_target(self):
        value = self.read()
        self.assertEqual(value["source_commit"], "a" * 40)
        self.assertEqual(value["platform"], "windows/amd64")
        self.assertEqual(value["go_sha256"], hashlib.sha256(self.go.read_bytes()).hexdigest())

    def test_producer_and_consumers_are_exactly_allowlisted(self):
        for job in ("artifact-engine", "artifact-package-assembly", "artifact-ci-direct-tests"):
            with self.subTest(job=job), self.assertRaises(ValueError):
                self.read(env={**self.ambient, "GITHUB_JOB": job})
        for consumer in ci.TEST_CONSUMERS:
            self.assertEqual(self.read("verify", env={**self.ambient, "GITHUB_JOB": consumer})
                             ["platform"], "windows/amd64")
        with self.assertRaises(ValueError):
            self.read("verify")

    def test_ambient_identity_and_source_mismatches_fail_closed(self):
        for name, value in (
            ("GITHUB_ACTIONS", "false"), ("GITHUB_REPOSITORY", "other/repo"),
            ("GITHUB_SHA", "BAD"), ("GITHUB_RUN_ID", "0"),
            ("GITHUB_RUN_ATTEMPT", "01"), ("GITHUB_WORKFLOW_REF", "some/other/workflow"),
        ):
            with self.subTest(name=name), self.assertRaises(ValueError):
                self.read(env={**self.ambient, name: value})
        with self.assertRaises(ValueError):
            self.read(checked="b" * 40)

    def test_no_cross_compilation_or_unpinned_toolchain(self):
        for key, value in (("GOOS", "linux"), ("GOHOSTARCH", "arm64"),
                           ("GOVERSION", "go1.28.0"), ("CGO_ENABLED", "1")):
            with self.subTest(key=key), self.assertRaises(ValueError):
                self.read(go={**self.go_fields, key: value})


if __name__ == "__main__":
    unittest.main(verbosity=2)
