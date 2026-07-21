#!/usr/bin/env python3
"""CI-owned, stdlib-only facts for exact Pi promotion candidates."""

from __future__ import annotations

import json
import re
import subprocess
import sys
from argparse import ArgumentParser
from dataclasses import dataclass
from datetime import date as calendar_date
from pathlib import Path
from typing import Any


SEMVER = re.compile(r"^(0|[1-9]\d*)\.(0|[1-9]\d*)\.(0|[1-9]\d*)$")
VERSION_LITERAL = re.compile(r'"(?P<version>[^"\r\n]+)"')
REPOSITORY = Path(__file__).resolve().parents[2]
OFFICIAL_PROMOTION_PATHS = frozenset({
    ".codearbiter/specs/pi-support.md",
    ".codearbiter/tech-stack.md",
    ".github/scripts/test_host_descriptors.py",
    ".github/scripts/test_pi_child_live.py",
    ".github/scripts/test_public_pi_docs.py",
    ".github/scripts/test_pi_package.py",
    ".github/scripts/test_pi_platform_contract.py",
    ".github/scripts/test_verify_pi_support.py",
    ".github/scripts/verify_pi_support.py",
    ".github/workflows/ci.yml",
    "README.md",
    "core/hosts.json",
    "core/surface/commands/doctor.md",
    "core/surface/includes/pi-host-notes.md",
    "docs/parity.md",
    "docs/pi-parity-testing.md",
    "plugins/ca-pi/tools/src/pi-api.d.ts",
    "site/src/content/docs/getting-started/compatibility.md",
    "site/src/content/docs/getting-started/pi.md",
    "site/src/content/docs/guides/troubleshooting.md",
    "plugins/ca-pi/CHANGELOG.md",
    "plugins/ca-pi/package.json",
    "plugins/ca-pi/tools/build.mjs",
    "plugins/ca-pi/tools/src/compatibility.ts",
    "plugins/ca-pi/tools/src/doctor.ts",
    "plugins/ca-pi/tools/test/compaction.test.ts",
    "plugins/ca-pi/tools/test/doctor.test.ts",
    "plugins/ca-pi/tools/test/package.test.ts",
    "plugins/ca-pi/tools/test/runner-isolation.test.ts",
})


class PromotionError(ValueError):
    """A candidate or CI-owned promotion configuration is invalid."""


@dataclass(frozen=True)
class PolicySource:
    compatibility_source: Path
    supported_versions_pattern: re.Pattern[str]
    node_floor_pattern: re.Pattern[str]


@dataclass(frozen=True)
class PromotionTarget:
    id: str
    path: Path
    kind: str
    before: str
    after: str
    occurrences: str


@dataclass(frozen=True)
class ReleaseSource:
    package_path: Path
    changelog_path: Path


@dataclass(frozen=True)
class Targets:
    policy: PolicySource
    targets: tuple[PromotionTarget, ...]
    release: ReleaseSource | None


@dataclass(frozen=True)
class SupportPolicy:
    minimum: str
    last_verified: str
    node_floor: tuple[int, int, int]

    @property
    def supported_versions(self) -> tuple[str, str]:
        return (self.minimum, self.last_verified)


@dataclass(frozen=True)
class Candidate:
    version: str


@dataclass(frozen=True)
class HelpDelta:
    removed: tuple[str, ...]
    added: tuple[str, ...]

    @property
    def incompatible(self) -> bool:
        return bool(self.removed)


def _semver_key(value: str) -> tuple[int, int, int]:
    match = SEMVER.fullmatch(value)
    if match is None:
        raise PromotionError(f"expected stable exact semver, got {value!r}")
    return tuple(int(part) for part in match.groups())


def _relative_path(value: object, field: str) -> Path:
    if not isinstance(value, str) or not value or "\x00" in value:
        raise PromotionError(f"{field} must be a non-empty relative path")
    path = Path(value)
    if path.is_absolute() or ".." in path.parts:
        raise PromotionError(f"{field} must stay within the repository")
    return path


def _pattern(value: object, field: str) -> re.Pattern[str]:
    if not isinstance(value, str) or not value:
        raise PromotionError(f"{field} must be a non-empty regex")
    try:
        return re.compile(value)
    except re.error as error:
        raise PromotionError(f"{field} is not a valid regex: {error}") from error


def load_targets(path: Path) -> Targets:
    try:
        document = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as error:
        raise PromotionError(f"cannot load promotion targets: {error}") from error
    if not isinstance(document, dict) or document.get("schema") != 1:
        raise PromotionError("promotion targets must use schema 1")
    policy = document.get("policy")
    if not isinstance(policy, dict):
        raise PromotionError("promotion targets require a policy object")
    versions = _pattern(policy.get("supported_versions_pattern"), "supported_versions_pattern")
    floor = _pattern(policy.get("node_floor_pattern"), "node_floor_pattern")
    if "versions" not in versions.groupindex:
        raise PromotionError("supported_versions_pattern must define a versions group")
    if set(floor.groupindex) != {"major", "minor", "patch"}:
        raise PromotionError("node_floor_pattern must define major, minor, and patch groups")
    raw_targets = document.get("targets")
    if not isinstance(raw_targets, list):
        raise PromotionError("promotion targets must contain a targets list")
    parsed_targets = []
    target_ids = set()
    allowed_kinds = {"policy", "ci", "generated", "current-doc", "release-metadata"}
    for item in raw_targets:
        if not isinstance(item, dict):
            raise PromotionError("every promotion target must be an object")
        target_id = item.get("id")
        if not isinstance(target_id, str) or not target_id:
            raise PromotionError("every promotion target needs a non-empty id")
        if target_id in target_ids:
            raise PromotionError(f"duplicate promotion target id: {target_id}")
        target_ids.add(target_id)
        kind = item.get("class")
        if kind not in allowed_kinds:
            raise PromotionError(f"{target_id}: unknown promotion target class")
        before, after = item.get("before"), item.get("after")
        if not isinstance(before, str) or not before or not isinstance(after, str) or not after:
            raise PromotionError(f"{target_id}: before and after must be non-empty strings")
        occurrences = item.get("occurrences", "one")
        if occurrences not in {"one", "all"}:
            raise PromotionError(f"{target_id}: occurrences must be one or all")
        parsed_targets.append(PromotionTarget(
            target_id,
            _relative_path(item.get("path"), f"{target_id}.path"),
            kind,
            before,
            after,
            occurrences,
        ))
    release = document.get("release")
    if release is None:
        parsed_release = None
    elif not isinstance(release, dict):
        raise PromotionError("release must be an object when present")
    else:
        parsed_release = ReleaseSource(
            _relative_path(release.get("package_path"), "release.package_path"),
            _relative_path(release.get("changelog_path"), "release.changelog_path"),
        )
    return Targets(
        policy=PolicySource(
            _relative_path(policy.get("compatibility_source"), "compatibility_source"),
            versions,
            floor,
        ),
        targets=tuple(parsed_targets),
        release=parsed_release,
    )


def read_policy(repo: Path, targets: Targets) -> SupportPolicy:
    source = (repo / targets.policy.compatibility_source).resolve()
    root = repo.resolve()
    if not source.is_relative_to(root):
        raise PromotionError("compatibility source escapes the repository")
    try:
        text = source.read_text(encoding="utf-8")
    except (OSError, UnicodeError) as error:
        raise PromotionError(f"cannot read compatibility source: {error}") from error
    versions_match = targets.policy.supported_versions_pattern.search(text)
    floor_match = targets.policy.node_floor_pattern.search(text)
    if versions_match is None or floor_match is None:
        raise PromotionError("compatibility source does not match declared policy patterns")
    versions = tuple(match.group("version") for match in VERSION_LITERAL.finditer(versions_match.group("versions")))
    if len(versions) != 2 or len(set(versions)) != 2:
        raise PromotionError("compatibility source must declare exactly two supported Pi versions")
    if any(SEMVER.fullmatch(version) is None for version in versions):
        raise PromotionError("compatibility source contains a non-stable Pi version")
    if _semver_key(versions[0]) >= _semver_key(versions[1]):
        raise PromotionError("supported Pi versions must be ordered minimum then last verified")
    return SupportPolicy(
        minimum=versions[0],
        last_verified=versions[1],
        node_floor=tuple(int(floor_match.group(name)) for name in ("major", "minor", "patch")),
    )


def parse_candidate(raw: str, policy: SupportPolicy) -> Candidate:
    candidate = raw.strip()
    if SEMVER.fullmatch(candidate) is None:
        raise PromotionError("candidate must be a stable exact semver")
    if _semver_key(candidate) <= _semver_key(policy.last_verified):
        raise PromotionError("candidate must be newer than the last verified Pi version")
    return Candidate(candidate)


def _render(template: str, policy: SupportPolicy, candidate: Candidate, target_id: str) -> str:
    try:
        return template.format(
            minimum=policy.minimum,
            last_verified=policy.last_verified,
            candidate=candidate.version,
        )
    except (KeyError, ValueError) as error:
        raise PromotionError(f"{target_id}: invalid promotion template: {error}") from error


def _target_path(repo: Path, target: PromotionTarget) -> Path:
    root = repo.resolve()
    path = (root / target.path).resolve()
    if not path.is_relative_to(root):
        raise PromotionError(f"{target.id}: target escapes the repository")
    return path


def _enforce_official_write_scope(repo: Path, targets: Targets) -> None:
    """Keep the checked-in recipe from becoming a general write primitive."""
    if repo.resolve() != REPOSITORY:
        return
    paths = {str(target.path).replace("\\", "/") for target in targets.targets}
    paths.add(str(targets.policy.compatibility_source).replace("\\", "/"))
    if targets.release is not None:
        paths.update({
            str(targets.release.package_path).replace("\\", "/"),
            str(targets.release.changelog_path).replace("\\", "/"),
        })
    unknown = sorted(paths - OFFICIAL_PROMOTION_PATHS)
    if unknown:
        raise PromotionError(f"promotion recipe declares unapproved write path: {unknown[0]}")


def _release_metadata(repo: Path, release: ReleaseSource, candidate: Candidate, date: str) -> tuple[Path, Path]:
    package_path = _target_path(repo, PromotionTarget("release-package", release.package_path, "release-metadata", "-", "-", "one"))
    changelog_path = _target_path(repo, PromotionTarget("release-changelog", release.changelog_path, "release-metadata", "-", "-", "one"))
    try:
        package = json.loads(package_path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as error:
        raise PromotionError(f"cannot read ca-pi package metadata: {error}") from error
    version = package.get("version") if isinstance(package, dict) else None
    if not isinstance(version, str) or SEMVER.fullmatch(version) is None:
        raise PromotionError("ca-pi package version must be a stable exact semver")
    major, minor, patch = _semver_key(version)
    next_version = f"{major}.{minor}.{patch + 1}"
    package["version"] = next_version
    package_path.write_text(json.dumps(package, indent=2) + "\n", encoding="utf-8", newline="\n")
    try:
        changelog = changelog_path.read_text(encoding="utf-8")
    except (OSError, UnicodeError) as error:
        raise PromotionError(f"cannot read ca-pi changelog: {error}") from error
    marker = "All notable changes to `ca-pi` are documented in this file."
    if changelog.count(marker) != 1:
        raise PromotionError("ca-pi changelog has no unique insertion marker")
    entry = (
        f"\n\n## [{next_version}] - {date}\n\n### Changed\n\n"
        f"- Promote the verified Pi host window through exact Pi {candidate.version}.\n"
    )
    changelog_path.write_text(changelog.replace(marker, marker + entry, 1), encoding="utf-8", newline="\n")
    return release.package_path, release.changelog_path


def apply_promotion(
    repo: Path,
    targets: Targets,
    candidate: Candidate,
    *,
    date: str = "1970-01-01",
) -> tuple[Path, ...]:
    _enforce_official_write_scope(repo, targets)
    policy = read_policy(repo, targets)
    changed = []
    for target in targets.targets:
        path = _target_path(repo, target)
        try:
            text = path.read_text(encoding="utf-8")
        except (OSError, UnicodeError) as error:
            raise PromotionError(f"{target.id}: cannot read target: {error}") from error
        before = _render(target.before, policy, candidate, target.id)
        after = _render(target.after, policy, candidate, target.id)
        count = text.count(before)
        if count == 0 or (target.occurrences == "one" and count != 1):
            raise PromotionError(f"{target.id}: declared promotion target occurrence mismatch")
        path.write_text(
            text.replace(before, after, -1 if target.occurrences == "all" else 1),
            encoding="utf-8",
            newline="\n",
        )
        changed.append(target.path)
    if targets.release is not None:
        changed.extend(_release_metadata(repo, targets.release, candidate, date))
    return tuple(changed)


def compare_help(baseline: tuple[str, ...], candidate: tuple[str, ...]) -> HelpDelta:
    baseline_set = set(baseline)
    candidate_set = set(candidate)
    return HelpDelta(
        removed=tuple(sorted(baseline_set - candidate_set)),
        added=tuple(sorted(candidate_set - baseline_set)),
    )


def normalize_help(raw: str) -> tuple[str, ...]:
    """Keep only public option signatures; never retain raw tool output."""
    entries = []
    for line in raw.splitlines():
        stripped = line.strip()
        if not stripped.startswith("-"):
            continue
        signature = re.split(r"\s{2,}", stripped, maxsplit=1)[0]
        if len(signature) <= 160:
            entries.append(signature)
    return tuple(sorted(set(entries)))


def capture_help(executable: str) -> tuple[str, ...]:
    """Run a bounded public-help probe and return its normalized surface."""
    try:
        completed = subprocess.run(
            [executable, "--help"],
            check=False,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=30,
        )
    except (OSError, subprocess.TimeoutExpired) as error:
        raise PromotionError(f"cannot capture Pi help: {type(error).__name__}") from error
    if completed.returncode != 0:
        raise PromotionError("Pi help probe failed")
    return normalize_help(completed.stdout)


def render_receipt(
    *,
    candidate: str,
    platform: str,
    contract: str,
    delta: HelpDelta | None = None,
) -> str:
    """Render a compact, secret-free failure receipt for summaries/artifacts."""
    lines = [
        f"candidate={candidate}",
        f"platform={platform}",
        f"contract={contract}",
    ]
    if delta is not None:
        lines.append("removed=" + ",".join(delta.removed[:20]))
        lines.append("added=" + ",".join(delta.added[:20]))
    return "\n".join(lines) + "\n"


def _main() -> int:
    parser = ArgumentParser(description=__doc__)
    parser.add_argument("--targets", type=Path, default=Path(".github/pi-promotion-targets.json"))
    subcommands = parser.add_subparsers(dest="command", required=True)
    subcommands.add_parser("policy")
    apply = subcommands.add_parser("apply")
    apply.add_argument("--candidate", required=True)
    help_probe = subcommands.add_parser("help")
    help_probe.add_argument("--executable", default="pi")
    arguments = parser.parse_args()
    targets = load_targets(arguments.targets)
    root = Path.cwd()
    if arguments.command == "policy":
        policy = read_policy(root, targets)
        print(json.dumps({"minimum": policy.minimum, "last_verified": policy.last_verified, "node_floor": policy.node_floor}))
        return 0
    if arguments.command == "apply":
        candidate = parse_candidate(arguments.candidate, read_policy(root, targets))
        changed = apply_promotion(root, targets, candidate, date=calendar_date.today().isoformat())
        print(json.dumps({"candidate": candidate.version, "changed": [str(path) for path in changed]}))
        return 0
    print(json.dumps({"help": capture_help(arguments.executable)}))
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(_main())
    except PromotionError as error:
        print(f"promotion-error: {error}", file=sys.stderr)
        raise SystemExit(2)
