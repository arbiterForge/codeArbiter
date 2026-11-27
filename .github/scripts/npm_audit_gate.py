#!/usr/bin/env python3
"""Judge npm audit JSON with dated exceptions for exact build and tool lockfiles.

A high or critical finding blocks unless the exact advisory, package, severity,
lockfile and audited scope are covered by a current maintainer approval. Tool
production audits are independent and have no exception path.
"""
from __future__ import annotations

import argparse
from collections import Counter, defaultdict, deque
from datetime import date, timedelta
import hashlib
import json
from pathlib import Path
import re
import sys
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[2]
SCHEMA = "codearbiter-npm-audit-exceptions-v2"
SEVERITIES = ("info", "low", "moderate", "high", "critical")
LOCKFILE_SCOPES = {
    "site/package-lock.json": "production",
    "plugins/ca/tools/package-lock.json": "full",
    "plugins/ca-sandbox/tools/package-lock.json": "full",
    "plugins/ca-pi/tools/package-lock.json": "full",
}
EXCEPTION_FIELDS = {"ghsa", "package", "severity", "reason", "approved_by", "approved_on", "backstop", "lockfiles"}
MAX_BACKSTOP_DAYS = 30
GHSA = re.compile(r"^GHSA(?:-[23456789cfghjmpqrvwx]{4}){3}$")
ADVISORY_URL = "https://github.com/advisories/"
PACKAGE = re.compile(r"^(?:@[a-z0-9][a-z0-9._~-]*/)?[a-z0-9][a-z0-9._~-]*$")
SHA256 = re.compile(r"[0-9a-f]{64}")


class GateError(ValueError):
    """A report or exception record the gate refuses to trust."""


def unique_object(items):
    result = {}
    for key, value in items:
        if key in result:
            raise GateError("duplicate JSON field")
        result[key] = value
    return result


def load_exceptions(path: Path, today: date) -> dict[tuple[str, str], dict[str, Any]]:
    try:
        document = json.loads(path.read_text(encoding="utf-8"), object_pairs_hook=unique_object)
    except (OSError, ValueError) as error:
        raise GateError(f"audit exceptions are unreadable: {path}") from error
    if not isinstance(document, dict) or set(document) != {"schema", "exceptions"} or document["schema"] != SCHEMA:
        raise GateError("audit exceptions have missing or unknown fields")
    records = document["exceptions"]
    if not isinstance(records, list):
        raise GateError("audit exceptions must be a list")
    accepted: dict[tuple[str, str], dict[str, Any]] = {}
    for item in records:
        if not isinstance(item, dict) or set(item) != EXCEPTION_FIELDS:
            raise GateError("audit exception record is malformed")
        if (
            not isinstance(item["ghsa"], str) or GHSA.fullmatch(item["ghsa"]) is None
            or not isinstance(item["package"], str) or PACKAGE.fullmatch(item["package"]) is None
            or item["severity"] not in SEVERITIES
            or not isinstance(item["reason"], str) or not item["reason"].strip()
            or not isinstance(item["approved_by"], str) or not item["approved_by"].strip()
        ):
            raise GateError("audit exception record is malformed")
        lockfiles = item["lockfiles"]
        if (not isinstance(lockfiles, dict) or not lockfiles
                or any(path not in LOCKFILE_SCOPES or not isinstance(digest, str)
                       or not SHA256.fullmatch(digest) for path, digest in lockfiles.items())):
            raise GateError("audit exception lockfiles are malformed or out of scope")
        try:
            approved = date.fromisoformat(str(item["approved_on"]))
            backstop = date.fromisoformat(str(item["backstop"]))
        except ValueError as error:
            raise GateError("audit exception dates are invalid") from error
        if not approved <= backstop <= approved + timedelta(days=MAX_BACKSTOP_DAYS):
            raise GateError(f"{item['ghsa']} backstop is outside its approval window")
        if approved > today:
            raise GateError(f"{item['ghsa']} approval date {approved} is in the future")
        if today > backstop:
            raise GateError(f"{item['ghsa']} exception expired on {backstop}; re-review or remove it")
        key = (item["ghsa"], item["package"])
        if key in accepted:
            raise GateError(f"{item['ghsa']} is recorded twice for {item['package']}")
        accepted[key] = item
    return accepted


def applicable_exceptions(accepted, repo: Path, cwd: Path, scope: str):
    directory = cwd.resolve()
    lockfile = directory / "package-lock.json"
    root = repo.resolve()
    if not directory.is_relative_to(root):
        raise GateError("audit working directory is outside the repository")
    relative = lockfile.relative_to(root).as_posix()
    if LOCKFILE_SCOPES.get(relative) != scope:
        return {}
    applicable = {key: item for key, item in accepted.items() if relative in item["lockfiles"]}
    if applicable:
        try:
            if lockfile.resolve(strict=True) != lockfile or not lockfile.is_file():
                raise OSError("unresolved lockfile")
            digest = hashlib.sha256(lockfile.read_bytes()).hexdigest()
        except OSError as error:
            raise GateError(f"cannot verify audit exception lockfile: {relative}") from error
        if any(item["lockfiles"][relative] != digest for item in applicable.values()):
            raise GateError(f"audit exception lockfile changed: {relative}")
    return applicable


def findings(report_text: str) -> list[tuple[str, str, str]]:
    """Return direct findings after validating the vulnerability inventory."""
    try:
        report = json.loads(report_text, object_pairs_hook=unique_object)
    except ValueError as error:
        raise GateError("npm audit report is unreadable") from error
    if (not isinstance(report, dict) or "error" in report
            or type(report.get("auditReportVersion")) is not int or report["auditReportVersion"] != 2):
        raise GateError("npm audit did not produce a supported report")
    vulnerabilities = report.get("vulnerabilities")
    metadata = report.get("metadata")
    counts = metadata.get("vulnerabilities") if isinstance(metadata, dict) else None
    if not isinstance(vulnerabilities, dict) or not isinstance(counts, dict):
        raise GateError("npm audit report has no vulnerability inventory or metadata")

    declared = Counter()
    found = []
    dependents = defaultdict(set)
    confirmed = {}
    for name, entry in vulnerabilities.items():
        if (not PACKAGE.fullmatch(name) or not isinstance(entry, dict) or entry.get("name") != name
                or entry.get("severity") not in SEVERITIES or not isinstance(entry.get("via"), list)
                or not entry["via"]):
            raise GateError("npm audit report entry is malformed")
        declared[entry["severity"]] += 1
        for source in entry["via"]:
            if isinstance(source, str):
                if source not in vulnerabilities:
                    raise GateError(f"npm audit report has an unresolved reference at {name}")
                dependents[source].add(name)
                continue
            if (not isinstance(source, dict) or source.get("name") != name or source.get("dependency") != name
                    or not isinstance(source.get("url"), str) or source.get("severity") not in SEVERITIES):
                raise GateError(f"npm audit advisory is malformed at {name}")
            severity = source["severity"]
            ghsa = source["url"].removeprefix(ADVISORY_URL)
            if not source["url"].startswith(ADVISORY_URL) or not GHSA.fullmatch(ghsa):
                ghsa = "unrecognized advisory"
            found.append((ghsa, name, severity))
            confirmed[name] = max(confirmed.get(name, -1), SEVERITIES.index(severity))

    expected_counts = {severity: declared[severity] for severity in SEVERITIES}
    expected_counts["total"] = len(vulnerabilities)
    if counts != expected_counts or any(type(count) is not int for count in counts.values()):
        raise GateError("npm audit report vulnerability counts disagree with its inventory")
    # npm's dependent entries may form cycles. Every reported severity still
    # needs a path to a direct advisory at least as severe.
    queue = deque(confirmed)
    while queue:
        source = queue.popleft()
        for dependent in dependents[source]:
            if confirmed[source] > confirmed.get(dependent, -1):
                confirmed[dependent] = confirmed[source]
                queue.append(dependent)
    if any(confirmed.get(name, -1) < SEVERITIES.index(entry["severity"])
           for name, entry in vulnerabilities.items()):
        raise GateError("npm audit report has an unsubstantiated vulnerability")
    return found


def evaluate(report_text: str, accepted: dict[tuple[str, str], dict[str, Any]], level: str) -> list[str]:
    threshold = SEVERITIES.index(level)
    blocking = []
    applied = set()
    seen = set()
    for ghsa, package, severity in findings(report_text):
        seen.add((ghsa, package))
        if SEVERITIES.index(severity) < threshold:
            continue
        record = accepted.get((ghsa, package))
        if record is None:
            blocking.append(f"{severity} {ghsa} in {package}")
        elif severity != record["severity"]:
            blocking.append(f"{severity} {ghsa} in {package} differs from its accepted {record['severity']}")
        elif (ghsa, package) not in applied:
            applied.add((ghsa, package))
            print(f"note: accepted {severity} {ghsa} in {package} through {record['backstop']}", file=sys.stderr)
    for ghsa, package in sorted(set(accepted) - seen):
        print(f"note: exception {ghsa} for {package} matches no finding; remove it", file=sys.stderr)
    return blocking


def main(argv: list[str] | None = None, stdin: str | None = None, today: date | None = None, *,
         repo: Path = REPO_ROOT, cwd: Path | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--exceptions", type=Path, required=True)
    parser.add_argument("--scope", choices=("production", "full"), required=True)
    parser.add_argument("--audit-level", choices=SEVERITIES, required=True)
    args = parser.parse_args(argv)
    try:
        accepted = load_exceptions(args.exceptions, today or date.today())
        accepted = applicable_exceptions(accepted, repo, cwd or Path.cwd(), args.scope)
        blocking = evaluate(sys.stdin.read() if stdin is None else stdin, accepted, args.audit_level)
    except GateError as error:
        print(f"npm audit gate: {error}", file=sys.stderr)
        return 1
    if blocking:
        print("npm audit gate: unaccepted findings at or above " + args.audit_level + ":", file=sys.stderr)
        for line in blocking:
            print(f"  {line}", file=sys.stderr)
        return 1
    print(f"npm audit gate: no unaccepted findings at or above {args.audit_level}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
