#!/usr/bin/env python3
"""codeArbiter — fail-closed helpers for exact ca-pi npm publication.

The release workflow owns orchestration and credentials. This module validates
the immutable Git/GitHub/package boundary, selects the exact tarball retained
from protected CI without repacking it, distinguishes registry absence from
registry failure, and requires matching integrity plus npm provenance before
success.
"""
from __future__ import annotations

import argparse
import base64
import binascii
import hashlib
import json
import os
import re
import subprocess
import sys
import tempfile
import time
import tarfile
import importlib.util
from pathlib import Path


PACKAGE = "@arbiterforge/ca-pi"
REGISTRY = "https://registry.npmjs.org/"
SCOPED_REGISTRY_OPTION = f"--@arbiterforge:registry={REGISTRY}"
REPOSITORY_URL = "git+https://github.com/arbiterForge/codeArbiter.git"
TAG_RE = re.compile(r"ca-pi-v(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)\Z")
CODEX_VERSION_RE = re.compile(
    r"(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)\Z"
)
SHA_RE = re.compile(r"[0-9a-f]{40}\Z")
PROVENANCE_PREDICATE = "https://slsa.dev/provenance/v1"
REGISTRY_TIMEOUT_SECONDS = 30
REGISTRY_READBACK_ATTEMPTS = 120
REGISTRY_READBACK_DELAY_SECONDS = 5.0
REGISTRY_READBACK_SECONDS = 10 * 60.0
ATTESTATION_MAX_BYTES = 2 * 1024 * 1024
SOURCE_REPOSITORY = "https://github.com/arbiterForge/codeArbiter"
SOURCE_REF = "refs/heads/main"
SOURCE_WORKFLOWS = {
    ".github/workflows/release.yml",
    ".github/workflows/npm-publish.yml",
}
CONTINUATION_CHANGE_ALLOWLIST = {
    ".github/published-tags.json",
    ".github/scripts/_npm_publishlib.py",
    ".github/scripts/test_pi_package.py",
    ".github/scripts/test_release_workflow.py",
    ".github/workflows/npm-publish.yml",
    ".github/workflows/release.yml",
}
NPM_PACKER_INTEGRITY = "sha512-ztsxKxt/kkIaAs+2i0GU6I+DRmUdrNasxTZKJe9TCdSjKxlhah/4r/hl5ygMD6XAg1qZ9c2TNomR4qgOydp10g=="
DURABLE_RECEIPT_NAME = "codearbiter-cohort-publication-v1.json"
DURABLE_RECEIPT_FIELDS = {
    "format", "target", "host", "tag", "source_commit", "source_tree",
    "ci_run_id", "cohort_sha256", "package_file", "package_sha256",
    "cohort_tags", "cohort_targets", "tag_object_sha", "release_notes_sha256",
    "readback", "disposition",
}
COHORT_MARKER_FIELDS = {
    "format", "target", "host", "tag", "source_commit", "source_tree",
    "workflow", "ci_run_id", "cohort_sha256", "cohort_tags", "cohort_targets",
    "release_notes_sha256",
}
QUALIFIED_TARGET_HOSTS = {"ca": "claude", "ca-codex": "codex", "ca-pi": "pi"}
QUALIFIED_TAG_PATTERNS = {
    "ca": re.compile(r"v(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)\Z"),
    "ca-codex": re.compile(
        r"ca-codex-v(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)\Z"
    ),
    "ca-pi": TAG_RE,
}
COLD_FIELDS = {
    "format", "source_commit", "workflow", "run_id", "job", "host", "platform",
    "promotion_receipt_sha256", "package_sha256", "manifest_sha256",
    "binary_sha256", "response_sha256", "operation",
    "repository_operations_available", "runtime_downloads",
    "installed_workflow_response_sha256", "installed_bridge_sha256",
    "installed_workflow_format", "approval_evidence_mode",
    "prerequisite_evidence_mode",
    "interruption_reconciled", "redispatched",
    "commit_proof", "finalization_proof", "all_accepted_and_current",
    "markdown_shadow_count",
}
INSTALLED_WORKFLOW_FORMAT = "codearbiter.installed-host-workflow/0.2.0"
COLD_PLATFORMS = {
    "darwin/amd64", "darwin/arm64", "linux/amd64", "linux/arm64",
    "windows/amd64", "windows/arm64",
}


class RegistryUnavailable(ValueError):
    """The registry did not provide usable transport evidence yet."""


def _unique_object(pairs: list[tuple[str, object]]) -> dict:
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError(f"duplicate JSON field: {key}")
        result[key] = value
    return result


def validate_inputs(tag: str, expected_sha: str) -> str:
    match = TAG_RE.fullmatch(tag)
    if match is None:
        raise ValueError("release tag must be canonical ca-pi-vMAJOR.MINOR.PATCH")
    if SHA_RE.fullmatch(expected_sha) is None:
        raise ValueError("expected SHA must be exactly 40 lowercase hexadecimal characters")
    return ".".join(match.groups())


def validate_sha(value: str, label: str) -> None:
    if SHA_RE.fullmatch(value) is None:
        raise ValueError(f"{label} must be exactly 40 lowercase hexadecimal characters")


def validate_package_identity(root: dict, nested: dict, version: str) -> None:
    if root.get("name") != PACKAGE:
        raise ValueError("root package name does not match the public ca-pi package")
    if root.get("version") != version or nested.get("version") != version:
        raise ValueError("tag and synchronized manifest versions do not match")
    if nested.get("name") != PACKAGE or nested.get("private") is not True:
        raise ValueError("nested manifest must retain the private ca-pi package identity")
    repository = root.get("repository")
    if not isinstance(repository, dict) or repository != {
        "type": "git",
        "url": REPOSITORY_URL,
    }:
        raise ValueError("root package repository identity does not match codeArbiter")
    publish = root.get("publishConfig")
    if not isinstance(publish, dict):
        raise ValueError("root publishConfig is missing")
    if publish.get("access") != "public" or publish.get("provenance") is not True:
        raise ValueError("root publishConfig must require public provenance publication")
    if "registry" in publish:
        raise ValueError("publishConfig.registry must not override the approved npm registry")


def validate_project_registry(repo: Path) -> None:
    if (repo / ".npmrc").exists():
        raise ValueError("project .npmrc is forbidden at the publication boundary")


def _git(repo: Path, *args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["git", "-C", str(repo), *args],
        text=True,
        capture_output=True,
        check=False,
    )


def validate_git_identity(
    repo: Path, tag: str, expected_sha: str, *, main_ref: str = "origin/main"
) -> None:
    validate_inputs(tag, expected_sha)
    tag_ref = f"refs/tags/{tag}"
    kind = _git(repo, "cat-file", "-t", tag_ref)
    if kind.returncode != 0 or kind.stdout.strip() != "tag":
        raise ValueError("release ref must be an annotated tag")
    peeled = _git(repo, "rev-parse", f"{tag_ref}^{{commit}}")
    if peeled.returncode != 0 or peeled.stdout.strip() != expected_sha:
        raise ValueError("release tag does not resolve to the expected commit")
    checked_out = _git(repo, "rev-parse", "HEAD")
    if checked_out.returncode != 0 or checked_out.stdout.strip() != expected_sha:
        raise ValueError("checked-out package does not equal the expected release commit")
    ancestor = _git(repo, "merge-base", "--is-ancestor", expected_sha, main_ref)
    if ancestor.returncode != 0:
        raise ValueError("expected release commit is not contained in protected main")


def validate_main_commit(repo: Path, commit: str, main_ref: str = "origin/main") -> None:
    validate_sha(commit, "attested workflow SHA")
    ancestor = _git(repo, "merge-base", "--is-ancestor", commit, main_ref)
    if ancestor.returncode != 0:
        raise ValueError("attested workflow commit is not contained in protected main")


def validate_release_source_binding(trusted_repo: Path, source_repo: Path,
                                    expected_sha: str, trusted_sha: str, *,
                                    allow_continuation: bool = False) -> None:
    """Bind trusted workflow code and release source, with an explicit repair lane."""
    validate_sha(expected_sha, "expected SHA")
    validate_sha(trusted_sha, "trusted workflow SHA")
    if not allow_continuation and expected_sha != trusted_sha:
        raise ValueError("workflow, trusted verifier, and release source SHA must be identical")
    trusted_head = _git(trusted_repo, "rev-parse", "HEAD")
    if trusted_head.returncode != 0 or trusted_head.stdout.strip() != trusted_sha:
        raise ValueError("trusted verifier checkout does not equal the trusted workflow SHA")
    source_head = _git(source_repo, "rev-parse", "HEAD")
    same_checkout = trusted_repo.resolve() == source_repo.resolve()
    required_source_head = trusted_sha if allow_continuation and same_checkout else expected_sha
    if source_head.returncode != 0 or source_head.stdout.strip() != required_source_head:
        raise ValueError("release source checkout does not equal the required release identity")
    if allow_continuation:
        validate_continuation_revision(trusted_repo, expected_sha, trusted_sha)


def validate_continuation_revision(repo: Path, source_sha: str, revision_sha: str) -> None:
    validate_sha(source_sha, "continued release source")
    validate_sha(revision_sha, "continuation revision")
    ancestor = _git(repo, "merge-base", "--is-ancestor", source_sha, revision_sha)
    if ancestor.returncode != 0:
        raise ValueError("continued release source is not an ancestor of the trusted workflow")
    changed = _git(repo, "diff", "--name-status", source_sha, revision_sha)
    if changed.returncode != 0:
        raise ValueError("continued release payload comparison failed")
    for line in changed.stdout.splitlines():
        fields = line.split("\t")
        if (len(fields) != 2 or fields[0] != "M"
                or fields[1] not in CONTINUATION_CHANGE_ALLOWLIST):
            raise ValueError("continued release payload changed outside the repair allowlist")


def _archive_member_bytes(archive: Path, name: str) -> bytes:
    with tarfile.open(archive, "r:*") as stream:
        matches = [member for member in stream.getmembers() if member.name == name]
        if len(matches) != 1 or not matches[0].isfile():
            raise ValueError(f"final package member is missing or ambiguous: {name}")
        extracted = stream.extractfile(matches[0])
        if extracted is None:
            raise ValueError(f"final package member is unreadable: {name}")
        return extracted.read()


def verify_release_cohort(*, package_root: Path, stage_root: Path, cold_root: Path,
                          source_repo: Path, source_commit: str, ci_run_id: str,
                          npm_executable: Path, trusted_repo: Path,
                          workflow_sha: str, allow_continuation: bool = False) -> dict:
    """One fail-closed verifier for every qualified host before publication."""
    validate_release_source_binding(
        trusted_repo, source_repo, source_commit, workflow_sha,
        allow_continuation=allow_continuation,
    )
    packager_path = trusted_repo / "tools" / "build-host-packages.py"
    spec = importlib.util.spec_from_file_location("release_packager", packager_path)
    if spec is None or spec.loader is None:
        raise ValueError("trusted release packager is unavailable")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    cohort_path = package_root / "artifact-package-cohort.json"
    cohort_seed = json.loads(cohort_path.read_text(encoding="utf-8"))
    receipt = module.verify_artifact_release_packages(
        package_root=package_root, source_repo=source_repo,
        source_commit=source_commit, workflow=".github/workflows/ci.yml",
        run_id=ci_run_id,
        promotion_receipt_sha256=cohort_seed["promotion_receipt_sha256"],
        stage=stage_root, require_production=True,
        npm_executable=npm_executable, repo=trusted_repo,
    )
    required = {(host, platform) for host in ("claude", "codex", "pi")
                for platform in COLD_PLATFORMS}
    observed: set[tuple[str, str]] = set()
    prefixes = {
        "claude": "plugins/ca/helpers/artifacts/",
        "codex": "plugins/ca-codex/helpers/artifacts/",
        "pi": "package/plugins/ca-pi/helpers/artifacts/",
    }
    paths = sorted(cold_root.glob("*/artifact-package-cold.json"))
    for path in paths:
        if path.is_symlink() or not path.is_file():
            raise ValueError("cold-execution receipt must be a real file")
        cold = json.loads(path.read_text(encoding="utf-8"), object_pairs_hook=_unique_object)
        if not isinstance(cold, dict) or set(cold) != COLD_FIELDS:
            raise ValueError("cold-execution receipt schema is not exact")
        cell = (cold["host"], cold["platform"])
        if cell not in required or cell in observed:
            raise ValueError("cold-execution receipt matrix is duplicate or unexpected")
        package = receipt["packages"][cold["host"]]
        if not all((
            cold["format"] == "codearbiter.artifact-cold-execution/0.3.0",
            cold["source_commit"] == source_commit,
            cold["workflow"] == ".github/workflows/ci.yml",
            cold["run_id"] == ci_run_id,
            cold["job"] == "artifact-package-cold",
            cold["operation"] == "capabilities",
            cold["promotion_receipt_sha256"] == receipt["promotion_receipt_sha256"],
            cold["package_sha256"] == package["sha256"],
            cold["repository_operations_available"] is True,
            cold["runtime_downloads"] is False,
            re.fullmatch(r"[0-9a-f]{64}", cold["response_sha256"]) is not None,
            re.fullmatch(r"[0-9a-f]{64}", cold["installed_workflow_response_sha256"]) is not None,
            re.fullmatch(r"[0-9a-f]{64}", cold["installed_bridge_sha256"]) is not None,
            cold["installed_workflow_format"] == INSTALLED_WORKFLOW_FORMAT,
            cold["approval_evidence_mode"] == (
                "synthetic-policy-event"
                if cold["host"] == "pi"
                else "host-observed-prompt"
            ),
            cold["prerequisite_evidence_mode"] == (
                "synthetic-policy-event"
                if cold["host"] == "pi"
                else "host-observed-prompt"
            ),
            cold["interruption_reconciled"] is True,
            cold["redispatched"] is True,
            cold["commit_proof"] is True,
            cold["finalization_proof"] is True,
            cold["all_accepted_and_current"] is True,
            cold["markdown_shadow_count"] == 0 and not isinstance(cold["markdown_shadow_count"], bool),
        )):
            raise ValueError("cold-execution receipt is not bound to the exact cohort")
        prefix = prefixes[cold["host"]]
        manifest_name = prefix + "release.json"
        manifest_bytes = _archive_member_bytes(package_root / package["file"], manifest_name)
        manifest = json.loads(manifest_bytes)
        binary = manifest.get("binaries", {}).get(cold["platform"])
        if not isinstance(binary, dict) or not isinstance(binary.get("file"), str):
            raise ValueError("cold-execution binary is absent from the final manifest")
        binary_name = prefix + binary["file"]
        members = package["members"]
        if (cold["manifest_sha256"] != hashlib.sha256(manifest_bytes).hexdigest()
                or members.get(manifest_name, {}).get("sha256") != cold["manifest_sha256"]
                or binary.get("sha256") != cold["binary_sha256"]
                or members.get(binary_name, {}).get("sha256") != cold["binary_sha256"]):
            raise ValueError("cold-execution digests do not link to final package members")
        observed.add(cell)
    if observed != required:
        raise ValueError("cold-execution receipt matrix is incomplete")
    return receipt


def validate_durable_receipt(receipt: dict, *, target: str, host: str, tag: str,
                             source_commit: str, source_tree: str, ci_run_id: str,
                             cohort_sha256: str, package_file: str,
                             package_sha256: str, cohort_tags: dict,
                             tag_object_sha: str,
                             release_notes_sha256: str,
                             cohort_targets: list[str]) -> None:
    expected = {
        "format": "codearbiter.cohort-publication/0.1.0",
        "target": target, "host": host, "tag": tag,
        "source_commit": source_commit, "source_tree": source_tree,
        "ci_run_id": ci_run_id, "cohort_sha256": cohort_sha256,
        "package_file": package_file, "package_sha256": package_sha256,
        "tag_object_sha": tag_object_sha,
        "release_notes_sha256": release_notes_sha256,
        "cohort_tags": cohort_tags, "cohort_targets": cohort_targets,
        "readback": "verified", "disposition": "published-and-read-back",
    }
    if not isinstance(receipt, dict) or set(receipt) != DURABLE_RECEIPT_FIELDS:
        raise ValueError("durable publication receipt schema is not exact")
    if receipt != expected:
        raise ValueError("durable publication receipt does not match the exact cohort target")


def _validate_discovered_durable_receipt(receipt: dict) -> tuple:
    """Validate a receipt against its own immutable historical cohort identity."""
    if not isinstance(receipt, dict) or set(receipt) != DURABLE_RECEIPT_FIELDS:
        raise ValueError("durable publication receipt schema is not exact")
    target = receipt["target"]
    tags = receipt["cohort_tags"]
    targets = receipt["cohort_targets"]
    if (target not in QUALIFIED_TARGET_HOSTS
            or receipt["host"] != QUALIFIED_TARGET_HOSTS[target]
            or not isinstance(tags, dict) or set(tags) != set(QUALIFIED_TARGET_HOSTS)
            or any(not isinstance(value, str) or not value for value in tags.values())
            or receipt["tag"] != tags[target]
            or not isinstance(targets, list) or not targets
            or targets != sorted(set(targets))
            or not set(targets) <= set(QUALIFIED_TARGET_HOSTS)
            or target not in targets):
        raise ValueError("durable publication receipt target binding is invalid")
    validate_sha(receipt["source_commit"], "durable receipt source commit")
    validate_sha(receipt["source_tree"], "durable receipt source tree")
    if (not isinstance(receipt["ci_run_id"], str) or not receipt["ci_run_id"].isdigit()
            or re.fullmatch(r"[0-9a-f]{64}", receipt["cohort_sha256"]) is None
            or re.fullmatch(r"[0-9a-f]{64}", receipt["package_sha256"]) is None
            or re.fullmatch(r"[0-9a-f]{40}", receipt["tag_object_sha"]) is None
            or re.fullmatch(r"[0-9a-f]{64}", receipt["release_notes_sha256"]) is None
            or not isinstance(receipt["package_file"], str)
            or not receipt["package_file"] or Path(receipt["package_file"]).name != receipt["package_file"]
            or receipt["format"] != "codearbiter.cohort-publication/0.1.0"
            or receipt["readback"] != "verified"
            or receipt["disposition"] != "published-and-read-back"):
        raise ValueError("durable publication receipt identity is invalid")
    return (
        json.dumps(tags, sort_keys=True, separators=(",", ":")), tuple(targets),
        receipt["source_commit"], receipt["source_tree"], receipt["ci_run_id"],
        receipt["cohort_sha256"],
    )


def _validate_cohort_marker(marker: dict) -> tuple:
    if not isinstance(marker, dict) or set(marker) != COHORT_MARKER_FIELDS:
        raise ValueError("cohort-start marker schema is not exact")
    target = marker["target"]
    tags = marker["cohort_tags"]
    targets = marker["cohort_targets"]
    if (target not in QUALIFIED_TARGET_HOSTS
            or marker["host"] != QUALIFIED_TARGET_HOSTS[target]
            or marker["workflow"] != ".github/workflows/ci.yml"
            or not isinstance(tags, dict) or set(tags) != set(QUALIFIED_TARGET_HOSTS)
            or marker["tag"] != tags[target]
            or not isinstance(targets, list) or not targets
            or targets != sorted(set(targets)) or target not in targets
            or not set(targets) <= set(QUALIFIED_TARGET_HOSTS)
            or marker["format"] != "codearbiter.cohort-start/0.1.0"
            or not isinstance(marker["ci_run_id"], str) or not marker["ci_run_id"].isdigit()
            or re.fullmatch(r"[0-9a-f]{64}", marker["cohort_sha256"]) is None
            or re.fullmatch(r"[0-9a-f]{64}", marker["release_notes_sha256"]) is None):
        raise ValueError("cohort-start marker target binding is invalid")
    validate_sha(marker["source_commit"], "cohort marker source commit")
    validate_sha(marker["source_tree"], "cohort marker source tree")
    return (json.dumps(tags, sort_keys=True, separators=(",", ":")), tuple(targets),
            marker["source_commit"], marker["source_tree"], marker["ci_run_id"],
            marker["cohort_sha256"])


def _cohort_tags_strictly_newer(new_tags: dict, old_tags: dict,
                                targets: set[str]) -> bool:
    """Require every superseding target to advance its stable SemVer tag."""
    for target in targets:
        pattern = QUALIFIED_TAG_PATTERNS[target]
        new_match = pattern.fullmatch(new_tags.get(target, ""))
        old_match = pattern.fullmatch(old_tags.get(target, ""))
        if new_match is None or old_match is None:
            raise ValueError("durable cohort tag map is not canonical")
        if tuple(map(int, new_match.groups())) <= tuple(map(int, old_match.groups())):
            return False
    return True


def _active_incomplete_cohort_keys(incomplete: list[tuple],
                                   completed: list[tuple], *,
                                   replacement_tags: dict | None = None,
                                   replacement_targets: list[str] | None = None
                                   ) -> list[tuple]:
    """Drop old cohorts only for a completed or full newer replacement."""
    replacements = [(json.loads(key[0]), set(key[1])) for key in completed]
    if replacement_tags is not None:
        replacements.append((replacement_tags, set(replacement_targets or [])))
    active = []
    for key in incomplete:
        tags = json.loads(key[0])
        intended = set(key[1])
        superseded = False
        for owner_tags, owner_targets in replacements:
            if not intended <= owner_targets:
                continue
            if not _cohort_tags_strictly_newer(owner_tags, tags, intended):
                continue
            superseded = True
            break
        if not superseded:
            active.append(key)
    return active


def resolve_durable_cohort_identity(*, current_source: str, current_run_id: str,
                                    current_tags: dict, eligible_targets: list[str],
                                    markers: list[dict], receipts: list[dict],
                                    draft_markers: list[dict]) -> dict:
    """Choose the current CI cohort or one unfinished durable cohort.

    A repair-only commit commonly has no package artifacts of its own.  Durable
    draft markers are therefore resolved before artifact download.  Selection
    is deliberately narrow: at most one historical cohort may be unfinished,
    and its version map must still be the repository's current release map.
    """
    validate_sha(current_source, "current release source")
    if not isinstance(current_run_id, str) or not current_run_id.isdigit():
        raise ValueError("current CI run identity is invalid")
    if (not isinstance(current_tags, dict)
            or set(current_tags) != set(QUALIFIED_TARGET_HOSTS)
            or any(not isinstance(value, str) or not value for value in current_tags.values())):
        raise ValueError("current cohort tag map is invalid")
    if (not isinstance(eligible_targets, list)
            or eligible_targets != sorted(set(eligible_targets))
            or not set(eligible_targets) <= set(QUALIFIED_TARGET_HOSTS)
            or not isinstance(markers, list)
            or not isinstance(receipts, list)
            or not isinstance(draft_markers, list)):
        raise ValueError("current cohort selection is invalid")

    marker_groups: dict[tuple, dict[str, dict]] = {}
    for marker in markers:
        key = _validate_cohort_marker(marker)
        group = marker_groups.setdefault(key, {})
        target = marker["target"]
        if target in group:
            raise ValueError("cohort-start marker group contains duplicate target markers")
        group[target] = marker
    receipt_groups: dict[tuple, dict[str, dict]] = {}
    for receipt in receipts:
        key = _validate_discovered_durable_receipt(receipt)
        group = receipt_groups.setdefault(key, {})
        if receipt["target"] in group:
            raise ValueError("durable publication cohort contains duplicate target receipts")
        group[receipt["target"]] = receipt
    if set(receipt_groups) - set(marker_groups):
        raise ValueError("durable receipt has no matching cohort-start marker")
    draft_pairs = set()
    for marker in draft_markers:
        key = _validate_cohort_marker(marker)
        pair = (key, marker["target"])
        if pair in draft_pairs or marker_groups.get(key, {}).get(marker["target"]) != marker:
            raise ValueError("draft cohort-start marker is duplicate or undiscovered")
        draft_pairs.add(pair)
    incomplete = []
    completed = []
    for key, marked in marker_groups.items():
        received = receipt_groups.get(key, {})
        intended = set(key[1])
        if not set(marked) <= intended or not set(received) <= intended:
            raise ValueError("durable publication cohort contains an unexpected target")
        for target in set(marked) & set(received):
            validate_durable_receipt_with_marker(received[target], marked[target])
        for target in marked:
            if target not in received and (key, target) not in draft_pairs:
                raise ValueError("marker-owned Release was published without its durable receipt")
        if (set(marked) != intended or set(received) != intended
                or any((key, target) in draft_pairs for target in intended)):
            incomplete.append(key)
        else:
            completed.append(key)
    # A strictly newer full-target obligation can replace an older partial
    # cohort. Completed cohorts prove historical replacement; the current
    # eligible target set prevents a partial old run from deadlocking the next
    # full release before its markers exist. Partial or non-monotonic
    # replacements never supersede the old obligation.
    active_incomplete = _active_incomplete_cohort_keys(
        incomplete, completed, replacement_tags=current_tags,
        replacement_targets=eligible_targets,
    )
    if len(active_incomplete) > 1:
        raise ValueError("multiple unresolved historical publication cohorts exist")
    if active_incomplete:
        key = active_incomplete[0]
        tags = json.loads(key[0])
        if tags != current_tags:
            raise ValueError("unresolved historical cohort versions differ from current manifests")
        return {
            "requires_cohort": True,
            "continuation": key[2] != current_source,
            "source_commit": key[2],
            "source_tree": key[3],
            "ci_run_id": key[4],
            "cohort_sha256": key[5],
            "cohort_tags": tags,
            "cohort_targets": list(key[1]),
        }
    return {
        "requires_cohort": bool(eligible_targets),
        "continuation": False,
        "source_commit": current_source,
        "source_tree": "",
        "ci_run_id": current_run_id,
        "cohort_sha256": "",
        "cohort_tags": current_tags,
        "cohort_targets": eligible_targets,
    }


def _validate_qualified_release_body(body: object, tag: str,
                                     marker_bytes: bytes) -> dict:
    """Validate the exact canonical notes + one terminal marker body."""
    if not isinstance(body, str):
        raise ValueError("qualified Release body is malformed")
    match = re.fullmatch(
        r"(?s)(.*\n)\n<!-- codearbiter-cohort-start-v1:([A-Za-z0-9_-]+) -->\n",
        body,
    )
    if match is None or body.count("codearbiter-cohort-start-v1:") != 1:
        raise ValueError("qualified Release marker is missing, duplicate, or malformed")
    try:
        encoded = match.group(2)
        observed = base64.urlsafe_b64decode(encoded + "=" * (-len(encoded) % 4))
    except (ValueError, binascii.Error) as exc:
        raise ValueError("qualified Release marker is malformed") from exc
    if observed != marker_bytes:
        raise ValueError("qualified Release marker identity mismatch")
    try:
        marker = json.loads(observed, object_pairs_hook=_unique_object)
    except json.JSONDecodeError as exc:
        raise ValueError("qualified Release marker is not exact JSON") from exc
    _validate_cohort_marker(marker)
    if marker["tag"] != tag:
        raise ValueError("qualified Release marker names the wrong tag")
    notes_bytes = match.group(1).encode("utf-8")
    if hashlib.sha256(notes_bytes).hexdigest() != marker["release_notes_sha256"]:
        raise ValueError("qualified Release notes identity mismatch")
    return marker


def validate_qualified_draft_release(pages: list, tag: str, marker_bytes: bytes,
                                     *, asset_name: str | None = None) -> tuple[int, str]:
    """Read one marker-owned qualified Release only while it remains a draft."""
    if not isinstance(pages, list) or any(not isinstance(page, list) for page in pages):
        raise ValueError("qualified Release inventory is malformed")
    found = [release for page in pages for release in page
             if isinstance(release, dict) and release.get("tag_name") == tag]
    if len(found) != 1:
        raise ValueError("qualified Release is missing or duplicate")
    release = found[0]
    if release.get("draft") is not True:
        raise ValueError("qualified Release must remain draft until exact readback completes")
    _validate_qualified_release_body(release.get("body"), tag, marker_bytes)
    release_id = release.get("id")
    if not isinstance(release_id, int) or isinstance(release_id, bool):
        raise ValueError("qualified Release id is invalid")
    if asset_name is None:
        return release_id, "missing"
    assets = release.get("assets", [])
    if not isinstance(assets, list):
        raise ValueError("qualified Release assets are malformed")
    matches = [asset for asset in assets
               if isinstance(asset, dict) and asset.get("name") == asset_name]
    if len(matches) > 1:
        raise ValueError(f"qualified Release asset {asset_name} is duplicate")
    if not matches:
        return release_id, "missing"
    url = matches[0].get("url")
    if not isinstance(url, str) or not url:
        raise ValueError(f"qualified Release asset {asset_name} URL is invalid")
    return release_id, url


def validate_qualified_finalization(pages: list, tag: str, marker_bytes: bytes,
                                    *, allowed_assets: list[str],
                                    expected_assets: dict[str, str] | None = None
                                    ) -> tuple[int, dict[str, str]]:
    """Require one exact marker-owned draft and exactly its declared assets."""
    release_id, _ = validate_qualified_draft_release(pages, tag, marker_bytes)
    found = [release for page in pages for release in page
             if isinstance(release, dict) and release.get("tag_name") == tag][0]
    if allowed_assets != sorted(set(allowed_assets)):
        raise ValueError("qualified finalization asset allowlist is invalid")
    assets = found.get("assets", [])
    if not isinstance(assets, list) or any(not isinstance(asset, dict) for asset in assets):
        raise ValueError("qualified finalization assets are malformed")
    names = [asset.get("name") for asset in assets]
    if sorted(names) != allowed_assets:
        raise ValueError("qualified finalization assets are missing, duplicate, or extra")
    urls = {}
    for asset in assets:
        if not isinstance(asset.get("url"), str) or not asset["url"]:
            raise ValueError("qualified finalization asset URL is invalid")
        urls[asset["name"]] = asset["url"]
    if expected_assets is not None:
        if (not isinstance(expected_assets, dict)
                or set(expected_assets) != set(allowed_assets)
                or any(not isinstance(value, str) or not value
                       for value in expected_assets.values())):
            raise ValueError("qualified finalization expected asset identity is invalid")
        if urls != expected_assets:
            raise ValueError("qualified finalization asset identity changed")
    return release_id, urls


def validate_durable_receipt_with_marker(receipt: dict, marker: dict) -> None:
    receipt_key = _validate_discovered_durable_receipt(receipt)
    marker_key = _validate_cohort_marker(marker)
    if (receipt_key != marker_key or receipt["target"] != marker["target"]
            or receipt["host"] != marker["host"] or receipt["tag"] != marker["tag"]
            or receipt["release_notes_sha256"] != marker["release_notes_sha256"]):
        raise ValueError("durable receipt does not match its exact cohort-start marker")


def validate_remote_annotated_tag(remote_text: str, tag: str, source_commit: str,
                                  expected_object: str | None = None) -> str:
    validate_sha(source_commit, "qualified release source commit")
    exact = f"refs/tags/{tag}"
    direct = []
    peeled = []
    for line in remote_text.splitlines():
        parts = line.split()
        if len(parts) != 2:
            continue
        sha, ref = parts
        if ref == exact:
            direct.append(sha)
        elif ref == exact + "^{}":
            peeled.append(sha)
    if len(direct) != 1 or len(peeled) != 1:
        raise ValueError("qualified release tag must be one exact annotated tag")
    validate_sha(direct[0], "qualified annotated tag object")
    if peeled[0] != source_commit:
        raise ValueError("qualified annotated tag does not peel to the exact source")
    if expected_object is not None and direct[0] != expected_object:
        raise ValueError("qualified annotated tag object identity changed")
    return direct[0]


def reject_markerless_current_tag(remote_text: str, tag: str, source_commit: str,
                                  *, has_marker: bool) -> None:
    """Reject the only tag-only state attributable to the current qualified run."""
    validate_sha(source_commit, "qualified release source commit")
    if has_marker:
        return
    direct: list[str] = []
    peeled: list[str] = []
    exact = f"refs/tags/{tag}"
    for line in remote_text.splitlines():
        parts = line.split()
        if len(parts) != 2:
            continue
        sha, ref = parts
        if ref == exact:
            direct.append(sha)
        elif ref == exact + "^{}":
            peeled.append(sha)
    if len(direct) > 1 or len(peeled) > 1:
        raise ValueError("qualified tag identity is duplicate")
    resolved = peeled[0] if peeled else (direct[0] if direct else "")
    if resolved == source_commit:
        raise ValueError("markerless current qualified tag is an unresolved partial publication")


def reconcile_durable_cohort(receipts: list[dict], *, current: dict,
                             missing_current: list[str] | None = None,
                             markers: list[dict] | None = None,
                             draft_markers: list[dict] | None = None) -> dict:
    """Reconcile every cohort into an exact repair or full newer replacement."""
    required = {"source_commit", "source_tree", "workflow", "ci_run_id", "cohort_sha256",
                "cohort_tags", "eligible_targets"}
    if not isinstance(current, dict) or set(current) != required:
        raise ValueError("current durable cohort schema is not exact")
    for name in ("source_commit", "source_tree"):
        validate_sha(current[name], f"current {name.replace('_', ' ')}")
    if (not isinstance(current["ci_run_id"], str) or not current["ci_run_id"].isdigit()
            or current["workflow"] != ".github/workflows/ci.yml"
            or re.fullmatch(r"[0-9a-f]{64}", current["cohort_sha256"]) is None
            or not isinstance(current["cohort_tags"], dict)
            or set(current["cohort_tags"]) != set(QUALIFIED_TARGET_HOSTS)):
        raise ValueError("current durable cohort identity is invalid")
    eligible = current["eligible_targets"]
    missing = missing_current or []
    marker_list = markers or []
    draft_list = draft_markers or []
    if (not isinstance(receipts, list) or not isinstance(eligible, list)
            or eligible != sorted(set(eligible))
            or not set(eligible) <= set(QUALIFIED_TARGET_HOSTS)
            or not isinstance(missing, list) or missing != sorted(set(missing))
            or not set(missing) <= set(QUALIFIED_TARGET_HOSTS)
            or not isinstance(draft_list, list)):
        raise ValueError("current durable cohort target state is invalid")

    groups: dict[tuple, dict[str, dict]] = {}
    for receipt in receipts:
        key = _validate_discovered_durable_receipt(receipt)
        group = groups.setdefault(key, {})
        target = receipt["target"]
        if target in group:
            raise ValueError("durable publication cohort contains duplicate target receipts")
        group[target] = receipt

    marker_groups: dict[tuple, dict[str, dict]] = {}
    for marker in marker_list:
        key = _validate_cohort_marker(marker)
        group = marker_groups.setdefault(key, {})
        if marker["target"] in group:
            raise ValueError("cohort-start marker group contains duplicate target markers")
        group[marker["target"]] = marker
    draft_keys: set[tuple[tuple, str]] = set()
    for marker in draft_list:
        key = _validate_cohort_marker(marker)
        pair = (key, marker["target"])
        if pair in draft_keys:
            raise ValueError("draft cohort-start marker is duplicate")
        draft_keys.add(pair)
        if marker_groups.get(key, {}).get(marker["target"]) != marker:
            raise ValueError("draft cohort-start marker is not discovered")
    if marker_groups:
        orphan_receipts = set(groups) - set(marker_groups)
        if orphan_receipts:
            raise ValueError("durable receipt has no matching cohort-start marker")
    else:
        # Compatibility is only for unit callers modelling the pre-marker branch;
        # hosted reconciliation always supplies markers and ignores pre-feature Releases.
        marker_groups = {key: {target: {} for target in key[1]} for key in groups}
        for key, markers_by_target in marker_groups.items():
            for target in set(markers_by_target) - set(groups.get(key, {})):
                draft_keys.add((key, target))

    incomplete = []
    completed = []
    for key, markers_by_target in marker_groups.items():
        group = groups.get(key, {})
        intended = set(key[1])
        if not set(group) <= intended or not set(markers_by_target) <= intended:
            raise ValueError("durable publication cohort contains an unexpected target")
        if any(target in group and target not in markers_by_target for target in group):
            raise ValueError("durable receipt target has no matching cohort-start marker")
        for target in set(group) & set(markers_by_target):
            marker = markers_by_target[target]
            if marker:  # Empty sentinels exist only for pre-marker unit compatibility.
                validate_durable_receipt_with_marker(group[target], marker)
        for target in markers_by_target:
            if target not in group and (key, target) not in draft_keys:
                raise ValueError("marker-owned Release was published without its durable receipt")
        if (set(group) != intended or set(markers_by_target) != intended
                or any((key, target) in draft_keys for target in intended)):
            incomplete.append((key, group, markers_by_target))
        else:
            completed.append(key)

    current_tags = json.dumps(current["cohort_tags"], sort_keys=True,
                              separators=(",", ":"))
    current_identity = (current["source_commit"], current["source_tree"],
                        current["ci_run_id"], current["cohort_sha256"])
    active_keys = set(_active_incomplete_cohort_keys(
        [entry[0] for entry in incomplete], completed,
        replacement_tags=current["cohort_tags"], replacement_targets=eligible,
    ))
    incomplete = [entry for entry in incomplete if entry[0] in active_keys]
    if incomplete:
        if len(incomplete) != 1:
            raise ValueError("multiple unresolved historical publication cohorts exist")
        key, group, markers_by_target = incomplete[0]
        intended = set(key[1])
        if (key[0] != current_tags or key[2:] != current_identity
                or not (set(group) | set(eligible) | set(missing) | set(markers_by_target)) <= intended):
            raise ValueError("unresolved historical cohort requires its exact original source")
        completed = {target for target in group if (key, target) not in draft_keys}
        repairs = sorted(intended - completed)
        return {"mode": "resume", "cohort_targets": list(key[1]),
                "repair_targets": repairs}

    if missing:
        raise ValueError("current publication is missing its durable receipt")
    if not eligible:
        return {"mode": "complete" if groups else "none", "cohort_targets": [],
                "repair_targets": []}
    for key, group in groups.items():
        if (key[0] == current_tags and key[2:] == current_identity
                and set(group) == set(key[1])
                and set(eligible) <= set(key[1])):
            return {"mode": "complete", "cohort_targets": list(key[1]),
                    "repair_targets": []}
    return {"mode": "start", "cohort_targets": eligible,
            "repair_targets": eligible}


def classify_durable_cohort(receipts: list[dict], *, current: dict,
                            missing_current: list[str] | None = None,
                            markers: list[dict] | None = None,
                            draft_markers: list[dict] | None = None) -> str:
    return reconcile_durable_cohort(
        receipts, current=current, missing_current=missing_current,
        markers=markers, draft_markers=draft_markers,
    )["mode"]


def validate_release_document(document: dict, tag: str, *, require_draft: bool = False) -> None:
    if document.get("tag_name") != tag:
        raise ValueError("GitHub Release does not name the exact ca-pi tag")
    if document.get("draft") is not require_draft:
        raise ValueError("GitHub Release draft state does not match the publication phase")


def _registry_document(stdout: str) -> dict:
    try:
        document = json.loads(stdout)
    except (TypeError, json.JSONDecodeError) as exc:
        raise ValueError("npm registry returned malformed JSON") from exc
    if not isinstance(document, dict):
        raise ValueError("npm registry returned a non-object response")
    return document


def classify_registry_lookup(
    returncode: int,
    stdout: str,
    stderr: str,
    expected_version: str,
    expected_integrity: str,
    *,
    package: str = PACKAGE,
) -> str:
    if returncode != 0:
        codes = {
            code.upper()
            for code in re.findall(r"\bE[A-Z0-9_]+\b", f"{stdout}\n{stderr}")
        }
        try:
            error_document = _registry_document(stdout)
        except ValueError:
            error_document = {}
        error = error_document.get("error")
        exact_404 = isinstance(error, dict) and error.get("code") == "E404"
        if codes == {"E404"} and exact_404:
            return "absent"
        retryable_codes = {
            "E429",
            "E500",
            "E502",
            "E503",
            "E504",
            "EAI_AGAIN",
            "EAI_FAIL",
            "ECONNRESET",
            "EHOSTUNREACH",
            "ENETUNREACH",
            "ENOTFOUND",
            "ERR_SOCKET_TIMEOUT",
            "ETIMEDOUT",
        }
        status_text = f"{stdout}\n{stderr}"
        retryable_http_status = re.search(
            r"(?:^|\D)(?:429|5[0-9]{2})(?:\D|$)", status_text
        )
        if (codes and codes <= retryable_codes) or (
            not codes and not exact_404 and retryable_http_status
        ):
            raise RegistryUnavailable("npm registry lookup is temporarily unavailable")
        raise ValueError("npm registry lookup failed without a confirmed 404")
    document = _registry_document(stdout)
    if document.get("version") != expected_version:
        raise ValueError("npm registry version does not match the release")
    dist = document.get("dist")
    if not isinstance(dist, dict) or dist.get("integrity") != expected_integrity:
        raise ValueError("npm registry tarball integrity does not match the packed payload")
    attestations = dist.get("attestations")
    provenance = attestations.get("provenance") if isinstance(attestations, dict) else None
    expected_attestation_url = (
        "https://registry.npmjs.org/-/npm/v1/attestations/"
        f"{package.replace('/', '%2f')}@{expected_version}"
    )
    if not isinstance(attestations, dict) or attestations.get("url") != expected_attestation_url:
        raise ValueError("npm provenance attestation URL is missing or untrusted")
    if not isinstance(provenance, dict) or provenance.get("predicateType") != PROVENANCE_PREDICATE:
        raise ValueError("npm registry has no matching SLSA provenance attestation")
    return "present"


def _integrity_hex(integrity: str) -> str:
    if not integrity.startswith("sha512-"):
        raise ValueError("expected integrity is not SHA-512")
    try:
        digest = base64.b64decode(integrity.removeprefix("sha512-"), validate=True)
    except (ValueError, binascii.Error) as exc:
        raise ValueError("expected integrity has malformed base64") from exc
    if len(digest) != 64:
        raise ValueError("expected integrity is not a complete SHA-512 digest")
    return digest.hex()


def validate_attestation_document(
    document: dict,
    version: str,
    integrity: str,
    trusted_sha: str | None,
    *,
    package: str = PACKAGE,
) -> str:
    if trusted_sha is not None:
        validate_sha(trusted_sha, "trusted workflow SHA")
    attestations = document.get("attestations")
    if not isinstance(attestations, list) or len(attestations) > 8:
        raise ValueError("npm attestation response has an invalid bounded list")
    provenance = [
        item
        for item in attestations
        if isinstance(item, dict) and item.get("predicateType") == PROVENANCE_PREDICATE
    ]
    if len(provenance) != 1:
        raise ValueError("npm response must contain exactly one SLSA provenance attestation")
    try:
        encoded = provenance[0]["bundle"]["dsseEnvelope"]["payload"]
        payload = base64.b64decode(encoded, validate=True)
        if len(payload) > ATTESTATION_MAX_BYTES:
            raise ValueError("npm provenance payload exceeds the evidence bound")
        statement = json.loads(payload.decode("utf-8"))
    except (KeyError, TypeError, UnicodeDecodeError, binascii.Error, json.JSONDecodeError) as exc:
        raise ValueError("npm provenance bundle is malformed") from exc
    if not isinstance(statement, dict) or statement.get("_type") != "https://in-toto.io/Statement/v1":
        raise ValueError("npm provenance statement type is not trusted")
    if statement.get("predicateType") != PROVENANCE_PREDICATE:
        raise ValueError("npm provenance statement predicate is not trusted")
    expected_subject = {
        "name": f"pkg:npm/{package.replace('@', '%40', 1)}@{version}",
        "digest": {"sha512": _integrity_hex(integrity)},
    }
    if statement.get("subject") != [expected_subject]:
        raise ValueError("npm provenance subject does not match the exact package tarball")
    try:
        build = statement["predicate"]["buildDefinition"]
        workflow = build["externalParameters"]["workflow"]
        dependencies = build["resolvedDependencies"]
        builder = statement["predicate"]["runDetails"]["builder"]["id"]
    except (KeyError, TypeError) as exc:
        raise ValueError("npm provenance source identity is incomplete") from exc
    if not isinstance(workflow, dict):
        raise ValueError("npm provenance workflow identity is not approved")
    if workflow != {
        "repository": SOURCE_REPOSITORY,
        "ref": SOURCE_REF,
        "path": workflow.get("path"),
    } or workflow.get("path") not in SOURCE_WORKFLOWS:
        raise ValueError("npm provenance workflow identity is not approved")
    if not isinstance(dependencies, list) or len(dependencies) != 1:
        raise ValueError("npm provenance does not bind the trusted workflow commit")
    dependency = dependencies[0]
    if not isinstance(dependency, dict) or dependency.get("uri") != (
        f"git+{SOURCE_REPOSITORY}@{SOURCE_REF}"
    ):
        raise ValueError("npm provenance does not bind the trusted workflow commit")
    digest = dependency.get("digest")
    if not isinstance(digest, dict) or set(digest) != {"gitCommit"}:
        raise ValueError("npm provenance does not bind the trusted workflow commit")
    source_sha = digest["gitCommit"]
    if not isinstance(source_sha, str):
        raise ValueError("npm provenance does not bind the trusted workflow commit")
    validate_sha(source_sha, "attested workflow SHA")
    if trusted_sha is not None and source_sha != trusted_sha:
        raise ValueError("npm provenance does not bind the trusted workflow commit")
    if builder != "https://github.com/actions/runner/github-hosted":
        raise ValueError("npm provenance builder is not GitHub-hosted")
    return source_sha


def validate_publication_attestation(document: dict, version: str, integrity: str,
                                     *, release_source_sha: str,
                                     trusted_sha: str, trusted_repo: Path,
                                     allow_continuation: bool,
                                     package: str = PACKAGE) -> str:
    """Bind npm provenance to this run or a prior authorized continuation run."""
    attestation_args = {}
    if package != PACKAGE:
        attestation_args["package"] = package
    attested = validate_attestation_document(
        document, version, integrity, None if allow_continuation else trusted_sha,
        **attestation_args,
    )
    if allow_continuation:
        validate_continuation_revision(trusted_repo, release_source_sha, attested)
        tail = _git(trusted_repo, "merge-base", "--is-ancestor", attested, trusted_sha)
        if tail.returncode != 0:
            raise ValueError("attested continuation is not contained in the trusted workflow history")
    elif attested != trusted_sha:
        raise ValueError("npm provenance does not bind the trusted workflow commit")
    return attested


def _signature_failure_detail(evidence: object) -> str:
    """Expose only fixed categories, never registry text or npm stderr."""
    if not isinstance(evidence, dict):
        return "schema=invalid"
    allowed = (
        "EINTEGRITYSIGNATURE", "EATTESTATIONVERIFY", "E503", "E502",
        "E504", "E429", "ETIMEDOUT", "ECONNRESET", "EAI_AGAIN",
    )

    def code(item: object) -> str:
        value = item.get("code") if isinstance(item, dict) else None
        return value if isinstance(value, str) and value in allowed else "unknown"

    invalid = evidence.get("invalid")
    if not isinstance(invalid, list):
        invalid_detail = "malformed"
    elif len(invalid) > 8:
        invalid_detail = "over-limit"
    else:
        invalid_detail = ",".join(sorted({code(item) for item in invalid})) or "none"
    missing = evidence.get("missing")
    missing_detail = ("yes" if missing else "no") if isinstance(missing, list) else "malformed"
    error_detail = code(evidence.get("error")) if "error" in evidence else "none"
    return f"invalid={invalid_detail}; missing={missing_detail}; error={error_detail}"


def verify_registry_authenticity(npm: str, version: str, *, package: str = PACKAGE) -> dict:
    """Use npm's supported Sigstore verifier; do not hand-roll bundle crypto."""

    with tempfile.TemporaryDirectory(prefix="codearbiter-npm-signatures-") as tmp:
        root = Path(tmp)
        user_config = root / "user.npmrc"
        global_config = root / "global.npmrc"
        user_config.write_text("", encoding="utf-8")
        global_config.write_text("", encoding="utf-8")
        npm_env = {
            key: value
            for key, value in os.environ.items()
            if not key.lower().startswith("npm_config_")
            and key.upper() not in {"NODE_AUTH_TOKEN", "NPM_TOKEN"}
        }
        npm_env.update(
            {
                "NPM_CONFIG_CACHE": str(root / "cache"),
                "NPM_CONFIG_LOGS_DIR": str(root / "logs"),
                "NPM_CONFIG_USERCONFIG": str(user_config),
                "NPM_CONFIG_GLOBALCONFIG": str(global_config),
            }
        )
        (root / "package.json").write_text(
            json.dumps(
                {
                    "name": "codearbiter-npm-signature-verifier",
                    "version": "1.0.0",
                    "private": True,
                },
                separators=(",", ":"),
            )
            + "\n",
            encoding="utf-8",
        )
        try:
            installed = subprocess.run(
                [
                    npm,
                    "install",
                    "--ignore-scripts",
                    "--no-audit",
                    "--no-fund",
                    "--save-exact",
                    f"{package}@{version}",
                    f"--registry={REGISTRY}",
                    SCOPED_REGISTRY_OPTION,
                ],
                cwd=root,
                env=npm_env,
                text=True,
                capture_output=True,
                check=False,
                timeout=60,
            )
            if installed.returncode != 0:
                raise ValueError("npm signature verification install failed")
            audited = subprocess.run(
                [
                    npm,
                    "audit",
                    "signatures",
                    "--json",
                    "--include-attestations",
                    f"--registry={REGISTRY}",
                    SCOPED_REGISTRY_OPTION,
                ],
                cwd=root,
                env=npm_env,
                text=True,
                capture_output=True,
                check=False,
                timeout=60,
            )
        except subprocess.TimeoutExpired as exc:
            raise ValueError("npm signature verification timed out") from exc
        try:
            evidence = json.loads(audited.stdout)
        except (TypeError, json.JSONDecodeError) as exc:
            raise ValueError("npm signature verification returned malformed evidence") from exc
        if (
            audited.returncode != 0
            or not isinstance(evidence, dict)
            or evidence.get("invalid") != []
            or evidence.get("missing") != []
        ):
            raise ValueError(
                "npm signature or provenance verification failed: "
                + _signature_failure_detail(evidence)
            )
        verified = evidence.get("verified")
        if not isinstance(verified, list) or len(verified) != 1:
            raise ValueError("npm signature verification did not identify one exact package")
        verified_package = verified[0]
        if not isinstance(verified_package, dict) or {
            "name": verified_package.get("name"),
            "version": verified_package.get("version"),
            "location": verified_package.get("location"),
            "registry": verified_package.get("registry"),
        } != {
            "name": package,
            "version": version,
            "location": f"node_modules/{package}",
            "registry": REGISTRY,
        }:
            raise ValueError("npm signature verification returned the wrong package identity")
        bundles = verified_package.get("attestationBundles")
        if not isinstance(bundles, list) or len(bundles) > 8:
            raise ValueError("npm signature verification returned invalid attestation evidence")
        provenance = [
            item
            for item in bundles
            if isinstance(item, dict) and item.get("predicateType") == PROVENANCE_PREDICATE
        ]
        if len(provenance) != 1:
            raise ValueError("npm signature verification returned ambiguous provenance evidence")
        return {"attestations": provenance}


def parse_pack_report(stdout: str) -> tuple[str, str]:
    try:
        report = json.loads(stdout)
        item = report[0]
        filename = item["filename"]
        integrity = item["integrity"]
    except (IndexError, KeyError, TypeError, json.JSONDecodeError) as exc:
        raise ValueError("npm pack returned malformed artifact evidence") from exc
    if (
        not isinstance(filename, str)
        or Path(filename).name != filename
        or re.fullmatch(r"[A-Za-z0-9._-]+\.tgz", filename) is None
    ):
        raise ValueError("npm pack returned an unsafe tarball path")
    if (
        not isinstance(integrity, str)
        or re.fullmatch(r"sha512-[A-Za-z0-9+/]+={0,2}", integrity) is None
    ):
        raise ValueError("npm pack did not return SHA-512 integrity")
    return filename, integrity


def registry_lookup(
    npm: str,
    version: str,
    *,
    package: str = PACKAGE,
    timeout: float = REGISTRY_TIMEOUT_SECONDS,
) -> subprocess.CompletedProcess[str]:
    try:
        return subprocess.run(
            [
                npm,
                "view",
                f"{package}@{version}",
                "version",
                "dist",
                "--json",
                f"--registry={REGISTRY}",
                SCOPED_REGISTRY_OPTION,
            ],
            text=True,
            capture_output=True,
            check=False,
            timeout=timeout,
        )
    except subprocess.TimeoutExpired as exc:
        raise RegistryUnavailable("npm registry lookup timed out") from exc


def load_prebuilt_pi_package(cohort_path: Path, tarball_path: Path, *, version: str,
                             expected_sha: str, ci_run_id: str) -> tuple[str, str]:
    """Bind npm publication to the production cohort already assembled by CI."""
    if not ci_run_id.isdecimal() or ci_run_id.startswith("0"):
        raise ValueError("CI run id must be a canonical positive integer")
    if (cohort_path.is_symlink() or not cohort_path.is_file()
            or tarball_path.is_symlink() or not tarball_path.is_file()):
        raise ValueError("prebuilt package cohort must contain real files")
    if cohort_path.resolve().parent != tarball_path.resolve().parent:
        raise ValueError("prebuilt Pi package must come from the retained cohort directory")
    cohort = json.loads(cohort_path.read_text(encoding="utf-8"))
    packages = cohort.get("packages") if isinstance(cohort, dict) else None
    package = packages.get("pi") if isinstance(packages, dict) else None
    packer = cohort.get("pi_packer") if isinstance(cohort, dict) else None
    if (cohort.get("format") != "codearbiter.artifact-package-cohort/0.1.0"
            or cohort.get("source_commit") != expected_sha
            or cohort.get("workflow") != ".github/workflows/ci.yml"
            or cohort.get("run_id") != ci_run_id
            or re.fullmatch(r"[0-9a-f]{40}", cohort.get("source_tree", "")) is None
            or re.fullmatch(r"[0-9a-f]{64}", cohort.get("promotion_receipt_sha256", "")) is None
            or not isinstance(packages, dict) or set(packages) != {"claude", "codex", "pi"}
            or not isinstance(packer, dict) or packer.get("qualification") != "production"
            or packer.get("name") != "npm" or packer.get("version") != "11.19.1"
            or packer.get("package_integrity") != NPM_PACKER_INTEGRITY
            or re.fullmatch(r"[0-9a-f]{64}", packer.get("executable_sha256", "")) is None
            or not isinstance(package, dict) or package.get("version") != version):
        raise ValueError("prebuilt Pi package is not bound to the exact production CI cohort")
    filename = package.get("file")
    if (not isinstance(filename, str) or Path(filename).name != filename
            or tarball_path.name != filename):
        raise ValueError("prebuilt Pi package filename does not match its cohort receipt")
    data = tarball_path.read_bytes()
    if (package.get("size") != len(data)
            or package.get("sha256") != hashlib.sha256(data).hexdigest()):
        raise ValueError("prebuilt Pi package bytes drifted from the cohort receipt")
    integrity = "sha512-" + base64.b64encode(hashlib.sha512(data).digest()).decode("ascii")
    return str(tarball_path.resolve()), integrity


def _codex_npm_metadata(metadata_path: Path, tarball_path: Path,
                        expected_sha: str, expected_cohort_sha256: str,
                        expected_source_archive_sha256: str) -> dict:
    if (metadata_path.is_symlink() or not metadata_path.is_file()
            or tarball_path.is_symlink() or not tarball_path.is_file()
            or metadata_path.resolve().parent != tarball_path.resolve().parent):
        raise ValueError("Codex npm package and metadata must be real sibling files")
    metadata = json.loads(
        metadata_path.read_text(encoding="utf-8"), object_pairs_hook=_unique_object
    )
    expected_fields = {
        "package", "version", "file", "size", "sha256", "integrity",
        "cohort_sha256", "source_commit", "source_archive",
        "source_archive_sha256", "members",
    }
    data = tarball_path.read_bytes()
    integrity = "sha512-" + base64.b64encode(hashlib.sha512(data).digest()).decode("ascii")
    if (not isinstance(metadata, dict) or set(metadata) != expected_fields
            or metadata.get("package") != "@arbiterforge/ca-codex"
            or CODEX_VERSION_RE.fullmatch(metadata.get("version", "")) is None
            or metadata.get("source_commit") != expected_sha
            or metadata.get("file") != tarball_path.name
            or metadata.get("size") != len(data)
            or metadata.get("sha256") != hashlib.sha256(data).hexdigest()
            or metadata.get("integrity") != integrity
            or re.fullmatch(r"[0-9a-f]{64}", expected_cohort_sha256) is None
            or metadata.get("cohort_sha256") != expected_cohort_sha256
            or re.fullmatch(r"[0-9a-f]{64}", expected_source_archive_sha256) is None
            or metadata.get("source_archive_sha256") != expected_source_archive_sha256
            or not isinstance(metadata.get("source_archive"), str)
            or Path(metadata["source_archive"]).name != metadata["source_archive"]
            or not isinstance(metadata.get("members"), dict)):
        raise ValueError("Codex npm package metadata is not bound to the exact qualified cohort")
    return metadata


def prepare_codex(args: argparse.Namespace) -> int:
    trusted_repo = Path(args.trusted_repo).resolve()
    validate_release_source_binding(
        trusted_repo, trusted_repo, args.expected_sha, args.trusted_sha,
        allow_continuation=getattr(args, "allow_continuation", False),
    )
    validate_project_registry(trusted_repo)
    metadata = _codex_npm_metadata(
        Path(args.metadata), Path(args.tarball), args.expected_sha,
        args.expected_cohort_sha256, args.expected_source_archive_sha256,
    )
    version = metadata["version"]
    integrity = metadata["integrity"]
    lookup = registry_lookup(
        args.npm, version, package="@arbiterforge/ca-codex"
    )
    state = classify_registry_lookup(
        lookup.returncode, lookup.stdout, lookup.stderr, version, integrity,
        package="@arbiterforge/ca-codex",
    )
    if state == "present":
        verified_document = verify_registry_authenticity(
            args.npm, version, package="@arbiterforge/ca-codex"
        )
        validate_publication_attestation(
            verified_document, version, integrity,
            release_source_sha=args.expected_sha, trusted_sha=args.trusted_sha,
            trusted_repo=trusted_repo,
            allow_continuation=getattr(args, "allow_continuation", False),
            package="@arbiterforge/ca-codex",
        )
    with Path(args.output).open("a", encoding="utf-8", newline="\n") as stream:
        stream.write(f"version={version}\n")
        stream.write(f"tarball={Path(args.tarball).resolve()}\n")
        stream.write(f"metadata={Path(args.metadata).resolve()}\n")
        stream.write(f"integrity={integrity}\n")
        stream.write(f"sha256={metadata['sha256']}\n")
        stream.write(f"cohort-sha256={metadata['cohort_sha256']}\n")
        stream.write(f"skip={'true' if state == 'present' else 'false'}\n")
        stream.write(f"publication-mode={'existing' if state == 'present' else 'new'}\n")
    return 0


def verify_codex(args: argparse.Namespace) -> int:
    if CODEX_VERSION_RE.fullmatch(args.version) is None:
        raise ValueError("Codex npm publication version must be exact stable SemVer")
    trusted_repo = Path(args.repo).resolve()
    validate_release_source_binding(
        trusted_repo, trusted_repo, args.expected_sha, args.trusted_sha,
        allow_continuation=getattr(args, "allow_continuation", False),
    )
    if args.attempts < 1 or args.delay_seconds < 0 or args.readback_seconds <= 0:
        raise ValueError("npm publication readback bounds are invalid")
    deadline = time.monotonic() + args.readback_seconds
    last_unavailable: RegistryUnavailable | None = None
    state = "absent"
    for attempt in range(args.attempts):
        remaining = deadline - time.monotonic()
        if remaining <= 0:
            break
        try:
            lookup = registry_lookup(
                args.npm, args.version, package="@arbiterforge/ca-codex",
                timeout=min(REGISTRY_TIMEOUT_SECONDS, remaining),
            )
            state = classify_registry_lookup(
                lookup.returncode, lookup.stdout, lookup.stderr,
                args.version, args.integrity, package="@arbiterforge/ca-codex",
            )
        except RegistryUnavailable as exc:
            last_unavailable = exc
            if attempt + 1 >= args.attempts:
                raise
            state = "unavailable"
        if state == "present":
            verified_document = verify_registry_authenticity(
                args.npm, args.version, package="@arbiterforge/ca-codex"
            )
            validate_publication_attestation(
                verified_document, args.version, args.integrity,
                release_source_sha=args.expected_sha, trusted_sha=args.trusted_sha,
                trusted_repo=trusted_repo,
                allow_continuation=getattr(args, "allow_continuation", False),
                package="@arbiterforge/ca-codex",
            )
            print(
                f"verified @arbiterforge/ca-codex@{args.version} "
                "integrity and provenance"
            )
            return 0
        remaining = deadline - time.monotonic()
        if attempt + 1 < args.attempts and remaining > 0:
            time.sleep(min(args.delay_seconds, remaining))
    if last_unavailable is not None and state == "unavailable":
        raise last_unavailable
    raise ValueError("npm publication did not become observable before the evidence deadline")


def prepare(args: argparse.Namespace) -> int:
    repo = Path(args.repo).resolve()
    trusted_repo = Path(args.trusted_repo).resolve()
    version = validate_inputs(args.tag, args.expected_sha)
    validate_release_source_binding(
        trusted_repo, repo, args.expected_sha, args.trusted_sha,
        allow_continuation=getattr(args, "allow_continuation", False),
    )
    validate_git_identity(repo, args.tag, args.expected_sha)
    validate_project_registry(repo)
    root = json.loads((repo / args.root_manifest).read_text(encoding="utf-8"))
    nested = json.loads((repo / args.plugin_manifest).read_text(encoding="utf-8"))
    validate_package_identity(root, nested, version)
    release = json.loads(Path(args.release_json).read_text(encoding="utf-8"))
    validate_release_document(
        release, args.tag, require_draft=getattr(args, "require_draft", False)
    )
    tarball, integrity = load_prebuilt_pi_package(
        Path(args.cohort), Path(args.tarball), version=version,
        expected_sha=args.expected_sha, ci_run_id=args.ci_run_id,
    )
    lookup = registry_lookup(args.npm, version)
    state = classify_registry_lookup(
        lookup.returncode, lookup.stdout, lookup.stderr, version, integrity
    )
    if state == "present":
        verified_document = verify_registry_authenticity(args.npm, version)
        source_sha = validate_publication_attestation(
            verified_document, version, integrity,
            release_source_sha=args.expected_sha, trusted_sha=args.trusted_sha,
            trusted_repo=trusted_repo,
            allow_continuation=getattr(args, "allow_continuation", False),
        )
    output = Path(args.output)
    with output.open("a", encoding="utf-8", newline="\n") as stream:
        stream.write(f"version={version}\n")
        stream.write(f"tarball={tarball}\n")
        stream.write(f"integrity={integrity}\n")
        stream.write(f"skip={'true' if state == 'present' else 'false'}\n")
        stream.write(f"publication_mode={'existing' if state == 'present' else 'new'}\n")
    return 0


def verify(args: argparse.Namespace) -> int:
    version = validate_inputs(args.tag, args.expected_sha)
    trusted_repo = Path(args.repo).resolve()
    validate_release_source_binding(
        trusted_repo, trusted_repo, args.expected_sha, args.trusted_sha,
        allow_continuation=getattr(args, "allow_continuation", False),
    )
    readback_seconds = getattr(args, "readback_seconds", REGISTRY_READBACK_SECONDS)
    if args.attempts < 1 or args.delay_seconds < 0 or readback_seconds <= 0:
        raise ValueError("npm publication readback bounds are invalid")
    deadline = time.monotonic() + readback_seconds
    last_unavailable: RegistryUnavailable | None = None
    state = "absent"
    for attempt in range(args.attempts):
        remaining = deadline - time.monotonic()
        if remaining <= 0:
            break
        try:
            lookup = registry_lookup(
                args.npm,
                version,
                timeout=min(REGISTRY_TIMEOUT_SECONDS, remaining),
            )
            state = classify_registry_lookup(
                lookup.returncode,
                lookup.stdout,
                lookup.stderr,
                version,
                args.integrity,
            )
        except RegistryUnavailable as exc:
            last_unavailable = exc
            if attempt + 1 >= args.attempts:
                raise
            state = "unavailable"
        if state == "present":
            verified_document = verify_registry_authenticity(args.npm, version)
            source_sha = validate_publication_attestation(
                verified_document,
                version,
                args.integrity,
                release_source_sha=args.expected_sha,
                trusted_sha=args.trusted_sha,
                trusted_repo=trusted_repo,
                allow_continuation=getattr(args, "allow_continuation", False),
            )
            print(f"verified {PACKAGE}@{version} integrity and provenance")
            return 0
        remaining = deadline - time.monotonic()
        if attempt + 1 < args.attempts and remaining > 0:
            time.sleep(min(args.delay_seconds, remaining))
    if last_unavailable is not None and state == "unavailable":
        raise last_unavailable
    raise ValueError("npm publication did not become observable before the evidence deadline")


def parser() -> argparse.ArgumentParser:
    result = argparse.ArgumentParser()
    sub = result.add_subparsers(dest="command", required=True)
    common = argparse.ArgumentParser(add_help=False)
    common.add_argument("--tag", required=True)
    common.add_argument("--expected-sha", required=True)
    common.add_argument("--trusted-sha", required=True)
    common.add_argument("--npm", default="npm")
    common.add_argument("--allow-continuation", action="store_true")
    sub.add_parser("validate", parents=[common])
    prepare_parser = sub.add_parser("prepare", parents=[common])
    prepare_parser.add_argument("--repo", default=".")
    prepare_parser.add_argument("--trusted-repo", required=True)
    prepare_parser.add_argument("--release-json", required=True)
    prepare_parser.add_argument("--output", required=True)
    prepare_parser.add_argument("--root-manifest", required=True)
    prepare_parser.add_argument("--plugin-manifest", required=True)
    prepare_parser.add_argument("--cohort", required=True)
    prepare_parser.add_argument("--tarball", required=True)
    prepare_parser.add_argument("--ci-run-id", required=True)
    prepare_parser.add_argument("--require-draft", action="store_true")
    verify_parser = sub.add_parser("verify", parents=[common])
    verify_parser.add_argument("--repo", default=".")
    verify_parser.add_argument("--integrity", required=True)
    verify_parser.add_argument(
        "--publication-mode", required=True, choices=("new", "existing")
    )
    verify_parser.add_argument(
        "--attempts", type=int, default=REGISTRY_READBACK_ATTEMPTS
    )
    verify_parser.add_argument(
        "--delay-seconds", type=float, default=REGISTRY_READBACK_DELAY_SECONDS
    )
    verify_parser.add_argument(
        "--readback-seconds", type=float, default=REGISTRY_READBACK_SECONDS
    )
    codex_prepare = sub.add_parser("prepare-codex")
    codex_prepare.add_argument("--metadata", required=True)
    codex_prepare.add_argument("--tarball", required=True)
    codex_prepare.add_argument("--expected-sha", required=True)
    codex_prepare.add_argument("--trusted-sha", required=True)
    codex_prepare.add_argument("--expected-cohort-sha256", required=True)
    codex_prepare.add_argument("--expected-source-archive-sha256", required=True)
    codex_prepare.add_argument("--trusted-repo", default=".")
    codex_prepare.add_argument("--npm", default="npm")
    codex_prepare.add_argument("--output", required=True)
    codex_prepare.add_argument("--allow-continuation", action="store_true")
    codex_verify = sub.add_parser("verify-codex")
    codex_verify.add_argument("--version", required=True)
    codex_verify.add_argument("--integrity", required=True)
    codex_verify.add_argument("--expected-sha", required=True)
    codex_verify.add_argument("--trusted-sha", required=True)
    codex_verify.add_argument("--repo", default=".")
    codex_verify.add_argument("--npm", default="npm")
    codex_verify.add_argument("--attempts", type=int, default=REGISTRY_READBACK_ATTEMPTS)
    codex_verify.add_argument("--delay-seconds", type=float, default=REGISTRY_READBACK_DELAY_SECONDS)
    codex_verify.add_argument("--readback-seconds", type=float, default=REGISTRY_READBACK_SECONDS)
    codex_verify.add_argument("--allow-continuation", action="store_true")
    cohort_parser = sub.add_parser("verify-cohort")
    cohort_parser.add_argument("--package-root", required=True)
    cohort_parser.add_argument("--stage-root", required=True)
    cohort_parser.add_argument("--cold-root", required=True)
    cohort_parser.add_argument("--source-repo", required=True)
    cohort_parser.add_argument("--source-commit", required=True)
    cohort_parser.add_argument("--workflow-sha", required=True)
    cohort_parser.add_argument("--ci-run-id", required=True)
    cohort_parser.add_argument("--npm", required=True)
    cohort_parser.add_argument("--trusted-repo", default=".")
    cohort_parser.add_argument("--host", required=True, choices=("claude", "codex", "pi"))
    cohort_parser.add_argument("--output", required=True)
    cohort_parser.add_argument("--allow-continuation", action="store_true")
    reconcile_parser = sub.add_parser("reconcile-state")
    reconcile_parser.add_argument("--current", required=True)
    reconcile_parser.add_argument("--state", required=True)
    reconcile_parser.add_argument("--output", required=True)
    draft_parser = sub.add_parser("qualified-draft")
    draft_parser.add_argument("--releases", required=True)
    draft_parser.add_argument("--tag", required=True)
    draft_parser.add_argument("--marker", required=True)
    draft_parser.add_argument("--asset")
    finalize_parser = sub.add_parser("qualified-finalize")
    finalize_parser.add_argument("--releases", required=True)
    finalize_parser.add_argument("--tag", required=True)
    finalize_parser.add_argument("--marker", required=True)
    finalize_parser.add_argument("--asset", action="append", default=[])
    finalize_parser.add_argument("--expected-assets")
    receipt_parser = sub.add_parser("cohort-receipt")
    receipt_parser.add_argument("--receipt", required=True)
    receipt_parser.add_argument("--marker", required=True)
    tag_parser = sub.add_parser("tag-identity")
    tag_parser.add_argument("--remote", required=True)
    tag_parser.add_argument("--tag", required=True)
    tag_parser.add_argument("--source", required=True)
    tag_parser.add_argument("--expected-object")
    return result


def main(argv: list[str] | None = None) -> int:
    args = parser().parse_args(argv)
    try:
        if args.command == "validate":
            validate_inputs(args.tag, args.expected_sha)
            validate_sha(args.trusted_sha, "trusted workflow SHA")
            if not args.allow_continuation and args.expected_sha != args.trusted_sha:
                raise ValueError("workflow, trusted verifier, and release source SHA must be identical")
            return 0
        if args.command == "verify-cohort":
            root = Path(args.package_root)
            receipt = verify_release_cohort(
                package_root=root, stage_root=Path(args.stage_root),
                cold_root=Path(args.cold_root), source_repo=Path(args.source_repo),
                source_commit=args.source_commit, ci_run_id=args.ci_run_id,
                npm_executable=Path(args.npm), trusted_repo=Path(args.trusted_repo),
                workflow_sha=args.workflow_sha,
                allow_continuation=args.allow_continuation,
            )
            package = receipt["packages"][args.host]
            cohort_path = root / "artifact-package-cohort.json"
            with Path(args.output).open("a", encoding="utf-8", newline="\n") as stream:
                stream.write(f"path={root / package['file']}\n")
                stream.write(f"file={package['file']}\n")
                stream.write(f"sha256={package['sha256']}\n")
                stream.write(f"cohort-sha256={hashlib.sha256(cohort_path.read_bytes()).hexdigest()}\n")
                stream.write(f"source-tree={receipt['source_tree']}\n")
            return 0
        if args.command == "prepare-codex":
            return prepare_codex(args)
        if args.command == "verify-codex":
            return verify_codex(args)
        if args.command == "reconcile-state":
            current = json.loads(Path(args.current).read_text(encoding="utf-8"),
                                 object_pairs_hook=_unique_object)
            state = json.loads(Path(args.state).read_text(encoding="utf-8"),
                               object_pairs_hook=_unique_object)
            if (not isinstance(state, dict)
                    or set(state) != {"receipts", "markers", "missing_current", "draft_markers"}
                    or not isinstance(state["receipts"], list)
                    or not isinstance(state["markers"], list)
                    or not isinstance(state["missing_current"], list)
                    or not isinstance(state["draft_markers"], list)):
                raise ValueError("durable publication discovery schema is not exact")
            result = reconcile_durable_cohort(
                state["receipts"], current=current,
                missing_current=state["missing_current"],
                markers=state["markers"], draft_markers=state["draft_markers"],
            )
            with Path(args.output).open("a", encoding="utf-8", newline="\n") as stream:
                stream.write(f"mode={result['mode']}\n")
                stream.write(f"cohort-targets={','.join(result['cohort_targets'])}\n")
                for target in QUALIFIED_TARGET_HOSTS:
                    stream.write(f"repair-{target}={'true' if target in result['repair_targets'] else 'false'}\n")
            return 0
        if args.command == "qualified-draft":
            pages = json.loads(Path(args.releases).read_text(encoding="utf-8"),
                               object_pairs_hook=_unique_object)
            release_id, asset_url = validate_qualified_draft_release(
                pages, args.tag, Path(args.marker).read_bytes().rstrip(b"\n"),
                asset_name=args.asset,
            )
            print(release_id, asset_url)
            return 0
        if args.command == "qualified-finalize":
            pages = json.loads(Path(args.releases).read_text(encoding="utf-8"),
                               object_pairs_hook=_unique_object)
            expected_assets = None
            if args.expected_assets:
                expected_assets = json.loads(
                    Path(args.expected_assets).read_text(encoding="utf-8"),
                    object_pairs_hook=_unique_object,
                )
            release_id, urls = validate_qualified_finalization(
                pages, args.tag, Path(args.marker).read_bytes().rstrip(b"\n"),
                allowed_assets=sorted(args.asset), expected_assets=expected_assets,
            )
            print(release_id, *(urls[name] for name in args.asset))
            return 0
        if args.command == "cohort-receipt":
            receipt = json.loads(Path(args.receipt).read_text(encoding="utf-8"),
                                 object_pairs_hook=_unique_object)
            marker = json.loads(Path(args.marker).read_text(encoding="utf-8"),
                                object_pairs_hook=_unique_object)
            validate_durable_receipt_with_marker(receipt, marker)
            return 0
        if args.command == "tag-identity":
            print(validate_remote_annotated_tag(
                Path(args.remote).read_text(encoding="utf-8"), args.tag,
                args.source, args.expected_object))
            return 0
        return prepare(args) if args.command == "prepare" else verify(args)
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        print(f"refusing npm publication: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
