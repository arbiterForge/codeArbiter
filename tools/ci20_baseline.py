#!/usr/bin/env python3
"""Read-only, commit-bound GitHub Actions critical-path baseline for CI20-01.

Requires Python 3.11+, PyYAML, Git and an authenticated gh CLI. Never changes
GitHub state, dispatches workflows, or excludes queueing from elapsed time.
"""
from __future__ import annotations

import argparse
from collections import Counter, defaultdict
from datetime import datetime
import hashlib
import json
from pathlib import Path
import re
import subprocess
import sys

import yaml


def command(*args: str, cwd: Path | None = None) -> str:
    return subprocess.check_output(args, cwd=cwd, text=True, encoding="utf-8")


def api(endpoint: str) -> dict:
    return json.loads(command("gh", "api", endpoint))


def count_conclusions(jobs: list[dict]) -> dict[str, int]:
    """Count every observed result; never silently omit unexpected outcomes."""
    counts = dict(Counter(str(job.get("conclusion")) for job in jobs))
    if sum(counts.values()) != len(jobs):
        raise ValueError("Incomplete job conclusions")
    return counts


def timestamp(value: str) -> float:
    return datetime.fromisoformat(value.replace("Z", "+00:00")).timestamp()


def seconds(start: str, end: str) -> float:
    return round(timestamp(end) - timestamp(start), 3)


def name_pattern(template: str) -> re.Pattern:
    # A skipped matrix job is sometimes reported with the literal template.
    fragments = re.split(r"(\$\{\{.*?\}\})", template)
    regex = "".join(r"(?:.+?)" if part.startswith("${{") else re.escape(part)
                    for part in fragments)
    return re.compile("^" + regex + "$")


def identify_jobs(workflow: dict, jobs: list[dict]) -> dict[str, list[dict]]:
    patterns = {key: name_pattern(value.get("name", key))
                for key, value in workflow["jobs"].items()}
    owners = defaultdict(list)
    for job in jobs:
        matched = [key for key, pattern in patterns.items()
                   if pattern.fullmatch(job["name"]) or
                   workflow["jobs"][key].get("name", key) == job["name"]]
        if len(matched) != 1:
            raise ValueError(f"Job owner not unique: {job['name']!r}: {matched}")
        owners[matched[0]].append(job)
    return dict(owners)


def dependencies(workflow: dict) -> dict[str, list[str]]:
    result = {}
    for key, value in workflow["jobs"].items():
        needs = value.get("needs", [])
        if isinstance(needs, str):
            needs = [needs]
        if not isinstance(needs, list) or any(n not in workflow["jobs"] for n in needs):
            raise ValueError(f"Invalid dependencies for {key}")
        result[key] = needs
    return result


def replay(workflow: dict, owners: dict[str, list[dict]]) -> dict:
    """Model the full group-level needs graph, preserving all observed durations.

    Each matrix child depends on every child of each prerequisite job group.
    Skipped jobs are modeled as zero work but retain dependency ordering.
    """
    graph = dependencies(workflow)
    if set(owners) != set(graph):
        raise ValueError(f"Missing or extra job groups: {set(graph) ^ set(owners)}")
    memo = {}
    visiting = set()

    def finish(group: str) -> float:
        if group in memo:
            return memo[group]
        if group in visiting:
            raise ValueError("Cyclic workflow dependencies")
        visiting.add(group)
        prerequisite = max((finish(n) for n in graph[group]), default=0)
        duration = max((seconds(j["started_at"], j["completed_at"])
                        if j.get("started_at") and j.get("completed_at") else 0
                        for j in owners[group]), default=0)
        memo[group] = prerequisite + duration
        visiting.remove(group)
        return memo[group]

    for group in graph:
        finish(group)
    # The final required aggregate is the endpoint, not the last random job.
    if "ci-passed" not in memo:
        raise ValueError("Missing protected merge readiness group")
    return {"queue_free_seconds": round(memo["ci-passed"], 3),
            "group_finish_seconds": {k: round(v, 3) for k, v in memo.items()},
            "method": "Group-level zero-queue replay; max observed matrix duration per group; all needs edges; preserves setup and cleanup; no capacity contention modeled"}


def collect(repository: str, run_id: int, checkout: Path) -> dict:
    head = command("git", "rev-parse", "HEAD", cwd=checkout).strip()
    if not re.fullmatch(r"[a-f0-9]{40}", head):
        raise ValueError("Invalid checkout SHA")
    workflow_path = checkout / ".github/workflows/ci.yml"
    raw = workflow_path.read_bytes()
    workflow = yaml.safe_load(raw)
    if not isinstance(workflow, dict) or not isinstance(workflow.get("jobs"), dict):
        raise ValueError("Invalid workflow")
    run = api(f"repos/{repository}/actions/runs/{run_id}")
    if run["head_sha"] != head:
        raise ValueError(f"Run source {run['head_sha']} differs from checkout {head}")
    if run["status"] != "completed":
        raise ValueError("Only completed runs qualify as historical baseline")
    all_jobs = []
    page = 1
    while True:
        data = api(f"repos/{repository}/actions/runs/{run_id}/jobs?per_page=100&page={page}")
        all_jobs.extend(data["jobs"])
        if len(all_jobs) >= data["total_count"]:
            if len(all_jobs) != data["total_count"]:
                raise ValueError("Incomplete or duplicate paginated jobs")
            break
        page += 1
        if page > 100:
            raise ValueError("Too many job pages")
    ids = [j["id"] for j in all_jobs]
    if len(ids) != len(set(ids)):
        raise ValueError("Duplicate job IDs")
    owners = identify_jobs(workflow, all_jobs)
    model = replay(workflow, owners)
    end = max((j["completed_at"] for j in all_jobs if j.get("completed_at")),
              default=run["updated_at"])
    elapsed = seconds(run["created_at"], end)
    job_records = []
    for group, children in owners.items():
        for j in children:
            job_records.append({
                "id": j["id"], "group": group, "name": j["name"],
                "status": j["status"], "conclusion": j["conclusion"],
                "labels": j.get("labels", []),
                "started_at": j.get("started_at"), "completed_at": j.get("completed_at"),
                "seconds": seconds(j["started_at"], j["completed_at"])
                           if j.get("started_at") and j.get("completed_at") else 0,
                "steps": [{"name": s["name"], "conclusion": s["conclusion"],
                           "seconds": seconds(s["started_at"], s["completed_at"])
                                      if s.get("started_at") and s.get("completed_at") else 0}
                          for s in j.get("steps", [])],
            })
    job_records.sort(key=lambda j: (j["group"], j["name"]))
    return {
        "format": "codearbiter.ci20-baseline/1", "repository": repository,
        "source_commit": head, "workflow_path": ".github/workflows/ci.yml",
        "workflow_sha256": hashlib.sha256(raw).hexdigest(),
        "run_id": run_id, "run_attempt": run["run_attempt"],
        "run_status": run["status"], "run_conclusion": run["conclusion"],
        "created_at": run["created_at"], "last_job_completed_at": end,
        "actual_trigger_to_last_job_seconds": elapsed,
        "job_count": len(all_jobs), "group_count": len(owners),
        "conclusions": count_conclusions(all_jobs),
        "runner_seconds": round(sum(j["seconds"] for j in job_records), 3),
        "macos_runner_seconds": round(sum(j["seconds"] for j in job_records
                                         if any(label.startswith("macos") for label in j["labels"])), 3),
        "needs": dependencies(workflow),
        "model": model,
        "jobs": job_records,
        "caveats": [
            "Trigger-to-last-job is not the final GitHub workflow settlement time.",
            "The zero-queue replay is a counterfactual, not a hosted speedup.",
            "Skipped impact-selected work is not evidence of full-workload verification.",
            "Job-ready delay includes scheduling/provisioning and cannot alone prove account quota.",
        ],
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo", default="arbiterForge/codeArbiter")
    parser.add_argument("--run-id", type=int, required=True)
    parser.add_argument("--checkout", type=Path, default=Path.cwd())
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    result = collect(args.repo, args.run_id, args.checkout.resolve())
    if args.output.exists():
        parser.error("Refusing to overwrite baseline evidence")
    args.output.parent.mkdir(parents=True, exist_ok=True)
    with args.output.open("x", encoding="utf-8", newline="\n") as file:
        json.dump(result, file, indent=2, sort_keys=True)
        file.write("\n")
    print(json.dumps({key: result[key] for key in
                      ("source_commit", "run_id", "run_conclusion", "job_count",
                       "actual_trigger_to_last_job_seconds")}, indent=2))
    print("Queue-free replay seconds:", result["model"]["queue_free_seconds"])


if __name__ == "__main__":
    main()
