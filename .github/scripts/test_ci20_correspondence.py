#!/usr/bin/env python3
"""Negative controls for six-platform exact-byte CI-only/native-tested correspondence.

No test writes an ordinary release or native receipt to the real repository;
all positive records here are explicitly synthetic fixture inputs.
"""
from __future__ import annotations

import copy
import hashlib
import json
from pathlib import Path
import tempfile
import unittest
from unittest import mock

import ci20_candidate as early
import ci20_correspondence as join


class CorrespondenceTest(unittest.TestCase):
    def setUp(self):
        self.owner = tempfile.TemporaryDirectory(prefix="ci20-join-")
        self.addCleanup(self.owner.cleanup)
        self.root = Path(self.owner.name).resolve()
        self.early = self.root / "early"
        self.qualified = self.root / "qualified"
        self.early.mkdir()
        self.qualified.mkdir()
        self.binding = {
            "source_commit": "a" * 40, "run_id": "123",
            "run_attempt": "2",
            "workflow_ref": (
                "arbiterForge/codeArbiter/.github/workflows/ci.yml@refs/pull/1013/merge"
            ),
        }
        self.module = "b" * 64
        self.go = "c" * 64
        for runner, platform in join.PLATFORM_RUNNERS.items():
            provisional = self.early / ("ci20-test-input-" + runner)
            released = self.qualified / ("artifact-native-" + runner)
            candidate = released / "artifact-candidate"
            provisional.mkdir()
            candidate.mkdir(parents=True)
            binary = (platform + " synthetic binary").encode("ascii")
            filename = early._filename(platform)
            (provisional / filename).write_bytes(binary)
            (candidate / filename).write_bytes(binary)
            identity = {
                **self.binding, "run_attempt": "1", "platform": platform,
                "go_version": early.GO_VERSION, "go_sha256": self.go,
                "module_sha256": self.module,
            }
            provisional_record = early._record(identity, binary)
            (provisional / "ci-input.json").write_text(
                json.dumps(provisional_record), encoding="utf-8")
            release = {
                "format": join.RELEASE_FORMAT, "version": join.VERSION,
                "protocol": join.PROTOCOL, "schema_version": join.SCHEMA,
                "binaries": {
                    platform: {
                        "file": filename,
                        "sha256": hashlib.sha256(binary).hexdigest(),
                        "native_tested": True,
                    },
                },
            }
            (candidate / "release.json").write_text(json.dumps(release), encoding="utf-8")
            receipt = {
                "format": join.RECEIPT_FORMAT,
                "source_commit": self.binding["source_commit"],
                "workflow": early.WORKFLOW,
                "run_id": self.binding["run_id"],
                "job": join.EXPECTED_JOB,
                "platform": platform,
                "binary_sha256": hashlib.sha256(binary).hexdigest(),
                "version": join.VERSION, "protocol": join.PROTOCOL,
                "schema_version": join.SCHEMA,
                "native_tests": join.EXPECTED_NATIVE_TESTS,
                "context_native": {
                    "format": "codearbiter.context-native-observation/0.1.0",
                    "module_sha256": self.module,
                    "go_sha256": self.go,
                    "cases": [{"name": "synthetic-only"} for _ in range(6)],
                },
            }
            (released / "artifact-qualification.json").write_text(
                json.dumps(receipt), encoding="utf-8")

    def compute(self):
        return join.compare(self.early, self.qualified, self.binding, self.module)

    def mutate(self, runner, path, updater):
        target = self.root / path.format(runner=runner)
        obj = json.loads(target.read_text(encoding="utf-8"))
        updater(obj)
        target.write_text(json.dumps(obj), encoding="utf-8")

    def test_complete_six_platform_cohort_proves_byte_correspondence_not_authority(self):
        outcome = self.compute()
        self.assertEqual(outcome["format"], join.FORMAT)
        self.assertEqual(len(outcome["native_platforms"]), 6)
        self.assertFalse(outcome["qualified_by_this_check"])
        self.assertEqual({cell["platform"] for cell in outcome["native_platforms"]},
                         set(join.PLATFORM_RUNNERS.values()))
        self.assertEqual({cell["producer_attempt"] for cell in outcome["native_platforms"]},
                         {"1"})

    def test_no_platform_may_be_missing_or_duplicated(self):
        first = next(iter(join.PLATFORM_RUNNERS))
        (self.early / ("ci20-test-input-" + first)).rename(
            self.early / "duplicate-platform")
        with self.assertRaisesRegex(ValueError, "six"):
            self.compute()

    def test_changed_binary_on_either_side_refuses(self):
        first = next(iter(join.PLATFORM_RUNNERS))
        platform = join.PLATFORM_RUNNERS[first]
        for root_name, rel in (
            ("early", "ci20-test-input-{runner}"),
            ("qualified", "artifact-native-{runner}/artifact-candidate"),
        ):
            with self.subTest(which=root_name):
                target = self.root / root_name / rel.format(runner=first) / early._filename(platform)
                saved = target.read_bytes()
                target.write_bytes(b"altered binary")
                with self.assertRaisesRegex(ValueError, "differs"):
                    self.compute()
                target.write_bytes(saved)

    def test_wrong_run_source_tool_platform_and_flags_refuse(self):
        runner = next(iter(join.PLATFORM_RUNNERS))
        path = "early/ci20-test-input-{runner}/ci-input.json"
        target = self.root / path.format(runner=runner)
        original = target.read_bytes()
        for key, value in (
            ("source_commit", "d" * 40),
            ("run_id", "124"),
            ("module_sha256", "e" * 64),
            ("go_sha256", "f" * 64),
            ("platform", "linux/arm64"),
            ("go_version", "go1.28.0"),
            ("workflow_ref", "different/ci.yml@refs/main"),
            ("build_flags", []),
            ("build_environment", {}),
            ("state", "qualified"),
            ("format", "codearbiter.artifact-release/0.1.0"),
        ):
            with self.subTest(field=key):
                obj = json.loads(original)
                obj[key] = value
                target.write_text(json.dumps(obj), encoding="utf-8")
                with self.assertRaises(ValueError):
                    self.compute()
        target.write_bytes(original)

    def test_future_attempt_and_wrong_consumer_attempt_refuse(self):
        runner = next(iter(join.PLATFORM_RUNNERS))
        self.mutate(runner, "early/ci20-test-input-{runner}/ci-input.json",
                    lambda d: d.update(producer_attempt="3"))
        with self.assertRaises(ValueError):
            self.compute()
        self.mutate(runner, "early/ci20-test-input-{runner}/ci-input.json",
                    lambda d: d.update(producer_attempt="1"))
        with self.assertRaises(ValueError):
            join.compare(self.early, self.qualified,
                         {**self.binding, "run_attempt": "0"}, self.module)

    def test_native_manifest_cannot_be_unqualified_or_mislabeled(self):
        runner = next(iter(join.PLATFORM_RUNNERS))
        platform = join.PLATFORM_RUNNERS[runner]
        target = self.qualified / ("artifact-native-" + runner) / "artifact-candidate/release.json"
        prior = target.read_bytes()
        for field, value in (
            ("native_tested", False), ("native_tested", "true"),
            ("sha256", "f" * 64), ("file", "../unexpected.exe"),
        ):
            obj = json.loads(prior)
            obj["binaries"][platform][field] = value
            target.write_text(json.dumps(obj), encoding="utf-8")
            with self.subTest(field=field), self.assertRaises(ValueError):
                self.compute()
        target.write_bytes(prior)

    def test_native_receipt_must_be_real_tested_job_bound_to_cohort(self):
        runner = next(iter(join.PLATFORM_RUNNERS))
        target = self.qualified / ("artifact-native-" + runner) / "artifact-qualification.json"
        original = target.read_bytes()
        changes = (
            ("job", "artifact-ci-build"), ("source_commit", "f" * 40),
            ("run_id", "124"), ("native_tests", []),
            ("platform", "linux/arm64"), ("binary_sha256", "0" * 64),
        )
        for field, value in changes:
            obj = json.loads(original)
            obj[field] = value
            target.write_text(json.dumps(obj), encoding="utf-8")
            with self.subTest(field=field), self.assertRaises(ValueError):
                self.compute()
        target.write_bytes(original)

    def test_native_context_tool_and_case_identity_required(self):
        runner = next(iter(join.PLATFORM_RUNNERS))
        target = self.qualified / ("artifact-native-" + runner) / "artifact-qualification.json"
        saved = target.read_bytes()
        for mode in ("remove", "module", "go", "cases", "format"):
            data = json.loads(saved)
            if mode == "remove":
                del data["context_native"]
            elif mode == "module":
                data["context_native"]["module_sha256"] = "3" * 64
            elif mode == "go":
                data["context_native"]["go_sha256"] = "4" * 64
            elif mode == "cases":
                data["context_native"]["cases"].pop()
            else:
                data["context_native"]["format"] = "unknown-format"
            target.write_text(json.dumps(data), encoding="utf-8")
            with self.subTest(mode=mode), self.assertRaises(ValueError):
                self.compute()
        target.write_bytes(saved)

    def test_duplicate_fields_bad_json_and_unexpected_files_refuse(self):
        runner = next(iter(join.PLATFORM_RUNNERS))
        target = self.early / ("ci20-test-input-" + runner) / "ci-input.json"
        original = target.read_bytes()
        for raw in (b"{", b"[]", b'{"state":"unqualified","state":"qualified"}',
                    b"x" * (65_536 + 1)):
            with self.subTest(raw=raw[:28]):
                target.write_bytes(raw)
                with self.assertRaises((ValueError, TypeError)):
                    self.compute()
        target.write_bytes(original)
        extra = target.parent / "release.json"
        extra.write_text("{}")
        with self.assertRaises(ValueError):
            self.compute()

    def test_symlinked_candidate_refuses_without_following_external_content(self):
        runner = next(iter(join.PLATFORM_RUNNERS))
        candidate = self.early / ("ci20-test-input-" + runner)
        foreign = self.root / "untrusted"
        foreign.write_bytes(b"external")
        malicious = candidate / "ci-input.json"
        malicious.unlink()
        try:
            malicious.symlink_to(foreign)
        except OSError:
            self.skipTest("symlink creation is unavailable")
        with self.assertRaises(ValueError):
            self.compute()
        self.assertEqual(foreign.read_bytes(), b"external")

    def test_wrong_job_or_checkout_never_reads_cohort(self):
        expected = {
            "GITHUB_ACTIONS": "true",
            "GITHUB_REPOSITORY": early.REPOSITORY,
            "GITHUB_SHA": "a" * 40,
            "GITHUB_RUN_ID": "123",
            "GITHUB_RUN_ATTEMPT": "2",
            "GITHUB_WORKFLOW_REF": self.binding["workflow_ref"],
            "GITHUB_JOB": "artifact-package-assembly",
        }
        with mock.patch.object(join.subprocess, "check_output", return_value="a" * 40):
            self.assertEqual(join.identity(expected)["source_commit"], "a" * 40)
            for field, value in (("GITHUB_JOB", "artifact-ci-build"),
                                 ("GITHUB_REPOSITORY", "elsewhere/repo"),
                                 ("GITHUB_SHA", "invalid"),
                                 ("GITHUB_RUN_ATTEMPT", "0")):
                with self.subTest(field=field), self.assertRaises(ValueError):
                    join.identity({**expected, field: value})
        with mock.patch.object(join.subprocess, "check_output", return_value="b" * 40):
            with self.assertRaises(ValueError):
                join.identity(expected)


if __name__ == "__main__":
    unittest.main(verbosity=2)
