#!/usr/bin/env python3
"""Fail closed when a commit would be rejected by auto-release preflight.

This is the shared, read-only candidate-authorization check used by required
CI and release.yml. It deliberately performs no API calls and no mutation.
"""

from __future__ import annotations

import argparse
import importlib.util
import json
import os
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[2]
RELEASELIB_PATH = Path(__file__).with_name("_releaselib.py")


def _load_release_lib():
    spec = importlib.util.spec_from_file_location("candidate_release_lib", RELEASELIB_PATH)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"could not load {RELEASELIB_PATH}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


RELEASELIB = _load_release_lib()


class CandidateError(RuntimeError):
    """The selected commit is not an authorized automatic-release candidate."""


@dataclass(frozen=True)
class TargetResult:
    target: str
    version: str
    eligible: bool


def _git(repo: Path, *args: str, check: bool = True) -> subprocess.CompletedProcess[str]:
    result = subprocess.run(
        ["git", *args], cwd=repo, capture_output=True, text=True, timeout=30
    )
    if check and result.returncode != 0:
        detail = result.stderr.strip() or result.stdout.strip() or f"exit {result.returncode}"
        raise CandidateError(f"git {' '.join(args)} failed: {detail}")
    return result


def _commit(repo: Path, revision: str) -> str:
    value = _git(repo, "rev-parse", "--verify", f"{revision}^{{commit}}").stdout.strip()
    if len(value) != 40:
        raise CandidateError(f"could not resolve commit {revision!r}")
    return value


def _value_at(repo: Path, commit: str, path: str) -> bytes:
    result = subprocess.run(
        ["git", "show", f"{commit}:{path}"], cwd=repo, capture_output=True, timeout=30
    )
    if result.returncode != 0:
        raise CandidateError(f"release surface {path} is absent from {commit}")
    return result.stdout


def _manifest_version(repo: Path, commit: str, path: str) -> str:
    try:
        value = json.loads(_value_at(repo, commit, path).decode("utf-8"))["version"]
    except (UnicodeDecodeError, json.JSONDecodeError, KeyError, TypeError) as exc:
        raise CandidateError(f"manifest {path} has no valid version at {commit}") from exc
    if not isinstance(value, str) or not value:
        raise CandidateError(f"manifest {path} has no valid version at {commit}")
    return value


def _as_list(value) -> list[str]:
    if isinstance(value, list):
        return value
    return [value] if isinstance(value, str) and value else []


def _intent_paths(row) -> list[str]:
    """Return the declared, target-specific release-intent surface."""
    paths: list[str] = []
    for field in ("manifest", "generated-manifest", "changelog", "payload", "artifacts"):
        for path in _as_list(row.get(field)):
            if path not in paths:
                paths.append(path)
    for path in _as_list(row.get("payload-exclude")):
        paths.append(f":(exclude){path}")
    return paths


def _run_pre_tag(repo: Path, targets: list[TargetResult]) -> None:
    python = sys.executable
    environment = {"PATH": os.environ.get("PATH", ""), "PY": python}
    if os.environ.get("SYSTEMROOT"):
        environment["SYSTEMROOT"] = os.environ["SYSTEMROOT"]
    for result in targets:
        if not result.eligible:
            continue
        completed = subprocess.run(
            [python, "core/pysrc/_releaselib.py", "run-pre-tag", result.target],
            cwd=repo,
            env=environment,
            timeout=600,
        )
        if completed.returncode != 0:
            raise CandidateError(
                f"{result.target} declared pre-tag checks failed with exit "
                f"{completed.returncode}"
            )


def evaluate_candidate(
    repo: Path,
    candidate: str,
    targets_path: Path | None = None,
) -> list[TargetResult]:
    """Return target eligibility or raise CandidateError on predictable rejection."""
    repo = repo.resolve()
    candidate = _commit(repo, candidate)
    target_file = targets_path or repo / ".codearbiter" / "release-targets.md"
    rows = RELEASELIB.load_targets(str(target_file))
    tags = _git(repo, "tag", "-l").stdout.split()
    results: list[TargetResult] = []

    for row in rows:
        target = row["target"]
        manifests = _as_list(row.get("manifest"))
        changelog = row.get("changelog")
        prefix = row.get("prefix")
        if not manifests or not isinstance(changelog, str) or not isinstance(prefix, str):
            raise CandidateError(f"{target} has incomplete release declarations")
        versions = [_manifest_version(repo, candidate, path) for path in manifests]
        if len(set(versions)) != 1:
            raise CandidateError(f"{target} manifests disagree at {candidate}: {versions}")
        version = versions[0]
        last_tag = RELEASELIB.last_tag_select(tags, prefix)
        if (last_tag != RELEASELIB.NONE_SENTINEL
                and RELEASELIB.semver_greater(
                    RELEASELIB._bare_version(last_tag), version
                )):
            raise CandidateError(
                f"{target} manifest {version} is behind published tag {last_tag}"
            )
        eligible = (
            last_tag == RELEASELIB.NONE_SENTINEL
            or RELEASELIB.semver_greater(version, RELEASELIB._bare_version(last_tag))
        )
        print(f"{target}: manifest={version} eligible={'true' if eligible else 'false'}")
        results.append(TargetResult(target, version, eligible))
        if not eligible:
            continue

        changed_at = _git(
            repo, "log", "--first-parent", "-1", "--format=%H", candidate, "--", changelog
        ).stdout.strip()
        if not changed_at:
            raise CandidateError(f"{target} release surface {changelog} has no intent commit")
        intent_version = _manifest_version(repo, changed_at, manifests[0])
        unchanged_intent = _git(
            repo,
            "diff",
            "--quiet",
            changed_at,
            candidate,
            "--",
            *_intent_paths(row),
            check=False,
        ).returncode == 0
        if intent_version != version or not unchanged_intent:
            raise CandidateError(
                f"{target} release intent at {changed_at} does not bind the current "
                f"{version} payload"
            )
        for surface in (*manifests, changelog):
            _value_at(repo, candidate, surface)

    return results


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--repo", type=Path, default=REPO_ROOT)
    parser.add_argument("--candidate", default="HEAD")
    parser.add_argument("--run-pre-tag", action="store_true")
    args = parser.parse_args(argv)
    try:
        results = evaluate_candidate(args.repo, args.candidate)
        if args.run_pre_tag:
            _run_pre_tag(args.repo.resolve(), results)
    except (CandidateError, RELEASELIB.ReleaseTargetsError) as exc:
        print(f"::error::{exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
