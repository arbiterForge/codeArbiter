#!/usr/bin/env python3
"""Reproduce complete codeArbiter Actions timing from exact-commit API evidence.

CI20-01 diagnostic only. This file does not change CI selection, qualification,
release admission, tests, or GitHub settings. Its zero-queue replay is a
counterfactual dependency lower bound, NOT measured faster CI.
"""
from __future__ import annotations

import argparse
from collections import Counter, defaultdict
from datetime import datetime
from functools import lru_cache
import gzip
import io
import hashlib
import json
from pathlib import Path
import re
import subprocess
import sys

REPO = "arbiterForge/codeArbiter"
WORKFLOW = ".github/workflows/ci.yml"
NESTED = ".github/workflows/ci-native-platform.yml"
SHA_RE = re.compile(r"^[0-9a-f]{40}$")
ID_RE = re.compile(r"^[a-zA-Z][a-zA-Z0-9_-]*$")
JOB_RE = re.compile(r"^  ([a-zA-Z][a-zA-Z0-9_-]*):\s*(?:#.*)?$", re.M)
ATTRIBUTE_RE = re.compile(r"^    ([a-zA-Z][a-zA-Z0-9_-]*):(?:\s+(.+))?\s*$", re.M)
EXPRESSION_RE = re.compile(r"\$\{\{[^{}]*\}\}")
RESULT_RE = re.compile(r"\$\{\{\s*needs(?:\['([^']+)'\]|\.([A-Za-z0-9_-]+))\.result\s*\}\}")
MAX_JSON_BYTES = 30 * 1024 * 1024


def fail(message: str) -> None:
    raise ValueError(message)


def encode(data: object) -> bytes:
    return (json.dumps(data, sort_keys=True, indent=2, ensure_ascii=False) + "\n").encode("utf-8")


def hash_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def parse_time(value: str | None) -> datetime:
    if not isinstance(value, str) or not value:
        fail("missing ISO-8601 job/run timestamp")
    result = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if result.tzinfo is None:
        fail("timestamp without UTC offset")
    return result


def seconds(first: str, last: str) -> float:
    return (parse_time(last) - parse_time(first)).total_seconds()


def needs_list(value: str, following: list[str]) -> tuple[str, ...]:
    raw = value.strip()
    if raw.startswith("[") and raw.endswith("]"):
        values = [item.strip().strip("'\"") for item in raw[1:-1].split(",") if item.strip()]
    elif raw:
        values = [raw.strip().strip("'\"")]
    else:
        values = []
        for line in following:
            if line.startswith("      - "):
                values.append(line[8:].strip().split("#", 1)[0].strip())
            elif line.startswith("    " ) and not line.startswith("      "):
                break
    if any(not ID_RE.fullmatch(value) for value in values) or len(values) != len(set(values)):
        fail("invalid or duplicate workflow needs entries")
    return tuple(values)


def parse_jobs(source: str) -> dict[str, dict]:
    """Parse only the indented jobs/name/needs/uses/runs-on contracts.

    This intentionally refuses an unrecognized layout instead of applying
    best-effort guesses to release-relevant dependency evidence.
    """
    lines = source.splitlines()
    try:
        index = next(i for i, line in enumerate(lines) if line == "jobs:")
    except StopIteration:
        fail("workflow has no top-level jobs section")
    starts = [(i, JOB_RE.match(line).group(1)) for i, line in enumerate(lines[index+1:], index+1)
              if JOB_RE.match(line)]
    if not starts:
        fail("workflow has no job declarations")
    jobs: dict[str, dict] = {}
    for (start, ident), (end, _) in zip(starts, starts[1:] + [(len(lines), "")]):
        if ident in jobs:
            fail(f"duplicate workflow job ID: {ident}")
        block = lines[start+1:end]
        attrs: dict[str, str] = {}
        for line in block:
            match = ATTRIBUTE_RE.match(line)
            if match:
                if match.group(1) in attrs:
                    fail(f"duplicate job attribute: {ident}.{match.group(1)}")
                attrs[match.group(1)] = (match.group(2) or "").strip()
        name = attrs.get("name", ident)
        if name.startswith('"') and name.endswith('"'):
            try:
                name = json.loads(name)
            except json.JSONDecodeError:
                name = name[1:-1]
        elif name.startswith("'") and name.endswith("'"):
            name = name[1:-1].replace("''", "'")
        if not isinstance(name, str) or not name:
            fail(f"missing job name: {ident}")
        needs = needs_list(attrs.get("needs", ""), block[0:] if "needs" not in attrs else
                          block[next(i for i, line in enumerate(block) if line.startswith("    needs:"))+1:])
        jobs[ident] = {
            "id": ident, "name": name, "needs": list(needs),
            "uses": attrs.get("uses", ""), "runs_on": attrs.get("runs-on", ""),
            "if": attrs.get("if", ""), "timeout": attrs.get("timeout-minutes", ""),
            "observed_instances": 0,
        }
    for job in jobs.values():
        if set(job["needs"]) - set(jobs):
            fail(f"unknown upstream dependency for {job['id']}: {sorted(set(job['needs'])-set(jobs))}")
    return jobs


def job_pattern(name: str) -> re.Pattern:
    fragments = EXPRESSION_RE.split(name)
    if EXPRESSION_RE.search(name):
        return re.compile("^" + "[^\\n]+?".join(re.escape(chunk) for chunk in fragments) + "$")
    return re.compile("^" + re.escape(name) + "$")


def identify(name: str, root: dict[str, dict], nested: dict[str, dict]) -> tuple[str, str]:
    """Map one named Actions job to one exact root/reusable job owner."""
    if name.startswith("Native pipeline <") and " / " in name:
        prefix, child = name.split(" / ", 1)
        match = re.fullmatch(r"Native pipeline <(.*?)>", prefix)
        if not match or not nested or "artifact-platform" not in root:
            fail(f"invalid reusable-workflow job name: {name}")
        platform = match.group(1)
        candidates = [key for key, job in nested.items() if job_pattern(job["name"]).fullmatch(child)]
        if len(candidates) != 1:
            fail(f"missing/ambiguous nested job mapping: {name} => {candidates}")
        return platform, candidates[0]
    candidates = [key for key, job in root.items()
                  if not job["uses"] and job_pattern(job["name"]).fullmatch(name)]
    if len(candidates) != 1:
        fail(f"missing/ambiguous root job mapping: {name} => {candidates}")
    return "", candidates[0]


def validate_pages(pages: list[dict]) -> list[dict]:
    if not isinstance(pages, list) or not pages:
        fail("missing job API pages")
    totals = {page.get("total_count") for page in pages if isinstance(page, dict)}
    if len(totals) != 1 or any(type(count) is not int or count < 0 for count in totals):
        fail("job pages changed total_count")
    total = next(iter(totals))
    if any(not isinstance(page.get("jobs"), list) or len(page["jobs"]) > 100 for page in pages):
        fail("malformed or overfull job page")
    if len(pages) > 1 and any(len(page["jobs"]) != 100 for page in pages[:-1]):
        fail("missing/interleaved API job page")
    rows = [job for page in pages for job in page["jobs"]]
    if len(rows) != total or len({j.get("id") for j in rows if isinstance(j, dict)}) != total:
        fail("incomplete or duplicate Actions jobs")
    if any(not isinstance(job, dict) or type(job.get("id")) is not int for job in rows):
        fail("malformed job ID")
    return rows


def analyze(run: dict, pages: list[dict], workflows: dict[str, str]) -> dict:
    if run.get("name") != "ci" or run.get("path") != WORKFLOW:
        fail("run is not the codeArbiter CI workflow")
    source = run.get("head_sha")
    if not isinstance(source, str) or not SHA_RE.fullmatch(source):
        fail("missing exact head SHA")
    if run.get("status") != "completed" or run.get("conclusion") not in ("success", "failure", "cancelled"):
        fail("run not in a terminal state")
    if WORKFLOW not in workflows:
        fail("missing exact root workflow source")
    root = parse_jobs(workflows[WORKFLOW])
    nested = parse_jobs(workflows[NESTED]) if NESTED in workflows else {}
    if any(job["uses"].endswith("ci-native-platform.yml") for job in root.values()) != bool(nested):
        fail("reusable native workflow source missing or unexpected")
    rows = validate_pages(pages)
    if run["conclusion"] == "success" and any(
            item.get("conclusion") not in ("success", "skipped") for item in rows):
        fail("successful run contains an unsuccessful job")
    run_created = run["created_at"]
    run_finished = run["updated_at"]
    if seconds(run_created, run_finished) < 0:
        fail("invalid workflow elapsed time")
    groups: dict[tuple[str, str], list[int]] = defaultdict(list)
    nodes: dict[int, dict] = {}
    for row in rows:
        if (row.get("run_id") != run.get("id") or row.get("head_sha") != source
                or row.get("status") != "completed"
                or row.get("conclusion") not in ("success", "failure", "cancelled", "skipped")
                or not isinstance(row.get("name"), str)):
            fail(f"mismatched job evidence: {row.get('id')}")
        platform, ident = identify(row["name"], root, nested)
        owner = nested[ident] if platform else root[ident]
        owner["observed_instances"] += 1
        start, finish = row.get("started_at"), row.get("completed_at")
        if not start or not finish:
            if row["conclusion"] != "skipped":
                fail("non-skipped job missing timestamps")
            duration, start_offset, finish_offset = 0.0, 0.0, 0.0
        else:
            duration = seconds(start, finish)
            start_offset = seconds(run_created, start)
            finish_offset = seconds(run_created, finish)
            if duration < 0 or start_offset < -2:
                fail(f"invalid timestamps for job {row['id']}")
        nodes[row["id"]] = {
            "id": row["id"], "name": row["name"],
            "key": (platform, ident), "duration": duration,
            "start_offset": start_offset, "finish_offset": finish_offset,
            "started_at": start, "finished_at": finish,
            "conclusion": row["conclusion"], "labels": row.get("labels", []),
            "parents": [], "ready_offset": 0.0, "delay": 0.0,
        }
        groups[(platform, ident)].append(row["id"])
    for node in nodes.values():
        platform, ident = node["key"]
        spec = nested[ident] if platform else root[ident]
        upstream = []
        if platform:
            for parent in root["artifact-platform"]["needs"]:
                upstream.extend(groups[("", parent)])
            for parent in spec["needs"]:
                upstream.extend(groups[(platform, parent)])
        else:
            for parent in spec["needs"]:
                if parent == "artifact-platform":
                    upstream.extend(node_id for (os_platform, _), ids in groups.items()
                                    if os_platform for node_id in ids)
                else:
                    upstream.extend(groups[("", parent)])
        if spec["needs"] and not upstream:
            fail(f"unresolved dependency for job {node['name']}")
        node["parents"] = sorted(set(upstream))
        node["ready_offset"] = max([nodes[parent]["finish_offset"] for parent in node["parents"]] + [0.0])
        if node["conclusion"] == "skipped" and not node["started_at"]:
            node["start_offset"] = node["ready_offset"]
            node["finish_offset"] = node["ready_offset"]
        node["delay"] = node["start_offset"] - node["ready_offset"]
        if node["delay"] < -2:
            fail(f"job began before required predecessor finished: {node['name']} ({node['delay']})")

    @lru_cache(maxsize=None)
    def earliest(node_id: int, active: frozenset[int] = frozenset()) -> float:
        if node_id in active:
            fail("cyclic workflow job dependency")
        node = nodes[node_id]
        return node["duration"] + max([earliest(parent, active | {node_id})
                                      for parent in node["parents"]] + [0.0])

    last = max(nodes, key=earliest)
    def model_chain(node_id: int) -> list[dict]:
        result: list[dict] = []
        while True:
            node = nodes[node_id]
            result.append({"job_id": node_id, "name": node["name"],
                           "work_seconds": node["duration"], "modeled_finish_seconds": earliest(node_id)})
            if not node["parents"]:
                return list(reversed(result))
            node_id = max(node["parents"], key=earliest)

    actual_last = max(nodes, key=lambda node_id: nodes[node_id]["finish_offset"])
    def actual_chain(node_id: int) -> list[dict]:
        result: list[dict] = []
        while True:
            node = nodes[node_id]
            result.append({"job_id": node_id, "name": node["name"],
                           "work_seconds": node["duration"], "ready_to_start_seconds": node["delay"],
                           "finished_seconds": node["finish_offset"]})
            if not node["parents"]:
                return list(reversed(result))
            node_id = max(node["parents"], key=lambda parent: nodes[parent]["finish_offset"])

    stamps: list[tuple[datetime, int]] = []
    for node in nodes.values():
        if node["started_at"] and node["finished_at"]:
            stamps.extend([(parse_time(node["started_at"]), 1), (parse_time(node["finished_at"]), -1)])
    live = peak = 0
    for _, delta in sorted(stamps):
        live += delta
        peak = max(peak, live)
    all_seconds = sum(n["duration"] for n in nodes.values())
    mac_nodes = [n for n in nodes.values() if isinstance(n["labels"], list)
                 and any(str(label).startswith("macos") for label in n["labels"])]
    gate = root.get("ci-passed")
    if not gate:
        fail("no protected final CI gate")
    # Count only the required_results assignment. Advisory probes and explicit
    # coverage/release checks elsewhere in the gate are NOT the same contract.
    gate_source = workflows[WORKFLOW].split("\n  ci-passed:\n", 1)
    if len(gate_source) != 2:
        fail("cannot isolate final gate")
    assignments = [line.strip().split('required_results="', 1)[1].split('"', 1)[0]
                   for line in gate_source[1].splitlines() if 'required_results="' in line]
    if len(assignments) != 1:
        fail("protected gate lacks a single required_results assignment")
    required = sorted(set(x or y for x, y in RESULT_RE.findall(assignments[0])))
    gate_needs = gate["needs"]
    if not set(required).issubset(gate_needs):
        fail("merge gate references an unregistered required job")
    if not any(node["key"] == ("", "ci-passed") for node in nodes.values()):
        fail("missing observed protected merge job")
    return {
        "format": "codearbiter.ci-critical-path/1",
        "repository": REPO, "run_id": run["id"], "head_sha": source,
        "status": run["conclusion"], "run_attempt": run["run_attempt"],
        "run_created_at": run_created, "run_updated_at": run_finished,
        "actual_run_seconds": seconds(run_created, run_finished),
        "jobs": len(nodes), "job_conclusions": dict(sorted(Counter(n["conclusion"] for n in nodes.values()).items())),
        "queue_free_replay_seconds": earliest(last),
        "queue_free_chain": model_chain(last),
        "actual_dependency_chain": actual_chain(actual_last),
        "total_runner_seconds": all_seconds,
        "macos_runner_seconds": sum(n["duration"] for n in mac_nodes),
        "macos_jobs": len(mac_nodes), "observed_peak_active_jobs": peak,
        "largest_ready_to_start_delays": [
            {"job_id": n["id"], "name": n["name"], "seconds": n["delay"], "work_seconds": n["duration"]}
            for n in sorted(nodes.values(), key=lambda n: -n["delay"])[:15]
        ],
        "source_to_job_map": [
            {"scope": "native-reusable" if key in nested else "root", "job_id": key,
             "name": job["name"], "needs": job["needs"], "selector": job["if"],
             "runs_on": job["runs_on"], "uses": job["uses"], "timeout": job["timeout"],
             "observed_instances": job["observed_instances"]}
            for owner in (root, nested) for key, job in owner.items()
        ],
        "gate_needs": gate_needs,
        "gate_required_results": required,
        # A missing required_results registration is not automatically an advisory
        # exception. This is a discovery finding, deliberately not a green gate.
        "gate_awaited_not_in_required_results": sorted(set(gate_needs) - set(required)),
        "gate_registration_contradiction": sorted(set(gate_needs) - set(required) - {"ca-pi-latest"}),
        "interpretation": "Zero-queue result is a counterfactual preserving measured job durations, not achieved CI. Ready-to-start delay includes provisioning/scheduling and does not identify an account quota.",
    }


def gh_json(url: str) -> dict:
    completed = subprocess.run(["gh", "api", url], text=True, encoding="utf-8",
                               capture_output=True, timeout=90, check=False)
    if completed.returncode != 0:
        fail("GitHub API unavailable: " + completed.stderr[-400:])
    result = json.loads(completed.stdout)
    if not isinstance(result, dict):
        fail("expected a GitHub JSON object")
    return result


def fetch_workflow(repository: str, source: str, path: str) -> bytes:
    import base64
    response = gh_json(f"repos/{repository}/contents/{path}?ref={source}")
    if response.get("type") != "file" or response.get("encoding") != "base64":
        fail(f"missing canonical GitHub file at {source}:{path}")
    raw = base64.b64decode(response["content"], validate=False)
    if not raw or len(raw) > 1_000_000:
        fail("workflow content missing or too large")
    return raw


def capture(run_id: int, directory: Path) -> dict:
    if directory.exists():
        fail("capture destination already exists")
    run = gh_json(f"repos/{REPO}/actions/runs/{run_id}")
    if run.get("id") != run_id or run.get("status") != "completed":
        fail("capture requires a fully completed Actions run")
    source = run.get("head_sha")
    if not isinstance(source, str) or not SHA_RE.fullmatch(source):
        fail("GitHub run has no immutable source commit")
    pages: list[dict] = []
    for page in range(1, 100):
        result = gh_json(f"repos/{REPO}/actions/runs/{run_id}/jobs?per_page=100&page={page}")
        pages.append(result)
        if sum(len(p["jobs"]) for p in pages) >= result["total_count"]:
            break
    validate_pages(pages)
    workflows = {WORKFLOW: fetch_workflow(REPO, source, WORKFLOW)}
    root = parse_jobs(workflows[WORKFLOW].decode("utf-8"))
    if any(job["uses"].endswith("ci-native-platform.yml") for job in root.values()):
        workflows[NESTED] = fetch_workflow(REPO, source, NESTED)
    report = analyze(run, pages, {name: value.decode("utf-8") for name, value in workflows.items()})
    directory.mkdir(parents=True, exist_ok=False)
    payloads = {"run.json.gz": gzip.compress(encode(run), mtime=0),
                "jobs-pages.json.gz": gzip.compress(encode(pages), mtime=0)}
    payloads.update({Path(name).name + ".gz": gzip.compress(raw, mtime=0)
                     for name, raw in workflows.items()})
    manifest = {"format": "codearbiter.ci-critical-path-inputs/1",
                "run_id": run_id, "head_sha": source, "repository": REPO,
                "files": {name: hash_bytes(data) for name, data in payloads.items()}}
    payloads["manifest.json"] = encode(manifest)
    payloads["replay.json.gz"] = gzip.compress(encode(report), mtime=0)
    for name, raw in payloads.items():
        (directory / name).write_bytes(raw)
    return report


def unpack(raw: bytes, limit: int = MAX_JSON_BYTES) -> bytes:
    """Bound gzip expansion before allocating untrusted decompressed evidence."""
    with gzip.GzipFile(fileobj=io.BytesIO(raw)) as stream:
        data = stream.read(limit + 1)
        if len(data) > limit or stream.read(1):
            fail("expanded capture input exceeds its bound")
        return data


def replay(directory: Path) -> dict:
    manifest = json.loads((directory / "manifest.json").read_text(encoding="utf-8"))
    if manifest.get("format") != "codearbiter.ci-critical-path-inputs/1" or manifest.get("repository") != REPO:
        fail("unknown capture format/repository")
    files = manifest.get("files")
    if not isinstance(files, dict) or not files:
        fail("missing capture file hashes")
    raw_files = {}
    for filename, expected in files.items():
        if filename not in ("run.json.gz", "jobs-pages.json.gz",
                            "ci.yml.gz", "ci-native-platform.yml.gz"):
            fail("unexpected capture input filename")
        raw = (directory / filename).read_bytes()
        if hash_bytes(raw) != expected:
            fail("capture input bytes changed: " + filename)
        raw_files[filename] = raw
    jobs_raw = unpack(raw_files["jobs-pages.json.gz"])
    run = json.loads(unpack(raw_files["run.json.gz"], 10 * 1024 * 1024))
    pages = json.loads(jobs_raw)
    if run.get("id") != manifest.get("run_id") or run.get("head_sha") != manifest.get("head_sha"):
        fail("manifest run identity mismatch")
    workflows = {WORKFLOW: unpack(raw_files["ci.yml.gz"], 2 * 1024 * 1024).decode("utf-8")}
    if "ci-native-platform.yml.gz" in raw_files:
        workflows[NESTED] = unpack(raw_files["ci-native-platform.yml.gz"], 2 * 1024 * 1024).decode("utf-8")
    return analyze(run, pages, workflows)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("mode", choices=("capture", "replay"))
    parser.add_argument("--run-id", type=int)
    parser.add_argument("--directory", required=True, type=Path)
    args = parser.parse_args()
    try:
        if args.mode == "capture":
            if not args.run_id or args.run_id < 1:
                parser.error("capture requires --run-id")
            report = capture(args.run_id, args.directory)
        else:
            if args.run_id is not None:
                parser.error("replay reads the immutable run ID from its capture")
            report = replay(args.directory)
        print(json.dumps({key: report[key] for key in ("run_id", "head_sha", "jobs", "actual_run_seconds",
                                                     "queue_free_replay_seconds", "total_runner_seconds",
                                                     "macos_runner_seconds")}, indent=2))
    except (OSError, ValueError, KeyError, TypeError, subprocess.TimeoutExpired,
            json.JSONDecodeError, EOFError, gzip.BadGzipFile) as error:
        parser.exit(1, f"CI benchmark evidence refused: {error}\n")


if __name__ == "__main__":
    main()
