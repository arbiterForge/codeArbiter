#!/usr/bin/env python3
"""Regression tests for the CLAUDE_PLUGIN_ROOT classification inventory."""
from __future__ import annotations

import importlib.util
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
            ".github/scripts/fixture.py", f'ROOT_LITERAL = "{ROOT_LITERAL}"\n'
        )
        self.assertEqual(errors, [])
        self.assertEqual(
            [entry.category for entry in inventory], ["codex-compatibility-fixture-input"]
        )

    def test_immutable_history_is_classified_without_rewrite(self):
        errors, inventory = self.inventory(
            "CHANGELOG.md", f"Historical command used {ROOT_LITERAL}/hooks/pre-write.py.\n"
        )
        self.assertEqual(errors, [])
        self.assertEqual([entry.category for entry in inventory], ["immutable-history"])

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
