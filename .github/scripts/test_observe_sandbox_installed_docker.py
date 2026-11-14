"""Synthetic Sandbox observer controls. No Docker, npm or installed execution."""
from __future__ import annotations

import copy
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
from types import SimpleNamespace
import unittest
from unittest import mock

HERE = Path(__file__).resolve().parent
DEPENDENCY_ROOT = Path(os.environ.get("CA_SANDBOX_OBSERVER_DEPENDENCY_REPO", str(HERE.parents[1])))
GROUP = "shipped sandbox bundle [docker]"
NAMES = [
    GROUP + " resolves exec through the shipped CLI",
    GROUP + " copies out through the shipped CLI",
    GROUP + " destroys its owned container and volume",
]
sha = lambda raw: hashlib.sha256(raw).hexdigest()
encode = lambda value: (json.dumps(value, sort_keys=True) + "\n").encode()


def load(name):
    path = HERE / (name + ".py")
    if not path.is_file():
        return None
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


def fixture(root):
    """Deliberately inert package and process records, not product evidence."""
    payload = root / "payload"
    plugin = payload / "plugins/ca-sandbox"
    plugin.mkdir(parents=True)
    files = {
        ".claude-plugin/plugin.json": encode({"name": "ca-sandbox", "version": "0.2.0"}),
        "tools/sandbox.js": b"INERT UNIT BUNDLE; NEVER EXECUTED",
        "tools/claude-inside.js": b"INERT UNIT BUNDLE; NEVER EXECUTED",
    }
    for name, raw in files.items():
        path = plugin / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(raw)
    expected = {"source_commit": "a" * 40, "source_tree": "b" * 40,
                "ci_run_id": 17, "producer_job_id": 23, "execution_run_attempt": 1}
    receipt = {"format": "codearbiter.sandbox-plain-payload/1",
               **{k: expected[k] for k in ("source_commit", "source_tree")},
               "workflow": ".github/workflows/ci.yml", "version": "0.2.0",
               "plugin_root": "plugins/ca-sandbox", "execution_run_attempt": 1,
               "members": {name: {"size": len(raw), "sha256": sha(raw)}
                           for name, raw in files.items()}}
    (payload / "artifact-sandbox-payload.json").write_bytes(encode(receipt))
    physical = {p.relative_to(payload).as_posix(): sha(p.read_bytes())
                for p in sorted(payload.rglob("*")) if p.is_file()}
    auth = {"artifact_id": 71, "archive_sha256": "c" * 64,
            "members": [{"path": name, "sha256": digest} for name, digest in physical.items()]}
    source = {"source_commit": expected["source_commit"], "source_tree": expected["source_tree"],
              "clean": True, "inputs": {"unit-controller.py": "d" * 64,
              **{"plugins/ca-sandbox/" + path: sha(value) for path, value in files.items()}}}
    runtime = {"binaries": {name: {"path": "/unit/" + name, "sha256": "e" * 64,
                                  "version": "synthetic-inert-unit"}
                            for name in ("node", "npm", "docker", "git", "python", "nixpacks")},
               "modules": {"root": "/unit/node_modules",
                           "members": {"vitest.js": {"size": 4, "sha256": "f" * 64}}},
               "image": {"reference": "node:20-slim@sha256:" +
                         "2cf067cfed83d5ea958367df9f966191a942351a2df77d6f0193e162b5febfc0",
                         "id": "sha256:" + "1" * 64, "repo_digests": [
                             "node@sha256:" + "2cf067cfed83d5ea958367df9f966191a942351a2df77d6f0193e162b5febfc0"],
                         "os": "linux", "architecture": "amd64"}}
    acquisition_receipt = {"format": "codearbiter.nixpacks-acquisition/1", "version": "1.41.0",
        "scope": "Linux amd64; fixed plan generation only; no image or workflow qualification",
        "archive_sha256": "0f55de7874507b9cf7502113120bd96f2ab6979f78d10eaf2eb2ade9207b3af6",
        "binary_sha256": "e" * 64, "bin_dir": "/unit/ca-nixpacks-reviewed-fixture"}
    acquisition_raw = encode(acquisition_receipt)
    runtime["nixpacks_acquisition"] = {"runner_temp": "/unit", "path": "/unit/nixpacks-acquisition.json",
        "sha256": sha(acquisition_raw), "document_utf8": acquisition_raw.decode()}
    runtime["binaries"]["nixpacks"].update(path=acquisition_receipt["bin_dir"] + "/nixpacks",
                                            version="nixpacks 1.41.0")
    rows = [{"id": "vitest:plugins/ca-sandbox/tools/installed-bundle.test.ts:" + name,
             "result": "passed"} for name in NAMES]
    witnesses = []
    for index, name in enumerate(NAMES):
        identity = "unit" + str(index)
        temporary = "/unit/fixtures/" + identity
        commands = []
        def command(tail, stdout):
            commands.append({"argv": ["/unit/node", str(plugin / "tools/sandbox.js"), *tail],
                             "exit_code": 0, "timed_out": False, "containment": "exited",
                             "stdout_utf8": stdout, "stderr_utf8": ""})
        if index == 0:
            command(["exec", identity, "--", "sh", "-c", "printf SBX_INSTALLED_EXEC"],
                    json.dumps({"id": identity, "exitCode": 0, "stdout": "SBX_INSTALLED_EXEC"}))
        elif index == 1:
            command(["exec", identity, "--", "sh", "-c",
                     "printf SBX_INSTALLED_COPY > /tmp/result"],
                    json.dumps({"id": identity, "exitCode": 0, "stdout": ""}))
            command(["cp", identity + ":/tmp/result", temporary + "/result"], "")
        else:
            command(["destroy", identity], json.dumps({"id": identity, "failureCount": 0,
                    "remainingContainers": [], "remainingVolumes": []}))
        witnesses.append({"format": "codearbiter.sandbox-bundle-case/1", "name": name,
                          "plugin_root": str(plugin),
                          "bundle_sha256": sha(files["tools/sandbox.js"]),
                          "node": "/unit/node", "image": runtime["image"],
                          "fixture": {"id": identity, "container": "2" * 64,
                                      "volume": "ca-sbx-vol-" + identity, "host_dir": temporary,
                                      "labels": {"ca.sandbox": "1", "ca.sandbox.id": identity,
                                                 "ca.sandbox.qualification": identity}},
                          "commands": commands, "checks": {
                              "exec_marker": index == 0, "copy_sha256": sha(b"SBX_INSTALLED_COPY") if index == 1 else None,
                              "destroy_empty": index == 2},
                          "cleanup": {"container_absent": True, "volume_absent": True,
                                      "owned_only": True}})
    suite = {"argv": ["/unit/node", "/unit/npm", "test", "--", "--reporter=default",
                     "--reporter=github-actions", "--reporter=json", "--no-cache",
                     "--outputFile.json=/unit/output/sandbox-vitest.json"],
             "cwd": "/unit/source/plugins/ca-sandbox/tools", "exit_code": 0,
             "timed_out": False, "containment": "exited",
             "raw_sha256": "3" * 64, "sentinel_sha256": "4" * 64,
             "declared_layers": {"installed-bundle": ["installed-bundle.test.ts"]},
             "recorded_layers": ["installed-bundle"], "tests": rows}
    binding = {"format": "codearbiter.installed-observation-binding/1",
               "profile": "sandbox-installed-docker-v1", **expected,
               "workflow": ".github/workflows/ci.yml",
               "payload": {"artifact_name": "artifact-sandbox-plugin-" + expected["source_commit"] + "-1", **auth},
               "payload_document_utf8": encode(receipt).decode(), "installed_root": str(plugin),
               "manifest_document_utf8": files[".claude-plugin/plugin.json"].decode(),
               "source_before": source, "source_after": copy.deepcopy(source),
               "runtime_before": runtime, "runtime_after": copy.deepcopy(runtime),
               "payload_before": {"root": str(payload), "members": physical},
               "payload_after": {"root": str(payload), "members": dict(physical)},
               "suite": suite, "witnesses": witnesses}
    observation = {"format": "codearbiter.major-test-observation/1",
                   **{k: expected[k] for k in ("source_commit", "source_tree", "ci_run_id")},
                   "source_stable": True, "proof_kind": "live-host",
                   "producer": "sandbox-installed-docker-observer-v1",
                   "argv": suite["argv"], "exit_code": 0, "tests": rows,
                   "installed_binding": binding}
    return expected, observation, {"artifact-sandbox-plugin-" + expected["source_commit"] + "-1": auth}


class SandboxProfileTests(unittest.TestCase):
    def subject(self):
        subject = load("_sandbox_docker_profile")
        self.assertIsNotNone(subject, "the closed installed Sandbox profile is not implemented")
        return subject

    def test_valid_finite_profile_derives_one_installed_cell_and_one_real_payload_role(self):
        owner = self.subject()
        with tempfile.TemporaryDirectory(prefix="sbx-unit-profile-") as raw:
            expected, observed, auth = fixture(Path(raw))
            admitted = owner.admit(observed, expected=expected, authenticated_payloads=auth)
            self.assertEqual(admitted["installed_cells"], ["installed:sandbox:docker"])
            self.assertEqual(admitted["payload_artifact_ids"], [71])
            self.assertEqual(len(admitted["tests"]), 3)

    def test_actual_bundle_source_epoch_and_artifact_pins_cannot_be_relabelled(self):
        owner = self.subject()
        with tempfile.TemporaryDirectory(prefix="sbx-unit-tamper-") as raw:
            expected, observed, auth = fixture(Path(raw))
            for fault in ("source", "producer", "proof-kind", "artifact", "bundle", "payload-drift", "runtime-drift"):
                with self.subTest(fault=fault):
                    value = copy.deepcopy(observed)
                    if fault == "source": value["source_commit"] = "9" * 40
                    elif fault == "producer": value["producer"] = "python-test-result-observer"
                    elif fault == "proof-kind": value["proof_kind"] = "source-test"
                    elif fault == "artifact": value["installed_binding"]["payload"]["artifact_id"] = 99
                    elif fault == "bundle": value["installed_binding"]["witnesses"][0]["bundle_sha256"] = "0" * 64
                    elif fault == "payload-drift": value["installed_binding"]["payload_after"]["members"]["extra"] = "0" * 64
                    else: value["installed_binding"]["runtime_after"]["binaries"]["node"]["sha256"] = "0" * 64
                    with self.assertRaises(ValueError):
                        owner.admit(value, expected=expected, authenticated_payloads=auth)

    def test_missing_skipped_repeated_cases_or_sentinel_and_wrong_cli_refuse(self):
        owner = self.subject()
        with tempfile.TemporaryDirectory(prefix="sbx-unit-names-") as raw:
            expected, observed, auth = fixture(Path(raw))
            for fault in ("missing", "skip", "repeat", "layer", "argv", "timeout", "cleanup"):
                with self.subTest(fault=fault):
                    value = copy.deepcopy(observed)
                    b = value["installed_binding"]
                    if fault == "missing": value["tests"] = value["tests"][:-1]
                    elif fault == "skip": b["suite"]["tests"][0]["result"] = "skipped"
                    elif fault == "repeat": b["witnesses"].append(copy.deepcopy(b["witnesses"][0]))
                    elif fault == "layer": b["suite"]["recorded_layers"] = []
                    elif fault == "argv": b["witnesses"][0]["commands"][0]["argv"][1] = "/source/fallback.js"
                    elif fault == "timeout": b["witnesses"][0]["commands"][0]["timed_out"] = True
                    else: b["witnesses"][0]["cleanup"]["volume_absent"] = False
                    with self.assertRaises(ValueError):
                        owner.admit(value, expected=expected, authenticated_payloads=auth)

    def test_coherent_omission_of_nonmandatory_selected_plugin_file_refuses(self):
        owner = self.subject()
        with tempfile.TemporaryDirectory(prefix="sbx-unit-omission-") as raw:
            expected, observed, auth = fixture(Path(raw))
            binding = observed["installed_binding"]
            # The selected Git plugin has this nonmandatory file. The complete
            # physical payload, receipt and authenticated archive all omit it.
            # Mandatory bundles/manifests and every other join remain coherent.
            for when in ("source_before", "source_after"):
                binding[when]["inputs"]["plugins/ca-sandbox/docs/optional.txt"] = sha(b"SELECTED GIT DATA")
            with self.assertRaisesRegex(ValueError, "complete selected source"):
                owner.admit(observed, expected=expected, authenticated_payloads=auth)

    def test_stable_wrong_nixpacks_version_refuses_at_profile_intake(self):
        owner = self.subject()
        with tempfile.TemporaryDirectory(prefix="sbx-unit-wrong-builder-") as raw:
            expected, observed, auth = fixture(Path(raw))
            for when in ("runtime_before", "runtime_after"):
                observed["installed_binding"][when]["binaries"]["nixpacks"]["version"] = "nixpacks 9.9.9"
            with self.assertRaisesRegex(ValueError, "Nixpacks"):
                owner.admit(observed, expected=expected, authenticated_payloads=auth)

    def test_coherent_nixpacks_receipt_and_executable_substitutions_refuse_at_intake(self):
        owner = self.subject()
        with tempfile.TemporaryDirectory(prefix="sbx-unit-builder-binding-") as raw:
            expected, observed, auth = fixture(Path(raw))
            for fault in ("missing", "format", "version", "archive", "binary", "bin-dir", "scope", "path", "hash", "receipt-path"):
                with self.subTest(fault=fault):
                    value = copy.deepcopy(observed)
                    for when in ("runtime_before", "runtime_after"):
                        runtime = value["installed_binding"][when]
                        acquisition = runtime["nixpacks_acquisition"]
                        receipt = json.loads(acquisition["document_utf8"])
                        if fault == "missing":
                            del runtime["nixpacks_acquisition"]
                            continue
                        elif fault == "path": runtime["binaries"]["nixpacks"]["path"] = "/other/nixpacks"
                        elif fault == "hash": runtime["binaries"]["nixpacks"]["sha256"] = "9" * 64
                        elif fault == "receipt-path": acquisition["path"] = "/other/nixpacks-acquisition.json"
                        else:
                            key, replacement = {
                                "format": ("format", "other/1"), "version": ("version", "9.9.9"),
                                "archive": ("archive_sha256", "9" * 64), "binary": ("binary_sha256", "9" * 64),
                                "bin-dir": ("bin_dir", "/other/ca-nixpacks-reviewed-fixture"), "scope": ("scope", "other")}[fault]
                            receipt[key] = replacement
                        acquisition["document_utf8"] = encode(receipt).decode()
                        acquisition["sha256"] = sha(encode(receipt))
                    with self.assertRaises(ValueError):
                        owner.admit(value, expected=expected, authenticated_payloads=auth)


class SandboxObserverTests(unittest.TestCase):
    def subject(self):
        subject = load("observe_sandbox_installed_docker")
        self.assertIsNotNone(subject, "the sanctioned one-run Sandbox producer is not implemented")
        return subject

    def test_child_environment_is_credential_blind_but_retains_required_ci_truth(self):
        owner = self.subject()
        with tempfile.TemporaryDirectory(prefix="sbx-unit-env-") as raw:
            parent = {"GH_TOKEN": "PrivateFixtureValue", "OPENAI_API_KEY": "PrivateFixtureValue",
                      "DOCKER_HOST": "tcp://unapproved.invalid", "CI": "true",
                      "CA_SANDBOX_REQUIRE_DOCKER": "1"}
            env = owner.child_environment(Path(raw), ["/unit/bin"], parent)
            self.assertEqual(env["CI"], "true")
            self.assertEqual(env["CA_SANDBOX_REQUIRE_DOCKER"], "1")
            self.assertNotIn("GH_TOKEN", env)
            self.assertNotIn("OPENAI_API_KEY", env)
            self.assertNotIn("DOCKER_HOST", env)

    def test_source_has_fixed_one_run_entry_and_three_real_bundle_cases(self):
        owner = self.subject()
        self.assertTrue(callable(getattr(owner, "produce", None)))
        self.assertTrue(callable(getattr(owner, "stage_payload", None)))
        source = (HERE.parents[1] / "plugins/ca-sandbox/tools/installed-bundle.test.ts")
        self.assertTrue(source.is_file(), "actual shipped-bundle Docker cases are absent")
        code = source.read_text()
        for name in ("resolves exec through the shipped CLI", "copies out through the shipped CLI",
                     "destroys its owned container and volume"):
            self.assertIn(name, code)
        self.assertIn('dockerGate("installed-bundle"', code)
        self.assertNotIn('"prune"', code)

    def producer_fixture(self, root, fault=None):
        owner = self.subject()
        profile = load("_sandbox_docker_profile")
        expected, observed, auth = fixture(root)
        repo = root / "source"
        testfile = repo / "plugins/ca-sandbox/tools/installed-bundle.test.ts"
        testfile.parent.mkdir(parents=True)
        testfile.write_bytes(b"// inert unit source; never executed")
        out = root / "output"
        out.mkdir()
        b = observed["installed_binding"]
        calls = {"spawn": 0, "runtime": 0}
        def source():
            value = copy.deepcopy(b["source_before"])
            if fault == "source-drift" and calls["spawn"]:
                value["inputs"]["unit-controller.py"] = "0" * 64
            return value
        def runtime():
            calls["runtime"] += 1
            return copy.deepcopy(b["runtime_before"])
        def payload():
            return {"root": str(root / "payload"),
                    "members": {p: item["sha256"] for p, item in owner.inventory(root / "payload")["members"].items()}}
        def spawn(argv, *, timeout, cwd, env):
            calls["spawn"] += 1
            self.assertEqual(argv[:3], ["/unit/node", "/unit/npm", "test"])
            self.assertEqual(timeout, 2400)
            self.assertEqual(env["PATH"].split(os.pathsep)[0], str(Path("/unit/ca-nixpacks-reviewed-fixture")))
            self.assertEqual(cwd, str(repo / "plugins/ca-sandbox/tools"))
            self.assertEqual(env["CA_SANDBOX_REQUIRE_DOCKER"], "1")
            self.assertNotIn("GH_TOKEN", env)
            self.assertNotIn("OPENAI_API_KEY", env)
            self.assertNotIn("DOCKER_HOST", env)
            if fault in ("failed-exit", "timeout"):
                return SimpleNamespace(returncode=9, timed_out=fault == "timeout",
                                       containment="unknown" if fault == "timeout" else "exited",
                                       stdout="", stderr="inert synthetic failure")
            result = {"success": True, "numTotalTests": 3, "numPassedTests": 3,
                      "numFailedTests": 0, "numPendingTests": 0,
                      "testResults": [{"name": str(testfile),
                          "assertionResults": [{"fullName": name, "status": "passed"} for name in NAMES]}]}
            Path(argv[-1].split("=", 1)[1]).write_bytes(encode(result))
            Path(env["CA_SANDBOX_DOCKER_SENTINEL"]).write_bytes(b"installed-bundle\n")
            Path(env["CA_SANDBOX_BUNDLE_OBSERVATION"]).write_bytes(
                b"".join(encode(case) for case in b["witnesses"]))
            return SimpleNamespace(returncode=0, timed_out=False, containment="exited", stdout="", stderr="")
        auth[next(iter(auth))]["native_bindings"] = []  # Real shared owner returns this unrelated extra.
        services = SimpleNamespace(source_snapshot=source, runtime_snapshot=runtime,
            payload_snapshot=payload, declared_layers=lambda: {"installed-bundle": ["installed-bundle.test.ts"]},
            spawn=spawn, profile=profile, authenticated_payloads=auth)
        config = {"repo": repo, "payload_root": root / "payload", "output_dir": out, "expected": expected}
        return owner, config, services, calls

    def test_one_original_process_generates_named_observation_and_retains_raw_data(self):
        with tempfile.TemporaryDirectory(prefix="sbx-unit-one-run-") as rawdir:
            owner, config, services, calls = self.producer_fixture(Path(rawdir))
            with mock.patch.dict(os.environ, {"CA_SANDBOX_REQUIRE_DOCKER": "1", "CI": "true",
                                             "GH_TOKEN": "PrivateFixtureValue"}, clear=False):
                result = owner._observe(config, services)
            self.assertEqual(calls["spawn"], 1)
            self.assertEqual(len(result["tests"]), 3)
            self.assertEqual(result["installed_binding"]["execution_run_attempt"], 1)
            for filename in ("suite-execution.json", "sandbox-vitest.json",
                             "sandbox-docker-layers.sentinel", "sandbox-bundle-cases.jsonl",
                             "inputs-before.json", "inputs-after.json", "cleanup.json", "observation.json"):
                self.assertTrue((config["output_dir"] / filename).is_file(), filename)
            self.assertFalse((config["output_dir"] / "failure.json").exists())

    def test_package_drift_and_wrong_attempt_refuse_before_any_runtime_or_test_process(self):
        for fault in ("payload", "attempt"):
            with self.subTest(fault=fault), tempfile.TemporaryDirectory(prefix="sbx-unit-before-effect-") as rawdir:
                owner, config, services, calls = self.producer_fixture(Path(rawdir))
                if fault == "payload":
                    (config["payload_root"] / "plugins/ca-sandbox/tools/sandbox.js").write_bytes(b"CHANGED")
                else:
                    config["expected"]["execution_run_attempt"] = 2
                with self.assertRaises(ValueError):
                    owner._observe(config, services)
                self.assertEqual(calls["spawn"], 0)
                self.assertEqual(calls["runtime"], 0)
                self.assertTrue((config["output_dir"] / "failure.json").is_file())
                self.assertFalse((config["output_dir"] / "observation.json").exists())

    def test_coherent_nonmandatory_omission_refuses_before_any_runtime_or_test_process(self):
        with tempfile.TemporaryDirectory(prefix="sbx-unit-omission-before-effect-") as rawdir:
            owner, config, services, calls = self.producer_fixture(Path(rawdir))
            original = services.source_snapshot
            def selected_source():
                selected = original()
                selected["inputs"]["plugins/ca-sandbox/docs/optional.txt"] = sha(b"SELECTED GIT DATA")
                return selected
            services.source_snapshot = selected_source
            with self.assertRaisesRegex(ValueError, "complete selected source"):
                owner._observe(config, services)
            self.assertEqual(calls["runtime"], 0)
            self.assertEqual(calls["spawn"], 0)
            self.assertFalse((config["output_dir"] / "observation.json").exists())

    def test_nixpacks_owning_receipt_is_joined_before_even_version_probe(self):
        owner, profile = self.subject(), load("_sandbox_docker_profile")
        for fault in (None, "missing", "format", "version", "archive", "binary", "bin-dir", "substituted-path", "physical-hash"):
            with self.subTest(fault=fault), tempfile.TemporaryDirectory(prefix="sbx-unit-builder-preprobe-") as rawdir:
                root = Path(rawdir)
                directory = root / "ca-nixpacks-reviewed-unit"
                directory.mkdir()
                executable = directory / "nixpacks"
                executable.write_bytes(b"INERT UNIT BUILDER; NEVER EXECUTED")
                receipt = {"format": "codearbiter.nixpacks-acquisition/1", "version": "1.41.0",
                    "scope": "Linux amd64; fixed plan generation only; no image or workflow qualification",
                    "archive_sha256": "0f55de7874507b9cf7502113120bd96f2ab6979f78d10eaf2eb2ade9207b3af6",
                    "binary_sha256": sha(executable.read_bytes()), "bin_dir": str(directory)}
                if fault in ("format", "version", "archive", "binary", "bin-dir"):
                    key, replacement = {"format": ("format", "other/1"), "version": ("version", "9.9.9"),
                        "archive": ("archive_sha256", "9" * 64), "binary": ("binary_sha256", "9" * 64),
                        "bin-dir": ("bin_dir", str(root / "other"))}[fault]
                    receipt[key] = replacement
                elif fault == "substituted-path":
                    executable = root / "substituted-helper"
                    executable.write_bytes(b"INERT UNIT BUILDER; NEVER EXECUTED")
                elif fault == "physical-hash": executable.write_bytes(b"CHANGED INERT UNIT BUILDER")
                if fault != "missing": (root / "nixpacks-acquisition.json").write_bytes(encode(receipt))
                calls = []
                def probe(argv, **kwargs):
                    calls.append(argv)
                    return SimpleNamespace(returncode=0, timed_out=False, containment="exited",
                                           stdout="nixpacks 1.41.0\n", stderr="")
                if fault is None:
                    identity, acquisition = owner._probe_nixpacks(executable, root, profile, probe, env={}, cwd=root)
                    self.assertEqual(calls, [[str(executable), "--version"]])
                    self.assertEqual(identity["version"], "nixpacks 1.41.0")
                    self.assertEqual(acquisition["path"], str(root / "nixpacks-acquisition.json"))
                else:
                    with self.assertRaises((ValueError, OSError)):
                        owner._probe_nixpacks(executable, root, profile, probe, env={}, cwd=root)
                    self.assertEqual(calls, [], "unadmitted helper must never reach --version")

    def test_admitted_nixpacks_wrong_actual_version_or_receipt_drift_cannot_reach_suite(self):
        owner, profile = self.subject(), load("_sandbox_docker_profile")
        for fault in ("actual-version", "receipt-drift"):
            with self.subTest(fault=fault), tempfile.TemporaryDirectory(prefix="sbx-unit-builder-postprobe-") as rawdir:
                root = Path(rawdir)
                directory = root / "ca-nixpacks-reviewed-unit"
                directory.mkdir()
                executable = directory / "nixpacks"
                executable.write_bytes(b"INERT UNIT BUILDER; NEVER EXECUTED")
                receipt = {"format": "codearbiter.nixpacks-acquisition/1", "version": "1.41.0",
                    "scope": "Linux amd64; fixed plan generation only; no image or workflow qualification",
                    "archive_sha256": "0f55de7874507b9cf7502113120bd96f2ab6979f78d10eaf2eb2ade9207b3af6",
                    "binary_sha256": sha(executable.read_bytes()), "bin_dir": str(directory)}
                path = root / "nixpacks-acquisition.json"
                path.write_bytes(encode(receipt))
                calls = []
                def probe(argv, **kwargs):
                    calls.append(argv)
                    if fault == "receipt-drift": path.write_bytes(encode({**receipt, "version": "9.9.9"}))
                    return SimpleNamespace(returncode=0, timed_out=False, containment="exited",
                        stdout="nixpacks 9.9.9\n" if fault == "actual-version" else "nixpacks 1.41.0\n", stderr="")
                with self.assertRaises(ValueError):
                    owner._probe_nixpacks(executable, root, profile, probe, env={}, cwd=root)
                self.assertEqual(calls, [[str(executable), "--version"]])

    def test_failed_exit_timeout_and_source_drift_keep_failure_without_affirmative_output(self):
        for fault in ("failed-exit", "timeout", "source-drift"):
            with self.subTest(fault=fault), tempfile.TemporaryDirectory(prefix="sbx-unit-failure-") as rawdir:
                owner, config, services, calls = self.producer_fixture(Path(rawdir), fault)
                with mock.patch.dict(os.environ, {"CA_SANDBOX_REQUIRE_DOCKER": "1"}):
                    with self.assertRaises(ValueError):
                        owner._observe(config, services)
                self.assertEqual(calls["spawn"], 1)
                self.assertTrue((config["output_dir"] / "suite-execution.json").is_file())
                self.assertTrue((config["output_dir"] / "failure.json").is_file())
                self.assertFalse((config["output_dir"] / "observation.json").exists())

    def test_control_token_is_removed_before_test_imports_and_environment_restored(self):
        owner = self.subject()
        with tempfile.TemporaryDirectory(prefix="sbx-unit-control-") as rawdir:
            with mock.patch.dict(os.environ, {"GH_TOKEN": "PrivateFixtureValue", "CA_SANDBOX_REQUIRE_DOCKER": "1"}):
                before = dict(os.environ)
                with owner.control_environment(Path(rawdir) / "control", ["/unit/bin"]):
                    self.assertNotIn("GH_TOKEN", os.environ)
                    self.assertEqual(os.environ["CA_SANDBOX_REQUIRE_DOCKER"], "1")
                    self.assertEqual(os.environ["DOCKER_CONFIG"], str(Path(rawdir) / "control/docker"))
                self.assertEqual(dict(os.environ), before)


class SandboxGitStageTests(unittest.TestCase):
    def unit_repo(self, root):
        repo = root / "repo"
        repo.mkdir()
        plugin = repo / "plugins/ca-sandbox"
        for name, value in {
            ".claude-plugin/plugin.json": encode({"name": "ca-sandbox", "version": "0.2.0"}),
            "tools/sandbox.js": b"INERT UNIT BUNDLE",
            "tools/claude-inside.js": b"INERT UNIT BUNDLE",
        }.items():
            p = plugin / name
            p.parent.mkdir(parents=True, exist_ok=True)
            p.write_bytes(value)
        for name in (".github/scripts/fixture.py", "core/pysrc/fixture.py", "tools/fixture.py",
                     "core/surface/plain.txt", "core/hosts.json"):
            p = repo / name
            p.parent.mkdir(parents=True, exist_ok=True)
            p.write_bytes(b"UNIT SOURCE DATA; NEVER EXECUTED")
        env = {k: v for k, v in os.environ.items()
               if k.upper() in ("PATH", "SYSTEMROOT", "WINDIR", "COMSPEC", "PATHEXT", "TEMP", "TMP")}
        env.update(HOME=str(root), USERPROFILE=str(root), GIT_CONFIG_NOSYSTEM="1",
                   GIT_CONFIG_GLOBAL=os.devnull, GIT_TERMINAL_PROMPT="0")
        for args in (["init", "-q"], ["config", "core.autocrlf", "false"],
                     ["add", "--", "plugins", ".github", "core", "tools"],
                     ["-c", "user.name=Unit", "-c", "user.email=unit@example.invalid", "commit", "-qm", "unit fixture"]):
            subprocess.run(["git", "-C", str(repo), *args], env=env, check=True,
                           capture_output=True, timeout=15)
        source = subprocess.check_output(["git", "-C", str(repo), "rev-parse", "HEAD"],
                                         env=env, timeout=15).decode().strip()
        return repo, source

    def test_exact_git_stage_ignores_dirty_worktree_and_never_overwrites(self):
        owner = load("observe_sandbox_installed_docker")
        with tempfile.TemporaryDirectory(prefix="sbx-unit-stage-") as rawdir:
            root = Path(rawdir)
            repo, source = self.unit_repo(root)
            (repo / "plugins/ca-sandbox/tools/sandbox.js").write_bytes(b"DIRTY SOURCE")
            output = root / "payload"
            result = owner.stage_payload(repo, source, output, run_attempt=2)
            self.assertEqual((output / "plugins/ca-sandbox/tools/sandbox.js").read_bytes(), b"INERT UNIT BUNDLE")
            self.assertEqual(result["artifact_name"], "artifact-sandbox-plugin-" + source + "-2")
            self.assertEqual(result["receipt"]["execution_run_attempt"], 2)
            before = (output / "artifact-sandbox-payload.json").read_bytes()
            with self.assertRaises(ValueError):
                owner.stage_payload(repo, source, output, run_attempt=2)
            self.assertEqual((output / "artifact-sandbox-payload.json").read_bytes(), before)

    def test_source_capture_rejects_untracked_ignored_data_under_pycache(self):
        owner = load("observe_sandbox_installed_docker")
        with tempfile.TemporaryDirectory(prefix="sbx-unit-source-") as rawdir:
            repo, source = self.unit_repo(Path(rawdir))
            initial = owner.source_snapshot(repo, source)
            self.assertTrue(initial["clean"])
            # Git's status ignores this directory after the local exclude; the
            # surface reader still consumes data there, so membership must fail.
            (repo / ".git/info/exclude").write_bytes(b"__pycache__/\n")
            extra = repo / "core/surface/__pycache__/untracked.txt"
            extra.parent.mkdir()
            extra.write_bytes(b"UNTRACKED DATA")
            with self.assertRaisesRegex(ValueError, "data membership"):
                owner.source_snapshot(repo, source)

    def public_repo(self, root):
        repo, _ = self.unit_repo(root)
        owner = load("observe_sandbox_installed_docker")
        for name in ("observe_sandbox_installed_docker.py", "_sandbox_docker_profile.py"):
            (repo / ".github/scripts" / name).write_bytes((HERE / name).read_bytes())
        (repo / ".github/scripts/_boundedproc.py").write_bytes(
            (DEPENDENCY_ROOT / ".github/scripts/_boundedproc.py").read_bytes())
        owner.git(repo, "add", "--", ".github/scripts/observe_sandbox_installed_docker.py",
                  ".github/scripts/_sandbox_docker_profile.py", ".github/scripts/_boundedproc.py")
        owner.git(repo, "-c", "user.name=Unit", "-c", "user.email=unit@example.invalid",
                  "commit", "-qm", "unit public observer source")
        source = owner.git(repo, "rev-parse", "HEAD").decode().strip()
        expected = {"source_commit": source,
                    "source_tree": owner.git(repo, "rev-parse", "HEAD^{tree}").decode().strip(),
                    "ci_run_id": 17, "producer_job_id": 23, "execution_run_attempt": 1}
        payload = root / "payload"
        owner.stage_payload(repo, source, payload, run_attempt=1)
        spec = importlib.util.spec_from_file_location("unit_public_observer_" + root.name,
            repo / ".github/scripts/observe_sandbox_installed_docker.py")
        public = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(public)
        return public, repo, {"repo": repo, "payload_root": payload,
                             "output_dir": root / "output", "expected": expected}

    def test_public_entry_rejects_physical_helper_drift_before_import_or_marker_effect(self):
        with tempfile.TemporaryDirectory(prefix="sbx-unit-public-shim-") as rawdir:
            root = Path(rawdir)
            public, repo, config = self.public_repo(root)
            marker = root / "must-not-run"
            path = repo / ".github/scripts/_sandbox_docker_profile.py"
            path.write_bytes(path.read_bytes() + (
                "\nfrom pathlib import Path\nPath(" + repr(str(marker)) + ").write_bytes(b'bad')\n").encode())
            with self.assertRaisesRegex(ValueError, "source is not clean"):
                public.produce(config, authenticated_payloads={})
            self.assertFalse(marker.exists())
            self.assertFalse(config["output_dir"].exists())

    def test_public_entry_rejects_ignored_surface_data_before_effects(self):
        with tempfile.TemporaryDirectory(prefix="sbx-unit-public-data-") as rawdir:
            public, repo, config = self.public_repo(Path(rawdir))
            (repo / ".git/info/exclude").write_bytes(b"__pycache__/\n")
            path = repo / "core/surface/__pycache__/untracked.txt"
            path.parent.mkdir()
            path.write_bytes(b"UNTRACKED DATA")
            with self.assertRaisesRegex(ValueError, "data membership"):
                public.produce(config, authenticated_payloads={})
            self.assertFalse(config["output_dir"].exists())

    def test_actual_project_import_replaces_same_path_stale_module_and_restores_registry(self):
        owner = load("observe_sandbox_installed_docker")
        with tempfile.TemporaryDirectory(prefix="sbx-unit-registry-") as rawdir:
            root = Path(rawdir)
            _, repo, _ = self.public_repo(root)
            previous = sys.modules.get("_sandbox_docker_profile")
            poison = SimpleNamespace(__file__=str(repo / ".github/scripts/_sandbox_docker_profile.py"),
                                     PROFILE="STALE")
            sys.modules["_sandbox_docker_profile"] = poison
            before_path, before_prefix = sys.path[:], sys.pycache_prefix
            try:
                with owner.project_modules(repo, root / "fresh-bytecode"):
                    import _sandbox_docker_profile as actual
                    self.assertIsNot(actual, poison)
                    self.assertEqual(actual.PROFILE, "sandbox-installed-docker-v1")
                    self.assertEqual(Path(sys.pycache_prefix), root / "fresh-bytecode")
                self.assertIs(sys.modules["_sandbox_docker_profile"], poison)
                self.assertEqual(sys.path, before_path)
                self.assertEqual(sys.pycache_prefix, before_prefix)
            finally:
                if previous is None:
                    sys.modules.pop("_sandbox_docker_profile", None)
                else:
                    sys.modules["_sandbox_docker_profile"] = previous


if __name__ == "__main__":
    unittest.main(verbosity=2)
