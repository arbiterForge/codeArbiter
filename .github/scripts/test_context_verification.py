#!/usr/bin/env python3
# codeArbiter — verify the finite context test bridge.
# The fixture is a real, offline Go invocation; parser controls are deliberately
# synthetic and cannot establish product or installed-host qualification.

import hashlib
import json
import os
from pathlib import Path
import platform
import shutil
import sys
import tempfile
import unittest
from unittest import mock

import _contextverificationlib as bridge


GO = Path(shutil.which("go") or "go")


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def event(action, test=None, package="fixture"):
    item = {"Action": action, "Package": package}
    if test is not None:
        item["Test"] = test
    return json.dumps(item, separators=(",", ":")).encode() + b"\n"


def passing_output():
    return b"".join((
        event("run", "TestBridgeFixture"),
        event("run", "TestBridgeFixture/works"),
        event("pass", "TestBridgeFixture/works"),
        event("pass", "TestBridgeFixture"),
        event("pass"),
    ))


class GoOutputContract(unittest.TestCase):
    def verify(self, raw, **changes):
        inputs = dict(raw_stdout=raw, raw_stderr=b'', exit_code=0,
                      case='TestBridgeFixture', expected_subtests=('works',))
        return bridge.verify_go_output(**{**inputs, **changes})

    def test_parallel_events_and_unselected_package_preserve_raw_evidence(self):
        raw = (event('start', package='idle') + event('skip', package='idle') +
               event('run', 'TestBridgeFixture') +
               event('run', 'TestBridgeFixture/works') +
               event('pause', 'TestBridgeFixture/works') +
               event('cont', 'TestBridgeFixture/works') +
               event('output', 'TestBridgeFixture/works') +
               event('pass', 'TestBridgeFixture/works') +
               event('pass', 'TestBridgeFixture') + event('pass'))
        observed = self.verify(raw, raw_stderr=b'diagnostic\n')
        self.assertEqual(observed.raw_stdout, raw)
        self.assertEqual(observed.raw_stderr, b'diagnostic\n')
        self.assertEqual(observed.subtests, ('works',))
        self.assertFalse(observed.live_qualified)

    def test_duplicate_keys_invalid_utf8_and_truncated_stream_are_rejected(self):
        for raw, error in (
            (b'{"Action":"fail","Action":"pass","Package":"fixture"}\n' +
             passing_output(), 'duplicate Go JSON key'),
            (b'\xff\n' + passing_output(), 'malformed Go JSON'),
            (passing_output().rstrip(b'\n'), 'truncated Go JSON stream'),
        ):
            with self.subTest(error=error):
                with self.assertRaisesRegex(bridge.VerificationError, error):
                    self.verify(raw)

    def test_named_results_cannot_cross_packages_or_run_after_passing(self):
        raw = passing_output()
        cases = (
            (raw.replace(event('pass', 'TestBridgeFixture/works'),
                         event('pass', 'TestBridgeFixture/works', package='other')),
             'crossed package identity'),
            (raw.replace(event('run', 'TestBridgeFixture'), b'') +
             event('run', 'TestBridgeFixture'), 'absent, duplicate or incomplete'),
            (raw + event('run', 'TestBridgeFixture'), 'absent, duplicate or incomplete'),
            (raw + event('pass'), 'no unique passing outcome'),
            (raw + event('run', 'TestBridgeFixtureSibling'), 'unexpected test or subtest'),
        )
        for output, error in cases:
            with self.subTest(error=error):
                with self.assertRaisesRegex(bridge.VerificationError, error):
                    self.verify(output)

    def test_exit_code_requires_an_integer_zero(self):
        for code in (False, True, '0', 0.0, None, 1, -1):
            with self.subTest(code=code):
                with self.assertRaisesRegex(bridge.VerificationError, 'did not exit successfully'):
                    self.verify(passing_output(), exit_code=code)

    def test_subtest_selection_requires_unique_exact_names(self):
        for names in (['works'], ('works', 'works'), ('works child',), ('',), ('works.*',)):
            with self.subTest(names=names):
                with self.assertRaises(bridge.VerificationError):
                    self.verify(passing_output(), expected_subtests=names)

    def test_stderr_byte_limit_is_inclusive(self):
        stderr = b'x' * bridge.MAX_STDERR_BYTES
        self.assertEqual(self.verify(passing_output(), raw_stderr=stderr).raw_stderr, stderr)
        with self.assertRaisesRegex(bridge.VerificationError, 'exceeds its bound'):
            self.verify(passing_output(), raw_stderr=stderr + b'x')


class ContextVerificationBridge(unittest.TestCase):
    def shortDescription(self):
        return None

    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="ca-context-bridge-")
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.module = self.root / "module"
        self.module.mkdir()
        (self.module / "go.mod").write_text("module fixture\n\ngo 1.18\n", encoding="utf-8")
        self.source = self.module / "bridge_test.go"
        self.source.write_text(
            'package fixture\nimport "testing"\n'
            'func TestBridgeFixture(t *testing.T) { t.Run("works", func(t *testing.T) {}) }\n'
            'func TestBridgeFixtureSibling(t *testing.T) { t.Fatal("sibling selected") }\n',
            encoding="utf-8",
        )

    def run_fixture(self, **changes):
        args = dict(
            case="TestBridgeFixture", go_executable=GO, module_root=self.module,
            source_file=self.source, expected_go_sha256=digest(GO),
            expected_source_sha256=digest(self.source),
            expected_module_sha256=bridge.hash_go_module(self.module),
            expected_subtests=("works",),
        )
        args.update(changes)
        return bridge.run_go_case(**args)

    def installed_inputs(self, **changes):
        candidate = self.root / "candidate"
        candidate.mkdir(exist_ok=True)
        plugin = candidate / "plugin"
        plugin.mkdir(exist_ok=True)
        installation = plugin / "helpers" / "artifacts"
        installation.mkdir(parents=True, exist_ok=True)
        system = {"Windows": "windows", "Linux": "linux", "Darwin": "darwin"}[platform.system()]
        machine = {"amd64": "amd64", "x86_64": "amd64", "aarch64": "arm64", "arm64": "arm64"}[platform.machine().casefold()]
        name = f"ca-artifact-{system}-{machine}" + (".exe" if system == "windows" else "")
        binary = installation / name
        binary.write_bytes(b"inert test binary")
        release = installation / "release.json"
        release.write_text(json.dumps({
            "format": "codearbiter.artifact-release/0.1.0",
            "version": "0.1.0",
            "protocol": "codearbiter.artifact-api/0.1.0",
            "schema_version": "0.3.1",
            "binaries": {f"{system}/{machine}": {
                "file": binary.name, "sha256": digest(binary), "native_tested": True,
            }},
        }), encoding="utf-8")
        hooks = plugin / "hooks"
        hooks.mkdir(exist_ok=True)
        (hooks / "_artifactlib.py").write_text("# inert fixture\n", encoding="utf-8")
        prefix = "plugins/ca-codex/"
        members = {prefix + path.relative_to(plugin).as_posix(): {
            "size": path.stat().st_size, "sha256": digest(path),
        } for path in plugin.rglob("*") if path.is_file()}
        manifest = candidate / "artifact-package-cohort.json"
        manifest.write_text(json.dumps({
            "source_commit": "b" * 40, "source_tree": "c" * 40,
            "packages": {"codex": {"members": members}},
        }), encoding="utf-8")
        repo = self.root / "repository"
        repo.mkdir(exist_ok=True)
        empty_path = self.root / "empty-path"
        empty_path.mkdir(exist_ok=True)
        args = dict(
            host="codex", candidate_root=candidate, plugin_root=plugin,
            repository=repo, binary_sha256=digest(binary),
            candidate_commit="b" * 40, candidate_tree="c" * 40,
            candidate_manifest_path=manifest,
            candidate_manifest_sha256=digest(manifest),
            python_executable=Path(sys.executable),
            empty_path_dir=empty_path,
        )
        args.update(changes)
        return args


    def rebind_installed_release(self, inputs, raw):
        """Rebind inert fixture bytes so negatives test admission, not stale hashes."""
        release = inputs["plugin_root"] / "helpers" / "artifacts" / "release.json"
        release.write_bytes(raw)
        manifest = inputs["candidate_manifest_path"]
        cohort = json.loads(manifest.read_text(encoding="utf-8"))
        cohort["packages"]["codex"]["members"] = {
            "plugins/ca-codex/" + path.relative_to(inputs["plugin_root"]).as_posix(): {
                "size": path.stat().st_size, "sha256": digest(path),
            } for path in inputs["plugin_root"].rglob("*") if path.is_file()
        }
        manifest.write_text(json.dumps(cohort), encoding="utf-8")
        return {**inputs, "candidate_manifest_sha256": digest(manifest)}

    def test_installed_bridge_rejects_invalid_release_manifest_contract(self):
        inputs = self.installed_inputs()
        release_path = inputs["plugin_root"] / "helpers" / "artifacts" / "release.json"
        valid = json.loads(release_path.read_text(encoding="utf-8"))
        platform_key = next(iter(valid["binaries"]))
        # The optional field is permitted by the installed adapter. Merely
        # carrying it makes no qualification claim in this preflight fixture.
        with_optional = {**valid, "context_qualification": {}}
        inputs = self.rebind_installed_release(inputs, json.dumps(with_optional).encode())
        self.assertFalse(bridge.build_installed_invocation(**inputs).live_qualified)
        controls = []
        for field in ("format", "version", "protocol", "schema_version"):
            controls.append(("missing-" + field, {k: v for k, v in valid.items() if k != field}))
        for field, values in (
            ("format", ("unsupported", None, 1, [])),
            ("protocol", ("codearbiter.artifact-api/999.0.0", None, 1, [])),
            ("schema_version", ("999.0.0", None, 1, [])),
            ("version", (None, 1, True, [])),
        ):
            for value in values:
                controls.append((field + "-" + repr(value), {**valid, field: value}))
        controls.append(("unknown-top-level-field", {**valid, "unrecognized": True}))
        entry = valid["binaries"][platform_key]
        controls.append(("unknown-native-entry-field", {
            **valid, "binaries": {platform_key: {**entry, "unrecognized": True}},
        }))
        controls.append(("missing-binaries", {k: v for k, v in valid.items() if k != "binaries"}))
        for value in (None, [], "binaries", 1, True):
            controls.append(("binaries-" + repr(value), {**valid, "binaries": value}))
        controls.append(("missing-native-entry", {**valid, "binaries": {}}))
        for value in (None, [], "native", 1, True):
            controls.append(("native-entry-" + repr(value), {
                **valid, "binaries": {platform_key: value},
            }))
        for field in ("file", "sha256", "native_tested"):
            controls.append(("missing-native-" + field, {
                **valid, "binaries": {platform_key: {k: v for k, v in entry.items() if k != field}},
            }))
        for field, values in (
            ("file", (None, 1, True, [], {}, "")),
            ("sha256", (None, 1, True, [], {}, "", "bad", "g" * 64)),
            ("native_tested", (False, None, 0, 1, "true", [], {})),
        ):
            for value in values:
                controls.append(("native-" + field + "-" + repr(value), {
                    **valid, "binaries": {platform_key: {**entry, field: value}},
                }))
        for label, malformed in controls:
            with self.subTest(control=label):
                rebound = self.rebind_installed_release(inputs, json.dumps(malformed).encode())
                with self.assertRaises(bridge.VerificationError):
                    bridge.build_installed_invocation(**rebound)

    def test_installed_bridge_rejects_platform_filename_mismatch(self):
        for system, machine, wrong_name in (
            ("Windows", "AMD64", "ca-artifact-windows-amd64"),
            ("Windows", "ARM64", "ca-artifact-windows-amd64.exe"),
            ("Linux", "x86_64", "ca-artifact-linux-amd64.exe"),
            ("Linux", "aarch64", "ca-artifact-linux-amd64"),
            ("Darwin", "x86_64", "ca-artifact-darwin-amd64.exe"),
            ("Darwin", "arm64", "ca-artifact-darwin-amd64"),
        ):
            with self.subTest(system=system, machine=machine):
                with mock.patch.object(platform, "system", return_value=system), \
                        mock.patch.object(platform, "machine", return_value=machine):
                    inputs = self.installed_inputs()
                    self.assertFalse(bridge.build_installed_invocation(**inputs).live_qualified)
                    installation = inputs["plugin_root"] / "helpers" / "artifacts"
                    release = json.loads((installation / "release.json").read_text(encoding="utf-8"))
                    entry = next(iter(release["binaries"].values()))
                    (installation / entry["file"]).replace(installation / wrong_name)
                    entry["file"] = wrong_name
                    rebound = self.rebind_installed_release(inputs, json.dumps(release).encode())
                    with self.assertRaises(bridge.VerificationError):
                        bridge.build_installed_invocation(**rebound)

    def test_installed_bridge_rejects_oversized_release_before_launch(self):
        inputs = self.installed_inputs()
        release = inputs["plugin_root"] / "helpers" / "artifacts" / "release.json"
        raw = release.read_bytes()
        boundary = raw + b" " * (65_536 - len(raw))
        accepted = self.rebind_installed_release(inputs, boundary)
        self.assertFalse(bridge.build_installed_invocation(**accepted).live_qualified)
        oversized = self.rebind_installed_release(inputs, boundary + b" ")
        with self.assertRaises(bridge.VerificationError):
            bridge.build_installed_invocation(**oversized)

    def test_windows_arm64_installed_inputs_bind_native_release(self):
        with mock.patch.object(platform, "system", return_value="Windows"), \
                mock.patch.object(platform, "machine", return_value="ARM64"):
            inputs = self.installed_inputs()
            release = inputs["plugin_root"] / "helpers" / "artifacts" / "release.json"
            self.assertIn("windows/arm64", json.loads(release.read_text(
                encoding="utf-8"))["binaries"])
            invocation = bridge.build_installed_invocation(**inputs)
        self.assertEqual(invocation.proof_kind, "candidate-preflight")

    def test_unknown_installed_architecture_remains_unsupported(self):
        inputs = self.installed_inputs()
        with mock.patch.object(platform, "machine", return_value="unknown-cpu"):
            with self.assertRaisesRegex(bridge.VerificationError, "platform is unsupported"):
                bridge.build_installed_invocation(**inputs)

    def test_go_bridge_observes_a_real_named_fixture(self):
        observation = self.run_fixture()
        self.assertEqual(observation.exit_code, 0)
        self.assertIn(b'"Test":"TestBridgeFixture"', observation.raw_stdout)
        self.assertNotIn(b'"Test":"TestBridgeFixtureSibling"', observation.raw_stdout)
        self.assertEqual(observation.test_name, "TestBridgeFixture")
        self.assertEqual(observation.subtests, ("works",))
        self.assertEqual(observation.proof_kind, "fixture")
        self.assertEqual(observation.go_sha256, digest(GO))
        self.assertEqual(observation.source_sha256, digest(self.source))
        original = os.environ.get("GOFLAGS")
        try:
            os.environ["GOFLAGS"] = "-toolexec=missing-untrusted-wrapper"
            overridden = self.run_fixture()
            self.assertEqual(overridden.exit_code, 0)
            self.assertIn(b'"Test":"TestBridgeFixture"', overridden.raw_stdout)
        finally:
            if original is None:
                os.environ.pop("GOFLAGS", None)
            else:
                os.environ["GOFLAGS"] = original

    def test_go_bridge_rejects_missing_duplicate_skipped_failed_and_zero_match(self):
        baseline = passing_output()
        controls = (
            baseline.replace(event("pass", "TestBridgeFixture"), b""),
            baseline.replace(event("pass", "TestBridgeFixture"), event("pass", "TestBridgeFixture") * 2),
            baseline.replace(event("pass", "TestBridgeFixture"), event("skip", "TestBridgeFixture")),
            baseline.replace(event("pass", "TestBridgeFixture"), event("fail", "TestBridgeFixture")),
            event("pass"),
            baseline.replace(event("pass", "TestBridgeFixture/works"), b""),
        )
        for raw in controls:
            with self.subTest(raw=raw):
                with self.assertRaises(bridge.VerificationError):
                    bridge.verify_go_output(raw, b"", 0, "TestBridgeFixture", ("works",))
        with self.assertRaises(bridge.VerificationError):
            bridge.verify_go_output(baseline, b"", 1, "TestBridgeFixture", ("works",))
        self.source.write_text(
            'package fixture\nimport "testing"\n'
            'func TestBridgeFixture(t *testing.T) { t.Fatal("controlled failure") }\n',
            encoding="utf-8",
        )
        with self.assertRaises(bridge.VerificationError) as failed:
            self.run_fixture(expected_subtests=())
        self.assertNotEqual(failed.exception.exit_code, 0)
        self.assertIn(b'"Test":"TestBridgeFixture"', failed.exception.raw_stdout)
        self.assertLessEqual(len(failed.exception.raw_stdout), bridge.MAX_STDOUT_BYTES)

    def test_go_bridge_accepts_unselected_packages_not_skipped_named_tests(self):
        # The required ./... invocation includes packages without test files.
        # Their package-level skip is not a skipped selected test.
        idle = self.module / "idle"
        idle.mkdir()
        (idle / "idle.go").write_text("package idle\n", encoding="utf-8")
        observation = self.run_fixture()
        records = [json.loads(line) for line in observation.raw_stdout.splitlines()]
        self.assertTrue(any(record.get("Package") == "fixture/idle" and
                            record.get("Action") == "skip" and
                            "Test" not in record for record in records))
        self.assertEqual(observation.exit_code, 0)

        baseline = passing_output()
        # Skip/pass ordering must not let the selected package gain a pass.
        # These parser controls are synthetic, distinct from the real run.
        for raw in (
            event("skip") + baseline,
            baseline + event("skip"),
            baseline.replace(event("pass"), event("skip")),
            baseline + event("fail", package="unselected"),
            baseline + event("skip", "TestBridgeFixture", package="unselected"),
        ):
            with self.subTest(raw=raw):
                with self.assertRaises(bridge.VerificationError):
                    bridge.verify_go_output(raw, b"", 0, "TestBridgeFixture", ("works",))

    def test_go_bridge_binds_cwd_executable_and_source(self):
        wrong_module = self.root / "other"
        wrong_module.mkdir()
        (wrong_module / "go.mod").write_text("module other\n", encoding="utf-8")
        for changes in (
            {"module_root": wrong_module},
            {"go_executable": self.source},
            {"expected_go_sha256": "0" * 64},
            {"expected_source_sha256": "0" * 64},
            {"expected_module_sha256": "0" * 64},
            {"source_file": self.root / "missing_test.go"},
            {"case": "TestUnapprovedTarget"},
        ):
            with self.subTest(changes=changes):
                with self.assertRaises(bridge.VerificationError):
                    self.run_fixture(**changes)
        unrelated_source = self.module / "other.go"
        original_module_hash = bridge.hash_go_module(self.module)
        unrelated_source.write_text("package fixture\n", encoding="utf-8")
        with self.assertRaises(bridge.VerificationError):
            self.run_fixture(expected_module_sha256=original_module_hash)
        self.source.write_text(
            'package fixture\nimport ("os"; "testing")\n'
            'func TestBridgeFixture(t *testing.T) { '
            'if err := os.WriteFile("mutable.txt", []byte("changed"), 0600); err != nil { t.Fatal(err) } }\n',
            encoding="utf-8",
        )
        (self.module / "mutable.txt").write_text("original", encoding="utf-8")
        with self.assertRaises(bridge.VerificationError) as changed:
            self.run_fixture(expected_subtests=())
        self.assertIn("changed during the run", str(changed.exception))
        self.assertEqual(changed.exception.exit_code, 0)
        self.assertIn(b'"Test":"TestBridgeFixture"', changed.exception.raw_stdout)
        self.assertLessEqual(len(changed.exception.raw_stdout), bridge.MAX_STDOUT_BYTES)

    def test_bridge_rejects_malformed_or_unbounded_output(self):
        for raw in (b"", b"not-json\n", b"[]\n", b'{}\n', b'{}\n' * 700_000):
            with self.subTest(size=len(raw)):
                with self.assertRaises(bridge.VerificationError):
                    bridge.verify_go_output(raw, b"", 0, "TestBridgeFixture", ("works",))
        with self.assertRaises(bridge.VerificationError):
            bridge.verify_go_output(passing_output(), b"e" * 2_000_000, 0, "TestBridgeFixture", ("works",))

    def test_installed_bridge_requires_all_exact_candidate_inputs(self):
        valid = self.installed_inputs()
        invocation = bridge.build_installed_invocation(**valid)
        self.assertEqual(invocation.cwd, valid["repository"].resolve())
        self.assertEqual(invocation.argv[1:3], ("-I", "-B"))
        self.assertEqual(invocation.argv[3], str(Path(__file__).with_name("test_artifact_installed_host.py").resolve()))
        for name, bad in (
            ("host", "unknown"), ("plugin_root", self.root),
            ("repository", valid["plugin_root"]), ("binary_sha256", "f" * 64),
            ("candidate_commit", "d" * 40), ("candidate_tree", "e" * 40),
            ("candidate_manifest_sha256", "d" * 64),
            ("candidate_manifest_path", self.root / "missing.json"),
            ("python_executable", Path("python")),
        ):
            with self.subTest(name=name):
                with self.assertRaises(bridge.VerificationError):
                    bridge.build_installed_invocation(**{**valid, name: bad})
        installation = valid["plugin_root"] / "helpers" / "artifacts"
        release = json.loads((installation / "release.json").read_text(encoding="utf-8"))
        binary = installation / next(iter(release["binaries"].values()))["file"]
        binary.write_bytes(b"changed after cohort capture")
        with self.assertRaises(bridge.VerificationError):
            bridge.build_installed_invocation(**valid)

    def test_installed_bridge_enforces_empty_path_and_no_pythonpath(self):
        valid = self.installed_inputs()
        invocation = bridge.build_installed_invocation(**valid)
        self.assertEqual(invocation.environment["PATH"], str(valid["empty_path_dir"].resolve()))
        self.assertNotIn("PYTHONPATH", invocation.environment)
        self.assertEqual(invocation.environment["PYTHONDONTWRITEBYTECODE"], "1")
        pollution = valid["empty_path_dir"] / "pollution"
        pollution.write_text("x", encoding="utf-8")
        with self.assertRaises(bridge.VerificationError):
            bridge.build_installed_invocation(**valid)
        pollution.unlink()
        with self.assertRaises(bridge.VerificationError):
            bridge.build_installed_invocation(**self.installed_inputs(empty_path_dir=self.root / "absent"))
        original = {name: os.environ.get(name) for name in ("PYTHONPATH", "PYTHONHOME")}
        try:
            os.environ["PYTHONPATH"] = str(self.root / "development-checkout")
            os.environ["PYTHONHOME"] = str(self.root / "development-checkout")
            invocation = bridge.build_installed_invocation(**self.installed_inputs())
            self.assertNotIn("PYTHONPATH", invocation.environment)
            self.assertNotIn("PYTHONHOME", invocation.environment)
        finally:
            for name, value in original.items():
                if value is None:
                    os.environ.pop(name, None)
                else:
                    os.environ[name] = value

    def test_bridge_fixture_results_cannot_claim_live_authority(self):
        observation = bridge.verify_go_output(
            passing_output(), b"", 0, "TestBridgeFixture", ("works",)
        )
        self.assertEqual(observation.proof_kind, "fixture")
        self.assertFalse(observation.live_qualified)
        invocation = bridge.build_installed_invocation(**self.installed_inputs())
        self.assertEqual(invocation.proof_kind, "candidate-preflight")
        self.assertFalse(invocation.live_qualified)
        with self.assertRaises(bridge.VerificationError):
            bridge.build_installed_invocation(**self.installed_inputs(proof_kind="live-qualified"))


if __name__ == "__main__":
    unittest.main()
