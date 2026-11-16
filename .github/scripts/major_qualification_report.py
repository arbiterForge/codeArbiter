#!/usr/bin/env python3
"""Named-test observations and exact-payload reports for Q-02.

Observers reuse an owning test execution. Selection maps are reviewed semantic
claims, not discovery or pass flags. Missing mappings, skipped selected tests,
source drift and source-only claims about installed hosts refuse emission.
Only trusted main/program push CI can emit reports; final readiness remains main-only.
The existing readiness owner
authenticates its original upload job and archive independently.
"""
from __future__ import annotations

import argparse
from contextlib import ExitStack
import hashlib
import io
import zipfile
import json
import os
from pathlib import Path, PurePosixPath
import runpy
import stat
import subprocess
import sys
import traceback
import unittest
from unittest import mock

import major_readiness as readiness
import ci20_native_binding as native_binding_owner
from _boundedproc import start as start_process, terminate_tree
from _gitexec import local_read_git_env

ROOT = Path(__file__).resolve().parents[2]
OBSERVATION = "codearbiter.major-test-observation/1"
SELECTIONS = "codearbiter.major-test-selections/1"
MAX_JSON = 16 * 1024 * 1024
MAX_TESTS = 32768


def require(value, reason):
    if not value:
        raise ValueError(reason)


def unique(pairs):
    result = {}
    for key, value in pairs:
        require(key not in result, "duplicate JSON field")
        result[key] = value
    return result


def load_json(path):
    path = Path(path)
    info = path.lstat()
    require(stat.S_ISREG(info.st_mode) and not path.is_symlink()
            and not getattr(info, "st_file_attributes", 0) & stat.FILE_ATTRIBUTE_REPARSE_POINT
            and info.st_size <= MAX_JSON, "observation must be a bounded regular file")
    raw = path.read_bytes()
    require(len(raw) <= MAX_JSON, "observation exceeds bound")
    return json.loads(raw, object_pairs_hook=unique)


def new_output(path, document):
    # A partial JSON file cannot be admitted by any reader. Never overwrite a
    # retained outcome after uncertain publication or a retry.
    with Path(path).open("x", encoding="utf-8") as stream:
        json.dump(document, stream, indent=2, ensure_ascii=False)
        stream.write("\n")


def git(repo, *args, raw=False, input=None):
    env = local_read_git_env()
    result = subprocess.run(["git", "--no-replace-objects", "--no-lazy-fetch", "-C", str(repo), *args],
                            env=env, input=input, capture_output=True, timeout=30, check=True)
    return result.stdout if raw else result.stdout.decode("utf-8").strip()


def ordinary_native_read_lock(repo):
    """Recognize only the empty untracked lock created by the native read owner.

    Do not ignore the store namespace: journals, arbitrary additions, tracked
    changes and linked/nonempty lock objects must still invalidate source.
    """
    path = Path(repo)
    try:
        for component in (".codearbiter", ".artifacts", "store.lock"):
            path = path / component
            info = path.lstat()
            if path.is_symlink() or getattr(info, "st_file_attributes", 0) & stat.FILE_ATTRIBUTE_REPARSE_POINT:
                return False
            if component != "store.lock":
                if not stat.S_ISDIR(info.st_mode):
                    return False
            elif not stat.S_ISREG(info.st_mode) or info.st_size != 0 or info.st_nlink != 1:
                return False
        return True
    except OSError:
        return False


def source_identity(repo):
    status = git(repo, "status", "--porcelain=v1", "--untracked-files=all", "-z")
    clean = all(not entry or (entry == "?? .codearbiter/.artifacts/store.lock" and ordinary_native_read_lock(repo))
                for entry in status.split("\0"))
    return {"source_commit": git(repo, "rev-parse", "HEAD"),
            "source_tree": git(repo, "rev-parse", "HEAD^{tree}"),
            "clean": clean}


SOURCE_PATHS = frozenset(('.codearbiter/reports/agent-lane-proof.json',
 '.github/scripts/_boundedproc.py',
 '.github/scripts/_contextverificationlib.py',
 '.github/scripts/_immutable_git_blobs.py',
 '.github/scripts/check_skill_proof_fresh.py',
 '.github/scripts/ci20_native_binding.py',
 '.github/scripts/major_qualification_report.py',
 '.github/scripts/major_readiness.py',
 '.github/scripts/test_check_skill_proof_fresh.py',
 '.github/scripts/test_generated_output.py',
 'core/artifact-release-manifest.json',
 'core/hosts.json',
 'core/pysrc/_artifactmanifestlib.py',
 'core/pysrc/_gitexec.py',
 'core/surface/COMMANDS.md',
 'core/surface/README.md',
 'core/surface/SPRINT.md',
 'core/surface/agents/INDEX.md',
 'core/surface/agents/architecture-drift-reviewer.md',
 'core/surface/agents/auth-crypto-reviewer.md',
 'core/surface/agents/authority-reviewer.md',
 'core/surface/agents/backend-author.md',
 'core/surface/agents/checkpoint-aggregator.md',
 'core/surface/agents/coverage-auditor.md',
 'core/surface/agents/decision-challenger.md',
 'core/surface/agents/dependency-reviewer.md',
 'core/surface/agents/design-quality-reviewer.md',
 'core/surface/agents/finding-triage.md',
 'core/surface/agents/frontend-author.md',
 'core/surface/agents/grader.md',
 'core/surface/agents/infra-author.md',
 'core/surface/agents/map-deps.md',
 'core/surface/agents/map-structure.md',
 'core/surface/agents/migration-reviewer.md',
 'core/surface/agents/scout.md',
 'core/surface/agents/security-reviewer.md',
 'core/surface/agents/tribunal-lens-reviewer.md',
 'core/surface/agents/verdict-aggregator.md',
 'core/surface/arbiter.md',
 'core/surface/command-routes.json',
 'core/surface/commands/add-dep.md',
 'core/surface/commands/adr-status.md',
 'core/surface/commands/adr.md',
 'core/surface/commands/audit.md',
 'core/surface/commands/checkpoint.md',
 'core/surface/commands/chore.md',
 'core/surface/commands/cleanup.md',
 'core/surface/commands/commit.md',
 'core/surface/commands/conflict.md',
 'core/surface/commands/context-check.md',
 'core/surface/commands/create-context.md',
 'core/surface/commands/debug.md',
 'core/surface/commands/decompose.md',
 'core/surface/commands/doctor.md',
 'core/surface/commands/feature.md',
 'core/surface/commands/fix.md',
 'core/surface/commands/init.md',
 'core/surface/commands/override.md',
 'core/surface/commands/pr.md',
 'core/surface/commands/prune.md',
 'core/surface/commands/reconcile.md',
 'core/surface/commands/refactor.md',
 'core/surface/commands/release.md',
 'core/surface/commands/review.md',
 'core/surface/commands/spike.md',
 'core/surface/commands/sprint.md',
 'core/surface/commands/standup.md',
 'core/surface/commands/status.md',
 'core/surface/commands/statusline.md',
 'core/surface/commands/task.md',
 'core/surface/commands/threat-model.md',
 'core/surface/commands/tribunal.md',
 'core/surface/commands/watch.md',
 'core/surface/includes/anti-slop-design/INDEX.md',
 'core/surface/includes/anti-slop-design/color.md',
 'core/surface/includes/anti-slop-design/core.md',
 'core/surface/includes/anti-slop-design/images.md',
 'core/surface/includes/anti-slop-design/layout.md',
 'core/surface/includes/anti-slop-design/medium-cli.md',
 'core/surface/includes/anti-slop-design/medium-dataviz.md',
 'core/surface/includes/anti-slop-design/medium-diagram.md',
 'core/surface/includes/anti-slop-design/medium-documents.md',
 'core/surface/includes/anti-slop-design/medium-slides.md',
 'core/surface/includes/anti-slop-design/medium-web.md',
 'core/surface/includes/anti-slop-design/typography.md',
 'core/surface/includes/artifacts-attestation.md',
 'core/surface/includes/artifacts.md',
 'core/surface/includes/author-tdd-workflow.md',
 'core/surface/includes/codex-host-notes.md',
 'core/surface/includes/command-compatibility.md',
 'core/surface/includes/compaction-charter.md',
 'core/surface/includes/cut-docs.md',
 'core/surface/includes/dangerous-mode.md',
 'core/surface/includes/farm.md',
 'core/surface/includes/fresh-verification.md',
 'core/surface/includes/harvest.md',
 'core/surface/includes/helper-invocation.md',
 'core/surface/includes/knowledge.md',
 'core/surface/includes/maturity-coverage.md',
 'core/surface/includes/ops-mode.md',
 'core/surface/includes/pi-host-notes.md',
 'core/surface/includes/redirect.md',
 'core/surface/includes/reference-map.md',
 'core/surface/includes/review-matrix.md',
 'core/surface/includes/reviewer-contract.md',
 'core/surface/includes/routing-table.md',
 'core/surface/includes/safety-core.md',
 'core/surface/includes/security-gate-record.md',
 'core/surface/includes/smarts/core.md',
 'core/surface/includes/smarts/decision-log-format.md',
 'core/surface/includes/smarts/lenses.md',
 'core/surface/includes/sprint-authority.md',
 'core/surface/includes/verification-boundary.md',
 'core/surface/skills/INDEX.md',
 'core/surface/skills/brainstorming/SKILL.md',
 'core/surface/skills/commit-gate/SKILL.md',
 'core/surface/skills/context-check/SKILL.md',
 'core/surface/skills/context-creation/SKILL.md',
 'core/surface/skills/context-creation/references/markdown-format.md',
 'core/surface/skills/crypto-compliance/SKILL.md',
 'core/surface/skills/debug/SKILL.md',
 'core/surface/skills/debug/references/debug-handoff.schema.json',
 'core/surface/skills/debug/references/handoff.md',
 'core/surface/skills/debug/references/minimal-unresolved.json',
 'core/surface/skills/debug/references/preparation.md',
 'core/surface/skills/decision-lifecycle/SKILL.md',
 'core/surface/skills/decision-lifecycle/references/adr-template.md',
 'core/surface/skills/decision-lifecycle/references/authoring.md',
 'core/surface/skills/decision-variance/SKILL.md',
 'core/surface/skills/decision-variance/references/analysis.md',
 'core/surface/skills/decompose/SKILL.md',
 'core/surface/skills/decompose/references/markdown-format.md',
 'core/surface/skills/dispatching-parallel-agents/SKILL.md',
 'core/surface/skills/executing-plans/SKILL.md',
 'core/surface/skills/finishing-a-development-branch/SKILL.md',
 'core/surface/skills/post-merge-cleanup/SKILL.md',
 'core/surface/skills/refactor/SKILL.md',
 'core/surface/skills/release/SKILL.md',
 'core/surface/skills/secret-handling/SKILL.md',
 'core/surface/skills/security-architecture/SKILL.md',
 'core/surface/skills/subagent-driven-development/SKILL.md',
 'core/surface/skills/subagent-driven-development/references/farm-dispatch.md',
 'core/surface/skills/tdd/SKILL.md',
 'core/surface/skills/tribunal/SKILL.md',
 'core/surface/skills/tribunal/references/ai-markers.md',
 'core/surface/skills/tribunal/references/cost-and-models.md',
 'core/surface/skills/tribunal/references/finding-record.md',
 'core/surface/skills/tribunal/references/issue-filing.md',
 'core/surface/skills/tribunal/references/lenses/appsec.md',
 'core/surface/skills/tribunal/references/lenses/architecture.md',
 'core/surface/skills/tribunal/references/lenses/change-closure.md',
 'core/surface/skills/tribunal/references/lenses/coverage.md',
 'core/surface/skills/tribunal/references/lenses/infra.md',
 'core/surface/skills/tribunal/references/lenses/migration.md',
 'core/surface/skills/tribunal/references/lenses/observability.md',
 'core/surface/skills/tribunal/references/lenses/performance.md',
 'core/surface/skills/tribunal/references/lenses/reliability.md',
 'core/surface/skills/tribunal/references/lenses/secrets-supply.md',
 'core/surface/skills/tribunal/references/lenses/semantic-contract.md',
 'core/surface/skills/tribunal/references/lenses/test-fidelity.md',
 'core/surface/skills/tribunal/references/lenses/typesafety.md',
 'core/surface/skills/tribunal/references/report.md',
 'core/surface/skills/tribunal/references/review-risk.md',
 'core/surface/skills/tribunal/references/schemas.md',
 'core/surface/skills/tribunal/references/telemetry.md',
 'core/surface/skills/tribunal/references/triage.md',
 'core/surface/skills/tribunal/references/verification-quality.md',
 'core/surface/skills/using-git-worktrees/SKILL.md',
 'core/surface/skills/writing-plans/SKILL.md',
 'core/surface/skills/writing-plans/references/farm-plan.md',
 'plugins/ca/skills/release/SKILL.md',
 'tools/build-artifact-manifest-contract.py',
 'tools/build-surface.py',
 'tools/command_compatibility.py',
 'tools/host_descriptors.py',
 'tools/owned_output.py'))

SOURCE_PROFILE = "hooks-proof-publisher-v1"
SOURCE_MANIFEST = "source-test-inputs.json"
SOURCE_FORMAT = "codearbiter.source-test-input-payload/1"
SOURCE_BINDING = "codearbiter.source-test-input-binding/1"
SOURCE_PAYLOAD = readiness.SOURCE_INPUT_PAYLOAD
SOURCE_JOB = "[CHECK] | [CORE] | Hook contract  <os: windows-latest · partition: contracts>"
SOURCE_UPLOAD = readiness.SOURCE_INPUT_UPLOAD


def _source_file(repo, relative):
    require(relative in SOURCE_PATHS, "source payload path outside fixed profile")
    path = Path(repo)
    for component in PurePosixPath(relative).parts:
        path = path / component
        info = path.lstat()
        require(not path.is_symlink() and not getattr(info, "st_file_attributes", 0) & stat.FILE_ATTRIBUTE_REPARSE_POINT,
                "source payload link/reparse input")
        if path != Path(repo) / relative:
            require(stat.S_ISDIR(info.st_mode), "source payload ancestor is not a directory")
    require(stat.S_ISREG(info.st_mode) and info.st_nlink == 1 and info.st_size <= 8 * 1024 * 1024,
            "source payload input is not bounded regular data")
    descriptor = os.open(path, os.O_RDONLY | getattr(os, "O_BINARY", 0) | getattr(os, "O_NOFOLLOW", 0))
    with os.fdopen(descriptor, "rb") as stream:
        opened = os.fstat(stream.fileno())
        require((opened.st_dev, opened.st_ino) == (info.st_dev, info.st_ino)
                and stat.S_ISREG(opened.st_mode), "source payload input changed before read")
        value = stream.read(8 * 1024 * 1024 + 1)
        after = os.fstat(stream.fileno())
    require(len(value) <= 8 * 1024 * 1024 and (opened.st_size, opened.st_mtime_ns) == (after.st_size, after.st_mtime_ns),
            "source payload input changed during read")
    return value


def _source_root_members(repo):
    found, pending, directories = set(), [Path(repo) / "core/surface"], 0
    while pending:
        folder = pending.pop(); directories += 1
        info = folder.lstat()
        require(directories <= 512 and stat.S_ISDIR(info.st_mode) and not folder.is_symlink()
                and not getattr(info, "st_file_attributes", 0) & stat.FILE_ATTRIBUTE_REPARSE_POINT,
                "source payload root is unsafe or unbounded")
        for path in folder.iterdir():
            info = path.lstat()
            require(not path.is_symlink() and not getattr(info, "st_file_attributes", 0) & stat.FILE_ATTRIBUTE_REPARSE_POINT,
                    "source payload membership contains a link")
            if stat.S_ISDIR(info.st_mode): pending.append(path)
            else:
                require(stat.S_ISREG(info.st_mode), "source payload membership is not regular")
                found.add(path.relative_to(repo).as_posix())
                require(len(found) <= 2048, "source payload membership exceeds bound")
    require(found == {p for p in SOURCE_PATHS if p.startswith("core/surface/")},
            "source payload physical membership differs")


def source_input_snapshot(repo):
    repo = Path(repo).resolve(strict=True)
    identity = source_identity(repo)
    require(identity["clean"], "source payload checkout is not clean")
    _source_root_members(repo)
    rows = git(repo, "ls-tree", "-rz", "--full-tree", identity["source_commit"], "--", *sorted(SOURCE_PATHS), raw=True)
    entries = []
    for row in rows.split(b"\0"):
        if not row: continue
        header, relative = row.split(b"\t", 1)
        mode, kind, blob = header.decode("ascii").split()
        relative = relative.decode("utf-8")
        require(relative in SOURCE_PATHS and kind == "blob" and mode in ("100644", "100755")
                and readiness.SHA.fullmatch(blob), "source payload immutable member invalid")
        entries.append((relative, mode, blob))
    require(len(entries) == len(SOURCE_PATHS) and len({p for p, _, _ in entries}) == len(SOURCE_PATHS),
            "source payload immutable membership differs")
    batch = git(repo, "cat-file", "--batch", raw=True,
                input="".join(blob + "\n" for _, _, blob in entries).encode("ascii"))
    require(len(batch) <= 64 * 1024 * 1024, "source payload byte bound exceeded")
    cursor, members, total = 0, [], 0
    for relative, mode, expected in entries:
        end = batch.index(b"\n", cursor)
        blob, kind, size = batch[cursor:end].decode("ascii").split()
        size = int(size); cursor = end + 1
        require(blob == expected and kind == "blob" and 0 <= size <= 8 * 1024 * 1024, "source payload blob invalid")
        value = batch[cursor:cursor + size]; cursor += size
        require(batch[cursor:cursor + 1] == b"\n", "source payload blob truncated"); cursor += 1
        require(_source_file(repo, relative) == value, "source payload physical bytes differ from Git")
        total += size
        require(total <= 64 * 1024 * 1024, "source payload total exceeds bound")
        members.append({"path": relative, "sha256": readiness.digest(value), "bytes": size, "git_mode": mode})
    require(cursor == len(batch), "source payload has trailing blob data")
    return {**identity, "members": sorted(members, key=lambda item: item["path"])}


def validate_source_manifest(record, req, job_name, members):
    fields = {"format", "profile", "source_commit", "source_tree", "workflow", "ci_run_id", "producer_job_name", "members"}
    require(isinstance(record, dict) and set(record) == fields and record["format"] == SOURCE_FORMAT
            and record["profile"] == SOURCE_PROFILE and record["workflow"] == ".github/workflows/ci.yml"
            and job_name == record["producer_job_name"] == SOURCE_JOB
            and type(record["source_commit"]) is str and record["source_commit"] == req["source_commit"] and readiness.SHA.fullmatch(record["source_commit"])
            and type(record["source_tree"]) is str and record["source_tree"] == req["source_tree"] and readiness.SHA.fullmatch(record["source_tree"])
            and type(record["ci_run_id"]) is int and record["ci_run_id"] == req["ci_run_id"] > 0,
            "source payload manifest identity differs")
    rows = record["members"]
    require(isinstance(rows, list) and len(rows) == len(SOURCE_PATHS), "source payload manifest population differs")
    require(all(isinstance(row, dict) and set(row) == {"path", "sha256", "bytes", "git_mode"}
                and type(row["path"]) is str and row["path"] in SOURCE_PATHS
                and type(row["sha256"]) is str and readiness.DIGEST.fullmatch(row["sha256"])
                and type(row["bytes"]) is int and 0 <= row["bytes"] <= 8 * 1024 * 1024
                and row["git_mode"] in ("100644", "100755") for row in rows), "source payload manifest member invalid")
    require([row["path"] for row in rows] == sorted(SOURCE_PATHS)
            and sum(row["bytes"] for row in rows) <= 64 * 1024 * 1024, "source payload manifest membership differs")
    expected = {row["path"]: row["sha256"] for row in rows}
    actual = {row["path"]: row["sha256"] for row in members}
    require(len(actual) == len(members) and set(actual) == SOURCE_PATHS | {SOURCE_MANIFEST}
            and all(actual[path] == value for path, value in expected.items()), "source payload archive membership differs")
    return record


def prepare_source_payload(repo, output, job_name):
    require(job_name == SOURCE_JOB, "source payload owner differs")
    repo = Path(repo).resolve(strict=True); output = Path(output).absolute()
    output = output.parent.resolve(strict=True) / output.name
    require(not output.exists() and not output.is_symlink() and not output.is_relative_to(repo),
            "new external source payload directory required")
    before = source_input_snapshot(repo)
    output.mkdir()
    for row in before["members"]:
        value = _source_file(repo, row["path"])
        require(readiness.digest(value) == row["sha256"], "source payload changed before staging")
        target = output / row["path"]; target.parent.mkdir(parents=True, exist_ok=True)
        with target.open("xb") as stream: stream.write(value)
    record = {"format": SOURCE_FORMAT, "profile": SOURCE_PROFILE,
        "source_commit": before["source_commit"], "source_tree": before["source_tree"],
        "workflow": ".github/workflows/ci.yml", "ci_run_id": int(os.environ.get("GITHUB_RUN_ID", "0")),
        "producer_job_name": job_name, "members": before["members"]}
    require(record["ci_run_id"] > 0 and source_input_snapshot(repo) == before, "source payload staging source changed")
    new_output(output / SOURCE_MANIFEST, record)
    return record


def source_observation_binding(repo, staged, identity):
    staged = Path(staged)
    info = staged.lstat()
    require(stat.S_ISDIR(info.st_mode) and not staged.is_symlink()
            and not getattr(info, "st_file_attributes", 0) & stat.FILE_ATTRIBUTE_REPARSE_POINT,
            "source payload stage is not an ordinary directory")
    staged = staged.resolve(strict=True)
    require(not staged.is_relative_to(Path(repo).resolve()), "source payload must be outside source")
    record = load_json(staged / SOURCE_MANIFEST)
    snapshot = source_input_snapshot(repo)
    require(all(snapshot[key] == identity[key] for key in ("source_commit", "source_tree", "clean")),
            "source payload observation source changed")
    members = [{"path": row["path"], "sha256": row["sha256"]} for row in snapshot["members"]]
    raw = (staged / SOURCE_MANIFEST).read_bytes()
    require(len(raw) <= 1024 * 1024, "source payload manifest exceeds bound")
    members.append({"path": SOURCE_MANIFEST, "sha256": readiness.digest(raw)})
    validate_source_manifest(record, {**identity, "ci_run_id": int(os.environ.get("GITHUB_RUN_ID", "0"))}, SOURCE_JOB, members)
    require(record["members"] == snapshot["members"], "source payload observation members changed")
    actual, pending = set(), [staged]
    permitted = SOURCE_PATHS | {SOURCE_MANIFEST}
    parents = {parent.as_posix() for name in permitted for parent in PurePosixPath(name).parents if parent.as_posix() != "."}
    while pending:
        folder = pending.pop()
        for path in folder.iterdir():
            info = path.lstat(); name = path.relative_to(staged).as_posix()
            require(not path.is_symlink() and not getattr(info, "st_file_attributes", 0) & stat.FILE_ATTRIBUTE_REPARSE_POINT,
                    "source payload stage contains a link")
            if stat.S_ISDIR(info.st_mode):
                require(name in parents, "source payload stage has a foreign directory")
                pending.append(path)
            else:
                require(stat.S_ISREG(info.st_mode) and name in permitted, "source payload stage has a foreign member")
                actual.add(name)
    require(actual == SOURCE_PATHS | {SOURCE_MANIFEST}, "source payload stage contains extra/missing files")
    for row in record["members"]:
        require(readiness.digest(_source_file(staged, row["path"])) == row["sha256"], "source payload staged bytes differ")
    return {"format": SOURCE_BINDING, "profile": SOURCE_PROFILE,
            "payload_name": SOURCE_PAYLOAD, "manifest_sha256": readiness.digest(raw)}


def admit_source_observation(observed, payload, req, job_name, job_id):
    binding = observed.get("source_input_binding")
    require(isinstance(binding, dict) and set(binding) == {"format", "profile", "payload_name", "manifest_sha256"}
            and binding["format"] == SOURCE_BINDING and binding["profile"] == SOURCE_PROFILE
            and binding["payload_name"] == SOURCE_PAYLOAD
            and binding["manifest_sha256"] == payload.get("source_manifest_sha256")
            and type(payload.get("source_upload_job_id")) is int and payload.get("source_upload_job_id") == job_id,
            "source test payload binding missing or differs")
    record = payload.get("documents", {}).get(SOURCE_MANIFEST)
    validate_source_manifest(record, req, job_name, payload.get("members", []))
    require(next(row["sha256"] for row in payload["members"] if row["path"] == SOURCE_MANIFEST)
            == binding["manifest_sha256"], "source test manifest digest differs")


def observe_python(repo, script, arguments, output, source_payload=None):
    """Run the original Python entry point once, observing actual TestResult calls."""
    repo = Path(repo).resolve(strict=True)
    script = (repo / script).resolve(strict=True)
    relative = script.relative_to(repo).as_posix()
    require(script.suffix == ".py" and not Path(output).exists() and not Path(output).is_symlink(),
            "new Python observation required")
    before = source_identity(repo)
    source_binding = source_observation_binding(repo, source_payload, before) if source_payload else None
    rows, active = [], {}
    original_argv, original_path = sys.argv[:], sys.path[:]
    original_cwd = Path.cwd()

    def start(original):
        def wrapped(result, test):
            test_id = test.id()
            require(isinstance(test_id, str) and 0 < len(test_id.encode("utf-8")) <= 2048
                    and len(rows) < MAX_TESTS, "Python named observation exceeds bound")
            row = {"id": "python:" + relative + ":" + test_id, "result": "unknown"}
            rows.append(row)
            active[id(test)] = row
            return original(result, test)
        return wrapped

    def outcome(original, name):
        def wrapped(result, test, *args, **kwargs):
            if id(test) in active:
                active[id(test)]["result"] = name
            return original(result, test, *args, **kwargs)
        return wrapped

    def subtest(original):
        def wrapped(result, test, sub, error):
            if error is not None and id(test) in active:
                active[id(test)]["result"] = "failed"
            return original(result, test, sub, error)
        return wrapped

    code = 0
    try:
        os.chdir(repo)
        sys.argv[:] = [str(script), *arguments]
        sys.path[0] = str(script.parent)
        with ExitStack() as stack:
            stack.enter_context(mock.patch.object(unittest.TestResult, "startTest", start(unittest.TestResult.startTest)))
            for name, state in (("addSuccess", "passed"), ("addFailure", "failed"), ("addError", "failed"),
                                ("addSkip", "skipped"), ("addExpectedFailure", "expected-failure"),
                                ("addUnexpectedSuccess", "failed")):
                stack.enter_context(mock.patch.object(unittest.TestResult, name, outcome(getattr(unittest.TestResult, name), state)))
            stack.enter_context(mock.patch.object(unittest.TestResult, "addSubTest", subtest(unittest.TestResult.addSubTest)))
            try:
                runpy.run_path(str(script), run_name="__main__")
            except SystemExit as error:
                code = error.code if type(error.code) is int else 0 if error.code is None else 1
            except BaseException:
                traceback.print_exc()
                code = 1
    finally:
        sys.argv[:] = original_argv
        sys.path[:] = original_path
        os.chdir(original_cwd)
    after = source_identity(repo)
    stable = before == after and before["clean"]
    if source_payload:
        try:
            stable = stable and source_observation_binding(repo, source_payload, after) == source_binding
        except (OSError, ValueError, KeyError, TypeError, subprocess.SubprocessError):
            stable = False
    document = {"format": OBSERVATION, **before,
                       "source_stable": stable,
                       "ci_run_id": int(os.environ.get("GITHUB_RUN_ID", "0")),
                       "proof_kind": "source-test", "producer": "python-test-result-observer",
                       "argv": [sys.executable, str(script), *arguments],
                       "exit_code": code, "tests": rows}
    if source_binding is not None: document["source_input_binding"] = source_binding
    new_output(output, document)
    return code if not source_payload or stable else 1


def admit_go(record, binding, source_tree):
    """Join the original named run to its existing same-run native stamp."""
    require(record.get("format") == "codearbiter.go-test-observation/1"
            and binding.get("format") == "codearbiter.ci-native-candidate/1",
            "wrong native observation or stamp")
    require(set(binding) == native_binding_owner.RECORD_FIELDS
            and binding["producer_job"] == native_binding_owner.PRODUCER
            and binding["workflow"] == native_binding_owner.WORKFLOW
            and binding["toolchain"] == native_binding_owner.TOOLCHAIN
            and binding["platform"] in native_binding_owner.PLATFORMS
            and readiness.SHA.fullmatch(binding["source_commit"])
            and isinstance(binding["run_id"], str) and binding["run_id"].isdigit() and int(binding["run_id"]) > 0
            and all(readiness.DIGEST.fullmatch(binding[key]) for key in (
                "module_sha256", "go_sha256", "manifest_sha256", "binary_sha256")),
            "native stamp lacks the original producer/source/input binding")
    require(record.get("complete") is True
            and record.get("module_sha256_before") == record.get("module_sha256_after")
            == binding.get("module_sha256")
            and readiness.DIGEST.fullmatch(binding.get("module_sha256", "")),
            "native test inputs changed or run incomplete")
    selected = [(r["package"], r["test"]) for r in record["selected"]]
    observed = [(r["package"], r["test"]) for r in record["observed"]]
    require(selected and len(set(selected)) == len(selected) and sorted(selected) == sorted(observed)
            and len(set(observed)) == len(observed), "native named population differs")
    require(all(r.get("result") in ("pass", "skip") for r in record["observed"]), "native failure cannot qualify")
    return {"format": OBSERVATION, "source_commit": binding["source_commit"],
            "source_tree": source_tree, "source_stable": True, "ci_run_id": int(binding["run_id"]),
            "proof_kind": "native-module", "producer": "go-named-ci20-join",
            "native_binding": binding, "argv": record["argv"], "exit_code": 0,
            "tests": [{"id": "go:" + r["package"] + ":" + r["test"],
                       "result": "passed" if r["result"] == "pass" else "skipped"}
                      for r in record["observed"]]}


def admit_vitest(record, *, repo, before, after, argv, exit_code, run_id):
    require(isinstance(record, dict) and isinstance(record.get("testResults"), list)
            and len(record["testResults"]) <= MAX_TESTS, "Vitest named outcomes missing or exceed bound")
    rows, identities = [], set()
    repo = Path(repo).resolve()
    for suite in record["testResults"]:
        require(isinstance(suite, dict) and isinstance(suite.get("name"), str)
                and 0 < len(suite["name"].encode("utf-8")) <= 4096
                and isinstance(suite.get("assertionResults"), list), "malformed Vitest suite")
        try:
            path = Path(suite["name"]).resolve().relative_to(repo).as_posix()
        except (OSError, ValueError):
            raise ValueError("Vitest suite is outside source repository") from None
        for case in suite["assertionResults"]:
            require(isinstance(case, dict) and isinstance(case.get("fullName"), str)
                    and 0 < len(case["fullName"].encode("utf-8")) <= 2048
                    and isinstance(case.get("status"), str) and len(rows) < MAX_TESTS,
                    "malformed or unbounded Vitest named outcome")
            state = {"passed": "passed", "failed": "failed", "pending": "skipped",
                     "skipped": "skipped", "todo": "skipped", "disabled": "skipped"}.get(case["status"])
            require(state is not None, "unknown Vitest outcome")
            identity = "vitest:" + path + ":" + case["fullName"]
            require(identity not in identities, "duplicate Vitest named outcome")
            identities.add(identity)
            rows.append({"id": identity, "result": state})
    require(rows, "Vitest ran no named tests")
    return {"format": OBSERVATION, **before, "source_stable": before == after and before["clean"],
            "ci_run_id": run_id, "proof_kind": "source-test", "producer": "vitest-json-observer", "argv": argv,
            "exit_code": exit_code, "tests": rows}


def _vitest_cwd(repo, requested):
    path = Path(requested) if requested is not None else repo
    require(".." not in path.parts, "Vitest execution cwd must be an owned project directory")
    path = path if path.is_absolute() else repo / path
    try:
        relative = path.relative_to(repo)
        current = repo
        for component in (None, *relative.parts):
            if component is not None:
                current = current / component
            info = current.lstat()
            require(stat.S_ISDIR(info.st_mode) and not current.is_symlink()
                    and not getattr(info, "st_file_attributes", 0) & stat.FILE_ATTRIBUTE_REPARSE_POINT,
                    "Vitest execution cwd must not contain a link or reparse point")
        return path.resolve(strict=True)
    except (OSError, ValueError):
        raise ValueError("Vitest execution cwd must be an owned project directory") from None


def _vitest_new_path(value):
    path = Path(value).absolute()
    require(path.name not in ("", ".", "..") and ".." not in path.parts, "unsafe Vitest output path")
    parent = path.parent
    info = parent.lstat()
    require(stat.S_ISDIR(info.st_mode) and not parent.is_symlink()
            and not getattr(info, "st_file_attributes", 0) & stat.FILE_ATTRIBUTE_REPARSE_POINT,
            "Vitest output parent must be a regular directory")
    try:
        path.lstat()
    except FileNotFoundError:
        pass
    else:
        raise ValueError("new Vitest result and observation paths required")
    return parent.resolve(strict=True) / path.name, (info.st_dev, info.st_ino)


def _vitest_command(arguments, raw_results, cwd):
    require(isinstance(arguments, (list, tuple)) and arguments
            and all(isinstance(arg, str) and arg and "\0" not in arg for arg in arguments),
            "original Vitest argv required")
    reporters, outputs = [], {}
    index = 0
    while index < len(arguments):
        arg = arguments[index]
        option, separator, value = arg.partition("=")
        if option in ("--reporter", "--reporters") or option == "--outputFile" or option.startswith("--outputFile."):
            if not separator:
                index += 1
                require(index < len(arguments) and not arguments[index].startswith("--"), "Vitest option value missing")
                value = arguments[index]
            require(value and "\0" not in value, "Vitest option value missing")
            if option in ("--reporter", "--reporters"):
                reporters.append(value)
            else:
                key = option.removeprefix("--outputFile")
                require(key not in outputs, "duplicate Vitest output ownership")
                outputs[key] = value
        elif option.startswith(("--reporter", "--outputFile")):
            raise ValueError("unsupported Vitest reporter/output option")
        index += 1
    require(reporters.count("json") <= 1, "duplicate JSON reporter ownership")
    require(not ("" in outputs and len(outputs) > 1), "ambiguous generic/per-reporter output ownership")
    if "" in outputs:
        require(reporters.count("json") == 1 and not any(r not in ("json", "default", "verbose", "dot", "github-actions") for r in reporters),
                "generic output cannot ambiguously select JSON")
    selected = outputs.get(".json", outputs.get(""))
    if selected is not None:
        path = Path(selected)
        path = path if path.is_absolute() else cwd / path
        require(not path.exists() and not path.is_symlink(), "original JSON output is stale or linked")
        require(path.resolve(strict=False) == raw_results, "original JSON output differs from owned result path")
    for key, value in outputs.items():
        if key in ("", ".json"):
            continue
        other = Path(value)
        other = other if other.is_absolute() else cwd / other
        require(other.resolve(strict=False) != raw_results, "another reporter shares JSON output")
    command = list(arguments)
    if "json" not in reporters:
        command.append("--reporter=json")
    if selected is None:
        # Keep the original simple wrapper's generic output argument compatible.
        key = "--outputFile=" if not reporters and not outputs else "--outputFile.json="
        command.append(key + str(raw_results))
    return command


def _vitest_owned_json(path, descriptor, original):
    info, opened = path.lstat(), os.fstat(descriptor)
    for item in (info, opened):
        require(stat.S_ISREG(item.st_mode) and item.st_nlink == 1
                and not getattr(item, "st_file_attributes", 0) & stat.FILE_ATTRIBUTE_REPARSE_POINT
                and (item.st_dev, item.st_ino) == (original.st_dev, original.st_ino)
                and item.st_size <= MAX_JSON, "Vitest result was replaced, linked or exceeds bound")
    os.lseek(descriptor, 0, os.SEEK_SET)
    raw = bytearray()
    while len(raw) <= MAX_JSON:
        chunk = os.read(descriptor, min(1024 * 1024, MAX_JSON + 1 - len(raw)))
        if not chunk:
            break
        raw.extend(chunk)
    final, current = os.fstat(descriptor), path.lstat()
    require(len(raw) <= MAX_JSON and len(raw) == info.st_size
            and all((value.st_dev, value.st_ino, value.st_size, value.st_mtime_ns, value.st_nlink)
                    == (info.st_dev, info.st_ino, info.st_size, info.st_mtime_ns, 1)
                    for value in (final, current)), "Vitest result changed while read")
    return json.loads(raw, object_pairs_hook=unique), hashlib.sha256(raw).hexdigest()


def observe_vitest(repo, arguments, raw_results, output, execution_cwd=None):
    """Observe one original invocation, preserving its reporters and project cwd."""
    require(arguments and raw_results and output, "Vitest invocation and new outputs required")
    repo = Path(repo).resolve(strict=True)
    cwd = _vitest_cwd(repo, execution_cwd)
    raw_results, raw_parent = _vitest_new_path(raw_results)
    output, observation_parent = _vitest_new_path(output)
    require(raw_results != output, "result and observation output ownership conflict")
    command = _vitest_command(arguments, raw_results, cwd)
    before = source_identity(repo)
    descriptor = os.open(raw_results, os.O_RDWR | os.O_CREAT | os.O_EXCL | getattr(os, "O_BINARY", 0)
                         | getattr(os, "O_NOFOLLOW", 0), 0o600)
    try:
        original = os.fstat(descriptor)
        process = start_process(command, cwd=cwd)
        try:
            code = process.wait(timeout=1200)
        except subprocess.TimeoutExpired:
            containment = terminate_tree(process)
            raise ValueError("original Vitest run timed out; containment=" + containment) from None
        after = source_identity(repo)
        require(all((path.parent.stat().st_dev, path.parent.stat().st_ino) == expected
                    for path, expected in ((raw_results, raw_parent), (output, observation_parent))),
                "Vitest output parent changed")
        record, raw_digest = _vitest_owned_json(raw_results, descriptor, original)
        document = admit_vitest(record, repo=repo, before=before, after=after,
                                argv=command, exit_code=code, run_id=int(os.environ.get("GITHUB_RUN_ID", "0")))
        document.update(original_argv=list(arguments), cwd=str(cwd), raw_results_sha256=raw_digest)
        new_output(output, document)
        return code
    finally:
        os.close(descriptor)


def validate_selections(document):
    require(isinstance(document, dict) and document.get("schema") == SELECTIONS
            and set(document) == {"schema", "groups"} and isinstance(document["groups"], list)
            and len(document["groups"]) <= 512, "invalid semantic selection map")
    identities = set()
    for group in document["groups"]:
        require(isinstance(group, dict) and set(group) == {"id", "job", "payload_name", "observation", "proof_kind", "selectors", "cells", "scope"},
                "invalid semantic selection group")
        require(group["id"] not in identities and all(isinstance(group[k], str) and group[k]
                for k in ("id", "job", "payload_name", "observation", "proof_kind", "scope")), "invalid selection identity")
        identities.add(group["id"])
        for name in ("selectors", "cells"):
            values = group[name]
            require(isinstance(values, list) and 0 < len(values) <= 4096
                    and all(isinstance(v, str) and v and len(v.encode()) <= 2048 for v in values)
                    and len(set(values)) == len(values), "empty or ambiguous semantic population")
        require(group["proof_kind"] in ("source-test", "native-module", "retained-archive-cli", "live-host"), "unknown proof kind")
    return document["groups"]


def build_report(req, *, job_name, job_id, selections, observations, payloads,
                 producer_job=None, runtime_acquisitions=None):
    require(type(job_id) is int and job_id > 0, "positive actual job identity required")
    groups = validate_selections(selections)
    # One declared original-package role is source-bound; no general formatting
    # or caller-provided replacement expressions are accepted.
    require(isinstance(req["source_commit"], str) and readiness.SHA.fullmatch(req["source_commit"]), "exact report source required")
    resolved = []
    for group in groups:
        if group["payload_name"] == "artifact-release-packages-{source_commit}":
            group = dict(group, payload_name="artifact-release-packages-" + req["source_commit"])
        elif group["payload_name"] == "artifact-sandbox-plugin-{source_commit}-{run_attempt}":
            # Resolve only the selected owning job, using actual API job context.
            # An observation's attempt or arbitrary format string is never input.
            if group["job"] == job_name:
                require(isinstance(producer_job, dict)
                        and type(producer_job.get("id")) is int and producer_job["id"] == job_id
                        and producer_job.get("name") == job_name
                        and type(producer_job.get("run_id")) is int and producer_job["run_id"] == req["ci_run_id"]
                        and producer_job.get("status") == "in_progress"
                        and type(producer_job.get("run_attempt")) is int and 0 < producer_job["run_attempt"] <= 9999,
                        "actual original Sandbox job attempt required")
                group = dict(group, payload_name="artifact-sandbox-plugin-" + req["source_commit"]
                             + "-" + str(producer_job["run_attempt"]))
        resolved.append(group)
    groups = resolved
    expected = {cell for cell in req["cells"] if req["cell_jobs"][cell] == job_name}
    require(expected, "job has no required mapped cells")
    selected_groups = [g for g in groups if g["job"] == job_name and expected.intersection(g["cells"])]
    require({cell for g in selected_groups for cell in g["cells"]} == expected,
            "semantic cell mapping is missing, extra or assigned to another job")
    results, indices, retained_payloads = [], {}, {}
    installed_admissions, dual_payload_report = {}, False
    for cell in sorted(expected):
        evidence, selected, executed, payload_name, native_bindings = [], set(), set(), set(), []
        installed_payloads = {}
        for group in (g for g in selected_groups if cell in g["cells"]):
            observed = observations.get(group["observation"], {})
            require(observed.get("format") == OBSERVATION
                    and observed.get("source_commit") == req["source_commit"]
                    and observed.get("source_tree") == req["source_tree"]
                    and observed.get("ci_run_id") == req["ci_run_id"]
                    and observed.get("source_stable") is True
                    and observed.get("proof_kind") == group["proof_kind"]
                    and type(observed.get("exit_code")) is int and observed["exit_code"] == 0,
                    "original execution is absent, failed, stale or has a different proof kind")
            argv = observed.get("argv")
            require(isinstance(argv, list) and argv and all(isinstance(a, str) and a for a in argv), "original command missing")
            if cell.startswith("installed:"):
                require(group["proof_kind"] in ("native-module", "retained-archive-cli", "live-host"),
                        "source tests cannot qualify installed hosts")
                require(group["proof_kind"] != "native-module",
                        "native module tests cannot qualify an upstream host or installed native package")
            producers = {"source-test": ("python-test-result-observer", "vitest-json-observer"),
                         "native-module": ("go-named-ci20-join",)}
            if group["proof_kind"] in ("retained-archive-cli", "live-host"):
                if group["proof_kind"] == "retained-archive-cli":
                    from retained_archive_cli_observation import admit
                elif (observed.get("producer") == "pi-installed-rpc-observer-v1"
                      and isinstance(observed.get("installed_binding"), dict)
                      and observed["installed_binding"].get("profile") == "pi-installed-rpc-v1"):
                    from pi_live_report_profile import admit
                elif (observed.get("producer") == "sandbox-installed-docker-observer-v1"
                      and isinstance(observed.get("installed_binding"), dict)
                      and observed["installed_binding"].get("profile") == "sandbox-installed-docker-v1"):
                    from sandbox_live_report_profile import admit
                else:
                    from codex_live_report_profile import admit
                if group["observation"] not in installed_admissions:
                    extra = {}
                    if observed.get("producer") == "sandbox-installed-docker-observer-v1":
                        extra = {"producer_job": producer_job,
                                 "runtime_acquisition": (runtime_acquisitions or {}).get(group["observation"])}
                    elif (observed.get("producer") == "pi-installed-rpc-observer-v1"
                          and isinstance(observed.get("installed_binding"), dict)
                          and observed["installed_binding"].get("profile") == "pi-installed-rpc-v1"):
                        extra = {"runtime_acquisition": (runtime_acquisitions or {}).get(group["observation"])}
                    installed_admissions[group["observation"]] = admit(
                        observed, req=req, job_id=job_id, authenticated_payloads=payloads, repo=ROOT, **extra)
                require(installed_admissions[group["observation"]]["tests"] == observed.get("tests"),
                        "installed outcomes differ from closed observer admission")
                admitted = installed_admissions[group["observation"]]
                require(group["payload_name"] == admitted["primary_payload_name"], "cold primary payload differs")
                require(group["proof_kind"] != "live-host" or cell in admitted["installed_cells"],
                        "closed live profile cannot qualify this cell")
                require(not cell.startswith("installed:") or cell in admitted["installed_cells"],
                        "cold profile cannot qualify this upstream installed cell")
                require(cell != "task:PI-D07", "cold profile cannot qualify packaged Pi authorship")
                for item in admitted["payloads"]:
                    installed_payloads[item["artifact_id"]] = item
                dual_payload_report = True
            else:
                require(observed.get("producer") in producers.get(group["proof_kind"], ()),
                        "no qualified observer for this proof kind")
            if group["proof_kind"] == "source-test":
                require(group["payload_name"] == SOURCE_PAYLOAD, "source test payload binding role differs")
                admit_source_observation(observed, payloads.get(SOURCE_PAYLOAD, {}), req, job_name, job_id)
            if group["proof_kind"] == "native-module":
                native_bindings.append(observed.get("native_binding"))
            key = group["observation"]
            if key not in indices:
                tests = observed.get("tests")
                require(isinstance(tests, list) and len(tests) <= MAX_TESTS
                        and all(isinstance(test, dict) and set(test) == {"id", "result"}
                                and isinstance(test["id"], str) and test["id"]
                                and len(test["id"].encode("utf-8")) <= 4096 for test in tests),
                        "invalid or unbounded original named outcomes")
                indices[key] = {}
                for test in tests:
                    indices[key].setdefault(test["id"], []).append(test)
            for selector in group["selectors"]:
                matches = indices[key].get(selector, [])
                require(len(matches) == 1 and matches[0].get("result") == "passed",
                        "selected named test missing, repeated, skipped or failed: " + selector)
                selected.add((group["observation"], selector))
                executed.add((group["observation"], selector))
            evidence.append({"argv": argv, "exit_code": 0})
            payload_name.add(group["payload_name"])
        require(len(payload_name) == 1, "one cell requires incompatible payload bindings")
        payload = payloads.get(payload_name.pop(), {})
        require(type(payload.get("artifact_id")) is int and payload["artifact_id"] > 0
                and readiness.DIGEST.fullmatch(payload.get("archive_sha256", ""))
                and payload.get("members"), "authenticated consumed payload missing")
        require(all(binding is not None and binding in payload.get("native_bindings", [])
                    for binding in native_bindings), "native tests do not bind the actual consumed payload")
        retained = {"artifact_id": payload["artifact_id"], "archive_sha256": payload["archive_sha256"],
                    "members": payload["members"]}
        identity = retained["artifact_id"]
        require(identity not in retained_payloads or retained_payloads[identity] == retained,
                "one payload artifact has conflicting consumed bytes")
        retained_payloads[identity] = retained
        for extra_id, extra in installed_payloads.items():
            require(extra_id not in retained_payloads or retained_payloads[extra_id] == extra,
                    "one payload artifact has conflicting consumed bytes")
            retained_payloads[extra_id] = extra
        result = {"cell": cell, "result": "PASSED", "commands": evidence,
                  "selected_population": len(selected), "executed_population": len(executed)}
        if installed_payloads:
            require(identity in installed_payloads and 1 <= len(installed_payloads) <= 2,
                    "installed report requires one or two distinct original payloads")
            result["payload_artifact_ids"] = sorted(installed_payloads)
        else:
            result["payload_artifact_id"] = identity
        results.append(result)
    if dual_payload_report:
        for result in results:
            if "payload_artifact_id" in result:
                result["payload_artifact_ids"] = [result.pop("payload_artifact_id")]
    return {"schema": "codearbiter-major-qualification/3" if dual_payload_report else "codearbiter-major-qualification/2", "source_commit": req["source_commit"],
            "source_tree": req["source_tree"], "ci_run_id": req["ci_run_id"],
            "job_id": job_id, "results": results,
            "payloads": [retained_payloads[i] for i in sorted(retained_payloads)]}


def authenticated_payload(metadata, req, consumed_root, source_job=None):
    archive = readiness.artifact_bytes(metadata, req)
    members = readiness.members(archive)
    root = Path(consumed_root).resolve(strict=True)
    native_bindings, documents = [], {}
    source_manifest_sha256 = None
    if any(member["path"] == SOURCE_MANIFEST for member in members):
        require(isinstance(source_job, dict) and type(source_job.get("id")) is int
                and source_job["id"] > 0 and source_job.get("name") == SOURCE_JOB
                and source_job.get("status") == "in_progress" and source_job.get("conclusion") is None,
                "source payload original uploader job missing")
        # The owning job is still running, so its completed job log does not
        # exist yet. Bind producer-time identity to its completed upload step;
        # final readiness authenticates both uploader logs independently.
        upload_steps = [step for step in source_job.get("steps", []) if step.get("name") == SOURCE_UPLOAD]
        require(metadata.get("name") == SOURCE_PAYLOAD and len(upload_steps) == 1
                and upload_steps[0].get("status") == "completed"
                and upload_steps[0].get("conclusion") == "success", "source payload upload step did not complete")
        with zipfile.ZipFile(io.BytesIO(archive)) as source_archive:
            require(source_archive.getinfo(SOURCE_MANIFEST).file_size <= 1024 * 1024,
                    "source payload manifest exceeds bound")
            raw = source_archive.read(SOURCE_MANIFEST)
        manifest = json.loads(raw, object_pairs_hook=unique)
        validate_source_manifest(manifest, req, source_job["name"], members)
        snapshot = source_input_snapshot(root)
        require(snapshot["source_commit"] == req["source_commit"] and snapshot["source_tree"] == req["source_tree"]
                and snapshot["members"] == manifest["members"], "source payload actual consumed source differs")
        documents[SOURCE_MANIFEST] = manifest
        source_manifest_sha256 = readiness.digest(raw)
    for member in members:
        if member["path"] == SOURCE_MANIFEST:
            continue  # Validated archive metadata, never claimed as executed input.

        path = root
        for part in PurePosixPath(member["path"]).parts:
            path = path / part
            info = path.lstat()
            require(not path.is_symlink() and not getattr(info, "st_file_attributes", 0) & stat.FILE_ATTRIBUTE_REPARSE_POINT,
                    "consumed payload contains a link or reparse point")
        require(path.is_file() and path.stat().st_size <= 64 * 1024 * 1024,
                "executed payload member is not a bounded regular file")
        content = path.read_bytes()
        require(len(content) <= 64 * 1024 * 1024
                and hashlib.sha256(content).hexdigest() == member["sha256"],
                "executed payload differs from authenticated archive")
        if member["path"] == "artifact-package-cohort.json":
            require(len(content) <= 8 * 1024 * 1024, "cohort document exceeds bound")
            documents[member["path"]] = content
        if path.name == "ci20-native-tested.json":
            binding = load_json(path)
            require(binding.get("format") == native_binding_owner.FORMAT,
                    "consumed native stamp has the wrong format")
            native_bindings.append(binding)
    result = {"artifact_id": metadata["id"], "archive_sha256": readiness.digest(archive),
            "members": members, "native_bindings": native_bindings, "documents": documents}
    if source_manifest_sha256 is not None:
        result.update(source_manifest_sha256=source_manifest_sha256, source_upload_job_id=source_job["id"])
    return result


def validate_emitter_environment():
    require(os.environ.get("GITHUB_ACTIONS") == "true"
            and os.environ.get("GITHUB_REPOSITORY") == readiness.REPOSITORY
            and os.environ.get("GITHUB_REF") in ("refs/heads/main", "refs/heads/major/state-contracts")
            and os.environ.get("GITHUB_EVENT_NAME") == "push", "reports require trusted main/program push CI")


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("operation", choices=("prepare-source", "observe-python", "observe-vitest", "admit-go", "emit"))
    parser.add_argument("--repo", type=Path, default=ROOT)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--observation", action="append", default=[], help="key=JSON path")
    parser.add_argument("--source-payload", type=Path)
    parser.add_argument("--native-binding", type=Path)
    parser.add_argument("--raw-results", type=Path)
    parser.add_argument("--execution-cwd", type=Path)
    parser.add_argument("--job-name")
    parser.add_argument("--payload-root", action="append", default=[], help="artifact name=original consumed root")
    parser.add_argument("arguments", nargs="*")
    args = parser.parse_args(argv)
    try:
        if args.operation == "prepare-source":
            prepare_source_payload(args.repo, args.output, args.job_name)
            return 0
        if args.operation == "observe-python":
            require(args.arguments, "Python entry point required")
            return observe_python(args.repo, args.arguments[0], args.arguments[1:], args.output, args.source_payload)
        if args.operation == "observe-vitest":
            return observe_vitest(args.repo, args.arguments, args.raw_results, args.output, args.execution_cwd)
        if args.operation == "admit-go":
            require(len(args.observation) == 1 and args.native_binding, "native observation and original stamp required")
            binding = load_json(args.native_binding)
            tree = git(args.repo, "rev-parse", binding["source_commit"] + "^{tree}")
            new_output(args.output, admit_go(load_json(args.observation[0]), binding, tree))
            return 0
        validate_emitter_environment()
        source, run_id = os.environ["GITHUB_SHA"], int(os.environ["GITHUB_RUN_ID"])
        identity = source_identity(args.repo)
        require(identity["source_commit"] == source and identity["clean"], "report source differs from actual clean checkout")
        req, _, artifacts, jobs = readiness.collect(args.repo, source, run_id, producing=True, allow_program_branch=True, producer_scope=True)
        matching = [j for j in jobs if j["name"] == args.job_name and j.get("status") == "in_progress"]
        require(len(matching) == 1, "one current original owning job required")
        observations = {}
        for item in args.observation:
            key, path = item.split("=", 1)
            require(key not in observations, "duplicate observation key")
            observations[key] = load_json(path)
        payloads = {}
        for item in args.payload_root:
            name, path = item.split("=", 1)
            require(name not in payloads, "duplicate payload identity")
            found = [a for a in artifacts if a["name"] == name]
            require(len(found) == 1, "original consumed artifact missing or ambiguous")
            payloads[name] = authenticated_payload(found[0], req, path, source_job=matching[0] if name == SOURCE_PAYLOAD else None)
        report = build_report(req, job_name=args.job_name, job_id=matching[0]["id"],
                              selections=load_json(args.repo / ".github/major-test-selections.json"),
                              producer_job=matching[0],
                              observations=observations, payloads=payloads)
        new_output(args.output, report)
        return 0
    except (OSError, ValueError, KeyError, TypeError, subprocess.SubprocessError, readiness.ReadinessError) as error:
        print("::error::Major qualification report pending: " + str(error), file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
