#!/usr/bin/env python3
"""Assemble the sanitized Pi promotion evidence pair (promotion.json + promotion.md).

Stdlib-only. Reads hosted adapter-contract and CodeQL job durations from the
GitHub API via the `gh` CLI, merges caller-measured local rows, validates the
document against verify_pi_support.strict_promotion, and writes both artifacts
with the exact rendering that verifier enforces.

Usage (all rows carry real measurements; nothing here invents a number):

  python .github/scripts/pi_evidence.py \
    --commit <sha-the-hosted-matrix-ran-on> \
    --ci-run-id <ci run id> --codeql-run-id <codeql run id> \
    --local 0.80.5=70572 --local 0.80.10=70937 \
    --canary 0.80.6=899:VERSION_UNSUPPORTED

The promotion workflow can invoke this after a green validation matrix so the
evidence pair regenerates automatically whenever the supported window is
re-tested; verify_pi_support.py --mode final then proves the result.
"""
from __future__ import annotations

import argparse
import importlib.util
import json
import platform
import re
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
REPORT_DIR = REPO / "docs" / "reports" / "pi-support"
ADAPTER_JOB = re.compile(r"Adapter contract\s+<os: (?P<os>[a-z]+)-latest · runtime: Pi (?P<version>[0-9.]+)>")
OS_TO_PLATFORM = {"ubuntu": "linux", "windows": "windows", "macos": "macos"}
HOSTED_ARCH = {"linux": "x64", "windows": "x64", "macos": "arm64"}


def _verify_module():
    spec = importlib.util.spec_from_file_location(
        "verify_pi_support", REPO / ".github" / "scripts" / "verify_pi_support.py"
    )
    module = importlib.util.module_from_spec(spec)
    sys.modules["verify_pi_support"] = module
    spec.loader.exec_module(module)
    return module


def _duration_ms(job: dict) -> int:
    started = datetime.fromisoformat(job["started_at"].replace("Z", "+00:00"))
    completed = datetime.fromisoformat(job["completed_at"].replace("Z", "+00:00"))
    return round((completed - started).total_seconds() * 1000)


def _run_jobs(run_id: str) -> list[dict]:
    result = subprocess.run(
        ["gh", "api", f"repos/{{owner}}/{{repo}}/actions/runs/{run_id}/jobs", "--paginate"],
        cwd=REPO, text=True, encoding="utf-8", capture_output=True, check=True,
    )
    return json.loads(result.stdout)["jobs"]


def hosted_rows(run_id: str, supported: tuple[str, ...]) -> list[dict]:
    rows = []
    for job in _run_jobs(run_id):
        match = ADAPTER_JOB.search(job["name"])
        if match is None or match.group("version") not in supported:
            continue
        if job["conclusion"] != "success":
            raise SystemExit(f"pi-evidence: hosted cell not green: {job['name']}")
        host_platform = OS_TO_PLATFORM[match.group("os")]
        rows.append({
            "version": match.group("version"), "platform": host_platform,
            "architecture": HOSTED_ARCH[host_platform], "resultCode": "PI-HOSTED-SUPPORTED",
            "passed": True, "timingMs": _duration_ms(job), "diagnosticCode": "NONE",
        })
    return rows


def codeql_row(run_id: str) -> dict:
    result = subprocess.run(
        ["gh", "api", f"repos/{{owner}}/{{repo}}/actions/runs/{run_id}"],
        cwd=REPO, text=True, encoding="utf-8", capture_output=True, check=True,
    )
    run = json.loads(result.stdout)
    if run["conclusion"] != "success":
        raise SystemExit("pi-evidence: CodeQL run is not green")
    started = datetime.fromisoformat(run["run_started_at"].replace("Z", "+00:00"))
    updated = datetime.fromisoformat(run["updated_at"].replace("Z", "+00:00"))
    return {
        "version": "codeql", "platform": "github", "architecture": "x64",
        "resultCode": "PI-CODEQL-HIGH", "passed": True,
        "timingMs": round((updated - started).total_seconds() * 1000), "diagnosticCode": "NONE",
    }


def local_arch() -> str:
    return "arm64" if platform.machine().lower() in {"arm64", "aarch64"} else "x64"


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--commit", required=True)
    parser.add_argument("--ci-run-id", required=True)
    parser.add_argument("--codeql-run-id", required=True)
    parser.add_argument("--local", action="append", default=[], metavar="VERSION=MS",
                        help="measured local windows-local platform-contract timing, one per supported version")
    parser.add_argument("--canary", required=True, metavar="VERSION=MS:DIAGNOSTIC",
                        help="measured refusal (or pass) of a version outside the supported set")
    args = parser.parse_args()

    verify = _verify_module()
    supported = verify.SUPPORTED
    rows = []
    for spec_text in args.local:
        version, _, ms = spec_text.partition("=")
        if version not in supported:
            raise SystemExit(f"pi-evidence: local row {version} is not a supported version")
        rows.append({
            "version": version, "platform": "windows-local", "architecture": local_arch(),
            "resultCode": "PI-LOCAL-SUPPORTED", "passed": True,
            "timingMs": int(ms), "diagnosticCode": "NONE",
        })
    rows.extend(hosted_rows(args.ci_run_id, supported))
    rows.append(codeql_row(args.codeql_run_id))
    canary_version, _, rest = args.canary.partition("=")
    canary_ms, _, diagnostic = rest.partition(":")
    rows.append({
        "version": canary_version, "platform": "windows-local", "architecture": local_arch(),
        "resultCode": "PI-LATEST-CANARY", "passed": diagnostic == "NONE",
        "timingMs": int(canary_ms), "diagnosticCode": diagnostic or "NONE",
    })

    document = {"schema": "codearbiter-pi-promotion-v1", "mode": "final",
                "commit": args.commit, "rows": rows}
    ok, detail = verify.strict_promotion(document, "final")
    if not ok:
        raise SystemExit(f"pi-evidence: assembled document fails strict_promotion: {detail}")
    REPORT_DIR.mkdir(parents=True, exist_ok=True)
    (REPORT_DIR / "promotion.json").write_text(
        json.dumps(document, indent=1) + "\n", encoding="utf-8", newline="\n")
    (REPORT_DIR / "promotion.md").write_text(
        verify.render_promotion_markdown(document), encoding="utf-8", newline="\n")
    print(json.dumps({"rows": len(rows), "commit": args.commit, "written": True}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
