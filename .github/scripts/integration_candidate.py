#!/usr/bin/env python3
"""Integration-branch candidate-version rule (major state-contract program, task P-01).

The ordinary payload-version gates compare a PR's payload against its IMMEDIATE
base and demand a strict advance. On a long-lived integration branch that rule
cannot hold: the first child PR moves `ca` to its candidate major version, and
every later child PR that changes payload again would be told to invent a fresh
version. Bumping per child walks the candidate into numbers main's own patch
stream may claim before promotion.

This module defines the ONE narrow exception, shared by both gate owners
(`payload_version_gate.py` for ca/ca-codex/ca-sandbox and
`tools/build-host-packages.py --release-guard-base` for ca-pi):

* It applies only when the CI-supplied PR base branch equals the declared
  integration branch. The branch name comes from the event context, never from
  the record, so a record cannot enrol an arbitrary base.
* Payload change is measured against the recorded MAIN baseline, not the
  immediate integration base.
* The head version must equal the declared candidate for that target, must
  strictly advance both the baseline main version and the live main version,
  and its tag must be unused.
* The recorded baseline must be an ancestor of live main AND of HEAD; a record
  naming an unrelated commit fails closed.

Any other base (main, merge_group, a fork's other branch) is untouched and keeps
the strict immediate-base rule. A malformed record on the integration base fails
closed rather than falling back to the strict rule silently.
"""

from __future__ import annotations

import json
import re
import subprocess
from dataclasses import dataclass
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
RECORD = REPO / ".github" / "integration-candidate.json"
SCHEMA = "codearbiter-integration-candidate/1"
_SHA = re.compile(r"^[0-9a-f]{40}$")
_NUMERIC = re.compile(r"^(0|[1-9]\d*)\.(0|[1-9]\d*)\.(0|[1-9]\d*)$")


class IntegrationRecordError(Exception):
    """The integration record is absent, unreadable, or not well-formed."""


@dataclass(frozen=True)
class Candidate:
    branch: str
    baseline: str
    versions: dict[str, str]


def normalize_branch(name: str | None) -> str:
    return (name or "").strip().removeprefix("refs/heads/")


def load(record_path: Path = RECORD) -> Candidate:
    try:
        data = json.loads(record_path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        raise IntegrationRecordError(f"{record_path} unreadable: {exc}") from exc
    if not isinstance(data, dict) or data.get("schema") != SCHEMA:
        raise IntegrationRecordError(f"{record_path} does not declare schema {SCHEMA}")
    branch = data.get("branch")
    baseline = data.get("baseline_main_commit")
    versions = data.get("candidates")
    if not isinstance(branch, str) or not branch or branch == "main":
        raise IntegrationRecordError("integration branch must be a non-main branch name")
    if not isinstance(baseline, str) or not _SHA.match(baseline):
        raise IntegrationRecordError("baseline_main_commit must be a full 40-hex commit SHA")
    if not isinstance(versions, dict) or not versions:
        raise IntegrationRecordError("candidates must be a non-empty object")
    for target, version in versions.items():
        if not isinstance(version, str) or not _NUMERIC.match(version):
            raise IntegrationRecordError(
                f"candidate for {target!r} must be a plain numeric MAJOR.MINOR.PATCH version, got {version!r}"
            )
    return Candidate(branch=branch, baseline=baseline, versions=dict(versions))


def select(base_branch: str | None, record_path: Path = RECORD) -> Candidate | None:
    """Return the record only when the CI base branch is the declared integration branch.

    None means "use the strict rule". `main` and an absent record always select the
    strict rule. For any other base a present-but-malformed record raises
    IntegrationRecordError: whether that base is the integration branch cannot be
    decided from a record that does not parse, so the caller fails closed.
    """
    base = normalize_branch(base_branch)
    if not base or base == "main" or not record_path.exists():
        return None
    record = load(record_path)
    return record if base == record.branch else None


def _git(root: Path, *args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(["git", *args], cwd=root, capture_output=True, text=True, encoding="utf-8", timeout=120)


def baseline_problem(record: Candidate, main_ref: str, root: Path = REPO) -> str | None:
    """Diagnose a baseline that is not a real main commit contained in HEAD."""
    if _git(root, "rev-parse", "--verify", "--quiet", f"{record.baseline}^{{commit}}").returncode != 0:
        return f"integration baseline {record.baseline} does not resolve to a commit (fetch full history)"
    if _git(root, "rev-parse", "--verify", "--quiet", f"{main_ref}^{{commit}}").returncode != 0:
        return f"{main_ref} does not resolve to a commit - fetch main before the integration gate"
    if _git(root, "merge-base", "--is-ancestor", record.baseline, main_ref).returncode != 0:
        return f"integration baseline {record.baseline} is not on {main_ref}"
    if _git(root, "merge-base", "--is-ancestor", record.baseline, "HEAD").returncode != 0:
        return f"integration baseline {record.baseline} is not contained in HEAD"
    return None


def show(root: Path, ref: str, path: str) -> str | None:
    shown = _git(root, "show", f"{ref}:{path}")
    return shown.stdout if shown.returncode == 0 else None
