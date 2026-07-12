#!/usr/bin/env python3
"""Tests for the pinned ca-codex package validator."""

import importlib.util
import json
import tempfile
import unittest
from pathlib import Path


MODULE_PATH = Path(__file__).with_name("validate_codex_plugin.py")
SPEC = importlib.util.spec_from_file_location("validate_codex_plugin", MODULE_PATH)
validator = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(validator)


VALID_MANIFEST = {
    "name": "ca-codex",
    "version": "0.2.1",
    "description": "Governance for Codex.",
    "author": {"name": "arbiterForge"},
    "license": "AGPL-3.0-only",
    "interface": {
        "displayName": "codeArbiter for Codex",
        "shortDescription": "Governance for Codex repositories.",
        "longDescription": "Shared governance and enforcement for Codex and Claude Code.",
        "developerName": "arbiterForge",
        "category": "Developer Tools",
        "capabilities": ["Interactive", "Write"],
        "defaultPrompt": ["Initialize codeArbiter for this repository."],
        "brandColor": "#0E8A16",
    },
}

VALID_MARKETPLACE = {
    "name": "codearbiter",
    "interface": {"displayName": "codeArbiter"},
    "plugins": [{
        "name": "ca-codex",
        "source": {"source": "local", "path": "./plugins/ca-codex"},
        "policy": {"installation": "AVAILABLE", "authentication": "ON_INSTALL"},
        "category": "Developer Tools",
    }],
}


class PackageFixture:
    def __init__(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.plugin = self.root / "plugins" / "ca-codex"
        (self.plugin / ".codex-plugin").mkdir(parents=True)
        (self.plugin / "skills" / "ca-init").mkdir(parents=True)
        self.marketplace = self.root / ".agents" / "plugins" / "marketplace.json"
        self.marketplace.parent.mkdir(parents=True)
        self.write_manifest(VALID_MANIFEST)
        self.write_marketplace(VALID_MARKETPLACE)
        self.write_skill("---\nname: ca-init\ndescription: \"Initialize: safely.\"\nargument-hint: \"[path]\"\n---\n\n# Init\n")

    def cleanup(self):
        self.tmp.cleanup()

    def write_manifest(self, value):
        (self.plugin / ".codex-plugin" / "plugin.json").write_text(
            json.dumps(value), encoding="utf-8")

    def write_marketplace(self, value):
        self.marketplace.write_text(json.dumps(value), encoding="utf-8")

    def write_skill(self, value):
        (self.plugin / "skills" / "ca-init" / "SKILL.md").write_text(
            value, encoding="utf-8")

    def errors(self):
        return validator.validate_plugin(self.plugin, self.marketplace)


class TestValidateCodexPlugin(unittest.TestCase):
    def setUp(self):
        self.fx = PackageFixture()

    def tearDown(self):
        self.fx.cleanup()

    def test_valid_package_has_no_errors(self):
        self.assertEqual(self.fx.errors(), [])

    def test_rejects_unsupported_top_level_display_name(self):
        manifest = dict(VALID_MANIFEST, displayName="wrong level")
        self.fx.write_manifest(manifest)
        self.assertIn("plugin.json field `displayName` is not accepted",
                      self.fx.errors())

    def test_requires_complete_interface_and_prompt_array(self):
        manifest = json.loads(json.dumps(VALID_MANIFEST))
        del manifest["interface"]["shortDescription"]
        manifest["interface"]["defaultPrompt"] = "$ca-init"
        self.fx.write_manifest(manifest)
        errors = self.fx.errors()
        self.assertIn("plugin.json field `interface.shortDescription` must be a non-empty string", errors)
        self.assertIn("plugin.json field `interface.defaultPrompt` must be an array of strings", errors)

    def test_rejects_unquoted_colon_in_skill_scalar(self):
        self.fx.write_skill("---\nname: ca-init\ndescription: Initialize: safely.\n---\n")
        self.assertIn("skill `ca-init` frontmatter must be valid YAML",
                      self.fx.errors())

    def test_rejects_invalid_argument_hint_scalar(self):
        self.fx.write_skill("---\nname: ca-init\ndescription: Safe init.\nargument-hint: [path] | --force\n---\n")
        self.assertIn("skill `ca-init` frontmatter must be valid YAML",
                      self.fx.errors())

    def test_requires_marketplace_source_policy_and_category(self):
        stale = {"name": "codearbiter", "plugins": [{
            "name": "ca-codex", "source": "./plugins/ca-codex"}]}
        self.fx.write_marketplace(stale)
        errors = self.fx.errors()
        self.assertIn("marketplace plugin `ca-codex` source must be a local source object", errors)
        self.assertIn("marketplace plugin `ca-codex` policy.installation is required", errors)
        self.assertIn("marketplace plugin `ca-codex` policy.authentication is required", errors)
        self.assertIn("marketplace plugin `ca-codex` category is required", errors)


if __name__ == "__main__":
    unittest.main()
