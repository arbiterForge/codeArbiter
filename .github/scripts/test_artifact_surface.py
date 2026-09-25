#!/usr/bin/env python3
"""Artifact-engine public-surface and startup-context closure checks."""

from __future__ import annotations

import hashlib
import json
import pathlib
import re
import subprocess
import tempfile
import unittest


ROOT = pathlib.Path(__file__).resolve().parents[2]
INVENTORY_PATH = ROOT / "docs" / "artifacts" / "consumer-inventory.json"
POLICY_BASELINE_REVISION = "4c1fe026d2eb26ea842308d312f7f1250d835a51"
POLICY_STARTUP_FIXTURES = (
    "core/surface/arbiter.md",
    "core/pysrc/session-start.py",
)
# Historical artifact-policy baseline is immutable. PR843 separately reviewed
# the resident routing body; do not freeze all future policy to the pilot.
STARTUP_CONTENT_SHA256 = {
    "core/surface/arbiter.md": "4bbe2beb49d1026271025d2553709728af1b300a9fdabd7c9d80978925faeb14",
}

ARTIFACT_GUIDANCE_PATHS = (
    "core/surface/includes/artifacts.md",
    "plugins/ca/includes/artifacts.md",
    "plugins/ca-codex/includes/artifacts.md",
    "plugins/ca-pi/includes/artifacts.md",
)


def load_inventory() -> dict:
    with INVENTORY_PATH.open(encoding="utf-8") as handle:
        return json.load(handle)


def git_bytes(revision: str, path: str) -> bytes:
    result = subprocess.run(
        ["git", "show", f"{revision}:{path}"],
        cwd=ROOT,
        capture_output=True,
        check=False,
    )
    if result.returncode != 0:
        raise AssertionError(result.stderr.decode(errors="replace"))
    return result.stdout


def tree_names(revision: str, path: str, suffix: str) -> list[str]:
    result = subprocess.run(
        ["git", "ls-tree", "--name-only", f"{revision}:{path}"],
        cwd=ROOT,
        text=True,
        capture_output=True,
        check=False,
    )
    if result.returncode != 0:
        raise AssertionError(result.stderr)
    return sorted(
            pathlib.PurePosixPath(item).stem
        for item in result.stdout.splitlines()
        if item.endswith(suffix) and pathlib.PurePosixPath(item).name != "INDEX.md"
    )


def persistent_tool_names(text: str) -> list[str]:
    return sorted(
        set(re.findall(r'name:\s*["\'](codearbiter_[a-z0-9_]+)["\']', text))
    )


def surface_at_revision(revision: str | None = None) -> dict[str, list[str]]:
    if revision:
        routes = json.loads(
            git_bytes(revision, "core/surface/command-routes.json").decode()
        )
        agents = tree_names(revision, "core/surface/agents", ".md")
        skills = sorted(
            pathlib.PurePosixPath(item).name
            for item in subprocess.check_output(
                [
                    "git",
                    "ls-tree",
                    "-d",
                    "--name-only",
                    f"{revision}:core/surface/skills",
                ],
                cwd=ROOT,
                text=True,
            ).splitlines()
        )
        pi_paths = subprocess.check_output(
            ["git", "ls-tree", "-r", "--name-only", revision, "plugins/ca-pi/tools/src"],
            cwd=ROOT,
            text=True,
        ).splitlines()
        pi_source_paths = [path for path in pi_paths if path.endswith(".ts")]
        pi_sources = "\n".join(
            git_bytes(revision, path).decode() for path in pi_source_paths
        )
    else:
        routes = json.loads(
            (ROOT / "core" / "surface" / "command-routes.json").read_text(
                encoding="utf-8"
            )
        )
        agents = sorted(
            path.stem
            for path in (ROOT / "core" / "surface" / "agents").glob("*.md")
            if path.name != "INDEX.md"
        )
        skills = sorted(
            path.name
            for path in (ROOT / "core" / "surface" / "skills").iterdir()
            if path.is_dir()
        )
        pi_sources = "\n".join(
            path.read_text(encoding="utf-8")
            for path in sorted(
                (ROOT / "plugins" / "ca-pi" / "tools" / "src").rglob("*.ts")
            )
        )
    return {
        "commands": sorted(routes["commands"]),
        "agents": agents,
        "top_level_skills": skills,
        "persistent_tools": persistent_tool_names(pi_sources),
    }


def surface_delta(expected: dict[str, list[str]], actual: dict[str, list[str]]) -> list[str]:
    findings: list[str] = []
    for category in sorted(expected):
        wanted = set(expected[category])
        found = set(actual.get(category, []))
        for name in sorted(found - wanted):
            findings.append(f"added {category}: {name}")
        for name in sorted(wanted - found):
            findings.append(f"removed {category}: {name}")
    return findings


def surface_digest(surface: dict[str, list[str]]) -> str:
    encoded = json.dumps(surface, sort_keys=True, separators=(",", ":")).encode()
    return hashlib.sha256(encoded).hexdigest()


def eager_markers(text: str, forbidden: list[str]) -> list[str]:
    lowered = text.lower()
    return sorted(marker for marker in forbidden if marker.lower() in lowered)


def reviewed_surface(baseline: dict) -> dict[str, list[str]]:
    """The immutable historical baseline plus each explicitly reviewed addition."""
    surface = {key: list(value) for key, value in baseline["registrations"].items()}
    for addition in baseline.get("reviewed_additions", []):
        surface[addition["category"]] = sorted(surface[addition["category"]] + [addition["name"]])
    return surface


class ArtifactSurfaceTest(unittest.TestCase):
    def setUp(self) -> None:
        self.inventory = load_inventory()
        self.baseline = self.inventory["public_surface_baseline"]
        self.reviewed = reviewed_surface(self.baseline)

    def test_no_added_discovery(self) -> None:
        self.assertEqual(self.inventory["baseline_revision"], POLICY_BASELINE_REVISION)
        historical = surface_at_revision(POLICY_BASELINE_REVISION)
        self.assertEqual(self.baseline["registrations"], historical)
        self.assertEqual(
            surface_digest(historical),
            self.baseline["registration_sha256"],
        )
        self.assertEqual(
            surface_delta(self.reviewed, surface_at_revision()),
            [],
        )

    def test_reviewed_additions_are_named_and_justified(self) -> None:
        additions = self.baseline.get("reviewed_additions", [])
        self.assertEqual(
            [(item["category"], item["name"]) for item in additions],
            [("agents", "authority-reviewer")],
        )
        for item in additions:
            self.assertEqual(
                set(item), {"category", "name", "hosts", "invocation", "rationale", "approved_by"}
            )
            self.assertTrue(all(isinstance(item[key], (str, list)) and item[key] for key in item))

    def test_pi_prompt_approval_is_explicitly_unsupported(self) -> None:
        warning = (
            "Pi 0.84.1 exposes no\n"
            "pre-model event carrying the user's exact prompt, so under Pi do not arm this\n"
            "adapter"
        )
        for relative in ARTIFACT_GUIDANCE_PATHS:
            text = (ROOT / relative).read_text(encoding="utf-8")
            self.assertIn(warning, text, relative)

    def test_authority_guidance_names_the_codex_only_production_seam(self) -> None:
        for relative in ARTIFACT_GUIDANCE_PATHS:
            text = (ROOT / relative).read_text(encoding="utf-8")
            self.assertIn("Verification and review authority below is supported on Codex and Claude Code", text, relative)
            self.assertNotIn("Codex-only", text, relative)
            self.assertNotIn("corroborated exit 0", text, relative)
        host_notes = (ROOT / "core/surface/includes/codex-host-notes.md").read_text(encoding="utf-8")
        self.assertIn("`verify` command shown in `artifacts.md`", host_notes)
        self.assertNotIn("wrapper command returned by the", host_notes)

    def test_policy_baseline_is_in_candidate_history(self) -> None:
        result = subprocess.run(
            [
                "git",
                "merge-base",
                "--is-ancestor",
                POLICY_BASELINE_REVISION,
                "HEAD",
            ],
            cwd=ROOT,
            capture_output=True,
            check=False,
        )
        self.assertEqual(
            result.returncode,
            0,
            "policy baseline must be reachable from the candidate history",
        )

    def test_added_spec_command_is_named(self) -> None:
        candidate = surface_at_revision()
        candidate["commands"] = sorted(candidate["commands"] + ["spec"])
        self.assertEqual(
            surface_delta(self.reviewed, candidate),
            ["added commands: spec"],
        )

    def test_added_persistent_artifact_tool_is_named(self) -> None:
        candidate = surface_at_revision()
        candidate["persistent_tools"] = sorted(
            candidate["persistent_tools"] + ["codearbiter_artifact"]
        )
        self.assertEqual(
            surface_delta(self.reviewed, candidate),
            ["added persistent_tools: codearbiter_artifact"],
        )

    def test_nested_persistent_tool_source_is_discovered(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = pathlib.Path(temporary)
            nested = root / "nested" / "registration.ts"
            nested.parent.mkdir()
            nested.write_text('name: "codearbiter_artifact"', encoding="utf-8")
            sources = "\n".join(
                path.read_text(encoding="utf-8")
                for path in sorted(root.rglob("*.ts"))
            )
            self.assertEqual(persistent_tool_names(sources), ["codearbiter_artifact"])

    def test_startup_fixtures_match_baseline(self) -> None:
        self.assertEqual(
            tuple(item["path"] for item in self.baseline["startup_fixtures"]),
            POLICY_STARTUP_FIXTURES,
        )
        for fixture in self.baseline["startup_fixtures"]:
            path = ROOT / fixture["path"]
            historical_digest = hashlib.sha256(
                git_bytes(POLICY_BASELINE_REVISION, fixture["path"])
            ).hexdigest()
            self.assertEqual(fixture["sha256"], historical_digest, fixture["path"])
            digest = hashlib.sha256(path.read_bytes()).hexdigest()
            expected_digest = STARTUP_CONTENT_SHA256.get(fixture["path"], fixture["sha256"])
            self.assertEqual(digest, expected_digest, fixture["path"])

    def test_reviewed_startup_digest_is_narrow_and_history_independent(self) -> None:
        # A golden content digest survives a squash merge; a feature-branch
        # commit object or ancestry requirement would not. Historical baseline
        # provenance is still checked separately by test_startup_fixtures_match_baseline.
        self.assertEqual(set(STARTUP_CONTENT_SHA256), {"core/surface/arbiter.md"})
        for path, expected in STARTUP_CONTENT_SHA256.items():
            self.assertIn(path, POLICY_STARTUP_FIXTURES)
            self.assertRegex(expected, r"^[0-9a-f]{64}$")
            self.assertEqual(hashlib.sha256((ROOT / path).read_bytes()).hexdigest(), expected)

    def test_reviewed_startup_content_still_rejects_drift_and_eager_schema(self) -> None:
        for path, expected in STARTUP_CONTENT_SHA256.items():
            approved = (ROOT / path).read_bytes()
            self.assertNotEqual(hashlib.sha256(approved + b"\n").hexdigest(), expected)
            forbidden = self.baseline["forbidden_startup_markers"]
            self.assertTrue(forbidden)
            seeded = approved.decode() + "\n" + forbidden[0] + "\n"
            self.assertTrue(eager_markers(seeded, forbidden))

    def test_startup_fixtures_do_not_eager_load_artifact_content(self) -> None:
        forbidden = self.baseline["forbidden_startup_markers"]
        for fixture in self.baseline["startup_fixtures"]:
            path = ROOT / fixture["path"]
            self.assertEqual(
                eager_markers(path.read_text(encoding="utf-8"), forbidden),
                [],
                fixture["path"],
            )

    def test_eager_schema_negative_control(self) -> None:
        text = "startup context: core/artifacts/schemas/spec.schema.json"
        self.assertEqual(
            eager_markers(text, self.baseline["forbidden_startup_markers"]),
            ["core/artifacts/schemas/spec.schema.json"],
        )


if __name__ == "__main__":
    unittest.main(verbosity=2)
