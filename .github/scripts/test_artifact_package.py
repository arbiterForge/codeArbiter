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
import tarfile
import tempfile
import textwrap
import unittest
from unittest import mock

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO / "core/pysrc"))
from _artifactlib import ArtifactClient
import _artifactlib
from test_artifact_authoring import physical_test_directory

INSTALLATION = None
INSTALLER = None
PACKAGER = None
BUILDER = None
INSTALLED_HOST = None
FIXTURE_SOURCE_COMMIT = "a" * 40
FIXTURE_WORKFLOW_RUN = "123456789"
FIXTURE_WORKFLOW = ".github/workflows/ci.yml"


def setUpModule():
    global INSTALLATION, INSTALLER, PACKAGER, BUILDER, INSTALLED_HOST
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
    workflow_spec = importlib.util.spec_from_file_location(
        "test_artifact_installed_host",
        REPO / ".github/scripts/test_artifact_installed_host.py",
    )
    INSTALLED_HOST = importlib.util.module_from_spec(workflow_spec)
    workflow_spec.loader.exec_module(INSTALLED_HOST)


class PackageTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.base = physical_test_directory(self.tmp.name)
        ambient_npm = shutil.which("npm.cmd") or shutil.which("npm")
        if ambient_npm is None:
            self.fail("npm is required for package tests")
        if os.name == "nt":
            self.npm_executable = self.base / "reviewed-npm.cmd"
            self.npm_executable.write_text(
                "@echo off\r\n"
                "if \"%1\"==\"--version\" (echo 11.19.1& exit /b 0)\r\n"
                f'\"{ambient_npm}\" %*\r\n',
                encoding="utf-8",
            )
        else:
            self.npm_executable = self.base / "reviewed-npm"
            self.npm_executable.write_text(
                "#!/bin/sh\n"
                "if [ \"$1\" = \"--version\" ]; then echo 11.19.1; exit 0; fi\n"
                f"exec '{ambient_npm}' \"$@\"\n",
                encoding="utf-8",
            )
            self.npm_executable.chmod(0o755)

    def test_installed_host_plan_commands_are_preflight_qualified(self):
        from _artifactauthoritylib import validate_command_definition
        plan = INSTALLED_HOST.plan_normative("a" * 64)
        for task in plan["tasks"]:
            for definition in task["verification"]:
                with self.subTest(task=task["id"], argv=definition["argv"]):
                    self.assertEqual(
                        "python-unittest-text/0.1.0",
                        validate_command_definition(definition, cwd=self.base),
                    )

    def test_installed_bridge_offline_guard_has_negative_controls(self):
        bridge = (REPO / "core/pysrc/_artifactlib.py").read_bytes()
        INSTALLED_HOST.assert_offline_bridge(bridge)
        cases = (
            (bridge + b"\nimport socket\n", "unreviewed modules"),
            (bridge + b"\nimport os\nos.system('escape')\n", "process escape"),
            (bridge + b"\nimport os\nos.fork()\n", "process escape"),
            (
                bridge
                + b"\nimport ctypes\nctypes.WinDLL('kernel32').CreateProcessW\n",
                "unreviewed kernel32 procedure",
            ),
            (bridge + b"\neval('1 + 1')\n", "dynamic code/import escape"),
        )
        for candidate, diagnostic in cases:
            with self.subTest(diagnostic=diagnostic), self.assertRaisesRegex(
                AssertionError, diagnostic
            ):
                INSTALLED_HOST.assert_offline_bridge(candidate)

    def test_installed_host_runtime_guard_and_failure_redaction(self):
        manifest = json.loads((INSTALLATION / "release.json").read_text(encoding="utf-8"))
        entry = next(iter(manifest["binaries"].values()))
        binary = (INSTALLATION / entry["file"]).resolve(strict=True)
        INSTALLED_HOST.enforce_runtime_event(
            "subprocess.Popen", (str(binary), [str(binary)], None, {}),
            binary=binary, binary_sha256=entry["sha256"],
            permit_verifier_children=False,
        )
        with self.assertRaisesRegex(RuntimeError, "forbids network access"):
            INSTALLED_HOST.enforce_runtime_event(
                "socket.connect", (None, None), binary=binary,
                binary_sha256=entry["sha256"],
                permit_verifier_children=False,
            )
        with self.assertRaisesRegex(RuntimeError, "process escape"):
            INSTALLED_HOST.enforce_runtime_event(
                "os.fork", (), binary=binary, binary_sha256=entry["sha256"],
                permit_verifier_children=False,
            )
        with self.assertRaisesRegex(RuntimeError, "unreviewed process"):
            INSTALLED_HOST.enforce_runtime_event(
                "subprocess.Popen",
                (sys.executable, [sys.executable, "-c", "pass"], None, {}),
                binary=binary, binary_sha256=entry["sha256"],
                permit_verifier_children=False,
            )

        tainted = b"::stop-commands::candidate\nsecret-value"
        completed = subprocess.CompletedProcess([], 9, b"", tainted)
        for failure in (
            INSTALLED_HOST.subprocess_failure("phase", completed),
            PACKAGER._subprocess_failure("cold", completed),
        ):
            message = str(failure)
            self.assertNotIn("stop-commands", message)
            self.assertNotIn("secret-value", message)
            self.assertIn(f"stderr_bytes={len(tainted)}", message)
            self.assertIn(hashlib.sha256(tainted).hexdigest(), message)

    def test_installed_host_runtime_guard_accepts_only_exact_darwin_stage(self):
        manifest = json.loads((INSTALLATION / "release.json").read_text(encoding="utf-8"))
        entry = next(iter(manifest["binaries"].values()))
        binary = (INSTALLATION / entry["file"]).resolve(strict=True)
        with tempfile.TemporaryDirectory(prefix="ca-artifact-exec-") as temporary:
            staged = physical_test_directory(temporary) / "ca-artifact"
            staged.write_bytes(binary.read_bytes())
            staged.chmod(0o500)
            details = (str(staged), [str(staged), "capabilities"], None, {})
            with (
                mock.patch.object(INSTALLED_HOST.platform, "system", return_value="Darwin"),
                mock.patch.object(INSTALLED_HOST.stat, "S_IMODE", return_value=0o500),
            ):
                INSTALLED_HOST.enforce_runtime_event(
                    "subprocess.Popen", details, binary=binary,
                    binary_sha256=entry["sha256"], permit_verifier_children=False,
                )
                staged.chmod(0o600)
                staged.write_bytes(staged.read_bytes() + b"drift")
                staged.chmod(0o500)
                with self.assertRaisesRegex(RuntimeError, "unreviewed process"):
                    INSTALLED_HOST.enforce_runtime_event(
                        "subprocess.Popen", details, binary=binary,
                        binary_sha256=entry["sha256"], permit_verifier_children=False,
                    )

    def qualification(self, candidate=None, *, destination=None,
                      source_commit=FIXTURE_SOURCE_COMMIT):
        candidate = candidate or INSTALLATION
        manifest = json.loads((candidate / "release.json").read_text(encoding="utf-8"))
        platform_name, entry = next(iter(manifest["binaries"].items()))
        receipt = {
            "format": "codearbiter.artifact-qualification/0.1.0",
            "source_commit": source_commit,
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
              qualification_receipts=None, source_commit=FIXTURE_SOURCE_COMMIT):
        candidates = candidates or [INSTALLATION]
        manifest = json.loads((candidates[0] / "release.json").read_text(encoding="utf-8"))
        native_platform = next(iter(manifest["binaries"]))
        return PACKAGER.stage_artifact_host_payloads(
            candidates=candidates,
            qualification_receipts=qualification_receipts or [self.qualification(
                candidates[0], source_commit=source_commit)],
            trusted_source_commit=source_commit,
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
        self.assertTrue(caps["host_default_enabled"])

    def test_capability_upgrade_does_not_reinterpret_legacy_pair(self):
        slug = "reaudit-ra03-read-only-review-aggregation"
        repository = self.base / "legacy-production-pair"
        (repository / ".codearbiter/specs").mkdir(parents=True)
        (repository / ".codearbiter/plans").mkdir(parents=True)
        paths = {
            kind: repository / ".codearbiter" / f"{kind}s" / f"{slug}.md"
            for kind in ("spec", "plan")
        }
        for kind, path in paths.items():
            path.write_bytes(
                (REPO / ".codearbiter" / f"{kind}s" / f"{slug}.md").read_bytes()
            )
        before = {kind: path.read_bytes() for kind, path in paths.items()}
        evidence = json.loads(
            (REPO / "docs/artifacts/DEFAULT-ROLLOUT-PILOT.json").read_text(
                encoding="utf-8"
            )
        )
        upgrade_case = next(
            case for case in evidence["cases"] if case["id"] == "upgrade-inertness"
        )
        self.assertEqual(upgrade_case["test"], self._testMethodName)
        self.assertEqual(upgrade_case["result"], "local_pass_hosted_pending")

        self.assertEqual(
            _artifactlib._resolve_workflow_pair(repository, slug)["format"], "md"
        )
        capabilities = ArtifactClient(repository, INSTALLATION).call("capabilities")

        self.assertTrue(capabilities["repository_operations_available"])
        self.assertEqual(
            _artifactlib._resolve_workflow_pair(repository, slug)["format"], "md"
        )
        self.assertEqual({kind: path.read_bytes() for kind, path in paths.items()}, before)
        self.assertFalse((repository / ".codearbiter/specs" / f"{slug}.html").exists())
        self.assertFalse((repository / ".codearbiter/plans" / f"{slug}.html").exists())

    def test_unqualified_binary_is_rejected_before_install(self):
        candidate = self.base / "candidate"
        shutil.copytree(INSTALLATION, candidate)
        manifest_path = candidate / "release.json"
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        next(iter(manifest["binaries"].values()))["native_tested"] = False
        manifest_path.write_text(json.dumps(manifest), encoding="utf-8")
        with self.assertRaisesRegex(ValueError, "unqualified platform entry"):
            INSTALLER.load_payload(candidate)

    def test_invalid_candidates_are_rejected_before_package_output_is_created(self):
        manifest = json.loads((INSTALLATION / "release.json").read_text(encoding="utf-8"))
        native_platform = next(iter(manifest["binaries"]))

        def corrupt_protocol(_candidate, release):
            release["protocol"] = "invalid"

        def advertise_other_cell(_candidate, release):
            entry = release["binaries"][native_platform]
            release["binaries"] = {"freebsd/amd64": entry}

        def mismatch_binary_identity(_candidate, release):
            release["binaries"][native_platform]["file"] = "wrong-artifact-binary"

        def mark_unqualified(_candidate, release):
            next(iter(release["binaries"].values()))["native_tested"] = False

        mutations = {
            "corrupt": (
                corrupt_protocol,
                "unsupported protocol/schema/version identity",
            ),
            "unsupported-advertised-cell": (
                advertise_other_cell,
                "unqualified platform entry",
            ),
            "manifest-binary-identity": (
                mismatch_binary_identity,
                "unqualified platform entry",
            ),
            "unqualified": (
                mark_unqualified,
                "unqualified platform entry",
            ),
        }
        for index, (name, (mutate, diagnostic)) in enumerate(mutations.items()):
            candidate = self.base / f"candidate-{name}"
            shutil.copytree(INSTALLATION, candidate)
            release_path = candidate / "release.json"
            release = json.loads(release_path.read_text(encoding="utf-8"))
            mutate(candidate, release)
            release_path.write_text(json.dumps(release), encoding="utf-8")
            output = self.base / f"output-{name}"
            receipt = self.qualification(
                destination=self.base / f"candidate-receipt-{index}.json"
            )
            with self.subTest(payload=name), self.assertRaisesRegex(ValueError, diagnostic):
                PACKAGER.stage_artifact_host_payloads(
                    candidates=[candidate],
                    qualification_receipts=[receipt],
                    trusted_source_commit=FIXTURE_SOURCE_COMMIT,
                    trusted_workflow=FIXTURE_WORKFLOW,
                    trusted_workflow_run=FIXTURE_WORKFLOW_RUN,
                    output=output,
                    required_platforms=[native_platform],
                    repo=REPO,
                )
            self.assertFalse(output.exists())

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
            self.assertTrue(capabilities["host_default_enabled"])

    def test_package_notices_require_complete_canonical_bytes(self):
        canonical = {name: (b"complete fixture notice\n", 0o644, "source", name)
                     for name in ("LICENSE", "THIRD_PARTY_NOTICES.md")}
        members = {f"plugins/ca/{name}": value for name, value in canonical.items()}
        PACKAGER._require_package_notices(members, "plugins/ca", canonical)
        for name in canonical:
            with self.subTest(name=name):
                missing = dict(members)
                del missing[f"plugins/ca/{name}"]
                with self.assertRaisesRegex(ValueError, "package notice"):
                    PACKAGER._require_package_notices(missing, "plugins/ca", canonical)
                identifier_only = dict(members)
                identifier_only[f"plugins/ca/{name}"] = (b"AGPL-3.0-only", 0o644, "source", name)
                with self.assertRaisesRegex(ValueError, "package notice"):
                    PACKAGER._require_package_notices(identifier_only, "plugins/ca", canonical)

    def test_final_normal_packages_bind_exact_source_and_promoted_bytes(self):
        source_commit = subprocess.check_output(
            ["git", "rev-parse", "HEAD"], cwd=REPO, text=True, encoding="utf-8"
        ).strip()
        source_tree = subprocess.check_output(
            ["git", "rev-parse", f"{source_commit}^{{tree}}"],
            cwd=REPO, text=True, encoding="utf-8",
        ).strip()
        manifest = json.loads((INSTALLATION / "release.json").read_text(encoding="utf-8"))
        native_platform = next(iter(manifest["binaries"]))
        stage = self.base / "stage"
        staged = self.stage(
            output=stage,
            required_platforms=[native_platform],
            source_commit=source_commit,
        )
        output = self.base / "packages"

        result = PACKAGER.build_artifact_release_packages(
            stage=stage,
            source_repo=REPO,
            source_commit=source_commit,
            workflow=FIXTURE_WORKFLOW,
            run_id=FIXTURE_WORKFLOW_RUN,
            promotion_receipt_sha256=staged["promotion_receipt_sha256"],
            output=output,
            npm_executable=self.npm_executable,
            npm_package_integrity=PACKAGER.NPM_PACKER_INTEGRITY,
            production=False,
        )
        verified = PACKAGER.verify_artifact_release_packages(
            package_root=output,
            source_repo=REPO,
            source_commit=source_commit,
            workflow=FIXTURE_WORKFLOW,
            run_id=FIXTURE_WORKFLOW_RUN,
            promotion_receipt_sha256=staged["promotion_receipt_sha256"],
            stage=stage,
            require_production=False,
            npm_executable=self.npm_executable,
        )

        self.assertEqual(source_tree, result["source_tree"])
        self.assertEqual(result, verified)
        self.assertEqual(["claude", "codex", "pi"], sorted(result["packages"]))
        self.assertTrue((output / "artifact-package-cohort.json").is_file())
        expected_payload = {
            path.name: path.read_bytes()
            for path in (stage / "plugins" / "ca" / "helpers" / "artifacts").iterdir()
        }
        extracted = {}
        for host in ("claude", "codex", "pi"):
            artifact = output / result["packages"][host]["file"]
            self.assertEqual(
                result["packages"][host]["sha256"],
                hashlib.sha256(artifact.read_bytes()).hexdigest(),
            )
            destination = self.base / f"extracted-{host}"
            PACKAGER.extract_artifact_release_package(artifact, destination, host=host)
            extracted[host] = destination
            plugin_prefix = {"claude": "plugins/ca", "codex": "plugins/ca-codex",
                             "pi": "package/plugins/ca-pi"}[host]
            for notice in ("LICENSE", "THIRD_PARTY_NOTICES.md"):
                committed = subprocess.check_output(
                    ["git", "show", f"{source_commit}:{notice}"], cwd=REPO)
                self.assertEqual((destination / plugin_prefix / notice).read_bytes(), committed)
                self.assertIn(f"{plugin_prefix}/{notice}", result["packages"][host]["members"])
            relative = {
                "claude": "plugins/ca/helpers/artifacts",
                "codex": "plugins/ca-codex/helpers/artifacts",
                "pi": "package/plugins/ca-pi/helpers/artifacts",
            }[host]
            payload = destination / relative
            self.assertEqual(
                expected_payload,
                {path.name: path.read_bytes() for path in payload.iterdir()},
            )
            repository = self.base / f"repo-{host}"
            repository.mkdir()
            empty_path = self.base / f"empty-path-{host}"
            empty_path.mkdir()
            with mock.patch.dict(os.environ, {"PATH": str(empty_path)}):
                capabilities = ArtifactClient(repository, payload).call("capabilities")
            self.assertTrue(capabilities["repository_operations_available"])
            self.assertFalse(capabilities["runtime_downloads"])

        checker_spec = importlib.util.spec_from_file_location(
            "codex_static_package",
            REPO / ".github" / "scripts" / "check_codex_static_package.py",
        )
        checker = importlib.util.module_from_spec(checker_spec)
        checker_spec.loader.exec_module(checker)
        self.assertEqual(
            "PASS",
            checker.candidate_static_contract(
                extracted["codex"] / "plugins" / "ca-codex",
                verified_large_files={
                    name.removeprefix("plugins/ca-codex/"): {
                        key: member[key]
                        for key in ("type", "mode", "size", "sha256", "origin")
                    }
                    for name, member in result["packages"]["codex"]["members"].items()
                    if (
                        name.startswith(
                            "plugins/ca-codex/helpers/artifacts/ca-artifact-"
                        )
                        and member["size"] > 2 * 1024 * 1024
                    )
                },
            )["verdict"],
        )
        claude_catalog = json.loads(
            (extracted["claude"] / ".claude-plugin" / "marketplace.json").read_text(
                encoding="utf-8"
            )
        )
        codex_catalog = json.loads(
            (extracted["codex"] / ".agents" / "plugins" / "marketplace.json").read_text(
                encoding="utf-8"
            )
        )
        self.assertEqual(["ca"], [entry["name"] for entry in claude_catalog["plugins"]])
        self.assertEqual(
            ["ca-codex"], [entry["name"] for entry in codex_catalog["plugins"]]
        )

        npm_output = self.base / "codex-npm"
        npm_result = PACKAGER.build_codex_npm_package(
            package_root=output,
            package_cohort_sha256=hashlib.sha256(
                (output / "artifact-package-cohort.json").read_bytes()).hexdigest(),
            output=npm_output,
        )
        with tarfile.open(npm_output / npm_result["file"], "r:gz") as archive:
            for notice in ("LICENSE", "THIRD_PARTY_NOTICES.md"):
                member = archive.extractfile(f"package/{notice}")
                self.assertIsNotNone(member)
                self.assertEqual(member.read(), subprocess.check_output(
                    ["git", "show", f"{source_commit}:{notice}"], cwd=REPO))

        pi_artifact = output / result["packages"]["pi"]["file"]
        with tarfile.open(pi_artifact, "r:gz") as archive:
            members = {member.name: member for member in archive.getmembers()}
        for name in expected_payload:
            member = members[f"package/plugins/ca-pi/helpers/artifacts/{name}"]
            expected_mode = 0o644 if name == "release.json" else 0o755
            self.assertEqual(expected_mode, member.mode)

        cohort_path = output / "artifact-package-cohort.json"
        cohort_bytes = cohort_path.read_bytes()
        for field, value in {
            "version": "11.19.0",
            "package_integrity": "sha512-invalid",
            "executable_sha256": "0" * 64,
        }.items():
            cohort = json.loads(cohort_bytes)
            cohort["pi_packer"][field] = value
            cohort_path.write_text(json.dumps(cohort), encoding="utf-8")
            with self.subTest(packer_receipt=field), self.assertRaisesRegex(
                ValueError, "Pi packer"
            ):
                PACKAGER.verify_artifact_release_packages(
                    package_root=output, source_repo=REPO,
                    source_commit=source_commit, workflow=FIXTURE_WORKFLOW,
                    run_id=FIXTURE_WORKFLOW_RUN,
                    promotion_receipt_sha256=staged["promotion_receipt_sha256"],
                    stage=stage, require_production=False,
                    npm_executable=self.npm_executable,
                )
            cohort_path.write_bytes(cohort_bytes)

        with self.assertRaisesRegex(ValueError, "output already exists"):
            PACKAGER.build_artifact_release_packages(
                stage=stage,
                source_repo=REPO,
                source_commit=source_commit,
                workflow=FIXTURE_WORKFLOW,
                run_id=FIXTURE_WORKFLOW_RUN,
                promotion_receipt_sha256=staged["promotion_receipt_sha256"],
                output=output,
                npm_executable=self.npm_executable,
                npm_package_integrity=PACKAGER.NPM_PACKER_INTEGRITY,
                production=False,
            )

    def test_release_package_extraction_rejects_nonportable_member_names(self):
        cases = (
            "plugins/ca/C:\\escape.txt",
            "plugins/ca/CON",
            "plugins/ca/trailing.",
            "plugins/ca/alternate:data",
            "plugins/ca/x\n::stop-commands::secret-value",
        )
        for index, name in enumerate(cases):
            archive_path = self.base / f"unsafe-{index}.tar.gz"
            with tarfile.open(archive_path, "w:gz") as archive:
                data = b"unsafe"
                member = tarfile.TarInfo(name)
                member.size = len(data)
                archive.addfile(member, __import__("io").BytesIO(data))
            destination = self.base / f"unsafe-output-{index}"
            with self.subTest(name=name), self.assertRaisesRegex(
                ValueError, "unsafe member"
            ) as raised:
                PACKAGER.extract_artifact_release_package(
                    archive_path, destination, host="claude"
                )
            self.assertNotIn(name, str(raised.exception))
            self.assertNotIn("stop-commands", str(raised.exception))
            self.assertNotIn("secret-value", str(raised.exception))
            self.assertFalse(destination.exists())

        collision = self.base / "unicode-collision.tar.gz"
        with tarfile.open(collision, "w:gz") as archive:
            for name in ("plugins/ca/\u00e9.txt", "plugins/ca/e\u0301.txt"):
                member = tarfile.TarInfo(name)
                member.size = 1
                archive.addfile(member, __import__("io").BytesIO(b"x"))
        with self.assertRaisesRegex(ValueError, "unsafe member"):
            PACKAGER.extract_artifact_release_package(
                collision, self.base / "collision-output", host="claude"
            )

    def test_final_package_build_refuses_wrong_source_or_promotion_before_output(self):
        source_commit = subprocess.check_output(
            ["git", "rev-parse", "HEAD"], cwd=REPO, text=True, encoding="utf-8"
        ).strip()
        manifest = json.loads((INSTALLATION / "release.json").read_text(encoding="utf-8"))
        native_platform = next(iter(manifest["binaries"]))
        stage = self.base / "stage"
        staged = self.stage(
            output=stage,
            required_platforms=[native_platform],
            source_commit=source_commit,
        )
        cases = {
            "source": dict(source_commit="b" * 40,
                           receipt=staged["promotion_receipt_sha256"]),
            "promotion": dict(source_commit=source_commit, receipt="0" * 64),
        }
        for index, (name, case) in enumerate(cases.items()):
            output = self.base / f"rejected-{index}"
            with self.subTest(drift=name), self.assertRaises((ValueError, RuntimeError)):
                PACKAGER.build_artifact_release_packages(
                    stage=stage,
                    source_repo=REPO,
                    source_commit=case["source_commit"],
                    workflow=FIXTURE_WORKFLOW,
                    run_id=FIXTURE_WORKFLOW_RUN,
                    promotion_receipt_sha256=case["receipt"],
                    output=output,
                    npm_executable=self.npm_executable,
                    npm_package_integrity=PACKAGER.NPM_PACKER_INTEGRITY,
                    production=False,
                )
            self.assertFalse(output.exists())

    def test_npm_packer_receives_only_isolated_environment_and_redacts_failures(self):
        source_commit = subprocess.check_output(
            ["git", "rev-parse", "HEAD"], cwd=REPO, text=True, encoding="utf-8"
        ).strip()
        manifest = json.loads((INSTALLATION / "release.json").read_text(encoding="utf-8"))
        native_platform = next(iter(manifest["binaries"]))
        stage = self.base / "npm-env-stage"
        staged = self.stage(
            output=stage, required_platforms=[native_platform],
            source_commit=source_commit,
        )
        secret = "npm-child-secret-sentinel"
        secret_names = {
            "NPMJS_TOKEN", "NODE_AUTH_TOKEN", "GH_TOKEN", "GITHUB_TOKEN",
            "FARM_API_KEY", "UNDECLARED_BUILD_SECRET",
        }
        captured = []
        real_run = PACKAGER.subprocess.run

        def record(argv, **kwargs):
            if Path(argv[0]) == self.npm_executable:
                captured.append(kwargs.get("env"))
            return real_run(argv, **kwargs)

        injected = {name: f"{secret}-{name}" for name in secret_names}
        output = self.base / "npm-env-packages"
        with mock.patch.dict(os.environ, injected), mock.patch.object(
            PACKAGER.subprocess, "run", side_effect=record
        ):
            PACKAGER.build_artifact_release_packages(
                stage=stage, source_repo=REPO, source_commit=source_commit,
                workflow=FIXTURE_WORKFLOW, run_id=FIXTURE_WORKFLOW_RUN,
                promotion_receipt_sha256=staged["promotion_receipt_sha256"],
                output=output, npm_executable=self.npm_executable,
                npm_package_integrity=PACKAGER.NPM_PACKER_INTEGRITY,
                production=False,
            )
        self.assertGreaterEqual(len(captured), 3)
        allowed_environment = {
            "PATH", "SystemRoot", "WINDIR", "ComSpec", "PATHEXT",
            "HOME", "USERPROFILE", "APPDATA", "LOCALAPPDATA", "TMP", "TEMP",
            "LANG", "LC_ALL", "NO_COLOR", "FORCE_COLOR",
            "npm_config_userconfig", "npm_config_globalconfig", "npm_config_cache",
            "npm_config_logs_dir", "npm_config_logs_max", "npm_config_offline",
            "npm_config_audit", "npm_config_fund", "npm_config_ignore_scripts",
            "npm_config_update_notifier",
        }
        for child_environment in captured:
            self.assertIsInstance(child_environment, dict)
            self.assertTrue(set(child_environment) <= allowed_environment)
            self.assertTrue(secret_names.isdisjoint(child_environment))
            self.assertNotIn(secret, "\n".join(child_environment.values()))
            self.assertNotEqual(os.environ.get("HOME"), child_environment["HOME"])
            for key in (
                "npm_config_userconfig", "npm_config_globalconfig",
                "npm_config_cache", "npm_config_logs_dir",
            ):
                self.assertIn("ca-artifact-", child_environment[key])

        def fail_pack(argv, **kwargs):
            if Path(argv[0]) == self.npm_executable and "pack" in argv:
                return subprocess.CompletedProcess(
                    argv, 19, stdout="", stderr=f"failure relayed {secret}"
                )
            return real_run(argv, **kwargs)

        failed_output = self.base / "npm-error-packages"
        with mock.patch.dict(os.environ, injected), mock.patch.object(
            PACKAGER.subprocess, "run", side_effect=fail_pack
        ):
            with self.assertRaises(ValueError) as failure:
                PACKAGER.build_artifact_release_packages(
                    stage=stage, source_repo=REPO, source_commit=source_commit,
                    workflow=FIXTURE_WORKFLOW, run_id=FIXTURE_WORKFLOW_RUN,
                    promotion_receipt_sha256=staged["promotion_receipt_sha256"],
                    output=failed_output, npm_executable=self.npm_executable,
                    npm_package_integrity=PACKAGER.NPM_PACKER_INTEGRITY,
                    production=False,
                )
        self.assertNotIn(secret, str(failure.exception))
        self.assertFalse(failed_output.exists())

        def fail_identity(argv, **kwargs):
            return subprocess.CompletedProcess(
                argv, 23, stdout="", stderr=f"identity relayed {secret}"
            )

        with mock.patch.object(PACKAGER.subprocess, "run", side_effect=fail_identity):
            with self.assertRaises(ValueError) as identity_failure:
                PACKAGER._verified_npm_packer(
                    self.npm_executable,
                    package_integrity=PACKAGER.NPM_PACKER_INTEGRITY,
                    production=False,
                )
        self.assertNotIn(secret, str(identity_failure.exception))

        ambient_npm = Path(shutil.which("npm.cmd") or shutil.which("npm"))
        for name, executable, integrity in (
            ("ambient-version", ambient_npm, PACKAGER.NPM_PACKER_INTEGRITY),
            ("wrong-integrity", self.npm_executable, "sha512-invalid"),
        ):
            output = self.base / f"rejected-packer-{name}"
            with self.subTest(packer=name), self.assertRaisesRegex(
                ValueError, "npm packer"
            ):
                PACKAGER.build_artifact_release_packages(
                    stage=stage, source_repo=REPO, source_commit=source_commit,
                    workflow=FIXTURE_WORKFLOW, run_id=FIXTURE_WORKFLOW_RUN,
                    promotion_receipt_sha256=staged["promotion_receipt_sha256"],
                    output=output, npm_executable=executable,
                    npm_package_integrity=integrity, production=False,
                )
            self.assertFalse(output.exists())

    def test_promotion_receipt_binds_exact_payload_and_native_qualification_bytes(self):
        manifest = json.loads((INSTALLATION / "release.json").read_text(encoding="utf-8"))
        native_platform = next(iter(manifest["binaries"]))
        qualification = self.qualification(destination=self.base / "native-qualification.json")
        stage = self.base / "stage"
        result = self.stage(
            output=stage,
            required_platforms=[native_platform],
            qualification_receipts=[qualification],
        )

        receipt_path = stage / "artifact-promotion.json"
        receipt = json.loads(receipt_path.read_text(encoding="utf-8"))
        self.assertEqual("codearbiter.artifact-promotion/0.1.0", receipt["format"])
        self.assertEqual(FIXTURE_SOURCE_COMMIT, receipt["source_commit"])
        self.assertEqual(FIXTURE_WORKFLOW, receipt["workflow"])
        self.assertEqual(FIXTURE_WORKFLOW_RUN, receipt["run_id"])
        self.assertEqual(
            hashlib.sha256(qualification.read_bytes()).hexdigest(),
            receipt["qualifications"][native_platform]["receipt_sha256"],
        )
        self.assertEqual(str(receipt_path), result["promotion_receipt"])
        self.assertEqual(
            hashlib.sha256(receipt_path.read_bytes()).hexdigest(),
            result["promotion_receipt_sha256"],
        )
        for host, plugin_dir in {
            "claude": "plugins/ca",
            "codex": "plugins/ca-codex",
            "pi": "plugins/ca-pi",
        }.items():
            payload = stage / plugin_dir / "helpers" / "artifacts"
            verified = INSTALLER.load_promotion_receipt(
                payload,
                receipt_path,
                host=host,
                source_commit=FIXTURE_SOURCE_COMMIT,
                workflow=FIXTURE_WORKFLOW,
                run_id=FIXTURE_WORKFLOW_RUN,
                receipt_sha256=result["promotion_receipt_sha256"],
            )
            self.assertEqual(receipt, verified.receipt)

    def test_verified_promotion_snapshot_cannot_be_swapped_before_install(self):
        manifest = json.loads((INSTALLATION / "release.json").read_text(encoding="utf-8"))
        native_platform, entry = next(iter(manifest["binaries"].items()))
        stage = self.base / "stage"
        result = self.stage(output=stage, required_platforms=[native_platform])
        receipt_path = stage / "artifact-promotion.json"
        payload = stage / "plugins" / "ca" / "helpers" / "artifacts"
        verified = INSTALLER.load_promotion_receipt(
            payload, receipt_path, host="claude",
            source_commit=FIXTURE_SOURCE_COMMIT,
            workflow=FIXTURE_WORKFLOW, run_id=FIXTURE_WORKFLOW_RUN,
            receipt_sha256=result["promotion_receipt_sha256"])
        original_manifest = (payload / "release.json").read_bytes()
        original_binary = (payload / entry["file"]).read_bytes()

        real_verifier = INSTALLER.load_promotion_receipt
        def verify_then_replace(*args, **kwargs):
            snapshot = real_verifier(*args, **kwargs)
            (payload / "release.json").write_bytes(original_manifest + b" ")
            (payload / entry["file"]).write_bytes(original_binary + b"replaced")
            return snapshot

        consumer = self.base / "consumer"
        consumer.mkdir()
        with mock.patch.object(INSTALLER, "load_promotion_receipt",
                               side_effect=verify_then_replace):
            if os.name == "nt":
                with self.assertRaisesRegex(ValueError, "release-packaging only"):
                    INSTALLER.install_promoted_payload(
                        consumer, "plugin", payload, receipt_path,
                        host="claude", source_commit=FIXTURE_SOURCE_COMMIT,
                        workflow=FIXTURE_WORKFLOW, run_id=FIXTURE_WORKFLOW_RUN,
                        receipt_sha256=result["promotion_receipt_sha256"])
            else:
                installed = INSTALLER.install_promoted_payload(
                    consumer, "plugin", payload, receipt_path,
                    host="claude", source_commit=FIXTURE_SOURCE_COMMIT,
                    workflow=FIXTURE_WORKFLOW, run_id=FIXTURE_WORKFLOW_RUN,
                    receipt_sha256=result["promotion_receipt_sha256"])
                self.assertEqual(original_manifest, (installed / "release.json").read_bytes())
                self.assertEqual(original_binary, (installed / entry["file"]).read_bytes())
        self.assertEqual(original_manifest, verified.manifest_bytes)
        self.assertEqual(original_binary, dict(verified.payload)[entry["file"]])
        with self.assertRaisesRegex(ValueError, "payload bytes drifted"):
            real_verifier(
                payload, receipt_path, host="claude",
                source_commit=FIXTURE_SOURCE_COMMIT,
                workflow=FIXTURE_WORKFLOW, run_id=FIXTURE_WORKFLOW_RUN,
                receipt_sha256=result["promotion_receipt_sha256"])

    def test_promotion_receipt_rejects_context_host_file_set_and_byte_drift(self):
        manifest = json.loads((INSTALLATION / "release.json").read_text(encoding="utf-8"))
        native_platform, entry = next(iter(manifest["binaries"].items()))
        stage = self.base / "stage"
        result = self.stage(output=stage, required_platforms=[native_platform])
        receipt_path = stage / "artifact-promotion.json"
        payload = stage / "plugins" / "ca" / "helpers" / "artifacts"

        bad_contexts = {
            "host": dict(host="codex", source_commit=FIXTURE_SOURCE_COMMIT,
                         workflow=FIXTURE_WORKFLOW, run_id=FIXTURE_WORKFLOW_RUN,
                         receipt_sha256=result["promotion_receipt_sha256"]),
            "commit": dict(host="claude", source_commit="b" * 40,
                           workflow=FIXTURE_WORKFLOW, run_id=FIXTURE_WORKFLOW_RUN,
                           receipt_sha256=result["promotion_receipt_sha256"]),
            "workflow": dict(host="claude", source_commit=FIXTURE_SOURCE_COMMIT,
                             workflow=".github/workflows/release.yml",
                             run_id=FIXTURE_WORKFLOW_RUN,
                             receipt_sha256=result["promotion_receipt_sha256"]),
            "run": dict(host="claude", source_commit=FIXTURE_SOURCE_COMMIT,
                        workflow=FIXTURE_WORKFLOW, run_id="987654321",
                        receipt_sha256=result["promotion_receipt_sha256"]),
        }
        for name, context in bad_contexts.items():
            with self.subTest(drift=name), self.assertRaisesRegex(
                    ValueError, "promotion receipt"):
                INSTALLER.load_promotion_receipt(payload, receipt_path, **context)

        binary = payload / entry["file"]
        original = binary.read_bytes()
        binary.write_bytes(original + b"drift")
        with self.assertRaisesRegex(ValueError, "payload bytes drifted"):
            INSTALLER.load_promotion_receipt(
                payload, receipt_path, host="claude",
                source_commit=FIXTURE_SOURCE_COMMIT,
                workflow=FIXTURE_WORKFLOW, run_id=FIXTURE_WORKFLOW_RUN,
                receipt_sha256=result["promotion_receipt_sha256"])
        binary.write_bytes(original)

        extra = payload / "unqualified-extra"
        extra.write_bytes(b"extra")
        with self.assertRaisesRegex(ValueError, "payload file set drifted"):
            INSTALLER.load_promotion_receipt(
                payload, receipt_path, host="claude",
                source_commit=FIXTURE_SOURCE_COMMIT,
                workflow=FIXTURE_WORKFLOW, run_id=FIXTURE_WORKFLOW_RUN,
                receipt_sha256=result["promotion_receipt_sha256"])
        extra.unlink()

        receipt = json.loads(receipt_path.read_text(encoding="utf-8"))
        receipt["qualifications"][native_platform]["receipt_sha256"] = "0" * 64
        receipt_path.write_text(json.dumps(receipt), encoding="utf-8")
        with self.assertRaisesRegex(ValueError, "promotion receipt bytes drifted"):
            INSTALLER.load_promotion_receipt(
                payload, receipt_path, host="claude",
                source_commit=FIXTURE_SOURCE_COMMIT,
                workflow=FIXTURE_WORKFLOW, run_id=FIXTURE_WORKFLOW_RUN,
                receipt_sha256=result["promotion_receipt_sha256"])

    def test_promotion_receipt_is_create_only_with_the_stage(self):
        manifest = json.loads((INSTALLATION / "release.json").read_text(encoding="utf-8"))
        native_platform = next(iter(manifest["binaries"]))
        stage = self.base / "stage"
        self.stage(output=stage, required_platforms=[native_platform])
        receipt = stage / "artifact-promotion.json"
        original = receipt.read_bytes()
        with self.assertRaisesRegex(ValueError, "output already exists"):
            self.stage(output=stage, required_platforms=[native_platform])
        self.assertEqual(original, receipt.read_bytes())

    def test_cold_execution_receipt_binds_each_host_to_the_native_promoted_bytes(self):
        source_commit = subprocess.check_output(
            ["git", "rev-parse", "HEAD"], cwd=REPO, text=True, encoding="utf-8"
        ).strip()
        manifest = json.loads((INSTALLATION / "release.json").read_text(encoding="utf-8"))
        native_platform, entry = next(iter(manifest["binaries"].items()))
        stage = self.base / "stage"
        result = self.stage(
            output=stage, required_platforms=[native_platform],
            source_commit=source_commit,
        )
        packages = self.base / "packages"
        PACKAGER.build_artifact_release_packages(
            stage=stage, source_repo=REPO, source_commit=source_commit,
            workflow=FIXTURE_WORKFLOW, run_id=FIXTURE_WORKFLOW_RUN,
            promotion_receipt_sha256=result["promotion_receipt_sha256"],
            output=packages,
            npm_executable=self.npm_executable,
            npm_package_integrity=PACKAGER.NPM_PACKER_INTEGRITY,
            production=False,
        )
        observed = []
        observed_workflows = []
        observed_workflow_paths = []
        real_run = PACKAGER.subprocess.run

        def record_run(argv, **kwargs):
            if "capabilities" in argv:
                observed.append((argv, kwargs))
            is_workflow = any(
                str(value).endswith("test_artifact_installed_host.py") for value in argv
            )
            if is_workflow:
                observed_workflows.append((argv, kwargs))
                empty_path = Path(kwargs["env"]["PATH"])
                observed_workflow_paths.append(
                    (empty_path.is_dir(), list(empty_path.iterdir()))
                )
            return real_run(argv, **kwargs)

        with mock.patch.object(PACKAGER.subprocess, "run", side_effect=record_run):
            for host in ("claude", "codex", "pi"):
                destination = self.base / f"cold-{host}.json"
                cold = PACKAGER.cold_execute_artifact_host_payload(
                    stage=stage,
                    package_root=packages,
                    source_repo=REPO,
                    host=host,
                    expected_platform=native_platform,
                    source_commit=source_commit,
                    workflow=FIXTURE_WORKFLOW,
                    run_id=FIXTURE_WORKFLOW_RUN,
                    promotion_receipt_sha256=result["promotion_receipt_sha256"],
                    output=destination,
                    require_production=False,
                )
                self.assertEqual(host, cold["host"])
                self.assertEqual(native_platform, cold["platform"])
                self.assertEqual(entry["sha256"], cold["binary_sha256"])
                self.assertEqual(result["promotion_receipt_sha256"],
                                 cold["promotion_receipt_sha256"])
                self.assertTrue(cold["all_accepted_and_current"])
                self.assertTrue(cold["interruption_reconciled"])
                self.assertTrue(cold["redispatched"])
                self.assertTrue(cold["commit_proof"])
                self.assertTrue(cold["finalization_proof"])
                self.assertEqual(0, cold["markdown_shadow_count"])
                self.assertEqual(cold, json.loads(destination.read_text(encoding="utf-8")))

        self.assertEqual(3, len(observed))
        for argv, kwargs in observed:
            self.assertTrue(Path(argv[0]).is_absolute())
            self.assertEqual({}, kwargs["env"])
            self.assertNotIn("shell", kwargs)
        self.assertEqual(3, len(observed_workflows))
        for (argv, kwargs), (path_existed, path_contents) in zip(
            observed_workflows, observed_workflow_paths, strict=True
        ):
            self.assertTrue(Path(argv[0]).is_absolute())
            self.assertIn("--plugin-root", argv)
            self.assertIn("--expected-binary-sha256", argv)
            self.assertTrue(Path(kwargs["cwd"]).is_absolute())
            self.assertTrue(path_existed)
            self.assertEqual([], path_contents)
            self.assertFalse(Path(kwargs["env"]["PATH"]).exists())
            self.assertEqual("1", kwargs["env"]["PYTHONNOUSERSITE"])
            self.assertNotIn("PYTHONPATH", kwargs["env"])
            self.assertNotIn("shell", kwargs)

    def test_cold_execution_refuses_wrong_cell_context_and_is_create_only(self):
        source_commit = subprocess.check_output(
            ["git", "rev-parse", "HEAD"], cwd=REPO, text=True, encoding="utf-8"
        ).strip()
        manifest = json.loads((INSTALLATION / "release.json").read_text(encoding="utf-8"))
        native_platform = next(iter(manifest["binaries"]))
        stage = self.base / "stage"
        result = self.stage(
            output=stage, required_platforms=[native_platform],
            source_commit=source_commit,
        )
        packages = self.base / "packages"
        PACKAGER.build_artifact_release_packages(
            stage=stage, source_repo=REPO, source_commit=source_commit,
            workflow=FIXTURE_WORKFLOW, run_id=FIXTURE_WORKFLOW_RUN,
            promotion_receipt_sha256=result["promotion_receipt_sha256"],
            output=packages,
            npm_executable=self.npm_executable,
            npm_package_integrity=PACKAGER.NPM_PACKER_INTEGRITY,
            production=False,
        )
        wrong_platform = "linux/arm64" if native_platform != "linux/arm64" else "linux/amd64"
        cases = {
            "host": dict(host="other", expected_platform=native_platform,
                         promotion_receipt_sha256=result["promotion_receipt_sha256"]),
            "platform": dict(host="claude", expected_platform=wrong_platform,
                             promotion_receipt_sha256=result["promotion_receipt_sha256"]),
            "promotion": dict(host="claude", expected_platform=native_platform,
                              promotion_receipt_sha256="0" * 64),
        }
        for name, context in cases.items():
            output = self.base / f"rejected-{name}.json"
            with self.subTest(context=name), self.assertRaises((ValueError, RuntimeError)):
                PACKAGER.cold_execute_artifact_host_payload(
                    stage=stage, package_root=packages, source_repo=REPO,
                    source_commit=source_commit,
                    workflow=FIXTURE_WORKFLOW, run_id=FIXTURE_WORKFLOW_RUN,
                    output=output, require_production=False, **context)
            self.assertFalse(output.exists())

        output = self.base / "cold.json"
        PACKAGER.cold_execute_artifact_host_payload(
            stage=stage, package_root=packages, source_repo=REPO,
            host="claude", expected_platform=native_platform,
            source_commit=source_commit, workflow=FIXTURE_WORKFLOW,
            run_id=FIXTURE_WORKFLOW_RUN,
            promotion_receipt_sha256=result["promotion_receipt_sha256"], output=output,
            require_production=False,
        )
        original = output.read_bytes()
        with self.assertRaisesRegex(ValueError, "cold-execution receipt output"):
            PACKAGER.cold_execute_artifact_host_payload(
                stage=stage, package_root=packages, source_repo=REPO,
                host="claude", expected_platform=native_platform,
                source_commit=source_commit, workflow=FIXTURE_WORKFLOW,
                run_id=FIXTURE_WORKFLOW_RUN,
                promotion_receipt_sha256=result["promotion_receipt_sha256"], output=output,
                require_production=False)
        self.assertEqual(original, output.read_bytes())

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
        missing_platform = next(
            platform_name for platform_name in sorted(PACKAGER.ARTIFACT_PLATFORMS)
            if platform_name != native_platform
        )
        with self.assertRaisesRegex(ValueError, "missing required native-tested platform"):
            self.stage(output=self.base / "missing",
                       required_platforms=[native_platform, missing_platform])
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

    def test_git_archive_modes_are_canonical_across_host_umasks(self):
        source = self.base / "source-modes"
        source.mkdir()
        subprocess.run(["git", "init"], cwd=source, check=True,
                       capture_output=True)
        (source / "plain.txt").write_text("plain\n", encoding="utf-8")
        (source / "tool.sh").write_text("#!/bin/sh\nexit 0\n", encoding="utf-8")
        subprocess.run(["git", "add", "plain.txt", "tool.sh"], cwd=source,
                       check=True, capture_output=True)
        subprocess.run(["git", "update-index", "--chmod=+x", "tool.sh"],
                       cwd=source, check=True, capture_output=True)
        subprocess.run([
            "git", "-c", "user.name=Artifact Test", "-c",
            "user.email=artifact@example.invalid", "commit", "-m", "fixture",
        ], cwd=source, check=True, capture_output=True)
        commit = subprocess.run(
            ["git", "rev-parse", "HEAD"], cwd=source, check=True,
            capture_output=True, text=True, encoding="utf-8",
        ).stdout.strip()

        observed = []
        for umask in ("0002", "0000"):
            subprocess.run(["git", "config", "tar.umask", umask], cwd=source,
                           check=True, capture_output=True)
            observed.append(PACKAGER._git_archive_files(
                source, commit, ("plain.txt", "tool.sh")
            ))

        self.assertEqual(observed[0], observed[1])
        self.assertEqual(observed[0]["plain.txt"][1], 0o644)
        self.assertEqual(observed[0]["tool.sh"][1], 0o755)

    def test_git_archive_bytes_are_canonical_across_host_autocrlf(self):
        source = self.base / "source-autocrlf"
        source.mkdir()
        subprocess.run(["git", "init"], cwd=source, check=True,
                       capture_output=True)
        (source / "unclassified.txt").write_bytes(b"first\nsecond\n")
        subprocess.run(["git", "add", "unclassified.txt"], cwd=source,
                       check=True, capture_output=True)
        subprocess.run([
            "git", "-c", "user.name=Artifact Test", "-c",
            "user.email=artifact@example.invalid", "commit", "-m", "fixture",
        ], cwd=source, check=True, capture_output=True)
        commit = subprocess.run(
            ["git", "rev-parse", "HEAD"], cwd=source, check=True,
            capture_output=True, text=True, encoding="utf-8",
        ).stdout.strip()

        observed = []
        for autocrlf in ("false", "true"):
            subprocess.run(["git", "config", "core.autocrlf", autocrlf],
                           cwd=source, check=True, capture_output=True)
            observed.append(PACKAGER._git_archive_files(
                source, commit, ("unclassified.txt",)
            ))

        self.assertEqual(observed[0], observed[1])
        self.assertEqual(observed[0]["unclassified.txt"][0], b"first\nsecond\n")

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
        self.assertTrue(result["host_default_enabled"])

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
        self.assertEqual(PACKAGER.ARTIFACT_PLATFORMS, BUILDER.QUALIFIED_CI_PLATFORMS)
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
            "EXPECTED_ARTIFACT_PLATFORM": native_platform,
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

        wrong = self.base / "wrong-cell.json"
        other_platform = next(
            cell for cell in sorted(BUILDER.QUALIFIED_CI_PLATFORMS)
            if cell != native_platform
        )
        with mock.patch.dict(os.environ, {
                **environment, "EXPECTED_ARTIFACT_PLATFORM": other_platform}, clear=True), \
                mock.patch.object(BUILDER.subprocess, "check_output", side_effect=checked_output):
            with self.assertRaisesRegex(SystemExit, "candidate platform does not match"):
                BUILDER.write_qualification(INSTALLATION, wrong)
        self.assertFalse(wrong.exists())

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
