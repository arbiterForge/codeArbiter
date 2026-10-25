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

HISTORICAL_SOURCE_ROUTES = frozenset({
    "add-dep", "adr", "adr-status", "audit", "btw", "checkpoint", "chore",
    "cleanup", "commands", "commit", "conflict", "context-check", "create-context",
    "debug", "decompose", "doctor", "feature", "fix", "init", "metrics",
    "new-skill", "override", "pr", "preview", "prune", "reconcile", "refactor",
    "release", "review", "spike", "sprint", "standup", "status", "statusline",
    "task", "threat-model", "tribunal", "watch",
})

# Maintainer-approved removals: new-skill on 2026-09-25; btw, commands,
# metrics and preview on 2026-10-23. Every other route remains frozen.
EXPECTED_SOURCE_ROUTES = HISTORICAL_SOURCE_ROUTES - {
    "new-skill", "btw", "commands", "metrics", "preview",
}

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

# The init body includes T-020's bounded passive inspection before the normal
# scaffold procedure. T-027 adds its refresh pointer inside the additive mode.
# PR #983 intentionally updates the status body to distinguish DONE progress,
# verification and actual user stops. AssistiveCallerProjectionTest checks that
# behavior across all three hosts; routing and additive modes remain unchanged.
EXPECTED_DEFAULT_BODY_SHA256 = {
    "pr": "068521a57a408bfaa9ca84f8ae6b5ccd5292c81e3030b9a7522add07122a7ad7",
    "init": "14a38ed019243f3998b8f2f37b671b0c792f75f0052e0ef0e897903e2677e8d2",
    "status": "5e10b6af44eeb4257329a1dbeeadf83b04e342cbc7e7fdb216b29147d71fd2a9",
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


# PR #854: reviewed single-owner composition, not route retirement. Historical
# wrapper fingerprints above remain the original baseline; composed workflows
# preserve the entire owner preflight-through-hard-rules body instead.
COMPOSED_OWNERS = {"cleanup": "post-merge-cleanup", "context-check": "context-check",
                   "pr": "finishing-a-development-branch", "create-context": "context-creation",
                   "decompose": "decompose", "release": "release"}
OWNER_OPERATIONAL_SHA256 = {'cleanup': 'bbeed4efed778bb4f6d85149d70772ede5177dc0ca9d09a4edd072bdda69645d', 'context-check': '06be2a22d9b9ddc28e4826fed24b9d6edad44deab2c241a5e20c02c41d343954'}
# PR #871 delivers the reviewed bounded context-creation owner, retaining its
# initialized lock and routing refresh through the existing context-check owner.
OWNER_OPERATIONAL_SHA256.update({
    'create-context': '84ae53fb9d0ee29103bffa87d8a36d83b4433ba2ca52535b72d0c73ddee13e92',
    'decompose': 'e5952b1ac6cf42a77abbd9048c75a3918d01d413dfa4ff790edb967a688e70a0',
})

# PR #983 extends the reviewed assistive context lifecycle to initialization and
# refresh. Keep exact owner fingerprints as well as the historical route and
# compatibility clocks; test_context_workflow.py checks the new behavior.
EXPECTED_DEFAULT_BODY_SHA256.update({
    'init': '3161379ff0803d7c412fdadc9887e2692caf84ae03efd5c23a75461a60b44fc3',
})
OWNER_OPERATIONAL_SHA256.update({
    'create-context': '406291d45c2f8566d91db595d6c4f97ba8324adfadb6fac6778f19e170e015b1',
    'context-check': '77a8eb3a8500f46ebd158bd97e356c0564f8a8f8baccbfdaad65969490a3b17a',
})

# #1023 makes HTML knowledge the default. The create-context and decompose
# entries now carry the HTML procedure; the reviewed Markdown procedures move
# byte-for-byte into each owner's references/markdown-format.md and keep their
# PR #983 fingerprints. init gains the --format choice and .gitattributes.
LEGACY_FORMAT_REFERENCE_SHA256 = {
    'create-context': ('context-creation', '## Pre-flight\n',
                       '406291d45c2f8566d91db595d6c4f97ba8324adfadb6fac6778f19e170e015b1'),
    'decompose': ('decompose', '## 1. Inspect and resume\n',
                  'e5952b1ac6cf42a77abbd9048c75a3918d01d413dfa4ff790edb967a688e70a0'),
}
OWNER_OPERATIONAL_SHA256.update({
    'create-context': '53c7517302b6c9298a0d3167873cd597544431faf5f0b0be563fca2318a45eb7',
    'decompose': '548fb7672659664761d7b0236a249e3334691e904cf30ee06c6df37e11377a6a',
})
# PR #1030 adds the explicit section checklist to the HTML conversion owner.
# The Markdown procedures in references/markdown-format.md retain their pins.
OWNER_OPERATIONAL_SHA256.update({
    'create-context': 'a0f7c065ba6355291244208ce8a4fb7a498b93c1113a85f9ce624d0a3a601353',
    'decompose': 'de754accbc1bb7cae4f02e7ef710a180856d7589f9aa502c5bc38d1f7f5081ce',
})
EXPECTED_DEFAULT_BODY_SHA256.update({
    'init': '08746b4ddc731e134857c288fd321ed8072fec5408e05c147001614cc0f9c46d',
})

# The 2026-10-23 removal of /btw rewrites status's "When NOT to use" pointer
# for a specific question; nothing else in the body changes.
EXPECTED_DEFAULT_BODY_SHA256.update({
    'status': 'e579801e56c8e36fa6c1ab6db7148f02e999ca27180f3b73ffa4773dd12e0d23',
})

def command_source(slug: str) -> str:
    text = (COMMANDS / f"{slug}.md").read_text(encoding="utf-8")
    if slug in COMPOSED_OWNERS:
        owner = COMPOSED_OWNERS[slug]
        if text != "{{SKILL_ENTRY:" + owner + "}}\n":
            raise AssertionError(f"{slug}: expected the reviewed single owner")
        return (REPO / "core/surface/skills" / owner / "SKILL.md").read_text(encoding="utf-8")
    return text

def command_body(slug: str) -> str:
    text = command_source(slug)
    return text.split("\n---\n", 1)[1]


def argument_hint(slug: str) -> str:
    text = command_source(slug)
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

    def test_source_route_set_is_frozen_except_explicit_retirement(self):
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
            {"core": 17, "advanced": 10, "alias": 5, "internal": 1, "deprecated": 0},
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
                if slug in OWNER_OPERATIONAL_SHA256:
                    heading = ("## 1. Inspect and resume\n" if slug == "decompose"
                               else "## Pre-flight\n")
                    self.assertEqual(digest(body.split(heading, 1)[1]),
                                     OWNER_OPERATIONAL_SHA256[slug])
                    if slug in ('cleanup', 'context-check'):
                        self.assertIn("neither stages nor commits", " ".join(body.split()))
                else:
                    self.assertEqual(digest(NOTICE_RE.sub("", body)), expected)

    def test_markdown_format_procedures_stay_byte_frozen_in_their_references(self):
        for slug, (owner, heading, expected) in LEGACY_FORMAT_REFERENCE_SHA256.items():
            with self.subTest(slug=slug):
                reference = (REPO / "core" / "surface" / "skills" / owner / "references"
                             / "markdown-format.md").read_text(encoding="utf-8")
                self.assertEqual(digest(reference.split(heading, 1)[1]), expected)
                self.assertIn("references/markdown-format.md", command_body(slug))

    def test_default_canonical_bodies_are_byte_frozen_except_for_additive_modes(self):
        for slug, expected in EXPECTED_DEFAULT_BODY_SHA256.items():
            with self.subTest(slug=slug):
                body = command_body(slug)
                self.assertEqual(len(MODES_RE.findall(body)), 1)
                if slug == "pr":
                    procedure = body.split("### Open-PR procedure\n", 1)[1]
                    procedure = procedure[procedure.index("1. **Confirm"):].split("\n## Phase 4", 1)[0].strip()
                    self.assertEqual(digest(procedure), "bad0d9f173db7ef0c7fe5ff9ddb2aed6fc5176a8fd82d59110fe27e75cd51af0")
                    self.assertNotIn("{{PLUGIN_ROOT}}/commands/pr.md", body)
                else:
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
        self.assertEqual(policy["removalRequires"], "minor-release-with-changelog-notice")
        self.assertEqual(
            policy["targets"],
            {
                "claude": {
                    "publishedWithoutMetadata": "2.16.0",
                    "firstContainingRelease": "2.17.0",
                },
                "codex": {
                    "publishedWithoutMetadata": "0.8.0",
                    "firstContainingRelease": "0.9.0",
                },
                "pi": {
                    "publishedWithoutMetadata": "0.9.0",
                    "firstContainingRelease": "0.10.0",
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
