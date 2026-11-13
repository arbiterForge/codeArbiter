#!/usr/bin/env python3
"""Typed qualification outcomes, kept separate from process exit codes (R-06).

Several checks exit 0 for different reasons: the evidence was verified, the
check was deliberately skipped (no token, optional host absent), or part of the
evidence could not be read. Their exit codes stay compatible for ordinary CI,
but a green exit is not evidence. Each check can now also write one
observation naming what it actually established:

  verified        affirmative evidence for the named scope
  skipped         deliberately not evaluated (optional prerequisite absent)
  unavailable     attempted, but the evidence could not be read (403, 5xx, ...)
  rejected        evidence was read and it violates the requirement
  not-applicable  the requirement does not apply; needs evidence + rationale

Each consumer declares which outcomes satisfy it. Ordinary advisory lanes keep
their old exit behavior. A required major-readiness consumer accepts only
`verified`, plus `not-applicable` when that exact check was declared N/A-able
and the observation carries evidence and a rationale. A skipped, unavailable,
rejected, missing or duplicated required observation never counts as passed.
"""
from __future__ import annotations

import json
import os
import re
import subprocess
from pathlib import Path

FORMAT = "codearbiter.qualification-observation/0.1.0"
OUTCOMES = ("verified", "skipped", "unavailable", "rejected", "not-applicable")
SHA = re.compile(r"[0-9a-f]{40}")


class VerdictError(ValueError):
    """An observation is malformed and cannot be evaluated."""


def source_identity(repo: str = "", root: Path | None = None) -> dict[str, str]:
    """The exact source a check ran against: repository and commit."""
    commit = os.environ.get("GITHUB_SHA", "")
    if SHA.fullmatch(commit) is None:
        try:
            done = subprocess.run(["git", "rev-parse", "HEAD"], cwd=root or Path.cwd(),
                                  capture_output=True, text=True, timeout=30)
            commit = done.stdout.strip() if done.returncode == 0 else ""
        except (OSError, subprocess.SubprocessError):
            commit = ""
    return {"repository": repo or os.environ.get("GITHUB_REPOSITORY", ""),
            "commit": commit if SHA.fullmatch(commit) else "unknown"}


def observation(check: str, outcome: str, reason: str, *, scope: str,
                source: dict[str, str] | None = None, exit_code: int | None = None,
                evidence: list[str] | None = None) -> dict:
    if outcome not in OUTCOMES:
        raise VerdictError(f"unknown outcome {outcome!r}")
    if not check or not scope or not reason:
        raise VerdictError("an observation needs a check, scope and reason")
    record = {"format": FORMAT, "check": check, "outcome": outcome, "reason": reason,
              "scope": scope, "source": source or source_identity()}
    if exit_code is not None:
        record["exit_code"] = exit_code
    if evidence:
        record["evidence"] = list(evidence)
    return record


def write(record: dict, path: str | os.PathLike | None) -> None:
    """Append one observation as a JSON line when a path was requested."""
    if not path:
        return
    with open(path, "a", encoding="utf-8", newline="\n") as stream:
        stream.write(json.dumps(record, sort_keys=True) + "\n")


def read(path: str | os.PathLike) -> list[dict]:
    records = []
    for number, line in enumerate(Path(path).read_text(encoding="utf-8").splitlines(), 1):
        if not line.strip():
            continue
        try:
            record = json.loads(line)
        except json.JSONDecodeError as exc:
            raise VerdictError(f"observation line {number} is not JSON") from exc
        validate(record)
        records.append(record)
    return records


def validate(record) -> None:
    if not isinstance(record, dict) or record.get("format") != FORMAT:
        raise VerdictError("observation has an unknown format")
    if record.get("outcome") not in OUTCOMES:
        raise VerdictError(f"observation has unknown outcome {record.get('outcome')!r}")
    for key in ("check", "reason", "scope"):
        if not isinstance(record.get(key), str) or not record[key]:
            raise VerdictError(f"observation lacks {key}")
    source = record.get("source")
    if not isinstance(source, dict) or not isinstance(source.get("commit"), str):
        raise VerdictError("observation lacks its source identity")


def satisfies(record: dict, accepted: set[str] | frozenset[str]) -> bool:
    validate(record)
    return record["outcome"] in accepted


def require(records: list[dict], required: list[str], *, commit: str,
            not_applicable_allowed: frozenset[str] = frozenset()) -> list[str]:
    """Problems that stop a REQUIRED consumer; empty means every check passed.

    Every required check needs exactly one observation for `commit` whose
    outcome is affirmative. This is the major-readiness acceptance rule.
    """
    problems: list[str] = []
    for record in records:
        validate(record)
    for check in required:
        found = [r for r in records if r["check"] == check]
        if not found:
            problems.append(f"{check}: no observation (missing evidence is not a pass)")
            continue
        if len(found) > 1:
            problems.append(f"{check}: {len(found)} observations; exactly one is required")
            continue
        record = found[0]
        if record["source"].get("commit") != commit:
            problems.append(f"{check}: observed {record['source'].get('commit')}, not {commit}")
            continue
        outcome = record["outcome"]
        if outcome == "verified":
            continue
        if outcome == "not-applicable":
            if check not in not_applicable_allowed:
                problems.append(f"{check}: not-applicable is not a declared outcome for it")
            elif not record.get("evidence"):
                problems.append(f"{check}: not-applicable without evidence")
            continue
        problems.append(f"{check}: {outcome} ({record['reason']})")
    return problems
