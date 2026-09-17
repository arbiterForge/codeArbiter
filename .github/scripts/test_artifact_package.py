#!/usr/bin/env python3
"""Native artifact payload and cold-install contract tests."""
from __future__ import annotations

import importlib.util
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import textwrap
import unittest
from unittest import mock

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO / "core/pysrc"))
from _artifactlib import ArtifactClient
from test_artifact_authoring import physical_test_directory

INSTALLATION = None
INSTALLER = None
PACKAGER = None
BUILDER = None
FIXTURE_SOURCE_COMMIT = "a" * 40
FIXTURE_WORKFLOW_RUN = "123456789"
FIXTURE_WORKFLOW = ".github/workflows/ci.yml"


def setUpModule():
    global INSTALLATION, INSTALLER, PACKAGER, BUILDER
    configured = os.environ.get("ARTIFACT_TEST_INSTALLATION")
    if configured:
        INSTALLATION = Path(configured).resolve(strict=True)
    else:
        temporary = tempfile.TemporaryDirectory(prefix="ca-artifact-package-")
        unittest.addModuleCleanup(temporary.cleanup)
        INSTALLATION = physical_test_directory(temporary.name) / "payload"
        subprocess.run([sys.executable, str(REPO / "tools/build-artifacts.py"),
                        "--output", str(INSTALLATION)], check=True)
    spec = importlib.util.spec_from_file_location(
        "install_artifact_payload", REPO / "tools/install-artifact-payload.py")
    INSTALLER = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(INSTALLER)
    package_spec = importlib.util.spec_from_file_location(
        "build_host_packages", REPO / "tools/build-host-packages.py")
    PACKAGER = importlib.util.module_from_spec(package_spec)
    package_spec.loader.exec_module(PACKAGER)
    builder_spec = importlib.util.spec_from_file_location(
        "build_artifacts", REPO / "tools/build-artifacts.py")
    BUILDER = importlib.util.module_from_spec(builder_spec)
    builder_spec.loader.exec_module(BUILDER)


class PackageTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.base = physical_test_directory(self.tmp.name)

    def qualification(self, candidate=None, *, destination=None):
        candidate = candidate or INSTALLATION
        manifest = json.loads((candidate / "release.json").read_text(encoding="utf-8"))
        platform_name, entry = next(iter(manifest["binaries"].items()))
        receipt = {
            "format": "codearbiter.artifact-qualification/0.1.0",
            "source_commit": FIXTURE_SOURCE_COMMIT,
            "workflow": FIXTURE_WORKFLOW,
            "run_id": FIXTURE_WORKFLOW_RUN,
            "job": "artifact-engine",
            "platform": platform_name,
            "binary_sha256": entry["sha256"],
            "version": manifest["version"],
            "protocol": manifest["protocol"],
            "schema_version": manifest["schema_version"],
            "native_tests": [
                "artifact-bridge", "artifact-conformance", "artifact-native",
                "artifact-package", "go-test", "go-vet"
            ],
        }
        path = destination or (self.base / f"qualification-{platform_name.replace('/', '-')}.json")
        path.write_text(json.dumps(receipt), encoding="utf-8")
        return path

    def stage(self, *, candidates=None, output=None, required_platforms=None,
              qualification_receipts=None):
        candidates = candidates or [INSTALLATION]
        manifest = json.loads((candidates[0] / "release.json").read_text(encoding="utf-8"))
        native_platform = next(iter(manifest["binaries"]))
        return PACKAGER.stage_artifact_host_payloads(
            candidates=candidates,
            qualification_receipts=qualification_receipts or [self.qualification(candidates[0])],
            trusted_source_commit=FIXTURE_SOURCE_COMMIT,
            trusted_workflow=FIXTURE_WORKFLOW,
            trusted_workflow_run=FIXTURE_WORKFLOW_RUN,
            output=output or (self.base / "stage"),
            required_platforms=required_platforms or [native_platform],
            repo=REPO,
        )

    def test_native_cold_install_operates_without_source_tree(self):
        consumer = self.base / "consumer"
        repository = consumer / "repo"
        repository.mkdir(parents=True)
        if os.name == "nt":
            with self.assertRaisesRegex(ValueError, "release-packaging only"):
                INSTALLER.install_payload(consumer, "plugin", INSTALLATION)
            return
        installed = INSTALLER.install_payload(consumer, "plugin", INSTALLATION)
        caps = ArtifactClient(repository, installed).call("capabilities")
        self.assertTrue(caps["repository_operations_available"])
        self.assertFalse(caps["host_default_enabled"])

    def test_unqualified_binary_is_rejected_before_install(self):
        candidate = self.base / "candidate"
        shutil.copytree(INSTALLATION, candidate)
        manifest_path = candidate / "release.json"
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        next(iter(manifest["binaries"].values()))["native_tested"] = False
        manifest_path.write_text(json.dumps(manifest), encoding="utf-8")
        with self.assertRaisesRegex(ValueError, "unqualified platform entry"):
            INSTALLER.load_payload(candidate)

    def test_install_target_is_create_only(self):
        consumer = self.base / "consumer"
        consumer.mkdir()
        if os.name == "nt":
            with self.assertRaisesRegex(ValueError, "release-packaging only"):
                INSTALLER.install_payload(consumer, "plugin", INSTALLATION)
            return
        INSTALLER.install_payload(consumer, "plugin", INSTALLATION)
        with self.assertRaisesRegex(ValueError, "payload exists"):
            INSTALLER.install_payload(consumer, "plugin", INSTALLATION)

    def test_linked_installation_parent_cannot_escape(self):
        consumer = self.base / "consumer"
        external = self.base / "external"
        consumer.mkdir()
        external.mkdir()
        if os.name == "nt":
            with self.assertRaisesRegex(ValueError, "release-packaging only"):
                INSTALLER.install_payload(consumer, "plugin", INSTALLATION)
        else:
            (consumer / "plugin").symlink_to(external, target_is_directory=True)
            with self.assertRaises(OSError):
                INSTALLER.install_payload(consumer, "plugin", INSTALLATION)
        self.assertFalse((external / "helpers" / "artifacts").exists())

    def test_release_packaging_stages_package_owned_native_payloads(self):
        manifest = json.loads((INSTALLATION / "release.json").read_text(encoding="utf-8"))
        native_platform = next(iter(manifest["binaries"]))
        stage = self.base / "stage"
        result = self.stage(output=stage, required_platforms=[native_platform])
        self.assertEqual(result["platforms"], [native_platform])
        self.assertEqual(result["hosts"], ["claude", "codex", "pi"])
        for plugin_dir in ("plugins/ca", "plugins/ca-codex", "plugins/ca-pi"):
            installed = stage / plugin_dir / "helpers" / "artifacts"
            self.assertTrue((installed / "release.json").is_file())
            repository = self.base / ("repo-" + Path(plugin_dir).name)
            repository.mkdir()
            client = ArtifactClient(repository, installed)
            empty_path = self.base / "empty-path"
            empty_path.mkdir(exist_ok=True)
            with mock.patch.dict(os.environ, {"PATH": str(empty_path)}):
                capabilities = client.call("capabilities")
            self.assertTrue(capabilities["repository_operations_available"])
            self.assertFalse(capabilities["host_default_enabled"])

    def test_production_binary_has_no_network_capable_dependencies(self):
        completed = subprocess.run(
            ["go", "list", "-deps", "-f", "{{.ImportPath}}|{{.Standard}}",
             "./cmd/ca-artifact"],
            cwd=REPO / "core/artifacts", check=True, capture_output=True, text=True)
        dependencies = dict(line.rsplit("|", 1)
                            for line in completed.stdout.splitlines() if line)
        forbidden = sorted(package for package in dependencies
                           if package in {"net", "os/exec"}
                           or package.startswith(("net/http", "net/rpc", "net/smtp",
                                                  "crypto/tls", "golang.org/x/net")))
        self.assertEqual([], forbidden, "network-capable Go dependency entered the binary")
        module = "github.com/arbiterForge/codeArbiter/core/artifacts"
        third_party = sorted(package for package, standard in dependencies.items()
                             if standard == "false"
                             and package != module
                             and not package.startswith(module + "/"))
        self.assertEqual([], third_party, "unreviewed third-party dependency entered the binary")
        analyzer = self.base / "network_guard.go"
        analyzer.write_text(textwrap.dedent('''\
            package main

            import (
                "encoding/json"
                "fmt"
                "go/ast"
                "go/parser"
                "go/token"
                "io/fs"
                "os"
                "path/filepath"
                "sort"
                "strconv"
                "strings"
            )

            func main() {
                if len(os.Args) != 2 { panic("expected production Go root") }
                findings := []string{}
                err := filepath.WalkDir(os.Args[1], func(path string, entry fs.DirEntry, walkErr error) error {
                    if walkErr != nil { return walkErr }
                    if entry.IsDir() || !strings.HasSuffix(path, ".go") || strings.HasSuffix(path, "_test.go") { return nil }
                    parsed, err := parser.ParseFile(token.NewFileSet(), path, nil, 0)
                    if err != nil { return err }
                    sensitive := map[string]map[string]bool{}
                    for _, imported := range parsed.Imports {
                        importPath, err := strconv.Unquote(imported.Path.Value)
                        if err != nil { return err }
                        alias := filepath.Base(importPath)
                        if imported.Name != nil { alias = imported.Name.Name }
                        if importPath == "C" || importPath == "os/exec" {
                            findings = append(findings, fmt.Sprintf("%s imports %s", path, importPath))
                        }
                        if importPath == "syscall" {
                            if alias == "." { findings = append(findings, path+" dot-imports syscall") }
                            sensitive[alias] = map[string]bool{
                                "Socket": true, "Connect": true, "Exec": true,
                                "ForkExec": true, "StartProcess": true,
                                "LoadDLL": true, "MustLoadDLL": true,
                                "LoadLibrary": true, "GetProcAddress": true,
                                "NewLazyDLL": true,
                                "Syscall": true, "Syscall6": true,
                                "RawSyscall": true, "RawSyscall6": true,
                            }
                        }
                        if importPath == "os" {
                            sensitive[alias] = map[string]bool{"StartProcess": true}
                        }
                    }
                    ast.Inspect(parsed, func(node ast.Node) bool {
                        if call, ok := node.(*ast.CallExpr); ok {
                            selector, ok := call.Fun.(*ast.SelectorExpr)
                            if !ok { return true }
                            qualifier, ok := selector.X.(*ast.Ident)
                            if selector.Sel.Name == "NewProc" {
                                if len(call.Args) == 1 {
                                    if literal, ok := call.Args[0].(*ast.BasicLit); ok {
                                        name, err := strconv.Unquote(literal.Value)
                                        if err == nil && (name == "LockFileEx" || name == "UnlockFileEx") { return false }
                                    }
                                }
                                findings = append(findings, fmt.Sprintf("%s resolves a non-locking Windows procedure", path))
                                return false
                            }
                            if !ok || !sensitive[qualifier.Name][selector.Sel.Name] { return true }
                            if selector.Sel.Name == "NewLazyDLL" && len(call.Args) == 1 {
                                if literal, ok := call.Args[0].(*ast.BasicLit); ok {
                                    name, err := strconv.Unquote(literal.Value)
                                    if err == nil && strings.EqualFold(name, "kernel32.dll") { return false }
                                }
                            }
                            generic := strings.Contains(selector.Sel.Name, "Syscall")
                            if generic && len(call.Args) > 0 {
                                operation, ok := call.Args[0].(*ast.SelectorExpr)
                                operationQualifier, qualifierOK := operation.X.(*ast.Ident)
                                if ok && qualifierOK && operationQualifier.Name == qualifier.Name && operation.Sel.Name == "SYS_LINKAT" {
                                    return false
                                }
                            }
                            findings = append(findings, fmt.Sprintf("%s calls %s.%s", path, qualifier.Name, selector.Sel.Name))
                            return false
                        }
                        selector, ok := node.(*ast.SelectorExpr)
                        if !ok { return true }
                        qualifier, ok := selector.X.(*ast.Ident)
                        if selector.Sel.Name == "NewProc" {
                            findings = append(findings, fmt.Sprintf("%s references NewProc outside a validated literal call", path))
                            return true
                        }
                        if ok && sensitive[qualifier.Name][selector.Sel.Name] {
                            findings = append(findings, fmt.Sprintf("%s references %s.%s", path, qualifier.Name, selector.Sel.Name))
                        }
                        return true
                    })
                    return nil
                })
                if err != nil { panic(err) }
                sort.Strings(findings)
                if err := json.NewEncoder(os.Stdout).Encode(findings); err != nil { panic(err) }
            }
        '''), encoding="utf-8")
        guard_environment = dict(os.environ, GOTOOLCHAIN="local", GOPROXY="off", GOSUMDB="off")
        def run_guard(root):
            guarded = subprocess.run(
                ["go", "run", str(analyzer), str(root)],
                cwd=REPO / "core/artifacts", env=guard_environment,
                check=False, capture_output=True, text=True)
            self.assertEqual(0, guarded.returncode, guarded.stderr)
            return json.loads(guarded.stdout)

        self.assertEqual([], run_guard(REPO / "core/artifacts"),
                         "network/process escape entered production Go source")
        negative = self.base / "network-negative-control"
        negative.mkdir()
        (negative / "escape.go").write_text(textwrap.dedent('''\
            package escape
            import sx "syscall"
            import runner "os/exec"
            func escape() {
                sx.Syscall(sx.SYS_SOCKET, 0, 0, 0)
                sx.ForkExec("downloader", nil, nil)
                dll := sx.NewLazyDLL("wininet.dll")
                dll.NewProc("URLDownloadToFileW")
                resolve := dll.NewProc
                resolve("WinExec")
                _ = runner.Command("downloader")
            }
        '''), encoding="utf-8")
        negative_findings = run_guard(negative)
        self.assertTrue(any("imports os/exec" in item for item in negative_findings))
        self.assertTrue(any("calls sx.Syscall" in item for item in negative_findings))
        self.assertTrue(any("calls sx.ForkExec" in item for item in negative_findings))
        self.assertTrue(any("calls sx.NewLazyDLL" in item for item in negative_findings))
        self.assertTrue(any("non-locking Windows procedure" in item for item in negative_findings))
        self.assertTrue(any("NewProc outside a validated literal call" in item for item in negative_findings))

    def test_release_packaging_rejects_missing_duplicate_and_mismatched_candidates(self):
        manifest = json.loads((INSTALLATION / "release.json").read_text(encoding="utf-8"))
        native_platform = next(iter(manifest["binaries"]))
        with self.assertRaisesRegex(ValueError, "missing required native-tested platform"):
            self.stage(output=self.base / "missing",
                       required_platforms=[native_platform, "linux/arm64"])
        with self.assertRaisesRegex(ValueError, "duplicate native platform"):
            PACKAGER.stage_artifact_host_payloads(
                candidates=[INSTALLATION, INSTALLATION],
                qualification_receipts=[self.qualification(), self.qualification(
                    destination=self.base / "qualification-duplicate.json")],
                trusted_source_commit=FIXTURE_SOURCE_COMMIT,
                trusted_workflow=FIXTURE_WORKFLOW,
                trusted_workflow_run=FIXTURE_WORKFLOW_RUN,
                output=self.base / "duplicate", required_platforms=[native_platform], repo=REPO)

        mismatched = self.base / "mismatched"
        shutil.copytree(INSTALLATION, mismatched)
        release_path = mismatched / "release.json"
        release = json.loads(release_path.read_text(encoding="utf-8"))
        release["protocol"] = "codearbiter.artifact-api/999.0.0"
        release_path.write_text(json.dumps(release), encoding="utf-8")
        with self.assertRaisesRegex(ValueError, "protocol/schema/version identity"):
            PACKAGER.stage_artifact_host_payloads(
                candidates=[INSTALLATION, mismatched],
                qualification_receipts=[self.qualification(), self.qualification(
                    mismatched, destination=self.base / "qualification-mismatch.json")],
                trusted_source_commit=FIXTURE_SOURCE_COMMIT,
                trusted_workflow=FIXTURE_WORKFLOW,
                trusted_workflow_run=FIXTURE_WORKFLOW_RUN,
                output=self.base / "mismatch", required_platforms=[native_platform], repo=REPO)

    def test_release_packaging_is_create_only_and_rejects_linked_output(self):
        manifest = json.loads((INSTALLATION / "release.json").read_text(encoding="utf-8"))
        native_platform = next(iter(manifest["binaries"]))
        stage = self.base / "stage"
        self.stage(output=stage, required_platforms=[native_platform])
        with self.assertRaisesRegex(ValueError, "output already exists"):
            self.stage(output=stage, required_platforms=[native_platform])

        external = self.base / "external"
        external.mkdir()
        linked = self.base / "linked"
        try:
            linked.symlink_to(external, target_is_directory=True)
        except OSError:
            self.skipTest("directory symlinks are unavailable on this host")
        with self.assertRaisesRegex(ValueError, "output already exists"):
            self.stage(output=linked, required_platforms=[native_platform])
        self.assertEqual(list(external.iterdir()), [])

    def test_release_packaging_does_not_invoke_go_or_any_child_process(self):
        manifest = json.loads((INSTALLATION / "release.json").read_text(encoding="utf-8"))
        native_platform = next(iter(manifest["binaries"]))
        with mock.patch.object(PACKAGER.subprocess, "run", side_effect=AssertionError("child process")), \
                mock.patch.object(PACKAGER.subprocess, "check_output", side_effect=AssertionError("child process")), \
                mock.patch.object(PACKAGER.subprocess, "Popen", side_effect=AssertionError("child process")):
            result = self.stage(output=self.base / "offline-stage",
                                required_platforms=[native_platform])
        self.assertFalse(result["host_default_enabled"])

    def test_linked_ancestor_with_missing_descendant_cannot_mutate_external_tree(self):
        external = self.base / "external"
        (external / "created-outside").mkdir(parents=True)
        linked = self.base / "linked-parent"
        try:
            linked.symlink_to(external, target_is_directory=True)
        except OSError:
            self.skipTest("directory symlinks are unavailable on this host")
        with self.assertRaisesRegex(ValueError, "already-existing real directory"):
            self.stage(output=linked / "created-outside" / "stage")
        self.assertEqual(list((external / "created-outside").iterdir()), [])

    @unittest.skipIf(os.name == "nt", "Unix descriptor identity check")
    def test_unix_parent_swap_after_validation_cannot_redirect_creation(self):
        stable = self.base / "stable"
        parent = stable / "parent"
        parent.mkdir(parents=True)
        moved = self.base / "moved"
        external = self.base / "external"
        (external / "parent").mkdir(parents=True)
        real_open = PACKAGER._open_unix_parent

        def swap_then_open(path, flags):
            stable.rename(moved)
            stable.symlink_to(external, target_is_directory=True)
            return real_open(path, flags)

        with mock.patch.object(PACKAGER, "_open_unix_parent", side_effect=swap_then_open):
            with self.assertRaisesRegex(ValueError, "changed during validation"):
                self.stage(output=parent / "stage")
        self.assertFalse((external / "parent" / "stage").exists())

    def test_staging_root_replacement_is_blocked_or_detected(self):
        stage = self.base / "stage"
        moved = self.base / "moved"
        if os.name == "nt":
            try:
                with PACKAGER._pinned_artifact_stage(stage) as root:
                    stage.rename(moved)
                    stage.mkdir()
                    root.verify()
            except OSError:
                self.assertTrue(stage.is_dir())
                self.assertFalse(moved.exists())
                return
            except ValueError as error:
                self.assertRegex(str(error), "staging root was replaced")
                self.assertTrue(moved.is_dir())
                return
            self.fail("Windows staging-root replacement was neither blocked nor detected")
            return
        with self.assertRaisesRegex(ValueError, "staging root was replaced"):
            with PACKAGER._pinned_artifact_stage(stage) as root:
                stage.rename(moved)
                stage.mkdir()
                root.verify()

    def test_candidate_assertion_without_trusted_qualification_is_rejected(self):
        manifest = json.loads((INSTALLATION / "release.json").read_text(encoding="utf-8"))
        native_platform = next(iter(manifest["binaries"]))
        with self.assertRaisesRegex(ValueError, "qualification receipt"):
            PACKAGER.stage_artifact_host_payloads(
                candidates=[INSTALLATION], qualification_receipts=[],
                trusted_source_commit=FIXTURE_SOURCE_COMMIT,
                trusted_workflow=FIXTURE_WORKFLOW,
                trusted_workflow_run=FIXTURE_WORKFLOW_RUN,
                output=self.base / "unqualified", required_platforms=[native_platform], repo=REPO)

    def test_magic_only_fake_is_rejected_even_with_matching_receipt(self):
        real = json.loads((INSTALLATION / "release.json").read_text(encoding="utf-8"))
        native_platform, real_entry = next(iter(real["binaries"].items()))
        fake = self.base / "fake"
        fake.mkdir()
        data = {"linux": b"\x7fELF", "darwin": b"\xcf\xfa\xed\xfe", "windows": b"MZ"}[
            native_platform.split("/", 1)[0]] + b"candidate-controlled"
        digest = hashlib.sha256(data).hexdigest()
        entry = dict(real_entry, sha256=digest)
        (fake / entry["file"]).write_bytes(data)
        release = dict(real, binaries={native_platform: entry})
        (fake / "release.json").write_text(json.dumps(release), encoding="utf-8")
        receipt = self.qualification(fake, destination=self.base / "fake-qualification.json")
        with self.assertRaisesRegex(ValueError, "declared native architecture"):
            PACKAGER.stage_artifact_host_payloads(
                candidates=[fake], qualification_receipts=[receipt],
                trusted_source_commit=FIXTURE_SOURCE_COMMIT,
                trusted_workflow=FIXTURE_WORKFLOW,
                trusted_workflow_run=FIXTURE_WORKFLOW_RUN,
                output=self.base / "fake-stage", required_platforms=[native_platform], repo=REPO)

    def test_qualification_receipt_requires_protected_exact_host_ci(self):
        destination = self.base / "qualification.json"
        with mock.patch.dict(os.environ, {}, clear=True):
            with self.assertRaisesRegex(SystemExit, "protected exact-host CI"):
                BUILDER.write_qualification(INSTALLATION, destination)
        self.assertFalse(destination.exists())

        manifest = json.loads((INSTALLATION / "release.json").read_text(encoding="utf-8"))
        native_platform = next(iter(manifest["binaries"]))
        goos, goarch = native_platform.split("/", 1)
        environment = {
            "GITHUB_ACTIONS": "true",
            "GITHUB_SHA": FIXTURE_SOURCE_COMMIT,
            "GITHUB_RUN_ID": FIXTURE_WORKFLOW_RUN,
            "GITHUB_WORKFLOW_REF": f"arbiterForge/codeArbiter/{FIXTURE_WORKFLOW}@refs/heads/main",
            "GITHUB_JOB": "artifact-engine",
        }
        def checked_output(args, **_kwargs):
            if args[:3] == ["git", "rev-parse", "HEAD"]:
                return FIXTURE_SOURCE_COMMIT + "\n"
            if args == ["go", "env", "GOOS"]:
                return goos + "\n"
            if args == ["go", "env", "GOARCH"]:
                return goarch + "\n"
            raise AssertionError(args)
        with mock.patch.dict(os.environ, environment, clear=True), \
                mock.patch.object(BUILDER.subprocess, "check_output", side_effect=checked_output):
            BUILDER.write_qualification(INSTALLATION, destination)
        receipt = json.loads(destination.read_text(encoding="utf-8"))
        self.assertEqual(receipt["source_commit"], FIXTURE_SOURCE_COMMIT)
        self.assertEqual(receipt["binary_sha256"], next(iter(manifest["binaries"].values()))["sha256"])

    def test_empty_or_malformed_artifact_version_is_rejected(self):
        for index, version in enumerate(("", "version-one", "0.2.0")):
            candidate = self.base / f"bad-version-{index}"
            shutil.copytree(INSTALLATION, candidate)
            release_path = candidate / "release.json"
            release = json.loads(release_path.read_text(encoding="utf-8"))
            release["version"] = version
            release_path.write_text(json.dumps(release), encoding="utf-8")
            receipt = self.qualification(candidate, destination=self.base / f"bad-version-{index}.json")
            with self.assertRaisesRegex(ValueError, "supported artifact version"):
                PACKAGER.stage_artifact_host_payloads(
                    candidates=[candidate], qualification_receipts=[receipt],
                    trusted_source_commit=FIXTURE_SOURCE_COMMIT,
                    trusted_workflow=FIXTURE_WORKFLOW,
                    trusted_workflow_run=FIXTURE_WORKFLOW_RUN,
                    output=self.base / f"bad-version-stage-{index}",
                    required_platforms=[next(iter(release["binaries"]))], repo=REPO)

    def test_each_qualification_field_is_bound_to_trusted_context(self):
        manifest = json.loads((INSTALLATION / "release.json").read_text(encoding="utf-8"))
        native_platform = next(iter(manifest["binaries"]))
        base_receipt_path = self.qualification(destination=self.base / "receipt-base.json")
        base_receipt = json.loads(base_receipt_path.read_text(encoding="utf-8"))
        mutations = {
            "format": "codearbiter.artifact-qualification/999.0.0",
            "source_commit": "b" * 40,
            "workflow": ".github/workflows/other.yml",
            "run_id": "987654321",
            "job": "other-job",
            "platform": "linux/arm64" if native_platform != "linux/arm64" else "linux/amd64",
            "binary_sha256": "0" * 64,
            "version": "0.2.0",
            "protocol": "codearbiter.artifact-api/999.0.0",
            "schema_version": "999.0.0",
            "native_tests": ["go-test"],
        }
        for index, (field, value) in enumerate(mutations.items()):
            receipt = dict(base_receipt)
            receipt[field] = value
            path = self.base / f"receipt-{index}.json"
            path.write_text(json.dumps(receipt), encoding="utf-8")
            with self.subTest(field=field), self.assertRaisesRegex(
                    ValueError, "qualification receipt"):
                PACKAGER.stage_artifact_host_payloads(
                    candidates=[INSTALLATION], qualification_receipts=[path],
                    trusted_source_commit=FIXTURE_SOURCE_COMMIT,
                    trusted_workflow=FIXTURE_WORKFLOW,
                    trusted_workflow_run=FIXTURE_WORKFLOW_RUN,
                    output=self.base / f"tampered-{index}",
                    required_platforms=[native_platform], repo=REPO)


if __name__ == "__main__":
    unittest.main(verbosity=2)
