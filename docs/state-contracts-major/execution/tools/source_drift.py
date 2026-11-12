#!/usr/bin/env python3
"""Report which intake-cited source paths changed between the audit SHA and a base.

Read-only. Output is a source-revalidation worklist, not a verdict: a listed task
must have its changed owner files re-read before implementation; an unlisted task
still requires normal source inspection.
"""
from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path

AUDIT_SHA = "fd7eb34b2da439551443d09526ab48fd1d1bb9bf"


def git(repo: Path, *args: str) -> str:
    return subprocess.run(["git", "-C", str(repo), *args], check=True, capture_output=True, text=True, encoding="utf-8").stdout


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--repo", type=Path, required=True)
    parser.add_argument("--base", required=True, help="inspected base commit to compare against the audit SHA")
    parser.add_argument("--corpus", type=Path, default=Path(__file__).resolve().parents[2])
    args = parser.parse_args()

    base = git(args.repo, "rev-parse", args.base).strip()
    changed = sorted(p for p in git(args.repo, "diff", "--name-only", f"{AUDIT_SHA}..{base}").splitlines() if p)
    tasks = json.loads((args.corpus / "contracts/tasks.json").read_text(encoding="utf-8"))["tasks"]
    changed_set = set(changed)
    affected = []
    cited: set[str] = set()
    for task in tasks:
        paths = set(task.get("source_paths", []))
        cited |= paths
        hit = sorted(paths & changed_set)
        if hit:
            affected.append({"task": task["id"], "finding_ids": task.get("finding_ids", []), "changed_cited_paths": hit})
    report = {
        "kind": "SOURCE_DRIFT_WORKLIST",
        "audit_commit": AUDIT_SHA,
        "inspected_base": base,
        "commits_since_audit": int(git(args.repo, "rev-list", "--count", f"{AUDIT_SHA}..{base}").strip()),
        "changed_file_count": len(changed),
        "cited_source_path_count": len(cited),
        "changed_cited_paths": sorted(cited & changed_set),
        "tasks_requiring_source_revalidation": affected,
        "note": "Worklist only. Unchanged cited paths still require reading before edits; changed uncited files may still affect callers.",
    }
    json.dump(report, sys.stdout, indent=2)
    sys.stdout.write("\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
