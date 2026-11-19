"""Join the two original POSIX Pi author cases outside the ordinary readiness receipt."""

import major_readiness as owner
import pi_original_author_observation as original


CELL = "scenario:SEQ-12"
SELECTION = "pi_author_scenarios"
PIN = "pi_author_harness_sha256"


def requirements(policy, cells, source, load):
    if SELECTION not in policy:
        return {}
    owner.require(policy[SELECTION] == [CELL] and CELL in cells, "Pi author scenario selection differs")
    return {SELECTION: [CELL], PIN: owner.digest(load(source, original.HARNESS))}


def runtime_requirements(req):
    owner.require(req.get(SELECTION) == [CELL] and req["cells"].count(CELL) == 1
                  and req["cell_jobs"].get(CELL) == "major qualification / scenarios"
                  and isinstance(req.get(PIN), str) and owner.DIGEST.fullmatch(req[PIN]),
                  "Pi author scenario requirements differ")
    return {**{key: value for key, value in req.items() if key not in (SELECTION, PIN)},
            "cells": [cell for cell in req["cells"] if cell != CELL],
            "cell_jobs": {cell: name for cell, name in req["cell_jobs"].items() if cell != CELL}}


def inner_record(record):
    inner = record.get("runtime")
    owner.require(isinstance(inner, dict) and inner.get("schema") in (
        owner.SCHEMA, owner.SOURCE_SCHEMA, "codearbiter-major-readiness/2", "codearbiter-major-readiness/4",
        "codearbiter-major-site-source-readiness/1", "codearbiter-major-component-source-readiness/1"),
        "invalid Pi author envelope runtime schema")
    return inner


def admit(req, run, artifacts, jobs, *, producing=False):
    owner.validate_run(run, req, producing=producing)
    owner.require(type(run.get("run_attempt")) is int and run["run_attempt"] == 1
                  and ((run.get("status") == "completed" and run.get("conclusion") == "success")
                       or (producing and run.get("status") == "in_progress" and run.get("conclusion") is None)),
                  "Pi author evidence requires original main CI attempt 1")
    runtime_requirements(req)
    source, run_id = req["source_commit"], req["ci_run_id"]
    assembly = original._job(jobs, run_id, source, original.ASSEMBLY_JOB)
    instances = {}
    for platform, system in original.PLATFORMS.items():
        name = "[CHECK] | [PI  ] | Installed retained package <pi: " + system + " 1.5.0>"
        owner.require(req["cell_jobs"].get("installed:pi:" + system + ":1.5.0") == name,
                      "installed Pi author owner route differs")
        instances[platform] = (system, original._job(jobs, run_id, source, name))
    payloads = {prefix + source: original._artifact(req, assembly, prefix + source, step, None, inventory=artifacts)[1]
                for prefix, step in original.PAYLOADS.values()}
    cases = {}
    for platform, (system, job) in instances.items():
        raw, capture = original._artifact(req, job, "installed-pi-observation-" + system + "-1",
                                          original.OBSERVATION_UPLOAD, None, inventory=artifacts)
        cases[platform] = original._read_case(req, job, assembly, platform, req[PIN], capture, raw, payloads)
    identities = [p["artifact_id"] for p in payloads.values()] + [case["capture"]["artifact_id"] for case in cases.values()]
    owner.require(len(set(identities)) == len(identities), "Pi author archives alias the same artifact")
    return {"cell": CELL, "result": "PASSED", "cases": cases}


def produce(req, artifacts, jobs):
    run = owner.api(f"actions/runs/{req['ci_run_id']}")
    author = admit(req, run, artifacts, jobs, producing=True)
    return {"schema": owner.PI_AUTHOR_SCHEMA, "program_id": owner.PROGRAM, "state": "PREPUBLICATION_READY",
            **req, "author": author, "runtime": owner.produce(runtime_requirements(req), artifacts, jobs)}


def verify(*, record, requirements, run, artifact, archive_digest, jobs, build_artifacts, payload_members=None):
    req = requirements
    owner.validate_run(run, req)
    owner.require(isinstance(record, dict) and set(record) == {"schema", "program_id", "state", "author", "runtime", *req}
                  and record.get("schema") == owner.PI_AUTHOR_SCHEMA and record.get("program_id") == owner.PROGRAM
                  and record.get("state") == "PREPUBLICATION_READY"
                  and all(record.get(key) == value for key, value in req.items()),
                  "Pi author readiness differs from original requirements")
    runtime = inner_record(record)
    owner.require(record["author"] == admit(req, run, build_artifacts, jobs),
                  "Pi author readiness differs from authenticated original cases")
    return owner.verify(record=runtime, requirements=runtime_requirements(req), run=run, artifact=artifact,
                        archive_digest=archive_digest, jobs=jobs, build_artifacts=build_artifacts,
                        payload_members=payload_members)
