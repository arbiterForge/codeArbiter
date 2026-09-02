#!/usr/bin/env python3
"""Validate and observe RA-11 first-containing Release declarations.

Declaration checks are repository-local and hermetic. Observation consumes raw
`gh api --include` responses captured by the release workflow. Pre-publication
lookup consumes the complete authenticated `gh api --paginate --slurp` Release
list, because GitHub's by-tag endpoint exposes published Releases only and can
hide a draft behind 404. This module never opens the network. A Git tag is
install evidence, not publication evidence.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import re
import subprocess
import sys
from typing import NamedTuple


REPO = Path(__file__).resolve().parents[2]
REGISTRY_PATH = Path("core/surface/command-routes.json")
TARGETS = {
    "claude": {
        "manifest": Path("plugins/ca/.claude-plugin/plugin.json"),
        "tagPrefix": "v",
    },
    "codex": {
        "manifest": Path("plugins/ca-codex/.codex-plugin/plugin.json"),
        "tagPrefix": "ca-codex-v",
    },
    "pi": {
        "manifest": Path("plugins/ca-pi/package.json"),
        "tagPrefix": "ca-pi-v",
    },
}
SEMVER = re.compile(r"^(0|[1-9]\d*)\.(0|[1-9]\d*)\.(0|[1-9]\d*)$")
HTTP_STATUS = re.compile(r"^HTTP/\S+\s+(\d{3})(?:\s|$)")
COMMIT = re.compile(r"^[0-9a-f]{40}$")


class ContractError(ValueError):
    """The committed declaration or supplied evidence is invalid."""


class Declaration(NamedTuple):
    target: str
    version: str
    tag: str
    manifest: Path
    manifest_version: str


def strict_version(value: object, where: str) -> tuple[int, int, int]:
    match = SEMVER.fullmatch(value) if isinstance(value, str) else None
    if match is None:
        raise ContractError(f"{where} must be a strict semantic version")
    return tuple(int(part) for part in match.groups())


def validate_target_declaration(
    target: str,
    metadata: object,
    manifest_version: object,
    tag_prefix: str,
    manifest: Path = Path("manifest.json"),
) -> Declaration:
    where = f"compatibility.targets.{target}"
    required = {
        "publishedWithoutMetadata",
        "firstContainingRelease",
        "retainThrough",
        "earliestRemoval",
    }
    if not isinstance(metadata, dict) or set(metadata) != required:
        raise ContractError(f"{where} must contain exactly {sorted(required)!r}")
    baseline = strict_version(metadata["publishedWithoutMetadata"], f"{where}.publishedWithoutMetadata")
    first_text = metadata["firstContainingRelease"]
    first = strict_version(first_text, f"{where}.firstContainingRelease")
    current = strict_version(manifest_version, f"{manifest}.version")
    if first <= baseline:
        raise ContractError(f"{where}.firstContainingRelease must follow the published baseline")
    if current < first:
        raise ContractError(
            f"{manifest}.version {manifest_version} is behind declared first-containing "
            f"release {first_text}"
        )
    return Declaration(target, first_text, f"{tag_prefix}{first_text}", manifest, manifest_version)


def load_declarations(repo: Path) -> tuple[Declaration, ...]:
    try:
        registry = json.loads((repo / REGISTRY_PATH).read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        raise ContractError(f"cannot read {REGISTRY_PATH}: {error}") from error
    compatibility = registry.get("compatibility") if isinstance(registry, dict) else None
    if not isinstance(compatibility, dict):
        raise ContractError("registry compatibility must be an object")
    if compatibility.get("clockStarts") != "confirmed-non-draft-github-release":
        raise ContractError(
            "compatibility.clockStarts must be 'confirmed-non-draft-github-release'"
        )
    targets = compatibility.get("targets")
    if not isinstance(targets, dict) or set(targets) != set(TARGETS):
        raise ContractError(f"compatibility.targets must be exactly {sorted(TARGETS)!r}")

    declarations = []
    for target, config in TARGETS.items():
        manifest = config["manifest"]
        try:
            manifest_document = json.loads((repo / manifest).read_text(encoding="utf-8"))
            manifest_version = manifest_document["version"]
        except (OSError, json.JSONDecodeError, KeyError, TypeError) as error:
            raise ContractError(f"cannot read {manifest}.version: {error}") from error
        declarations.append(
            validate_target_declaration(
                target,
                targets[target],
                manifest_version,
                config["tagPrefix"],
                manifest,
            )
        )
    return tuple(declarations)


def parse_api_response(exit_code: int, response: str) -> tuple[str, dict | None]:
    normalized = response.replace("\r\n", "\n")
    statuses = [
        int(match.group(1))
        for line in normalized.splitlines()
        if (match := HTTP_STATUS.match(line))
    ]
    if not statuses:
        return "unavailable", None
    status = statuses[-1]
    if status == 404:
        return "missing", None
    if status != 200 or exit_code != 0 or "\n\n" not in normalized:
        return "unavailable", None
    body = normalized.rsplit("\n\n", 1)[1].strip()
    try:
        release = json.loads(body)
    except json.JSONDecodeError:
        return "unavailable", None
    if not isinstance(release, dict):
        return "unavailable", None
    return "available", release


def classify_release_list(expected_tag: str, exit_code: int, response: str) -> str:
    """Classify a complete authenticated Release listing before tag mutation."""
    if exit_code != 0:
        return "api-unavailable"
    try:
        pages = json.loads(response)
    except json.JSONDecodeError:
        return "mismatch"
    if not isinstance(pages, list) or not pages:
        return "mismatch"

    matches = []
    for page in pages:
        if not isinstance(page, list):
            return "mismatch"
        for release in page:
            if (
                not isinstance(release, dict)
                or not isinstance(release.get("tag_name"), str)
                or not isinstance(release.get("draft"), bool)
            ):
                return "mismatch"
            if release["tag_name"] == expected_tag:
                matches.append(release)
    if not matches:
        return "missing"
    if len(matches) != 1:
        return "mismatch"
    return "draft" if matches[0]["draft"] else "published"


def classify_release_state(
    *,
    expected_tag: str,
    expected_version: str,
    evidence: object,
) -> str:
    if not isinstance(evidence, dict):
        return "mismatch"
    lookup = evidence.get("lookup")
    if lookup == "unavailable":
        return "api-unavailable"
    if lookup not in {"available", "missing"}:
        return "mismatch"

    tag_exists = evidence.get("tagExists")
    if tag_exists is False:
        return "planned" if lookup == "missing" and evidence.get("release") is None else "mismatch"
    if tag_exists is not True:
        return "mismatch"

    tag_commit = evidence.get("tagCommit")
    if (
        not isinstance(tag_commit, str)
        or COMMIT.fullmatch(tag_commit) is None
        or evidence.get("tagContainsRegistry") is not True
        or evidence.get("tagRegistryMatches") is not True
        or evidence.get("tagManifestVersion") != expected_version
    ):
        return "mismatch"
    if lookup == "missing":
        return "tag-only" if evidence.get("release") is None else "mismatch"

    release = evidence.get("release")
    if not isinstance(release, dict) or not isinstance(release.get("draft"), bool):
        return "mismatch"
    if release["draft"]:
        return "draft"
    if (
        release.get("tag_name") != expected_tag
        or release.get("target_commitish") != tag_commit
    ):
        return "mismatch"
    return "published"


def _git(repo: Path, *args: str, check: bool = True) -> subprocess.CompletedProcess:
    return subprocess.run(
        ["git", *args],
        cwd=repo,
        check=check,
        capture_output=True,
        text=True,
    )


def collect_tag_evidence(repo: Path, declaration: Declaration) -> dict:
    ref = f"refs/tags/{declaration.tag}"
    if _git(repo, "show-ref", "--verify", "--quiet", ref, check=False).returncode != 0:
        return {
            "tagExists": False,
            "tagCommit": None,
            "tagContainsRegistry": False,
            "tagRegistryMatches": False,
            "tagManifestVersion": None,
        }
    try:
        commit = _git(repo, "rev-parse", "--verify", f"{ref}^{{commit}}").stdout.strip()
        contains = _git(
            repo,
            "ls-tree",
            "--name-only",
            commit,
            "--",
            REGISTRY_PATH.as_posix(),
        ).stdout.splitlines() == [REGISTRY_PATH.as_posix()]
        tag_registry = json.loads(
            _git(repo, "show", f"{ref}:{REGISTRY_PATH.as_posix()}").stdout
        ) if contains else None
        tag_manifest = json.loads(
            _git(repo, "show", f"{ref}:{declaration.manifest.as_posix()}").stdout
        )
        matches = (
            isinstance(tag_registry, dict)
            and tag_registry.get("compatibility", {}).get("targets", {}).get(
                declaration.target, {}
            ).get("firstContainingRelease") == declaration.version
        )
        manifest_version = tag_manifest.get("version") if isinstance(tag_manifest, dict) else None
    except (subprocess.CalledProcessError, json.JSONDecodeError, AttributeError):
        commit, contains, matches, manifest_version = "", False, False, None
    return {
        "tagExists": True,
        "tagCommit": commit,
        "tagContainsRegistry": contains,
        "tagRegistryMatches": matches,
        "tagManifestVersion": manifest_version,
    }


def _read_observation(evidence_dir: Path, target: str) -> tuple[str, dict | None]:
    try:
        exit_code = int((evidence_dir / f"{target}.exit").read_text(encoding="utf-8").strip())
        response = (evidence_dir / f"{target}.http").read_text(encoding="utf-8")
    except (OSError, ValueError):
        return "unavailable", None
    return parse_api_response(exit_code, response)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("mode", choices=("api-lookup", "declarations", "plan", "observe"))
    parser.add_argument("--repo", type=Path, default=REPO)
    parser.add_argument("--evidence-dir", type=Path)
    parser.add_argument("--expected-tag")
    parser.add_argument("--api-response", type=Path)
    parser.add_argument("--api-exit", type=int)
    args = parser.parse_args(argv)

    if args.mode == "api-lookup":
        if args.expected_tag is None or args.api_response is None or args.api_exit is None:
            parser.error("api-lookup requires --expected-tag, --api-response, and --api-exit")
        try:
            response = args.api_response.read_text(encoding="utf-8")
        except OSError:
            state = "api-unavailable"
        else:
            state = classify_release_list(args.expected_tag, args.api_exit, response)
        print(state)
        if state not in {"missing", "published"}:
            print(
                f"command-route release lookup for {args.expected_tag} is {state}; "
                "refusing publication before tag mutation",
                file=sys.stderr,
            )
            return 1
        return 0

    repo = args.repo.resolve()
    try:
        declarations = load_declarations(repo)
    except ContractError as error:
        print(f"command-route release contract: {error}", file=sys.stderr)
        return 2

    if args.mode == "plan":
        for declaration in declarations:
            print(f"{declaration.target}\t{declaration.tag}")
        return 0
    if args.mode == "declarations":
        for declaration in declarations:
            print(
                f"{declaration.target}: first-containing candidate {declaration.tag}; "
                f"current manifest {declaration.manifest_version}"
            )
        return 0
    if args.evidence_dir is None:
        parser.error("observe requires --evidence-dir")

    states = []
    for declaration in declarations:
        lookup, release = _read_observation(args.evidence_dir, declaration.target)
        evidence = collect_tag_evidence(repo, declaration)
        evidence.update({"lookup": lookup, "release": release})
        state = classify_release_state(
            expected_tag=declaration.tag,
            expected_version=declaration.version,
            evidence=evidence,
        )
        states.append(state)
        print(f"{declaration.target}: {declaration.tag}: {state}")
    return 0 if all(state == "published" for state in states) else 1


if __name__ == "__main__":
    raise SystemExit(main())
