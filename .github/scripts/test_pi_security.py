#!/usr/bin/env python3
"""Machine-readable Pi security promotion evidence with no raw sensitive output."""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import shutil
import subprocess
import sys
from typing import Any

from verify_pi_support import strict_promotion


REPO = Path(__file__).resolve().parents[2]
WORKFLOW = REPO / ".github" / "workflows" / "codeql.yml"
CODEQL_SHA = "7188fc363630916deb702c7fdcf4e481b751f97a"
SCHEMA = "codearbiter-pi-security-v1"


def result(code: str, passed: bool, count: int | None = None) -> dict[str, object]:
    row: dict[str, object] = {"code": code, "status": "pass" if passed else "fail"}
    if count is not None:
        row["count"] = count
    return row


def workflow_results() -> list[dict[str, object]]:
    try:
        text = WORKFLOW.read_text(encoding="utf-8")
    except (OSError, UnicodeError):
        return [result("PI-SEC-ACTIONS-PIN", False), result("PI-SEC-CODEQL-SCOPE", False)]
    pins = (
        f"github/codeql-action/init@{CODEQL_SHA}" in text
        and f"github/codeql-action/analyze@{CODEQL_SHA}" in text
        and "@v4" not in text
    )
    scope = all(
        marker in text
        for marker in (
            "languages: javascript-typescript",
            "plugins/ca-pi/tools/src",
            "plugins/ca-pi/extensions",
            "plugins/ca-pi/tools/node_modules",
            "test_pi_security.py --sarif",
        )
    )
    return [result("PI-SEC-ACTIONS-PIN", pins), result("PI-SEC-CODEQL-SCOPE", scope)]


def security_severity(rule: dict[str, Any], finding: dict[str, Any]) -> float | None:
    values = (
        finding.get("properties", {}).get("security-severity"),
        rule.get("properties", {}).get("security-severity"),
    )
    for value in values:
        try:
            return float(value)
        except (TypeError, ValueError):
            continue
    return None


def sarif_result(path: Path) -> dict[str, object]:
    files = [path] if path.is_file() else sorted(path.rglob("*.sarif")) if path.is_dir() else []
    high = 0
    valid = bool(files)
    for sarif in files:
        try:
            document = json.loads(sarif.read_text(encoding="utf-8"))
            for run in document.get("runs", []):
                rules = {
                    rule.get("id"): rule
                    for rule in run.get("tool", {}).get("driver", {}).get("rules", [])
                    if isinstance(rule, dict) and isinstance(rule.get("id"), str)
                }
                for finding in run.get("results", []):
                    if not isinstance(finding, dict):
                        continue
                    rule = rules.get(finding.get("ruleId"), {})
                    severity = security_severity(rule, finding)
                    if severity is not None and severity >= 7.0:
                        high += 1
        except (OSError, UnicodeError, json.JSONDecodeError, AttributeError, TypeError):
            valid = False
    return result("PI-SEC-CODEQL-HIGH", valid and high == 0, high)


def adversarial_results() -> list[dict[str, object]]:
    npm = shutil.which("npm.cmd" if sys.platform == "win32" else "npm") or shutil.which("npm")
    if npm is None:
        return [result("PI-SEC-ADVERSARIAL", False)]
    suites = (
        ("PI-SEC-ADVERSARIAL", ("test/security.test.ts", "test/final-arguments.test.ts")),
        ("PI-SEC-ISOLATION", ("test/child-env.test.ts", "test/runner-isolation.test.ts")),
        ("PI-SEC-OWNERSHIP", ("test/activation.test.ts", "test/commands.test.ts", "test/tool-guard.test.ts")),
        ("PI-SEC-COMPACTION", ("test/compaction.test.ts",)),
        ("PI-SEC-FARM", ("test/farm.test.ts",)),
        ("PI-SEC-PACKAGE", ("test/package.test.ts",)),
    )
    rows: list[dict[str, object]] = []
    for code, tests in suites:
        command = [npm, "--prefix", "plugins/ca-pi/tools", "exec", "vitest", "run", *tests]
        try:
            completed = subprocess.run(
                command,
                cwd=REPO,
                stdin=subprocess.DEVNULL,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                timeout=240,
                check=False,
            )
            passed = completed.returncode == 0
        except (OSError, subprocess.TimeoutExpired):
            passed = False
        rows.append(result(code, passed))
    return rows


def emit(rows: list[dict[str, object]]) -> int:
    passed = all(row["status"] == "pass" for row in rows)
    document = {"schema": SCHEMA, "status": "pass" if passed else "fail", "results": rows}
    sys.stdout.write(json.dumps(document, separators=(",", ":"), sort_keys=True) + "\n")
    return 0 if passed else 1


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--contract-only", action="store_true")
    parser.add_argument("--sarif", type=Path)
    parser.add_argument("--evidence", type=Path)
    args = parser.parse_args()
    rows = workflow_results()
    if args.sarif is not None:
        rows.append(sarif_result(args.sarif))
    elif args.evidence is not None:
        try:
            document = json.loads(args.evidence.read_text(encoding="utf-8"))
            mode = document.get("mode") if isinstance(document, dict) else "preclosure"
            passed, _detail = strict_promotion(document, mode if mode in {"preclosure", "final"} else "preclosure")
        except (OSError, UnicodeError, json.JSONDecodeError, AttributeError, TypeError):
            passed = False
        rows.append(result("PI-SEC-PROMOTION-EVIDENCE", passed))
    elif not args.contract_only:
        rows.extend(adversarial_results())
    return emit(rows)


if __name__ == "__main__":
    raise SystemExit(main())
