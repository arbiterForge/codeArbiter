#!/usr/bin/env python3
"""Fresh farm projection, seal, staleness and dispatcher-boundary fixtures.

All workflow receipts are synthetic isolated-test evidence. They exercise the
cooperative authority contract and do not qualify a model or promote --farm.
"""

from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest

from test_artifact_authoring import (
    ArtifactError,
    WorkflowHarness,
    build_installation,
    canonical_hash,
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


class ArtifactFarmTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.installation_owner, cls.installation = build_installation()

    @classmethod
    def tearDownClass(cls) -> None:
        if cls.installation_owner is not None:
            cls.installation_owner.cleanup()

    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory(prefix="ca-artifact-farm-")
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name) / "repo"
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
                    "gate": {"commands": ["python -m unittest tests.test_config"]},
                }
            ],
        }

    def project(self) -> dict:
        projection = self.projection()
        plan = self.harness.client.call("identity", {"artifact_id": "PLAN-FLOW"})
        spec = self.harness.client.call("identity", {"artifact_id": "SPEC-FLOW"})
        snapshot = self.harness.client.call("snapshot", {"artifact_id": "PLAN-FLOW"})
        task = self.harness.client.call(
            "read", {"artifact_id": "PLAN-FLOW", "symbol": "T-001", "mode": "exact"}
        )["record"]
        definition = task["verification"][0]
        base_sha256 = hashlib.sha256(canonical_bytes(projection)).hexdigest()
        authorization = self.harness.capture(
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
                        "command": "python -m unittest tests.test_config",
                        "exit": 1,
                        "stdout_sha256": hashlib.sha256(b"synthetic RED").hexdigest(),
                        "stderr_sha256": hashlib.sha256(b"").hexdigest(),
                    }
                ],
            },
        )
        return self.harness.mutate(
            "farm-project",
            "PLAN-FLOW",
            scope="CP-01",
            slice=["T-001"],
            target=".codearbiter/plans/flow.plan.json",
            projection=projection,
            receipt=authorization,
        )

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
        plugin = Path(self.temporary.name) / "isolated-plugin"
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

    def test_dispatcher_rejects_projection_bytes_other_than_the_parsed_bytes(self) -> None:
        projected = self.project()
        plugin = Path(self.temporary.name) / "isolated-plugin"
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
        real_plugin = Path(self.temporary.name) / "real-plugin"
        linked_plugin = Path(self.temporary.name) / "linked-plugin"
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


if __name__ == "__main__":
    unittest.main(verbosity=2)
