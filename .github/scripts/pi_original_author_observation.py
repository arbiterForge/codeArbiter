"""Read the original installed Pi package's finite parent-author observation."""

import io
import json
import re
import zipfile
from pathlib import Path, PurePosixPath

import _pi_rpc_profile as rpc
import major_readiness as readiness
import pi_parent_tui_observation as fixture


PLATFORMS = {"linux/amd64": "linux", "darwin/arm64": "darwin"}
ASSEMBLY_JOB = "[CHECK] | [CORE] | Structured artifact package assembly"
OBSERVATION_UPLOAD = "Retain original Pi coordinator and execution records"
PAYLOADS = {
    "promoted-stage": ("artifact-host-payloads-", "Preserve the exact multi-host package overlay"),
    "release-packages": ("artifact-release-packages-", "Preserve the exact normal release package cohort"),
}
HARNESS = ".github/scripts/pi_parent_tui_observation.py"
PARENT = "producer/parent-author/"


def _job(jobs, run_id, source, name):
    matching = [row for row in jobs if row.get("name") == name]
    fixture.require(len(matching) == 1, "original Pi or assembly owner missing/ambiguous")
    job = matching[0]
    fixture.require(rpc.positive(job.get("id")) and job.get("run_id") == run_id
                    and job.get("run_attempt") == 1 and job.get("head_sha") == source
                    and job.get("status") == "completed" and job.get("conclusion") == "success",
                    "original Pi or assembly owner unsuccessful")
    return job


def _artifact(req, job, name, step, archive_dir, *, inventory=None):
    if inventory is None:
        artifact = readiness.exact_run_artifact(req["ci_run_id"], name)
    else:
        matches = [metadata for metadata in inventory if metadata.get("name") == name]
        fixture.require(len(matches) == 1, "original Pi artifact missing or ambiguous: " + name)
        artifact = matches[0]
    if archive_dir is None:
        data = readiness.artifact_bytes(artifact, req)
    else:
        with (archive_dir / (name + ".zip")).open("rb") as stream:
            data = stream.read(readiness.MAX_ARCHIVE + 1)
        fixture.require(len(data) <= readiness.MAX_ARCHIVE, "cached original ZIP exceeds bound")
        readiness.validate_artifact(artifact, req, fixture.sha(data))
    readiness.validate_upload(job, artifact, step)
    identity = {"artifact_id": artifact["id"], "archive_sha256": fixture.sha(data), "members": readiness.members(data)}
    return data, identity


def _member(archive, name, limit):
    matches = [row for row in archive.infolist() if row.filename == name]
    fixture.require(len(matches) == 1 and 0 < matches[0].file_size <= limit,
                    "required Pi archive member missing/ambiguous/oversized: " + name)
    return archive.read(matches[0])


def _json(archive, name):
    limit = 16 * 1024 * 1024
    return fixture.decode(_member(archive, name, limit), limit)


def _process(record, argv, *, terminal=False):
    rpc.closed(record, "argv returncode timed_out pid forced_cleanup exit_key_sent group_cleanup", "parent process")
    fixture.require(record["argv"] == argv and type(record["returncode"]) is int and record["returncode"] == 0
                    and rpc.positive(record["pid"]) and record["timed_out"] is False
                    and record["forced_cleanup"] is False and record["exit_key_sent"] is terminal
                    and record["group_cleanup"] == "already-gone", "parent process or owned cleanup incomplete")


def _terminal(archive, nonce, cwd, events):
    raw = _member(archive, PARENT + "parent.ansi", fixture.CAP)
    text = _member(archive, PARENT + "parent.readable.txt", fixture.CAP).decode("utf-8")
    fixture.require(text == fixture.readable(raw) and "PI-D07 fixture completed " + nonce in text,
                    "retained parent terminal differs")
    gate = fixture.PromptGate(nonce)
    fixture.require(type(events) is list and len(events) == len(gate.ops), "parent prompts missing")
    for index, event in enumerate(events):
        end = event["new_output_end"]
        fixture.require(type(end) is int and len(gate.raw) < end <= len(raw), "parent prompt byte range")
        gate.feed(raw[len(gate.raw):end])
        if index < len(events) - 1:
            fixture.require(gate.consent(cwd) == b"\r", "parent prompt exact approval differs")
        else:
            fixture.require(gate.consent(cwd) == b"j", "parent prompt decline selection differs")
            end = event["no_selected_output_end"]
            fixture.require(type(end) is int and len(gate.raw) < end <= len(raw), "parent decline byte range")
            gate.feed(raw[len(gate.raw):end])
            fixture.require(gate.consent(cwd) == b"\r", "parent prompt exact decline differs")
    fixture.require(gate.events == events, "retained parent prompts do not replay")


def _effects(archive, nonce, expected_read, protocol):
    values = _json(archive, PARENT + "effects.json")
    fixture.require(set(values) == {"file", "command"}, "retained effect population")
    effects = {}
    for name, record in values.items():
        rpc.closed(record, "bytes sha256 utf8", "retained effect")
        value = record["utf8"].encode("utf-8")
        fixture.require(type(record["bytes"]) is int and len(value) == record["bytes"] <= 4096
                        and fixture.sha(value) == record["sha256"], "retained effect bytes differ")
        effects[name] = value
    journal = _json(archive, PARENT + "journal.json")
    fixture.check_effects(nonce, journal, effects)
    rows = [entry["record"] for entry in journal]
    fixture.require(len({row["runId"] for row in rows}) == 1 and all(
        row["callerCorrelation"] == fixture.sha(protocol.parent_call_id.encode())
        and row["role"] == "backend-author"
        and row["permissionCorrelation"] == fixture.sha((protocol.parent_call_id + ":" + row["requestId"]).encode())
        and row.get("target") == (expected_read["path"] if row["tool"] in ("write", "edit") else None)
        for row in rows), "effect journal does not bind the same original author")
    return {name: values[name]["sha256"] for name in effects}


def _author_case(archive, observation, harness_digest):
    parent = lambda name: _json(archive, PARENT + name + ".json")
    outcome = parent("original-outcome")
    fixture.require(isinstance(outcome.get("author_read"), dict),
                    "original author did not retain its own read before edit")
    binding = observation["installed_binding"]
    worker = binding["worker"]
    source = binding["source_commit"]
    fixture.require(harness_digest == fixture.sha(Path(fixture.__file__).read_bytes())
                    == worker["source_before"]["inputs"].get(HARNESS), "original author fixture source differs")
    fixture.require(outcome["format"] == "codearbiter.pi-parent-tui-fixture/1" and outcome["source_commit"] == source
                    and outcome["actual_case"] == "executed" and outcome["inspection_turn"] == 5
                    and outcome["consent"] == "scripted-public-TUI-keys-not-human-consent"
                    and parent("verification") == {"status": "passed",
                        "scope": "first POSIX scripted public-parent-TUI fixture only; not human/full PI-D07/major qualification"}
                    and parent("cleanup") == {"provider_thread_stopped": True, "private_workspace_retained": True},
                    "original author fixture did not complete")
    acquisition = binding["acquisition"]
    runtime = acquisition["runtime_before"]
    cli = (PurePosixPath(acquisition["prefix"]) /
           "node_modules/@earendil-works/pi-coding-agent/dist/bundle/cli.js")
    workspace = PurePosixPath(acquisition["prefix"]).parent
    producer_path = PurePosixPath(binding["supervision"]["argv"][3])
    supervision = _json(archive, "producer/parent-author-supervision.json")
    fixture.require(rpc.completed(supervision) and supervision["timeout_seconds"] == 120
                    and supervision["body_seconds"] == fixture.BODY_SECONDS and supervision["argv"] == [
                        runtime["python"]["path"], "-I", "-B", str(producer_path.with_name(Path(HARNESS).name)),
                        "--config", str(workspace / "parent-author-config.json"),
                        "--authenticated-payloads", str(workspace / "parent-author-payloads.json")],
                    "original author supervision and acquisition differ")
    before, after = parent("input-before"), parent("input-after")
    expected = {"source": worker["source_before"], "runtime": runtime, "graph": acquisition["graph_after"],
                "installed": {name: row["sha256"] for name, row in worker["installed_before"].items()},
                "payloads": worker["payload_before"]}
    fixture.require(before == {**expected, "consumed_payloads": binding["consumed_payloads"]} and after == expected,
                    "parent fixture package/runtime differs from authenticated RPC installation")
    for fixture_key, snapshot_key in (("source", "source"), ("runtime", "runtime"), ("admitted_graph", "graph"),
                                      ("installed", "installed"), ("payload", "payloads")):
        fixture.require(outcome[fixture_key + "_before"] == outcome[fixture_key + "_after"] == expected[snapshot_key],
                        "parent outcome snapshot differs")
    fixture.require(outcome["consumed_payloads"] == binding["consumed_payloads"], "parent payload role differs")
    process = parent("parent-process")
    title = "Run only the deterministic owned PI-D07 fixture "
    nonce_match = re.fullmatch(title + r"([0-9a-f]{16})\.", process["argv"][-1])
    fixture.require(nonce_match is not None and process == outcome["process"], "retained parent process identity differs")
    nonce = nonce_match[1]
    parent_argv = [runtime["node"]["path"], str(cli), "--offline", "--no-session", "--approve", "--no-context-files",
                   "--provider", "openai", "--model", "gpt-fixture", title + nonce + "."]
    _process(process, parent_argv, terminal=True)
    _process(parent("git-init"), [runtime["git"]["path"], "init", "-q", "-b", "feature/pi-author-fixture"])
    _process(parent("package-install"), [*parent_argv[:2], "install", str(workspace / "installed-pi/package"), "--no-approve"])
    provider = outcome["provider"]
    fixture.require(type(provider) is list and len(provider) == fixture.PROVIDER_RECORDS, "original provider steps differ")
    for row in provider:
        rpc.closed(row, "request_sha256 bytes response_finish", "fixture provider record")
        fixture.require(rpc.digest(row["request_sha256"]) and rpc.positive(row["bytes"])
                        and row["bytes"] <= fixture.REQUEST_CAP, "fixture provider record invalid")
    finishes = ["tool_calls"] * 6 + ["stop", "tool_calls", "tool_calls", "stop", "tool_calls", "stop", "stop"]
    fixture.require([row["response_finish"] for row in provider] == finishes
                    and sum(row["bytes"] for row in provider) <= fixture.CAP, "original provider sequence differs")
    protocol = fixture.ProviderProtocol(nonce)
    expected_read = {"tool_call_id": "fixture-child-1-" + nonce, "path": protocol.ops[1]["params"]["path"],
                     "content_sha256": fixture.sha(("before-" + nonce).encode())}
    fixture.require(outcome["author_read"] == expected_read, "original author read result identity/content differs")
    _terminal(archive, nonce, str(workspace / "parent-author-fixture/project"), outcome["prompts"])
    return {"author_read": expected_read, "retained_effect_sha256": _effects(archive, nonce, expected_read, protocol),
            "verified_command_sha256": fixture.sha(protocol.ops[3]["params"]["command"].encode())}


def _read_case(req, owner, assembly, platform, harness_digest, capture, raw, payloads):
    source, run_id = req["source_commit"], req["ci_run_id"]
    with zipfile.ZipFile(io.BytesIO(raw)) as archive:
        complete = {"source_commit": source, "run_id": run_id, "job_id": owner["id"]}
        fixture.require(_json(archive, "coordinator-inputs.json") == {
            **complete, "source_tree": req["source_tree"], "attempt": 1, "platform": platform, "consumed": payloads}
            and _json(archive, "coordinator-complete.json") == {**complete, "phase": "complete"}
            and _json(archive, "producer/cleanup.json") == {"complete": True}, "original coordinator identity/cleanup differs")
        observation = _json(archive, "producer/observation.json")
        rpc.admit(observation, req=req, job_id=owner["id"], authenticated_payloads=payloads,
                  runtime_acquisition=_json(archive, "producer/runtime-acquisition.json"))
        fixture.require(observation["installed_binding"]["platform"] == platform, "original Pi platform differs")
        try:
            case = _author_case(archive, observation, harness_digest)
        except (KeyError, TypeError, AttributeError, IndexError, UnicodeError) as error:
            raise ValueError("malformed original author observation") from error
    return {**complete, "source_tree": req["source_tree"], "attempt": 1, "platform": platform,
            "scope": "scripted parent author on an owned fixture", "capture": capture,
            "assembly_job_id": assembly["id"], "payloads": {
                name: {field: identity[field] for field in ("artifact_id", "archive_sha256")}
                for name, identity in payloads.items()}, **case}


def read_original(repo, source, run_id, platform, *, archive_dir=None):
    """Authenticate one completed original POSIX run and its script-driven author case."""
    fixture.require(isinstance(source, str) and rpc.SHA.fullmatch(source) and rpc.positive(run_id)
                    and platform in PLATFORMS, "exact original POSIX Pi source/run/platform required")
    system = PLATFORMS[platform]
    with readiness.blob_transaction(repo):
        req = readiness.producer_requirements(repo, source, run_id)
        workflow_job = "[CHECK] | [PI  ] | Installed retained package <pi: " + system + " 1.5.0>"
        fixture.require(req["cell_jobs"].get("installed:pi:" + system + ":1.5.0") == workflow_job,
                        "original installed Pi owner route differs")
        harness_digest = fixture.sha(readiness.blob(repo, source, HARNESS))
    attempt = f"actions/runs/{run_id}/attempts/1"
    run = readiness.api(attempt)
    readiness.validate_run(run, req, producing=True, allow_program_branch=True)
    fixture.require(run.get("status") == "completed" and run.get("conclusion") == "success"
                    and run.get("run_attempt") == 1, "successful original CI attempt required")
    pages = json.loads(readiness.command([
        "gh", "api", "--paginate", "--slurp", f"repos/{readiness.REPOSITORY}/{attempt}/jobs?per_page=100"]))
    jobs = [job for page in pages for job in page["jobs"]]
    fixture.require(0 < len(jobs) <= 512 and len({job["id"] for job in jobs}) == len(jobs), "original job inventory differs")
    owner = _job(jobs, run_id, source, workflow_job)
    assembly = _job(jobs, run_id, source, ASSEMBLY_JOB)
    raw, capture = _artifact(req, owner, "installed-pi-observation-" + system + "-1", OBSERVATION_UPLOAD, archive_dir)
    payloads = {prefix + source: _artifact(req, assembly, prefix + source, step, archive_dir)[1]
                for prefix, step in PAYLOADS.values()}
    return _read_case(req, owner, assembly, platform, harness_digest, capture, raw, payloads)
