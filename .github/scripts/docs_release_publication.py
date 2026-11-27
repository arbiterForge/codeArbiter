"""Read only the selected release run's exact original publication observation for Docs."""
import argparse
import io
import json
from pathlib import Path
import re
import zipfile

import major_readiness as owner

RELEASE_WORKFLOW = ".github/workflows/release.yml"
JOB = "[CHECK] | [RELEASE] | Route publication observation"
OBSERVE_STEP = "Observe declared first-containing Releases"
UPLOAD_STEP = "Retain the route publication observation"
MEMBER = "route-publication-observation.json"
FORMAT = "codearbiter.route-publication-observation/0.1.0"
MAX_BYTES = 1 << 20


def unique(pairs):
    result = {}
    for key, value in pairs:
        owner.require(key not in result, "duplicate release observation key")
        result[key] = value
    return result


def repository_id(run):
    repo, head = run["repository"], run["head_repository"]
    identity = repo["id"]
    owner.require(type(identity) is int and identity > 0 and head["id"] == identity
                  and repo["full_name"] == head["full_name"] == owner.REPOSITORY,
                  "release observation repository differs")
    return identity


def run_identity(run):
    return tuple(run[key] for key in ("id", "run_attempt", "head_sha", "head_branch", "event", "status", "conclusion"))


def population(document, field):
    values = document[field]
    owner.require(type(values) is list and len(values) == document["total_count"] <= 100,
                  "release observation metadata population differs")
    return values


def selected_observation(event, repo):
    upstream = event["workflow_run"]
    repo_id = repository_id(upstream)
    run_id, attempt, run_head, branch, trigger, status, conclusion = run_identity(upstream)
    owner.require((branch, status, conclusion) == ("main", "completed", "success")
                  and trigger in ("workflow_run", "workflow_dispatch")
                  and event["action"] == "completed"
                  and event["workflow"]["path"] == RELEASE_WORKFLOW
                  and type(event["workflow"]["id"]) is int and event["workflow"]["id"] > 0
                  and event["repository"]["id"] == repo_id
                  and event["repository"]["full_name"] == owner.REPOSITORY
                  and type(run_id) is int and run_id > 0 and type(attempt) is int and attempt > 0
                  and owner.SHA.fullmatch(run_head), "untrusted release trigger")
    run = owner.api(f"actions/runs/{run_id}/attempts/{attempt}")
    owner.require(run_identity(run) == run_identity(upstream) and repository_id(run) == repo_id
                  and run["path"] == RELEASE_WORKFLOW and run["workflow_id"] == event["workflow"]["id"],
                  "selected original release run differs")
    jobs = population(owner.api(f"actions/runs/{run_id}/attempts/{attempt}/jobs?per_page=100"), "jobs")
    [job] = [item for item in jobs if item["name"] == JOB]
    owner.require(type(job["id"]) is int and job["id"] > 0
                  and (job["run_id"], job["run_attempt"], job["head_sha"], job["status"], job["conclusion"]) ==
                  (run_id, attempt, run_head, "completed", "success"), "selected observer job did not succeed")
    [step] = [item for item in job["steps"] if item["name"] == OBSERVE_STEP]
    owner.require((step["status"], step["conclusion"]) == ("completed", "success"),
                  "selected original observation step did not succeed")
    name = f"route-publication-observation-{run_id}-{attempt}"
    artifacts = population(owner.api(f"actions/runs/{run_id}/artifacts?name={name}&per_page=100"), "artifacts")
    [artifact] = [item for item in artifacts if item["name"] == name]
    origin = artifact["workflow_run"]
    owner.require((origin["id"], origin["head_sha"], origin["head_branch"],
                   origin["repository_id"], origin["head_repository_id"]) ==
                  (run_id, run_head, branch, repo_id, repo_id)
                  and type(artifact["size_in_bytes"]) is int
                  and 0 < artifact["size_in_bytes"] <= MAX_BYTES, "selected original upload identity differs")
    log = owner.api(f"actions/jobs/{job['id']}/logs", binary=True)
    owner.validate_upload(job, artifact, UPLOAD_STEP, job_log=log)
    raw = owner.artifact_bytes(artifact, {"source_commit": run_head, "ci_run_id": run_id})
    owner.require(len(raw) == artifact["size_in_bytes"], "selected original archive length differs")
    members = owner.members(raw)
    owner.require([member["path"] for member in members] == [MEMBER], "selected original archive members differ")
    with zipfile.ZipFile(io.BytesIO(raw)) as zipped:
        owner.require(zipped.getinfo(MEMBER).file_size <= MAX_BYTES, "release observation content exceeds bound")
        content = zipped.read(MEMBER)
    record = json.loads(content, object_pairs_hook=unique)
    owner.require(type(record) is dict and set(record) ==
                  {"format", "observed_at", "source_commit", "ci_run_id", "workflow_run", "release_visibility",
                   "clock_starts", "removal_authorization", "observations", "site_observations", "route_clock_status"}
                  and record["format"] == FORMAT and record["workflow_run"] == str(run_id)
                  and record["release_visibility"] == "public"
                  and record["clock_starts"] == "confirmed-non-draft-github-release"
                  and record["removal_authorization"] == "not-evaluated"
                  and isinstance(record["source_commit"], str) and owner.SHA.fullmatch(record["source_commit"])
                  and isinstance(record["ci_run_id"], str) and re.fullmatch(r"[1-9][0-9]*", record["ci_run_id"])
                  and type(record["observations"]) is list
                  and (record["route_clock_status"], len(record["observations"])) in
                      (("observed", 3), ("declarations-unavailable", 0))
                  and type(record["site_observations"]) is list and len(record["site_observations"]) <= 3,
                  "selected original record envelope differs")
    source, ci_id = record["source_commit"], int(record["ci_run_id"])
    core = owner.api(f"actions/runs/{ci_id}")
    owner.validate_run(core, {"source_commit": source, "ci_run_id": ci_id})
    owner.require(repository_id(core) == repo_id and core["status"] == "completed",
                  "selected release source Core identity differs")
    owner.command(["git", "--no-lazy-fetch", "merge-base", "--is-ancestor", source, "HEAD"], repo)
    return content


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--event", required=True, type=Path)
    parser.add_argument("--repo", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()
    try:
        owner.require(args.event.stat().st_size <= MAX_BYTES, "workflow event exceeds bound")
        event = json.loads(args.event.read_bytes(), object_pairs_hook=unique)
        content = selected_observation(event, args.repo.resolve(strict=True))
        with args.output.open("xb") as stream:
            stream.write(content)
    except (owner.ReadinessError, OSError, TypeError, KeyError, ValueError, RuntimeError, zipfile.BadZipFile):
        print("::notice::No authenticated release publication observation was available. Docs use unknown publication state.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
