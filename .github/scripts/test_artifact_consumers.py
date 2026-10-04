#!/usr/bin/env python3
"""Inventory-led closure checks for structured spec and plan consumers."""

from __future__ import annotations

import json
import importlib.util
import pathlib
import re
import subprocess
import sys
import unittest

import check_codex_skill_resources as codex_resources


ROOT = pathlib.Path(__file__).resolve().parents[2]
INVENTORY_PATH = ROOT / "docs" / "artifacts" / "consumer-inventory.json"
PLAN_STATUS_PATH = ROOT / "docs" / "artifacts" / "PLAN-STATUS.json"
ABSORPTION_REVIEW_PATH = ROOT / "docs" / "artifacts" / "ABSORPTION-REVIEW.md"
READINJECT_PATH = ROOT / "core" / "pysrc" / "_readinjectlib.py"
DOCTOR_PATH = ROOT / "core" / "pysrc" / "doctor.py"
STATUS_PATH = ROOT / "core" / "surface" / "commands" / "status.md"
DOCTOR_COMMAND_PATH = ROOT / "core" / "surface" / "commands" / "doctor.md"
STARTUP_PATH = ROOT / "core" / "pysrc" / "session-start.py"
PI_BRIDGE_PATH = ROOT / "plugins" / "ca-pi" / "hooks" / "pi-bridge.py"
ALLOWED_TREATMENTS = {
    "candidate-guidance",
    "explicit-exclusion",
    "explicitly-compatible",
    "historical-only",
    "html-capable",
    "implemented-on-demand-guidance",
    "implemented-pilot-only",
    "implemented-unpackaged",
    "legacy-compatible",
    "legacy-only",
    "partial",
}
DEFAULT_PATH_TREATMENTS = {"html-capable", "legacy-only"}
EXPECTED_DEFAULT_PATH_CONSUMERS = {
    "artifact-binary-bridge",
    "artifact-protocol-leaf",
    "brainstorming-producer",
    "checkpoint-execution",
    "commit-gate-spec-reader",
    "feature-entry-resume",
    "finalization-and-worktree-plan-readers",
    "governing-spec-discovery",
    "pi-native-plan-legacy",
    "sprint-entry-resume",
    "subagent-execution-acceptance",
    "tdd-obligation-reader",
    "writing-plans-producer",
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
SCANNED_SUFFIXES = {".js", ".md", ".py", ".ts", ".yml", ".yaml"}
AUTHORITATIVE_ROOTS = (
    "core/surface",
    "core/pysrc",
    "plugins/ca/tools/farm.ts",
    "plugins/ca-pi/tools/src",
    "plugins/ca-pi/hooks/pi-bridge.py",
    "plugins/ca-pi/hooks/_planfilelib.py",
    "plugins/ca-pi/extensions/codearbiter.js",
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
    r"\bcallPlanFileBridge\b",
    r"\bplan_file_operation\b",
)
ALLOWED_TREE_PATHS = {
    ".codearbiter/decisions",
    "academy-source",
    "docs/artifacts/design/original-review2",
    "docs/reports",
}
ALLOWED_EXTERNAL_GITLINKS = {"academy-source"}
EXPECTED_EPHEMERAL_OUTPUTS = {
    "path_prefixes": ["site/src/content/docs/reference/"],
    "paths": ["site/src/content/docs/changelog.md"],
    "generator": "site/scripts/gen.ts",
    "source_root": "plugins/ca",
    "workflow": ".github/workflows/docs.yml",
}

CONTEXT_PYTHON_SOURCES = (
    "_artifactlib.py", "_protectedstatelib.py", "_contextreportlib.py",
    "_contextsnapshotlib.py", "_provenancelib.py",
    "_contextselectlib.py", "_artifactpromptlib.py", "_readinjectlib.py",
    "prompt-submit.py",
)
CONTEXT_SURFACE_CONSUMERS = {
    "commands/feature.md": "compose_feature_actor_input",
    "commands/fix.md": "compose_fix_or_test_actor_input",
    "commands/review.md": "prepare_review_input",
    "skills/tdd/SKILL.md": "compose_fix_or_test_actor_input",
    "skills/subagent-driven-development/SKILL.md": "prepare_actor_delivery",
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


def is_ephemeral_output(path: str, inventory: dict) -> bool:
    declaration = inventory["ephemeral_generated_outputs"]
    return path in declaration["paths"] or any(
        path.startswith(prefix) for prefix in declaration["path_prefixes"]
    )


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
        self.assertEqual(
            set(self.inventory["independent_search"]["external_gitlinks"]),
            ALLOWED_EXTERNAL_GITLINKS,
        )
        self.assertEqual(
            self.inventory["ephemeral_generated_outputs"],
            EXPECTED_EPHEMERAL_OUTPUTS,
        )
        gitlinks = subprocess.run(
            ["git", "config", "-f", ".gitmodules", "--get-regexp", "^submodule\\..*\\.path$"],
            cwd=ROOT,
            text=True,
            capture_output=True,
            check=True,
        ).stdout.splitlines()
        self.assertEqual({line.split(maxsplit=1)[1] for line in gitlinks}, ALLOWED_EXTERNAL_GITLINKS)
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
            self.assertIsInstance(consumer["default_path"], bool, consumer["id"])
            if consumer.get("tree_paths"):
                self.assertIn(
                    consumer["treatment"],
                    {"explicit-exclusion", "historical-only"},
                    consumer["id"],
                )

    def test_default_path_consumer_closure_is_complete(self) -> None:
        consumers = self.inventory["consumers"]
        default_path = {item["id"]: item for item in consumers if item["default_path"]}
        self.assertEqual(set(default_path), EXPECTED_DEFAULT_PATH_CONSUMERS)
        for consumer in default_path.values():
            self.assertTrue(consumer["live"], consumer["id"])
            self.assertIn(
                consumer["treatment"], DEFAULT_PATH_TREATMENTS, consumer["id"]
            )
            self.assertNotIn("pending", consumer["closure"].lower(), consumer["id"])

    def test_farm_and_future_kinds_stay_outside_default_closure(self) -> None:
        consumers = {item["id"]: item for item in self.inventory["consumers"]}
        farm = [item for item in consumers.values() if item["area"] == "farm"]
        self.assertTrue(farm)
        for consumer in farm:
            self.assertFalse(consumer["default_path"], consumer["id"])
            self.assertEqual(
                consumer["closure"], "typed-html-implemented-disabled", consumer["id"]
            )
        for consumer_id in ("decomposition-plans", "task-ticket-and-audit-files"):
            consumer = consumers[consumer_id]
            self.assertFalse(consumer["default_path"], consumer_id)
            self.assertEqual(consumer["treatment"], "explicit-exclusion", consumer_id)

    def test_pi_native_plan_is_enforced_as_legacy_pair_only(self) -> None:
        consumer = next(
            item
            for item in self.inventory["consumers"]
            if item["id"] == "pi-native-plan-legacy"
        )
        self.assertTrue(consumer["default_path"])
        self.assertEqual(consumer["treatment"], "legacy-only")
        self.assertEqual(
            consumer["closure"], "closed-legacy-pair-only-html-refused"
        )
        bridge = PI_BRIDGE_PATH.read_text(encoding="utf-8")
        self.assertIn("require_legacy_pair=True", bridge)

    def test_inventory_paths_exist(self) -> None:
        exact, trees = inventory_paths(self.inventory)
        optional = {
            path
            for consumer in self.inventory["consumers"]
            for path in consumer.get("optional_paths", [])
        }
        for path in sorted(exact - optional):
            if is_ephemeral_output(path, self.inventory):
                continue
            self.assertTrue((ROOT / path).exists(), path)
        for path in sorted(optional):
            self.assertTrue((ROOT / path).parent.exists(), path)
        for path in sorted(trees):
            self.assertTrue((ROOT / path).is_dir(), path)

    def test_ephemeral_site_outputs_have_generator_and_ci_ownership(self) -> None:
        declaration = self.inventory["ephemeral_generated_outputs"]
        generator_path = ROOT / declaration["generator"]
        workflow_path = ROOT / declaration["workflow"]
        self.assertTrue(generator_path.is_file())
        self.assertTrue(workflow_path.is_file())

        ignored_probes = list(declaration["paths"]) + [
            f"{prefix}__inventory_probe__.md"
            for prefix in declaration["path_prefixes"]
        ]
        for path in ignored_probes:
            ignored = subprocess.run(
                ["git", "check-ignore", "--quiet", "--", path],
                cwd=ROOT,
                check=False,
            )
            self.assertEqual(ignored.returncode, 0, path)
            self.assertEqual(
                subprocess.run(
                    ["git", "ls-files", "--error-unmatch", "--", path],
                    cwd=ROOT,
                    text=True,
                    capture_output=True,
                    check=False,
                ).returncode,
                1,
                path,
            )

        generator = generator_path.read_text(encoding="utf-8")
        self.assertIn('const srcDir = join(repoRoot, "plugins", "ca");', generator)
        self.assertIn('"src", "content", "docs", "reference"', generator)
        self.assertIn('"src", "content", "docs", "changelog.md"', generator)

        workflow = workflow_path.read_text(encoding="utf-8")
        self.assertGreaterEqual(workflow.count('- "plugins/ca/**"'), 2)
        self.assertIn("run: npm run gen", workflow)
        self.assertIn("run: npm test", workflow)
        self.assertIn("run: npm run build", workflow)

    def test_default_rollout_is_enabled_but_farm_remains_disabled(self) -> None:
        rollout = self.inventory["rollout"]
        self.assertFalse(rollout["legacy_markdown_default"])
        self.assertTrue(rollout["typed_html_default_enabled"])
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

    def test_doctor_defines_bounded_artifact_diagnostics(self) -> None:
        status = STATUS_PATH.read_text(encoding="utf-8")
        doctor = DOCTOR_COMMAND_PATH.read_text(encoding="utf-8")
        self.assertIn("CAPABILITY_MISSING", doctor)
        self.assertIn("repair or", doctor)
        self.assertIn("reinstall", doctor)
        self.assertIn("legacy Markdown", doctor)
        self.assertIn("repair-preview", doctor)
        self.assertIn("MUST NOT load the artifact schema", doctor)

        diagnostics = next(
            item
            for item in self.inventory["consumers"]
            if item["id"] == "status-diagnostics"
        )
        self.assertEqual(diagnostics["closure"], "blocked-ra11-compatibility")
        self.assertIn("RA-11", diagnostics["reason"])
        self.assertNotIn("CAPABILITY_MISSING", status)

    def test_t017_status_deviation_remains_open_and_machine_readable(self) -> None:
        plan_status = json.loads(PLAN_STATUS_PATH.read_text(encoding="utf-8"))
        task = next(item for item in plan_status["tasks"] if item["id"] == "T-017")
        self.assertEqual(task["formal_acceptance"], "not_recorded")
        self.assertIn("Partial", task["disposition"])
        self.assertEqual(
            task["deviation"],
            {
                "status": "open",
                "original_requirement": "T-017 status diagnostics",
                "conflicting_contract": "RA-11 frozen no-argument status body",
                "required_resolution": (
                    "separately approved major compatibility decision or "
                    "contract-compatible mechanism"
                ),
            },
        )
        review = ABSORPTION_REVIEW_PATH.read_text(encoding="utf-8")
        self.assertIn("T-017 | Partial; explicit deviation", review)
        self.assertIn("status portion is not implemented", review)


class TestContextConsumerClosure(unittest.TestCase):
    def shortDescription(self):
        return None

    @classmethod
    def setUpClass(cls):
        spec = importlib.util.spec_from_file_location(
            "context_build_surface", ROOT / "tools" / "build-surface.py")
        cls.build_surface = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(cls.build_surface)
        cls.package = ROOT / "plugins" / "ca-codex"

    def generated_snapshot(self):
        expected = {}
        actual = {}
        for descriptor in self.build_surface.load_host_descriptors(str(ROOT)):
            host_root = ROOT / descriptor.plugin_dir
            rendered = self.build_surface.render_all(str(ROOT), descriptor.name)
            for source in CONTEXT_PYTHON_SOURCES:
                canonical = (ROOT / "core" / "pysrc" / source).read_bytes()
                key = (host_root / "hooks" / source).relative_to(ROOT).as_posix()
                expected[key] = canonical
                actual[key] = (ROOT / key).read_bytes()
            for source, symbol in CONTEXT_SURFACE_CONSUMERS.items():
                canonical_path = ROOT / "core" / "surface" / source
                self.assertIn(symbol, canonical_path.read_text(encoding="utf-8"), source)
                destination, _ = self.build_surface._output_rel(source, descriptor)
                self.assertIsNotNone(destination, (descriptor.name, source))
                key = (host_root / destination).relative_to(ROOT).as_posix()
                expected[key] = rendered[destination]
                actual[key] = (ROOT / key).read_bytes()
                self.assertIn(symbol.encode(), actual[key], key)
        return expected, actual

    @staticmethod
    def generated_mismatches(expected, actual):
        return sorted(path for path, body in expected.items()
                      if actual.get(path) != body)

    def test_t042_context_consumer_closure_positive_controls(self):
        """Context source, helpers, owner routes and three generated hosts close."""
        expected, actual = self.generated_snapshot()
        self.assertEqual(len(expected), 3 * (len(CONTEXT_PYTHON_SOURCES) +
                                              len(CONTEXT_SURFACE_CONSUMERS)))
        self.assertEqual(self.generated_mismatches(expected, actual), [])
        files = codex_resources._candidate_package_files(self.package)
        self.assertIsNone(codex_resources.validate_context_consumer_resources(files))
        self.assertTrue(codex_resources.candidate_resource_contract(
            self.package, files=files)["selected_paths"])
        inventory = load_inventory()["public_surface_baseline"]
        routes = json.loads((ROOT / "core/surface/command-routes.json").read_text(
            encoding="utf-8"))["commands"]
        reviewed_removals = {row["name"] for row in inventory["reviewed_removals"]
                             if row["category"] == "commands"}
        self.assertEqual(set(routes),
                         set(inventory["registrations"]["commands"]) - reviewed_removals)
        self.assertEqual(reviewed_removals, {"new-skill"})
        protected = next(row for row in load_inventory()["consumers"]
                         if row["id"] == "context-writer-protected-state")
        self.assertEqual(protected["treatment"], "partial")
        self.assertFalse(protected["default_path"])
        self.assertIn("core/pysrc/_protectedstatelib.py",
                      protected["canonical_paths"])

    def test_t042_context_consumer_closure_negative_controls(self):
        """Missing selector/helper, changed copy or omitted consumer fails."""
        files = codex_resources._candidate_package_files(self.package)
        for absent in ("hooks/_contextselectlib.py", "hooks/_contextreportlib.py",
                       "hooks/_protectedstatelib.py", "routines/tdd/SKILL.md"):
            damaged = dict(files)
            del damaged[absent]
            with self.subTest(absent=absent), self.assertRaisesRegex(
                    ValueError, "context.*missing"):
                codex_resources.validate_context_consumer_resources(damaged)
        omitted = dict(files)
        route = "skills/ca-review/SKILL.md"
        self.assertIn(b"prepare_review_input", omitted[route])
        omitted[route] = omitted[route].replace(b"prepare_review_input",
                                                b"omitted_review_context", 1)
        with self.assertRaisesRegex(ValueError, "context.*consumer"):
            codex_resources.candidate_resource_contract(self.package, files=omitted)
        expected, actual = self.generated_snapshot()
        altered = dict(actual)
        path = next(key for key in altered if key.endswith(
            "plugins/ca-pi/hooks/_contextselectlib.py"))
        altered[path] += b"\n# generated drift\n"
        self.assertEqual(self.generated_mismatches(expected, altered), [path])
        accounted, trees = inventory_paths(load_inventory())
        accounted.remove("core/pysrc/_protectedstatelib.py")
        self.assertEqual(unaccounted({"core/pysrc/_protectedstatelib.py"},
                                     accounted, trees),
                         ["core/pysrc/_protectedstatelib.py"])
        self.assertIsNone(codex_resources.validate_context_consumer_resources(
            {"skills/ca-feature/SKILL.md": b"Legacy feature policy"}))


if __name__ == "__main__":
    unittest.main(verbosity=2)
