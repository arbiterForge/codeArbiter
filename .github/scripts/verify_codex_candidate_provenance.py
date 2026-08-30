#!/usr/bin/env python3
"""Verify the ca-codex candidate commit and attestation-only receipt commit."""

from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import re
import subprocess
import sys
import tempfile
from typing import Any


RECEIPT_PATH = "docs/reports/codex-desktop-candidate-resolution.json"
ATTESTATION_BUNDLE_PATH = (
    "docs/reports/evidence/codex-desktop-candidate/attestation.jsonl"
)
ATTESTATION_PATHS = frozenset((RECEIPT_PATH, ATTESTATION_BUNDLE_PATH))
CANDIDATE_OWNED_PATHS = (
    ".github/actions",
    ".github/scripts",
    ".github/workflows",
    "CHANGELOG.md",
    "README.md",
    "core",
    "package.json",
    "plugins/ca",
    "plugins/ca-codex",
    "plugins/ca-pi",
    "tools",
)
CHECKER_PATH = Path(__file__).with_name("check_codex_skill_resources.py")
OBJECT_ID_RE = re.compile(r"[0-9a-f]{40}")
SHA256_RE = re.compile(r"[0-9a-f]{64}")


def _object_id(value: Any, label: str) -> str:
    if not isinstance(value, str) or not OBJECT_ID_RE.fullmatch(value):
        raise ValueError(f"{label} must be an exact lowercase 40-hex object ID")
    return value


def _sha256(value: Any, label: str) -> str:
    if not isinstance(value, str) or not SHA256_RE.fullmatch(value):
        raise ValueError(f"{label} must be an exact lowercase SHA-256 digest")
    return value


def _git(repo: Path, *args: str, text: bool = True) -> str | bytes:
    completed = subprocess.run(
        ["git", *args],
        cwd=repo,
        check=True,
        capture_output=True,
        text=text,
        encoding="utf-8" if text else None,
    )
    return completed.stdout.strip() if text else completed.stdout


def _load_candidate_reader():
    spec = importlib.util.spec_from_file_location("codex_skill_resources", CHECKER_PATH)
    if spec is None or spec.loader is None:
        raise RuntimeError("could not load the ca-codex candidate reader")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module._candidate_package_files


def _load_checker():
    spec = importlib.util.spec_from_file_location("codex_skill_resources", CHECKER_PATH)
    if spec is None or spec.loader is None:
        raise RuntimeError("could not load the ca-codex receipt verifier")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _archive(repo: Path, revision: str, destination: Path) -> None:
    revision = _object_id(revision, "archive revision")
    subprocess.run(
        [
            "git",
            "archive",
            "--format=zip",
            f"--output={destination}",
            revision,
            "--",
            "plugins/ca-codex",
        ],
        cwd=repo,
        check=True,
        capture_output=True,
    )


def _attestation_only_changes(repo: Path, candidate: str, head: str) -> list[str]:
    raw = _git(repo, "diff", "--name-status", "-z", f"{candidate}..{head}", text=False)
    fields = raw.split(b"\0")
    if fields and fields[-1] == b"":
        fields.pop()
    if len(fields) % 2:
        raise ValueError("could not parse commit-R changed paths")

    paths: list[str] = []
    for index in range(0, len(fields), 2):
        status = fields[index].decode("ascii", errors="strict")
        path = fields[index + 1].decode("utf-8", errors="strict")
        if status != "A":
            raise ValueError(f"commit R must only add attestation files; found {status} {path}")
        if path not in ATTESTATION_PATHS:
            raise ValueError(f"commit R added an unexpected attestation path: {path}")
        paths.append(path)

    if RECEIPT_PATH not in paths:
        raise ValueError("commit R must add the candidate resolution receipt")
    if ATTESTATION_BUNDLE_PATH not in paths:
        raise ValueError("commit R must add the detached attestation bundle")
    return paths


def _candidate_owned_manifest(repo: Path, revision: str) -> dict[str, str]:
    """Return exact tree entries for every source/input/output owned by C."""
    revision = _object_id(revision, "candidate-owned tree revision")
    raw = _git(
        repo, "ls-tree", "-r", "-z", "--full-tree", revision, "--",
        *CANDIDATE_OWNED_PATHS, text=False,
    )
    manifest: dict[str, str] = {}
    for entry in raw.split(b"\0"):
        if not entry:
            continue
        metadata, path_bytes = entry.split(b"\t", 1)
        mode, kind, object_id = metadata.decode("ascii").split(" ")
        path = path_bytes.decode("utf-8", errors="strict")
        manifest[path] = f"{mode} {kind} {object_id}"
    return manifest


def _verify_candidate_owned_manifest(repo: Path, candidate: str, tree: str) -> int:
    candidate_manifest = _candidate_owned_manifest(repo, candidate)
    tree_manifest = _candidate_owned_manifest(repo, tree)
    if candidate_manifest != tree_manifest:
        changed = sorted(set(candidate_manifest) ^ set(tree_manifest))
        changed.extend(
            path for path in set(candidate_manifest) & set(tree_manifest)
            if candidate_manifest[path] != tree_manifest[path]
        )
        sample = ", ".join(sorted(set(changed))[:5])
        raise ValueError(
            "the synthesized merge changes candidate-owned source or gates"
            + (f": {sample}" if sample else "")
        )
    return len(candidate_manifest)


def verify_pr_candidate_graph(
    *, repo: Path, receipt: dict[str, Any], base: str, head: str
) -> dict[str, Any]:
    """Fail closed unless C→R and the synthesized merge preserve the payload."""
    repo = repo.resolve()
    candidate_data = receipt.get("candidate")
    if not isinstance(candidate_data, dict):
        raise ValueError("receipt candidate object is missing")
    candidate = _object_id(candidate_data.get("source_commit"), "candidate commit")
    expected_tree = _object_id(candidate_data.get("source_tree"), "candidate tree")
    expected_archive_sha256 = _sha256(
        candidate_data.get("archive_sha256"), "candidate archive digest"
    )
    base = _object_id(base, "base commit")
    head = _object_id(head, "head commit")

    actual_tree = _git(repo, "rev-parse", f"{candidate}^{{tree}}")
    if actual_tree != expected_tree:
        raise ValueError("candidate commit tree does not match the receipt")
    ancestor = subprocess.run(
        ["git", "merge-base", "--is-ancestor", candidate, head],
        cwd=repo,
        check=False,
        capture_output=True,
    )
    if ancestor.returncode != 0:
        raise ValueError("candidate commit C is not an ancestor of head")

    commit_r_count = int(_git(repo, "rev-list", "--count", f"{candidate}..{head}"))
    if commit_r_count != 1:
        raise ValueError("head must contain exactly one attestation-only commit after C")
    _attestation_only_changes(repo, candidate, head)

    merge_tree_output = str(_git(repo, "merge-tree", "--write-tree", base, head))
    merge_tree = merge_tree_output.splitlines()[0]
    candidate_owned_file_count = _verify_candidate_owned_manifest(
        repo, candidate, merge_tree
    )
    candidate_reader = _load_candidate_reader()
    with tempfile.TemporaryDirectory() as temporary:
        directory = Path(temporary)
        candidate_archive = directory / "candidate.zip"
        merge_archive = directory / "merge.zip"
        _archive(repo, candidate, candidate_archive)
        archive_sha256 = hashlib.sha256(candidate_archive.read_bytes()).hexdigest()
        if archive_sha256 != expected_archive_sha256:
            raise ValueError("candidate archive digest does not match the receipt")
        _archive(repo, merge_tree, merge_archive)
        candidate_files = candidate_reader(candidate_archive)
        merge_files = candidate_reader(merge_archive)
    if candidate_files != merge_files:
        raise ValueError("the synthesized merge changes the attested ca-codex payload")

    return {
        "candidate_commit": candidate,
        "candidate_file_count": len(candidate_files),
        "candidate_owned_file_count": candidate_owned_file_count,
        "commit_r_count": commit_r_count,
        "attestation_paths": _attestation_only_changes(repo, candidate, head),
    }


def verify_release_candidate_payload(
    *,
    repo: Path,
    receipt: dict[str, Any],
    final_ref: str,
    candidate_archive: Path,
) -> dict[str, Any]:
    """Compare final-main content with the downloaded, attested candidate bytes."""
    repo = repo.resolve()
    candidate_data = receipt.get("candidate")
    if not isinstance(candidate_data, dict):
        raise ValueError("receipt candidate object is missing")
    candidate = _object_id(candidate_data.get("source_commit"), "candidate commit")
    expected_archive_sha256 = _sha256(
        candidate_data.get("archive_sha256"), "candidate archive digest"
    )
    final_ref = _object_id(final_ref, "final commit")

    actual_archive_sha256 = hashlib.sha256(candidate_archive.read_bytes()).hexdigest()
    if actual_archive_sha256 != expected_archive_sha256:
        raise ValueError("downloaded candidate archive digest does not match the receipt")

    candidate_reader = _load_candidate_reader()
    with tempfile.TemporaryDirectory() as temporary:
        final_archive = Path(temporary) / "final-main.zip"
        _archive(repo, final_ref, final_archive)
        candidate_files = candidate_reader(candidate_archive)
        final_files = candidate_reader(final_archive)
    if candidate_files != final_files:
        raise ValueError("final-main ca-codex payload differs from the attested candidate")

    return {
        "candidate_commit": candidate,
        "candidate_file_count": len(candidate_files),
        "final_ref": final_ref,
    }


def verify_merge_group_candidate(
    *, repo: Path, receipt: dict[str, Any], head: str
) -> dict[str, Any]:
    """Recheck trusted candidate bytes against a merge-queue synthesis."""
    candidate_data = receipt.get("candidate")
    candidate = _object_id(
        candidate_data.get("source_commit") if isinstance(candidate_data, dict) else None,
        "candidate commit",
    )
    head = _object_id(head, "merge-group head")
    ancestor = subprocess.run(
        ["git", "merge-base", "--is-ancestor", candidate, head],
        cwd=repo,
        check=False,
        capture_output=True,
    )
    if ancestor.returncode != 0:
        raise ValueError("candidate commit C is not an ancestor of the merge group")
    with tempfile.TemporaryDirectory() as temporary:
        archive = Path(temporary) / "candidate.zip"
        _archive(repo, candidate, archive)
        result = verify_release_candidate_payload(
            repo=repo,
            receipt=receipt,
            final_ref=head,
            candidate_archive=archive,
        )
    candidate_owned_file_count = _verify_candidate_owned_manifest(repo, candidate, head)
    return {
        **result,
        "candidate_owned_file_count": candidate_owned_file_count,
        "merge_group_head": head,
    }


def _mapping(receipt: dict[str, Any], name: str) -> dict[str, Any]:
    value = receipt.get(name)
    if not isinstance(value, dict):
        raise ValueError(f"receipt {name} object is missing")
    return value


def verify_strict_receipt(
    receipt_path: Path, candidate_archive: Path, *, bundle_path: Path
) -> None:
    """Reuse the protected desktop receipt and GitHub attestation verifier."""
    try:
        receipt = json.loads(receipt_path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as error:
        raise ValueError("candidate receipt is not valid UTF-8 JSON") from error
    if not isinstance(receipt, dict):
        raise ValueError("candidate receipt must be a JSON object")
    candidate = _mapping(receipt, "candidate")
    desktop = _mapping(receipt, "desktop")
    workflow = _mapping(receipt, "workflow")
    arguments = {
        "receipt_path": receipt_path,
        "candidate_package": candidate_archive,
        "candidate_source_commit": candidate.get("source_commit"),
        "candidate_tree": candidate.get("source_tree"),
        "desktop_build": desktop.get("build"),
        "desktop_runtime_version": desktop.get("runtime_version"),
        "workflow_run_id": workflow.get("run_id"),
        "workflow_commit": workflow.get("commit"),
    }
    checker = _load_checker()
    preliminary = checker.validate_desktop_receipt(**arguments, attestation=None)
    if preliminary.get("verdict") != "PASS":
        raise ValueError("candidate receipt content or candidate binding is invalid")
    attestation = checker.verify_github_attestation(
        receipt_path,
        str(workflow.get("commit", "")),
        str(workflow.get("run_id", "")),
        bundle_path=bundle_path,
    )
    verified = checker.validate_desktop_receipt(**arguments, attestation=attestation)
    if verified.get("verdict") != "PASS":
        raise ValueError("candidate receipt GitHub attestation is invalid")


def _load_receipt(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as error:
        raise ValueError("candidate receipt is not valid UTF-8 JSON") from error
    if not isinstance(value, dict):
        raise ValueError("candidate receipt must be a JSON object")
    return value


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--mode", choices=("pr", "merge-group", "release"), required=True)
    parser.add_argument("--repo", default=".")
    parser.add_argument("--receipt", required=True)
    parser.add_argument("--base")
    parser.add_argument("--head")
    parser.add_argument("--final-ref")
    parser.add_argument("--candidate-archive")
    parser.add_argument("--allow-missing-receipt", action="store_true")
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args(argv)
    repo = Path(args.repo).resolve()
    receipt_path = Path(args.receipt).absolute()
    bundle_path = (repo / ATTESTATION_BUNDLE_PATH).resolve()

    if args.mode == "pr":
        if not args.base or not args.head or args.final_ref or args.candidate_archive:
            parser.error("PR mode requires --base and --head only")
    elif args.mode == "merge-group":
        if not args.head or args.base or args.final_ref or args.candidate_archive:
            parser.error("merge-group mode requires --head only")
    else:
        if not args.final_ref or not args.candidate_archive or args.base or args.head:
            parser.error("release mode requires --final-ref and --candidate-archive only")
        if args.allow_missing_receipt:
            parser.error("--allow-missing-receipt is not valid in release mode")

    if args.allow_missing_receipt and not os.path.lexists(receipt_path):
        result = {
            "verdict": "NOT_APPLICABLE",
            "reason": "desktop receipt not supplied",
        }
        if args.json:
            print(json.dumps(result, indent=2, sort_keys=True))
        else:
            print("ca-codex candidate provenance NOT_APPLICABLE (desktop receipt not supplied)")
        return 0

    try:
        receipt = _load_receipt(receipt_path)
    except ValueError as error:
        print(f"ERROR: {error}", file=sys.stderr)
        return 1
    try:
        candidate = _object_id(
            _mapping(receipt, "candidate").get("source_commit"), "candidate commit"
        )
    except ValueError as error:
        parser.error(str(error))

    try:
        if args.mode == "pr":
            with tempfile.TemporaryDirectory() as temporary:
                archive = Path(temporary) / "candidate.zip"
                _archive(repo, candidate, archive)
                verify_strict_receipt(receipt_path, archive, bundle_path=bundle_path)
            result = verify_pr_candidate_graph(
                repo=repo, receipt=receipt, base=args.base, head=args.head
            )
        elif args.mode == "merge-group":
            with tempfile.TemporaryDirectory() as temporary:
                archive = Path(temporary) / "candidate.zip"
                _archive(repo, candidate, archive)
                verify_strict_receipt(receipt_path, archive, bundle_path=bundle_path)
            result = verify_merge_group_candidate(
                repo=repo, receipt=receipt, head=args.head
            )
        else:
            archive = Path(args.candidate_archive).resolve()
            verify_strict_receipt(receipt_path, archive, bundle_path=bundle_path)
            result = verify_release_candidate_payload(
                repo=repo,
                receipt=receipt,
                final_ref=args.final_ref,
                candidate_archive=archive,
            )
    except (OSError, subprocess.CalledProcessError, ValueError) as error:
        print(f"ERROR: {error}", file=sys.stderr)
        return 1

    if args.json:
        print(json.dumps({"verdict": "PASS", **result}, indent=2, sort_keys=True))
    else:
        print(
            "ca-codex candidate provenance PASS "
            f"({result['candidate_file_count']} package files)"
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
