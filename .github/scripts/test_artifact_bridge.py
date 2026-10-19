#!/usr/bin/env python3
"""Tests the real executable through the stdlib installed-payload bridge."""
from __future__ import annotations
import hashlib
import json
import os
import platform
from pathlib import Path
import shutil
import stat
import subprocess
import sys
import tempfile
import unittest
from unittest import mock
REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0,str(REPO/"core/pysrc"))
from _artifactlib import (
    DEFAULT_ENGINE_TIMEOUT_SECONDS,
    ArtifactClient,
    ArtifactError,
    _select_authoring_route,
    _stage_darwin_executable,
    checked_spec_index,
)
from test_artifact_authoring import physical_test_directory
INSTALLATION = None

def setUpModule():
    global INSTALLATION
    configured = os.environ.get("ARTIFACT_TEST_INSTALLATION")
    if configured:
        INSTALLATION = Path(configured).resolve(strict=True)
    else:
        temporary = tempfile.TemporaryDirectory(prefix="ca-artifact-test-install-")
        unittest.addModuleCleanup(temporary.cleanup)
        INSTALLATION = physical_test_directory(temporary.name)/"payload"
        subprocess.run([sys.executable,str(REPO/"tools/build-artifacts.py"),
                        "--output",str(INSTALLATION)],check=True,stdout=subprocess.PIPE,stderr=subprocess.PIPE)


class EngineTimeoutTests(unittest.TestCase):
    """A whole-tree snapshot on a large Windows repository took ~30s, the old
    hard-coded bound, so every publish/arm/verify timed out. The default must
    leave headroom, an operator override must be honored, and a malformed
    override must refuse rather than silently fall back to a default."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(); self.addCleanup(self.tmp.cleanup)
        self.directory = physical_test_directory(self.tmp.name)

    def client(self, **kwargs):
        return ArtifactClient(self.directory, self.directory, **kwargs)

    def test_default_leaves_headroom_over_a_thirty_second_snapshot(self):
        with mock.patch.dict(os.environ, {}, clear=False):
            os.environ.pop("CODEARBITER_ENGINE_TIMEOUT", None)
            self.assertEqual(DEFAULT_ENGINE_TIMEOUT_SECONDS, 120)
            self.assertEqual(self.client().timeout, 120)

    def test_environment_override_is_honored(self):
        with mock.patch.dict(os.environ, {"CODEARBITER_ENGINE_TIMEOUT": "300"}):
            self.assertEqual(self.client().timeout, 300)
        with mock.patch.dict(os.environ, {"CODEARBITER_ENGINE_TIMEOUT": "45.5"}):
            self.assertEqual(self.client().timeout, 45.5)

    def test_explicit_timeout_wins_over_environment(self):
        with mock.patch.dict(os.environ, {"CODEARBITER_ENGINE_TIMEOUT": "300"}):
            self.assertEqual(self.client(timeout=7).timeout, 7)

    def test_malformed_override_refuses(self):
        for value in ("", "abc", "0", "-5", "nan", "inf", "3601", " 60"):
            with self.subTest(value=value), mock.patch.dict(os.environ, {"CODEARBITER_ENGINE_TIMEOUT": value}):
                with self.assertRaises(ArtifactError) as raised:
                    self.client()
                self.assertEqual(raised.exception.code, "INVALID_ENGINE_TIMEOUT")

    def test_timeout_reaches_the_bounded_child(self):
        import _artifactlib
        with mock.patch.dict(os.environ, {"CODEARBITER_ENGINE_TIMEOUT": "300"}):
            client = ArtifactClient(self.directory, INSTALLATION)
        seen = []

        def fake(argv, request, fd, timeout, **kwargs):
            seen.append(timeout)
            raise ArtifactError("TIMEOUT", "stop")
        with mock.patch.object(_artifactlib, "_bounded_child", fake):
            with self.assertRaises(ArtifactError):
                client.call("identity", {"artifact_id": "SPEC-X"})
        self.assertEqual(seen, [300], "the configured bound must be the one the engine child is waited on")


class PlatformSelectionTests(unittest.TestCase):
    def kernel(self, native, emulated=0, success=True):
        kernel = mock.Mock()
        kernel.GetCurrentProcess.return_value = -1

        def query(handle, process_machine, native_machine):
            self.assertEqual(handle, -1)
            process_machine._obj.value = emulated
            native_machine._obj.value = native
            return success

        kernel.IsWow64Process2.side_effect = query
        return kernel

    def test_windows_empty_machine_selects_native_not_emulated_architecture(self):
        for native, emulated, expected in ((0x8664, 0x014C, "amd64"), (0xAA64, 0x8664, "arm64")):
            with self.subTest(native=native), \
                    mock.patch("_artifactlib.platform.system", return_value="Windows"), \
                    mock.patch("_artifactlib.platform.machine", return_value=""), \
                    mock.patch("ctypes.WinDLL", return_value=self.kernel(native, emulated), create=True):
                self.assertEqual(ArtifactClient._binary_name(), f"ca-artifact-windows-{expected}.exe")

    def test_windows_native_query_failure_or_unsupported_cpu_refuses(self):
        for native, success in ((0x8664, False), (0, True), (0x014C, True), (0xFFFF, True)):
            with self.subTest(native=native, success=success), \
                    mock.patch("_artifactlib.platform.system", return_value="Windows"), \
                    mock.patch("_artifactlib.platform.machine", return_value=""), \
                    mock.patch.dict(os.environ, {"PROCESSOR_ARCHITECTURE": "AMD64"}), \
                    mock.patch("ctypes.WinDLL", return_value=self.kernel(native, success=success), create=True):
                with self.assertRaises(ArtifactError) as raised:
                    ArtifactClient._binary_name()
                self.assertEqual(raised.exception.code, "UNSUPPORTED_PLATFORM")

    def test_windows_native_api_unavailable_refuses(self):
        for failure in (OSError("loader unavailable"), AttributeError("API unavailable")):
            with self.subTest(failure=type(failure).__name__), \
                    mock.patch("_artifactlib.platform.system", return_value="Windows"), \
                    mock.patch("_artifactlib.platform.machine", return_value=""), \
                    mock.patch("ctypes.WinDLL", side_effect=failure, create=True):
                with self.assertRaises(ArtifactError) as raised:
                    ArtifactClient._binary_name()
                self.assertEqual(raised.exception.code, "UNSUPPORTED_PLATFORM")

    def test_existing_platform_aliases_do_not_probe_windows(self):
        for system, prefix, suffix in (("Linux", "linux", ""), ("Darwin", "darwin", ""), ("Windows", "windows", ".exe")):
            for machine, arch in (("x86_64", "amd64"), ("AMD64", "amd64"), ("aarch64", "arm64"), ("ARM64", "arm64")):
                with self.subTest(system=system, machine=machine), \
                        mock.patch("_artifactlib.platform.system", return_value=system), \
                        mock.patch("_artifactlib.platform.machine", return_value=machine), \
                        mock.patch("ctypes.WinDLL", create=True) as loader:
                    self.assertEqual(ArtifactClient._binary_name(), f"ca-artifact-{prefix}-{arch}{suffix}")
                    loader.assert_not_called()

    def test_unknown_platform_or_nonempty_architecture_never_falls_back(self):
        for system, machine in (("Linux", ""), ("Darwin", ""), ("Other", "AMD64"), ("Windows", "mips")):
            with self.subTest(system=system, machine=machine), \
                    mock.patch("_artifactlib.platform.system", return_value=system), \
                    mock.patch("_artifactlib.platform.machine", return_value=machine), \
                    mock.patch("ctypes.WinDLL", create=True) as loader:
                with self.assertRaises(ArtifactError) as raised:
                    ArtifactClient._binary_name()
                self.assertEqual(raised.exception.code, "UNSUPPORTED_PLATFORM")
                loader.assert_not_called()


class BridgeTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup)
        self.test_directory=physical_test_directory(self.tmp.name)
        self.root=self.test_directory/"repo";self.root.mkdir()
        self.client=ArtifactClient(self.root,INSTALLATION)

    def create(self):
        return self.client.call("create",{"operation_id":"bridge-spec-create","artifact_id":"SPEC-BRIDGE","kind":"spec","slug":"bridge","title":"Bridge fixture","summary":"Incomplete draft, not an approved fixture."})

    def repository_bytes(self):
        return {
            path.relative_to(self.root).as_posix(): path.read_bytes()
            for path in sorted(self.root.rglob("*"))
            if path.is_file()
        }

    def damaged_installation(self, name, mutate):
        destination = self.test_directory / name
        shutil.copytree(INSTALLATION, destination)
        release_path = destination / "release.json"
        release = json.loads(release_path.read_text(encoding="utf-8"))
        mutate(destination, release)
        release_path.write_text(json.dumps(release), encoding="utf-8")
        return destination

    def test_real_cli_draft_and_index(self):
        caps=self.client.call("capabilities");self.assertEqual(caps["public_registrations_added"],0)
        self.create();items=list(self.client.index("spec"));self.assertEqual(len(items),1)
        self.assertFalse(items[0]["authority"]["authority_verified"])
        result=self.client.call("validate",{"artifact_id":"SPEC-BRIDGE","gate":"ready"},permit_invalid=True)
        self.assertFalse(result["valid"])
        self.assertEqual(checked_spec_index(self.root,INSTALLATION),[])

    @unittest.skipUnless(platform.system() == "Windows", "requires the real Windows architecture API")
    def test_windows_empty_machine_uses_native_architecture(self):
        self.create()
        request = {"artifact_id": "SPEC-BRIDGE"}
        expected = self.client.call("identity", request)
        before = self.repository_bytes()
        # Reproduce the missing Python metadata from #986. The Windows API,
        # pinned executable, package checks and native read remain real.
        with mock.patch("_artifactlib.platform.machine", return_value=""):
            actual = self.client.call("identity", request)
        self.assertEqual(actual, expected)
        self.assertEqual(self.repository_bytes(), before)

    @unittest.skipUnless(platform.system() == "Windows", "requires the real Windows architecture API")
    def test_windows_empty_machine_preserves_payload_integrity_checks(self):
        name = self.client._binary_name()
        manifest = json.loads((INSTALLATION / "release.json").read_text(encoding="utf-8"))
        cell = next(key for key, entry in manifest["binaries"].items() if entry["file"] == name)

        def corrupt(destination, release):
            binary = destination / name
            binary.write_bytes(binary.read_bytes() + b"changed")

        def unqualified(destination, release):
            release["binaries"][cell]["native_tested"] = False

        def absent(destination, release):
            release["binaries"].pop(cell)

        for damage, code in ((corrupt, "PACKAGE_INTEGRITY"), (unqualified, "UNVERIFIED_PLATFORM"), (absent, "CAPABILITY_MISSING")):
            destination = self.damaged_installation(damage.__name__, damage)
            with self.subTest(damage=damage.__name__), mock.patch("_artifactlib.platform.machine", return_value=""):
                with self.assertRaises(ArtifactError) as raised:
                    ArtifactClient(self.root, destination).call("capabilities")
                self.assertEqual(raised.exception.code, code)

    def test_tampered_view_is_not_readable(self):
        self.create();p=self.root/".codearbiter/specs/bridge.html"
        p.write_bytes(p.read_bytes().replace(b"Bridge fixture",b"Modified view",1))
        with self.assertRaises(ArtifactError) as got:list(self.client.index())
        self.assertEqual(got.exception.code,"RENDER_DRIFT")

    def test_unknown_request_fields(self):
        with self.assertRaises(ArtifactError):self.client.call("create",{"force":True})

    def test_changed_installed_binary(self):
        dest=self.test_directory/"installation";shutil.copytree(INSTALLATION,dest)
        system={"Linux":"linux","Darwin":"darwin","Windows":"windows"}[platform.system()]
        arch={"x86_64":"amd64","amd64":"amd64","aarch64":"arm64","arm64":"arm64"}[platform.machine().lower()]
        manifest=json.loads((dest/"release.json").read_text());name=manifest["binaries"][system+"/"+arch]["file"]
        p=dest/name;p.write_bytes(p.read_bytes()+b"changed")
        with self.assertRaises(ArtifactError) as got:ArtifactClient(self.root,dest).call("capabilities")
        self.assertEqual(got.exception.code,"PACKAGE_INTEGRITY")

    def test_new_html_route_reports_actionable_capability_error_before_writing(self):
        (self.root / ".codearbiter" / "specs").mkdir(parents=True)
        (self.root / ".codearbiter" / "plans").mkdir(parents=True)

        def corrupt_binary(destination, release):
            # A released payload can contain several platforms. Corrupt the
            # binary this host will execute, not the manifest's first entry.
            system = {"Linux": "linux", "Darwin": "darwin", "Windows": "windows"}[platform.system()]
            architecture = {"x86_64": "amd64", "amd64": "amd64",
                            "aarch64": "arm64", "arm64": "arm64"}[platform.machine().lower()]
            entry = release["binaries"][f"{system}/{architecture}"]
            binary = destination / entry["file"]
            binary.write_bytes(binary.read_bytes() + b"corrupt")

        def unsupported_cell(_destination, release):
            release["binaries"] = {}

        def incompatible_protocol(_destination, release):
            release["protocol"] = "codearbiter.artifact-api/999.0.0"

        installations = {
            "missing": self.test_directory / "missing-payload",
            "corrupt": self.damaged_installation("corrupt-payload", corrupt_binary),
            "unsupported": self.damaged_installation("unsupported-payload", unsupported_cell),
            "incompatible": self.damaged_installation("incompatible-payload", incompatible_protocol),
        }
        installations["missing"].mkdir()
        before = self.repository_bytes()
        for name, installation in installations.items():
            with self.subTest(payload=name):
                client = ArtifactClient(self.root, installation)
                with self.assertRaises(ArtifactError) as got:
                    _select_authoring_route(
                        self.root,
                        "new-work",
                        workflow="feature",
                        lane="full",
                        client=client,
                        html_requested=True,
                    )
                self.assertEqual(got.exception.code, "CAPABILITY_MISSING")
                self.assertIn("repair or reinstall", str(got.exception))
                self.assertEqual(self.repository_bytes(), before)

    def test_existing_html_mutation_revalidates_payload_before_writing(self):
        self.create()
        identity = self.client.call("identity", {"artifact_id": "SPEC-BRIDGE"})
        system = {"Linux": "linux", "Darwin": "darwin", "Windows": "windows"}[
            platform.system()
        ]
        architecture = {
            "x86_64": "amd64",
            "amd64": "amd64",
            "aarch64": "arm64",
            "arm64": "arm64",
        }[platform.machine().lower()]
        current_cell = f"{system}/{architecture}"

        def corrupt_binary(destination, release):
            binary = destination / release["binaries"][current_cell]["file"]
            binary.write_bytes(binary.read_bytes() + b"corrupt")

        def advertise_other_cell(_destination, release):
            other_architecture = "arm64" if architecture == "amd64" else "amd64"
            release["binaries"] = {
                f"{system}/{other_architecture}": release["binaries"][current_cell]
            }

        def mismatch_binary_identity(_destination, release):
            release["binaries"][current_cell]["file"] = "wrong-artifact-binary"

        def mismatch_protocol(_destination, release):
            release["protocol"] = "codearbiter.artifact-api/999.0.0"

        missing = self.test_directory / "missing-existing-mutation"
        missing.mkdir()
        installations = {
            "missing": (missing, "CAPABILITY_MISSING"),
            "corrupt": (
                self.damaged_installation("corrupt-existing-mutation", corrupt_binary),
                "PACKAGE_INTEGRITY",
            ),
            "unsupported-advertised-cell": (
                self.damaged_installation(
                    "unsupported-existing-mutation", advertise_other_cell
                ),
                "CAPABILITY_MISSING",
            ),
            "manifest-binary-identity": (
                self.damaged_installation(
                    "identity-existing-mutation", mismatch_binary_identity
                ),
                "INVALID_INSTALLATION",
            ),
            "protocol-mismatch": (
                self.damaged_installation(
                    "protocol-existing-mutation", mismatch_protocol
                ),
                "UNSUPPORTED_VERSION",
            ),
        }
        before = self.repository_bytes()
        for name, (installation, error_code) in installations.items():
            with self.subTest(payload=name):
                broken = ArtifactClient(self.root, installation)
                with self.assertRaises(ArtifactError) as got:
                    broken.call(
                        "apply",
                        {
                            "artifact_id": "SPEC-BRIDGE",
                            "operation_id": f"must-not-write-{name}",
                            "expected": {
                                "revision": identity["revision"],
                                "model_sha256": identity["model_sha256"],
                            },
                            "changes": [],
                        },
                    )
                self.assertEqual(got.exception.code, error_code)
                self.assertEqual(self.repository_bytes(), before)

    def test_legacy_markdown_route_remains_usable_with_missing_payload(self):
        specs = self.root / ".codearbiter" / "specs"
        plans = self.root / ".codearbiter" / "plans"
        specs.mkdir(parents=True)
        plans.mkdir(parents=True)
        spec = specs / "legacy.md"
        plan = plans / "legacy.md"
        spec.write_text("# Existing specification\n", encoding="utf-8")
        plan.write_text("# Existing plan\n", encoding="utf-8")
        empty_installation = self.test_directory / "empty-installation"
        empty_installation.mkdir()
        selected = _select_authoring_route(
            self.root,
            "legacy",
            workflow="feature",
            lane="full",
            client=ArtifactClient(self.root, empty_installation),
        )
        self.assertEqual(selected["format"], "md")
        self.assertEqual(selected["state"], "pair")
        self.assertEqual(selected["spec_path"], spec)
        self.assertEqual(selected["plan_path"], plan)

    def test_symlink_binary_rejected(self):
        dest=self.test_directory/"installation";dest.mkdir()
        shutil.copy(INSTALLATION/"release.json",dest/"release.json")
        for p in INSTALLATION.glob("ca-artifact-*"):(dest/p.name).symlink_to(p)
        with self.assertRaises(ArtifactError):ArtifactClient(self.root,dest).call("capabilities")

    def test_linked_or_reparse_installation_directory_rejected(self):
        linked=self.test_directory/"linked-installation"
        if os.name == "nt":
            subprocess.run(["cmd","/c","mklink","/J",str(linked),str(INSTALLATION)],
                           check=True,stdout=subprocess.PIPE,stderr=subprocess.PIPE)
        else:
            linked.symlink_to(INSTALLATION,target_is_directory=True)
        with self.assertRaises(ArtifactError):ArtifactClient(self.root,linked)

    def test_artifact_mutations_never_execute_content(self):
        self.create();identity=self.client.call("identity",{"artifact_id":"SPEC-BRIDGE"})
        marker=self.root/"SHOULD_NOT_EXIST"
        request={"artifact_id":"SPEC-BRIDGE","operation_id":"bridge-inert-update","expected":{"revision":identity["revision"],"model_sha256":identity["model_sha256"]},"changes":[{"op":"record.update","symbol":"INTENT-01","fields":{"problem":f"$(touch {marker}) <script>alert(1)</script>"}}]}
        self.client.call("apply",request);self.assertFalse(marker.exists())
        data=self.client.call("read",{"artifact_id":"SPEC-BRIDGE","symbol":"INTENT-01","mode":"exact"})
        self.assertIn("<script>",data["record"]["problem"])

    def test_helper_child_receives_no_parent_environment(self):
        real_popen = subprocess.Popen
        calls = []

        def recording_popen(*args, **kwargs):
            calls.append(kwargs.copy())
            return real_popen(*args, **kwargs)

        with mock.patch.dict(os.environ, {"PATH": "", "CODEARBITER_GIT_EXECUTABLE": "",
                                          "ARTIFACT_SECRET_FIXTURE": "must-not-cross"}), \
                mock.patch.object(subprocess, "Popen", side_effect=recording_popen):
            self.client.call("capabilities")
        self.assertEqual(calls[-1].get("env"), {})

    def test_darwin_staging_uses_only_the_verified_open_descriptor(self):
        source = self.test_directory / "source-binary"
        source.write_bytes(b"verified executable bytes")
        descriptor = os.open(source, os.O_RDONLY)
        self.addCleanup(os.close, descriptor)
        if os.name != "nt":
            source.unlink()
            source.write_bytes(b"substituted pathname bytes")
        stage = self.test_directory / "stage"
        stage.mkdir()
        executable = _stage_darwin_executable(descriptor, stage)
        self.assertEqual(executable.read_bytes(), b"verified executable bytes")
        if os.name != "nt":
            self.assertTrue(executable.stat().st_mode & stat.S_IXUSR)

class StoreInitTests(unittest.TestCase):
    """A fresh checkout has no local store; the bridge initializes it once, explicitly."""

    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup)
        self.root=physical_test_directory(self.tmp.name)/"repo";self.root.mkdir()

    def scripted(self, answers, **options):
        client=ArtifactClient(self.root,INSTALLATION,**options)
        calls=[]
        def exchange(operation, request, permit_invalid=False):
            calls.append(operation)
            answer=answers.pop(0)
            if isinstance(answer,ArtifactError):
                raise answer
            return answer
        client._exchange=exchange
        return client,calls

    def test_no_local_store_initializes_then_retries_once(self):
        identity={"artifact_id":"SPEC-BRIDGE","revision":1}
        client,calls=self.scripted([ArtifactError("NO_LOCAL_STORE","absent"),{"store":"created"},identity])
        self.assertEqual(client.call("identity",{"artifact_id":"SPEC-BRIDGE"}),identity)
        self.assertEqual(calls,["identity","init-store","identity"])

    def test_refused_initialization_keeps_no_local_store(self):
        client,calls=self.scripted([ArtifactError("NO_LOCAL_STORE","absent"),ArtifactError("LOCK_FAILED","read-only")])
        with self.assertRaises(ArtifactError) as raised:
            client.call("identity",{"artifact_id":"SPEC-BRIDGE"})
        self.assertEqual(raised.exception.code,"NO_LOCAL_STORE")
        self.assertIn("LOCK_FAILED",str(raised.exception))
        self.assertEqual(calls,["identity","init-store"])
        # A retried read that still finds no store is not retried again.
        client,calls=self.scripted([ArtifactError("NO_LOCAL_STORE","absent"),{"store":"created"},ArtifactError("NO_LOCAL_STORE","absent")])
        with self.assertRaises(ArtifactError) as raised:
            client.call("identity",{"artifact_id":"SPEC-BRIDGE"})
        self.assertEqual(raised.exception.code,"NO_LOCAL_STORE")
        self.assertEqual(calls,["identity","init-store","identity"])
        # Disabled initialization never writes.
        client,calls=self.scripted([ArtifactError("NO_LOCAL_STORE","absent")],initialize_store=False)
        with self.assertRaises(ArtifactError) as raised:
            client.call("identity",{"artifact_id":"SPEC-BRIDGE"})
        self.assertEqual(raised.exception.code,"NO_LOCAL_STORE")
        self.assertEqual(calls,["identity"])

    def test_fresh_checkout_identity_through_client(self):
        client=ArtifactClient(self.root,INSTALLATION)
        client.call("create",{"operation_id":"store-init-spec-create","artifact_id":"SPEC-BRIDGE","kind":"spec","slug":"bridge","title":"Bridge fixture","summary":"Incomplete draft."})
        store=self.root/".codearbiter"/".artifacts"
        shutil.rmtree(store)
        if platform.system()=="Windows":
            with self.assertRaises(ArtifactError) as raised:
                ArtifactClient(self.root,INSTALLATION,initialize_store=False).call("identity",{"artifact_id":"SPEC-BRIDGE"})
            self.assertEqual(raised.exception.code,"NO_LOCAL_STORE")
            self.assertFalse(store.exists())
        self.assertEqual(client.call("identity",{"artifact_id":"SPEC-BRIDGE"})["artifact_id"],"SPEC-BRIDGE")
        if platform.system()!="Linux":  # Linux locks the repository directory itself.
            self.assertTrue((store/"store.lock").is_file())

    def test_protocol_documents_init_store(self):
        text=(REPO/"docs/artifacts/PROTOCOL.md").read_text(encoding="utf-8")
        self.assertRegex(text,r'`init-store`[\s\S]{0,600}"store": "created"[\s\S]{0,300}"store": "present"')
        self.assertRegex(text,r"NO_LOCAL_STORE[\s\S]{0,900}`init-store`\s+once[\s\S]{0,300}retr(y|ies)\s+the\s+(original\s+)?(read|request|call)\s+once")


if __name__=="__main__":unittest.main(verbosity=2)
