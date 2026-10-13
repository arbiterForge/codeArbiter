#!/usr/bin/env python3
"""Regression tests for the CLAUDE_PLUGIN_ROOT classification inventory."""
from __future__ import annotations

import hashlib
import importlib.util
import json
import subprocess
import tempfile
import unittest
from pathlib import Path


HERE = Path(__file__).resolve().parent
SPEC = importlib.util.spec_from_file_location(
    "check_plugin_refs_under_test", HERE / "check-plugin-refs.py"
)
CHECKER = importlib.util.module_from_spec(SPEC)
assert SPEC and SPEC.loader
SPEC.loader.exec_module(CHECKER)

ROOT_LITERAL = "${CLAUDE_PLUGIN_ROOT}"
ROOT_INSPECTION_NAME = "token"
HISTORICAL_CHANGELOG = "site/scripts/execution-maps/atlas-data/packet-preparation-changelog.json"
HISTORICAL_CHANGELOG_SHA256 = "8b76eefcb04bfc62454eb6cc433844851498749815d275d631fde8ff19876d81"


def write(root: Path, relative: str, text: str) -> None:
    path = root / relative
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8", newline="\n")


class ClaudeRootInventoryTest(unittest.TestCase):
    def inventory(self, relative: str, text: str):
        with tempfile.TemporaryDirectory() as raw:
            root = Path(raw)
            write(root, relative, text)
            return CHECKER.check_claude_root_inventory(root)

    def historical_changelog_bytes(self):
        encoded = (Path(CHECKER.REPO) / HISTORICAL_CHANGELOG).read_bytes()
        self.assertEqual(hashlib.sha256(encoded).hexdigest(), HISTORICAL_CHANGELOG_SHA256)
        decoded = json.loads(encoded)
        self.assertIsInstance(decoded, str)
        self.assertIn(ROOT_LITERAL, decoded)
        return encoded

    def byte_inventory(self, files):
        with tempfile.TemporaryDirectory() as raw:
            root = Path(raw)
            for relative, encoded in files.items():
                path = root / relative
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_bytes(encoded)
            result = CHECKER.check_claude_root_inventory(root)
            for relative, encoded in files.items():
                self.assertEqual((root / relative).read_bytes(), encoded)
            return result

    def test_exact_historical_changelog_fixture_is_immutable_history(self):
        encoded = self.historical_changelog_bytes()
        errors, inventory = self.byte_inventory({HISTORICAL_CHANGELOG: encoded})
        self.assertEqual(errors, [])
        self.assertEqual([row.path for row in inventory], [HISTORICAL_CHANGELOG])
        self.assertEqual([row.category for row in inventory], ["immutable-history"])

    def test_changed_or_malformed_historical_changelog_fixture_fails_closed(self):
        encoded = self.historical_changelog_bytes()
        mutations = {
            "extra newline": encoded + b"\n",
            "valid whitespace change": encoded + b" ",
            "malformed truncated JSON": encoded[:-2],
            "changed JSON shape": json.dumps({"historical": json.loads(encoded)}).encode(),
            "new active content": f'{{"active": "{ROOT_LITERAL}/hooks/pre-write.py"}}\n'.encode(),
        }
        for label, changed in mutations.items():
            with self.subTest(label=label):
                self.assertIn(ROOT_LITERAL.encode(), changed)
                errors, inventory = self.byte_inventory({HISTORICAL_CHANGELOG: changed})
                self.assertEqual(len(errors), 1)
                self.assertIn("historical fixture SHA-256 mismatch", errors[0])
                self.assertEqual(inventory, [])

    def test_moved_or_neighbour_historical_changelog_fixture_fails_closed(self):
        encoded = self.historical_changelog_bytes()
        paths = (
            "site/scripts/execution-maps/other-data/packet-preparation-changelog.json",
            "site/scripts/execution-maps/atlas-data/packet-preparation-changelog-copy.json",
            "packet-preparation-changelog.json",
        )
        for relative in paths:
            with self.subTest(path=relative):
                errors, inventory = self.byte_inventory({relative: encoded})
                self.assertEqual(len(errors), 1)
                self.assertIn("unclassified portable/product use", errors[0])
                self.assertEqual(inventory, [])

    def test_escaped_root_in_pinned_historical_fixture_fails_closed(self):
        encoded = self.historical_changelog_bytes()
        escaped = encoded.replace(b"$", b"\\u0024")
        self.assertNotIn(ROOT_LITERAL.encode(), escaped)
        self.assertEqual(json.loads(escaped), json.loads(encoded))
        errors, inventory = self.byte_inventory({HISTORICAL_CHANGELOG: escaped})
        self.assertEqual(len(errors), 1)
        self.assertIn("historical fixture SHA-256 mismatch", errors[0])
        self.assertEqual(inventory, [])

    def test_invalid_utf8_in_pinned_historical_fixture_fails_closed(self):
        invalid = b"\xff" + self.historical_changelog_bytes()
        with self.assertRaises(UnicodeDecodeError):
            invalid.decode("utf-8")
        errors, inventory = self.byte_inventory({HISTORICAL_CHANGELOG: invalid})
        self.assertEqual(len(errors), 1)
        self.assertIn("historical fixture SHA-256 mismatch", errors[0])
        self.assertEqual(inventory, [])

    def test_invalid_utf8_outside_pinned_fixture_keeps_existing_skip(self):
        errors, inventory = self.byte_inventory({
            "site/scripts/execution-maps/atlas-data/unpinned.json":
                b"\xff" + ROOT_LITERAL.encode(),
        })
        self.assertEqual(errors, [])
        self.assertEqual(inventory, [])

    def test_tracked_pinned_historical_fixture_missing_fails_closed(self):
        with tempfile.TemporaryDirectory() as raw:
            root = Path(raw)
            subprocess.run(["git", "init", "--quiet", str(root)], check=True)
            path = root / HISTORICAL_CHANGELOG
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(self.historical_changelog_bytes())
            subprocess.run(
                ["git", "-C", str(root), "add", HISTORICAL_CHANGELOG],
                check=True, capture_output=True,
            )
            path.unlink()
            errors, inventory = CHECKER.check_claude_root_inventory(root)
        self.assertEqual(len(errors), 1)
        self.assertIn("missing pinned historical fixture", errors[0])
        self.assertEqual(inventory, [])

    def test_exact_historical_fixture_does_not_hide_active_neighbour(self):
        neighbour = "site/scripts/execution-maps/atlas-data/active.json"
        errors, inventory = self.byte_inventory({
            HISTORICAL_CHANGELOG: self.historical_changelog_bytes(),
            neighbour: f'{{"active": "{ROOT_LITERAL}/hooks/pre-write.py"}}\n'.encode(),
        })
        self.assertEqual(len(errors), 1)
        self.assertIn(neighbour, errors[0])
        self.assertEqual([row.path for row in inventory], [HISTORICAL_CHANGELOG])
        self.assertEqual([row.category for row in inventory], ["immutable-history"])

    def test_unclassified_portable_product_occurrence_fails_closed(self):
        errors, _inventory = self.inventory(
            "plugins/ca-pi/arbiter.md", f"Use {ROOT_LITERAL}/hooks/pre-write.py.\n"
        )
        self.assertEqual(len(errors), 1)
        self.assertIn("unclassified portable/product use", errors[0])

    def test_unclassified_root_level_product_occurrence_fails_closed(self):
        errors, _inventory = self.inventory(
            "README.md", f"Use {ROOT_LITERAL}/hooks/pre-write.py.\n"
        )
        self.assertEqual(len(errors), 1)
        self.assertIn("unclassified portable/product use", errors[0])

    def test_claude_native_product_occurrence_is_classified(self):
        errors, inventory = self.inventory(
            "plugins/ca/skills/example/SKILL.md", f"Use {ROOT_LITERAL}/hooks/pre-write.py.\n"
        )
        self.assertEqual(errors, [])
        self.assertEqual([entry.category for entry in inventory], ["claude-native"])

    def test_codex_compatibility_fixture_input_is_classified(self):
        errors, inventory = self.inventory(
            ".github/scripts/check_skill_portability.py",
            f'ROOT_LITERAL = "{ROOT_LITERAL}"\n',
        )
        self.assertEqual(errors, [])
        self.assertEqual(
            [entry.category for entry in inventory], ["codex-compatibility-fixture-input"]
        )

    def test_installed_host_inspection_classifies_only_the_claude_branch_literal(self):
        source = f'    {ROOT_INSPECTION_NAME} = "{ROOT_LITERAL}" if host == "claude" else "${{PLUGIN_ROOT}}"\n'
        for path in ("core/pysrc/_artifactlib.py", "plugins/ca-codex/hooks/_artifactlib.py", "plugins/ca-pi/hooks/_artifactlib.py"):
            with self.subTest(path=path):
                errors, inventory = self.inventory(path, source)
                self.assertEqual(errors, [])
                self.assertEqual([row.category for row in inventory], ["claude-native"])

    def test_installed_host_inspection_does_not_allow_other_portable_root_uses(self):
        source = f'    {ROOT_INSPECTION_NAME} = "{ROOT_LITERAL}" if host == "claude" else "${{PLUGIN_ROOT}}"\n'
        mutations = (
            ("core/pysrc/_artifactlib.py", source.replace('host == "claude"', 'host == "codex"')),
            ("core/pysrc/_artifactlib.py", f'    {ROOT_INSPECTION_NAME} = "{ROOT_LITERAL}"\n'),
            ("plugins/ca-pi/hooks/_artifactlib.py", source + f'    path = "{ROOT_LITERAL}/hooks/elsewhere.py"\n'),
            ("core/pysrc/other.py", source),
        )
        for path, altered in mutations:
            with self.subTest(path=path, altered=altered):
                errors, _ = self.inventory(path, altered)
                self.assertEqual(len(errors), 1)
                self.assertIn("unclassified portable/product use", errors[0])

    def test_arbitrary_github_script_occurrence_fails_closed(self):
        errors, _inventory = self.inventory(
            ".github/scripts/portable_product.py", f'ROOT_LITERAL = "{ROOT_LITERAL}"\n'
        )
        self.assertEqual(len(errors), 1)
        self.assertIn("unclassified portable/product use", errors[0])

    def test_immutable_history_is_classified_without_rewrite(self):
        errors, inventory = self.inventory(
            "CHANGELOG.md", f"Historical command used {ROOT_LITERAL}/hooks/pre-write.py.\n"
        )
        self.assertEqual(errors, [])
        self.assertEqual([entry.category for entry in inventory], ["immutable-history"])

    def test_tribunal_frozen_bundle_history_is_classified(self):
        prefix = ".github/fixtures/tribunal/qualification/"
        captured = f'{{"captured": "{ROOT_LITERAL}/hooks/pre-write.py"}}\n'
        for name in (
            "candidate-bundle.json", "candidate-delivered-bundle.json", "incumbent-bundle.json"
        ):
            with self.subTest(name=name):
                errors, inventory = self.inventory(prefix + name, captured)
                self.assertEqual(errors, [])
                self.assertEqual(
                    [entry.category for entry in inventory], ["immutable-history"]
                )
        errors, inventory = self.inventory(prefix + "unlisted-bundle.json", captured)
        self.assertEqual(len(errors), 1)
        self.assertIn("unclassified portable/product use", errors[0])
        self.assertEqual(inventory, [])

    def test_repository_inventory_ignores_untracked_local_files(self):
        with tempfile.TemporaryDirectory() as raw:
            root = Path(raw)
            subprocess.run(["git", "init", "--quiet", str(root)], check=True)
            write(root, "plugins/ca/arbiter.md", f"Use {ROOT_LITERAL}/hooks/pre-write.py.\n")
            subprocess.run(["git", "-C", str(root), "add", "plugins/ca/arbiter.md"], check=True)
            write(root, "README.md", f"Use {ROOT_LITERAL}/hooks/pre-write.py.\n")
            errors, inventory = CHECKER.check_claude_root_inventory(root)
        self.assertEqual(errors, [])
        self.assertEqual([entry.category for entry in inventory], ["claude-native"])

    def test_live_repository_inventory_is_closed_and_nontrivial(self):
        errors, inventory = CHECKER.check_claude_root_inventory(CHECKER.REPO)
        self.assertEqual(errors, [])
        categories = {entry.category for entry in inventory}
        self.assertEqual(
            categories,
            {"claude-native", "codex-compatibility-fixture-input", "immutable-history"},
        )
        self.assertGreater(len(inventory), 0)

    def test_required_generated_surface_job_invokes_the_inventory(self):
        workflow = (Path(CHECKER.REPO) / ".github/workflows/ci.yml").read_text(encoding="utf-8")
        self.assertIn(
            "python3 .github/scripts/check-plugin-refs.py --claude-root-inventory",
            workflow,
        )


if __name__ == "__main__":
    unittest.main()
