#!/usr/bin/env python3
"""Fresh farm projection, seal, staleness and dispatcher-boundary fixtures.

All workflow receipts are synthetic isolated-test evidence. They exercise the
cooperative authority contract and do not qualify a model or promote --farm.
"""

from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import time
import unittest
from unittest import mock

from _boundedproc import run as run_bounded
from retained_archive_cli_observation import physical_members
from test_artifact_authoring import (
    ArtifactError,
    FixtureDirectory,
    WorkflowHarness,
    build_installation,
    canonical_hash,
    physical_test_directory,
)

REPO = Path(__file__).resolve().parents[2]


def canonical_bytes(value: object) -> bytes:
    return json.dumps(
        value,
        ensure_ascii=False,
        allow_nan=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")


def _project_fixture(harness: WorkflowHarness, projection: dict) -> dict:
    plan = harness.client.call("identity", {"artifact_id": "PLAN-FLOW"})
    spec = harness.client.call("identity", {"artifact_id": "SPEC-FLOW"})
    snapshot = harness.client.call("snapshot", {"artifact_id": "PLAN-FLOW"})
    task = harness.client.call(
        "read", {"artifact_id": "PLAN-FLOW", "symbol": "T-001", "mode": "exact"}
    )["record"]
    definition = task["verification"][0]
    base_sha256 = hashlib.sha256(canonical_bytes(projection)).hexdigest()
    authorization = harness.capture(
        "PLAN-FLOW",
        "CP-01",
        "farm_authorization",
        "user_workflow",
        "approved",
        {
            "format": "codearbiter.farm-authorization/0.1.0",
            "input_sha256": snapshot["sha256"],
            "spec_sha256": spec["normative_sha256"],
            "plan_sha256": plan["normative_sha256"],
            "scope": "CP-01",
            "base_sha256": base_sha256,
            "red_evidence": [
                {
                    "source_task": "T-001",
                    "farm_task": "t-001",
                    "test_path": "src/config.py",
                    "definition_sha256": canonical_hash(definition),
                    "command": "python -m unittest -v tests.test_config",
                    "exit": 1,
                    "stdout_sha256": hashlib.sha256(b"synthetic RED").hexdigest(),
                    "stderr_sha256": hashlib.sha256(b"").hexdigest(),
                }
            ],
        },
    )
    return harness.mutate(
        "farm-project",
        "PLAN-FLOW",
        scope="CP-01",
        slice=["T-001"],
        target=".codearbiter/plans/flow.plan.json",
        projection=projection,
        receipt=authorization,
    )


def cleanup_installation(owner: tempfile.TemporaryDirectory) -> None:
    """Remove owned test scratch, allowing only bounded Windows sharing retries.

    The ARM conformance run reached teardown after all assertions passed but
    encountered WinError 32 on its copied executable. Its holder was not known.
    Never ignore that error: a persistent holder or any other failure still
    fails the suite. This changes neither process containment nor production I/O.
    """
    deadline = time.monotonic() + 2.0
    for attempt in range(41):
        try:
            owner.cleanup()
            return
        except PermissionError as error:
            remaining = deadline - time.monotonic()
            if getattr(error, "winerror", None) != 32 or remaining <= 0 or attempt == 40:
                raise
            time.sleep(min(0.05, remaining))


class InstallationCleanupTest(unittest.TestCase):
    @staticmethod
    def sharing_error() -> PermissionError:
        error = PermissionError("test-owned file is held")
        error.winerror = 32
        return error

    def test_cleanup_success_needs_no_retry(self) -> None:
        owner = mock.Mock()
        with mock.patch.object(time, "sleep") as wait:
            cleanup_installation(owner)
        owner.cleanup.assert_called_once_with()
        wait.assert_not_called()

    def test_cleanup_retries_a_transient_sharing_violation(self) -> None:
        owner = mock.Mock()
        owner.cleanup.side_effect = [self.sharing_error(), None]
        with mock.patch.object(time, "monotonic", return_value=0), mock.patch.object(time, "sleep") as wait:
            cleanup_installation(owner)
        self.assertEqual(owner.cleanup.call_count, 2)
        wait.assert_called_once_with(0.05)

    def test_cleanup_preserves_error_at_deadline(self) -> None:
        owner = mock.Mock()
        error = self.sharing_error()
        owner.cleanup.side_effect = error
        with mock.patch.object(time, "monotonic", side_effect=[0, 0, 2]), mock.patch.object(time, "sleep") as wait:
            with self.assertRaises(PermissionError) as caught:
                cleanup_installation(owner)
        self.assertIs(caught.exception, error)
        self.assertEqual(owner.cleanup.call_count, 2)
        wait.assert_called_once_with(0.05)

    def test_cleanup_attempt_limit_cannot_spin_forever(self) -> None:
        owner = mock.Mock()
        error = self.sharing_error()
        owner.cleanup.side_effect = error
        with mock.patch.object(time, "monotonic", return_value=0), mock.patch.object(time, "sleep") as wait:
            with self.assertRaises(PermissionError) as caught:
                cleanup_installation(owner)
        self.assertIs(caught.exception, error)
        self.assertEqual(owner.cleanup.call_count, 41)
        self.assertEqual(wait.call_count, 40)

    def test_cleanup_does_not_retry_unrelated_failures(self) -> None:
        denied = PermissionError("access denied")
        denied.winerror = 5
        for error in [denied, PermissionError("ordinary permissions"), OSError("I/O failure")]:
            with self.subTest(error=str(error)):
                owner = mock.Mock()
                owner.cleanup.side_effect = error
                with mock.patch.object(time, "sleep") as wait:
                    with self.assertRaises(type(error)) as caught:
                        cleanup_installation(owner)
                self.assertIs(caught.exception, error)
                owner.cleanup.assert_called_once_with()
                wait.assert_not_called()

    def test_cleanup_real_owned_file_and_unrelated_sibling(self) -> None:
        with tempfile.TemporaryDirectory(prefix="ca-cleanup-boundary-") as outer:
            sibling = Path(outer) / "unrelated"
            sibling.write_bytes(b"retain")
            owner = tempfile.TemporaryDirectory(prefix="owned-", dir=outer)
            path = Path(owner.name) / "held.bin"
            path.write_bytes(b"owned")
            handle = path.open("rb")
            try:
                # Release an actual Windows deletion-denying handle at the
                # retry boundary, without a timer race or external process.
                with mock.patch.object(time, "sleep", side_effect=lambda _delay: handle.close()) as wait:
                    cleanup_installation(owner)
                self.assertFalse(Path(owner.name).exists())
                self.assertEqual(sibling.read_bytes(), b"retain")
                self.assertEqual(wait.call_count, 1 if os.name == "nt" else 0)
            finally:
                handle.close()
                owner.cleanup()


class ArtifactFarmTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.installation_owner, cls.installation = build_installation()

    @classmethod
    def tearDownClass(cls) -> None:
        if cls.installation_owner is not None:
            cleanup_installation(cls.installation_owner)

    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory(prefix="ca-artifact-farm-")
        self.addCleanup(self.temporary.cleanup)
        self.test_directory = physical_test_directory(self.temporary.name)
        self.root = self.test_directory / "repo"
        self.root.mkdir()
        self.harness = WorkflowHarness(self.root, self.installation)
        self.harness.create_pair()
        self.harness.approve_pair()

    @staticmethod
    def projection() -> dict:
        return {
            "meta": {"name": "flow"},
            "tasks": [
                {
                    "id": "t-001",
                    "description": "Implement configuration precedence",
                    "deps": [],
                    "filesInScope": ["src/config.py"],
                    "test": {"path": "src/config.py"},
                    "gate": {"commands": ["python -m unittest -v tests.test_config"]},
                }
            ],
        }

    def project(self) -> dict:
        return _project_fixture(self.harness, self.projection())

    def test_projection_binding_and_canary_preflight(self) -> None:
        projected = self.project()
        verified = self.harness.client.call(
            "farm-verify",
            {"projection_path": projected["path"], "phase": "canary"},
        )
        self.assertTrue(verified["typed"])
        self.assertEqual(verified["base_sha256"], projected["base_sha256"])

    def test_only_provider_enrichment_can_be_sealed_for_dispatch(self) -> None:
        projected = self.project()
        projection_path = self.root / projected["path"]
        value = json.loads(projection_path.read_text(encoding="utf-8"))
        value["meta"].update(
            {"model": "current-fixture/model", "apiBaseUrl": "https://example.invalid/v1"}
        )
        projection_path.write_bytes(canonical_bytes(value) + b"\n")
        sealed = self.harness.client.call(
            "farm-seal",
            {
                "projection_path": projected["path"],
                "provenance": {
                    "model": "current-fixture/model",
                    "api_base_url": "https://example.invalid/v1",
                    "selection_source": "canary",
                    "origin": "synthetic current-model selection fixture",
                },
            },
        )
        verified = self.harness.client.call(
            "farm-verify",
            {
                "projection_path": projected["path"],
                "phase": "dispatch",
                "effective_model": "current-fixture/model",
                "effective_api_base_url": "https://example.invalid/v1",
            },
        )
        self.assertEqual(verified["seal"], sealed["seal"])

        value["tasks"][0]["test"]["path"] = "src/other.py"
        projection_path.write_bytes(canonical_bytes(value) + b"\n")
        with self.assertRaises(ArtifactError) as caught:
            self.harness.client.call(
                "farm-seal",
                {
                    "projection_path": projected["path"],
                    "provenance": {
                        "model": "current-fixture/model",
                        "api_base_url": "https://example.invalid/v1",
                        "selection_source": "manual",
                        "origin": "tamper fixture",
                    },
                },
            )
        self.assertEqual(caught.exception.code, "FARM_BINDING_MISSING")

    def test_source_change_invalidates_canary_binding(self) -> None:
        projected = self.project()
        (self.root / "src").mkdir()
        (self.root / "src" / "config.py").write_text("changed = True\n", encoding="utf-8")
        with self.assertRaises(ArtifactError) as caught:
            self.harness.client.call(
                "farm-verify", {"projection_path": projected["path"], "phase": "canary"}
            )
        self.assertEqual(caught.exception.code, "STALE_EVIDENCE")

    def test_real_dispatcher_blocks_unbound_html_before_side_effects(self) -> None:
        plugin = self.test_directory / "isolated-plugin"
        (plugin / "tools").mkdir(parents=True)
        shutil.copy2(REPO / "plugins" / "ca" / "tools" / "farm.js", plugin / "tools" / "farm.js")
        shutil.copytree(self.installation, plugin / "helpers" / "artifacts")
        plan_dir = self.root / ".codearbiter" / "plans"
        plan_dir.mkdir(parents=True, exist_ok=True)
        plan_path = plan_dir / "flow.plan.json"
        plan_path.write_bytes(canonical_bytes(self.projection()) + b"\n")
        result = subprocess.run(
            ["node", str(plugin / "tools" / "farm.js"), "--canary", str(plan_path)],
            cwd=self.root,
            text=True,
            capture_output=True,
            timeout=30,
        )
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("FARM_BINDING_MISSING", result.stderr)
        self.assertFalse((self.root / ".farm").exists())

    def test_real_dispatcher_accepts_supported_optional_manifest_declaration(self) -> None:
        # This tests decoder compatibility with actual installed engine bytes.
        # Synthetic qualification metadata is NOT trusted qualification evidence.
        from _artifactmanifestlib import CONTRACT
        projected = self.project()
        plugin = self.test_directory / "isolated-plugin"
        (plugin / "tools").mkdir(parents=True)
        shutil.copy2(REPO / "plugins/ca/tools/farm.js", plugin / "tools/farm.js")
        payload = plugin / "helpers/artifacts"
        shutil.copytree(self.installation, payload)
        manifest_path = payload / "release.json"
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        manifest["context_qualification"] = {platform: {
            "source_commit": "a" * 40, "workflow": CONTRACT["workflow"], "run_id": "1",
            "binary_sha256": entry["sha256"], "observation_sha256": "b" * 64,
            "module_sha256": "c" * 64, "native_cases": CONTRACT["native_cases"],
        } for platform, entry in manifest["binaries"].items() if entry["native_tested"]}
        manifest_path.write_text(json.dumps(manifest), encoding="utf-8")
        script = """import(process.argv[1]).then(farm => farm.verifyFarmArtifactBoundary(process.argv[2], 'canary', '0'.repeat(64))).then(()=>process.exit(2)).catch(e=>{console.error(e.message);process.exit(1)});"""
        def invoke():
            return subprocess.run(["node", "--input-type=module", "-e", script,
                (plugin / "tools/farm.js").as_uri(), str(self.root / projected["path"])],
                cwd=self.root, text=True, capture_output=True, timeout=30)
        result = invoke()
        self.assertEqual(result.returncode, 1)
        self.assertIn("verified different projection bytes", result.stderr)
        manifest["context_qualification"] = 42
        manifest_path.write_text(json.dumps(manifest), encoding="utf-8")
        refused = invoke()
        self.assertEqual(refused.returncode, 1)
        self.assertIn("context qualification", refused.stderr)
        self.assertFalse((self.root / ".farm").exists())

    def test_dispatcher_rejects_projection_bytes_other_than_the_parsed_bytes(self) -> None:
        projected = self.project()
        plugin = self.test_directory / "isolated-plugin"
        (plugin / "tools").mkdir(parents=True)
        shutil.copy2(REPO / "plugins" / "ca" / "tools" / "farm.js", plugin / "tools" / "farm.js")
        shutil.copytree(self.installation, plugin / "helpers" / "artifacts")
        script = """
import(process.argv[1])
  .then((farm) => farm.verifyFarmArtifactBoundary(process.argv[2], "canary", "0".repeat(64)))
  .then(() => { console.error("unexpected verification success"); process.exit(2); })
  .catch((error) => { console.error(error.message); process.exit(1); });
"""
        result = subprocess.run(
            [
                "node",
                "--input-type=module",
                "-e",
                script,
                (plugin / "tools" / "farm.js").as_uri(),
                str(self.root / projected["path"]),
            ],
            cwd=self.root,
            text=True,
            capture_output=True,
            timeout=30,
        )
        self.assertEqual(result.returncode, 1)
        self.assertIn("verified different projection bytes", result.stderr)
        self.assertFalse((self.root / ".farm").exists())

    def test_dispatcher_rejects_linked_plugin_installation_ancestors(self) -> None:
        real_plugin = self.test_directory / "real-plugin"
        linked_plugin = self.test_directory / "linked-plugin"
        (real_plugin / "tools").mkdir(parents=True)
        shutil.copy2(REPO / "plugins" / "ca" / "tools" / "farm.js", real_plugin / "tools" / "farm.js")
        shutil.copytree(self.installation, real_plugin / "helpers" / "artifacts")
        if os.name == "nt":
            made = subprocess.run(
                ["cmd", "/d", "/c", "mklink", "/J", str(linked_plugin), str(real_plugin)],
                text=True,
                capture_output=True,
            )
            if made.returncode != 0:
                self.skipTest(f"junction creation unavailable: {made.stderr.strip()}")
        else:
            os.symlink(real_plugin, linked_plugin, target_is_directory=True)
        plan_path = self.root / ".codearbiter" / "plans" / "flow.plan.json"
        plan_path.write_bytes(canonical_bytes(self.projection()) + b"\n")
        result = subprocess.run(
            [
                "node",
                "--preserve-symlinks-main",
                str(linked_plugin / "tools" / "farm.js"),
                "--canary",
                str(plan_path),
            ],
            cwd=self.root,
            text=True,
            capture_output=True,
            timeout=30,
        )
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("without linked ancestors", result.stderr)
        self.assertFalse((self.root / ".farm").exists())

    def test_dispatcher_does_not_downgrade_after_html_and_binding_deleted(self) -> None:
        projected = self.project()
        plugin = self.root / "isolated-plugin"
        (plugin / "tools").mkdir(parents=True)
        shutil.copy2(REPO / "plugins" / "ca" / "tools" / "farm.js", plugin / "tools" / "farm.js")
        shutil.copytree(self.installation, plugin / "helpers" / "artifacts")
        (self.root / ".codearbiter" / "plans" / "flow.html").unlink()
        shutil.rmtree(self.root / ".codearbiter" / ".artifacts" / "farm-bindings")
        result = subprocess.run(
            ["node", str(plugin / "tools" / "farm.js"), "--canary", str(self.root / projected["path"])],
            cwd=self.root,
            text=True,
            capture_output=True,
            timeout=30,
        )
        self.assertNotEqual(result.returncode, 0)
        self.assertNotIn("Canary results", result.stdout)
        self.assertFalse((self.root / ".farm").exists())


PACKAGE_MANIFEST = "helpers/artifacts/release.json"
PACKAGE_FARM = "tools/farm.js"
PACKAGE_BRIDGE = "hooks/_artifactlib.py"
PACKAGE_DOCTOR = "hooks/doctor.py"

_INSTALLED_BRIDGE_AND_DOCTOR = """
import json
from pathlib import Path
import sys

plugin, project = map(Path, sys.argv[1:])
sys.path.insert(0, str(plugin / "hooks"))
from _artifactlib import ArtifactClient, ArtifactError
import doctor

try:
    capability = ArtifactClient(project, plugin / "helpers/artifacts").call("capabilities")
    bridge = {"platform": capability.get("platform"),
              "repository_operations_available": capability.get("repository_operations_available")}
except ArtifactError as error:
    bridge = {"error": error.code}
doctor.check_artifact_capability(str(plugin), str(project))
print(json.dumps({"bridge": bridge, "doctor": doctor.results}))
"""

_INSTALLED_FARM = """
import { pathToFileURL } from "node:url";
const [, , bundle, plan, digest] = process.argv;
const farm = await import(pathToFileURL(bundle).href);
try {
  console.log(JSON.stringify(await farm.verifyFarmArtifactBoundary(plan, "canary", digest)));
} catch (error) {
  console.log(JSON.stringify({ error: error.message.slice(0, 512) }));
}
"""


def _package_probe(argv, root, env, *, timeout=30):
    completed = run_bounded(argv, timeout=timeout, cwd=root, env=env, stdin=subprocess.DEVNULL)
    if completed.returncode != 0 or completed.timed_out or completed.containment != "exited" or completed.stderr:
        raise AssertionError("installed package probe failed: " + (completed.stderr or completed.stdout)[-400:])
    return completed.stdout


def replay_installed_package_identity(plugin: Path, *, expected_members: dict[str, str],
                                      platform: str, node: Path, git: Path) -> dict:
    """Use one verified extracted Claude package and an owned synthetic typed plan.

    The caller owns production cohort authentication and extraction. No runtime
    installation, Farm dispatch, provider, or repository code is called.
    """
    for runtime in (node, git):
        if not runtime.is_absolute() or runtime.resolve(strict=True) != runtime or not runtime.is_file():
            raise AssertionError("installed package probe needs absolute physical runtimes")
    before = physical_members(plugin)["members"]
    if before != expected_members or not {PACKAGE_MANIFEST, PACKAGE_FARM, PACKAGE_BRIDGE, PACKAGE_DOCTOR} <= before.keys():
        raise AssertionError("installed Claude package differs from the authenticated cohort")
    installer_path = REPO / "tools/install-artifact-payload.py"
    loader = importlib.util.spec_from_file_location("farm_fixture_artifact_installer", installer_path)
    installer = importlib.util.module_from_spec(loader)
    loader.loader.exec_module(installer)
    manifest, _ = installer.load_payload(plugin / "helpers/artifacts")
    release = json.loads(manifest)
    if platform not in release.get("context_qualification", {}):
        raise AssertionError("installed manifest lacks the qualified platform")
    if hashlib.sha256(manifest).hexdigest() != before[PACKAGE_MANIFEST]:
        raise AssertionError("installed manifest bytes changed after cohort admission")
    binary_sha256 = release["binaries"][platform]["sha256"]

    with FixtureDirectory(prefix="ca-farm-package-identity-") as temporary:
        owned = physical_test_directory(temporary)
        home = owned / "home"
        home.mkdir()
        project = owned / "project"
        project.mkdir()
        env = {name: os.environ[name] for name in ("SYSTEMROOT", "WINDIR") if name in os.environ}
        env.update({name: str(home) for name in ("HOME", "USERPROFILE", "APPDATA", "LOCALAPPDATA",
                    "XDG_CONFIG_HOME", "TEMP", "TMP", "TMPDIR")})
        env.update(PATH=str(git.parent), CODEARBITER_GIT_EXECUTABLE=str(git), GIT_CONFIG_NOSYSTEM="1",
                   GIT_CONFIG_GLOBAL=os.devnull, GIT_TERMINAL_PROMPT="0")
        _package_probe([str(git), "init", "-q", "-b", "feature/package-identity-fixture"], project, env)
        _package_probe([str(git), "-c", "user.name=Owned fixture", "-c", "user.email=fixture@example.invalid",
                        "-c", "commit.gpgsign=false", "commit", "--allow-empty", "-qm", "Owned fixture"], project, env)
        with mock.patch.dict(os.environ, env, clear=True):
            harness = WorkflowHarness(project, plugin / "helpers/artifacts")
            harness.create_pair()
            harness.approve_pair()
            projection = _project_fixture(harness, ArtifactFarmTest.projection())
        plan = project / projection["path"]
        projection_sha256 = hashlib.sha256(plan.read_bytes()).hexdigest()
        project_before = physical_members(project)["members"]

        unsupported = owned / "unsupported"
        shutil.copytree(plugin, unsupported)
        release["format"] = "codearbiter.artifact-release/99.0.0"
        (unsupported / PACKAGE_MANIFEST).write_bytes(canonical_bytes(release))
        unsupported_before = physical_members(unsupported)["members"]
        if {name: value for name, value in unsupported_before.items() if name != PACKAGE_MANIFEST} != {
                name: value for name, value in before.items() if name != PACKAGE_MANIFEST}:
            raise AssertionError("unsupported control differs outside its manifest")
        try:
            installer.load_payload(unsupported / "helpers/artifacts")
        except ValueError as error:
            if str(error) != "unsupported payload manifest":
                raise
        else:
            raise AssertionError("installer admitted the unsupported manifest")

        entry = owned / "farm-admission.mjs"
        entry.write_text(_INSTALLED_FARM, encoding="utf-8")
        observations = {}
        for name, installed in (("supported", plugin), ("unsupported", unsupported)):
            bridge_doctor = _package_probe([sys.executable, "-I", "-B", "-X", "utf8", "-c", _INSTALLED_BRIDGE_AND_DOCTOR,
                                            str(installed), str(project)], project, env)
            farm = _package_probe([str(node), str(entry), str(installed / PACKAGE_FARM), str(plan), projection_sha256],
                                  project, env, timeout=40)
            observations[name] = {**json.loads(bridge_doctor), "farm": json.loads(farm)}
        supported_result, unsupported_result = observations["supported"], observations["unsupported"]
        if (supported_result["bridge"] != {"platform": platform, "repository_operations_available": True}
                or supported_result["farm"] != {"typed": True}
                or len(supported_result["doctor"]) != 2
                or supported_result["doctor"][0][0] != "OK"
                or "digest verified against the pinned release manifest" not in supported_result["doctor"][0][1]
                or supported_result["doctor"][1] != ["OK", "HTML artifact catalog validates: 2 artifacts"]):
            raise AssertionError("installed package admission differs: " + json.dumps(supported_result))
        if (unsupported_result["bridge"] != {"error": "UNSUPPORTED_VERSION"}
                or unsupported_result["farm"] != {"error": "artifact release manifest identity is unsupported"}
                or len(unsupported_result["doctor"]) != 1
                or unsupported_result["doctor"][0][0] != "FAIL"
                or "(UNSUPPORTED_VERSION)" not in unsupported_result["doctor"][0][1]):
            raise AssertionError("installed unsupported-manifest refusal differs: " + json.dumps(unsupported_result))
        if (before != physical_members(plugin)["members"]
                or unsupported_before != physical_members(unsupported)["members"]
                or project_before != physical_members(project)["members"]):
            raise AssertionError("installed package or owned project changed during consumer readback")

    return {"format": "codearbiter.installed-package-identity/1", "platform": platform,
            "manifest_sha256": before[PACKAGE_MANIFEST], "farm_bundle_sha256": before[PACKAGE_FARM],
            "bridge_sha256": before[PACKAGE_BRIDGE], "doctor_sha256": before[PACKAGE_DOCTOR],
            "binary_sha256": binary_sha256, "projection_sha256": projection_sha256,
            "unsupported_manifest_sha256": unsupported_before[PACKAGE_MANIFEST], "observations": observations}



def observe_assembly() -> None:
    """Replay the final Claude archive after the package assembly verifier passes."""
    parser = argparse.ArgumentParser(description=observe_assembly.__doc__)
    parser.add_argument("--installed-package-cohort", type=Path, required=True)
    parser.add_argument("--promotion-receipt-sha256", required=True)
    parser.add_argument("--receipt", type=Path, required=True)
    args = parser.parse_args()
    package_root = args.installed_package_cohort.resolve(strict=True)
    cohort_bytes = (package_root / "artifact-package-cohort.json").read_bytes()
    cohort = json.loads(cohort_bytes)
    if (cohort["source_commit"], cohort["workflow"], cohort["run_id"],
            cohort["promotion_receipt_sha256"]) != (
            os.environ["GITHUB_SHA"], ".github/workflows/ci.yml", os.environ["GITHUB_RUN_ID"],
            args.promotion_receipt_sha256,
    ):
        raise ValueError("package cohort identity differs from this assembly")

    package = cohort["packages"]["claude"]
    archive = package_root / package["file"]
    if archive.resolve(strict=True) != archive or archive.parent != package_root:
        raise ValueError("Claude archive must be a physical member of the verified cohort")
    with archive.open("rb") as contents:
        if hashlib.file_digest(contents, "sha256").hexdigest() != package["sha256"]:
            raise ValueError("Claude archive bytes differ from the verified cohort")
    node = Path(shutil.which("node")).resolve(strict=True)
    git = Path(shutil.which("git")).resolve(strict=True)
    package_tools = REPO / "tools" / "build-host-packages.py"
    spec = importlib.util.spec_from_file_location("farm_assembly_package_tools", package_tools)
    tools = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(tools)
    prefix = "plugins/ca/"
    members = {name.removeprefix(prefix): entry["sha256"]
               for name, entry in package["members"].items() if name.startswith(prefix)}
    with FixtureDirectory(prefix="ca-farm-assembly-") as temporary:
        extracted = physical_test_directory(temporary) / "archive"
        tools.extract_artifact_release_package(archive, extracted, host="claude")
        observed = replay_installed_package_identity(
            extracted / "plugins" / "ca", expected_members=members,
            platform="linux/amd64", node=node, git=git,
        )
    receipt = {
        **observed,
        "source_commit": cohort["source_commit"],
        "source_tree": cohort["source_tree"],
        "workflow": cohort["workflow"],
        "run_id": cohort["run_id"],
        "run_attempt": os.environ["GITHUB_RUN_ATTEMPT"],
        "promotion_receipt_sha256": cohort["promotion_receipt_sha256"],
        "cohort_sha256": hashlib.sha256(cohort_bytes).hexdigest(),
        "archive_sha256": package["sha256"],
    }
    with args.receipt.open("x", encoding="utf-8") as stream:
        stream.write(json.dumps(receipt, indent=2, sort_keys=True) + "\n")


if __name__ == "__main__":
    if "--installed-package-cohort" in sys.argv:
        observe_assembly()
    else:
        unittest.main(verbosity=2)
