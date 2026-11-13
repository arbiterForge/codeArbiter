#!/usr/bin/env python3
"""Q-02: exact-byte, authenticated Actions readiness before major publication.

An integration run can test this verifier but cannot produce publication evidence.
The trusted main CI producer derives its required population from committed program
contracts and refuses unfinished work. The consumer authenticates the run and each
retained artifact through GitHub, then independently hashes downloaded bytes.
"""
from __future__ import annotations

import argparse
from datetime import datetime, timedelta
import hashlib
import io
import json
import os
from pathlib import Path, PurePosixPath
import re
import subprocess
import sys
import zipfile
from _boundedproc import start, terminate_tree

REPOSITORY = "arbiterForge/codeArbiter"
PROGRAM = "codearbiter-major-state-contracts"
SCHEMA = "codearbiter-major-readiness/1"
CORPUS = "docs/state-contracts-major/"
SHA = re.compile(r"(?!0{40}$)[0-9a-f]{40}")
DIGEST = re.compile(r"[0-9a-f]{64}")
MAX_ARCHIVE = 256 * 1024 * 1024
UPLOAD_ACTION = 'actions/upload-artifact@cf430e030ddbb5b0abf93d22962f4752f3646cd9'
TARGETS = frozenset(('ca', 'ca-codex', 'ca-pi', 'ca-sandbox'))


class ReadinessError(ValueError):
    pass


def require(condition, message):
    if not condition:
        raise ReadinessError(message)


def digest(data):
    return hashlib.sha256(data).hexdigest()


def command(argv, cwd=None):
    process = start(argv, cwd=cwd, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    try:
        stdout, _ = process.communicate(timeout=120)
    except subprocess.TimeoutExpired:
        containment = terminate_tree(process)
        try:
            process.communicate(timeout=3)
        except subprocess.TimeoutExpired:
            pass
        raise ReadinessError("readiness observation timed out; containment=" + containment) from None
    require(process.returncode == 0, "readiness observation failed: " + argv[0])
    return stdout


def blob(repo, source, path):
    return command(["git", "--no-lazy-fetch", "show", source + ":" + path], repo)


def candidate_marker(content):
    try:
        record = json.loads(content)
        require(isinstance(record, dict) and record.get('schema') == 'codearbiter-integration-candidate/1'
                and record.get('branch') == 'major/state-contracts'
                and isinstance(record.get('baseline_main_commit'), str)
                and SHA.fullmatch(record['baseline_main_commit']), 'malformed major-program candidate marker')
        versions = record.get('candidates')
        require(isinstance(versions, dict) and set(versions) == TARGETS
                and all(isinstance(v, str) and re.fullmatch(r'(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)', v)
                        for v in versions.values()), 'malformed major-program target versions')
        return versions
    except (ValueError, TypeError) as exc:
        raise ReadinessError('major-program candidate marker is unavailable or malformed') from exc


def applies(repo, source, target, version, effects):
    require(SHA.fullmatch(source or ""), "exact source commit required")
    versions = candidate_marker(blob(repo, source, '.github/integration-candidate.json'))
    require(target in versions and versions[target] == version,
            'major-program version mismatch; reselect through the declared owner while the program marker remains')
    # Receipt repair has no new tag/package/channel/public transition. Its
    # original successful publication is not repeated or retroactively gated.
    if set(effects.split()) <= {"receipt"}:
        return False
    return True


def evidence_paths(row):
    paths = {s['path'] for s in row.get('baseline', {}).get('source', [])}
    for ref in row.get('source_refs', []):
        require(isinstance(ref, str) and ':' in ref, 'invalid disposition source reference')
        paths.add(ref.split(':', 1)[1].split('#', 1)[0])
    return paths


def open_decisions(raw):
    """Match the canonical native question-board entry grammar.

    contextdocument/finalization.go validateQuestions distinguishes entries
    from explanatory or resolved-history prose. An active entry does not cease
    being unresolved merely because its description contains 'resolved'.
    """
    lines = raw.decode('utf-8').splitlines()
    require(lines and lines[0] == '# Open questions', 'authoritative question board missing or malformed')
    entry = re.compile(r'^(?:- )?(?:\[)?(CONFIRM-[0-9]{2,})(?:\])?(?::|\s+-)?\s+\S')
    found = set()
    for line in lines[1:]:
        line = line.strip()
        if not line.startswith(('CONFIRM-', '- [CONFIRM-', '[CONFIRM-')):
            continue
        match = entry.match(line)
        require(match and match[1] not in found, 'authoritative question entry malformed or duplicated')
        found.add(match[1])
    return sorted(found)


def authenticate_disposition(repo, candidate, cell, row, paths, load, cache):
    """Validate retained proof and applicability without relabelling its origin.

    A reviewed instruction may preserve many baseline rows. Local installed
    evidence remains local evidence; a hosted runner only authenticates its
    retained identities and the declared relationship to candidate inputs.
    """
    def ancestor(commit):
        require(isinstance(commit, str) and SHA.fullmatch(commit), 'invalid evidence source commit')
        if ('commit', commit) not in cache:
            command(['git', '--no-lazy-fetch', 'cat-file', '-e', commit + '^{commit}'], repo)
            command(['git', '--no-lazy-fetch', 'merge-base', '--is-ancestor', commit, candidate], repo)
            cache['commit', commit] = True
    def path_value(commit, path, expected):
        pure = PurePosixPath(path) if isinstance(path, str) else PurePosixPath('..')
        require(not pure.is_absolute() and '..' not in pure.parts and ':' not in str(pure)
                and '\\' not in str(pure) and DIGEST.fullmatch(expected or ''), 'invalid evidence path/digest')
        value = load(commit, path)
        require(digest(value) == expected, 'retained evidence bytes differ: ' + path)
        return value
    bound = []
    for item in row.get('evidence', []):
        require(item.get('kind') in ('test', 'sequence-test', 'installed-run', 'hosted-run', 'review', 'conformance-check', 'release-readback'),
                'unknown original evidence class')
        tested = item.get('commit')
        ancestor(tested)
        retained = item.get('ref_commit', candidate)
        ancestor(retained)
        key = ('proof', retained, item.get('ref'), item.get('sha256'))
        if key not in cache:
            content = path_value(retained, item.get('ref'), item.get('sha256'))
            record = json.loads(content)
            require(isinstance(record, dict) and record.get('schema') == 'codearbiter-disposition-evidence/1',
                    'unknown disposition proof schema')
            require(record.get('source_commit') == tested and record.get('kind') == item.get('kind'),
                    'disposition proof source/kind differs')
            producer = record.get('producer', {})
            require(isinstance(producer, dict)
                    and producer.get('class') in ('local-host', 'hosted', 'independent-review', 'source-conformance')
                    and isinstance(producer.get('identity'), str) and producer['identity'].strip(),
                    'disposition proof lacks original producer identity')
            raw = record.get('raw_evidence', [])
            require(isinstance(raw, list) and raw and all(isinstance(p, dict) for p in raw),
                    'disposition proof lacks original raw evidence')
            require(isinstance(record.get('disposition_ids'), list) and record['disposition_ids']
                    and len(set(record['disposition_ids'])) == len(record['disposition_ids']),
                    'disposition proof scope is malformed or duplicated')
            if producer['class'] == 'hosted':
                require(any('run_id' in p for p in raw), 'hosted proof lacks original hosted-run evidence')
            for proof in raw:
                if 'path' in proof:
                    path_value(retained, proof['path'], proof.get('sha256'))
                else:
                    # A hosted artifact is observed through authenticated API
                    # metadata, not through a URL or caller-authored pass flag.
                    run_id, job_id, artifact_id = (proof.get(k) for k in ('run_id', 'job_id', 'artifact_id'))
                    require(all(type(n) is int and n > 0 for n in (run_id, job_id, artifact_id)),
                            'invalid original hosted evidence identity')
                    run, job = api(f'actions/runs/{run_id}'), api(f'actions/jobs/{job_id}')
                    require(run.get('head_sha') == tested and run.get('event') == 'push'
                            and run.get('repository', {}).get('full_name') == REPOSITORY
                            and run.get('path') in ('.github/workflows/ci.yml', '.github/workflows/docs.yml')
                            and run.get('head_branch') in ('main', 'major/state-contracts')
                            and run.get('conclusion') == 'success'
                            and job.get('run_id') == run_id and job.get('conclusion') == 'success',
                            'original hosted evidence is unavailable or not applicable')
                    metadata = api(f'actions/artifacts/{artifact_id}')
                    expected = {'source_commit': tested, 'ci_run_id': run_id}
                    content = artifact_bytes(metadata, expected)
                    require(digest(content) == proof.get('sha256'), 'original hosted evidence digest differs')
            inputs = record.get('inputs', {})
            require(isinstance(inputs, dict) and inputs, 'disposition proof lacks checked inputs')
            for path, expected in inputs.items():
                path_value(tested, path, expected)
                path_value(candidate, path, expected)
            cache[key] = record
        record = cache[key]
        require(record.get('source_commit') == tested and record.get('kind') == item.get('kind'),
                'cached disposition proof source/kind differs')
        require(cell in record.get('disposition_ids', []), 'disposition proof does not cover ' + cell)
        require(paths <= set(record['inputs']),
                'disposition proof omits owning source inputs: ' + cell)
        result = record.get('result')
        allowed = {'PASSED', 'PRESERVED'} if row['status'] == 'PRESERVED' else {'PASSED'}
        if row['status'] == 'NOT_APPLICABLE':
            allowed = {'NOT_APPLICABLE'}
            require(record.get('contract') == row.get('contract') and record.get('rationale'), 'N/A proof lacks contract/rationale')
        require(result in allowed, 'disposition proof has no applicable affirmative result: ' + cell)
        if row['status'] not in ('PRESERVED', 'NOT_APPLICABLE'):
            commands = record.get('commands', [])
            require(commands and all(c.get('argv') and type(c.get('exit_code')) is int and c['exit_code'] == 0 for c in commands),
                    'tested disposition lacks executed original checks')
        if row['status'] in ('INSTALLED_QUALIFIED', 'RELEASED'):
            require(record['producer']['class'] in ('local-host', 'hosted') and record.get('host')
                    and record.get('platform') and record.get('installed_artifacts'), 'installed proof lacks actual host/package identity')
        bound.append({'ref': item['ref'], 'sha256': item['sha256'], 'source_commit': tested,
                      'producer_class': record['producer']['class']})
    require(bound, 'disposition has no retained proof: ' + cell)
    return bound


def bind_named_jobs(cell_jobs, policy):
    """Bind selected cells to existing owning jobs without inventing a second run.

    Unmapped cells retain their unresolved original group. They cannot pass
    production until an actual owning report and semantic selection exist.
    """
    overrides = policy.get('cell_job_bindings', {})
    require(isinstance(overrides, dict) and set(overrides) <= set(cell_jobs)
            and all(isinstance(name, str) and 0 < len(name) <= 512
                    and not any(ord(c) < 32 for c in name) for name in overrides.values()),
            'invalid explicit cell/job binding')
    return {cell: overrides.get(cell, name) for cell, name in cell_jobs.items()}


def requirements(repo, source, run_id):
    require(SHA.fullmatch(source or ""), "exact source commit required")
    require(type(run_id) is int and run_id > 0, "positive exact CI run id required")
    loaded, authenticated = {}, {}
    def load(commit, path):
        key = (commit, path)
        if key not in loaded:
            try:
                loaded[key] = blob(repo, commit, path)
            except (OSError, ValueError) as exc:
                raise ReadinessError('required source/evidence unavailable: ' + str(path)) from exc
        return loaded[key]
    def read(path):
        return json.loads(load(source, path))
    program = read(CORPUS + "contracts/program.json")
    tasks = read(CORPUS + "contracts/tasks.json")["tasks"]
    progress = read(CORPUS + "execution/progress.json")
    require(program["id"] == PROGRAM, "wrong program")
    required = sorted(t["id"] for t in tasks if t["required_before_publication"] and t["id"] != "Q-03")
    require(sorted(program["delivery_predicates"]["PREPUBLICATION_READY"]["required_task_ids"]) == required,
            "prepublication task population differs from program contract")
    updates = {t["id"]: t for t in progress["task_updates"]}
    for task in required:
        require(task in updates and updates[task]["status"] in ("TESTED", "INSTALLED_QUALIFIED", "DONE"),
                "unfinished required task: " + task)
    for item in progress.get("new_required_work", []):
        require(item.get("status") == "DONE", "unfinished added required work: " + item["id"])
        required.append(item["id"])
    require(not progress.get("pending_user_decisions") and not progress.get("scoped_blockers")
            and not progress.get("unknown_outcomes"), "program has unresolved decisions or outcomes")
    questions = load(source, '.codearbiter/open-questions.md')
    unresolved = open_decisions(questions)
    require(not unresolved, 'authoritative unresolved decisions: ' + ', '.join(unresolved))
    ledger = read(CORPUS + "execution/coverage-ledger.json")
    contracts = {
        'findings': {r['finding_id']: r for r in read(CORPUS + 'contracts/finding-dispositions.json')['records']},
        'machines': {r['machine_id']: r for r in read(CORPUS + 'contracts/machine-coverage.json')['machines']},
        'transitions': {r['transition_id']: r for r in read(CORPUS + 'contracts/transition-coverage.json')['transitions']},
        'added_transitions': {r['transition_id']: r for r in progress.get('new_transition_rows', [])},
    }
    expected_groups = {group: set(rows) for group, rows in contracts.items()}
    for group, identities in expected_groups.items():
        require(set(ledger.get(group, {})) == identities, "disposition population differs: " + group)
    require(program.get("counts") == {"tasks": 82, "findings": 70, "machines": 287,
                                     "transitions": 1748, "composed_scenarios": 31},
            "frozen program population differs")
    for entry in read(CORPUS + "MANIFEST.json")["files"]:
        path = PurePosixPath(entry["path"])
        require(not path.is_absolute() and ".." not in path.parts, "invalid frozen intake path")
        content = blob(repo, source, CORPUS + entry["path"])
        require(len(content) == entry["bytes"] and digest(content) == entry["sha256"],
                "frozen intake identity differs: " + entry["path"])
    dispositions, disposition_jobs = {}, {}
    task_owners = {t['id']: t['owner'] for t in tasks}
    for group in ("findings", "machines", "transitions", "added_transitions"):
        for identity, row in ledger.get(group, {}).items():
            require(row["status"] in ("TESTED", "INSTALLED_QUALIFIED", "RELEASED", "PRESERVED", "NOT_APPLICABLE")
                    and row.get("evidence"), "unqualified disposition: " + identity)
            if row["status"] == "NOT_APPLICABLE":
                require(row.get("contract"), "N/A lacks contract: " + identity)
            for evidence in row["evidence"]:
                require(evidence.get("ref") and SHA.fullmatch(evidence.get("commit", "")),
                        "disposition evidence lacks source identity: " + identity)
            if row["status"] not in ("PRESERVED", "NOT_APPLICABLE"):
                require(any(e.get("kind") in ("test", "sequence-test", "installed-run", "hosted-run", "conformance-check")
                            for e in row["evidence"]), "disposition lacks executed evidence: " + identity)
            cell = 'disposition:' + group + ':' + identity
            contract = contracts[group][identity]
            paths = evidence_paths(contract)
            require(paths, 'disposition has no source scope: ' + cell)
            dispositions[cell] = authenticate_disposition(repo, source, cell, row, paths, load, authenticated)
            owner_name = row.get('owner') or contract.get('owner')
            if not owner_name:
                owners = {task_owners[t] for t in row.get('task_ids', [])}
                require(len(owners) == 1, 'disposition owner requires explicit assignment: ' + cell)
                owner_name = owners.pop()
            disposition_jobs[cell] = 'major qualification / ' + owner_name
    # Accepted lifecycle identities are validated by the existing immutable owner,
    # not inferred from an accepted label inside this record.
    command([sys.executable, str(Path(__file__).with_name("check_adr_lifecycle.py")),
             "--root", str(repo), "--current-ref", source], repo)
    ledger_bytes = blob(repo, source, ".codearbiter/decisions/adr-lifecycle.jsonl")
    targets = candidate_marker(load(source, '.github/integration-candidate.json'))
    prefixes = {"ca": "v", "ca-codex": "ca-codex-v", "ca-pi": "ca-pi-v", "ca-sandbox": "ca-sandbox-v"}
    scenarios = read(CORPUS + "contracts/scenarios.json")["scenarios"]
    cells = ["task:" + t for t in required] + ["scenario:" + s["id"] for s in scenarios] + list(dispositions)
    owners = {t["id"]: t["owner"] for t in tasks}
    owners.update({t["id"]: t["owner"] for t in progress.get("new_required_work", [])})
    cell_jobs = {"task:" + t: "major qualification / " + owners[t] for t in required}
    cell_jobs.update({"scenario:" + s["id"]: "major qualification / scenarios" for s in scenarios})
    cell_jobs.update(disposition_jobs)
    policy = read(".github/major-qualification-policy.json")
    require(policy.get("program_id") == PROGRAM and policy.get("required_installed_cells"),
            "installed qualification policy missing")
    routes = policy.get('owner_job_routes', {})
    require(isinstance(routes, dict) and all(isinstance(k, str) and isinstance(v, str) and k and v
                                           for k, v in routes.items()), 'invalid explicit owner/job routes')
    for cell, job_name in list(cell_jobs.items()):
        if cell.startswith('disposition:'):
            original_owner = job_name.removeprefix('major qualification / ')
            cell_jobs[cell] = 'major qualification / ' + routes.get(original_owner, original_owner)
    cells.extend(policy["required_installed_cells"])
    cell_jobs.update({cell: "major qualification / " + cell for cell in policy["required_installed_cells"]})
    cell_jobs = bind_named_jobs(cell_jobs, policy)
    require(len(cells) == len(set(cells)), "duplicate required cell")
    return {"source_commit": source,
            "source_tree": command(["git", "rev-parse", source + "^{tree}"], repo).decode().strip(),
            "ci_run_id": int(run_id), "task_ids": sorted(required),
            "task_manifest_sha256": digest(blob(repo, source, CORPUS + "execution/progress.json")),
            "dispositions_sha256": digest(blob(repo, source, CORPUS + "execution/coverage-ledger.json")),
            "decisions_sha256": digest(ledger_bytes),
            "open_questions_sha256": digest(questions), "unresolved_decision_count": len(unresolved),
            "disposition_evidence_sha256": digest(json.dumps(dispositions, sort_keys=True, separators=(',', ':')).encode()),
            "targets": [{"target": t, "version": targets[t], "tag": prefixes[t] + targets[t]} for t in sorted(targets)],
            "cells": sorted(cells), "cell_jobs": cell_jobs,
            "required_artifact_names": ["artifact-host-payloads-" + source,
                                        "artifact-release-packages-" + source]}


def members(archive):
    require(len(archive) <= MAX_ARCHIVE, "qualification archive exceeds bound")
    result, seen, total = [], set(), 0
    with zipfile.ZipFile(io.BytesIO(archive)) as z:
        require(len(z.infolist()) <= 4096, "too many artifact members")
        for item in z.infolist():
            p = PurePosixPath(item.filename)
            require(not p.is_absolute() and ".." not in p.parts and "\\" not in item.orig_filename
                    and "\x00" not in item.orig_filename and ":" not in item.orig_filename
                    and p.as_posix() == item.orig_filename.rstrip("/")
                    and not item.flag_bits & 1 and (item.external_attr >> 16) & 0o170000 != 0o120000,
                    "unsafe qualification artifact member")
            if item.is_dir():
                continue
            require(item.filename not in seen, "duplicate qualification artifact member")
            seen.add(item.filename)
            total += item.file_size
            require(total <= MAX_ARCHIVE and item.file_size <= 64 * 1024 * 1024,
                    "qualification archive expansion exceeds bound")
            result.append({"path": item.filename, "sha256": digest(z.read(item))})
    require(result, "empty qualification artifact")
    return sorted(result, key=lambda r: r["path"])


def validate_run(run, req, producing=False):
    require(isinstance(run, dict) and run.get("id") == req["ci_run_id"]
            and run.get("head_sha") == req["source_commit"] and run.get("event") == "push"
            and run.get("head_branch") == "main"
            and (run.get("conclusion") == "success" or producing and run.get("conclusion") is None)
            and run.get("path") == ".github/workflows/ci.yml"
            and run.get("repository", {}).get("full_name") == REPOSITORY,
            "qualification run is not successful trusted main CI for the exact source")


def validate_artifact(artifact, req, archive_digest):
    require(isinstance(artifact, dict) and artifact.get("expired") is False
            and type(artifact.get("id")) is int and artifact["id"] > 0
            and type(artifact.get("size_in_bytes")) is int and 0 < artifact["size_in_bytes"] <= MAX_ARCHIVE
            and artifact.get("workflow_run", {}).get("id") == req["ci_run_id"]
            and artifact.get("workflow_run", {}).get("head_sha") == req["source_commit"]
            and DIGEST.fullmatch(archive_digest or "")
            and artifact.get("digest") == "sha256:" + archive_digest,
            "missing, expired, mismatched or unauthenticated artifact")


def validate_upload(job, artifact, step_name):
    """Bind an artifact to the exact successful upload step in its claimed job.

    Artifact metadata identifies a run, not its uploader job. Authenticate the
    job's upload action, time window, finalized ID/name and archive digest from
    its original Actions log instead of trusting a report's claimed job ID.
    """
    steps = [s for s in job.get('steps', []) if s.get('name') == step_name]
    require(len(steps) == 1 and steps[0].get('status') == 'completed'
            and steps[0].get('conclusion') == 'success', 'required exact upload step did not succeed')
    try:
        step = steps[0]
        start = datetime.fromisoformat(step['started_at'].replace('Z', '+00:00'))
        end = datetime.fromisoformat(step['completed_at'].replace('Z', '+00:00')) + timedelta(seconds=1)
        created = datetime.fromisoformat(artifact['created_at'].replace('Z', '+00:00'))
        require(start.tzinfo and end.tzinfo and created.tzinfo and end >= start, 'invalid upload time identity')
        require(start <= created <= end, 'artifact created outside claimed upload step')
        raw = api(f"actions/jobs/{job['id']}/logs", binary=True)
        require(len(raw) <= 32 * 1024 * 1024, 'upload attribution log exceeds bound')
        selected = []
        for line in raw.decode('utf-8-sig').splitlines():
            stamp, _, message = line.partition(' ')
            if not stamp.endswith('Z'):
                continue
            time = datetime.fromisoformat(stamp.replace('Z', '+00:00'))
            if start <= time <= end:
                selected.append(message)
        text = '\n'.join(selected)
        require('##[group]Run ' + UPLOAD_ACTION in text,
                'claimed upload step did not run the pinned artifact uploader')
        require('SHA256 digest of uploaded artifact is ' + artifact['digest'].removeprefix('sha256:') in text
                and f"Artifact {artifact['name']} successfully finalized. Artifact ID {artifact['id']}" in text,
                'artifact ID/name/digest not finalized by claimed upload job')
    except (KeyError, ValueError, UnicodeError) as exc:
        raise ReadinessError('upload attribution unavailable or malformed') from exc


def verify(*, record, requirements, run, artifact, archive_digest, jobs, build_artifacts,
           payload_members=None):
    req = requirements
    validate_run(run, req)
    validate_artifact(artifact, req, archive_digest)
    require(artifact.get("name") == "major-readiness-" + req["source_commit"], "wrong readiness artifact")
    require(isinstance(record, dict) and record.get("schema") == SCHEMA
            and record.get("program_id") == PROGRAM and record.get("state") == "PREPUBLICATION_READY",
            "missing valid prepublication readiness record")
    require(set(record) == {"schema", "program_id", "state", "results", "artifacts", "producer_job_id", *req},
            "unexpected readiness record fields")
    require("Q-03" not in req["task_ids"], "Q-03 cannot be a prepublication prerequisite")
    for field in req:
        require(record.get(field) == req[field], "readiness differs from selected " + field)
    by_job = {j["id"]: j for j in jobs}
    producer = by_job.get(record.get('producer_job_id'), {})
    require(producer.get('name') == 'major readiness producer' and producer.get('conclusion') == 'success',
            'readiness producer job did not succeed')
    validate_upload(producer, artifact, 'Upload major readiness record')
    by_artifact = {a["id"]: a for a in build_artifacts}
    rows = record.get("results", [])
    require(len(rows) == len(req["cells"]) and sorted(r.get("cell", "") for r in rows) == sorted(req["cells"]),
            "missing, extra or duplicate qualification cell")
    qualified_ids = set()
    for row in rows:
        job = by_job.get(row.get("job_id"), {})
        require(row.get("result") == "PASSED" and job.get("conclusion") == "success"
                and job.get("name") == req["cell_jobs"][row["cell"]],
                "required qualification cell lacks successful named execution: " + row["cell"])
        qualified_ids.add(row.get("evidence_artifact_id"))
    archives = record.get("artifacts", [])
    require(archives and len({a["artifact_id"] for a in archives}) == len(archives), "missing or duplicate payload artifacts")
    for payload in archives:
        identity = payload["artifact_id"]
        require(identity in qualified_ids, "artifact has no executed qualification")
        validate_artifact(by_artifact.get(identity), req, payload.get("archive_sha256"))
        require(payload.get("members") and all(DIGEST.fullmatch(m.get("sha256", "")) for m in payload["members"]),
                "payload member digests missing")
        if payload_members is not None:
            require(payload["members"] == payload_members.get(identity), "qualified payload members differ")
    require(qualified_ids == {a["artifact_id"] for a in archives}, "qualification names missing evidence artifact")
    names = {by_artifact[a["artifact_id"]]["name"] for a in archives}
    require(set(req["required_artifact_names"]) <= names, "exact host payload and release package cohorts required")
    return {"state": "PREPUBLICATION_READY", "source": req["source_commit"], "ci_run_id": req["ci_run_id"]}


def api(path, binary=False):
    raw = command(["gh", "api", "repos/" + REPOSITORY + "/" + path])
    return raw if binary else json.loads(raw)


def artifact_bytes(artifact, req):
    require(isinstance(artifact, dict), "required qualification artifact missing")
    declared = artifact.get("digest", "").removeprefix("sha256:")
    validate_artifact(artifact, req, declared)  # validate identity and size before download
    content = api(f"actions/artifacts/{artifact['id']}/zip", binary=True)
    validate_artifact(artifact, req, digest(content))
    require(len(content) <= MAX_ARCHIVE, "artifact download exceeds bound")
    return content


def collect(repo, source, run_id, producing=False):
    req = requirements(repo, source, run_id)
    run = api(f"actions/runs/{run_id}")
    validate_run(run, req, producing)
    # gh's complete paginated list is bounded before consumption.
    artifacts = json.loads(command(["gh", "api", "--paginate", "--slurp",
        f"repos/{REPOSITORY}/actions/runs/{run_id}/artifacts?per_page=100"]))
    artifacts = [a for p in artifacts for a in p["artifacts"]]
    require(len(artifacts) <= 512, "artifact population exceeds bound")
    require(len({a["id"] for a in artifacts}) == len(artifacts)
            and len({a["name"] for a in artifacts}) == len(artifacts),
            "duplicate or ambiguous retained artifact population")
    jobs = json.loads(command(["gh", "api", "--paginate", "--slurp",
        f"repos/{REPOSITORY}/actions/runs/{run_id}/jobs?filter=latest&per_page=100"]))
    jobs = [j for p in jobs for j in p["jobs"]]
    return req, run, artifacts, jobs


def read_artifact_json(artifact, req, filename):
    require(isinstance(artifact, dict), "required qualification artifact missing")
    content = artifact_bytes(artifact, req)
    require(len(content) <= 8 * 1024 * 1024, "qualification report archive exceeds bound")
    with zipfile.ZipFile(io.BytesIO(content)) as z:
        members(content)
        require(z.namelist() == [filename], "unexpected qualification report archive contents")
        require(z.getinfo(filename).file_size <= 4 * 1024 * 1024, "qualification report exceeds bound")
        return json.loads(z.read(filename))


def report_payloads(report, rows):
    """Resolve the v2 intern table without changing per-cell byte admission.

    Existing v1 reports retain their per-row archive/member bindings. The v2
    table is closed over the exact referenced IDs: no duplicate, absent,
    unused or ambiguous row-local binding can be silently ignored.
    """
    if report.get("schema") == "codearbiter-major-qualification/1":
        require("payloads" not in report, "ambiguous legacy qualification payload table")
        return None
    require(report.get("schema") == "codearbiter-major-qualification/2",
            "unsupported qualification report schema")
    table = report.get("payloads")
    require(isinstance(table, list) and 0 < len(table) <= len(rows),
            "qualification payload table missing or unbounded")
    result = {}
    for entry in table:
        require(isinstance(entry, dict) and set(entry) == {"artifact_id", "archive_sha256", "members"}
                and type(entry.get("artifact_id")) is int and entry["artifact_id"] > 0
                and entry["artifact_id"] not in result
                and isinstance(entry.get("archive_sha256"), str)
                and DIGEST.fullmatch(entry["archive_sha256"])
                and isinstance(entry.get("members"), list) and entry["members"],
                "invalid or duplicate qualification payload table entry")
        result[entry["artifact_id"]] = entry
    require(all(type(row.get("payload_artifact_id")) is int
                and "payload_members" not in row and "payload_archive_sha256" not in row for row in rows)
            and set(result) == {row["payload_artifact_id"] for row in rows},
            "qualification payload references missing, extra or ambiguous")
    return result


def produce(req, artifacts, jobs):
    """Build only from authenticated run artifacts emitted by successful test jobs.

    No project report file or caller-supplied pass flag is an input. Each job's
    artifact binds its actual command population and exact package artifact IDs.
    """
    by_name = {a["name"]: a for a in artifacts}
    by_id = {a["id"]: a for a in artifacts}
    results, payloads = [], {}
    expected_jobs = set(req["cell_jobs"].values())
    for name in sorted(expected_jobs):
        matches = [j for j in jobs if j["name"] == name]
        require(len(matches) == 1 and matches[0].get("conclusion") == "success",
                "required qualification job is missing or unsuccessful: " + name)
        job = matches[0]
        report_artifact = by_name.get("major-qualification-" + str(job["id"]))
        require(isinstance(report_artifact, dict), 'required original qualification report missing')
        validate_upload(job, report_artifact, 'Upload major qualification report')
        report = read_artifact_json(report_artifact, req, "qualification.json")
        require(report.get("schema") in ("codearbiter-major-qualification/1", "codearbiter-major-qualification/2")
                and report.get("source_commit") == req["source_commit"]
                and report.get("source_tree") == req["source_tree"]
                and report.get("ci_run_id") == req["ci_run_id"] and report.get("job_id") == job["id"],
                "qualification report source or runner identity differs")
        expected = sorted(c for c in req["cells"] if req["cell_jobs"][c] == name)
        rows = report.get("results", [])
        require(sorted(r.get("cell", "") for r in rows) == expected,
                "qualification report population differs: " + name)
        retained_payloads = report_payloads(report, rows)
        for row in rows:
            require(row.get("result") == "PASSED" and row.get("commands")
                    and row.get("selected_population") == row.get("executed_population")
                    and type(row.get("executed_population")) is int and row["executed_population"] > 0
                    and all(type(c.get("exit_code")) is int and c["exit_code"] == 0
                            and isinstance(c.get("argv"), list) and c["argv"]
                            and all(isinstance(arg, str) and arg for arg in c["argv"])
                            for c in row["commands"]),
                    "required cell lacks affirmative executed evidence: " + row["cell"])
            payload_id = row.get("payload_artifact_id")
            require(payload_id in by_id, "qualification payload artifact missing")
            if payload_id not in payloads:
                payload = by_id[payload_id]
                content = artifact_bytes(payload, req)
                payloads[payload_id] = {"artifact_id": payload_id,
                    "archive_sha256": digest(content), "members": members(content)}
            binding = row if retained_payloads is None else retained_payloads[payload_id]
            require(binding.get("payload_archive_sha256" if retained_payloads is None else "archive_sha256")
                    == payloads[payload_id]["archive_sha256"]
                    and binding.get("payload_members" if retained_payloads is None else "members") == payloads[payload_id]["members"],
                    "executed qualification bytes differ from retained payload: " + row["cell"])
            results.append({"cell": row["cell"], "result": "PASSED", "job_id": job["id"],
                            "evidence_artifact_id": payload_id,
                            "report_artifact_id": report_artifact["id"]})
    require(set(req["required_artifact_names"]) <= {by_id[i]["name"] for i in payloads},
            "qualification has no complete exact package cohort")
    producers = [j for j in jobs if j.get('name') == 'major readiness producer']
    require(len(producers) == 1, 'exact readiness producer job identity required')
    return {"schema": SCHEMA, "program_id": PROGRAM, "state": "PREPUBLICATION_READY",
            "producer_job_id": producers[0]['id'],
            **req, "results": sorted(results, key=lambda r: r["cell"]),
            "artifacts": list(payloads.values())}


def main(argv=None):
    p = argparse.ArgumentParser()
    p.add_argument("operation", choices=("verify", "requirements", "produce"))
    p.add_argument("--repo", type=Path, default=Path(__file__).resolve().parents[2])
    p.add_argument("--source", required=True)
    p.add_argument("--ci-run-id", type=int, required=True)
    p.add_argument("--output", type=Path)
    p.add_argument("--target")
    p.add_argument("--version")
    p.add_argument("--effects", default="publish")
    a = p.parse_args(argv)
    try:
        if a.operation == "verify" and a.target:
            require(a.version, "target verification requires version")
            if not applies(a.repo, a.source, a.target, a.version, a.effects):
                print("No new publication effect; major readiness does not repeat receipt-only repair")
                return 0
        if a.operation == "requirements":
            print(json.dumps(requirements(a.repo, a.source, a.ci_run_id), sort_keys=True))
            return 0
        if a.operation == "produce":
            require(os.environ.get("GITHUB_ACTIONS") == "true"
                    and os.environ.get("GITHUB_REPOSITORY") == REPOSITORY
                    and os.environ.get("GITHUB_RUN_ID") == str(a.ci_run_id)
                    and os.environ.get("GITHUB_SHA") == a.source and a.output,
                    "producer must run in the exact trusted CI run")
            req, run, artifacts, jobs = collect(a.repo, a.source, a.ci_run_id, producing=True)
            receipt = produce(req, artifacts, jobs)
            a.output.write_text(json.dumps(receipt, sort_keys=True, indent=2) + "\n", encoding="utf-8")
            print("PREPUBLICATION_READY receipt produced from authenticated executed evidence")
            return 0
        req, run, artifacts, jobs = collect(a.repo, a.source, a.ci_run_id)
        candidates = [x for x in artifacts if x["name"] == "major-readiness-" + a.source]
        require(len(candidates) == 1, "exactly one retained major-readiness artifact required")
        artifact = candidates[0]
        archive = artifact_bytes(artifact, req)
        with zipfile.ZipFile(io.BytesIO(archive)) as z:
            members(archive)
            require(z.namelist() == ["major-readiness.json"], "unexpected readiness archive contents")
            require(z.getinfo("major-readiness.json").file_size <= 4 * 1024 * 1024, "readiness exceeds bound")
            record = json.loads(z.read("major-readiness.json"))
        observed_members = {}
        for payload in record.get("artifacts", []):
            metadata = next((x for x in artifacts if x["id"] == payload["artifact_id"]), None)
            validate_artifact(metadata, req, payload.get("archive_sha256"))
            content = artifact_bytes(metadata, req)
            require(digest(content) == payload.get("archive_sha256"), "payload archive digest differs")
            observed_members[payload["artifact_id"]] = members(content)
        # Rebuild the record from the test jobs' original authenticated reports;
        # a readiness uploader cannot invent a passed cell after those jobs ran.
        require(record == produce(req, artifacts, jobs), "readiness differs from original qualification evidence")
        print(json.dumps(verify(record=record, requirements=req, run=run, artifact=artifact,
            archive_digest=digest(archive), jobs=jobs, build_artifacts=artifacts, payload_members=observed_members)))
        return 0
    except (ReadinessError, OSError, ValueError, KeyError, TypeError, zipfile.BadZipFile) as exc:
        print("::error::Major publication pending: " + str(exc), file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
