#!/usr/bin/env python3
"""Fail an `npm audit --json` report on any unaccepted finding at or above a threshold.

`npm audit` has no way to accept a specific advisory, so a HIGH with no patched
release anywhere blocks every PR until upstream ships one. This gate reads the
report on stdin and admits only advisories recorded in an exceptions file, each
named by GHSA and package, approved by a named maintainer, and bounded by a
dated backstop no more than 30 days after approval. Everything else keeps
npm's own behaviour: any other finding at or above `--audit-level` fails.

Fail-closed by construction: an empty, unreadable, or error report fails, as
does a malformed, expired, or over-long exception. An exception that no longer
matches any finding is reported so it can be removed, but does not fail.

Usage (from the audited package directory):
    npm audit --omit=dev --json | python npm_audit_gate.py --exceptions FILE --audit-level=high
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from datetime import date, timedelta
from pathlib import Path
from typing import Any

SCHEMA = "codearbiter-npm-audit-exceptions-v1"
SEVERITIES = ("info", "low", "moderate", "high", "critical")
EXCEPTION_FIELDS = {"ghsa", "package", "severity", "reason", "approved_by", "approved_on", "backstop"}
MAX_BACKSTOP_DAYS = 30
GHSA = re.compile(r"^GHSA(?:-[23456789cfghjmpqrvwx]{4}){3}$")
PACKAGE = re.compile(r"^(?:@[a-z0-9][a-z0-9._~-]*/)?[a-z0-9][a-z0-9._~-]*$")


class GateError(ValueError):
    """A report or exception record the gate refuses to trust."""


def load_exceptions(path: Path, today: date) -> dict[tuple[str, str], dict[str, Any]]:
    try:
        document = json.loads(path.read_text(encoding="utf-8"))
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
        try:
            approved = date.fromisoformat(str(item["approved_on"]))
            backstop = date.fromisoformat(str(item["backstop"]))
        except ValueError as error:
            raise GateError("audit exception dates are invalid") from error
        if not approved <= backstop <= approved + timedelta(days=MAX_BACKSTOP_DAYS):
            raise GateError(f"{item['ghsa']} backstop is outside its approval window")
        if approved > today:
            # A future approval date would stretch the 30-day bound arbitrarily.
            raise GateError(f"{item['ghsa']} approval date {approved} is in the future")
        if today > backstop:
            raise GateError(f"{item['ghsa']} exception expired on {backstop}; re-review or remove it")
        key = (item["ghsa"], item["package"])
        if key in accepted:
            raise GateError(f"{item['ghsa']} is recorded twice for {item['package']}")
        accepted[key] = item
    return accepted


def findings(report_text: str) -> list[tuple[str, str, str]]:
    """Every advisory (GHSA, package, severity) the report names directly."""
    try:
        report = json.loads(report_text)
    except ValueError as error:
        raise GateError("npm audit report is unreadable") from error
    if not isinstance(report, dict) or "error" in report:
        raise GateError("npm audit did not produce a report")
    vulnerabilities = report.get("vulnerabilities")
    if not isinstance(vulnerabilities, dict):
        raise GateError("npm audit report has no vulnerability inventory")
    found: list[tuple[str, str, str]] = []
    for name, entry in vulnerabilities.items():
        via = entry.get("via") if isinstance(entry, dict) else None
        if not isinstance(via, list):
            raise GateError(f"npm audit report entry is malformed at {name}")
        for source in via:
            if isinstance(source, str):
                continue  # A pointer to another inventory entry, judged there.
            if not isinstance(source, dict):
                raise GateError(f"npm audit report entry is malformed at {name}")
            url = source.get("url")
            severity = source.get("severity")
            if not isinstance(url, str) or severity not in SEVERITIES:
                raise GateError(f"npm audit advisory is malformed at {name}")
            found.append((url.rstrip("/").rsplit("/", 1)[-1], str(source.get("name", name)), severity))
    return found


def evaluate(report_text: str, accepted: dict[tuple[str, str], dict[str, Any]], level: str) -> list[str]:
    """Return the unaccepted findings at or above `level`; raise on an untrusted report."""
    threshold = SEVERITIES.index(level)
    blocking = []
    seen = set()
    for ghsa, package, severity in findings(report_text):
        seen.add((ghsa, package))
        if SEVERITIES.index(severity) < threshold:
            continue
        record = accepted.get((ghsa, package))
        if record is None:
            blocking.append(f"{severity} {ghsa} in {package}")
        elif SEVERITIES.index(severity) > SEVERITIES.index(record["severity"]):
            blocking.append(f"{severity} {ghsa} in {package} exceeds its accepted {record['severity']}")
    for ghsa, package in sorted(set(accepted) - seen):
        print(f"note: exception {ghsa} for {package} matches no finding; remove it", file=sys.stderr)
    return blocking


def main(argv: list[str] | None = None, stdin: str | None = None, today: date | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--exceptions", type=Path, required=True)
    parser.add_argument("--audit-level", choices=SEVERITIES, required=True)
    args = parser.parse_args(argv)
    try:
        accepted = load_exceptions(args.exceptions, today or date.today())
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
