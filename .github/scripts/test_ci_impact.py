#!/usr/bin/env python3
"""Unit tests for the fail-safe CI impact planner.

Run: python .github/scripts/test_ci_impact.py

The planner is intentionally stdlib-only.  These tests keep its classification
contract deterministic and, most importantly, prove that an unrecognised file
selects the broad validation lane instead of silently predicting a skip.
"""
import importlib.util
import json
import sys
import tempfile
import unittest
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[2]
_TOOL = REPO_ROOT / "tools" / "ci-impact.py"
_DESCRIPTORS_TOOL = REPO_ROOT / "tools" / "host_descriptors.py"

_spec = importlib.util.spec_from_file_location("ci_impact", _TOOL)
module = importlib.util.module_from_spec(_spec)
sys.modules[_spec.name] = module
_spec.loader.exec_module(module)


def hosts():
    spec = importlib.util.spec_from_file_location("host_descriptors_ci_impact", _DESCRIPTORS_TOOL)
    descriptors = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = descriptors
    spec.loader.exec_module(descriptors)
    return descriptors.load_host_descriptors(str(REPO_ROOT))


def map_document():
    return {
        "schema": 1,
        "checks": [
            {
                "id": "broad-lane",
                "lane": "CHECK",
                "scope": "REPO",
                "contract": "Broad validation",
            },
            {
                "id": "pi-adapter",
                "lane": "CHECK",
                "scope": "PI",
                "contract": "Adapter contract",
            },
            {
                "id": "pi-latest",
                "lane": "WATCH",
                "scope": "PI",
                "contract": "Upstream compatibility",
            },
            {
                "id": "ca-surface",
                "lane": "CHECK",
                "scope": "CA",
                "contract": "Generated surface",
            },
            {
                "id": "codex-surface",
                "lane": "CHECK",
                "scope": "CDX",
                "contract": "Generated surface",
            },
            {
                "id": "pi-surface",
                "lane": "CHECK",
                "scope": "PI",
                "contract": "Generated surface",
            },
        ],
        "edges": [
            {"glob": "plugins/ca-pi/**", "checks": ["pi-adapter", "pi-latest"]},
            {"glob": "core/pysrc/**", "checks": ["broad-lane"]},
            {
                "kind": "descriptor_surface",
                "source_prefix": "core/surface/",
                "checks": {
                    "claude": "ca-surface",
                    "codex": "codex-surface",
                    "pi": "pi-surface",
                },
            },
        ],
    }


def valid_map():
    with tempfile.TemporaryDirectory() as temporary:
        path = Path(temporary) / "impact-map.json"
        path.write_text(json.dumps(map_document()), encoding="utf-8")
        return module.load_map(path)


class CheckNameTest(unittest.TestCase):
    def test_render_check_name_uses_the_fixed_tag_grammar(self):
        check = module.Check(
            id="pi-adapter",
            lane="CHECK",
            scope="PI",
            contract="Adapter contract",
            dimensions=("os: Windows", "runtime: Pi 0.80.5"),
        )
        self.assertEqual(
            module.render_check_name(check),
            "[CHECK] | [PI  ] | Adapter contract  <os: Windows · runtime: Pi 0.80.5>",
        )


class EvaluationTest(unittest.TestCase):
    def test_unknown_path_expands_to_the_broad_lane(self):
        result = module.evaluate(
            valid_map(), ["unclassified/new-file.txt"], hosts=()
        )
        self.assertTrue(result.fallback)
        self.assertEqual(result.reason, "unmapped path: unclassified/new-file.txt")
        self.assertEqual([check.id for check in result.selected], ["broad-lane"])

    def test_pi_plugin_change_selects_adapter_and_advisory_contracts(self):
        result = module.evaluate(
            valid_map(), ["plugins/ca-pi/tools/src/index.ts"], hosts=()
        )
        self.assertFalse(result.fallback)
        self.assertEqual(
            [check.id for check in result.selected], ["pi-adapter", "pi-latest"]
        )

    def test_multiple_paths_have_a_deterministic_deduplicated_selection(self):
        result = module.evaluate(
            valid_map(),
            ["plugins/ca-pi/tools/src/index.ts", "plugins/ca-pi/extensions/a.ts"],
            hosts=(),
        )
        self.assertEqual(
            [check.id for check in result.selected], ["pi-adapter", "pi-latest"]
        )


class MapValidationTest(unittest.TestCase):
    def load(self, document):
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / "impact-map.json"
            path.write_text(json.dumps(document), encoding="utf-8")
            return module.load_map(path)

    def test_rejects_duplicate_check_ids(self):
        document = map_document()
        document["checks"].append(document["checks"][0].copy())
        with self.assertRaisesRegex(module.ImpactMapError, "duplicate check id"):
            self.load(document)

    def test_rejects_unknown_edge_target(self):
        document = map_document()
        document["edges"][0]["checks"] = ["missing"]
        with self.assertRaisesRegex(module.ImpactMapError, "unknown check"):
            self.load(document)

    def test_rejects_missing_broad_lane(self):
        document = map_document()
        document["checks"] = document["checks"][1:]
        with self.assertRaisesRegex(module.ImpactMapError, "broad-lane"):
            self.load(document)


class DescriptorSurfaceTest(unittest.TestCase):
    def test_codex_host_note_selects_only_codex_surface_contract(self):
        result = module.evaluate(
            valid_map(), ["core/surface/includes/codex-host-notes.md"], hosts()
        )
        self.assertFalse(result.fallback)
        self.assertEqual([check.id for check in result.selected], ["codex-surface"])

    def test_shared_surface_template_selects_every_host_surface_contract(self):
        result = module.evaluate(
            valid_map(), ["core/surface/ORCHESTRATOR.md"], hosts()
        )
        self.assertFalse(result.fallback)
        self.assertEqual(
            {check.scope for check in result.selected}, {"CA", "CDX", "PI"}
        )


class WorkflowContractTest(unittest.TestCase):
    def test_ci_runs_impact_planner_without_replacing_existing_job_conditions(self):
        ci = (REPO_ROOT / ".github/workflows/ci.yml").read_text(encoding="utf-8")
        self.assertIn(
            "ci-${{ github.workflow }}-${{ github.event.pull_request.number || github.ref }}",
            ci,
        )
        self.assertIn("cancel-in-progress: true", ci)
        self.assertIn("id: impact", ci)
        self.assertIn("python tools/ci-impact.py", ci)
        self.assertIn("list-files: shell", ci)
        self.assertIn("impact: ${{ steps.filter.outputs.impact }}", ci)
        self.assertIn("needs.changes.outputs.impact == 'true'", ci)
        self.assertIn("needs.changes.outputs.ca-pi == 'true'", ci)

    def test_ci_uses_the_typed_check_name_schema_for_every_owned_job(self):
        ci = (REPO_ROOT / ".github/workflows/ci.yml").read_text(encoding="utf-8")
        expected = (
            "[CHECK] | [REPO] | Impact selection",
            "[CHECK] | [REPO] | Impact planner contract",
            "[CHECK] | [CORE] | Host descriptor contract",
            "[CHECK] | [CA  ] | Farm dispatcher contract",
            "[CHECK] | [SBX ] | Sandbox driver contract",
            "[CHECK] | [PI  ] | Adapter contract  <os: ${{ matrix.os }} · runtime: Pi ${{ matrix.pi-version }}>",
            "[WATCH] | [PI  ] | Upstream compatibility  <runtime: npm latest>",
            "[CHECK] | [PI  ] | Security analysis  <language: JavaScript/TypeScript>",
            "[CHECK] | [CORE] | Hook contract  <os: ${{ matrix.os }}>",
            "[GATE ] | [CA  ] | Payload version",
            "[GATE ] | [SBX ] | Payload version",
            "[GATE ] | [CDX ] | Payload version",
            "[GATE ] | [PI  ] | Payload version",
            "[CHECK] | [CA  ] | Reference graph",
            "[CHECK] | [CA  ] | Documentation consistency",
            "[CHECK] | [SBX ] | Reference graph",
            "[CHECK] | [REPO] | Manifest contract",
            "[CHECK] | [REPO] | License consistency",
            "[CHECK] | [CORE] | Generated surface",
            "[CHECK] | [CDX ] | Reference graph",
            "[GATE ] | [REPO] | Merge readiness",
        )
        for name in expected:
            self.assertIn(f'name: "{name}"', ci)


class ReceiptCommandTest(unittest.TestCase):
    def test_cli_writes_deterministic_json_and_a_markdown_summary(self):
        with tempfile.TemporaryDirectory() as temporary:
            temporary_path = Path(temporary)
            output = temporary_path / "impact.json"
            summary = temporary_path / "summary.md"
            rc = module.main(
                [
                    "--map",
                    str(REPO_ROOT / ".github/ci-impact-map.json"),
                    "--hosts",
                    str(REPO_ROOT / "core/hosts.json"),
                    "--changed-files",
                    "plugins/ca-pi/tools/src/extension.ts",
                    "--output",
                    str(output),
                    "--summary",
                    str(summary),
                ]
            )
            self.assertEqual(rc, 0)
            receipt = json.loads(output.read_text(encoding="utf-8"))
            self.assertFalse(receipt["fallback"])
            self.assertEqual(
                [check["id"] for check in receipt["selected"]],
                ["pi-adapter", "pi-latest"],
            )
            self.assertEqual(
                receipt["predicted_not_selected"],
                ["ca-surface", "codex-surface", "pi-surface"],
            )
            self.assertEqual(
                receipt["selected"][0]["reproduce"],
                "npm --prefix plugins/ca-pi/tools test",
            )
            self.assertEqual(
                receipt["selected"][0]["reason"],
                "matched path: plugins/ca-pi/tools/src/extension.ts",
            )
            markdown = summary.read_text(encoding="utf-8")
            self.assertIn("## CI impact receipt", markdown)
            self.assertIn("Predicted not selected", markdown)
            self.assertIn("advisory", markdown)

    def test_a_malformed_map_falls_back_to_broad_validation_without_failing(self):
        # main()'s documented fail-safe contract (tools/ci-impact.py ~422-448):
        # any planner error (ImpactMapError/OSError/ValueError) degrades to the
        # broad-lane receipt rather than propagating, and the exit code stays 0
        # so a planner bug can never fail-closed the merge gate itself.
        with tempfile.TemporaryDirectory() as temporary:
            temporary_path = Path(temporary)
            malformed_map = temporary_path / "impact-map.json"
            malformed_map.write_text("not valid json", encoding="utf-8")
            output = temporary_path / "impact.json"
            summary = temporary_path / "summary.md"
            rc = module.main(
                [
                    "--map",
                    str(malformed_map),
                    "--hosts",
                    str(REPO_ROOT / "core/hosts.json"),
                    "--changed-files",
                    "plugins/ca-pi/tools/src/extension.ts",
                    "--output",
                    str(output),
                    "--summary",
                    str(summary),
                ]
            )
            self.assertEqual(rc, 0)
            receipt = json.loads(output.read_text(encoding="utf-8"))
            self.assertTrue(receipt["fallback"])
            self.assertEqual(
                [check["id"] for check in receipt["selected"]],
                ["broad-lane"],
            )
            self.assertTrue(receipt["reason"].startswith("planner error:"))
            markdown = summary.read_text(encoding="utf-8")
            self.assertIn("## CI impact receipt", markdown)


if __name__ == "__main__":
    unittest.main()
