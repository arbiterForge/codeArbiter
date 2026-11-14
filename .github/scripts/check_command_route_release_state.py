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
sys.path.insert(0, str(REPO / "tools"))
from command_compatibility import validate_removal_policy  # noqa: E402
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
    required = {"publishedWithoutMetadata", "firstContainingRelease"}
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
    if set(compatibility) != {"clockStarts", "removalRequires", "targets"}:
        raise ContractError("registry compatibility must contain exactly clockStarts, removalRequires and targets")
    try:
        validate_removal_policy(compatibility["removalRequires"])
    except ValueError as error:
        raise ContractError(str(error)) from error
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
    target = release.get("target_commitish")
    # The tag's commit (read from Git) is the identity. A Release created
    # against an existing tag records a branch name such as "main" as its
    # mutable target_commitish; only a commit-shaped value can contradict it.
    if (
        release.get("tag_name") != expected_tag
        or not isinstance(target, str)
        or (COMMIT.fullmatch(target) is not None and target != tag_commit)
    ):
        return "mismatch"
    return "published"


OBSERVATION_FORMAT = "codearbiter.route-publication-observation/0.1.0"


def _release_for(expected_tag: str, exit_code: int, response: str,
                 visibility: str) -> tuple[str, dict | None]:
    """Map a Release list without inferring the absence of hidden drafts."""
    state = classify_release_list(expected_tag, exit_code, response)
    if state == "api-unavailable":
        return "unavailable", None
    if state == "missing":
        return ("missing" if visibility == "draft-inclusive" else "unavailable"), None
    if state == "mismatch":
        return "mismatch", None
    pages = json.loads(response)
    release = next(r for page in pages for r in page if r["tag_name"] == expected_tag)
    return "available", release


def record_observations(repo: Path, declarations, exit_code: int, response: str, *,
                        source: str, run_id: str, observed_at: str,
                        visibility: str = "public") -> dict:
    """Non-mutating observation of every declared first-containing Release.

    Publication clocks start only from an observed non-draft Release. An
    unreadable listing or absence from a draft-hidden public listing is
    `api-unavailable` (unknown), never `published`, and
    the record carries no removal authority: alias removal stays a separate,
    explicitly approved decision (`compatibility.removalRequires`).
    """
    rows = []
    for declaration in declarations:
        lookup, release = _release_for(declaration.tag, exit_code, response, visibility)
        evidence = collect_tag_evidence(repo, declaration)
        if lookup == "mismatch":
            state = "mismatch"
        else:
            evidence.update({"lookup": lookup, "release": release})
            state = classify_release_state(expected_tag=declaration.tag,
                                           expected_version=declaration.version,
                                           evidence=evidence)
        rows.append({
            "target": declaration.target, "tag": declaration.tag,
            "first_containing_version": declaration.version, "state": state,
            "tag_commit": evidence.get("tagCommit") or None,
            "release_id": release.get("id") if isinstance(release, dict) else None,
            "release_draft": release.get("draft") if isinstance(release, dict) else None,
        })
    return {
        "format": OBSERVATION_FORMAT, "observed_at": observed_at,
        "source_commit": source, "workflow_run": run_id,
        "release_visibility": visibility,
        "clock_starts": "confirmed-non-draft-github-release",
        "removal_authorization": "not-evaluated",
        "observations": rows,
    }


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
    parser.add_argument("mode", choices=("api-lookup", "declarations", "plan", "observe", "record"))
    parser.add_argument("--repo", type=Path, default=REPO)
    parser.add_argument("--evidence-dir", type=Path)
    parser.add_argument("--expected-tag")
    parser.add_argument("--api-response", type=Path)
    parser.add_argument("--api-exit", type=int)
    parser.add_argument("--releases", type=Path, help="record: observed Release list")
    parser.add_argument("--releases-exit", type=int, help="record: exit code of that listing")
    parser.add_argument("--releases-visibility", choices=("public", "draft-inclusive"),
                        default="public", help="record: visibility actually established by the reader")
    parser.add_argument("--source", help="record: the observing workflow's source commit")
    parser.add_argument("--run-id", default="", help="record: the observing workflow run")
    parser.add_argument("--output", type=Path, help="record: observation JSON to write")
    parser.add_argument("--summary", type=Path, help="record: Markdown summary to append")
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
    if args.mode == "record":
        if args.releases is None or args.releases_exit is None or args.output is None:
            parser.error("record requires --releases, --releases-exit and --output")
        if args.source is None or COMMIT.fullmatch(args.source) is None:
            parser.error("record requires --source as a full commit id")
        try:
            response = args.releases.read_text(encoding="utf-8")
            exit_code = args.releases_exit
        except OSError:
            response, exit_code = "", 1
        from datetime import datetime, timezone
        document = record_observations(
            repo, declarations, exit_code, response, source=args.source,
            run_id=args.run_id, visibility=args.releases_visibility,
            observed_at=datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"))
        args.output.write_text(json.dumps(document, indent=2, sort_keys=True) + "\n",
                               encoding="utf-8")
        lines = [f"{row['target']}: {row['tag']}: {row['state']}"
                 for row in document["observations"]]
        print("\n".join(lines))
        if args.summary:
            with args.summary.open("a", encoding="utf-8") as stream:
                stream.write("### Command-route publication observation\n\n"
                             + "".join(f"- `{line}`\n" for line in lines)
                             + "\nObservation only: it starts no removal and undoes nothing.\n")
        # Observation never fails or reverses a settled publication.
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
