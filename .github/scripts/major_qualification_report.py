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
import shutil
import stat
import subprocess
import sys
import tempfile
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
MAX_TEST_ID_BYTES = 4096


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


def _source_git(repo, *args, index=None):
    """Read the actual index without refresh; only the owned index is writable."""
    env = local_read_git_env()
    env["GIT_OPTIONAL_LOCKS"] = "0"
    command = ["git", "--no-optional-locks", "--no-replace-objects", "--no-lazy-fetch"]
    if index is not None:
        env["GIT_INDEX_FILE"] = str(index)
        command += ["-c", "core.splitIndex=false", "-c", "core.fsmonitor=false",
                    "-c", "core.untrackedCache=false", "-c", "index.sparse=false",
                    "-c", "core.sparseCheckout=false"]
    result = subprocess.run([*command, "-C", str(repo), *args], env=env,
                            capture_output=True, timeout=30, check=True)
    require(len(result.stdout) <= MAX_JSON, "source status exceeds bound")
    return result.stdout


def _source_index_independent(raw, object_bytes):
    """Reject split-index reads before Git can freshen real shared metadata.

    Walk only the documented v2/v3/v4 entry/extension lengths. Git remains the
    checksum/object/index validator; this does not compute Git object hashes.
    """
    end = len(raw) - object_bytes
    require(object_bytes in (20, 32) and end >= 12 and raw[:4] == b"DIRC", "invalid source index header")
    version, count = int.from_bytes(raw[4:8], "big"), int.from_bytes(raw[8:12], "big")
    fixed = 42 + object_bytes
    require(version in (2, 3, 4) and count <= (end - 12) // (fixed + 1), "unsupported source index layout")
    cursor = 12
    for _ in range(count):
        start = cursor
        require(cursor + fixed <= end, "truncated source index entry")
        flags = int.from_bytes(raw[cursor + fixed - 2:cursor + fixed], "big")
        cursor += fixed
        if flags & 0x4000:
            require(version >= 3 and cursor + 2 <= end, "invalid extended source index entry")
            cursor += 2
        if version == 4:
            for number in range(10):
                require(cursor < end, "truncated source index prefix")
                value = raw[cursor]; cursor += 1
                if not value & 0x80:
                    break
            else:
                require(False, "unbounded source index prefix")
        nul = raw.find(b"\0", cursor, end)
        require(nul >= 0, "unterminated source index name")
        if version != 4:
            require(flags & 0xFFF == 0xFFF or nul - cursor == flags & 0xFFF, "invalid source index name length")
        cursor = nul + 1
        if version != 4:
            padding = -(cursor - start) % 8
            require(cursor + padding <= end and raw[cursor:cursor + padding] == b"\0" * padding,
                    "invalid source index padding")
            cursor += padding
    while cursor < end:
        require(cursor + 8 <= end, "truncated source index extension")
        signature = raw[cursor:cursor + 4]
        size = int.from_bytes(raw[cursor + 4:cursor + 8], "big")
        cursor += 8
        require(size <= end - cursor, "truncated source index extension")
        require(signature != b"link", "split source index cannot be read without changing shared metadata")
        cursor += size


def _source_index_state(path, object_bytes=20, *, retain=False):
    """Bind both the bytes and metadata of the real index, without changing it."""
    path = Path(path)
    before = path.lstat()
    require(stat.S_ISREG(before.st_mode) and not path.is_symlink()
            and not getattr(before, "st_file_attributes", 0) & stat.FILE_ATTRIBUTE_REPARSE_POINT
            and before.st_size <= 64 * 1024 * 1024, "source index must be a bounded regular file")
    def identity(info):
        return (info.st_dev, info.st_ino, info.st_mode, info.st_size,
                info.st_mtime_ns, info.st_ctime_ns)
    with path.open("rb") as stream:
        opened = os.fstat(stream.fileno())
        raw = stream.read(64 * 1024 * 1024 + 1)
        finished = os.fstat(stream.fileno())
    # Windows path/handle APIs can report different creation/ctime values for
    # a Git-replaced index. Check each API's ctime for stability, and bind the
    # descriptor to the path through device/inode/mode/size/mtime instead.
    require(identity(before) == identity(path.lstat())
            and identity(opened) == identity(finished)
            and identity(before)[:5] == identity(opened)[:5]
            and len(raw) == before.st_size, "source index changed during read")
    _source_index_independent(raw, object_bytes)
    state = identity(before), hashlib.sha256(raw).hexdigest()
    return (state, raw) if retain else state


def _source_indices(repo, *, retain=False):
    actual = os.fsdecode(_source_git(repo, "rev-parse", "--path-format=absolute", "--git-path", "index").rstrip(b"\r\n"))
    format_name = _source_git(repo, "rev-parse", "--show-object-format").strip()
    require(format_name in (b"sha1", b"sha256"), "unknown source object format")
    state = _source_index_state(actual, 20 if format_name == b"sha1" else 32, retain=retain)
    if retain:
        return (actual, state[0]), state[1]
    return actual, state


def source_checkout(repo, profile=None):
    """Return identity and the same current-policy status used by diagnostics.

    An index stat cache may have been produced under another text policy. A
    fresh HEAD index forces a current-policy read; the real index is checked
    independently so staged or unmerged changes cannot disappear in that view.
    """
    require(profile is None or profile in (SOURCE_PROFILE, SDK_SOURCE_PROFILE, Q02_SOURCE_PROFILE, HOOK_REVIEW_SOURCE_PROFILE) or profile in TS_PROFILE_PATHS, "unknown source identity profile")
    source = _source_git(repo, "rev-parse", "HEAD").decode("ascii").strip()
    tree = _source_git(repo, "rev-parse", source + "^{tree}").decode("ascii").strip()
    before, actual_raw = _source_indices(repo, retain=True)
    with tempfile.TemporaryDirectory(prefix="ca-source-index-") as temporary:
        private = Path(temporary).resolve(strict=True)
        require(not private.is_relative_to(Path(repo).resolve(strict=True)), "source index must be outside checkout")
        actual_copy = private / "actual-index"
        with actual_copy.open("xb") as stream:
            stream.write(actual_raw)
        staged = _source_git(repo, "diff", "--cached", "--no-ext-diff", "--no-textconv",
                             "--no-renames", "--name-status", "-z", source, "--", index=actual_copy)
        owned_index = private / "HEAD-index"
        _source_git(repo, "read-tree", source, index=owned_index)
        status = _source_git(repo, "status", "--porcelain=v1", "--no-renames",
                             "--untracked-files=all", "-z", index=owned_index)
    require(before == _source_indices(repo)
            and source == _source_git(repo, "rev-parse", "HEAD").decode("ascii").strip(),
            "source HEAD or index changed during observation")
    # Preserve staged/conflict diagnostics even when worktree bytes equal HEAD.
    parts = staged.split(b"\0")
    require(parts[-1] == b"" and (len(parts) - 1) % 2 == 0, "invalid staged source status")
    for label, path in zip(parts[:-1:2], parts[1:-1:2]):
        require(label in (b"A", b"C", b"D", b"M", b"R", b"T", b"U", b"X", b"B")
                and path, "invalid staged source status")
        status += (b"UU " if label == b"U" else label + b"  ") + path + b"\0"
    require(len(status) <= MAX_JSON, "source status exceeds bound")
    outputs = _pi_output_members(repo) if profile == "pi-tools-v1" else set()
    clean = not staged and all(not entry or (entry == "?? .codearbiter/.artifacts/store.lock" and ordinary_native_read_lock(repo))
                or (entry.startswith("?? ") and entry[3:] in outputs) for entry in status.decode("utf-8").split("\0"))
    return {"source_commit": source, "source_tree": tree, "clean": clean}, status


def source_identity(repo, profile=None):
    return source_checkout(repo, profile)[0]


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
SOURCE_PROFILE_CELLS = frozenset(('disposition:added_transitions:S75:added-rolled-back', 'disposition:added_transitions:S75:added-stage-failed', 'disposition:added_transitions:S75:added-unusable', 'disposition:added_transitions:S75:added-writer-refused', 'disposition:machines:C33', 'disposition:transitions:C33:01', 'disposition:transitions:C33:02', 'disposition:transitions:C33:03', 'disposition:transitions:S75:05'))


TS_COMMON_PATHS = frozenset(('.github/major-qualification-policy.json',
 '.github/major-test-selections.json',
 '.github/scripts/_boundedproc.py',
 '.github/scripts/_contextverificationlib.py',
 '.github/scripts/_immutable_git_blobs.py',
 '.github/scripts/ci20_native_binding.py',
 '.github/scripts/major_qualification_report.py',
 '.github/scripts/major_readiness.py',
 '.github/workflows/ci.yml',
 'core/pysrc/_artifactauthoritylib.py',
 'core/pysrc/_artifactlib.py',
 'core/pysrc/_artifactmanifestlib.py',
 'core/pysrc/_artifactpromptlib.py',
 'core/pysrc/_gitexec.py',
 'core/pysrc/_replylib.py'))
TS_PROFILE_PATHS = {
    'pi-tools-v1': TS_COMMON_PATHS | frozenset(('core/hosts.json',
     'plugins/ca-pi/extensions/codearbiter-child.js',
     'plugins/ca-pi/extensions/codearbiter.js',
     'plugins/ca-pi/tools/build.mjs',
     'plugins/ca-pi/tools/package-lock.json',
     'plugins/ca-pi/tools/package.json',
     'plugins/ca-pi/tools/src/activation.ts',
     'plugins/ca-pi/tools/src/activity.ts',
     'plugins/ca-pi/tools/src/approval-dialog.ts',
     'plugins/ca-pi/tools/src/approval-entry.ts',
     'plugins/ca-pi/tools/src/attestation.ts',
     'plugins/ca-pi/tools/src/audit-sink.ts',
     'plugins/ca-pi/tools/src/background-jobs.ts',
     'plugins/ca-pi/tools/src/bridge.ts',
     'plugins/ca-pi/tools/src/child-env.ts',
     'plugins/ca-pi/tools/src/child-extension.ts',
     'plugins/ca-pi/tools/src/command-ownership.ts',
     'plugins/ca-pi/tools/src/commands.ts',
     'plugins/ca-pi/tools/src/compaction.ts',
     'plugins/ca-pi/tools/src/compatibility.ts',
     'plugins/ca-pi/tools/src/contracts.ts',
     'plugins/ca-pi/tools/src/delegated-executor.ts',
     'plugins/ca-pi/tools/src/delegation-client.ts',
     'plugins/ca-pi/tools/src/delegation-contract.ts',
     'plugins/ca-pi/tools/src/delegation-journal.ts',
     'plugins/ca-pi/tools/src/delegation-session.ts',
     'plugins/ca-pi/tools/src/dispatch.ts',
     'plugins/ca-pi/tools/src/doctor.ts',
     'plugins/ca-pi/tools/src/extension.ts',
     'plugins/ca-pi/tools/src/farm.ts',
     'plugins/ca-pi/tools/src/footer-state.ts',
     'plugins/ca-pi/tools/src/footer.ts',
     'plugins/ca-pi/tools/src/git-facts.ts',
     'plugins/ca-pi/tools/src/inference-broker.ts',
     'plugins/ca-pi/tools/src/native-background.ts',
     'plugins/ca-pi/tools/src/native-plan.ts',
     'plugins/ca-pi/tools/src/notices.ts',
     'plugins/ca-pi/tools/src/parent-delegation.ts',
     'plugins/ca-pi/tools/src/path-boundary.ts',
     'plugins/ca-pi/tools/src/pi-api.d.ts',
     'plugins/ca-pi/tools/src/plan-mode.ts',
     'plugins/ca-pi/tools/src/policy.ts',
     'plugins/ca-pi/tools/src/process-tree.ts',
     'plugins/ca-pi/tools/src/redaction.ts',
     'plugins/ca-pi/tools/src/roles.ts',
     'plugins/ca-pi/tools/src/runner.ts',
     'plugins/ca-pi/tools/src/runtime-resolver.ts',
     'plugins/ca-pi/tools/src/session-identity.ts',
     'plugins/ca-pi/tools/src/sidebar-compositor.ts',
     'plugins/ca-pi/tools/src/sidebar-data.ts',
     'plugins/ca-pi/tools/src/sidebar-manager.ts',
     'plugins/ca-pi/tools/src/sidebar.ts',
     'plugins/ca-pi/tools/src/status.ts',
     'plugins/ca-pi/tools/src/tool-guard.ts',
     'plugins/ca-pi/tools/src/windows-supervisor.ts',
     'plugins/ca-pi/tools/test/activation.test.ts',
     'plugins/ca-pi/tools/test/activity.test.ts',
     'plugins/ca-pi/tools/test/approval-dialog.test.ts',
     'plugins/ca-pi/tools/test/audit-sink.test.ts',
     'plugins/ca-pi/tools/test/background-jobs.test.ts',
     'plugins/ca-pi/tools/test/benchmark-boundary.ts',
     'plugins/ca-pi/tools/test/bridge.test.ts',
     'plugins/ca-pi/tools/test/child-env.test.ts',
     'plugins/ca-pi/tools/test/commands.test.ts',
     'plugins/ca-pi/tools/test/compaction.test.ts',
     'plugins/ca-pi/tools/test/delegated-executor.test.ts',
     'plugins/ca-pi/tools/test/delegation-contract.test.ts',
     'plugins/ca-pi/tools/test/delegation-journal.test.ts',
     'plugins/ca-pi/tools/test/delegation-session.test.ts',
     'plugins/ca-pi/tools/test/dispatch.test.ts',
     'plugins/ca-pi/tools/test/doctor.test.ts',
     'plugins/ca-pi/tools/test/farm.test.ts',
     'plugins/ca-pi/tools/test/final-arguments-live.test.ts',
     'plugins/ca-pi/tools/test/final-arguments.test.ts',
     'plugins/ca-pi/tools/test/fixtures/live-governed-extension.mjs',
     'plugins/ca-pi/tools/test/fixtures/live-later-extension.mjs',
     'plugins/ca-pi/tools/test/fixtures/pi-0.80.5-help.txt',
     'plugins/ca-pi/tools/test/fixtures/pi-0.80.6-help.txt',
     'plugins/ca-pi/tools/test/footer.test.ts',
     'plugins/ca-pi/tools/test/git-facts.test.ts',
     'plugins/ca-pi/tools/test/inference-broker.test.ts',
     'plugins/ca-pi/tools/test/live-pi-host.ts',
     'plugins/ca-pi/tools/test/module-structure.test.ts',
     'plugins/ca-pi/tools/test/notices.test.ts',
     'plugins/ca-pi/tools/test/package.test.ts',
     'plugins/ca-pi/tools/test/parent-delegation.test.ts',
     'plugins/ca-pi/tools/test/path-boundary.test.ts',
     'plugins/ca-pi/tools/test/plan-mode.test.ts',
     'plugins/ca-pi/tools/test/policy.test.ts',
     'plugins/ca-pi/tools/test/process-tree.test.ts',
     'plugins/ca-pi/tools/test/runner-broker-lifecycle.test.ts',
     'plugins/ca-pi/tools/test/runner-isolation.test.ts',
     'plugins/ca-pi/tools/test/runtime-resolver.test.ts',
     'plugins/ca-pi/tools/test/security.test.ts',
     'plugins/ca-pi/tools/test/setup-disposable-home.ts',
     'plugins/ca-pi/tools/test/sidebar-compositor.test.ts',
     'plugins/ca-pi/tools/test/sidebar-data.test.ts',
     'plugins/ca-pi/tools/test/sidebar-manager.test.ts',
     'plugins/ca-pi/tools/test/sidebar-probe-live.test.ts',
     'plugins/ca-pi/tools/test/sidebar-window-contract.test.ts',
     'plugins/ca-pi/tools/test/sidebar.test.ts',
     'plugins/ca-pi/tools/test/status.test.ts',
     'plugins/ca-pi/tools/test/tool-guard.test.ts',
     'plugins/ca-pi/tools/test/windows-supervisor.test.ts',
     'plugins/ca-pi/tools/test/workflow-recovery.test.ts',
     'plugins/ca-pi/tools/tsconfig.json',
     'plugins/ca-pi/tools/vitest.config.ts',
     'plugins/ca/hooks/secret-detection-corpus.json',
     'plugins/ca/tools/redactor.ts')),
    'sandbox-tools-v1': TS_COMMON_PATHS | frozenset(('plugins/ca-sandbox/tools/__fixtures__/docker-required/gate.fixture.test.ts',
     'plugins/ca-sandbox/tools/__fixtures__/docker-required/vitest.config.ts',
     'plugins/ca-sandbox/tools/__fixtures__/go/go.mod',
     'plugins/ca-sandbox/tools/__fixtures__/go/main.go',
     'plugins/ca-sandbox/tools/__fixtures__/node/index.js',
     'plugins/ca-sandbox/tools/__fixtures__/node/package.json',
     'plugins/ca-sandbox/tools/__fixtures__/py/main.py',
     'plugins/ca-sandbox/tools/__fixtures__/py/requirements.txt',
     'plugins/ca-sandbox/tools/__fixtures__/rust/Cargo.lock',
     'plugins/ca-sandbox/tools/__fixtures__/rust/Cargo.toml',
     'plugins/ca-sandbox/tools/__fixtures__/rust/src/main.rs',
     'plugins/ca-sandbox/tools/__tests__/isolation.test.ts',
     'plugins/ca-sandbox/tools/build-pinned-base.test.ts',
     'plugins/ca-sandbox/tools/build.test.ts',
     'plugins/ca-sandbox/tools/build.ts',
     'plugins/ca-sandbox/tools/builder-observation.test.ts',
     'plugins/ca-sandbox/tools/cache-provenance.test.ts',
     'plugins/ca-sandbox/tools/claude-inside-cli.test.ts',
     'plugins/ca-sandbox/tools/claude-inside-cli.ts',
     'plugins/ca-sandbox/tools/claude-inside.js',
     'plugins/ca-sandbox/tools/claude-inside.test.ts',
     'plugins/ca-sandbox/tools/claude-inside.ts',
     'plugins/ca-sandbox/tools/cli-resolve.test.ts',
     'plugins/ca-sandbox/tools/cli.test.ts',
     'plugins/ca-sandbox/tools/cli.ts',
     'plugins/ca-sandbox/tools/cp.test.ts',
     'plugins/ca-sandbox/tools/cp.ts',
     'plugins/ca-sandbox/tools/create-failure-diagnostics.test.ts',
     'plugins/ca-sandbox/tools/create-partial-compensation.test.ts',
     'plugins/ca-sandbox/tools/create.test.ts',
     'plugins/ca-sandbox/tools/create.ts',
     'plugins/ca-sandbox/tools/deadline.test.ts',
     'plugins/ca-sandbox/tools/dephash.test.ts',
     'plugins/ca-sandbox/tools/dephash.ts',
     'plugins/ca-sandbox/tools/destroy.ts',
     'plugins/ca-sandbox/tools/docker-gate.test.ts',
     'plugins/ca-sandbox/tools/docker-gate.ts',
     'plugins/ca-sandbox/tools/docker.ts',
     'plugins/ca-sandbox/tools/exec.test.ts',
     'plugins/ca-sandbox/tools/exec.ts',
     'plugins/ca-sandbox/tools/installed-bundle.test.ts',
     'plugins/ca-sandbox/tools/layering.test.ts',
     'plugins/ca-sandbox/tools/lifecycle.test.ts',
     'plugins/ca-sandbox/tools/mounts.test.ts',
     'plugins/ca-sandbox/tools/mounts.ts',
     'plugins/ca-sandbox/tools/multistack.test.ts',
     'plugins/ca-sandbox/tools/native-build-inputs.test.ts',
     'plugins/ca-sandbox/tools/network.test.ts',
     'plugins/ca-sandbox/tools/network.ts',
     'plugins/ca-sandbox/tools/package-lock.json',
     'plugins/ca-sandbox/tools/package.json',
     'plugins/ca-sandbox/tools/registry.ts',
     'plugins/ca-sandbox/tools/run.test.ts',
     'plugins/ca-sandbox/tools/run.ts',
     'plugins/ca-sandbox/tools/sandbox.js',
     'plugins/ca-sandbox/tools/smoke.test.ts',
     'plugins/ca-sandbox/tools/smoke.ts',
     'plugins/ca-sandbox/tools/state-contracts.test.ts',
     'plugins/ca-sandbox/tools/supply-chain.test.ts',
     'plugins/ca-sandbox/tools/teardown.test.ts',
     'plugins/ca-sandbox/tools/tsconfig.json',
     'plugins/ca-sandbox/tools/vitest.config.ts')),
}

TS_PROFILE_ROOTS = {"pi-tools-v1": "plugins/ca-pi/tools", "sandbox-tools-v1": "plugins/ca-sandbox/tools"}
TS_PROFILE_JOBS = {"pi-tools-v1": "Coverage union (Pi)  <os: windows-latest>",
                   "sandbox-tools-v1": "[CHECK] | [SBX ] | Sandbox driver contract"}
TS_PROFILE_PAYLOADS = {"pi-tools-v1": "major-source-inputs-pi-windows-coverage",
                       "sandbox-tools-v1": "major-source-inputs-sandbox-driver"}
TS_PROFILE_UPLOADS = {"pi-tools-v1": "Upload Pi source-test inputs", "sandbox-tools-v1": "Upload Sandbox source-test inputs"}
TS_PROFILE_CELLS = {"pi-tools-v1": frozenset("disposition:transitions:pi-qualification:disposable-home:" + number for number in ("01", "02", "03")),
                    "sandbox-tools-v1": frozenset(("disposition:transitions:S54:01",
                        "disposition:transitions:S51:01", "disposition:transitions:S51:02",
                        "disposition:transitions:S52:06"))}
TS_OUTPUT_NAMES = frozenset("windows-latest" + suffix for suffix in (".json", ".provenance.json", ".checked.json"))


SDK_SOURCE_PROFILE = "pi-sdk-footer-v1"
SDK_SOURCE_JOB = "[CHECK] | [PI  ] | Host-independent adapter contract"
SDK_SOURCE_PAYLOAD = "major-source-inputs-pi-sdk-footer"
SDK_SOURCE_UPLOAD = "Upload Pi SDK footer source-test inputs"
SDK_SOURCE_CELLS = frozenset(("disposition:transitions:S18:07",))
SDK_SOURCE_SCRIPT = ".github/scripts/test_pi_package.py"
SDK_SOURCE_PATHS = frozenset(('.github/fixtures/pi-hosts/1.5.0/.npmrc',
 '.github/fixtures/pi-hosts/1.5.0/package-lock.json',
 '.github/fixtures/pi-hosts/1.5.0/package.json',
 '.github/fixtures/pi-hosts/1.5.0/review.json',
 '.github/major-qualification-policy.json',
 '.github/major-test-selections.json',
 '.github/scripts/_boundedproc.py',
 '.github/scripts/_contextverificationlib.py',
 '.github/scripts/_immutable_git_blobs.py',
 '.github/scripts/ci20_native_binding.py',
 '.github/scripts/major_qualification_report.py',
 '.github/scripts/major_readiness.py',
 '.github/scripts/pi_cli_resolver.py',
 '.github/scripts/pi_host_locks.py',
 '.github/scripts/test_pi_package.py',
 '.github/scripts/test_pi_platform_contract.py',
 '.github/workflows/ci.yml',
 'core/pysrc/_artifactauthoritylib.py',
 'core/pysrc/_artifactlib.py',
 'core/pysrc/_artifactmanifestlib.py',
 'core/pysrc/_artifactpromptlib.py',
 'core/pysrc/_gitexec.py',
 'core/pysrc/_replylib.py',
 'plugins/ca-pi/tools/src/activation.ts',
 'plugins/ca-pi/tools/src/activity.ts',
 'plugins/ca-pi/tools/src/approval-dialog.ts',
 'plugins/ca-pi/tools/src/approval-entry.ts',
 'plugins/ca-pi/tools/src/attestation.ts',
 'plugins/ca-pi/tools/src/audit-sink.ts',
 'plugins/ca-pi/tools/src/background-jobs.ts',
 'plugins/ca-pi/tools/src/bridge.ts',
 'plugins/ca-pi/tools/src/child-env.ts',
 'plugins/ca-pi/tools/src/child-extension.ts',
 'plugins/ca-pi/tools/src/command-ownership.ts',
 'plugins/ca-pi/tools/src/commands.ts',
 'plugins/ca-pi/tools/src/compaction.ts',
 'plugins/ca-pi/tools/src/compatibility.ts',
 'plugins/ca-pi/tools/src/contracts.ts',
 'plugins/ca-pi/tools/src/delegated-executor.ts',
 'plugins/ca-pi/tools/src/delegation-client.ts',
 'plugins/ca-pi/tools/src/delegation-contract.ts',
 'plugins/ca-pi/tools/src/delegation-journal.ts',
 'plugins/ca-pi/tools/src/delegation-session.ts',
 'plugins/ca-pi/tools/src/dispatch.ts',
 'plugins/ca-pi/tools/src/doctor.ts',
 'plugins/ca-pi/tools/src/extension.ts',
 'plugins/ca-pi/tools/src/farm.ts',
 'plugins/ca-pi/tools/src/footer-state.ts',
 'plugins/ca-pi/tools/src/footer.ts',
 'plugins/ca-pi/tools/src/git-facts.ts',
 'plugins/ca-pi/tools/src/inference-broker.ts',
 'plugins/ca-pi/tools/src/native-background.ts',
 'plugins/ca-pi/tools/src/native-plan.ts',
 'plugins/ca-pi/tools/src/notices.ts',
 'plugins/ca-pi/tools/src/parent-delegation.ts',
 'plugins/ca-pi/tools/src/path-boundary.ts',
 'plugins/ca-pi/tools/src/pi-api.d.ts',
 'plugins/ca-pi/tools/src/plan-mode.ts',
 'plugins/ca-pi/tools/src/policy.ts',
 'plugins/ca-pi/tools/src/process-tree.ts',
 'plugins/ca-pi/tools/src/redaction.ts',
 'plugins/ca-pi/tools/src/roles.ts',
 'plugins/ca-pi/tools/src/runner.ts',
 'plugins/ca-pi/tools/src/runtime-resolver.ts',
 'plugins/ca-pi/tools/src/session-identity.ts',
 'plugins/ca-pi/tools/src/sidebar-compositor.ts',
 'plugins/ca-pi/tools/src/sidebar-data.ts',
 'plugins/ca-pi/tools/src/sidebar-manager.ts',
 'plugins/ca-pi/tools/src/sidebar.ts',
 'plugins/ca-pi/tools/src/status.ts',
 'plugins/ca-pi/tools/src/tool-guard.ts',
 'plugins/ca-pi/tools/src/windows-supervisor.ts',
 'plugins/ca/tools/redactor.ts'))


def _sdk_source_members(repo):
    """The fixed SDK source namespace cannot acquire an unbound sibling/import."""
    root = Path(repo) / "plugins/ca-pi/tools/src"
    found, pending, count = set(), [root], 0
    while pending:
        folder = pending.pop(); count += 1
        info = folder.lstat()
        require(count <= 512 and stat.S_ISDIR(info.st_mode) and not folder.is_symlink()
                and not getattr(info, "st_file_attributes", 0) & stat.FILE_ATTRIBUTE_REPARSE_POINT,
                "SDK source namespace is unsafe or unbounded")
        for path in folder.iterdir():
            info = path.lstat()
            require(not path.is_symlink() and not getattr(info, "st_file_attributes", 0) & stat.FILE_ATTRIBUTE_REPARSE_POINT,
                    "SDK source namespace contains a link")
            if stat.S_ISDIR(info.st_mode): pending.append(path)
            else:
                require(stat.S_ISREG(info.st_mode), "SDK source namespace contains nonregular data")
                found.add(path.relative_to(repo).as_posix())
                require(len(found) <= 2048, "SDK source namespace exceeds bound")
    require(found == {name for name in SDK_SOURCE_PATHS if name.startswith("plugins/ca-pi/tools/src/")},
            "SDK source physical membership differs")


def _sdk_python_command(argv):
    require(isinstance(argv, list) and len(argv) == 2 and all(type(value) is str and value for value in argv)
            and (argv[1].replace("\\", "/") == SDK_SOURCE_SCRIPT
                 or argv[1].replace("\\", "/").endswith("/" + SDK_SOURCE_SCRIPT)),
            "SDK source observation requires the original unfiltered Python command")


# Q02 reports implementation/regression completion on integration only. This
# closed profile never stands in for final-main readiness or Q03 settlement.
Q02_SOURCE_PROFILE = "major-readiness-implementation-v1"
Q02_SOURCE_JOB = SOURCE_JOB
Q02_SOURCE_PAYLOAD = "major-source-inputs-q02-implementation"
Q02_SOURCE_UPLOAD = "Upload Q02 implementation source-test inputs"
Q02_SOURCE_CELLS = frozenset(("task:Q-02",))
Q02_SOURCE_SCRIPTS = frozenset((".github/scripts/test_major_readiness.py", ".github/scripts/test_release_workflow.py"))
Q02_SOURCE_PATHS = frozenset(('.codearbiter/decisions/0030-orchestration-mode-plane-with-composed-persona.md',
 '.codearbiter/decisions/0040-independent-per-target-release-with-consumer-safety-gates.md',
 '.codearbiter/decisions/0043-assistive-state-engine.md',
 '.codearbiter/decisions/0044-trusted-pi-npm-publication.md',
 '.codearbiter/decisions/adr-lifecycle.jsonl',
 '.codearbiter/open-questions.md',
 '.codearbiter/reports/agent-lane-proof.json',
 '.github/actions/publish-target/action.yml',
 '.github/integration-candidate.json',
 '.github/major-qualification-policy.json',
 '.github/major-test-selections.json',
 '.github/scripts/_boundedproc.py',
 '.github/scripts/_context_fixturelib.py',
 '.github/scripts/_contextverificationlib.py',
 '.github/scripts/_git_fixture_diagnostics.py',
 '.github/scripts/_immutable_git_blobs.py',
 '.github/scripts/_npm_publishlib.py',
 '.github/scripts/_releaselib.py',
 '.github/scripts/academy_promotion.py',
 '.github/scripts/build_release_targets_provenance.py',
 '.github/scripts/check_adr_lifecycle.py',
 '.github/scripts/check_auto_release_candidate.py',
 '.github/scripts/check_branch_protection.py',
 '.github/scripts/check_codex_host.py',
 '.github/scripts/check_codex_skill_resources.py',
 '.github/scripts/check_codex_static_package.py',
 '.github/scripts/check_command_route_release_state.py',
 '.github/scripts/check_sandbox_docker_layers.py',
 '.github/scripts/check_skill_proof_fresh.py',
 '.github/scripts/check_state_contracts_integration.py',
 '.github/scripts/check_tag_immutability.py',
 '.github/scripts/ci20_native_binding.py',
 '.github/scripts/coverage_union.py',
 '.github/scripts/create_codex_distribution_token.py',
 '.github/scripts/major_native_observation.py',
 '.github/scripts/major_qualification_report.py',
 '.github/scripts/major_readiness.py',
 '.github/scripts/npm_audit_gate.py',
 '.github/scripts/pages_readiness.py',
 '.github/scripts/payload_scope.py',
 '.github/scripts/payload_version_gate.py',
 '.github/scripts/pi_benchmark.py',
 '.github/scripts/pi_evidence.py',
 '.github/scripts/pi_host_locks.py',
 '.github/scripts/pi_promotion.py',
 '.github/scripts/prepare_adr_acceptance.py',
 '.github/scripts/reconcile_tag_receipt.py',
 '.github/scripts/release_source.py',
 '.github/scripts/release_target.py',
 '.github/scripts/run_artifact_authority_shard.py',
 '.github/scripts/run_concurrent_suites.py',
 '.github/scripts/site_playwright_observation.py',
 '.github/scripts/tag_publication_receipt.py',
 '.github/scripts/test_check_skill_proof_fresh.py',
 '.github/scripts/test_generated_output.py',
 '.github/scripts/test_major_native_observation.py',
 '.github/scripts/test_major_readiness.py',
 '.github/scripts/test_release_lib.py',
 '.github/scripts/test_release_workflow.py',
 '.github/scripts/test_site_playwright_observation.py',
 '.github/scripts/test_workflow_recovery.py',
 '.github/scripts/validate_codex_distribution_identity.py',
 '.github/scripts/verify_codex_candidate_provenance.py',
 '.github/scripts/verify_codex_distribution_rulesets.py',
 '.github/scripts/verify_codex_static_candidate.py',
 '.github/scripts/verify_pi_support.py',
 '.github/workflows/academy-promotion.yml',
 '.github/workflows/ci.yml',
 '.github/workflows/docs.yml',
 '.github/workflows/pi-promotion.yml',
 '.github/workflows/release.yml',
 'README.md',
 'core/artifact-release-manifest.json',
 'core/artifacts/cmd/ca-artifact/main.go',
 'core/artifacts/internal/authority/receipt.go',
 'core/artifacts/internal/contextdocument/contract.go',
 'core/artifacts/internal/contextdocument/evidence.go',
 'core/artifacts/internal/contextdocument/finalization.go',
 'core/artifacts/internal/contextdocument/operations.go',
 'core/artifacts/internal/evidence/completion.go',
 'core/artifacts/internal/evidence/completion_workspace.go',
 'core/artifacts/internal/evidence/snapshot.go',
 'core/artifacts/internal/model/artifact.go',
 'core/artifacts/internal/model/assistive.go',
 'core/artifacts/internal/observation/contract.go',
 'core/artifacts/internal/observation/runner_contract.go',
 'core/artifacts/internal/observation/sprint.go',
 'core/artifacts/internal/operations/assistive.go',
 'core/artifacts/internal/operations/capture_export.go',
 'core/artifacts/internal/operations/context_assistive.go',
 'core/artifacts/internal/operations/context_authority.go',
 'core/artifacts/internal/operations/engine.go',
 'core/artifacts/internal/operations/evidence_context.go',
 'core/artifacts/internal/operations/farm_projection.go',
 'core/artifacts/internal/operations/input_scope.go',
 'core/artifacts/internal/operations/knowledge_merge.go',
 'core/artifacts/internal/operations/knowledge_ops.go',
 'core/artifacts/internal/operations/lifecycle.go',
 'core/artifacts/internal/operations/migration.go',
 'core/artifacts/internal/operations/mutations.go',
 'core/artifacts/internal/operations/prerequisite_observation.go',
 'core/artifacts/internal/operations/project_view.go',
 'core/artifacts/internal/operations/protocol.go',
 'core/artifacts/internal/operations/sprint.go',
 'core/artifacts/internal/operations/task_check.go',
 'core/artifacts/internal/operations/task_context.go',
 'core/artifacts/internal/operations/work.go',
 'core/artifacts/internal/operations/work_adopt.go',
 'core/artifacts/internal/operations/work_coordination.go',
 'core/artifacts/internal/operations/work_effects.go',
 'core/artifacts/internal/operations/work_project.go',
 'core/artifacts/internal/operations/work_transition_map.go',
 'core/artifacts/internal/read/read.go',
 'core/artifacts/internal/render/render.go',
 'core/artifacts/internal/repository/catalog.go',
 'core/artifacts/internal/schema/work.schema.json',
 'core/artifacts/internal/store/fs_lock_darwin.go',
 'core/artifacts/internal/store/fs_lock_windows.go',
 'core/artifacts/internal/store/fs_other.go',
 'core/artifacts/internal/store/fs_portable.go',
 'core/artifacts/internal/store/infrastructure.go',
 'core/artifacts/internal/store/memo.go',
 'core/artifacts/internal/store/transaction.go',
 'core/artifacts/internal/symbol/index.go',
 'core/artifacts/internal/validate/knowledge.go',
 'core/artifacts/internal/validate/validate.go',
 'core/hosts.json',
 'core/pysrc/_activationlib.py',
 'core/pysrc/_adrlifecycle.py',
 'core/pysrc/_adrlifecyclegit.py',
 'core/pysrc/_appendonlyconflictlib.py',
 'core/pysrc/_approvallib.py',
 'core/pysrc/_arbiterstatelib.py',
 'core/pysrc/_artifactauthoritylib.py',
 'core/pysrc/_artifactlib.py',
 'core/pysrc/_artifactmanifestlib.py',
 'core/pysrc/_artifactpromptlib.py',
 'core/pysrc/_babysitlib.py',
 'core/pysrc/_bashguardlib.py',
 'core/pysrc/_boxlib.py',
 'core/pysrc/_cleanuplib.py',
 'core/pysrc/_colorlib.py',
 'core/pysrc/_contextmergelib.py',
 'core/pysrc/_contextreportlib.py',
 'core/pysrc/_contextselectlib.py',
 'core/pysrc/_contextsnapshotlib.py',
 'core/pysrc/_contextwriterlib.py',
 'core/pysrc/_debughandofflib.py',
 'core/pysrc/_durabilitylib.py',
 'core/pysrc/_entrylib.py',
 'core/pysrc/_fmtlib.py',
 'core/pysrc/_gitexec.py',
 'core/pysrc/_githooks.py',
 'core/pysrc/_gitlib.py',
 'core/pysrc/_hooklib.py',
 'core/pysrc/_intentlib.py',
 'core/pysrc/_knowledgelib.py',
 'core/pysrc/_ledgerlib.py',
 'core/pysrc/_modelib.py',
 'core/pysrc/_overrideappendlib.py',
 'core/pysrc/_pathnorm.py',
 'core/pysrc/_planfilelib.py',
 'core/pysrc/_prerequisitelib.py',
 'core/pysrc/_protectedlib.py',
 'core/pysrc/_protectedstatelib.py',
 'core/pysrc/_provenancelib.py',
 'core/pysrc/_prunelib.py',
 'core/pysrc/_prunepolicy.py',
 'core/pysrc/_readinjectlib.py',
 'core/pysrc/_reconciliationlib.py',
 'core/pysrc/_releaselib.py',
 'core/pysrc/_replylib.py',
 'core/pysrc/_scopelib.py',
 'core/pysrc/_segmentslib.py',
 'core/pysrc/_sensitivelib.py',
 'core/pysrc/_sessionlib.py',
 'core/pysrc/_sloplib.py',
 'core/pysrc/_sprintapprovallib.py',
 'core/pysrc/_standuplib.py',
 'core/pysrc/_subagentslib.py',
 'core/pysrc/_taskboardlib.py',
 'core/pysrc/_taskexcludelib.py',
 'core/pysrc/_tribunalinventorylib.py',
 'core/pysrc/_tribunalrunlib.py',
 'core/pysrc/_updatelib.py',
 'core/pysrc/_usagelib.py',
 'core/pysrc/_workadopt.py',
 'core/pysrc/_workflowrecoverylib.py',
 'core/pysrc/_workgithub.py',
 'core/pysrc/_worklib.py',
 'core/pysrc/adr-merge-method.py',
 'core/pysrc/append-override.py',
 'core/pysrc/artifact-authority-hook.py',
 'core/pysrc/artifact-authority.py',
 'core/pysrc/artifact-reconcile.py',
 'core/pysrc/babysit.py',
 'core/pysrc/boardsync.py',
 'core/pysrc/debug-handoff.py',
 'core/pysrc/doctor.py',
 'core/pysrc/git-enforce.py',
 'core/pysrc/hostapi.py',
 'core/pysrc/init-codearbiter.py',
 'core/pysrc/knowledge.py',
 'core/pysrc/migration-pass.py',
 'core/pysrc/post-write-edit.py',
 'core/pysrc/pre-bash.py',
 'core/pysrc/pre-edit.py',
 'core/pysrc/pre-read.py',
 'core/pysrc/pre-write.py',
 'core/pysrc/prompt-submit.py',
 'core/pysrc/prune-transcript.py',
 'core/pysrc/releasehash.py',
 'core/pysrc/resolve-append-only-conflict.py',
 'core/pysrc/resolve-context-conflict.py',
 'core/pysrc/security-pass.py',
 'core/pysrc/session-start.py',
 'core/pysrc/statusline.py',
 'core/pysrc/taskwrite.py',
 'core/pysrc/tribunal.py',
 'core/pysrc/update-refresh.py',
 'core/pysrc/wire-statusline.py',
 'core/pysrc/work.py',
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
 'core/workflow-recovery-contract.json',
 'docs/state-contracts-major/BRANCH-AND-RELEASE.md',
 'docs/state-contracts-major/contracts/finding-dispositions.json',
 'docs/state-contracts-major/contracts/machine-coverage.json',
 'docs/state-contracts-major/contracts/program.json',
 'docs/state-contracts-major/contracts/scenarios.json',
 'docs/state-contracts-major/contracts/tasks.json',
 'docs/state-contracts-major/contracts/transition-coverage.json',
 'docs/state-contracts-major/execution/coverage-ledger.json',
 'docs/state-contracts-major/execution/progress.json',
 'docs/state-contracts-major/root-tasks.json',
 'plugins/ca-codex/hooks/_host.py',
 'plugins/ca-codex/hooks/pre-tool-adapter.py',
 'plugins/ca-codex/hooks/tribunal-usage.py',
 'plugins/ca-pi/hooks/_host.py',
 'plugins/ca-pi/hooks/pi-approval.py',
 'plugins/ca-pi/hooks/pi-bridge.py',
 'plugins/ca-pi/package.json',
 'plugins/ca-pi/tools/build.mjs',
 'plugins/ca-pi/tools/src/activation.ts',
 'plugins/ca-pi/tools/src/activity.ts',
 'plugins/ca-pi/tools/src/approval-dialog.ts',
 'plugins/ca-pi/tools/src/approval-entry.ts',
 'plugins/ca-pi/tools/src/attestation.ts',
 'plugins/ca-pi/tools/src/audit-sink.ts',
 'plugins/ca-pi/tools/src/background-jobs.ts',
 'plugins/ca-pi/tools/src/bridge.ts',
 'plugins/ca-pi/tools/src/child-env.ts',
 'plugins/ca-pi/tools/src/child-extension.ts',
 'plugins/ca-pi/tools/src/command-ownership.ts',
 'plugins/ca-pi/tools/src/commands.ts',
 'plugins/ca-pi/tools/src/compaction.ts',
 'plugins/ca-pi/tools/src/compatibility.ts',
 'plugins/ca-pi/tools/src/contracts.ts',
 'plugins/ca-pi/tools/src/dispatch.ts',
 'plugins/ca-pi/tools/src/doctor.ts',
 'plugins/ca-pi/tools/src/extension.ts',
 'plugins/ca-pi/tools/src/farm.ts',
 'plugins/ca-pi/tools/src/footer-state.ts',
 'plugins/ca-pi/tools/src/footer.ts',
 'plugins/ca-pi/tools/src/git-facts.ts',
 'plugins/ca-pi/tools/src/inference-broker.ts',
 'plugins/ca-pi/tools/src/native-background.ts',
 'plugins/ca-pi/tools/src/native-plan.ts',
 'plugins/ca-pi/tools/src/notices.ts',
 'plugins/ca-pi/tools/src/plan-mode.ts',
 'plugins/ca-pi/tools/src/policy.ts',
 'plugins/ca-pi/tools/src/process-tree.ts',
 'plugins/ca-pi/tools/src/roles.ts',
 'plugins/ca-pi/tools/src/runner.ts',
 'plugins/ca-pi/tools/src/runtime-resolver.ts',
 'plugins/ca-pi/tools/src/session-identity.ts',
 'plugins/ca-pi/tools/src/sidebar-compositor.ts',
 'plugins/ca-pi/tools/src/sidebar-data.ts',
 'plugins/ca-pi/tools/src/sidebar-manager.ts',
 'plugins/ca-pi/tools/src/sidebar.ts',
 'plugins/ca-pi/tools/src/status.ts',
 'plugins/ca-pi/tools/src/tool-guard.ts',
 'plugins/ca-pi/tools/src/windows-supervisor.ts',
 'plugins/ca-pi/tools/test/live-pi-host.ts',
 'plugins/ca-pi/tools/test/setup-disposable-home.ts',
 'plugins/ca-sandbox/COMMANDS.md',
 'plugins/ca-sandbox/README.md',
 'plugins/ca-sandbox/commands/sandbox-cp.md',
 'plugins/ca-sandbox/commands/sandbox-destroy.md',
 'plugins/ca-sandbox/commands/sandbox-exec.md',
 'plugins/ca-sandbox/commands/sandbox-shell.md',
 'plugins/ca-sandbox/commands/sandbox.md',
 'plugins/ca-sandbox/skills/INDEX.md',
 'plugins/ca-sandbox/skills/sandbox-claude-inside/SKILL.md',
 'plugins/ca-sandbox/skills/sandbox-lifecycle/SKILL.md',
 'plugins/ca-sandbox/tools/build.ts',
 'plugins/ca-sandbox/tools/claude-inside-cli.ts',
 'plugins/ca-sandbox/tools/claude-inside.ts',
 'plugins/ca-sandbox/tools/cli.ts',
 'plugins/ca-sandbox/tools/cp.ts',
 'plugins/ca-sandbox/tools/create.ts',
 'plugins/ca-sandbox/tools/dephash.ts',
 'plugins/ca-sandbox/tools/destroy.ts',
 'plugins/ca-sandbox/tools/docker-gate.ts',
 'plugins/ca-sandbox/tools/docker.ts',
 'plugins/ca-sandbox/tools/exec.ts',
 'plugins/ca-sandbox/tools/mounts.ts',
 'plugins/ca-sandbox/tools/network.ts',
 'plugins/ca-sandbox/tools/registry.ts',
 'plugins/ca-sandbox/tools/run.ts',
 'plugins/ca/README.md',
 'plugins/ca/hooks/_host.py',
 'plugins/ca/hooks/tribunal-usage.py',
 'plugins/ca/skills/release/SKILL.md',
 'plugins/ca/tools/exec.ts',
 'plugins/ca/tools/farm.ts',
 'plugins/ca/tools/mutation.ts',
 'plugins/ca/tools/worktree-fs.ts',
 'site/astro.config.mjs',
 'site/scripts/academy-source.ts',
 'site/scripts/academy-wayfinding.ts',
 'site/scripts/capture-context-examples.py',
 'site/scripts/capture-hook-proof.ts',
 'site/scripts/capture-statusline-themes.py',
 'site/scripts/capture/fixture.ts',
 'site/scripts/capture/harness.ts',
 'site/scripts/capture/label.ts',
 'site/scripts/capture/normalize.ts',
 'site/scripts/capture/py-runner.py',
 'site/scripts/capture/render.ts',
 'site/scripts/capture/run.ts',
 'site/scripts/capture/targets.ts',
 'site/scripts/capture/verify.ts',
 'site/scripts/concept-directory.ts',
 'site/scripts/decision-evidence.ts',
 'site/scripts/diagram-audit.ts',
 'site/scripts/execution-maps/atlas-command.ts',
 'site/scripts/execution-maps/atlas-model.ts',
 'site/scripts/execution-maps/atlas-render.ts',
 'site/scripts/execution-maps/atlas-theme.ts',
 'site/scripts/execution-maps/atlas.ts',
 'site/scripts/execution-maps/locations.ts',
 'site/scripts/execution-maps/render.ts',
 'site/scripts/gen.ts',
 'site/scripts/generate-academy.ts',
 'site/scripts/generate-atlas.ts',
 'site/scripts/generate-diagrams.ts',
 'site/scripts/generate-product-example.py',
 'site/scripts/generator/assign-slugs.ts',
 'site/scripts/generator/build-index.ts',
 'site/scripts/generator/classify-source.ts',
 'site/scripts/generator/collect-lenses.ts',
 'site/scripts/generator/collect-sources.ts',
 'site/scripts/generator/configuration-reference.ts',
 'site/scripts/generator/curated-drift.ts',
 'site/scripts/generator/derive-name.ts',
 'site/scripts/generator/extract-hook-gates.ts',
 'site/scripts/generator/forge-status.ts',
 'site/scripts/generator/format-tools-list.ts',
 'site/scripts/generator/generate.ts',
 'site/scripts/generator/host-command-catalog.ts',
 'site/scripts/generator/landing-stats.ts',
 'site/scripts/generator/load-curated.ts',
 'site/scripts/generator/markdown-fences.ts',
 'site/scripts/generator/model-tier.ts',
 'site/scripts/generator/normalize-source.ts',
 'site/scripts/generator/parse-doc.ts',
 'site/scripts/generator/parse-fields.ts',
 'site/scripts/generator/plugin-workflow-pairs.ts',
 'site/scripts/generator/render-agent-page.ts',
 'site/scripts/generator/render-changelog.ts',
 'site/scripts/generator/render-command-page.ts',
 'site/scripts/generator/render-gates-table.ts',
 'site/scripts/generator/render-hooks-reference.ts',
 'site/scripts/generator/render-lens-page.ts',
 'site/scripts/generator/render-reader-fields.ts',
 'site/scripts/generator/render-reference-lead.ts',
 'site/scripts/generator/render-related-links.ts',
 'site/scripts/generator/render-skill-page.ts',
 'site/scripts/generator/render-source-embed.ts',
 'site/scripts/generator/slugify.ts',
 'site/scripts/generator/source-ref.ts',
 'site/scripts/generator/split-frontmatter.ts',
 'site/scripts/generator/truncate-description.ts',
 'site/scripts/generator/types.ts',
 'site/scripts/generator/workflow-pairs.ts',
 'site/scripts/generator/yaml-quote.ts',
 'site/scripts/guide-directory.ts',
 'site/scripts/journey-navigation.ts',
 'site/scripts/link-audit.ts',
 'site/scripts/link-audit/lib.ts',
 'site/scripts/pagefind-build.ts',
 'site/scripts/product-example.ts',
 'site/scripts/reference-sidebar.ts',
 'site/scripts/rehype-base-links.ts',
 'site/scripts/rehype-table-shell.ts',
 'site/scripts/release-applicability.ts',
 'site/scripts/statusline-capture.ts',
 'site/scripts/topic-map.ts',
 'site/scripts/version-facts.ts',
 'site/src/components/AcademyBookmark.astro',
 'site/src/components/AcademyCommandPreferences.astro',
 'site/src/components/AcademyOverview.astro',
 'site/src/components/ContextExplorer.astro',
 'site/src/components/DecisionEvidence.astro',
 'site/src/components/ExampleChoices.astro',
 'site/src/components/ExecutionMap.astro',
 'site/src/components/GuideDirectory.astro',
 'site/src/components/Search.astro',
 'site/src/components/SplashDocsRail.astro',
 'site/src/components/TableOfContents.astro',
 'site/src/components/ThemeProvider.astro',
 'site/src/components/WorkflowAtlas.astro',
 'site/src/content.config.ts',
 'site/src/pages/release-applicability.json.ts',
 'site/src/release-applicability-presentation.ts',
 'site/src/scripts/academy-bookmark.ts',
 'site/src/scripts/academy-command-preferences.ts',
 'site/src/scripts/execution-map-navigation.ts',
 'site/src/scripts/guide-filter.ts',
 'site/src/scripts/workflow-atlas.ts',
 'tools/artifact-coverage.py',
 'tools/build-artifact-manifest-contract.py',
 'tools/build-artifacts.py',
 'tools/build-host-packages.py',
 'tools/build-surface.py',
 'tools/ci-impact.py',
 'tools/ci20_baseline.py',
 'tools/ci20_inventory.py',
 'tools/codex-parity-fixture.py',
 'tools/command_compatibility.py',
 'tools/create-artifact-examples.py',
 'tools/generate-artifact-types.py',
 'tools/go_test_parallel.py',
 'tools/host_descriptors.py',
 'tools/install-artifact-payload.py',
 'tools/live-smarts-exercise.py',
 'tools/measure-knowledge-retrieval.py',
 'tools/owned_output.py',
 'tools/promote-claude-marketplace.py',
 'tools/promote-codex-marketplace.py',
 'tools/statusline-bench.py',
 'tools/statusline-screenshot.py',
 'tools/sync-core.py',
 'tools/tribunal-eval.py'))
Q02_REQUIRED_SELECTORS = frozenset(('python:.github/scripts/test_major_readiness.py:__main__.CompletedPopulationTest.test_complete_population_does_not_reopen_resolved_history_prose',
 'python:.github/scripts/test_major_readiness.py:__main__.CompletedPopulationTest.test_complete_population_rejects_a_review_that_does_not_cover_the_row',
 'python:.github/scripts/test_major_readiness.py:__main__.CompletedPopulationTest.test_complete_population_rejects_missing_or_changed_raw_proof_and_inputs',
 'python:.github/scripts/test_major_readiness.py:__main__.CompletedPopulationTest.test_complete_reviewed_population_preserves_local_origin_and_non_circularity',
 'python:.github/scripts/test_major_readiness.py:__main__.CompletedPopulationTest.test_completed_metadata_does_not_clear_authoritative_confirmation',
 'python:.github/scripts/test_major_readiness.py:__main__.CompletedPopulationTest.test_existing_evidence_commit_does_not_make_an_unavailable_reference_valid',
 'python:.github/scripts/test_major_readiness.py:__main__.CompletedPopulationTest.test_preserved_rows_do_not_admit_a_nonexistent_evidence_commit',
 'python:.github/scripts/test_major_readiness.py:__main__.ProgramProducingGuardTest.test_finite_producer_catalog_does_not_require_unfinished_program_to_be_ready',
 'python:.github/scripts/test_major_readiness.py:__main__.ProgramProducingGuardTest.test_program_push_is_producing_only_and_publication_reader_stays_main_only',
 'python:.github/scripts/test_major_readiness.py:__main__.ReadinessTest.test_archive_members_reject_traversal_symlink_duplicates_and_empty',
 'python:.github/scripts/test_major_readiness.py:__main__.ReadinessTest.test_caller_pass_cannot_replace_successful_named_job',
 'python:.github/scripts/test_major_readiness.py:__main__.ReadinessTest.test_complete_frozen_population_receipt_fits_existing_json_bound',
 'python:.github/scripts/test_major_readiness.py:__main__.ReadinessTest.test_distributed_settlement_is_not_prepublication',
 'python:.github/scripts/test_major_readiness.py:__main__.ReadinessTest.test_exact_member_readback_is_required_by_live_verification',
 'python:.github/scripts/test_major_readiness.py:__main__.ReadinessTest.test_first_effect_gate_precedes_tag_and_keeps_pi_provenance_check',
 'python:.github/scripts/test_major_readiness.py:__main__.ReadinessTest.test_forged_untrusted_run_refuses',
 'python:.github/scripts/test_major_readiness.py:__main__.ReadinessTest.test_interned_report_payloads_preserve_exact_archive_and_member_admission',
 'python:.github/scripts/test_major_readiness.py:__main__.ReadinessTest.test_malformed_marker_is_not_an_ordinary_release_escape',
 'python:.github/scripts/test_major_readiness.py:__main__.ReadinessTest.test_matching_candidate_without_required_readiness_remains_pending',
 'python:.github/scripts/test_major_readiness.py:__main__.ReadinessTest.test_missing_expired_wrong_archive_refuses',
 'python:.github/scripts/test_major_readiness.py:__main__.ReadinessTest.test_producer_refuses_reports_without_the_named_jobs_upload_step',
 'python:.github/scripts/test_major_readiness.py:__main__.ReadinessTest.test_producer_requires_original_executed_reports',
 'python:.github/scripts/test_major_readiness.py:__main__.ReadinessTest.test_publication_task_cannot_enter_prepublication_population',
 'python:.github/scripts/test_major_readiness.py:__main__.ReadinessTest.test_receipt_only_does_not_repeat_publication',
 'python:.github/scripts/test_major_readiness.py:__main__.ReadinessTest.test_unfinished_program_cannot_produce_readiness',
 'python:.github/scripts/test_major_readiness.py:__main__.ReadinessTest.test_unknown_skipped_missing_duplicate_cells_refuse',
 'python:.github/scripts/test_major_readiness.py:__main__.ReadinessTest.test_unsettled_version_mismatch_never_bypasses_major_qualification',
 'python:.github/scripts/test_major_readiness.py:__main__.ReadinessTest.test_valid_receipt_is_non_circular',
 'python:.github/scripts/test_major_readiness.py:__main__.ReadinessTest.test_wrong_or_expired_payload_artifact_refuses',
 'python:.github/scripts/test_major_readiness.py:__main__.ReadinessTest.test_wrong_source_tree_run_and_manifests_refuse',
 'python:.github/scripts/test_major_readiness.py:__main__.UploadAttributionTest.test_another_jobs_artifact_or_different_digest_or_window_refuses',
 'python:.github/scripts/test_major_readiness.py:__main__.UploadAttributionTest.test_artifact_service_clock_offset_does_not_override_authenticated_step_log',
 'python:.github/scripts/test_major_readiness.py:__main__.UploadAttributionTest.test_exact_successful_upload_has_original_attribution',
 'python:.github/scripts/test_major_readiness.py:__main__.UploadAttributionTest.test_metadata_and_step_timestamps_still_require_wellformed_aware_values',
 'python:.github/scripts/test_major_readiness.py:__main__.UploadAttributionTest.test_original_actions_log_utf8_bom_is_accepted',
 'python:.github/scripts/test_major_readiness.py:__main__.UploadAttributionTest.test_report_name_and_json_job_id_do_not_replace_successful_upload_step',
 'python:.github/scripts/test_release_workflow.py:__main__.ConsumerSafetyGateTest.test_attached_package_reads_back_byte_identical',
 'python:.github/scripts/test_release_workflow.py:__main__.ConsumerSafetyGateTest.test_package_cohort_is_verified_before_anything_is_published',
 'python:.github/scripts/test_release_workflow.py:__main__.ConsumerSafetyGateTest.test_pi_publish_refuses_a_different_workflow_commit',
 'python:.github/scripts/test_release_workflow.py:__main__.ConsumerSafetyGateTest.test_receipt_is_written_after_the_release_is_public',
 'python:.github/scripts/test_release_workflow.py:__main__.ConsumerSafetyGateTest.test_release_goes_public_only_after_every_channel',
 'python:.github/scripts/test_release_workflow.py:__main__.IndependenceTest.test_each_release_job_gates_only_on_its_own_eligibility',
 'python:.github/scripts/test_release_workflow.py:__main__.IndependenceTest.test_each_release_job_serializes_only_with_itself',
 'python:.github/scripts/test_release_workflow.py:__main__.IndependenceTest.test_every_release_job_depends_only_on_the_preflight',
 'python:.github/scripts/test_release_workflow.py:__main__.IndependenceTest.test_one_targets_planning_error_does_not_block_the_others',
 'python:.github/scripts/test_release_workflow.py:__main__.ReceiptShellBoundaryTest.test_missing_receipt_is_uploaded_once_and_replay_only_reads',
 'python:.github/scripts/test_release_workflow.py:__main__.ReceiptShellBoundaryTest.test_same_named_wrong_receipt_is_downloaded_and_refused_without_overwrite',
 'python:.github/scripts/test_release_workflow.py:__main__.ReceiptShellBoundaryTest.test_uploaded_receipt_with_lost_response_is_observed_before_retry',
 'python:.github/scripts/test_release_workflow.py:__main__.SourceSelectionTest.test_workflow_run_event_binds_its_own_run',
 'python:.github/scripts/test_release_workflow.py:__main__.TriggerTest.test_dispatch_is_refused_off_the_default_branch',
 'python:.github/scripts/test_release_workflow.py:__main__.TriggerTest.test_each_run_releases_its_own_commit_from_its_own_manifests',
 'python:.github/scripts/test_release_workflow.py:__main__.TriggerTest.test_every_publisher_receives_the_selected_source_and_ci_run',
 'python:.github/scripts/test_release_workflow.py:__main__.TriggerTest.test_preflight_requires_a_successful_same_repo_main_push',
 'python:.github/scripts/test_release_workflow.py:__main__.TriggerTest.test_releases_follow_successful_main_ci_and_manual_retry'))


# Exact declarative W-F03 severity-policy composition; shared task links do
# not make this a model, whole-task or installed-host qualification.
HOOK_REVIEW_SOURCE_PROFILE = "hooks-finding-contracts-v1"
HOOK_REVIEW_SOURCE_JOB = SOURCE_JOB
HOOK_REVIEW_SOURCE_PAYLOAD = "major-source-inputs-hooks-findings-windows-contracts"
HOOK_REVIEW_SOURCE_UPLOAD = "Upload hook finding source-test inputs"
HOOK_REVIEW_SOURCE_SCRIPT = ".github/scripts/test_review_funnel.py"
HOOK_REVIEW_SOURCE_PATHS = SOURCE_PATHS | frozenset(['.github/major-qualification-policy.json', '.github/major-test-selections.json', '.github/scripts/test_hook_ci_partition.py', '.github/scripts/test_review_funnel.py', '.github/workflows/ci.yml', 'docs/state-contracts-major/PROGRAM.md', 'docs/state-contracts-major/contracts/decisions.json', 'docs/state-contracts-major/contracts/finding-dispositions.json', 'docs/state-contracts-major/contracts/tasks.json', 'plugins/ca-codex/agents/INDEX.md', 'plugins/ca-codex/agents/architecture-drift-reviewer.md', 'plugins/ca-codex/agents/auth-crypto-reviewer.md', 'plugins/ca-codex/agents/backend-author.md', 'plugins/ca-codex/agents/checkpoint-aggregator.md', 'plugins/ca-codex/agents/coverage-auditor.md', 'plugins/ca-codex/agents/decision-challenger.md', 'plugins/ca-codex/agents/dependency-reviewer.md', 'plugins/ca-codex/agents/design-quality-reviewer.md', 'plugins/ca-codex/agents/finding-triage.md', 'plugins/ca-codex/agents/frontend-author.md', 'plugins/ca-codex/agents/grader.md', 'plugins/ca-codex/agents/infra-author.md', 'plugins/ca-codex/agents/map-deps.md', 'plugins/ca-codex/agents/map-structure.md', 'plugins/ca-codex/agents/migration-reviewer.md', 'plugins/ca-codex/agents/scout.md', 'plugins/ca-codex/agents/security-reviewer.md', 'plugins/ca-codex/agents/tribunal-lens-reviewer.md', 'plugins/ca-codex/agents/verdict-aggregator.md', 'plugins/ca-codex/includes/reviewer-contract.md', 'plugins/ca-pi/agents/INDEX.md', 'plugins/ca-pi/agents/architecture-drift-reviewer.md', 'plugins/ca-pi/agents/auth-crypto-reviewer.md', 'plugins/ca-pi/agents/backend-author.md', 'plugins/ca-pi/agents/checkpoint-aggregator.md', 'plugins/ca-pi/agents/coverage-auditor.md', 'plugins/ca-pi/agents/decision-challenger.md', 'plugins/ca-pi/agents/dependency-reviewer.md', 'plugins/ca-pi/agents/design-quality-reviewer.md', 'plugins/ca-pi/agents/finding-triage.md', 'plugins/ca-pi/agents/frontend-author.md', 'plugins/ca-pi/agents/grader.md', 'plugins/ca-pi/agents/infra-author.md', 'plugins/ca-pi/agents/map-deps.md', 'plugins/ca-pi/agents/map-structure.md', 'plugins/ca-pi/agents/migration-reviewer.md', 'plugins/ca-pi/agents/scout.md', 'plugins/ca-pi/agents/security-reviewer.md', 'plugins/ca-pi/agents/tribunal-lens-reviewer.md', 'plugins/ca-pi/agents/verdict-aggregator.md', 'plugins/ca-pi/includes/reviewer-contract.md', 'plugins/ca/agents/INDEX.md', 'plugins/ca/agents/architecture-drift-reviewer.md', 'plugins/ca/agents/auth-crypto-reviewer.md', 'plugins/ca/agents/authority-reviewer.md', 'plugins/ca/agents/backend-author.md', 'plugins/ca/agents/checkpoint-aggregator.md', 'plugins/ca/agents/coverage-auditor.md', 'plugins/ca/agents/decision-challenger.md', 'plugins/ca/agents/dependency-reviewer.md', 'plugins/ca/agents/design-quality-reviewer.md', 'plugins/ca/agents/finding-triage.md', 'plugins/ca/agents/frontend-author.md', 'plugins/ca/agents/grader.md', 'plugins/ca/agents/infra-author.md', 'plugins/ca/agents/map-deps.md', 'plugins/ca/agents/map-structure.md', 'plugins/ca/agents/migration-reviewer.md', 'plugins/ca/agents/scout.md', 'plugins/ca/agents/security-reviewer.md', 'plugins/ca/agents/tribunal-lens-reviewer.md', 'plugins/ca/agents/verdict-aggregator.md', 'plugins/ca/includes/reviewer-contract.md', 'site/src/curated/commands/review.md'])
HOOK_REVIEW_REQUIRED_SELECTORS = frozenset(['python:.github/scripts/test_review_funnel.py:__main__.ReadOnlyReviewFunnelTest.test_author_collection_does_not_invoke_review_verdict', 'python:.github/scripts/test_review_funnel.py:__main__.ReadOnlyReviewFunnelTest.test_checkpoint_persistence_is_explicit_and_non_overwriting', 'python:.github/scripts/test_review_funnel.py:__main__.ReadOnlyReviewFunnelTest.test_checkpoint_writer_reports_the_selected_dated_filename', 'python:.github/scripts/test_review_funnel.py:__main__.ReadOnlyReviewFunnelTest.test_curated_review_projection_uses_the_read_only_terminal', 'python:.github/scripts/test_review_funnel.py:__main__.ReadOnlyReviewFunnelTest.test_dispatch_contract_uses_canonical_routes_and_preserves_findings', 'python:.github/scripts/test_review_funnel.py:__main__.ReadOnlyReviewFunnelTest.test_inbound_pr_review_route_is_byte_invariant', 'python:.github/scripts/test_review_funnel.py:__main__.ReadOnlyReviewFunnelTest.test_triage_requires_the_complete_batch_contract', 'python:.github/scripts/test_review_funnel.py:__main__.ReadOnlyReviewFunnelTest.test_verdict_has_unambiguous_incomplete_precedence_and_schema', 'python:.github/scripts/test_review_funnel.py:__main__.ReadOnlyReviewFunnelTest.test_working_diff_review_route_is_byte_invariant', 'python:.github/scripts/test_review_funnel.py:__main__.SeverityDispositionPolicyTest.test_dependency_owner_assigns_medium_to_maintenance_only', 'python:.github/scripts/test_review_funnel.py:__main__.SeverityDispositionPolicyTest.test_index_blocks_column_matches_owner_severities', 'python:.github/scripts/test_review_funnel.py:__main__.SeverityDispositionPolicyTest.test_no_reviewer_body_declares_a_non_blocking_high', 'python:.github/scripts/test_review_funnel.py:__main__.SeverityDispositionPolicyTest.test_security_highs_block_in_the_dependency_owner', 'python:.github/scripts/test_review_funnel.py:__main__.SeverityDispositionPolicyTest.test_shared_contract_states_one_rule_and_the_single_exception', 'python:.github/scripts/test_review_funnel.py:__main__.SeverityDispositionPolicyTest.test_triage_never_conditions_high_blocking'])
HOOK_REVIEW_FINDING_SELECTORS = frozenset(['python:.github/scripts/test_review_funnel.py:__main__.SeverityDispositionPolicyTest.test_dependency_owner_assigns_medium_to_maintenance_only', 'python:.github/scripts/test_review_funnel.py:__main__.SeverityDispositionPolicyTest.test_index_blocks_column_matches_owner_severities', 'python:.github/scripts/test_review_funnel.py:__main__.SeverityDispositionPolicyTest.test_no_reviewer_body_declares_a_non_blocking_high', 'python:.github/scripts/test_review_funnel.py:__main__.SeverityDispositionPolicyTest.test_security_highs_block_in_the_dependency_owner', 'python:.github/scripts/test_review_funnel.py:__main__.SeverityDispositionPolicyTest.test_shared_contract_states_one_rule_and_the_single_exception', 'python:.github/scripts/test_review_funnel.py:__main__.SeverityDispositionPolicyTest.test_triage_never_conditions_high_blocking'])
HOOK_REVIEW_FINDING_CELL = "disposition:findings:W-F03"


def _hook_review_python_command(argv):
    require(isinstance(argv, list) and len(argv) == 2 and all(type(v) is str and v for v in argv)
            and (argv[1].replace("\\", "/") == HOOK_REVIEW_SOURCE_SCRIPT
                 or argv[1].replace("\\", "/").endswith("/" + HOOK_REVIEW_SOURCE_SCRIPT)),
            "hook review profile requires its original unfiltered Python entry point")


def _hook_review_members(repo):
    for tree in ("core/surface", "plugins/ca", "plugins/ca-codex", "plugins/ca-pi"):
        folder = Path(repo) / tree / "agents"
        info = folder.lstat()
        require(stat.S_ISDIR(info.st_mode) and not folder.is_symlink()
                and not getattr(info, "st_file_attributes", 0) & stat.FILE_ATTRIBUTE_REPARSE_POINT,
                "hook review agent directory is unsafe")
        actual = {p.relative_to(repo).as_posix() for p in folder.glob("*.md")}
        expected = {p for p in HOOK_REVIEW_SOURCE_PATHS if p.startswith(tree + "/agents/")}
        require(actual == expected, "hook review agent inventory differs")


def _q02_python_command(argv):
    require(isinstance(argv, list) and len(argv) == 2 and all(type(v) is str and v for v in argv)
            and any(argv[1].replace("\\", "/") == script or argv[1].replace("\\", "/").endswith("/" + script)
                    for script in Q02_SOURCE_SCRIPTS),
            "Q02 source profile requires an original unfiltered owning Python entry point")


def source_profile(profile=SOURCE_PROFILE):
    if profile == SOURCE_PROFILE:
        return {"paths": SOURCE_PATHS, "job": SOURCE_JOB, "payload": SOURCE_PAYLOAD, "upload": SOURCE_UPLOAD}
    if profile == SDK_SOURCE_PROFILE:
        return {"paths": SDK_SOURCE_PATHS, "job": SDK_SOURCE_JOB, "payload": SDK_SOURCE_PAYLOAD, "upload": SDK_SOURCE_UPLOAD}
    if profile == HOOK_REVIEW_SOURCE_PROFILE:
        return {"paths": HOOK_REVIEW_SOURCE_PATHS, "job": HOOK_REVIEW_SOURCE_JOB, "payload": HOOK_REVIEW_SOURCE_PAYLOAD, "upload": HOOK_REVIEW_SOURCE_UPLOAD}
    if profile == Q02_SOURCE_PROFILE:
        return {"paths": Q02_SOURCE_PATHS, "job": Q02_SOURCE_JOB, "payload": Q02_SOURCE_PAYLOAD, "upload": Q02_SOURCE_UPLOAD}
    require(type(profile) is str and profile in TS_PROFILE_PATHS, "unknown source input profile")
    return {"paths": TS_PROFILE_PATHS[profile], "job": TS_PROFILE_JOBS[profile],
            "payload": TS_PROFILE_PAYLOADS[profile], "upload": TS_PROFILE_UPLOADS[profile], "root": TS_PROFILE_ROOTS[profile]}


def _ts_members(repo, profile):
    root = Path(repo) / TS_PROFILE_ROOTS[profile]
    found, pending, count = set(), [root], 0
    while pending:
        folder = pending.pop(); count += 1
        info = folder.lstat()
        require(count <= 512 and stat.S_ISDIR(info.st_mode) and not folder.is_symlink()
                and not getattr(info, "st_file_attributes", 0) & stat.FILE_ATTRIBUTE_REPARSE_POINT,
                "source profile namespace is unsafe or unbounded")
        for path in folder.iterdir():
            if folder == root and path.name in ("node_modules", "coverage", ".vitest-reports"):
                continue  # Declared third-party/runtime outputs, never claimed as captured source.
            if folder == root and profile == "pi-tools-v1" and path.name == "coverage-inputs":
                _pi_output_members(repo)
                continue
            info = path.lstat()
            require(not path.is_symlink() and not getattr(info, "st_file_attributes", 0) & stat.FILE_ATTRIBUTE_REPARSE_POINT,
                    "source profile namespace contains a link")
            if stat.S_ISDIR(info.st_mode): pending.append(path)
            else:
                require(stat.S_ISREG(info.st_mode), "source profile namespace contains nonregular data")
                found.add(path.relative_to(repo).as_posix())
                require(len(found) <= 2048, "source profile namespace exceeds bound")
    require(found == {p for p in TS_PROFILE_PATHS[profile] if p.startswith(TS_PROFILE_ROOTS[profile] + "/")},
            "source profile physical membership differs")


def _pi_output_members(repo):
    folder = Path(repo) / "plugins/ca-pi/tools/coverage-inputs"
    if not folder.exists() and not folder.is_symlink(): return set()
    info = folder.lstat()
    require(stat.S_ISDIR(info.st_mode) and not folder.is_symlink()
            and not getattr(info, "st_file_attributes", 0) & stat.FILE_ATTRIBUTE_REPARSE_POINT,
            "Pi coverage output directory is unsafe")
    names = set()
    for path in folder.iterdir():
        info = path.lstat()
        require(path.name in TS_OUTPUT_NAMES and stat.S_ISREG(info.st_mode) and info.st_nlink == 1
                and not path.is_symlink() and not getattr(info, "st_file_attributes", 0) & stat.FILE_ATTRIBUTE_REPARSE_POINT
                and info.st_size <= MAX_JSON, "foreign or unsafe Pi coverage output")
        names.add(path.relative_to(repo).as_posix())
    return names



def _source_file(repo, relative, paths=None):
    paths = SOURCE_PATHS if paths is None else paths
    require(relative in paths, "source payload path outside fixed profile")
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


def _source_byte_mismatch(relative, expected, actual):
    # Do not decode source content or forward arbitrary paths/metadata. This
    # diagnostic describes only one bounded member of a closed source profile.
    require(type(relative) is str and (relative in SOURCE_PATHS or relative in SDK_SOURCE_PATHS or relative in Q02_SOURCE_PATHS or relative in HOOK_REVIEW_SOURCE_PATHS
            or any(relative in paths for paths in TS_PROFILE_PATHS.values())),
            "byte mismatch diagnostic member is outside fixed profiles")
    require(type(expected) is bytes and type(actual) is bytes
            and len(expected) <= 8 * 1024 * 1024 and len(actual) <= 8 * 1024 * 1024,
            "byte mismatch diagnostic requires bounded source bytes")
    def summary(value):
        crlf = value.count(b"\r\n")
        return {"sha256": readiness.digest(value), "bytes": len(value),
                "lf": value.count(b"\n") - crlf, "crlf": crlf,
                "cr": value.count(b"\r") - crlf}
    record = {"format": "codearbiter.source-input-byte-mismatch/1",
              "member_sha256": readiness.digest(relative.encode("utf-8")),
              "expected": summary(expected), "actual": summary(actual)}
    return "source payload physical bytes differ from Git: " + json.dumps(record, sort_keys=True, separators=(",", ":"))


def source_input_snapshot(repo, profile=SOURCE_PROFILE):
    repo = Path(repo).resolve(strict=True)
    spec = source_profile(profile)
    paths = spec["paths"]
    identity = source_identity(repo, profile)
    require(identity["clean"], "source payload checkout is not clean")
    if profile == HOOK_REVIEW_SOURCE_PROFILE:
        _source_root_members(repo)
        _hook_review_members(repo)
    elif profile in (SOURCE_PROFILE, Q02_SOURCE_PROFILE): _source_root_members(repo)
    elif profile == SDK_SOURCE_PROFILE: _sdk_source_members(repo)
    else: _ts_members(repo, profile)
    rows = git(repo, "ls-tree", "-rz", "--full-tree", identity["source_commit"], "--", *sorted(paths), raw=True)
    entries = []
    for row in rows.split(b"\0"):
        if not row: continue
        header, relative = row.split(b"\t", 1)
        mode, kind, blob = header.decode("ascii").split()
        relative = relative.decode("utf-8")
        require(relative in paths and kind == "blob" and mode in ("100644", "100755")
                and readiness.SHA.fullmatch(blob), "source payload immutable member invalid")
        entries.append((relative, mode, blob))
    require(len(entries) == len(paths) and len({p for p, _, _ in entries}) == len(paths),
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
        actual = _source_file(repo, relative, paths)
        if actual != value:
            raise ValueError(_source_byte_mismatch(relative, value, actual))
        total += size
        require(total <= 64 * 1024 * 1024, "source payload total exceeds bound")
        members.append({"path": relative, "sha256": readiness.digest(value), "bytes": size, "git_mode": mode})
    require(cursor == len(batch), "source payload has trailing blob data")
    return {**identity, "members": sorted(members, key=lambda item: item["path"])}


def validate_source_manifest(record, req, job_name, members):
    spec = source_profile(record.get("profile") if isinstance(record, dict) else None)
    paths = spec["paths"]
    fields = {"format", "profile", "source_commit", "source_tree", "workflow", "ci_run_id", "producer_job_name", "members"}
    require(isinstance(record, dict) and set(record) == fields and record["format"] == SOURCE_FORMAT
            and record["profile"] in (SOURCE_PROFILE, SDK_SOURCE_PROFILE, Q02_SOURCE_PROFILE, HOOK_REVIEW_SOURCE_PROFILE, *TS_PROFILE_PATHS) and record["workflow"] == ".github/workflows/ci.yml"
            and job_name == record["producer_job_name"] == spec["job"]
            and type(record["source_commit"]) is str and record["source_commit"] == req["source_commit"] and readiness.SHA.fullmatch(record["source_commit"])
            and type(record["source_tree"]) is str and record["source_tree"] == req["source_tree"] and readiness.SHA.fullmatch(record["source_tree"])
            and type(record["ci_run_id"]) is int and record["ci_run_id"] == req["ci_run_id"] > 0,
            "source payload manifest identity differs")
    rows = record["members"]
    require(isinstance(rows, list) and len(rows) == len(paths), "source payload manifest population differs")
    require(all(isinstance(row, dict) and set(row) == {"path", "sha256", "bytes", "git_mode"}
                and type(row["path"]) is str and row["path"] in paths
                and type(row["sha256"]) is str and readiness.DIGEST.fullmatch(row["sha256"])
                and type(row["bytes"]) is int and 0 <= row["bytes"] <= 8 * 1024 * 1024
                and row["git_mode"] in ("100644", "100755") for row in rows), "source payload manifest member invalid")
    require([row["path"] for row in rows] == sorted(paths)
            and sum(row["bytes"] for row in rows) <= 64 * 1024 * 1024, "source payload manifest membership differs")
    expected = {row["path"]: row["sha256"] for row in rows}
    actual = {row["path"]: row["sha256"] for row in members}
    require(len(actual) == len(members) and set(actual) == paths | {SOURCE_MANIFEST}
            and all(actual[path] == value for path, value in expected.items()), "source payload archive membership differs")
    return record


def prepare_source_payload(repo, output, job_name, profile=SOURCE_PROFILE):
    spec = source_profile(profile)
    require(job_name == spec["job"], "source payload owner differs")
    repo = Path(repo).resolve(strict=True); output = Path(output).absolute()
    output = output.parent.resolve(strict=True) / output.name
    require(not output.exists() and not output.is_symlink() and not output.is_relative_to(repo),
            "new external source payload directory required")
    before = source_input_snapshot(repo, profile)
    output.mkdir()
    for row in before["members"]:
        value = _source_file(repo, row["path"], spec["paths"])
        require(readiness.digest(value) == row["sha256"], "source payload changed before staging")
        target = output / row["path"]; target.parent.mkdir(parents=True, exist_ok=True)
        with target.open("xb") as stream: stream.write(value)
    record = {"format": SOURCE_FORMAT, "profile": profile,
        "source_commit": before["source_commit"], "source_tree": before["source_tree"],
        "workflow": ".github/workflows/ci.yml", "ci_run_id": int(os.environ.get("GITHUB_RUN_ID", "0")),
        "producer_job_name": job_name, "members": before["members"]}
    require(record["ci_run_id"] > 0 and source_input_snapshot(repo, profile) == before, "source payload staging source changed")
    new_output(output / SOURCE_MANIFEST, record)
    return record


def source_observation_binding(repo, staged, identity, profile=SOURCE_PROFILE):
    spec = source_profile(profile)
    staged = Path(staged)
    info = staged.lstat()
    require(stat.S_ISDIR(info.st_mode) and not staged.is_symlink()
            and not getattr(info, "st_file_attributes", 0) & stat.FILE_ATTRIBUTE_REPARSE_POINT,
            "source payload stage is not an ordinary directory")
    staged = staged.resolve(strict=True)
    require(not staged.is_relative_to(Path(repo).resolve()), "source payload must be outside source")
    record = load_json(staged / SOURCE_MANIFEST)
    require(record.get("profile") == profile, "source payload profile differs from original invocation")
    snapshot = source_input_snapshot(repo, profile)
    require(all(snapshot[key] == identity[key] for key in ("source_commit", "source_tree", "clean")),
            "source payload observation source changed")
    members = [{"path": row["path"], "sha256": row["sha256"]} for row in snapshot["members"]]
    raw = (staged / SOURCE_MANIFEST).read_bytes()
    require(len(raw) <= 1024 * 1024, "source payload manifest exceeds bound")
    members.append({"path": SOURCE_MANIFEST, "sha256": readiness.digest(raw)})
    validate_source_manifest(record, {**identity, "ci_run_id": int(os.environ.get("GITHUB_RUN_ID", "0"))}, spec["job"], members)
    require(record["members"] == snapshot["members"], "source payload observation members changed")
    actual, pending = set(), [staged]
    permitted = spec["paths"] | {SOURCE_MANIFEST}
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
    require(actual == permitted, "source payload stage contains extra/missing files")
    for row in record["members"]:
        require(readiness.digest(_source_file(staged, row["path"], spec["paths"])) == row["sha256"], "source payload staged bytes differ")
    return {"format": SOURCE_BINDING, "profile": profile,
            "payload_name": spec["payload"], "manifest_sha256": readiness.digest(raw)}


def admit_source_observation(observed, payload, req, job_name, job_id):
    binding = observed.get("source_input_binding")
    spec = source_profile(binding.get("profile") if isinstance(binding, dict) else None)
    require(isinstance(binding, dict) and set(binding) == {"format", "profile", "payload_name", "manifest_sha256"}
            and binding["format"] == SOURCE_BINDING and binding["profile"] in (SOURCE_PROFILE, SDK_SOURCE_PROFILE, Q02_SOURCE_PROFILE, HOOK_REVIEW_SOURCE_PROFILE, *TS_PROFILE_PATHS)
            and binding["payload_name"] == spec["payload"]
            and binding["manifest_sha256"] == payload.get("source_manifest_sha256")
            and type(payload.get("source_upload_job_id")) is int and payload.get("source_upload_job_id") == job_id,
            "source test payload binding missing or differs")
    if binding["profile"] == HOOK_REVIEW_SOURCE_PROFILE:
        require(observed.get("producer") == "python-test-result-observer", "hook review profile requires original Python observer")
        _hook_review_python_command(observed.get("argv"))
    elif binding["profile"] == Q02_SOURCE_PROFILE:
        require(observed.get("producer") == "python-test-result-observer", "Q02 source profile requires original Python observer")
        _q02_python_command(observed.get("argv"))
    elif binding["profile"] == SDK_SOURCE_PROFILE:
        require(observed.get("producer") == "python-test-result-observer", "SDK source profile requires original Python observer")
        _sdk_python_command(observed.get("argv"))
    elif binding["profile"] != SOURCE_PROFILE:
        require(observed.get("producer") == "vitest-json-observer", "TS source profile requires original Vitest observer")
    record = payload.get("documents", {}).get(SOURCE_MANIFEST)
    validate_source_manifest(record, req, job_name, payload.get("members", []))
    require(next(row["sha256"] for row in payload["members"] if row["path"] == SOURCE_MANIFEST)
            == binding["manifest_sha256"], "source test manifest digest differs")


def observe_python(repo, script, arguments, output, source_payload=None, profile=SOURCE_PROFILE):
    """Run the original Python entry point once, observing actual TestResult calls."""
    repo = Path(repo).resolve(strict=True)
    script = (repo / script).resolve(strict=True)
    relative = script.relative_to(repo).as_posix()
    require(script.suffix == ".py" and not Path(output).exists() and not Path(output).is_symlink(),
            "new Python observation required")
    source_profile(profile)
    if profile == HOOK_REVIEW_SOURCE_PROFILE:
        require(relative == HOOK_REVIEW_SOURCE_SCRIPT and arguments == [] and source_payload is not None,
                "hook review profile requires its original unfiltered Python entry point and payload")
    elif profile == Q02_SOURCE_PROFILE:
        require(relative in Q02_SOURCE_SCRIPTS and arguments == [] and source_payload is not None,
                "Q02 source profile requires its original unfiltered Python entry point and payload")
    elif profile == SDK_SOURCE_PROFILE:
        require(relative == SDK_SOURCE_SCRIPT and arguments == [] and source_payload is not None,
                "SDK source profile requires its original unfiltered Python entry point and payload")
    else:
        require(profile == SOURCE_PROFILE, "Python observer requires a closed Python source profile")
    before = source_identity(repo, profile)
    source_binding = source_observation_binding(repo, source_payload, before, profile) if source_payload else None
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
    after = source_identity(repo, profile)
    stable = before == after and before["clean"]
    if source_payload:
        try:
            stable = stable and source_observation_binding(repo, source_payload, after, profile) == source_binding
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
    children = record.get("subtests", [])
    require(isinstance(children, list) and len(children) + len(selected) <= MAX_TESTS,
            "native child population exceeds bound")
    child_names = set()
    for child in children:
        require(isinstance(child, dict) and set(child) == {"package", "test", "result"}
                and isinstance(child["package"], str) and isinstance(child["test"], str)
                and "/" in child["test"] and len(child["test"].encode("utf-8")) <= 4096
                and (child["package"], child["test"].split("/", 1)[0]) in selected
                and child["result"] in ("pass", "skip"), "invalid native child outcome")
        identity = (child["package"], child["test"])
        require(identity not in child_names, "repeated native child outcome")
        child_names.add(identity)
    return {"format": OBSERVATION, "source_commit": binding["source_commit"],
            "source_tree": source_tree, "source_stable": True, "ci_run_id": int(binding["run_id"]),
            "proof_kind": "native-module", "producer": "go-named-ci20-join",
            "native_binding": binding, "argv": record["argv"], "exit_code": 0,
            "tests": [{"id": "go:" + r["package"] + ":" + r["test"],
                       "result": "passed" if r["result"] == "pass" else "skipped"}
                      for r in [*record["observed"], *children]]}


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
                    and 0 < len(case["fullName"].encode("utf-8")) <= MAX_TEST_ID_BYTES
                    and isinstance(case.get("status"), str) and len(rows) < MAX_TESTS,
                    "malformed or unbounded Vitest named outcome")
            state = {"passed": "passed", "failed": "failed", "pending": "skipped",
                     "skipped": "skipped", "todo": "skipped", "disabled": "skipped"}.get(case["status"])
            require(state is not None, "unknown Vitest outcome")
            identity = "vitest:" + path + ":" + case["fullName"]
            require(len(identity.encode("utf-8")) <= MAX_TEST_ID_BYTES,
                    "Vitest complete named identity exceeds canonical bound")
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


def _vitest_runtime_file(path):
    declared = Path(path).absolute()
    resolved = declared.resolve(strict=True)  # npm's ordinary POSIX alias is recorded, never hashed as a symlink.
    info = resolved.lstat()
    require(stat.S_ISREG(info.st_mode) and info.st_size <= 128 * 1024 * 1024
            and not resolved.is_symlink() and not getattr(info, "st_file_attributes", 0) & stat.FILE_ATTRIBUTE_REPARSE_POINT,
            "Vitest launch input is not bounded regular data")
    digest = hashlib.sha256(); total = 0
    with resolved.open("rb") as stream:
        opened = os.fstat(stream.fileno())
        require((opened.st_dev, opened.st_ino) == (info.st_dev, info.st_ino), "Vitest launch input changed before read")
        while chunk := stream.read(1024 * 1024):
            total += len(chunk)
            require(total <= 128 * 1024 * 1024, "Vitest launch input exceeds bound")
            digest.update(chunk)
        after = os.fstat(stream.fileno())
    require((info.st_dev, info.st_ino, info.st_size, info.st_mtime_ns)
            == (after.st_dev, after.st_ino, after.st_size, after.st_mtime_ns)
            and declared.resolve(strict=True) == resolved, "Vitest launch input changed during read")
    return {"path": str(declared), "resolved_path": str(resolved), "bytes": total,
            "sha256": digest.hexdigest(), "filesystem_id": str(info.st_dev) + ":" + str(info.st_ino)}


def _vitest_launch(command):
    executable = shutil.which(command[0])
    require(executable, "original Vitest executable unavailable")
    executable = Path(executable).absolute()
    paths = [executable]
    if os.name == "nt" and executable.suffix.casefold() in (".cmd", ".bat"):
        from _artifactauthoritylib import _native_launch
        require(executable.name.casefold() in ("npm.cmd", "npx.cmd"), "unsupported Vitest batch launcher")
        npm = executable.with_name("npm.cmd")
        launch, bound = _native_launch(npm, list(command[1:]))
        paths.extend(Path(row["path"]) for row in bound)
        if executable.name.casefold() == "npx.cmd":
            # Reuse HW04's qualified npm wrapper, changing only its closed sibling entry.
            expected = npm.read_text(encoding="utf-8").replace("NPM_PREFIX_NPM_CLI_JS", "NPM_PREFIX_NPX_CLI_JS")
            expected = expected.replace("NPM_CLI_JS", "NPX_CLI_JS").replace("npm-cli.js", "npx-cli.js")
            require([line for line in executable.read_text(encoding="utf-8").splitlines() if line]
                    == [line for line in expected.splitlines() if line], "unqualified npx wrapper")
            entry = Path(launch[1]).with_name("npx-cli.js")
            paths.append(entry); launch[1] = str(entry)
    else:
        launch = [str(executable.resolve(strict=True)), *command[1:]]
    records = [_vitest_runtime_file(path) for path in dict.fromkeys(paths)]
    return launch, records


def _vitest_environment(root):
    env = local_read_git_env()
    for key in ("CI", "GITHUB_ACTIONS", "GITHUB_WORKSPACE", "GITHUB_RUN_ID", "GITHUB_RUN_ATTEMPT",
                "CA_SANDBOX_REQUIRE_DOCKER", "CA_SANDBOX_DOCKER_SENTINEL", "NAPI_RS_FORCE_WASI"):
        if key in os.environ: env[key] = os.environ[key]
    for name in ("home", "appdata", "localappdata", "tmp", "cache", "config", "pycache"):
        (root / name).mkdir()
    (root / "empty-user.npmrc").write_bytes(b"")
    (root / "empty-global.npmrc").write_bytes(b"")
    env.update(HOME=str(root / "home"), USERPROFILE=str(root / "home"), APPDATA=str(root / "appdata"),
        LOCALAPPDATA=str(root / "localappdata"), TEMP=str(root / "tmp"), TMP=str(root / "tmp"), TMPDIR=str(root / "tmp"),
        XDG_CACHE_HOME=str(root / "cache"), XDG_CONFIG_HOME=str(root / "config"),
        PYTHONNOUSERSITE="1", PYTHONDONTWRITEBYTECODE="1", PYTHONPYCACHEPREFIX=str(root / "pycache"),
        GIT_CONFIG_GLOBAL=os.devnull, GIT_CONFIG_NOSYSTEM="1", NPM_CONFIG_USERCONFIG=str(root / "empty-user.npmrc"),
        NPM_CONFIG_GLOBALCONFIG=str(root / "empty-global.npmrc"), NPM_CONFIG_CACHE=str(root / "cache"))
    env.pop("HOMEDRIVE", None); env.pop("HOMEPATH", None)
    return env


def observe_vitest(repo, arguments, raw_results, output, execution_cwd=None, source_payload=None):
    """Observe one original invocation, preserving its reporters and project cwd."""
    require(arguments and raw_results and output, "Vitest invocation and new outputs required")
    repo = Path(repo).resolve(strict=True)
    cwd = _vitest_cwd(repo, execution_cwd)
    raw_results, raw_parent = _vitest_new_path(raw_results)
    output, observation_parent = _vitest_new_path(output)
    require(raw_results != output, "result and observation output ownership conflict")
    command = _vitest_command(arguments, raw_results, cwd)
    profile = load_json(Path(source_payload) / SOURCE_MANIFEST).get("profile") if source_payload else None
    if source_payload:
        spec = source_profile(profile)
        require(profile in TS_PROFILE_PATHS and cwd == repo / spec["root"], "TS source profile requires its original project cwd")
    before = source_identity(repo, profile)
    source_binding = source_observation_binding(repo, source_payload, before, profile) if source_payload else None
    raw_before = git(repo, "status", "--porcelain=v1", "--untracked-files=all", "-z", raw=True) if source_payload else None
    launch, runtime = _vitest_launch(command) if source_payload else (command, None)
    descriptor = os.open(raw_results, os.O_RDWR | os.O_CREAT | os.O_EXCL | getattr(os, "O_BINARY", 0)
                         | getattr(os, "O_NOFOLLOW", 0), 0o600)
    with ExitStack() as stack:
        try:
            original = os.fstat(descriptor)
            if source_payload:
                # Capturing reports on another volume must not change the
                # original suite's temp-filesystem capabilities (for example
                # Windows short aliases). Keep a fresh private ambient temp
                # root; report files retain their independent ownership checks.
                private = Path(stack.enter_context(tempfile.TemporaryDirectory(prefix="ca-vitest-profile-"))).resolve(strict=True)
                process = start_process(launch, cwd=cwd, env=_vitest_environment(private))
            else:
                process = start_process(command, cwd=cwd)
            try:
                code = process.wait(timeout=1200)
            except subprocess.TimeoutExpired:
                containment = terminate_tree(process)
                raise ValueError("original Vitest run timed out; containment=" + containment) from None
            if source_payload:
                try:
                    after = source_identity(repo, profile)
                    stable = before == after and before["clean"]
                    stable = stable and source_observation_binding(repo, source_payload, after, profile) == source_binding
                    stable = stable and [_vitest_runtime_file(row["path"]) for row in runtime] == runtime
                except (OSError, ValueError, KeyError, TypeError, subprocess.SubprocessError):
                    after = None
                    stable = False
            else:
                after = source_identity(repo)
                stable = before == after and before["clean"]
            require(all((path.parent.stat().st_dev, path.parent.stat().st_ino) == expected
                        for path, expected in ((raw_results, raw_parent), (output, observation_parent))),
                    "Vitest output parent changed")
            record, raw_digest = _vitest_owned_json(raw_results, descriptor, original)
            document = admit_vitest(record, repo=repo, before=before, after=after,
                                    argv=command, exit_code=code, run_id=int(os.environ.get("GITHUB_RUN_ID", "0")))
            document.update(original_argv=list(arguments), cwd=str(cwd), raw_results_sha256=raw_digest)
            if source_payload:
                document.update(source_stable=stable, source_input_binding=source_binding, launch_argv=launch,
                    launch_inputs=runtime, runtime_scope="Selected launch inputs only; ignored third-party graph and installed host bytes are not attested.",
                    raw_worktree_status_before_sha256=readiness.digest(raw_before),
                    raw_worktree_status_after_sha256=readiness.digest(git(repo, "status", "--porcelain=v1", "--untracked-files=all", "-z", raw=True)))
            new_output(output, document)
            return code if not source_payload or stable else 1
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
                 producer_job=None, runtime_acquisitions=None, native_components=None):
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
    if "task:Q-02" in expected:
        q02_groups = [g for g in selected_groups if "task:Q-02" in g["cells"]]
        require(all(g["proof_kind"] == "source-test" and g["payload_name"] == Q02_SOURCE_PAYLOAD for g in q02_groups),
                "Q02 implementation requires original source observations")
        require({selector for g in q02_groups for selector in g["selectors"]} == Q02_REQUIRED_SELECTORS,
                "Q02 implementation requires the complete original readiness and publication guard union")
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
            elif (group["proof_kind"] == "source-test"
                  and observed.get("producer") == "python-mapped-native-consumer-observer-v1"):
                from mapped_work_observation import admit, CELL, SOURCE_PAYLOAD, JOB
                require(cell == CELL and set(group["cells"]) == {CELL}
                        and group["payload_name"] == SOURCE_PAYLOAD and job_name == JOB,
                        "mapped native consumer cannot qualify another cell or job")
                if group["observation"] not in installed_admissions:
                    installed_admissions[group["observation"]] = admit(
                        observed, req=req, job_id=job_id, authenticated_payloads=payloads, repo=ROOT,
                        native_component=(native_components or {}).get(group["observation"]))
                admitted = installed_admissions[group["observation"]]
                require(admitted["tests"] == observed.get("tests") and cell in admitted["qualified_cells"]
                        and admitted["primary_payload_name"] == group["payload_name"],
                        "mapped native consumer outcomes or finite scope differ")
                for item in admitted["payloads"]:
                    installed_payloads[item["artifact_id"]] = item
                dual_payload_report = True
            else:
                require(observed.get("producer") in producers.get(group["proof_kind"], ()),
                        "no qualified observer for this proof kind")
            if (group["proof_kind"] == "source-test"
                    and observed.get("producer") != "python-mapped-native-consumer-observer-v1"):
                binding = observed.get("source_input_binding")
                require(isinstance(binding, dict), "source input binding is missing")
                profile = binding.get("profile") if isinstance(binding, dict) else None
                spec = source_profile(profile)
                require(group["payload_name"] == spec["payload"], "source test payload binding role differs")
                if profile == HOOK_REVIEW_SOURCE_PROFILE:
                    require(set(group["cells"]) == {HOOK_REVIEW_FINDING_CELL}
                            and set(group["selectors"]) == HOOK_REVIEW_FINDING_SELECTORS,
                            "hook finding profile requires its complete exact declarative finding composition")
                elif profile == Q02_SOURCE_PROFILE:
                    require(set(group["cells"]) <= Q02_SOURCE_CELLS
                            and set(group["selectors"]) <= Q02_REQUIRED_SELECTORS,
                            "Q02 implementation profile cannot qualify another task or scope")
                elif profile == SOURCE_PROFILE:
                    require(set(group["cells"]) <= SOURCE_PROFILE_CELLS, "Python profile cannot qualify another software scope")
                elif profile == SDK_SOURCE_PROFILE:
                    require(set(group["cells"]) <= SDK_SOURCE_CELLS, "SDK Python profile cannot qualify another software scope")
                else:
                    require(set(group["cells"]) <= TS_PROFILE_CELLS[profile], "TS profile cannot qualify another software scope")
                admit_source_observation(observed, payloads.get(spec["payload"], {}), req, job_name, job_id)
            if group["proof_kind"] == "native-module":
                native_bindings.append(observed.get("native_binding"))
            key = group["observation"]
            if key not in indices:
                tests = observed.get("tests")
                require(isinstance(tests, list) and len(tests) <= MAX_TESTS
                        and all(isinstance(test, dict) and set(test) == {"id", "result"}
                                and isinstance(test["id"], str) and test["id"]
                                and len(test["id"].encode("utf-8")) <= MAX_TEST_ID_BYTES for test in tests),
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
        with zipfile.ZipFile(io.BytesIO(archive)) as source_archive:
            require(source_archive.getinfo(SOURCE_MANIFEST).file_size <= 1024 * 1024, "source payload manifest exceeds bound")
            raw = source_archive.read(SOURCE_MANIFEST)
        manifest = json.loads(raw, object_pairs_hook=unique)
        spec = source_profile(manifest.get("profile") if isinstance(manifest, dict) else None)
        require(isinstance(source_job, dict) and type(source_job.get("id")) is int
                and source_job["id"] > 0 and source_job.get("name") == spec["job"]
                and source_job.get("status") == "in_progress" and source_job.get("conclusion") is None,
                "source payload original uploader job missing")
        # The owning job is still running, so its completed job log does not
        # exist yet. Bind producer-time identity to its completed upload step;
        # final readiness authenticates both uploader logs independently.
        upload_steps = [step for step in source_job.get("steps", []) if step.get("name") == spec["upload"]]
        require(metadata.get("name") == spec["payload"] and len(upload_steps) == 1
                and upload_steps[0].get("status") == "completed"
                and upload_steps[0].get("conclusion") == "success", "source payload upload step did not complete")
        validate_source_manifest(manifest, req, source_job["name"], members)
        snapshot = source_input_snapshot(root, manifest["profile"])
        require(snapshot["source_commit"] == req["source_commit"] and snapshot["source_tree"] == req["source_tree"]
                and snapshot["members"] == manifest["members"], "source payload actual consumed source differs")
        documents[SOURCE_MANIFEST] = manifest
        source_manifest_sha256 = readiness.digest(raw)
    if any(member["path"] == "major-mapped-work-inputs.json" for member in members):
        from mapped_work_observation import MANIFEST as MAPPED_MANIFEST, SOURCE_PAYLOAD as MAPPED_PAYLOAD, JOB as MAPPED_JOB, UPLOAD as MAPPED_UPLOAD, validate_manifest as validate_mapped_manifest
        require(metadata.get("name") == MAPPED_PAYLOAD and isinstance(source_job, dict)
                and type(source_job.get("id")) is int and source_job["id"] > 0
                and source_job.get("name") == MAPPED_JOB and source_job.get("status") == "in_progress"
                and source_job.get("conclusion") is None, "mapped original source uploader missing")
        steps = [step for step in source_job.get("steps", []) if step.get("name") == MAPPED_UPLOAD]
        require(len(steps) == 1 and steps[0].get("status") == "completed" and steps[0].get("conclusion") == "success",
                "mapped original source upload did not complete")
        with zipfile.ZipFile(io.BytesIO(archive)) as source_archive:
            require(source_archive.getinfo(MAPPED_MANIFEST).file_size <= 1024 * 1024, "mapped manifest exceeds bound")
            raw = source_archive.read(MAPPED_MANIFEST)
        manifest = json.loads(raw, object_pairs_hook=unique)
        validate_mapped_manifest(manifest, req=req, repo=ROOT, members=members)
        documents[MAPPED_MANIFEST] = manifest
        source_manifest_sha256 = readiness.digest(raw)
    for member in members:
        if member["path"] in (SOURCE_MANIFEST, "major-mapped-work-inputs.json"):
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
    parser.add_argument("--source-profile", default=SOURCE_PROFILE, choices=(SOURCE_PROFILE, SDK_SOURCE_PROFILE, Q02_SOURCE_PROFILE, HOOK_REVIEW_SOURCE_PROFILE, *TS_PROFILE_PATHS), help="closed prepare-source input profile")
    parser.add_argument("--native-binding", type=Path)
    parser.add_argument("--raw-results", type=Path)
    parser.add_argument("--execution-cwd", type=Path)
    parser.add_argument("--job-name")
    parser.add_argument("--payload-root", action="append", default=[], help="artifact name=original consumed root")
    parser.add_argument("arguments", nargs="*")
    args = parser.parse_args(argv)
    try:
        if args.operation == "prepare-source":
            prepare_source_payload(args.repo, args.output, args.job_name, args.source_profile)
            return 0
        if args.operation == "observe-python":
            require(args.arguments, "Python entry point required")
            return observe_python(args.repo, args.arguments[0], args.arguments[1:], args.output, args.source_payload, args.source_profile)
        if args.operation == "observe-vitest":
            return observe_vitest(args.repo, args.arguments, args.raw_results, args.output, args.execution_cwd, args.source_payload)
        if args.operation == "admit-go":
            require(len(args.observation) == 1 and args.native_binding, "native observation and original stamp required")
            binding = load_json(args.native_binding)
            tree = git(args.repo, "rev-parse", binding["source_commit"] + "^{tree}")
            new_output(args.output, admit_go(load_json(args.observation[0]), binding, tree))
            return 0
        require(args.output.name == "qualification.json", "emit output must be named qualification.json")
        validate_emitter_environment()
        source, run_id = os.environ["GITHUB_SHA"], int(os.environ["GITHUB_RUN_ID"])
        profile = next((p for p, job in TS_PROFILE_JOBS.items() if job == args.job_name), None)
        identity = source_identity(args.repo, profile)
        require(identity["source_commit"] == source and identity["clean"], "report source differs from actual clean checkout")
        req, _, artifacts, jobs = readiness.collect(args.repo, source, run_id, producing=True, allow_program_branch=True, producer_scope=True)
        matching = [j for j in jobs if j["name"] == args.job_name and j.get("status") == "in_progress"]
        require(len(matching) == 1, "one current original owning job required")
        observations = {}
        for item in args.observation:
            key, path = item.split("=", 1)
            require(key not in observations, "duplicate observation key")
            observations[key] = load_json(path)
        native_components = {}
        mapped_keys = [key for key, value in observations.items()
                       if value.get("producer") == "python-mapped-native-consumer-observer-v1"]
        if mapped_keys:
            require(len(mapped_keys) == 1, "one original mapped consumer observation required")
            from major_native_observation import authenticate_component
            # Pins come only from the immutable owning source, never the report.
            with readiness.blob_transaction(args.repo):
                for order in ("posix", "windows"):
                    pin = readiness._module_membership(args.repo, source,
                        {"root": "core/artifacts", "path_order": order},
                        lambda commit, path: readiness.blob(args.repo, commit, path), {})
                    req.setdefault("native_module_sha256", {})[order] = pin
            run = readiness.api(f"actions/runs/{run_id}")
            native_components[mapped_keys[0]] = authenticate_component(req, run, artifacts, jobs, "windows/amd64")
        payloads = {}
        for item in args.payload_root:
            name, path = item.split("=", 1)
            require(name not in payloads, "duplicate payload identity")
            found = [a for a in artifacts if a["name"] == name]
            require(len(found) == 1, "original consumed artifact missing or ambiguous")
            if mapped_keys and name == "ci20-native-tested-windows-2025":
                from mapped_work_observation import authenticate_native_consumption
                payloads[name] = authenticate_native_consumption(path, native_components[mapped_keys[0]])
                require(found[0].get("id") == payloads[name]["artifact_id"], "mapped native artifact API identity differs")
            else:
                payloads[name] = authenticated_payload(found[0], req, path, source_job=matching[0]
                    if name in (SOURCE_PAYLOAD, SDK_SOURCE_PAYLOAD, Q02_SOURCE_PAYLOAD, HOOK_REVIEW_SOURCE_PAYLOAD, *TS_PROFILE_PAYLOADS.values(), "major-source-inputs-mapped-work-windows") else None)
        report = build_report(req, job_name=args.job_name, job_id=matching[0]["id"],
                              selections=load_json(args.repo / ".github/major-test-selections.json"),
                              producer_job=matching[0],
                              observations=observations, payloads=payloads, native_components=native_components)
        new_output(args.output, report)
        return 0
    except (OSError, ValueError, KeyError, TypeError, subprocess.SubprocessError, readiness.ReadinessError) as error:
        print("::error::Major qualification report pending: " + str(error), file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
