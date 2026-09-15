#!/usr/bin/env python3
"""RA-11 route taxonomy and compatibility-body regression contract."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
import re
import unittest


REPO = Path(__file__).resolve().parents[2]
COMMANDS = REPO / "core" / "surface" / "commands"
REGISTRY = REPO / "core" / "surface" / "command-routes.json"

EXPECTED_SOURCE_ROUTES = frozenset({
    "add-dep", "adr", "adr-status", "audit", "btw", "checkpoint", "chore",
    "cleanup", "commands", "commit", "conflict", "context-check", "create-context",
    "debug", "decompose", "doctor", "feature", "fix", "init", "metrics",
    "new-skill", "override", "pr", "preview", "prune", "reconcile", "refactor",
    "release", "review", "spike", "sprint", "standup", "status", "statusline",
    "task", "threat-model", "tribunal", "watch",
})

EXPECTED_REPLACEMENTS = {
    "cleanup": ("pr", "pr --cleanup"),
    "context-check": ("status", "status drift"),
    "create-context": ("init", "init --brownfield"),
    "decompose": ("init", "init --greenfield"),
    "watch": ("pr", "pr --watch"),
}

EXPECTED_LEGACY_BODY_SHA256 = {
    "watch": "7e0fb0068195694ccdc8c5575a3d794a8b634710add06c5dbb17cb489b866c01",
    "cleanup": "2fc7f4836182ab9c5baa62810098753ce7f1047d229fcf03b724b0e3ceb1c45e",
    "decompose": "3f0d3108290e518038b105f22e73d7fee50fb33b849c2c13bcf86f0ccfed9d7a",
    "create-context": "aba430641baa3be0202dccd55c8782a591cf8899ed321f6469cca54fa2b7f423",
    "context-check": "1b4ac38f1bd4d5d8ce4d037d5cc070ea87691bde361c547a5cfc2bfd91948326",
}

EXPECTED_DEFAULT_BODY_SHA256 = {
    "pr": "068521a57a408bfaa9ca84f8ae6b5ccd5292c81e3030b9a7522add07122a7ad7",
    "init": "f6053db11c296e53afee8964f474602b43c60a92fd72addd28b90acc9e655fc9",
    "status": "0888f248ea6848d93201fa96ea167ae9575a55055b5518d58a74b323e6144f80",
}

NOTICE_RE = re.compile(
    r"<!-- catalog-compatibility-notice:start -->\n.*?"
    r"<!-- catalog-compatibility-notice:end -->\n\n",
    re.DOTALL,
)
MODES_RE = re.compile(
    r"<!-- catalog-command-modes:start -->\n.*?"
    r"<!-- catalog-command-modes:end -->\n\n",
    re.DOTALL,
)
STRICT_SEMVER_RE = re.compile(r"^(0|[1-9]\d*)\.(0|[1-9]\d*)\.(0|[1-9]\d*)$")

EXPECTED_FIRST_CONTAINING_RELEASES = {
    "claude": ("2.17.0", REPO / "plugins" / "ca" / ".claude-plugin" / "plugin.json"),
    "codex": ("0.9.0", REPO / "plugins" / "ca-codex" / ".codex-plugin" / "plugin.json"),
    "pi": ("0.10.0", REPO / "plugins" / "ca-pi" / "package.json"),
}


def command_body(slug: str) -> str:
    text = (COMMANDS / f"{slug}.md").read_text(encoding="utf-8")
    return text.split("\n---\n", 1)[1]


def argument_hint(slug: str) -> str:
    text = (COMMANDS / f"{slug}.md").read_text(encoding="utf-8")
    frontmatter = text.split("\n---\n", 1)[0]
    match = re.search(r"^argument-hint:\s*(.+)$", frontmatter, re.MULTILINE)
    if match is None:
        raise AssertionError(f"{slug}: missing argument-hint")
    value = match.group(1)
    return json.loads(value) if value.startswith('"') else value


def digest(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def strict_version(value: str) -> tuple[int, int, int]:
    match = STRICT_SEMVER_RE.fullmatch(value)
    if match is None:
        raise AssertionError(f"expected strict release version, got {value!r}")
    return tuple(int(part) for part in match.groups())


class CommandRouteCompatibilityTest(unittest.TestCase):
    def registry(self) -> dict:
        return json.loads(REGISTRY.read_text(encoding="utf-8"))

    def test_source_route_set_is_frozen_during_the_compatibility_window(self):
        actual = frozenset(path.stem for path in COMMANDS.glob("*.md"))
        self.assertEqual(actual, EXPECTED_SOURCE_ROUTES)

    def test_canonical_argument_hints_expose_modes_without_stealing_pr_titles(self):
        self.assertEqual(argument_hint("pr"), '["title"] | --watch [PR] | --cleanup')
        self.assertEqual(
            argument_hint("init"),
            "[--stage N] [--greenfield|--brownfield] | --check",
        )
        self.assertEqual(argument_hint("status"), "(none) | drift")

    def test_registry_has_the_verified_taxonomy_and_only_safe_replacements(self):
        commands = self.registry()["commands"]
        self.assertEqual(frozenset(commands), EXPECTED_SOURCE_ROUTES)
        counts = {
            visibility: sum(item["visibility"] == visibility for item in commands.values())
            for visibility in ("core", "advanced", "alias", "internal", "deprecated")
        }
        self.assertEqual(
            counts,
            {"core": 18, "advanced": 13, "alias": 5, "internal": 1, "deprecated": 1},
        )
        actual = {
            slug: (entry["canonical"], entry["replacement"])
            for slug, entry in commands.items()
            if entry["visibility"] == "alias"
        }
        self.assertEqual(actual, EXPECTED_REPLACEMENTS)
        for slug in ("checkpoint", "tribunal", "threat-model", "adr-status"):
            self.assertEqual(commands[slug]["visibility"], "advanced")
            self.assertEqual(commands[slug]["canonical"], slug)
        self.assertEqual(commands["add-dep"]["visibility"], "core")
        self.assertEqual(commands["add-dep"]["canonical"], "add-dep")

    def test_package_descriptions_do_not_freeze_inventory_counts(self):
        frozen_count = re.compile(
            r"\b\d+\s+(?:[a-z-]+\s+){0,3}(?:commands|skills|agents|routes|lanes)\b",
            re.IGNORECASE,
        )
        for manifest in (
            REPO / "plugins" / "ca" / ".claude-plugin" / "plugin.json",
            REPO / "plugins" / "ca-codex" / ".codex-plugin" / "plugin.json",
        ):
            with self.subTest(manifest=manifest.relative_to(REPO).as_posix()):
                description = json.loads(manifest.read_text(encoding="utf-8"))["description"]
                self.assertNotRegex(description, frozen_count)

    def test_ra11_governance_and_operator_prose_remains_unambiguous(self):
        plan = (
            REPO / ".codearbiter" / "plans" / "reaudit-ra11-catalog-rationalization.md"
        ).read_text(encoding="utf-8")
        spec = (
            REPO / ".codearbiter" / "specs" / "reaudit-ra11-catalog-rationalization.md"
        ).read_text(encoding="utf-8")
        sprint_log = (REPO / ".codearbiter" / "sprint-log.md").read_text(encoding="utf-8")
        commands = (REPO / "core" / "surface" / "COMMANDS.md").read_text(encoding="utf-8")
        status = command_body("status")

        self.assertIn("**Document role:** approved pre-execution plan", plan)
        self.assertIn("`python tools/build-surface.py --check`", spec)
        self.assertRegex(sprint_log, r"31 registry-canonical\s+routes")
        self.assertIn("Superseded by RA11-SD-02/04 final correction", sprint_log)
        self.assertNotIn("§6 redirect", commands)
        self.assertIn("Compatibility routes", commands)
        self.assertIn(
            "the opening summary and Hard gate below apply only to the no-argument snapshot",
            status,
        )

    def test_legacy_bodies_are_byte_frozen_except_for_one_migration_notice(self):
        for slug, expected in EXPECTED_LEGACY_BODY_SHA256.items():
            with self.subTest(slug=slug):
                body = command_body(slug)
                self.assertEqual(len(NOTICE_RE.findall(body)), 1)
                self.assertEqual(digest(NOTICE_RE.sub("", body)), expected)

    def test_default_canonical_bodies_are_byte_frozen_except_for_additive_modes(self):
        for slug, expected in EXPECTED_DEFAULT_BODY_SHA256.items():
            with self.subTest(slug=slug):
                body = command_body(slug)
                self.assertEqual(len(MODES_RE.findall(body)), 1)
                self.assertEqual(digest(MODES_RE.sub("", body)), expected)

    def test_mode_markers_and_notices_close_over_each_safe_replacement(self):
        commands = self.registry()["commands"]
        for legacy, (canonical, replacement) in EXPECTED_REPLACEMENTS.items():
            with self.subTest(legacy=legacy):
                mode = replacement.split(" ", 1)[1]
                marker = f"<!-- command-mode:{mode} legacy-route:{legacy} -->"
                self.assertIn(marker, command_body(canonical))
                tokenized = replacement.replace(canonical, f"{{{{CMD:{canonical}}}}}", 1)
                notice = NOTICE_RE.search(command_body(legacy))
                self.assertIsNotNone(notice)
                self.assertIn(tokenized, notice.group(0))
                self.assertEqual(commands[canonical]["legacyRoutes"].count(legacy), 1)
                self.assertIn(mode, commands[canonical]["modes"])

    def test_compatibility_clock_starts_only_on_independent_publication(self):
        policy = self.registry()["compatibility"]
        self.assertEqual(policy["clockStarts"], "confirmed-non-draft-github-release")
        self.assertEqual(policy["removalRequires"], "separately-approved-major")
        self.assertEqual(
            policy["targets"],
            {
                "claude": {
                    "publishedWithoutMetadata": "2.16.0",
                    "firstContainingRelease": "2.17.0",
                    "retainThrough": "2.x",
                    "earliestRemoval": "3.0.0",
                },
                "codex": {
                    "publishedWithoutMetadata": "0.8.0",
                    "firstContainingRelease": "0.9.0",
                    "retainThrough": "0.x",
                    "earliestRemoval": "1.0.0",
                },
                "pi": {
                    "publishedWithoutMetadata": "0.9.0",
                    "firstContainingRelease": "0.10.0",
                    "retainThrough": "0.x",
                    "earliestRemoval": "1.0.0",
                },
            },
        )

    def test_first_containing_declarations_are_stable_when_manifests_advance(self):
        policy = self.registry()["compatibility"]["targets"]
        for target, (expected, manifest_path) in EXPECTED_FIRST_CONTAINING_RELEASES.items():
            with self.subTest(target=target):
                metadata = policy[target]
                manifest_version = json.loads(manifest_path.read_text(encoding="utf-8"))["version"]
                self.assertEqual(metadata["firstContainingRelease"], expected)
                self.assertGreaterEqual(strict_version(manifest_version), strict_version(expected))


if __name__ == "__main__":
    unittest.main(verbosity=2)
