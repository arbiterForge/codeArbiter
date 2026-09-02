#!/usr/bin/env python3
"""RA-11 route taxonomy and compatibility-body regression contract."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
import re
import subprocess
import tempfile
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


def release_tag_exists(tag: str, repo: Path = REPO) -> bool:
    return subprocess.run(
        ["git", "show-ref", "--verify", "--quiet", f"refs/tags/{tag}"],
        cwd=repo,
        check=False,
    ).returncode == 0


def release_tag_contains_registry(tag: str, repo: Path = REPO) -> bool:
    commit = subprocess.run(
        ["git", "rev-parse", "--verify", f"refs/tags/{tag}^{{commit}}"],
        cwd=repo,
        check=True,
        capture_output=True,
        text=True,
    ).stdout.strip()
    result = subprocess.run(
        ["git", "ls-tree", "--name-only", commit, "--", "core/surface/command-routes.json"],
        cwd=repo,
        check=True,
        capture_output=True,
        text=True,
    )
    return result.stdout.splitlines() == ["core/surface/command-routes.json"]


def strict_version(value: str) -> tuple[int, int, int]:
    match = STRICT_SEMVER_RE.fullmatch(value)
    if match is None:
        raise AssertionError(f"expected strict release version, got {value!r}")
    return tuple(int(part) for part in match.groups())


def first_release_containing_registry(
    prefix: str,
    baseline: str,
    repo: Path = REPO,
) -> str | None:
    baseline_version = strict_version(baseline)
    result = subprocess.run(
        ["git", "tag", "--list", f"{prefix}*"],
        cwd=repo,
        check=True,
        capture_output=True,
        text=True,
    )
    candidates: list[tuple[tuple[int, int, int], str]] = []
    for tag in result.stdout.splitlines():
        version_text = tag.removeprefix(prefix)
        if not STRICT_SEMVER_RE.fullmatch(version_text):
            continue
        version = strict_version(version_text)
        if version > baseline_version and release_tag_contains_registry(tag, repo):
            candidates.append((version, version_text))
    return min(candidates)[1] if candidates else None


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
        self.assertEqual(policy["clockStarts"], "published-release")
        self.assertEqual(policy["removalRequires"], "separately-approved-major")
        self.assertEqual(
            policy["targets"],
            {
                "claude": {
                    "publishedWithoutMetadata": "2.16.0",
                    "firstContainingRelease": None,
                    "retainThrough": "2.x",
                    "earliestRemoval": "3.0.0",
                },
                "codex": {
                    "publishedWithoutMetadata": "0.8.0",
                    "firstContainingRelease": None,
                    "retainThrough": "0.x",
                    "earliestRemoval": "1.0.0",
                },
                "pi": {
                    "publishedWithoutMetadata": "0.9.0",
                    "firstContainingRelease": None,
                    "retainThrough": "0.x",
                    "earliestRemoval": "1.0.0",
                },
            },
        )

    def test_compatibility_metadata_matches_release_tag_history(self):
        policy = self.registry()["compatibility"]["targets"]
        for target, prefix in {
            "claude": "v",
            "codex": "ca-codex-v",
            "pi": "ca-pi-v",
        }.items():
            with self.subTest(target=target):
                metadata = policy[target]
                baseline = metadata["publishedWithoutMetadata"]
                baseline_tag = f"{prefix}{baseline}"
                self.assertTrue(release_tag_exists(baseline_tag))
                self.assertFalse(release_tag_contains_registry(baseline_tag))
                self.assertEqual(
                    first_release_containing_registry(prefix, baseline),
                    metadata["firstContainingRelease"],
                )

    def test_release_history_detector_finds_first_later_tag_with_registry(self):
        with tempfile.TemporaryDirectory() as temporary:
            repo = Path(temporary)
            subprocess.run(["git", "init", "--quiet"], cwd=repo, check=True)
            subprocess.run(["git", "config", "user.name", "test"], cwd=repo, check=True)
            subprocess.run(["git", "config", "user.email", "test@example.invalid"], cwd=repo, check=True)
            (repo / "README.md").write_text("baseline\n", encoding="utf-8")
            subprocess.run(["git", "add", "README.md"], cwd=repo, check=True)
            subprocess.run(["git", "commit", "--quiet", "-m", "baseline"], cwd=repo, check=True)
            subprocess.run(["git", "tag", "v1.0.0"], cwd=repo, check=True)
            (repo / "core" / "surface").mkdir(parents=True)
            (repo / "core" / "surface" / "command-routes.json").write_text("{}\n", encoding="utf-8")
            subprocess.run(["git", "add", "core/surface/command-routes.json"], cwd=repo, check=True)
            subprocess.run(["git", "commit", "--quiet", "-m", "add registry"], cwd=repo, check=True)
            subprocess.run(["git", "tag", "v1.1.0"], cwd=repo, check=True)

            self.assertEqual(
                first_release_containing_registry("v", "1.0.0", repo=repo),
                "1.1.0",
            )

    def test_release_history_detector_rejects_non_commit_tag(self):
        with tempfile.TemporaryDirectory() as temporary:
            repo = Path(temporary)
            subprocess.run(["git", "init", "--quiet"], cwd=repo, check=True)
            blob = subprocess.run(
                ["git", "hash-object", "-w", "--stdin"],
                cwd=repo,
                check=True,
                capture_output=True,
                input="not a commit\n",
                text=True,
            ).stdout.strip()
            subprocess.run(
                ["git", "update-ref", "refs/tags/v1.1.0", blob],
                cwd=repo,
                check=True,
            )

            with self.assertRaises(subprocess.CalledProcessError):
                release_tag_contains_registry("v1.1.0", repo)

    def test_release_history_detector_qualifies_tag_when_branch_name_conflicts(self):
        with tempfile.TemporaryDirectory() as temporary:
            repo = Path(temporary)
            subprocess.run(["git", "init", "--quiet"], cwd=repo, check=True)
            subprocess.run(["git", "config", "user.name", "test"], cwd=repo, check=True)
            subprocess.run(["git", "config", "user.email", "test@example.invalid"], cwd=repo, check=True)
            (repo / "README.md").write_text("baseline\n", encoding="utf-8")
            subprocess.run(["git", "add", "README.md"], cwd=repo, check=True)
            subprocess.run(["git", "commit", "--quiet", "-m", "baseline"], cwd=repo, check=True)
            baseline_commit = subprocess.run(
                ["git", "rev-parse", "HEAD"], cwd=repo, check=True, capture_output=True, text=True
            ).stdout.strip()
            subprocess.run(["git", "tag", "v1.0.0"], cwd=repo, check=True)
            (repo / "core" / "surface").mkdir(parents=True)
            (repo / "core" / "surface" / "command-routes.json").write_text("{}\n", encoding="utf-8")
            subprocess.run(["git", "add", "core/surface/command-routes.json"], cwd=repo, check=True)
            subprocess.run(["git", "commit", "--quiet", "-m", "add registry"], cwd=repo, check=True)
            subprocess.run(["git", "tag", "v1.1.0"], cwd=repo, check=True)
            subprocess.run(["git", "branch", "v1.1.0", baseline_commit], cwd=repo, check=True)

            self.assertEqual(
                first_release_containing_registry("v", "1.0.0", repo=repo),
                "1.1.0",
            )


if __name__ == "__main__":
    unittest.main(verbosity=2)
