#!/usr/bin/env python3
"""Verify an inert ca-codex package from an exact Git commit.

The repository named by ``--repo`` supplies candidate data only.  Executable
verification code is loaded exclusively from this script's trusted checkout.
"""

from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
from pathlib import Path
import re
import subprocess
import sys
import tempfile
from typing import Any


SCRIPT_ROOT = Path(__file__).resolve().parent
TRUSTED_CHECKER_PATH = SCRIPT_ROOT / "check_codex_skill_resources.py"
COMMIT_ID = re.compile(r"^[0-9a-f]{40}$")
SHA256_ID = re.compile(r"^[0-9a-f]{64}$")
MAX_ARCHIVE_BYTES = 8 * 1024 * 1024


def _load_trusted_checker():
    if not TRUSTED_CHECKER_PATH.is_file():
        raise ValueError("trusted static candidate checker is missing")
    spec = importlib.util.spec_from_file_location(
        "codearbiter_trusted_codex_candidate_checker", TRUSTED_CHECKER_PATH
    )
    if spec is None or spec.loader is None:
        raise ValueError("trusted static candidate checker cannot be loaded")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _git(repo: Path, *arguments: str) -> str:
    completed = subprocess.run(
        ["git", *arguments],
        cwd=repo,
        check=False,
        capture_output=True,
        text=True,
        encoding="utf-8",
    )
    if completed.returncode != 0:
        detail = completed.stderr.strip() or completed.stdout.strip() or "git failed"
        raise ValueError(detail)
    return completed.stdout.strip()


def _exact_commit(repo: Path, final_ref: str) -> tuple[str, str]:
    if COMMIT_ID.fullmatch(final_ref) is None:
        raise ValueError("--final-ref must be an exact lowercase 40-character commit ID")
    try:
        commit = _git(repo, "rev-parse", "--verify", f"{final_ref}^{{commit}}")
    except ValueError as error:
        raise ValueError("--final-ref does not resolve to a commit") from error
    if commit != final_ref:
        raise ValueError("--final-ref does not resolve to the exact requested commit")
    tree = _git(repo, "rev-parse", "--verify", f"{commit}^{{tree}}")
    if COMMIT_ID.fullmatch(tree) is None:
        raise ValueError("candidate tree is not an exact Git object ID")
    return commit, tree


def _archive(repo: Path, commit: str, destination: Path) -> None:
    if COMMIT_ID.fullmatch(commit) is None:
        raise ValueError("candidate archive source must be a 40-character commit ID")
    completed = subprocess.run(
        [
            "git",
            "archive",
            "--format=zip",
            f"--output={destination}",
            commit,
            "--",
            "plugins/ca-codex",
        ],
        cwd=repo,
        check=False,
        capture_output=True,
        text=True,
        encoding="utf-8",
    )
    if completed.returncode != 0 or not destination.is_file():
        detail = completed.stderr.strip() or completed.stdout.strip() or "git archive failed"
        raise ValueError(detail)


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as source:
        while chunk := source.read(64 * 1024):
            digest.update(chunk)
    return digest.hexdigest()


def _expected_digest(value: str | None, label: str) -> str | None:
    if value is not None and SHA256_ID.fullmatch(value) is None:
        raise ValueError(f"expected {label} must be an exact lowercase SHA-256 digest")
    return value


def verify_static_candidate(
    *,
    repo: Path,
    final_ref: str,
    expected_archive_sha256: str | None = None,
    expected_package_sha256: str | None = None,
    expected_resource_sha256: str | None = None,
) -> dict[str, Any]:
    if COMMIT_ID.fullmatch(final_ref) is None:
        raise ValueError("--final-ref must be an exact lowercase 40-character commit ID")
    repo = repo.resolve()
    if not repo.is_dir():
        raise ValueError("--repo must name an existing Git checkout")
    commit, tree = _exact_commit(repo, final_ref)
    checker = _load_trusted_checker()
    with tempfile.TemporaryDirectory(prefix="ca-codex-candidate-") as temporary:
        archive = Path(temporary) / "ca-codex.zip"
        _archive(repo, commit, archive)
        if archive.stat().st_size > MAX_ARCHIVE_BYTES:
            raise ValueError("candidate archive exceeds the archive-byte limit")
        archive_sha256 = _sha256_file(archive)
        contract = checker.candidate_static_contract(archive)
    expectations = (
        (archive_sha256, expected_archive_sha256, "archive sha256"),
        (contract["package_sha256"], expected_package_sha256, "package sha256"),
        (contract["resource_sha256"], expected_resource_sha256, "resource sha256"),
    )
    for actual, expected, label in expectations:
        expected = _expected_digest(expected, label)
        if expected is not None and actual != expected:
            raise ValueError(f"{label} does not match the expected digest")
    return {
        "verdict": "PASS",
        "source_commit": commit,
        "source_tree": tree,
        "archive_sha256": archive_sha256,
        "package_sha256": contract["package_sha256"],
        "resource_sha256": contract["resource_sha256"],
        "plugin_version": contract["plugin_version"],
        "resource_count": len(contract["selected_paths"]),
        "relative_read_count": len(contract["relative_reads"]),
    }


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Verify the exact static ca-codex package at a Git commit."
    )
    parser.add_argument("--repo", type=Path, default=Path.cwd())
    parser.add_argument("--final-ref", required=True)
    parser.add_argument("--json", action="store_true")
    parser.add_argument("--expected-archive-sha256")
    parser.add_argument("--expected-package-sha256")
    parser.add_argument("--expected-resource-sha256")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        result = verify_static_candidate(
            repo=args.repo,
            final_ref=args.final_ref,
            expected_archive_sha256=args.expected_archive_sha256,
            expected_package_sha256=args.expected_package_sha256,
            expected_resource_sha256=args.expected_resource_sha256,
        )
    except (OSError, ValueError, KeyError) as error:
        if args.json:
            print(json.dumps({"verdict": "FAIL", "errors": [str(error)]}, sort_keys=True))
        print(f"ERROR: {error}", file=sys.stderr)
        return 1
    if args.json:
        print(json.dumps(result, indent=2, sort_keys=True))
    else:
        print(
            "static ca-codex candidate verified: "
            f"{result['source_commit']} package={result['package_sha256']}"
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
