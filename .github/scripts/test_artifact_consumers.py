#!/usr/bin/env python3
"""Inventory-led closure checks for structured spec and plan consumers."""

from __future__ import annotations

import json
import pathlib
import re
import subprocess
import sys
import unittest


ROOT = pathlib.Path(__file__).resolve().parents[2]
INVENTORY_PATH = ROOT / "docs" / "artifacts" / "consumer-inventory.json"
READINJECT_PATH = ROOT / "core" / "pysrc" / "_readinjectlib.py"
DOCTOR_PATH = ROOT / "core" / "pysrc" / "doctor.py"
STATUS_PATH = ROOT / "core" / "surface" / "commands" / "status.md"
DOCTOR_COMMAND_PATH = ROOT / "core" / "surface" / "commands" / "doctor.md"
STARTUP_PATH = ROOT / "core" / "pysrc" / "session-start.py"
ALLOWED_TREATMENTS = {
    "candidate-guidance",
    "explicit-exclusion",
    "explicitly-compatible",
    "historical-only",
    "implemented-on-demand-guidance",
    "implemented-pilot-only",
    "implemented-unpackaged",
    "legacy-compatible",
    "legacy-only",
    "partial",
}
REQUIRED_AREAS = {
    "entry-resume",
    "planning-tdd-execution",
    "context-capability",
    "status-doctor-startup-commit",
    "farm",
    "migration",
    "ci-release",
    "published-instructions",
    "explicit-exclusions",
}
SCANNED_SUFFIXES = {".md", ".py", ".ts", ".yml", ".yaml"}
AUTHORITATIVE_ROOTS = (
    "core/surface",
    "core/pysrc",
    "plugins/ca/tools/farm.ts",
    ".github/workflows/ci.yml",
    "site/src/content/docs",
    "site/src/curated",
    "tools/build-artifacts.py",
    "tools/install-artifact-payload.py",
    "tools/create-artifact-examples.py",
)
AUTHORITATIVE_PATTERNS = (
    r"\.codearbiter/(?:specs|plans)",
    r"(?:specs|plans)/<",
    r"plan\.json",
    r"ca-artifact",
    r"artifacts\.md",
)
ALLOWED_TREE_PATHS = {
    ".codearbiter/decisions",
    "docs/artifacts/design/original-review2",
    "docs/reports",
}


def load_inventory() -> dict:
    with INVENTORY_PATH.open(encoding="utf-8") as handle:
        return json.load(handle)


def inventory_paths(inventory: dict) -> tuple[set[str], set[str]]:
    exact: set[str] = set()
    trees: set[str] = set()
    for consumer in inventory["consumers"]:
        exact.update(consumer["canonical_paths"])
        exact.update(consumer["generated_paths"])
        exact.update(consumer.get("optional_paths", []))
        trees.update(consumer.get("tree_paths", []))
    return exact, trees


def discovered_paths() -> set[str]:
    patterns = [re.compile(pattern, re.IGNORECASE) for pattern in AUTHORITATIVE_PATTERNS]
    found: set[str] = set()
    for relative in AUTHORITATIVE_ROOTS:
        target = ROOT / relative
        candidates = [target] if target.is_file() else target.rglob("*")
        for path in candidates:
            if not path.is_file() or path.suffix not in SCANNED_SUFFIXES:
                continue
            text = path.read_text(encoding="utf-8")
            if any(pattern.search(text) for pattern in patterns):
                found.add(path.relative_to(ROOT).as_posix())
    return found


def unaccounted(
    discovered: set[str], accounted: set[str], accounted_trees: set[str]
) -> list[str]:
    missing: list[str] = []
    for path in sorted(discovered):
        if path in accounted:
            continue
        if any(path.startswith(prefix.rstrip("/") + "/") for prefix in accounted_trees):
            continue
        missing.append(path)
    return missing


class ArtifactConsumerClosureTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.inventory = load_inventory()

    def test_consumer_closure(self) -> None:
        accounted, trees = inventory_paths(self.inventory)
        self.assertEqual(
            unaccounted(discovered_paths(), accounted, trees),
            [],
            "live artifact reference lacks an inventory owner and treatment",
        )

    def test_inventory_contract_is_complete(self) -> None:
        self.assertEqual(self.inventory["schema_version"], 1)
        self.assertTrue(self.inventory["owner"])
        self.assertEqual(
            tuple(self.inventory["independent_search"]["roots"]),
            AUTHORITATIVE_ROOTS,
        )
        self.assertEqual(
            tuple(self.inventory["independent_search"]["patterns"]),
            AUTHORITATIVE_PATTERNS,
        )
        _, tree_paths = inventory_paths(self.inventory)
        self.assertEqual(tree_paths, ALLOWED_TREE_PATHS)
        for tree in tree_paths:
            self.assertFalse(
                any(
                    tree == root
                    or tree.startswith(root.rstrip("/") + "/")
                    for root in AUTHORITATIVE_ROOTS
                ),
                tree,
            )
        consumers = self.inventory["consumers"]
        ids = [consumer["id"] for consumer in consumers]
        self.assertEqual(len(ids), len(set(ids)), "duplicate consumer id")
        self.assertEqual({consumer["area"] for consumer in consumers}, REQUIRED_AREAS)
        for consumer in consumers:
            self.assertIn(consumer["treatment"], ALLOWED_TREATMENTS, consumer["id"])
            self.assertTrue(consumer["owner"], consumer["id"])
            self.assertTrue(consumer["reason"], consumer["id"])
            self.assertTrue(consumer["closure"], consumer["id"])
            self.assertTrue(consumer["task_refs"], consumer["id"])
            self.assertTrue(consumer["canonical_paths"], consumer["id"])
            if consumer.get("tree_paths"):
                self.assertIn(
                    consumer["treatment"],
                    {"explicit-exclusion", "historical-only"},
                    consumer["id"],
                )

    def test_inventory_paths_exist(self) -> None:
        exact, trees = inventory_paths(self.inventory)
        optional = {
            path
            for consumer in self.inventory["consumers"]
            for path in consumer.get("optional_paths", [])
        }
        for path in sorted(exact - optional):
            self.assertTrue((ROOT / path).exists(), path)
        for path in sorted(optional):
            self.assertTrue((ROOT / path).parent.exists(), path)
        for path in sorted(trees):
            self.assertTrue((ROOT / path).is_dir(), path)

    def test_rollout_remains_disabled(self) -> None:
        rollout = self.inventory["rollout"]
        self.assertTrue(rollout["legacy_markdown_default"])
        self.assertFalse(rollout["typed_html_default_enabled"])
        self.assertFalse(rollout["typed_html_farm_enabled"])

    def test_historical_records_are_explicitly_excluded(self) -> None:
        historical = next(
            item
            for item in self.inventory["consumers"]
            if item["id"] == "historical-records-and-reference-fixtures"
        )
        self.assertFalse(historical["live"])
        self.assertEqual(historical["treatment"], "historical-only")
        self.assertEqual(historical["closure"], "excluded-with-tested-reason")

    def test_unknown_live_reader_negative_control(self) -> None:
        accounted, trees = inventory_paths(self.inventory)
        synthetic = "core/pysrc/new_plan_reader.py"
        patterns = [
            re.compile(pattern, re.IGNORECASE)
            for pattern in AUTHORITATIVE_PATTERNS
        ]
        fixture = 'for path in glob(".codearbiter/plans/*.md"): consume(path)'
        self.assertTrue(any(pattern.search(fixture) for pattern in patterns))
        self.assertEqual(unaccounted({synthetic}, accounted, trees), [synthetic])

    def test_narrowed_search_scope_is_rejected(self) -> None:
        narrowed = dict(self.inventory)
        narrowed["independent_search"] = dict(self.inventory["independent_search"])
        narrowed["independent_search"]["roots"] = ["core/surface"]
        self.assertNotEqual(
            tuple(narrowed["independent_search"]["roots"]),
            AUTHORITATIVE_ROOTS,
        )

    def test_live_directory_cannot_mask_unknown_descendant(self) -> None:
        accounted, trees = inventory_paths(self.inventory)
        for root in AUTHORITATIVE_ROOTS:
            if not (ROOT / root).is_dir():
                continue
            synthetic = f"{root.rstrip('/')}/new_artifact_reader.md"
            self.assertEqual(
                unaccounted({synthetic}, accounted, trees),
                [synthetic],
                root,
            )

    def test_generated_host_copies_are_current(self) -> None:
        result = subprocess.run(
            [sys.executable, "tools/build-surface.py", "--check"],
            cwd=ROOT,
            text=True,
            capture_output=True,
            check=False,
        )
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)

    def test_diagnostic_readers_are_on_demand_and_schema_free(self) -> None:
        implementation = "\n".join(
            path.read_text(encoding="utf-8")
            for path in (READINJECT_PATH, DOCTOR_PATH)
        )
        self.assertNotIn('call("schema"', implementation)
        self.assertNotIn("call('schema'", implementation)
        startup = STARTUP_PATH.read_text(encoding="utf-8")
        self.assertNotIn("_artifactlib", startup)
        self.assertNotIn("artifact.schema", startup)

    def test_status_and_doctor_define_bounded_artifact_diagnostics(self) -> None:
        status = STATUS_PATH.read_text(encoding="utf-8")
        doctor = DOCTOR_COMMAND_PATH.read_text(encoding="utf-8")
        for text in (status, doctor):
            self.assertIn("CAPABILITY_MISSING", text)
            self.assertIn("repair or", text)
            self.assertIn("reinstall", text)
            self.assertIn("legacy Markdown", text)
            self.assertIn("repair-preview", text)
            self.assertIn("MUST NOT load the artifact schema", text)


if __name__ == "__main__":
    unittest.main(verbosity=2)
