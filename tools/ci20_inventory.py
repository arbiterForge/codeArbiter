#!/usr/bin/env python3
"""Create a commit-bound CI20-01 source/job inventory from the current checkout."""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import subprocess
import sys
import yaml

ROOT = Path(__file__).resolve().parents[1]


def required_contexts(branch: dict) -> list[str]:
    """Normalize both GitHub branch-protection API shapes fail-closed."""
    if not isinstance(branch, dict):
        raise SystemExit("Branch protection response must be a record")
    status = branch.get("required_status_checks")
    if not isinstance(status, dict):
        raise SystemExit("Branch protection does not declare required status checks")
    contexts = status.get("contexts")
    checks = status.get("checks")
    if contexts is None:
        contexts = []
    if checks is None:
        checks = []
    if not isinstance(contexts, list) or not isinstance(checks, list):
        raise SystemExit("Invalid branch-protection required-check collection")
    required: list[str] = []
    for value in contexts:
        if not isinstance(value, str) or not value:
            raise SystemExit("Invalid required context name")
        if value not in required:
            required.append(value)
    for entry in checks:
        if not isinstance(entry, dict) or not isinstance(entry.get("context"), str) or not entry["context"]:
            raise SystemExit("Invalid required check entry")
        if entry["context"] not in required:
            required.append(entry["context"])
    if "[GATE ] | [REPO] | Merge readiness" not in required:
        raise SystemExit("Protected merge readiness context missing")
    return required


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--baseline", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    baseline = json.loads(args.baseline.read_text(encoding="utf-8"))
    head = subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=ROOT, text=True).strip()
    if head != baseline["source_commit"]:
        raise SystemExit(
            f"Checkout {head} differs from baseline {baseline['source_commit']}")
    workflow = yaml.safe_load((ROOT / ".github/workflows/ci.yml").read_text(encoding="utf-8"))
    branch = json.loads(subprocess.check_output(
        ["gh", "api", "repos/arbiterForge/codeArbiter/branches/main/protection"],
        text=True))
    required = required_contexts(branch)
    inventory = {}
    for name, job in workflow["jobs"].items():
        inventory[name] = {
            "display_name": job.get("name", name),
            "needs": baseline["needs"][name],
            "condition": str(job.get("if", "")),
            "matrix": job.get("strategy", {}).get("matrix", {}),
            "timeout": job.get("timeout-minutes"),
            "runner": job.get("runs-on"),
            "commands": [{"name": step.get("name"), "run": step["run"],
                          "working_directory": step.get("working-directory", "."),
                          "condition": step.get("if", "")}
                         for step in job.get("steps", []) if "run" in step],
            "actions": [{"name": step.get("name"), "uses": step["uses"]}
                        for step in job.get("steps", []) if "uses" in step],
            "observed_jobs": sum(j["group"] == name for j in baseline["jobs"]),
            "observed_successes": sum(j["group"] == name and j["conclusion"] == "success"
                                      for j in baseline["jobs"]),
            "observed_skips": sum(j["group"] == name and j["conclusion"] == "skipped"
                                  for j in baseline["jobs"]),
        }
    other = {}
    for path in sorted((ROOT / ".github/workflows").glob("*.yml")):
        data = path.read_bytes()
        other[path.name] = {"sha256": hashlib.sha256(data).hexdigest(),
                            "jobs": sorted(yaml.safe_load(data).get("jobs", {}))}
    report = {
        "format": "codearbiter.ci20-source-inventory/1",
        "source_commit": head,
        "baseline_run_id": baseline["run_id"],
        "protected_required_contexts": required,
        "workflow_files": other,
        "job_inventory": inventory,
        "known_historical_reference": {
            "pr": 993, "head": "16983f5017b39e35de2f90994e30fcd60730e82c",
            "state": "closed_unmerged", "policy": "review individual improvements; never wholesale copy older workflow"
        },
    }
    target = args.output
    if target.exists():
        raise SystemExit("Refusing to overwrite source map")
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print("Source inventory:", len(inventory), "job groups;", sum(len(x["commands"]) for x in inventory.values()), "shell commands")
    print("Required contexts:", required)


if __name__ == "__main__":
    main()
