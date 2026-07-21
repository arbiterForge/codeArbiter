#!/usr/bin/env python3
"""Regression-first contracts for the CI-owned Pi promotion machinery."""

from __future__ import annotations

import importlib.util
import json
import sys
import tempfile
import unittest
from pathlib import Path


REPO = Path(__file__).resolve().parents[2]
MODULE_PATH = REPO / ".github" / "scripts" / "pi_promotion.py"
DOCS_MODULE_PATH = REPO / ".github" / "scripts" / "check_docs_contract.py"
WORKFLOW_PATH = REPO / ".github" / "workflows" / "pi-promotion.yml"


def load_module():
    spec = importlib.util.spec_from_file_location("pi_promotion", MODULE_PATH)
    if spec is None or spec.loader is None:
        raise AssertionError("pi_promotion module is unavailable")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def load_docs_module():
    spec = importlib.util.spec_from_file_location("check_docs_contract", DOCS_MODULE_PATH)
    if spec is None or spec.loader is None:
        raise AssertionError("documentation contract module is unavailable")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


class PromotionPolicyTests(unittest.TestCase):
    def targets(self, root: Path) -> Path:
        path = root / "targets.json"
        path.write_text(json.dumps({
            "schema": 1,
            "policy": {
                "compatibility_source": "plugins/ca-pi/tools/src/compatibility.ts",
                "supported_versions_pattern": r'new Set\(\[(?P<versions>[^]]+)\]\)',
                "node_floor_pattern": r'MINIMUM_NODE = \[(?P<major>\d+), (?P<minor>\d+), (?P<patch>\d+)\]',
            },
            "targets": [],
        }), encoding="utf-8")
        return path

    def fixture_repo(self, root: Path) -> None:
        source = root / "plugins" / "ca-pi" / "tools" / "src" / "compatibility.ts"
        source.parent.mkdir(parents=True)
        source.write_text(
            'const SUPPORTED_PI_VERSIONS = new Set(["0.80.5", "0.80.6"]);\n'
            "const MINIMUM_NODE = [22, 19, 0] as const;\n",
            encoding="utf-8",
        )

    def test_policy_reads_existing_compatibility_source(self):
        module = load_module()
        with tempfile.TemporaryDirectory() as raw:
            root = Path(raw)
            self.fixture_repo(root)
            policy = module.read_policy(root, module.load_targets(self.targets(root)))
        self.assertEqual(policy.minimum, "0.80.5")
        self.assertEqual(policy.last_verified, "0.80.6")
        self.assertEqual(policy.node_floor, (22, 19, 0))

    def test_candidate_requires_new_stable_exact_semver(self):
        module = load_module()
        policy = module.SupportPolicy("0.80.5", "0.80.6", (22, 19, 0))
        self.assertEqual(module.parse_candidate("0.80.10", policy).version, "0.80.10")
        for raw in ("latest", "0.80.6", "0.80.11-beta.1", "garbage"):
            with self.subTest(raw=raw):
                with self.assertRaises(module.PromotionError):
                    module.parse_candidate(raw, policy)

    def test_promotion_workflow_is_trusted_and_write_gated(self):
        workflow = WORKFLOW_PATH.read_text(encoding="utf-8")
        self.assertIn("workflow_dispatch:", workflow)
        self.assertIn("schedule:", workflow)
        self.assertNotIn("pull_request_target", workflow)
        self.assertIn("contents: read", workflow)
        self.assertIn("contents: write", workflow)
        self.assertIn("pull-requests: write", workflow)
        self.assertIn("inputs.create_pr == true", workflow)
        self.assertIn("--ignore-scripts", workflow)

    def test_checked_in_recipe_cannot_name_an_unapproved_runtime_write_path(self):
        module = load_module()
        with tempfile.TemporaryDirectory() as raw:
            path = Path(raw) / "targets.json"
            path.write_text(json.dumps({
                "schema": 1,
                "policy": {
                    "compatibility_source": "plugins/ca-pi/tools/src/compatibility.ts",
                    "supported_versions_pattern": r'new Set\(\[(?P<versions>[^]]+)\]\)',
                    "node_floor_pattern": r'MINIMUM_NODE = \[(?P<major>\d+), (?P<minor>\d+), (?P<patch>\d+)\]',
                },
                "targets": [{
                    "id": "escape", "path": ".git/config", "class": "policy",
                    "before": "x", "after": "y",
                }],
            }), encoding="utf-8")
            with self.assertRaises(module.PromotionError):
                module._enforce_official_write_scope(REPO, module.load_targets(path))


class PromotionPatchTests(unittest.TestCase):
    def targets(self, root: Path) -> Path:
        path = root / "targets.json"
        path.write_text(json.dumps({
            "schema": 1,
            "policy": {
                "compatibility_source": "plugins/ca-pi/tools/src/compatibility.ts",
                "supported_versions_pattern": r'new Set\(\[(?P<versions>[^]]+)\]\)',
                "node_floor_pattern": r'MINIMUM_NODE = \[(?P<major>\d+), (?P<minor>\d+), (?P<patch>\d+)\]',
            },
            "targets": [
                {
                    "id": "compatibility",
                    "path": "plugins/ca-pi/tools/src/compatibility.ts",
                    "class": "policy",
                    "before": 'new Set(["{minimum}", "{last_verified}"])',
                    "after": 'new Set(["{minimum}", "{candidate}"])',
                },
                {
                    "id": "current-doc",
                    "path": "docs/pi.md",
                    "class": "current-doc",
                    "before": "Supported: Pi {minimum} / Pi {last_verified}",
                    "after": "Supported: Pi {minimum} / Pi {candidate}",
                },
            ],
        }), encoding="utf-8")
        return path

    def fixture_repo(self, root: Path) -> None:
        compatibility = root / "plugins" / "ca-pi" / "tools" / "src" / "compatibility.ts"
        compatibility.parent.mkdir(parents=True)
        compatibility.write_text(
            'const SUPPORTED_PI_VERSIONS = new Set(["0.80.5", "0.80.6"]);\n'
            "const MINIMUM_NODE = [22, 19, 0] as const;\n",
            encoding="utf-8",
        )
        docs = root / "docs"
        docs.mkdir()
        (docs / "pi.md").write_text("Supported: Pi 0.80.5 / Pi 0.80.6\n", encoding="utf-8")
        reports = docs / "reports"
        reports.mkdir()
        (reports / "old-evidence.md").write_text("Observed Pi 0.80.6\n", encoding="utf-8")

    def test_apply_promotion_replaces_only_declared_singleton_targets(self):
        module = load_module()
        with tempfile.TemporaryDirectory() as raw:
            root = Path(raw)
            self.fixture_repo(root)
            changed = module.apply_promotion(
                root,
                module.load_targets(self.targets(root)),
                module.Candidate("0.80.10"),
            )
            self.assertEqual(set(changed), {
                Path("plugins/ca-pi/tools/src/compatibility.ts"),
                Path("docs/pi.md"),
            })
            self.assertIn("0.80.10", (root / "docs/pi.md").read_text(encoding="utf-8"))
            self.assertEqual(
                (root / "docs/reports/old-evidence.md").read_text(encoding="utf-8"),
                "Observed Pi 0.80.6\n",
            )

    def test_release_metadata_gets_one_patch_bump_and_changelog_entry(self):
        module = load_module()
        with tempfile.TemporaryDirectory() as raw:
            root = Path(raw)
            self.fixture_repo(root)
            package = root / "plugins" / "ca-pi" / "package.json"
            package.write_text('{"name":"ca-pi","version":"0.1.0"}\n', encoding="utf-8")
            changelog = root / "plugins" / "ca-pi" / "CHANGELOG.md"
            changelog.write_text("# Changelog\n\nAll notable changes to `ca-pi` are documented in this file.\n", encoding="utf-8")
            document = json.loads(self.targets(root).read_text(encoding="utf-8"))
            document["release"] = {
                "package_path": "plugins/ca-pi/package.json",
                "changelog_path": "plugins/ca-pi/CHANGELOG.md",
            }
            target_path = root / "targets-with-release.json"
            target_path.write_text(json.dumps(document), encoding="utf-8")
            module.apply_promotion(
                root, module.load_targets(target_path), module.Candidate("0.80.10"), date="2026-07-17",
            )
            self.assertEqual(json.loads(package.read_text(encoding="utf-8"))["version"], "0.1.1")
            self.assertIn("## [0.1.1] - 2026-07-17", changelog.read_text(encoding="utf-8"))
            self.assertIn("Pi 0.80.10", changelog.read_text(encoding="utf-8"))

    def test_help_delta_rejects_removed_required_flag(self):
        module = load_module()
        delta = module.compare_help(
            ("--no-approve", "--no-extensions"),
            ("--no-approve",),
        )
        self.assertTrue(delta.incompatible)
        self.assertEqual(delta.removed, ("--no-extensions",))

    def test_declared_replace_all_target_updates_only_its_one_file(self):
        module = load_module()
        with tempfile.TemporaryDirectory() as raw:
            root = Path(raw)
            self.fixture_repo(root)
            notes = root / "notes.md"
            notes.write_text("Pi 0.80.6 and Pi 0.80.6\n", encoding="utf-8")
            document = json.loads(self.targets(root).read_text(encoding="utf-8"))
            document["targets"].append({
                "id": "all-notes", "path": "notes.md", "class": "current-doc",
                "before": "0.80.6", "after": "{candidate}", "occurrences": "all",
            })
            target_path = root / "targets-all.json"
            target_path.write_text(json.dumps(document), encoding="utf-8")
            module.apply_promotion(root, module.load_targets(target_path), module.Candidate("0.80.10"))
            self.assertEqual(notes.read_text(encoding="utf-8"), "Pi 0.80.10 and Pi 0.80.10\n")

    def test_help_snapshot_keeps_only_public_option_lines(self):
        module = load_module()
        snapshot = module.normalize_help("""Pi 0.80.6\n\nUsage: pi [options]\n  --model <name>  Use a model\n  -h, --help      Show help\nExamples:\n  pi\n""")
        self.assertEqual(snapshot, ("--model <name>", "-h, --help"))

    def test_receipt_is_bounded_and_does_not_include_raw_output(self):
        module = load_module()
        receipt = module.render_receipt(
            candidate="0.80.7",
            platform="ubuntu-latest",
            contract="help-delta",
            delta=module.HelpDelta(removed=("--old",), added=("--new",)),
        )
        self.assertIn("candidate=0.80.7", receipt)
        self.assertIn("removed=--old", receipt)
        self.assertNotIn("Usage:", receipt)


class DocumentationContractTests(unittest.TestCase):
    def contract(self, root: Path) -> Path:
        path = root / "docs-contract.json"
        path.write_text(json.dumps({
            "schema": 1,
            "classes": [
                {"name": "historical", "include": ["docs/reports/**"]},
                {"name": "current", "include": ["README.md", "docs/*.md"], "exclude": ["docs/reports/**"]},
                {"name": "generated", "include": ["docs/generated/**"]},
            ],
            "bindings": [
                {"path": "docs/pi.md", "template": "Supported: Pi {minimum} / Pi {last_verified}"},
            ],
            "generator_checks": [],
        }), encoding="utf-8")
        return path

    def test_every_markdown_path_has_exactly_one_classification(self):
        docs = load_docs_module()
        promotion = load_module()
        with tempfile.TemporaryDirectory() as raw:
            root = Path(raw)
            (root / "docs").mkdir()
            (root / "README.md").write_text("# current\n", encoding="utf-8")
            (root / "notes.md").write_text("# unknown\n", encoding="utf-8")
            contract = docs.load_contract(self.contract(root))
            findings = docs.check_documentation(
                root,
                contract,
                promotion.SupportPolicy("0.80.5", "0.80.10", (22, 19, 0)),
                paths=(Path("README.md"), Path("notes.md")),
            )
        self.assertTrue(any(row.code == "DOC-UNCLASSIFIED" and row.path == "notes.md" for row in findings))

    def test_current_document_must_match_support_fact(self):
        docs = load_docs_module()
        promotion = load_module()
        with tempfile.TemporaryDirectory() as raw:
            root = Path(raw)
            (root / "docs").mkdir()
            (root / "docs" / "pi.md").write_text("Supported: Pi 0.80.5 / Pi 0.80.6\n", encoding="utf-8")
            contract = docs.load_contract(self.contract(root))
            findings = docs.check_documentation(
                root,
                contract,
                promotion.SupportPolicy("0.80.5", "0.80.10", (22, 19, 0)),
                paths=(Path("docs/pi.md"),),
            )
        self.assertTrue(any(row.code == "DOC-FACT-STALE" for row in findings))

    def test_historical_document_is_link_checked_without_current_fact_rewrite(self):
        docs = load_docs_module()
        promotion = load_module()
        with tempfile.TemporaryDirectory() as raw:
            root = Path(raw)
            reports = root / "docs" / "reports"
            reports.mkdir(parents=True)
            (reports / "evidence.md").write_text("[missing](gone.md) Pi 0.80.6\n", encoding="utf-8")
            contract = docs.load_contract(self.contract(root))
            findings = docs.check_documentation(
                root,
                contract,
                promotion.SupportPolicy("0.80.5", "0.80.10", (22, 19, 0)),
                paths=(Path("docs/reports/evidence.md"),),
            )
        self.assertEqual([(row.code, row.path) for row in findings], [("DOC-LINK-MISSING", "docs/reports/evidence.md")])

    def test_excluded_historical_path_does_not_overlap_a_broad_current_rule(self):
        docs = load_docs_module()
        with tempfile.TemporaryDirectory() as raw:
            root = Path(raw)
            reports = root / "docs" / "reports"
            reports.mkdir(parents=True)
            contract_path = root / "docs-contract.json"
            contract_path.write_text(json.dumps({
                "schema": 1,
                "classes": [
                    {"name": "historical", "include": ["docs/reports/**"]},
                    {"name": "current", "include": ["**/*.md"], "exclude": ["docs/reports/**"]},
                ],
                "bindings": [],
                "generator_checks": [],
            }), encoding="utf-8")
            contract = docs.load_contract(contract_path)
            self.assertEqual(docs.classify(Path("docs/reports/evidence.md"), contract), ("historical",))

    def broad_current_contract(self, root: Path) -> Path:
        path = root / "docs-contract.json"
        path.write_text(json.dumps({
            "schema": 1,
            "classes": [{"name": "current", "include": ["**/*.md"]}],
            "bindings": [],
            "generator_checks": [],
        }), encoding="utf-8")
        return path

    def test_link_scanner_ignores_markdown_code_fences(self):
        docs = load_docs_module()
        promotion = load_module()
        with tempfile.TemporaryDirectory() as raw:
            root = Path(raw)
            (root / "README.md").write_text("```ts\nconst x = [factory](options.cwd);\n```\n", encoding="utf-8")
            findings = docs.check_documentation(
                root,
                docs.load_contract(self.broad_current_contract(root)),
                promotion.SupportPolicy("0.80.5", "0.80.10", (22, 19, 0)),
                paths=(Path("README.md"),),
            )
        self.assertEqual(findings, [])

    def test_link_scanner_accepts_github_relative_pull_links(self):
        docs = load_docs_module()
        promotion = load_module()
        with tempfile.TemporaryDirectory() as raw:
            root = Path(raw)
            (root / "CHANGELOG.md").write_text("[#11](../../pull/11)\n", encoding="utf-8")
            findings = docs.check_documentation(
                root,
                docs.load_contract(self.broad_current_contract(root)),
                promotion.SupportPolicy("0.80.5", "0.80.10", (22, 19, 0)),
                paths=(Path("CHANGELOG.md"),),
            )
        self.assertEqual(findings, [])

    def test_site_route_links_resolve_from_docs_content_root(self):
        docs = load_docs_module()
        promotion = load_module()
        with tempfile.TemporaryDirectory() as raw:
            root = Path(raw)
            content = root / "site" / "src" / "content" / "docs"
            (content / "concepts").mkdir(parents=True)
            (content / "overview.md").write_text("[Concepts](../concepts/)\n", encoding="utf-8")
            (content / "concepts" / "index.md").write_text("# concepts\n", encoding="utf-8")
            findings = docs.check_documentation(
                root,
                docs.load_contract(self.broad_current_contract(root)),
                promotion.SupportPolicy("0.80.5", "0.80.10", (22, 19, 0)),
                paths=(Path("site/src/content/docs/overview.md"),),
            )
        self.assertEqual(findings, [])

    def test_generator_check_failure_is_a_documentation_finding(self):
        docs = load_docs_module()
        promotion = load_module()
        with tempfile.TemporaryDirectory() as raw:
            root = Path(raw)
            (root / "README.md").write_text("# docs\n", encoding="utf-8")
            contract_path = self.broad_current_contract(root)
            document = json.loads(contract_path.read_text(encoding="utf-8"))
            command = [sys.executable, "-c", "raise SystemExit(7)"]
            document["generator_checks"] = [command]
            contract_path.write_text(json.dumps(document), encoding="utf-8")
            docs.ALLOWED_GENERATOR_CHECKS = frozenset({tuple(command)})
            findings = docs.check_documentation(
                root,
                docs.load_contract(contract_path),
                promotion.SupportPolicy("0.80.5", "0.80.10", (22, 19, 0)),
                paths=(Path("README.md"),),
            )
        self.assertEqual([row.code for row in findings], ["DOC-GENERATOR-FAILED"])

    def test_generator_check_configuration_cannot_execute_arbitrary_commands(self):
        docs = load_docs_module()
        with tempfile.TemporaryDirectory() as raw:
            root = Path(raw)
            contract_path = self.broad_current_contract(root)
            document = json.loads(contract_path.read_text(encoding="utf-8"))
            document["generator_checks"] = [["python", "-c", "print('unexpected')"]]
            contract_path.write_text(json.dumps(document), encoding="utf-8")
            with self.assertRaises(docs.ContractError):
                docs.load_contract(contract_path)


if __name__ == "__main__":
    unittest.main()
