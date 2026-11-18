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
    require(profile is None or profile in (SOURCE_PROFILE, SDK_SOURCE_PROFILE, Q02_SOURCE_PROFILE, HOOK_REVIEW_SOURCE_PROFILE, *PYTHON_COMPONENT_PROFILES) or profile in TS_PROFILE_PATHS or profile in PYTHON_FINDING_PROFILES, "unknown source identity profile")
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

# Additional finite findings use the same original typed source profiles.
# Every required assertion must survive selection; this is not installed/task credit.
# Original Sandbox driver cases for retained component scopes.
TS_PROFILE_CELLS["sandbox-tools-v1"] |= frozenset((
    "disposition:added_transitions:SBX-BUILD-OBSERVATION:01",
    "disposition:added_transitions:SBX-BUILD-OBSERVATION:02",
    "disposition:added_transitions:SBX-BUILD-OBSERVATION:03",
    "disposition:machines:S53",
    "disposition:transitions:S48:06",
    "disposition:transitions:S48:07",
    "disposition:transitions:S49:01",
    "disposition:transitions:S49:02",
    "disposition:transitions:S49:03",
    "disposition:transitions:S49:04",
    "disposition:transitions:S49:05",
    "disposition:transitions:S49:06",
    "disposition:transitions:S49:07",
    "disposition:transitions:S49:08",
    "disposition:transitions:S49:09",
    "disposition:transitions:S51:05",
    "disposition:transitions:S52:01",
    "disposition:transitions:S52:02",
    "disposition:transitions:S52:03",
    "disposition:transitions:S52:04",
    "disposition:transitions:S52:05",
    "disposition:transitions:S53:01",
    "disposition:transitions:S53:02",
    "disposition:transitions:S53:03",
    "disposition:transitions:S53:04",
    "disposition:transitions:S53:05",
    "disposition:transitions:S53:06",
    "disposition:transitions:S53:07",
))

TS_FINDING_RECIPES = {
    'disposition:findings:SF01': {"profile": 'pi-tools-v1', "selectors": frozenset((
        'vitest:plugins/ca-pi/tools/test/parent-delegation.test.ts:parent-authorized delegated file effects child proxy crosses real channel and parent final gate before durable file effect',
        'vitest:plugins/ca-pi/tools/test/delegation-session.test.ts:parent-owned delegation session lifecycle loss aborts active execution while its owned cleanup can settle',
        'vitest:plugins/ca-pi/tools/test/delegation-session.test.ts:parent-owned delegation session real loopback client sends only exact tool data, serializes concurrent requests and revokes',
        'vitest:plugins/ca-pi/tools/test/delegation-session.test.ts:parent-owned delegation session authenticates and joins duplicate requests; changed request identity never repeats effects',
        'vitest:plugins/ca-pi/tools/test/delegation-session.test.ts:parent-owned delegation session bounds sequence and grant operation population',
        'vitest:plugins/ca-pi/tools/test/delegation-session.test.ts:parent-owned delegation session expiry, lifecycle loss, explicit revoke and forged authority never admit effects',
    ))},
    'disposition:findings:SF02': {"profile": 'pi-tools-v1', "selectors": frozenset((
        'vitest:plugins/ca-pi/tools/test/activation.test.ts:Pi activation persona readiness is independent of bridge health (PI-L01) persona failure followed by bridge success alone stays persona-unavailable',
        'vitest:plugins/ca-pi/tools/test/activation.test.ts:Pi activation persona readiness is independent of bridge health (PI-L01) a successful persona retry in the current lifecycle restores prompt and readiness once',
        'vitest:plugins/ca-pi/tools/test/activation.test.ts:Pi activation persona readiness is independent of bridge health (PI-L01) a healthy start reports starting then governed, never persona unavailable',
        'vitest:plugins/ca-pi/tools/test/activation.test.ts:Pi activation persona readiness is independent of bridge health (PI-L01) an empty persona cannot mark the session governed',
        'vitest:plugins/ca-pi/tools/test/activation.test.ts:Pi activation persona readiness is independent of bridge health (PI-L01) a late persona from a retired session never populates the next session',
    ))},
    'disposition:findings:SF03': {"profile": 'pi-tools-v1', "selectors": frozenset((
        'vitest:plugins/ca-pi/tools/test/sidebar-manager.test.ts:sidebar manager disposal while installation is pending (PI-L02) off while metrics are pending keeps native hooks after metrics resolve',
        'vitest:plugins/ca-pi/tools/test/sidebar-manager.test.ts:sidebar manager disposal while installation is pending (PI-L02) dispose while metrics are pending, then resolve: nothing installs',
        'vitest:plugins/ca-pi/tools/test/sidebar-manager.test.ts:sidebar manager disposal while installation is pending (PI-L02) off during pending metrics does not persist into a new session',
        'vitest:plugins/ca-pi/tools/test/sidebar-manager.test.ts:sidebar manager disposal while installation is pending (PI-L02) a metrics failure after dispose does not report the next session degraded',
        'vitest:plugins/ca-pi/tools/test/sidebar-manager.test.ts:sidebar manager disposal while installation is pending (PI-L02) old and new session metrics resolve old-first: only the new session installs, once',
        'vitest:plugins/ca-pi/tools/test/sidebar-manager.test.ts:sidebar manager disposal while installation is pending (PI-L02) old and new session metrics resolve new-first: only the new session installs, once',
    ))},
    'disposition:findings:SF12': {"profile": 'pi-tools-v1', "selectors": frozenset((
        'vitest:plugins/ca-pi/tools/test/package.test.ts:ca-pi package private artifact approval stays unavailable on the admitted host and legacy evidence grants no ordinary support',
        'vitest:plugins/ca-pi/tools/test/approval-dialog.test.ts:isolated Pi native approval dialog passes only the exact native return with pending, session and fresh generation bindings',
        'vitest:plugins/ca-pi/tools/test/approval-dialog.test.ts:isolated Pi native approval dialog refuses RPC, missing trust and active tools before constructing a bridge',
        'vitest:plugins/ca-pi/tools/test/approval-dialog.test.ts:isolated Pi native approval dialog does not normalize a wrong reply into an approval',
        'vitest:plugins/ca-pi/tools/test/approval-dialog.test.ts:isolated Pi native approval dialog reports an uncertain outcome after a consume transport failure',
        'vitest:plugins/ca-pi/tools/test/approval-dialog.test.ts:isolated Pi native approval dialog requires one exact closed CLI launch and rejects added commands, tools, extensions or preloads',
    ))},
    'disposition:findings:SF08': {"profile": 'sandbox-tools-v1', "selectors": frozenset((
        'vitest:plugins/ca-sandbox/tools/state-contracts.test.ts:SBX-C01 equal inputs in different checkout basenames select a verified stable key',
        'vitest:plugins/ca-sandbox/tools/state-contracts.test.ts:SBX-C01 existence alone is a cache miss and toolchain identity changes the tag',
        'vitest:plugins/ca-sandbox/tools/state-contracts.test.ts:SBX-C01 malformed builder observation blocks reuse and invalid provenance forces rebuild',
        'vitest:plugins/ca-sandbox/tools/state-contracts.test.ts:SBX-C01 real probe output cannot launder malformed version prose into a cache identity',
        'vitest:plugins/ca-sandbox/tools/state-contracts.test.ts:SBX-C01 create uses the observed immutable image despite a mutable cache tag',
        'vitest:plugins/ca-sandbox/tools/state-contracts.test.ts:SBX-C01 manifest observation distinguishes absent inputs, valid bytes and unreadable declared inputs',
        'vitest:plugins/ca-sandbox/tools/state-contracts.test.ts:SBX-C01 dangling declared configuration is unavailable rather than a missing input',
        'vitest:plugins/ca-sandbox/tools/cache-provenance.test.ts:SBX-C01 real two-create cache provenance dockerfile-fallback: distinct staging names reuse the exact labeled image and preserve another box',
        'vitest:plugins/ca-sandbox/tools/cache-provenance.test.ts:SBX-C01 real two-create cache provenance nixpacks: distinct staging names reuse the exact labeled image and preserve another box',
    ))},
    'disposition:findings:SF10': {"profile": 'sandbox-tools-v1', "selectors": frozenset((
        'vitest:plugins/ca-sandbox/tools/state-contracts.test.ts:SBX-C03 reports failed resource observations as unavailable, not empty',
        'vitest:plugins/ca-sandbox/tools/state-contracts.test.ts:SBX-C03 cancellation cannot cancel compensation and unknown cleanup retains exact references',
        'vitest:plugins/ca-sandbox/tools/state-contracts.test.ts:SBX-C03 cancelled firewall setup keeps exact cleanup live and never invents destruction',
        'vitest:plugins/ca-sandbox/tools/state-contracts.test.ts:SBX-C03 partial failure stdout cannot authorize destruction of an unobserved target',
    ))},
    'disposition:findings:SF09': {"profile": 'sandbox-tools-v1', "selectors": frozenset((
        'vitest:plugins/ca-sandbox/tools/state-contracts.test.ts:SBX-C02 treats overflow as lost observation and verifies target containment',
        'vitest:plugins/ca-sandbox/tools/deadline.test.ts:#394 — a real hung command terminates within its deadline SBX-C02 real output overflow stops only its exact target and preserves another running box',
    ))},
}

# Farm reuses the original unfiltered source-test observer; native manifest
# declarations do not confer native runtime or installed-host qualification.
TS_PROFILE_PATHS["farm-tools-v1"] = TS_COMMON_PATHS | frozenset(('.github/fixtures/artifact-release-manifest.json',
 'core/artifact-release-manifest.json',
 'plugins/ca/tools/.env.example',
 'plugins/ca/tools/__fixtures__/simple.plan.json',
 'plugins/ca/tools/artifact-manifest.test.ts',
 'plugins/ca/tools/artifact-manifest.ts',
 'plugins/ca/tools/exec.test.ts',
 'plugins/ca/tools/exec.ts',
 'plugins/ca/tools/farm-cleanup-observation.test.ts',
 'plugins/ca/tools/farm-dist.test.ts',
 'plugins/ca/tools/farm-interruption.test.ts',
 'plugins/ca/tools/farm-recovery.test.ts',
 'plugins/ca/tools/farm-recovery.ts',
 'plugins/ca/tools/farm-registry-lock.test.ts',
 'plugins/ca/tools/farm-surface.test.ts',
 'plugins/ca/tools/farm.js',
 'plugins/ca/tools/farm.test.ts',
 'plugins/ca/tools/farm.ts',
 'plugins/ca/tools/farm.unit.test.ts',
 'plugins/ca/tools/mutation.test.ts',
 'plugins/ca/tools/mutation.ts',
 'plugins/ca/tools/package-lock.json',
 'plugins/ca/tools/package.json',
 'plugins/ca/tools/plan-contract.test.ts',
 'plugins/ca/tools/plan.schema.json',
 'plugins/ca/tools/redactor.test.ts',
 'plugins/ca/tools/redactor.ts',
 'plugins/ca/tools/state-contracts.test.ts',
 'plugins/ca/tools/tsconfig.json',
 'plugins/ca/tools/vitest.config.ts',
 'plugins/ca/tools/worktree-fs.test.ts',
 'plugins/ca/tools/worktree-fs.ts'))
TS_PROFILE_ROOTS["farm-tools-v1"] = "plugins/ca/tools"
TS_PROFILE_JOBS["farm-tools-v1"] = "[CHECK] | [CA  ] | Farm dispatcher contract"
TS_PROFILE_PAYLOADS["farm-tools-v1"] = "major-source-inputs-farm-dispatcher"
TS_PROFILE_UPLOADS["farm-tools-v1"] = "Upload Farm source-test inputs"
TS_PROFILE_CELLS["farm-tools-v1"] = frozenset((
    "disposition:added_transitions:FARM-COMMON-REGISTRY-LOCK:01",
    "disposition:added_transitions:FARM-COMMON-REGISTRY-LOCK:02",
    "disposition:added_transitions:FARM-COMMON-REGISTRY-LOCK:03",
    "disposition:added_transitions:FARM-COMMON-REGISTRY-LOCK:04",
    "disposition:added_transitions:FARM-COMMON-REGISTRY-LOCK:05",
    "disposition:added_transitions:FARM-COMMON-REGISTRY-LOCK:06",
))
TS_FINDING_RECIPES.update({
    'disposition:findings:SF04': {"profile": "farm-tools-v1", "selectors": frozenset((
        'vitest:plugins/ca/tools/artifact-manifest.test.ts:shared native manifest declarations candidate-five-fields',
        'vitest:plugins/ca/tools/artifact-manifest.test.ts:shared native manifest declarations qualified-declaration-six-fields',
        'vitest:plugins/ca/tools/artifact-manifest.test.ts:shared native manifest declarations unknown-field',
        'vitest:plugins/ca/tools/artifact-manifest.test.ts:shared native manifest declarations unknown-format',
        'vitest:plugins/ca/tools/artifact-manifest.test.ts:shared native manifest declarations malformed-context',
        'vitest:plugins/ca/tools/artifact-manifest.test.ts:shared native manifest declarations unknown-context-platform',
        'vitest:plugins/ca/tools/artifact-manifest.test.ts:shared native manifest declarations wrong-context-binary',
        'vitest:plugins/ca/tools/artifact-manifest.test.ts:shared native manifest declarations unknown-context-field',
        'vitest:plugins/ca/tools/artifact-manifest.test.ts:shared native manifest declarations wrong-platform-path',
        'vitest:plugins/ca/tools/artifact-manifest.test.ts:shared native manifest declarations unqualified-context',
        'vitest:plugins/ca/tools/artifact-manifest.test.ts:shared native manifest declarations bounds UTF-8 bytes before parsing',
        'vitest:plugins/ca/tools/artifact-manifest.test.ts:shared native manifest declarations rejects duplicate and escaped-duplicate keys',
    ))},
    'disposition:findings:SF05': {"profile": "farm-tools-v1", "selectors": frozenset((
        'vitest:plugins/ca/tools/state-contracts.test.ts:FARM-R01 exclusive identities preserve evidence under a same-ID race',
        'vitest:plugins/ca/tools/state-contracts.test.ts:FARM-R01 reconciles a post-merge crash in real Git without changing a ref or calling an author',
        'vitest:plugins/ca/tools/farm-interruption.test.ts:FARM-R01 real post-merge process interruption preserves unknown cleanup and concurrent receipt-only recovery (source)',
        'vitest:plugins/ca/tools/farm-interruption.test.ts:FARM-R01 real post-merge process interruption preserves unknown cleanup and concurrent receipt-only recovery (bundle)',
        'vitest:plugins/ca/tools/farm-interruption.test.ts:FARM-R01 real post-commit process interruption retains unacknowledged candidate without recovered green (source)',
        'vitest:plugins/ca/tools/farm-interruption.test.ts:FARM-R01 real post-commit process interruption retains unacknowledged candidate without recovered green (bundle)',
        'vitest:plugins/ca/tools/farm-interruption.test.ts:FARM-R01 real pre-merge interruption preserves pending merge resources through receipt-only recovery (source)',
        'vitest:plugins/ca/tools/farm-interruption.test.ts:FARM-R01 real pre-merge interruption preserves pending merge resources through receipt-only recovery (bundle)',
        'vitest:plugins/ca/tools/farm-interruption.test.ts:FARM-R01 unblocked real post-merge hook control publishes normal green receipt (bundle)',
        "vitest:plugins/ca/tools/farm.test.ts:farm artifact publication (#397 / #387) #397: a failed report publication leaves the previous run's complete report intact — never a truncated one",
        'vitest:plugins/ca/tools/farm.test.ts:farm artifact publication (#397 / #387) #387: a green run whose farm-report.json cannot be published exits non-zero and never claims a Report path',
        'vitest:plugins/ca/tools/farm.test.ts:farm artifact publication (#397 / #387) FARM-R01 journal publication failure drains independent tasks and retains their real outcomes',
        'vitest:plugins/ca/tools/farm.test.ts:farm artifact publication (#397 / #387) #387: a failure to publish farm-report.md also fails the run',
    ))},
    'disposition:findings:SF06': {"profile": "farm-tools-v1", "selectors": frozenset((
        'vitest:plugins/ca/tools/state-contracts.test.ts:FARM-R02 preserves failed containment and admits no reset or second author',
        'vitest:plugins/ca/tools/state-contracts.test.ts:FARM-R02 gate retains executor outcome instead of flattening code 125 into test failure',
        'vitest:plugins/ca/tools/state-contracts.test.ts:FARM-R02 uncontained sample setup retains scratch resources without authoring or reset',
    ))},
    'disposition:findings:SF07': {"profile": "farm-tools-v1", "selectors": frozenset((
        'vitest:plugins/ca/tools/state-contracts.test.ts:FARM-R03 refuses unknown Git drift instead of inventing a clean observation',
        'vitest:plugins/ca/tools/state-contracts.test.ts:FARM-R03 bounded read-only retry accepts only a successful current observation',
        'vitest:plugins/ca/tools/state-contracts.test.ts:FARM-R03 fresh pre-stage dirty drift controls dependent mutations',
        'vitest:plugins/ca/tools/state-contracts.test.ts:FARM-R03 fresh pre-stage unavailable drift controls dependent mutations',
        'vitest:plugins/ca/tools/state-contracts.test.ts:FARM-R03 fresh pre-stage clean drift controls dependent mutations',
    ))},
})

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
ROUTE_RELEASE_SOURCE_PROFILE = "route-release-state-component-v1"
ROUTE_RELEASE_SOURCE_SCRIPT = ".github/scripts/test_command_route_release_state.py"
ROUTE_COMPATIBILITY_SCRIPT = ".github/scripts/test_command_route_compatibility.py"
ROUTE_GENERATOR_SCRIPT = ".github/scripts/test_build_surface.py"
SF13_CELL = "disposition:findings:SF13"
SF13_SYNC_SCRIPT = ".github/scripts/test_sync_core.py"
OUTER_UNITTEST_RESULT = "entrypoint-text-runner"
ROUTE_RELEASE_SOURCE = {
    "job": "[CHECK] | [CORE] | Generated surface",
    "payload": "major-source-inputs-route-release-state",
    "upload": "Upload release-state classifier source-test inputs",
    "scripts": (ROUTE_RELEASE_SOURCE_SCRIPT, ROUTE_COMPATIBILITY_SCRIPT),
    "paths": frozenset((
        ROUTE_RELEASE_SOURCE_SCRIPT,
        ROUTE_COMPATIBILITY_SCRIPT,
        ".codearbiter/plans/reaudit-ra11-catalog-rationalization.md",
        ".codearbiter/specs/reaudit-ra11-catalog-rationalization.md",
        ".codearbiter/sprint-log.md",
        ".github/major-qualification-policy.json",
        ".github/scripts/_boundedproc.py",
        ".github/scripts/_contextverificationlib.py",
        ".github/scripts/_immutable_git_blobs.py",
        ".github/scripts/check_command_route_release_state.py",
        ".github/scripts/ci20_native_binding.py",
        ".github/scripts/major_qualification_report.py",
        ".github/scripts/major_readiness.py",
        ".github/workflows/ci.yml",
        "core/pysrc/_artifactmanifestlib.py",
        "core/pysrc/_gitexec.py",
        "core/surface/command-routes.json",
        "core/surface/includes/command-compatibility.md",
        "plugins/ca/.claude-plugin/plugin.json",
        "plugins/ca-codex/.codex-plugin/plugin.json",
        "plugins/ca-pi/package.json",
        "tools/command_compatibility.py",
    )) | frozenset(path for path in SOURCE_PATHS if path.startswith("core/surface/")),
}
RECOVERY_RUNTIME_PROFILE = "workflow-recovery-runtime-v1"
RECOVERY_RUNTIME_SCRIPT = ".github/scripts/test_workflow_recovery.py"
RECOVERY_INSTALLED_SCRIPTS = {
    ".github/scripts/test_workflow_recovery_cli.py": ("cli", "InstalledRecoveryTest"),
    ".github/scripts/test_workflow_recovery_hosts.py": ("hosts", "RecoveryHostTest"),
}
RECOVERY_INSTALLATION_ENV = "WORKFLOW_RECOVERY_INSTALLATION_OBSERVATION"
RECOVERY_NATIVE_PLATFORM = "windows/amd64"
RECOVERY_NATIVE_BINARY = "ca-artifact-windows-amd64.exe"
RECOVERY_FINDING_CELLS = ("disposition:findings:HOOK-B04", "disposition:findings:W-F04")
DEBUG_RESUBMISSION_FINDING = "disposition:findings:W-F02"
DEBUG_LAUNCHER = ".github/scripts/test_ci_impact.py"
DEBUG_WORKFLOW_SUITE = ".github/scripts/test_debug_workflow.py"
DEBUG_HANDOFF_SUITE = ".github/scripts/test_debug_handoff.py"
DEBUG_RESUBMISSION_SCRIPT = ".github/scripts/test_review_resubmission.py"
DEBUG_LOCKED_PROFILE = "debug-reference-component-v1"
DEBUG_LOCK_PATH = ".github/requirements/artifact-conformance-py314.lock"
DEBUG_HOOK_PROFILE = "hooks-single-owner-findings-v1"
DEBUG_RUNNERS = {
    DEBUG_HOOK_PROFILE: ("hooks", DEBUG_WORKFLOW_SUITE, "single-owner-hook-source-inputs", "python-debug-workflow-observation.json"),
    DEBUG_LOCKED_PROFILE: ("artifact-native-bridges", DEBUG_HANDOFF_SUITE, "debug-reference-source-inputs", "debug-reference-observation.json"),
}
CATALOG_SOURCE_PROFILE = "command-catalog-component-v1"
CATALOG_SCRIPT = ".github/scripts/test_command_catalog.py"
CATALOG_FINDING_CELL = "disposition:findings:W-F08"
CATALOG_COMMAND_PATHS = frozenset("plugins/ca/commands/" + PurePosixPath(path).name
    for path in SOURCE_PATHS if path.startswith("core/surface/commands/") and path.endswith(".md"))
PYTHON_COMPONENT_PROFILES = {
    ROUTE_RELEASE_SOURCE_PROFILE: ROUTE_RELEASE_SOURCE,
    CATALOG_SOURCE_PROFILE: {
        "job": "[CHECK] | [CA  ] | Documentation consistency",
        "payload": "major-source-inputs-command-catalog",
        "upload": "Upload command catalog source-test inputs",
        "scripts": (CATALOG_SCRIPT,),
        "paths": CATALOG_COMMAND_PATHS | frozenset((
            CATALOG_SCRIPT,
            ".github/scripts/_boundedproc.py",
            ".github/scripts/_contextverificationlib.py",
            ".github/scripts/_immutable_git_blobs.py",
            ".github/scripts/check_command_catalog.py",
            ".github/scripts/ci20_native_binding.py",
            ".github/scripts/major_qualification_report.py",
            ".github/scripts/major_readiness.py",
            ".github/workflows/ci.yml",
            "core/pysrc/_artifactmanifestlib.py",
            "core/pysrc/_gitexec.py",
            "core/surface/skills/INDEX.md",
            "plugins/ca/COMMANDS.md",
            "plugins/ca/skills/INDEX.md",
            "plugins/ca-codex/routines/INDEX.md",
            "plugins/ca-pi/routines/INDEX.md",
        )),
    },
    DEBUG_LOCKED_PROFILE: {
        "job": "[CHECK] | [CORE] | Native adapters and conformance <linux/amd64>",
        "payload": "major-source-inputs-debug-reference",
        "upload": "Upload locked debug reference source-test inputs",
        "scripts": (DEBUG_HANDOFF_SUITE,),
        "paths": frozenset((
            DEBUG_LAUNCHER, DEBUG_HANDOFF_SUITE, DEBUG_LOCK_PATH,
            ".github/fixtures/debug/cases.json",
            ".github/fixtures/debug/handoff-examples.json",
            ".github/fixtures/debug/qualification-cells.json",
            ".github/scripts/_boundedproc.py",
            ".github/scripts/_contextverificationlib.py",
            ".github/scripts/_immutable_git_blobs.py",
            ".github/scripts/ci20_native_binding.py",
            ".github/scripts/major_qualification_report.py",
            ".github/scripts/major_readiness.py",
            ".github/scripts/test_hook_ci_partition.py",
            ".github/workflows/ci.yml",
            "core/pysrc/_artifactmanifestlib.py",
            "core/pysrc/_debughandofflib.py",
            "core/pysrc/_gitexec.py",
            "core/pysrc/debug-handoff.py",
            "tools/ci-impact.py",
        )) | frozenset(path for path in SOURCE_PATHS if path.startswith("core/surface/skills/debug/")),
    },
    RECOVERY_RUNTIME_PROFILE: {
        "job": "[CHECK] | [CORE] | Workflow recovery  <os: windows-latest>",
        "payload": "major-source-inputs-workflow-recovery-runtime",
        "upload": "Upload workflow recovery runtime source inputs",
        "scripts": (RECOVERY_RUNTIME_SCRIPT, DEBUG_RESUBMISSION_SCRIPT, *RECOVERY_INSTALLED_SCRIPTS),
        "paths": frozenset((
            RECOVERY_RUNTIME_SCRIPT,
            DEBUG_RESUBMISSION_SCRIPT,
            ".github/scripts/fixtures/claude-hooks/agent-posttooluse.json",
            ".github/scripts/fixtures/claude-hooks/agent-pretooluse.json",
            ".github/scripts/fixtures/claude-hooks/subagentstart.json",
            ".github/scripts/fixtures/claude-hooks/subagentstop-first.json",
            *RECOVERY_INSTALLED_SCRIPTS,
            ".github/scripts/_boundedproc.py",
            ".github/scripts/_contextverificationlib.py",
            ".github/scripts/_immutable_git_blobs.py",
            ".github/scripts/ci20_native_binding.py",
            ".github/scripts/major_qualification_report.py",
            ".github/scripts/major_readiness.py",
            ".github/scripts/test_artifact_authoring.py",
            ".github/scripts/test_artifact_authority_adapter.py",
            ".github/workflows/ci.yml",
            "core/artifact-release-manifest.json",
            "core/pysrc/_activationlib.py",
            "core/pysrc/_arbiterstatelib.py",
            "core/pysrc/_artifactauthoritylib.py",
            "core/pysrc/_artifactlib.py",
            "core/pysrc/_artifactmanifestlib.py",
            "core/pysrc/_artifactpromptlib.py",
            "core/pysrc/_gitexec.py",
            "core/pysrc/_hooklib.py",
            "core/pysrc/_modelib.py",
            "core/pysrc/_pathnorm.py",
            "core/pysrc/_protectedlib.py",
            "core/pysrc/_protectedstatelib.py",
            "core/pysrc/_replylib.py",
            "core/pysrc/_scopelib.py",
            "core/pysrc/_sensitivelib.py",
            "core/pysrc/_taskboardlib.py",
            "core/pysrc/_workflowrecoverylib.py",
            "core/pysrc/_worklib.py",
            "core/pysrc/hostapi.py",
            "core/pysrc/taskwrite.py",
            "core/pysrc/work.py",
            "core/pysrc/workflow-recovery.py",
            "core/workflow-recovery-contract.json",
            "plugins/ca/.claude-plugin/plugin.json",
            "plugins/ca/hooks/prompt-submit.py",
            "plugins/ca/hooks/session-start.py",
            "plugins/ca/hooks/workflow-recovery.py",
            "plugins/ca-codex/.codex-plugin/plugin.json",
            "plugins/ca-codex/hooks/pre-tool-adapter.py",
            "plugins/ca-codex/hooks/prompt-submit.py",
            "plugins/ca-codex/hooks/session-start.py",
            "plugins/ca-codex/hooks/workflow-recovery.py",
            "plugins/ca-pi/hooks/pi-bridge.py",
            "plugins/ca-pi/hooks/workflow-recovery.py",
            "plugins/ca-pi/package.json",
            "tools/build-artifacts.py",
            "tools/go_test_parallel.py",
        )),
    },
}
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


Q02_FINDING_RECIPES = {
    "disposition:findings:C-F02": {
        "script": ".github/scripts/test_release_workflow.py",
        "observation": "q02-release",
        "selectors": frozenset(
            "python:.github/scripts/test_release_workflow.py:__main__.SourceSelectionTest." + name
            for name in (
                "test_newer_failed_head_selects_the_older_successful_source_and_says_so",
                "test_route_publication_is_observed_after_every_target_settles",
                "test_route_observer_uses_only_read_permission_and_declares_public_visibility",
                "test_no_successful_ci_is_refused",
                "test_source_no_longer_on_main_is_refused",
                "test_expired_or_missing_artifacts_are_reported_not_hidden",
                "test_selection_that_differs_from_the_approved_candidate_is_refused",
                "test_workflow_run_event_binds_its_own_run",
            )
        ),
    },
}


# Single-owner finding routes use existing unfiltered commands. Shared source
# transport grants no multi-owner, whole-task, model or installed-host claim.
_HOOK_SINGLE_OWNER_PATHS = SOURCE_PATHS | frozenset([
 '.claude-plugin/marketplace.json',
 'plugins/ca/skills/debug/SKILL.md', 'plugins/ca/skills/debug/references/preparation.md',
 'plugins/ca-codex/routines/debug/SKILL.md', 'plugins/ca-codex/routines/debug/references/preparation.md',
 'plugins/ca-pi/routines/debug/SKILL.md', 'plugins/ca-pi/routines/debug/references/preparation.md',
 '.gitattributes',
 '.github/major-qualification-policy.json',
 '.github/major-test-selections.json',
 '.github/scripts/_codex_cli_profile.py',
 '.github/scripts/_context_fixturelib.py',
 '.github/scripts/_git_fixture_diagnostics.py',
 '.github/scripts/_npm_publishlib.py',
 '.github/scripts/_pi_rpc_profile.py',
 '.github/scripts/_releaselib.py',
 '.github/scripts/_sandbox_docker_profile.py',
 '.github/scripts/_verdictlib.py',
 '.github/scripts/_windows_dbgeng.py',
 '.github/scripts/_windows_rpc_timeout.py',
 '.github/scripts/academy_promotion.py',
 '.github/scripts/acquire_nixpacks.py',
 '.github/scripts/adr_lifecycle.py',
 '.github/scripts/build_release_targets_provenance.py',
 '.github/scripts/check-plugin-refs.py',
 '.github/scripts/check_adr_identity.py',
 '.github/scripts/check_adr_lifecycle.py',
 '.github/scripts/check_auto_release_candidate.py',
 '.github/scripts/check_badge_consistency.py',
 '.github/scripts/check_branch_protection.py',
 '.github/scripts/check_codex_host.py',
 '.github/scripts/check_codex_skill_resources.py',
 '.github/scripts/check_codex_static_package.py',
 '.github/scripts/check_command_catalog.py',
 '.github/scripts/check_command_route_release_state.py',
 '.github/scripts/check_control_bytes.py',
 '.github/scripts/check_destructive_registry.py',
 '.github/scripts/check_docs_contract.py',
 '.github/scripts/check_license_consistency.py',
 '.github/scripts/check_routing_index_parity.py',
 '.github/scripts/check_sandbox_docker_layers.py',
 '.github/scripts/check_site_voice.py',
 '.github/scripts/check_skill_portability.py',
 '.github/scripts/check_state_contracts_integration.py',
 '.github/scripts/check_tag_immutability.py',
 '.github/scripts/codex_agent_routes.py',
 '.github/scripts/codex_live_report_profile.py',
 '.github/scripts/codex_runtime_acquisition.py',
 '.github/scripts/coordinate_codex_host.py',
 '.github/scripts/coordinate_pi_host.py',
 '.github/scripts/coordinate_sandbox_installed.py',
 '.github/scripts/coverage_union.py',
 '.github/scripts/create_codex_distribution_token.py',
 '.github/scripts/fixtures/claude-hooks/2.1.286/agent-posttooluse.json',
 '.github/scripts/fixtures/claude-hooks/2.1.286/agent-pretooluse.json',
 '.github/scripts/fixtures/claude-hooks/2.1.286/handback-posttooluse.json',
 '.github/scripts/fixtures/claude-hooks/2.1.286/handback-pretooluse.json',
 '.github/scripts/fixtures/claude-hooks/2.1.286/subagentstart.json',
 '.github/scripts/fixtures/claude-hooks/2.1.286/subagentstop-first.json',
 '.github/scripts/fixtures/claude-hooks/README.md',
 '.github/scripts/fixtures/claude-hooks/agent-posttooluse.json',
 '.github/scripts/fixtures/claude-hooks/agent-pretooluse.json',
 '.github/scripts/fixtures/claude-hooks/bash-posttooluse.json',
 '.github/scripts/fixtures/claude-hooks/bash-posttoolusefailure.json',
 '.github/scripts/fixtures/claude-hooks/bash-pretooluse.json',
 '.github/scripts/fixtures/claude-hooks/subagentstart.json',
 '.github/scripts/fixtures/claude-hooks/subagentstop-first.json',
 '.github/scripts/fixtures/claude-hooks/subagentstop-second.json',
 '.github/scripts/fixtures/release-trace/commit-graph.json',
 '.github/scripts/fixtures/release-trace/manifests/ca-codex-plugin.json',
 '.github/scripts/fixtures/release-trace/manifests/ca-pi-package.json',
 '.github/scripts/fixtures/release-trace/manifests/ca-pi-root-package.json',
 '.github/scripts/fixtures/release-trace/manifests/ca-plugin.json',
 '.github/scripts/fixtures/release-trace/manifests/ca-sandbox-plugin.json',
 '.github/scripts/fixtures/release-trace/release-targets.md',
 '.github/scripts/fixtures/release-trace/tags.txt',
 '.github/scripts/integration_candidate.py',
 '.github/scripts/major_native_observation.py',
 '.github/scripts/mapped_work_observation.py',
 '.github/scripts/npm_audit_gate.py',
 '.github/scripts/npm_binding_observation.py',
 '.github/scripts/observe_codex_installed_cli.py',
 '.github/scripts/observe_pi_installed_rpc.py',
 '.github/scripts/observe_sandbox_installed_docker.py',
 '.github/scripts/pages_readiness.py',
 '.github/scripts/payload_scope.py',
 '.github/scripts/payload_version_gate.py',
 '.github/scripts/pi_benchmark.py',
 '.github/scripts/pi_cli_resolver.py',
 '.github/scripts/pi_evidence.py',
 '.github/scripts/pi_host_locks.py',
 '.github/scripts/pi_live_report_profile.py',
 '.github/scripts/pi_parent_tui_observation.py',
 '.github/scripts/pi_promotion.py',
 '.github/scripts/prepare_adr_acceptance.py',
 '.github/scripts/project_knowledge.py',
 '.github/scripts/qualify_workflow_recovery_cohort.py',
 '.github/scripts/reconcile_tag_receipt.py',
 '.github/scripts/release_source.py',
 '.github/scripts/release_target.py',
 '.github/scripts/retained_archive_cli_observation.py',
 '.github/scripts/run_artifact_authority_shard.py',
 '.github/scripts/run_concurrent_suites.py',
 '.github/scripts/sandbox_live_report_profile.py',
 '.github/scripts/site_playwright_observation.py',
 '.github/scripts/site_vitest_observation.py',
 '.github/scripts/test_site_vitest_observation.py',
 '.github/scripts/tag_publication_receipt.py',
 '.github/scripts/test_academy_promotion.py',
 '.github/scripts/test_acquire_nixpacks.py',
 '.github/scripts/test_adr_identity.py',
 '.github/scripts/test_adr_lifecycle.py',
 '.github/scripts/test_artifact_approval_adapter.py',
 '.github/scripts/test_artifact_authoring.py',
 '.github/scripts/test_artifact_authority_adapter.py',
 '.github/scripts/test_artifact_authority_retention.py',
 '.github/scripts/test_artifact_bridge.py',
 '.github/scripts/test_artifact_cli.py',
 '.github/scripts/test_artifact_conformance.py',
 '.github/scripts/test_artifact_consumers.py',
 '.github/scripts/test_artifact_coverage.py',
 '.github/scripts/test_artifact_farm.py',
 '.github/scripts/test_artifact_git_excludes.py',
 '.github/scripts/test_artifact_installed_host.py',
 '.github/scripts/test_artifact_manifest_contract.py',
 '.github/scripts/test_artifact_native.py',
 '.github/scripts/test_artifact_npm_nested_launch.py',
 '.github/scripts/test_artifact_package.py',
 '.github/scripts/test_artifact_prerequisite_adapter.py',
 '.github/scripts/test_artifact_reconciliation_adapter.py',
 '.github/scripts/test_artifact_surface.py',
 '.github/scripts/test_artifact_work_cli.py',
 '.github/scripts/test_artifact_workflow.py',
 '.github/scripts/test_auto_release_candidate.py',
 '.github/scripts/test_badge_consistency.py',
 '.github/scripts/test_board_sync.py',
 '.github/scripts/test_boundedproc.py',
 '.github/scripts/test_branch_protection.py',
 '.github/scripts/test_build_surface.py',
 '.github/scripts/test_check_codex_host.py',
 '.github/scripts/test_check_plugin_refs.py',
 '.github/scripts/test_check_routing_index_parity.py',
 '.github/scripts/test_ci20_native_pipeline.py',
 '.github/scripts/test_ci_impact.py',
 '.github/scripts/test_cleanup_contract.py',
 '.github/scripts/test_cleanuplib.py',
 '.github/scripts/test_cleanuplib_inventory.py',
 '.github/scripts/test_cleanuplib_mutation.py',
 '.github/scripts/test_codex_adapter.py',
 '.github/scripts/test_codex_candidate_provenance.py',
 '.github/scripts/test_codex_ci_wiring.py',
 '.github/scripts/test_codex_marketplace_distribution.py',
 '.github/scripts/test_codex_parity_fixture.py',
 '.github/scripts/test_codex_release_identity.py',
 '.github/scripts/test_codex_skill_resources.py',
 '.github/scripts/test_codex_static_candidate.py',
 '.github/scripts/test_codex_static_package.py',
 '.github/scripts/test_command_catalog.py',
 '.github/scripts/test_command_route_compatibility.py',
 '.github/scripts/test_command_route_release_state.py',
 '.github/scripts/test_consumer_smoke.py',
 '.github/scripts/test_context_consumers.py',
 '.github/scripts/test_context_contracts.py',
 '.github/scripts/test_context_evaluation.py',
 '.github/scripts/test_context_fixtures.py',
 '.github/scripts/test_context_host.py',
 '.github/scripts/test_context_installed.py',
 '.github/scripts/test_context_named_output.py',
 '.github/scripts/test_context_native.py',
 '.github/scripts/test_context_verification.py',
 '.github/scripts/test_context_workflow.py',
 '.github/scripts/test_control_bytes.py',
 '.github/scripts/test_coverage_union.py',
 '.github/scripts/test_debug_handoff.py',
 '.github/scripts/test_debug_helper_invocation.py',
 '.github/scripts/test_debug_package.py',
 '.github/scripts/test_debug_qualification.py',
 '.github/scripts/test_debug_workflow.py',
 '.github/scripts/test_dual_host_store.py',
 '.github/scripts/test_go_test_parallel.py',
 '.github/scripts/test_greenfield_context.py',
 '.github/scripts/test_hook_ci_partition.py',
 '.github/scripts/test_hook_guards.py',
 '.github/scripts/test_hooklib.py',
 '.github/scripts/test_hooks_cold_install.py',
 '.github/scripts/test_host_descriptors.py',
 '.github/scripts/test_immutable_git_blobs.py',
 '.github/scripts/test_integration_candidate.py',
 '.github/scripts/test_knowledge_cli.py',
 '.github/scripts/test_license_consistency.py',
 '.github/scripts/test_literal_python_reads.py',
 '.github/scripts/test_major_native_observation.py',
 '.github/scripts/test_major_qualification_report.py',
 '.github/scripts/test_major_readiness.py',
 '.github/scripts/test_marketplace_git_channels.py',
 '.github/scripts/test_migration_backstop.py',
 '.github/scripts/test_mode_compaction.py',
 '.github/scripts/test_mode_readers.py',
 '.github/scripts/test_mode_surface.py',
 '.github/scripts/test_modelib.py',
 '.github/scripts/test_npm_audit_gate.py',
 '.github/scripts/test_npm_binding_observation.py',
 '.github/scripts/test_observe_codex_installed_cli.py',
 '.github/scripts/test_observe_pi_installed_rpc.py',
 '.github/scripts/test_observe_sandbox_installed_docker.py',
 '.github/scripts/test_payload_scope.py',
 '.github/scripts/test_payload_version_gate.py',
 '.github/scripts/test_persona_composition.py',
 '.github/scripts/test_pi_benchmark.py',
 '.github/scripts/test_pi_child_live.py',
 '.github/scripts/test_pi_ci_wiring.py',
 '.github/scripts/test_pi_compaction_surface.py',
 '.github/scripts/test_pi_doctor.py',
 '.github/scripts/test_pi_host_locks.py',
 '.github/scripts/test_pi_package.py',
 '.github/scripts/test_pi_parent_tui_observation.py',
 '.github/scripts/test_pi_parity.py',
 '.github/scripts/test_pi_payload_identity.py',
 '.github/scripts/test_pi_platform_contract.py',
 '.github/scripts/test_pi_process_tree.py',
 '.github/scripts/test_pi_promotion.py',
 '.github/scripts/test_pi_security.py',
 '.github/scripts/test_pi_shared_store.py',
 '.github/scripts/test_planfilelib.py',
 '.github/scripts/test_pre_read.py',
 '.github/scripts/test_prompt_submit.py',
 '.github/scripts/test_provenance_wiring.py',
 '.github/scripts/test_provenancelib.py',
 '.github/scripts/test_prune_nudge.py',
 '.github/scripts/test_prune_policy_parity.py',
 '.github/scripts/test_public_codex_docs.py',
 '.github/scripts/test_public_pi_docs.py',
 '.github/scripts/test_readinjectlib.py',
 '.github/scripts/test_reconcile_tag_receipt.py',
 '.github/scripts/test_recorded_intent_surface.py',
 '.github/scripts/test_release_lib.py',
 '.github/scripts/test_release_target.py',
 '.github/scripts/test_release_trace.py',
 '.github/scripts/test_release_workflow.py',
 '.github/scripts/test_replylib.py',
 '.github/scripts/test_retained_archive_cli_observation.py',
 '.github/scripts/test_retained_cold_observer_pipeline.py',
 '.github/scripts/test_review_funnel.py',
 '.github/scripts/test_review_resubmission.py',
 '.github/scripts/test_routing_and_cleanup_surface.py',
 '.github/scripts/test_run_concurrent_suites.py',
 '.github/scripts/test_sandbox_ci_wiring.py',
 '.github/scripts/test_sandbox_docker_layers.py',
 '.github/scripts/test_ship_set_inputs.py',
 '.github/scripts/test_site_playwright_observation.py',
 '.github/scripts/test_skill_portability.py',
 '.github/scripts/test_smarts_engine_contract.py',
 '.github/scripts/test_smarts_integration_surface.py',
 '.github/scripts/test_spike_findings_contract.py',
 '.github/scripts/test_startup_emitters.py',
 '.github/scripts/test_state_contracts_integration.py',
 '.github/scripts/test_suite_hermeticity.py',
 '.github/scripts/test_suite_observation.py',
 '.github/scripts/test_sync_core.py',
 '.github/scripts/test_tag_immutability.py',
 '.github/scripts/test_tag_publication_receipt.py',
 '.github/scripts/test_taskboardlib.py',
 '.github/scripts/test_taskwriter.py',
 '.github/scripts/test_ux_conversion.py',
 '.github/scripts/test_validate_codex_plugin.py',
 '.github/scripts/test_verdictlib.py',
 '.github/scripts/test_verify_pi_support.py',
 '.github/scripts/test_work_adopt.py',
 '.github/scripts/test_work_github.py',
 '.github/scripts/test_workflow_recovery.py',
 '.github/scripts/test_workflow_recovery_cli.py',
 '.github/scripts/test_workflow_recovery_contract.py',
 '.github/scripts/test_workflow_recovery_generator.py',
 '.github/scripts/test_workflow_recovery_hosts.py',
 '.github/scripts/validate_codex_distribution_identity.py',
 '.github/scripts/validate_codex_plugin.py',
 '.github/scripts/verify_codex_candidate_provenance.py',
 '.github/scripts/verify_codex_distribution_rulesets.py',
 '.github/scripts/verify_codex_static_candidate.py',
 '.github/scripts/verify_pi_support.py',
 '.github/workflows/academy-promotion.yml',
 '.github/workflows/ci.yml',
 '.github/workflows/codeql.yml',
 '.github/workflows/docs.yml',
 '.github/workflows/pi-promotion.yml',
 '.github/workflows/release.yml',
 'core/pysrc/_activationlib.py',
 'core/pysrc/_adrlifecycle.py',
 'core/pysrc/_adrlifecyclegit.py',
 'core/pysrc/_adrlifecyclewrite.py',
 'core/pysrc/_appendonlyconflictlib.py',
 'core/pysrc/_approvallib.py',
 'core/pysrc/_arbiterstatelib.py',
 'core/pysrc/_artifactauthoritylib.py',
 'core/pysrc/_artifactlib.py',
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
 'core/pysrc/adr-acceptance.py',
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
 'core/pysrc/workflow-recovery.py',
 'docs/state-contracts-major/PROGRAM.md',
 'docs/state-contracts-major/contracts/decisions.json',
 'docs/state-contracts-major/contracts/finding-dispositions.json',
 'docs/state-contracts-major/contracts/tasks.json',
 'plugins/ca-codex/arbiter.md',
 'plugins/ca-codex/includes/dangerous-mode.md',
 'plugins/ca-codex/includes/ops-mode.md',
 'plugins/ca-codex/includes/safety-core.md',
 'plugins/ca-pi/arbiter.md',
 'plugins/ca-pi/hooks/_host.py',
 'plugins/ca-pi/includes/dangerous-mode.md',
 'plugins/ca-pi/includes/ops-mode.md',
 'plugins/ca-pi/includes/safety-core.md',
 'plugins/ca-pi/package.json',
 'plugins/ca/arbiter.md',
 'plugins/ca/hooks/hooks.json',
 'plugins/ca/includes/dangerous-mode.md',
 'plugins/ca/includes/ops-mode.md',
 'plugins/ca/includes/safety-core.md',
 'tools/README.md',
 'tools/artifact-coverage.py',
 'tools/build-artifacts.py',
 'tools/build-host-packages.py',
 'tools/build-workflow-recovery-contract.py',
 'tools/ci-impact.py',
 'tools/ci20_baseline.py',
 'tools/ci20_inventory.py',
 'tools/codex-parity-fixture.py',
 'tools/create-artifact-examples.py',
 'tools/farm-first-pass.py',
 'tools/generate-artifact-types.py',
 'tools/go-test-timings.json',
 'tools/go_test_parallel.py',
 'tools/install-artifact-payload.py',
 'tools/live-smarts-exercise.py',
 'tools/measure-knowledge-retrieval.py',
 'tools/promote-claude-marketplace.py',
 'tools/promote-codex-marketplace.py',
 'tools/reviewer-yield.py',
 'tools/statusline-bench.py',
 'tools/statusline-screenshot.py',
 'tools/sync-core.py',
 'tools/test-artifact-mixed-schema.py',
 'tools/test-artifact-work-old-client.py',
 'tools/test_ci20_baseline.py',
 'tools/test_measurement_contracts.py',
 'tools/tribunal-eval.py'])

PYTHON_FINDING_PROFILES = {
    'hooks-single-owner-findings-v1': {"paths": _HOOK_SINGLE_OWNER_PATHS,
        'job': '[CHECK] | [CORE] | Hook contract  <os: windows-latest · partition: contracts>',
        'payload': 'major-source-inputs-hooks-single-owner',
        'upload': 'Upload single-owner hook source-test inputs',
        'roots': ('core/pysrc', '.github/scripts', '.github/workflows', 'tools'),
    },
    'impact-single-owner-findings-v1': {"paths": Q02_SOURCE_PATHS | _HOOK_SINGLE_OWNER_PATHS | frozenset(['.codearbiter/context/code-map.html',
 '.codearbiter/context/coding-standards.html',
 '.codearbiter/context/project.html',
 '.codearbiter/context/security-controls.html',
 '.codearbiter/context/tech-stack.html',
 'core/artifacts/cmd/ca-artifact/cli_boundary_contract_test.go',
 'core/artifacts/cmd/ca-artifact/main_test.go',
 'core/artifacts/go.mod',
 'core/artifacts/internal/authority/observed_event_test.go',
 'core/artifacts/internal/authority/reuse.go',
 'core/artifacts/internal/canonical/canonical_test.go',
 'core/artifacts/internal/canonical/json.go',
 'core/artifacts/internal/conformance/conformance_test.go',
 'core/artifacts/internal/contextdocument/assistive_recovery_test.go',
 'core/artifacts/internal/contextdocument/contract_test.go',
 'core/artifacts/internal/contextdocument/document_selection.go',
 'core/artifacts/internal/contextdocument/evidence_test.go',
 'core/artifacts/internal/contextdocument/finalization_test.go',
 'core/artifacts/internal/contextdocument/knowledge.go',
 'core/artifacts/internal/contextdocument/knowledge_test.go',
 'core/artifacts/internal/contextdocument/markdown.go',
 'core/artifacts/internal/contextdocument/markdown_test.go',
 'core/artifacts/internal/contextdocument/operations_test.go',
 'core/artifacts/internal/contextdocument/preview_contract.go',
 'core/artifacts/internal/contextdocument/preview_contract_test.go',
 'core/artifacts/internal/contextdocument/recovery_test.go',
 'core/artifacts/internal/contextdocument/refresh_test.go',
 'core/artifacts/internal/contextdocument/render.go',
 'core/artifacts/internal/contextdocument/render_test.go',
 'core/artifacts/internal/contextdocument/sections.go',
 'core/artifacts/internal/contextdocument/validation.go',
 'core/artifacts/internal/contextdocument/validation_test.go',
 'core/artifacts/internal/evidence/completion_identity_other.go',
 'core/artifacts/internal/evidence/completion_identity_unix.go',
 'core/artifacts/internal/evidence/completion_identity_windows.go',
 'core/artifacts/internal/evidence/completion_identity_windows_test.go',
 'core/artifacts/internal/evidence/completion_workspace_test.go',
 'core/artifacts/internal/evidence/launch_binding_limits_test.go',
 'core/artifacts/internal/evidence/output_contract_test.go',
 'core/artifacts/internal/evidence/review_regressions_test.go',
 'core/artifacts/internal/evidence/snapshot_bounds_test.go',
 'core/artifacts/internal/evidence/snapshot_canonical_test.go',
 'core/artifacts/internal/evidence/snapshot_hardening_test.go',
 'core/artifacts/internal/evidence/snapshot_short_other_test.go',
 'core/artifacts/internal/evidence/snapshot_short_windows_test.go',
 'core/artifacts/internal/evidence/snapshot_test.go',
 'core/artifacts/internal/evidence/verification.go',
 'core/artifacts/internal/fault/fault.go',
 'core/artifacts/internal/fault/fault_test.go',
 'core/artifacts/internal/kind/contracts.go',
 'core/artifacts/internal/kind/contracts_test.go',
 'core/artifacts/internal/model/artifact_test.go',
 'core/artifacts/internal/model/types_generated.go',
 'core/artifacts/internal/observation/completion.go',
 'core/artifacts/internal/observation/contract_test.go',
 'core/artifacts/internal/observation/native_v1_test.go',
 'core/artifacts/internal/observation/native_v2_test.go',
 'core/artifacts/internal/observation/runner_contract_test.go',
 'core/artifacts/internal/observation/sprint_test.go',
 'core/artifacts/internal/operations/assistive_test.go',
 'core/artifacts/internal/operations/capabilities_test.go',
 'core/artifacts/internal/operations/capture_boundary_test.go',
 'core/artifacts/internal/operations/catalog_bench_test.go',
 'core/artifacts/internal/operations/catalog_cap_linux_test.go',
 'core/artifacts/internal/operations/check_conflicts_test.go',
 'core/artifacts/internal/operations/completion_fixture_test.go',
 'core/artifacts/internal/operations/completion_git_diagnostics_test.go',
 'core/artifacts/internal/operations/completion_rerun_test.go',
 'core/artifacts/internal/operations/completion_review_test.go',
 'core/artifacts/internal/operations/concurrent_readers_test.go',
 'core/artifacts/internal/operations/context_assistive_test.go',
 'core/artifacts/internal/operations/context_authority_test.go',
 'core/artifacts/internal/operations/context_capability_test.go',
 'core/artifacts/internal/operations/context_finalization_test.go',
 'core/artifacts/internal/operations/context_preview_output_test.go',
 'core/artifacts/internal/operations/context_preview_reserved_test.go',
 'core/artifacts/internal/operations/context_readonly_linux_test.go',
 'core/artifacts/internal/operations/context_refresh_test.go',
 'core/artifacts/internal/operations/corrected_attempt_test.go',
 'core/artifacts/internal/operations/creation_review_scope_contract_test.go',
 'core/artifacts/internal/operations/cycle_view.go',
 'core/artifacts/internal/operations/dependency_advice_test.go',
 'core/artifacts/internal/operations/dependent_progress_history_test.go',
 'core/artifacts/internal/operations/descriptor_effects_test.go',
 'core/artifacts/internal/operations/descriptors.go',
 'core/artifacts/internal/operations/descriptors_test.go',
 'core/artifacts/internal/operations/eligible_bounds_test.go',
 'core/artifacts/internal/operations/engine_test.go',
 'core/artifacts/internal/operations/evidence_reads_test.go',
 'core/artifacts/internal/operations/farm_projection_test.go',
 'core/artifacts/internal/operations/index_page_bench_test.go',
 'core/artifacts/internal/operations/init_store_test.go',
 'core/artifacts/internal/operations/input_scope_test.go',
 'core/artifacts/internal/operations/intentional_change_test.go',
 'core/artifacts/internal/operations/knowledge_ops_test.go',
 'core/artifacts/internal/operations/knowledge_sections.go',
 'core/artifacts/internal/operations/knowledge_test.go',
 'core/artifacts/internal/operations/legacy_replay_contract_test.go',
 'core/artifacts/internal/operations/main_test.go',
 'core/artifacts/internal/operations/migration_test.go',
 'core/artifacts/internal/operations/native_recipe_portable_contract_test.go',
 'core/artifacts/internal/operations/native_v1_review_test.go',
 'core/artifacts/internal/operations/native_v2_review_test.go',
 'core/artifacts/internal/operations/next_native_boundary_contract_test.go',
 'core/artifacts/internal/operations/observed_fixture_test.go',
 'core/artifacts/internal/operations/ordinary_progress_contract_test.go',
 'core/artifacts/internal/operations/prerequisite_observation_test.go',
 'core/artifacts/internal/operations/preservation_contract_test.go',
 'core/artifacts/internal/operations/preservation_journal_test.go',
 'core/artifacts/internal/operations/project_view_test.go',
 'core/artifacts/internal/operations/protocol_boundary_test.go',
 'core/artifacts/internal/operations/protocol_test.go',
 'core/artifacts/internal/operations/read_mode_effects_test.go',
 'core/artifacts/internal/operations/read_only_windows_test.go',
 'core/artifacts/internal/operations/readiness_decision_contract_test.go',
 'core/artifacts/internal/operations/reorder_test.go',
 'core/artifacts/internal/operations/retirement_test.go',
 'core/artifacts/internal/operations/review_regression_test.go',
 'core/artifacts/internal/operations/review_regressions_test.go',
 'core/artifacts/internal/operations/smarts_epoch_test.go',
 'core/artifacts/internal/operations/sprint_active_writer_contract_test.go',
 'core/artifacts/internal/operations/sprint_authority_test.go',
 'core/artifacts/internal/operations/task_check_test.go',
 'core/artifacts/internal/operations/task_context_test.go',
 'core/artifacts/internal/operations/task_knowledge.go',
 'core/artifacts/internal/operations/verification_check_test.go',
 'core/artifacts/internal/operations/work_board_lock.go',
 'core/artifacts/internal/operations/work_board_lock_other.go',
 'core/artifacts/internal/operations/work_board_lock_unix.go',
 'core/artifacts/internal/operations/work_board_lock_windows.go',
 'core/artifacts/internal/operations/work_check_status_test.go',
 'core/artifacts/internal/operations/work_page_bench_test.go',
 'core/artifacts/internal/operations/work_project_bootstrap_test.go',
 'core/artifacts/internal/operations/work_project_test.go',
 'core/artifacts/internal/operations/work_test.go',
 'core/artifacts/internal/operations/work_transition_map_test.go',
 'core/artifacts/internal/operations/work_view.go',
 'core/artifacts/internal/operations/work_view_test.go',
 'core/artifacts/internal/read/outline_bench_test.go',
 'core/artifacts/internal/read/read_test.go',
 'core/artifacts/internal/render/assets/artifact.css',
 'core/artifacts/internal/render/assets/logo.svg',
 'core/artifacts/internal/render/brand.go',
 'core/artifacts/internal/render/cycle_view.go',
 'core/artifacts/internal/render/path_values_test.go',
 'core/artifacts/internal/render/project_view.go',
 'core/artifacts/internal/render/render_test.go',
 'core/artifacts/internal/render/review_compat_test.go',
 'core/artifacts/internal/render/work_check_provenance_test.go',
 'core/artifacts/internal/render/work_view.go',
 'core/artifacts/internal/render/work_view_test.go',
 'core/artifacts/internal/repository/catalog_bench_test.go',
 'core/artifacts/internal/repository/catalog_test.go',
 'core/artifacts/internal/repository/knowledge.go',
 'core/artifacts/internal/schema/common.schema.json',
 'core/artifacts/internal/schema/context.schema.json',
 'core/artifacts/internal/schema/decomposition.schema.json',
 'core/artifacts/internal/schema/diagnostics_test.go',
 'core/artifacts/internal/schema/knowledge.schema.json',
 'core/artifacts/internal/schema/pattern_test.go',
 'core/artifacts/internal/schema/plan.schema.json',
 'core/artifacts/internal/schema/schema.go',
 'core/artifacts/internal/schema/spec.schema.json',
 'core/artifacts/internal/store/backends.go',
 'core/artifacts/internal/store/backends_test.go',
 'core/artifacts/internal/store/crash_test.go',
 'core/artifacts/internal/store/entryname.go',
 'core/artifacts/internal/store/fs_linux.go',
 'core/artifacts/internal/store/fs_other_boundary_test.go',
 'core/artifacts/internal/store/hardening_unix_test.go',
 'core/artifacts/internal/store/io_fault.go',
 'core/artifacts/internal/store/io_linux_test.go',
 'core/artifacts/internal/store/io_windows_test.go',
 'core/artifacts/internal/store/journal_contract_boundary_test.go',
 'core/artifacts/internal/store/journal_contract_denial_unix_test.go',
 'core/artifacts/internal/store/journal_contract_denial_windows_test.go',
 'core/artifacts/internal/store/journal_diagnostics_test.go',
 'core/artifacts/internal/store/journal_digest_test.go',
 'core/artifacts/internal/store/journal_scan_bench_test.go',
 'core/artifacts/internal/store/journal_scan_hardening_unix_test.go',
 'core/artifacts/internal/store/journal_scan_open_test.go',
 'core/artifacts/internal/store/journal_unreadable_linux_test.go',
 'core/artifacts/internal/store/junction_windows_test.go',
 'core/artifacts/internal/store/openflags_darwin.go',
 'core/artifacts/internal/store/openflags_windows.go',
 'core/artifacts/internal/store/openstats.go',
 'core/artifacts/internal/store/readonly_lock_windows_test.go',
 'core/artifacts/internal/store/recovery_effect_contract_test.go',
 'core/artifacts/internal/store/review_regression_test.go',
 'core/artifacts/internal/store/review_regressions_test.go',
 'core/artifacts/internal/store/store_test.go',
 'core/artifacts/internal/symbol/index_test.go',
 'core/artifacts/internal/testutil/fixtures.go',
 'core/artifacts/internal/testutil/readonly_windows.go',
 'core/artifacts/internal/testutil/root.go',
 'core/artifacts/internal/validate/input_policy.go',
 'core/artifacts/internal/validate/review_policy_test.go',
 'core/artifacts/internal/validate/validate_test.go',
 'core/artifacts/schemas/common.schema.json',
 'core/artifacts/schemas/context.schema.json',
 'core/artifacts/schemas/decomposition.schema.json',
 'core/artifacts/schemas/knowledge.schema.json',
 'core/artifacts/schemas/plan.schema.json',
 'core/artifacts/schemas/spec.schema.json',
 'core/artifacts/schemas/work.schema.json',
 'core/artifacts/testdata/compat/knowledge-paths-0.3.2.html',
 'core/artifacts/testdata/compat/plan-0.3.0.html',
 'core/artifacts/testdata/compat/spec-0.3.0.html',
 'core/artifacts/testdata/reference/plan.html',
 'core/artifacts/testdata/reference/plan.json',
 'core/artifacts/testdata/reference/spec.html',
 'core/artifacts/testdata/reference/spec.json',
 'core/artifacts/testdata/spec-plan-golden/README.md',
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
 'plugins/ca-pi/tools/test/sidebar-compositor.test.ts',
 'plugins/ca-pi/tools/test/sidebar-data.test.ts',
 'plugins/ca-pi/tools/test/sidebar-manager.test.ts',
 'plugins/ca-pi/tools/test/sidebar-probe-live.test.ts',
 'plugins/ca-pi/tools/test/sidebar-window-contract.test.ts',
 'plugins/ca-pi/tools/test/sidebar.test.ts',
 'plugins/ca-pi/tools/test/status.test.ts',
 'plugins/ca-pi/tools/test/tool-guard.test.ts',
 'plugins/ca-pi/tools/test/windows-supervisor.test.ts',
 'plugins/ca-pi/tools/test/workflow-recovery.test.ts']),
        'job': '[CHECK] | [REPO] | Impact planner contract',
        'payload': 'major-source-inputs-impact-single-owner',
        'upload': 'Upload single-owner Impact source-test inputs',
        'roots': ('core/pysrc',
 '.github/scripts',
 '.github/workflows',
 'tools',
 'plugins/ca-pi/tools/test',
 'core/artifacts',
 '.codearbiter/context'),
    },
}
PYTHON_FINDING_RECIPES = {'disposition:findings:HOOK-F01': {'profile': 'hooks-single-owner-findings-v1',
                                   'script': '.github/scripts/test_prompt_submit.py',
                                   'observation': 'finite-hookf01',
                                   'selectors': frozenset({'python:.github/scripts/test_prompt_submit.py:__main__.TestPersonaFollowsRealTransitions.test_arbiter_dangerous_arbiter_redelivers_arbiter_claude',
                                                           'python:.github/scripts/test_prompt_submit.py:__main__.TestPersonaFollowsRealTransitions.test_arbiter_dangerous_arbiter_redelivers_arbiter_codex',
                                                           'python:.github/scripts/test_prompt_submit.py:__main__.TestPersonaFollowsRealTransitions.test_compaction_redelivers_the_current_mode_once',
                                                           'python:.github/scripts/test_prompt_submit.py:__main__.TestPersonaFollowsRealTransitions.test_double_denied_delivery_record_update_reports_remaining_limit',
                                                           'python:.github/scripts/test_prompt_submit.py:__main__.TestPersonaFollowsRealTransitions.test_failed_audit_then_recovery_delivers_the_eventual_effective_persona',
                                                           'python:.github/scripts/test_prompt_submit.py:__main__.TestPersonaFollowsRealTransitions.test_failed_delivery_record_write_does_not_suppress_return_persona',
                                                           'python:.github/scripts/test_prompt_submit.py:__main__.TestPersonaFollowsRealTransitions.test_legacy_modeinject_marker_does_not_suppress_delivery',
                                                           'python:.github/scripts/test_prompt_submit.py:__main__.TestPersonaFollowsRealTransitions.test_new_session_gets_its_own_delivery',
                                                           'python:.github/scripts/test_prompt_submit.py:__main__.TestPersonaFollowsRealTransitions.test_ops_arbiter_ops_redelivers_ops_claude',
                                                           'python:.github/scripts/test_prompt_submit.py:__main__.TestPersonaFollowsRealTransitions.test_ops_arbiter_ops_redelivers_ops_codex',
                                                           'python:.github/scripts/test_prompt_submit.py:__main__.TestPersonaFollowsRealTransitions.test_round_trip_without_an_ordinary_prompt_between_is_not_a_transition',
                                                           'python:.github/scripts/test_prompt_submit.py:__main__.TestPersonaFollowsRealTransitions.test_unchanged_mode_and_repeated_same_mode_token_do_not_repeat_persona',
                                                           'python:.github/scripts/test_prompt_submit.py:__main__.TestPersonaFollowsRealTransitions.test_unreadable_delivery_record_fails_toward_redelivery'}),
                                   'scope': 'Actual prompt/mode persona revisit, no-op, generation/session and '
                                            'storage-failure fixture behavior; no live host or universal double-denial '
                                            'redelivery.'},
 'disposition:findings:HOOK-F03': {'profile': 'hooks-single-owner-findings-v1',
                                   'script': '.github/scripts/test_pi_payload_identity.py',
                                   'observation': 'finite-hookf03',
                                   'selectors': frozenset({'python:.github/scripts/test_pi_payload_identity.py:__main__.PiPayloadIdentityTest.test_discovery_must_be_the_exact_single_extension_and_skills',
                                                           'python:.github/scripts/test_pi_payload_identity.py:__main__.PiPayloadIdentityTest.test_malformed_manifest_refuses_and_missing_core_stays_independent',
                                                           'python:.github/scripts/test_pi_payload_identity.py:__main__.PiPayloadIdentityTest.test_missing_bare_foreign_prefix_and_wrong_type_identity_refuse',
                                                           'python:.github/scripts/test_pi_payload_identity.py:__main__.PiPayloadIdentityTest.test_real_scoped_package_and_host_agree_without_a_probe'}),
                                   'scope': 'Actual check_payload predicate and actual PiHost/package identity on '
                                            'owned files only; no doctor.main, native/npm, host probe or installed '
                                            'health.'},
 'disposition:findings:C-F05': {'profile': 'impact-single-owner-findings-v1',
                                'script': '.github/scripts/test_ci_impact.py',
                                'observation': 'finite-cf05',
                                'selectors': frozenset({'python:.github/scripts/test_ci_impact.py:__main__.WorkflowContractTest.test_docs_pull_request_selection_covers_every_push_input',
                                                        'python:.github/scripts/test_ci_impact.py:__main__.WorkflowContractTest.test_docs_validation_triggers_never_grant_deploy'}),
                                'scope': 'Actual workflow input/event and deploy-authority declaration controls; no '
                                         'Pages deployment.'},
 'disposition:findings:C-F06': {'profile': 'hooks-single-owner-findings-v1',
                                'script': '.github/scripts/test_verdictlib.py',
                                'observation': 'finite-cf06',
                                'selectors': frozenset({'python:.github/scripts/test_verdictlib.py:__main__.CheckerObservationTest.test_branch_protection_forbidden_read_is_unavailable_not_verified',
                                                        'python:.github/scripts/test_verdictlib.py:__main__.CheckerObservationTest.test_branch_protection_violation_and_compliance',
                                                        'python:.github/scripts/test_verdictlib.py:__main__.CheckerObservationTest.test_branch_protection_without_token_is_skipped',
                                                        'python:.github/scripts/test_verdictlib.py:__main__.CheckerObservationTest.test_optional_codex_host_absent_is_skipped_required_absent_is_unavailable',
                                                        'python:.github/scripts/test_verdictlib.py:__main__.CheckerObservationTest.test_payload_gate_records_first_introduction_and_invalid_base_distinctly',
                                                        'python:.github/scripts/test_verdictlib.py:__main__.CheckerObservationTest.test_tag_audit_without_token_is_skipped_and_unavailable_api_is_unavailable',
                                                        'python:.github/scripts/test_verdictlib.py:__main__.RequiredAggregationTest.test_malformed_observations_are_refused',
                                                        'python:.github/scripts/test_verdictlib.py:__main__.RequiredAggregationTest.test_missing_duplicate_or_other_source_evidence_is_not_a_pass',
                                                        'python:.github/scripts/test_verdictlib.py:__main__.RequiredAggregationTest.test_not_applicable_needs_a_declaration_and_evidence',
                                                        'python:.github/scripts/test_verdictlib.py:__main__.RequiredAggregationTest.test_only_affirmative_evidence_satisfies_a_required_check',
                                                        'python:.github/scripts/test_verdictlib.py:__main__.RequiredAggregationTest.test_ordinary_consumers_declare_their_own_accepted_outcomes',
                                                        'python:.github/scripts/test_verdictlib.py:__main__.SourceIdentityTest.test_recovery_checkout_is_distinct_from_later_workflow_event',
                                                        'python:.github/scripts/test_verdictlib.py:__main__.SourceIdentityTest.test_unavailable_checkout_is_not_replaced_by_event_identity'}),
                                'scope': 'Typed injected outcomes and required-affirmative/source/refusal contract; no '
                                         'actual branch/tag/Codex protection observation.'},
 'disposition:findings:C-F07': {'profile': 'impact-single-owner-findings-v1',
                                'script': '.github/scripts/test_payload_version_gate.py',
                                'observation': 'finite-cf07',
                                'selectors': frozenset({'python:.github/scripts/test_payload_version_gate.py:__main__.TestTheGateRefusesTheOtherDirections.test_an_invalid_BASE_manifest_is_not_first_introduction',
                                                        'python:.github/scripts/test_payload_version_gate.py:__main__.TestTheGateRefusesTheOtherDirections.test_an_unresolvable_base_fails_rather_than_passing',
                                                        'python:.github/scripts/test_payload_version_gate.py:__main__.TestTheGateStillAllowsWhatItShould.test_a_first_introduction_passes',
                                                        'python:.github/scripts/test_payload_version_gate.py:__main__.TestTheGateStillAllowsWhatItShould.test_advancing_the_version_passes',
                                                        'python:.github/scripts/test_payload_version_gate.py:__main__.TestTheGateStillAllowsWhatItShould.test_no_payload_change_passes_without_a_bump'}),
                                'scope': 'Owned Git base absent/valid/invalid/unresolved manifest distinction; no '
                                         'release qualification.'},
 'disposition:findings:T-F02': {'profile': 'hooks-single-owner-findings-v1',
                                'script': 'tools/test_measurement_contracts.py',
                                'observation': 'finite-tf02',
                                'selectors': frozenset({'python:tools/test_measurement_contracts.py:__main__.MeasurementContracts.test_failed_smarts_child_cannot_pass_from_plausible_output',
                                                        'python:tools/test_measurement_contracts.py:__main__.MeasurementContracts.test_smarts_lens_keywords_are_not_material_alternatives'}),
                                'scope': 'Actual SMARTS predicate/producer-refusal on inert output fixtures; model '
                                         'reasoning quality and whole T01 remain unassessed.'}}

def _hook_contract_recipes(script, observation, cases_by_cell):
    return {
        cell: {
            "profile": "hooks-single-owner-findings-v1",
            "script": script,
            "observation": observation,
            "selectors": frozenset(f"python:{script}:__main__.{case}" for case in cases),
        }
        for cell, cases in cases_by_cell.items()
    }


PYTHON_FINDING_RECIPES.update(_hook_contract_recipes(
    ".github/scripts/test_boundedproc.py", "finite-bounded-reader", {
        "disposition:findings:C-F08": (
            "CodexHostCommandDeadlineTest.test_hanging_codex_command_fails_with_timeout_and_containment",
            "CodexHostCommandDeadlineTest.test_a_timed_out_marketplace_add_is_a_recorded_failure",
            "PiBenchmarkReadinessDeadlineTest.test_no_ready_line_is_a_bounded_failure_with_containment",
            "PiBenchmarkReadinessDeadlineTest.test_partial_ready_line_is_refused",
            "PiBenchmarkReadinessDeadlineTest.test_immediate_exit_is_refused",
            "PiBenchmarkReadinessDeadlineTest.test_hang_after_ready_is_bounded",
            "PiBenchmarkReadinessDeadlineTest.test_well_behaved_boundary_completes",
            "PiBenchmarkReadinessDeadlineTest.test_partial_early_exit_retains_readiness_failure_when_group_signal_is_denied",
        ),
        "disposition:added_transitions:C36:added-prefetched-completion": (
            "ReadinessWaitTest.test_binary_readiness_preserves_completion_from_one_write",
            "ReadinessWaitTest.test_binary_early_eof_reports_closed_and_finishes_empty",
            "PiBenchmarkReadinessDeadlineTest.test_well_behaved_boundary_completes",
        ),
        "disposition:added_transitions:C36:added-stdin-eof": (
            "ReadinessWaitTest.test_communicate_without_input_closes_stdin_after_readiness",
        ),
        "disposition:added_transitions:C36:added-input-once": (
            "ReadinessWaitTest.test_communicate_sends_text_or_binary_input_after_readiness",
            "ReadinessWaitTest.test_communicate_timeout_retry_sends_the_original_payload_once",
        ),
        "disposition:added_transitions:C36:added-input-timeout": (
            "ReadinessWaitTest.test_unread_stdin_stays_bounded_and_cleanup_settles_writer",
        ),
        "disposition:added_transitions:C36:added-cleanup-denied": (
            "PiBenchmarkReadinessDeadlineTest.test_partial_early_exit_retains_readiness_failure_when_group_signal_is_denied",
        ),
    },
))
PYTHON_FINDING_RECIPES.update(_hook_contract_recipes(
    ".github/scripts/test_marketplace_git_channels.py", "finite-git-channel", {
        "disposition:transitions:S73:01": (
            "ClaudeChannelTests.test_channel_carries_the_native_payload_under_the_git_subdir_path",
            "ClaudeChannelTests.test_version_must_match_the_qualified_manifest",
            "ClaudeChannelTests.test_package_without_native_payload_is_refused",
        ),
        "disposition:transitions:S73:02": (
            "ClaudeChannelTests.test_channel_carries_the_native_payload_under_the_git_subdir_path",
        ),
        "disposition:transitions:S73:03": (
            "ClaudeChannelTests.test_rerun_with_identical_inputs_is_a_no_op",
        ),
        "disposition:transitions:S73:04": (
            "ClaudeChannelTests.test_same_version_with_different_bytes_is_refused",
        ),
        "disposition:transitions:S73:05": (
            "ClaudeChannelTests.test_channel_refuses_to_roll_back",
        ),
        "disposition:transitions:S73:06": (
            "ClaudeChannelTests.test_rerun_with_identical_inputs_is_a_no_op",
        ),
        "disposition:transitions:S73:07": (
            "ClaudeChannelTests.test_newer_version_advances_as_a_descendant",
            "ClaudeChannelTests.test_unknown_current_channel_version_cannot_advance",
        ),
        "disposition:transitions:S73:08": (
            "ClaudeChannelTests.test_channel_carries_the_native_payload_under_the_git_subdir_path",
            "ClaudeChannelTests.test_push_response_loss_recovers_only_by_readback_without_repush",
        ),
        "disposition:transitions:S73:09": (
            "ClaudeChannelTests.test_newer_version_advances_as_a_descendant",
            "ClaudeChannelTests.test_push_response_loss_recovers_only_by_readback_without_repush",
        ),
        "disposition:transitions:S73:10": (
            "ClaudeChannelTests.test_push_response_loss_recovers_only_by_readback_without_repush",
            "UncertainPushTests.test_conflicting_or_unobservable_readback_never_retries",
            "ClaudeChannelTests.test_readback_finds_the_promotion_after_the_channel_moved_on",
            "ClaudeChannelTests.test_readback_never_pushes",
        ),
        "disposition:transitions:S74:03": (
            "CodexGitChannelTests.test_default_git_mode_pins_the_channel_to_the_immutable_dist_tag",
            "CodexGitChannelTests.test_git_mode_needs_no_npm_package",
        ),
        "disposition:transitions:S74:04": (
            "CodexGitChannelTests.test_default_git_mode_pins_the_channel_to_the_immutable_dist_tag",
        ),
        "disposition:transitions:S74:08": (
            "CodexGitChannelTests.test_default_git_mode_pins_the_channel_to_the_immutable_dist_tag",
            "CodexGitChannelTests.test_readback_finds_the_channel_promotion_after_a_newer_release",
        ),
        "disposition:transitions:S74:09": (
            "UncertainPushTests.test_conflicting_or_unobservable_readback_never_retries",
            "CodexGitChannelTests.test_readback_finds_the_channel_promotion_after_a_newer_release",
            "CodexGitChannelTests.test_readback_refuses_a_distribution_tag_the_channel_never_promoted",
        ),
        "disposition:findings:SF15": (
            "ClaudeChannelTests.test_push_response_loss_recovers_only_by_readback_without_repush",
            "UncertainPushTests.test_conflicting_or_unobservable_readback_never_retries",
            "ClaudeChannelTests.test_unknown_current_channel_version_cannot_advance",
            "CodexGitChannelTests.test_default_git_mode_pins_the_channel_to_the_immutable_dist_tag",
            "ClaudeChannelTests.test_readback_never_pushes",
        ),
    },
))

HOOK_F02_CELL = "disposition:findings:HOOK-F02"
HOOK_F02_COMPONENTS = {'finite-hookf02-modelib': {'script': '.github/scripts/test_modelib.py',
                            'selectors': frozenset({'python:.github/scripts/test_modelib.py:__main__.TestEnterRowIsLedgerBacked.test_a_flip_whose_row_never_landed_reports_failure',
                                                    'python:.github/scripts/test_modelib.py:__main__.TestEnterRowIsLedgerBacked.test_a_writable_trail_still_reports_a_flip_and_writes_exactly_one_row',
                                                    'python:.github/scripts/test_modelib.py:__main__.TestEnterRowIsLedgerBacked.test_an_unwritable_trail_leaves_the_enter_row_owed_not_lost',
                                                    'python:.github/scripts/test_modelib.py:__main__.TestEnterRowIsLedgerBacked.test_repeat_request_recovers_an_unsettled_enter_instead_of_reporting_noop',
                                                    'python:.github/scripts/test_modelib.py:__main__.TestEnterRowIsLedgerBacked.test_repeat_request_stays_failed_when_only_an_older_session_settles',
                                                    'python:.github/scripts/test_modelib.py:__main__.TestEnterRowIsLedgerBacked.test_repeat_request_stays_failed_while_the_enter_row_cannot_settle',
                                                    'python:.github/scripts/test_modelib.py:__main__.TestEnterRowIsLedgerBacked.test_the_owed_row_replays_on_the_next_settle',
                                                    'python:.github/scripts/test_modelib.py:__main__.TestFlip.test_double_flip_to_the_same_mode_is_a_noop_with_byte_identical_log',
                                                    'python:.github/scripts/test_modelib.py:__main__.TestFlip.test_existing_debt_does_not_prove_new_transition_was_recorded',
                                                    'python:.github/scripts/test_modelib.py:__main__.TestFlip.test_explicitly_entered_arbiter_is_exited_on_its_next_transition',
                                                    'python:.github/scripts/test_modelib.py:__main__.TestFlip.test_failed_queue_and_trail_do_not_claim_persisted_debt',
                                                    'python:.github/scripts/test_modelib.py:__main__.TestFlip.test_fallback_arbiter_with_old_enter_has_no_invented_exit',
                                                    'python:.github/scripts/test_modelib.py:__main__.TestFlip.test_first_flip_transitions_and_appends_one_enter_row',
                                                    'python:.github/scripts/test_modelib.py:__main__.TestFlip.test_flip_to_the_default_arbiter_when_already_arbiter_is_also_a_noop',
                                                    'python:.github/scripts/test_modelib.py:__main__.TestFlip.test_implicit_arbiter_and_unbacked_raw_modes_have_no_invented_exit',
                                                    'python:.github/scripts/test_modelib.py:__main__.TestFlip.test_legacy_backed_dangerous_transition_keeps_history_and_records_exit',
                                                    'python:.github/scripts/test_modelib.py:__main__.TestFlip.test_marker_failure_leaves_prior_audit_and_mode_unchanged',
                                                    'python:.github/scripts/test_modelib.py:__main__.TestFlip.test_partial_pair_retries_even_with_old_requested_mode_backing',
                                                    'python:.github/scripts/test_modelib.py:__main__.TestFlip.test_same_second_cycle_debt_is_not_satisfied_by_older_rows',
                                                    'python:.github/scripts/test_modelib.py:__main__.TestFlip.test_transition_exit_is_attributed_only_to_its_session',
                                                    'python:.github/scripts/test_modelib.py:__main__.TestFlip.test_transition_exits_prior_mode_exactly_once',
                                                    'python:.github/scripts/test_modelib.py:__main__.TestFlipOutcome.test_clean_flip_outcome_is_fully_settled',
                                                    'python:.github/scripts/test_modelib.py:__main__.TestFlipOutcome.test_failure_before_marker_commit_reports_nothing_changed',
                                                    'python:.github/scripts/test_modelib.py:__main__.TestFlipOutcome.test_failure_during_owed_row_replay_keeps_order_and_counts_all_debt',
                                                    'python:.github/scripts/test_modelib.py:__main__.TestFlipOutcome.test_flip_wrapper_keeps_the_legacy_sentinels',
                                                    'python:.github/scripts/test_modelib.py:__main__.TestFlipOutcome.test_marker_committed_audit_owed_is_raw_ops_effective_arbiter',
                                                    'python:.github/scripts/test_modelib.py:__main__.TestFlipOutcome.test_owed_row_settles_at_restart_without_duplicate_history',
                                                    'python:.github/scripts/test_modelib.py:__main__.TestFlipOutcome.test_retry_of_same_token_settles_owed_row_once',
                                                    'python:.github/scripts/test_modelib.py:__main__.TestFlipOutcome.test_return_to_arbiter_with_owed_row_reports_effective_arbiter',
                                                    'python:.github/scripts/test_modelib.py:__main__.TestFlipOutcome.test_unbacked_raw_with_no_owed_row_can_still_be_settled',
                                                    'python:.github/scripts/test_modelib.py:__main__.TestSettleGenericModeExitRow.test_interrupted_mode_exit_row_is_owed_and_settles_exactly_once'})},
 'finite-hookf01': {'script': '.github/scripts/test_prompt_submit.py',
                    'selectors': frozenset({'python:.github/scripts/test_prompt_submit.py:__main__.TestFlipMessagesReportTheActualOutcome.test_bare_mode_reports_effective_and_the_unbacked_raw_marker',
                                            'python:.github/scripts/test_prompt_submit.py:__main__.TestFlipMessagesReportTheActualOutcome.test_codex_envelope_carries_the_same_truthful_partial',
                                            'python:.github/scripts/test_prompt_submit.py:__main__.TestFlipMessagesReportTheActualOutcome.test_marker_write_failure_says_nothing_changed',
                                            'python:.github/scripts/test_prompt_submit.py:__main__.TestFlipMessagesReportTheActualOutcome.test_marker_written_audit_owed_names_raw_effective_and_next_action',
                                            'python:.github/scripts/test_prompt_submit.py:__main__.TestFlipMessagesReportTheActualOutcome.test_no_runtime_mode_message_claims_modes_switch_gates',
                                            'python:.github/scripts/test_prompt_submit.py:__main__.TestFlipMessagesReportTheActualOutcome.test_return_to_arbiter_with_owed_row_does_not_claim_the_old_mode'})}}

def _finding_python_command(argv, profile, script=None):
    permitted = {row["script"] for row in PYTHON_FINDING_RECIPES.values() if row["profile"] == profile}
    if profile == "hooks-single-owner-findings-v1":
        permitted |= {row["script"] for row in HOOK_F02_COMPONENTS.values()}
        permitted.update((ROUTE_GENERATOR_SCRIPT, SF13_SYNC_SCRIPT))
    require(isinstance(argv, list) and len(argv) == 2 and all(type(value) is str and value for value in argv),
            "single-owner profile requires its unfiltered Python entry point")
    path = argv[1].replace("\\", "/")
    require(any(path == candidate or path.endswith("/" + candidate) for candidate in permitted)
            and (script is None or path == script or path.endswith("/" + script)),
            "single-owner profile entry point differs")


def _finding_python_members(repo, profile):
    _source_root_members(repo)
    spec = PYTHON_FINDING_PROFILES[profile]
    found, directories = set(), 0
    for relative in spec["roots"]:
        pending = [Path(repo) / relative]
        while pending:
            folder = pending.pop(); directories += 1
            info = folder.lstat()
            require(directories <= 512 and stat.S_ISDIR(info.st_mode) and not folder.is_symlink()
                    and not getattr(info, "st_file_attributes", 0) & stat.FILE_ATTRIBUTE_REPARSE_POINT,
                    "Python finding source namespace is unsafe or unbounded")
            for path in folder.iterdir():
                info = path.lstat()
                require(not path.is_symlink() and not getattr(info, "st_file_attributes", 0) & stat.FILE_ATTRIBUTE_REPARSE_POINT,
                        "Python finding source namespace contains a link")
                if stat.S_ISDIR(info.st_mode):
                    if path.name != "__pycache__": pending.append(path)
                else:
                    require(stat.S_ISREG(info.st_mode), "Python finding source namespace is not regular")
                    found.add(path.relative_to(repo).as_posix())
                    require(len(found) <= 2048, "Python finding source namespace exceeds bound")
    expected = {path for path in spec["paths"] if any(path.startswith(root + "/") for root in spec["roots"])}
    require(found == expected, "Python finding source namespace differs")


def original_python_entrypoint(argv, script):
    if not isinstance(argv, list) or len(argv) != 2 or not all(type(value) is str and value for value in argv):
        return False
    path = argv[1].replace("\\", "/")
    return path == script or path.endswith("/" + script)


def original_debug_entrypoint(argv, profile):
    role = DEBUG_RUNNERS.get(profile)
    return (role is not None and isinstance(argv, list) and len(argv) == 4
            and original_python_entrypoint(argv[:2], DEBUG_LAUNCHER)
            and argv[2:] == ["--run-debug-suite", role[1]])


def _q02_python_command(argv):
    require(any(original_python_entrypoint(argv, script) for script in Q02_SOURCE_SCRIPTS),
            "Q02 source profile requires an original unfiltered owning Python entry point")


def source_profile(profile=SOURCE_PROFILE):
    if profile in PYTHON_COMPONENT_PROFILES:
        return PYTHON_COMPONENT_PROFILES[profile]
    if profile in PYTHON_FINDING_PROFILES:
        return {key: value for key, value in PYTHON_FINDING_PROFILES[profile].items() if key != "roots"}
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
            or any(relative in spec["paths"] for spec in PYTHON_COMPONENT_PROFILES.values())
            or any(relative in paths for paths in TS_PROFILE_PATHS.values())
            or any(relative in spec["paths"] for spec in PYTHON_FINDING_PROFILES.values())),
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
    if profile in PYTHON_FINDING_PROFILES:
        _finding_python_members(repo, profile)
    elif profile == HOOK_REVIEW_SOURCE_PROFILE:
        _source_root_members(repo)
        _hook_review_members(repo)
    elif profile in (SOURCE_PROFILE, Q02_SOURCE_PROFILE, *PYTHON_COMPONENT_PROFILES): _source_root_members(repo)
    elif profile == SDK_SOURCE_PROFILE: _sdk_source_members(repo)
    else: _ts_members(repo, profile)
    if profile == CATALOG_SOURCE_PROFILE:
        current = {path.relative_to(repo).as_posix() for path in (repo / "plugins/ca/commands").glob("*.md")
                   if path.stem.upper() != "INDEX"}
        require(current == CATALOG_COMMAND_PATHS, "command catalog source namespace differs")
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
            and record["workflow"] == ".github/workflows/ci.yml"
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
            and binding["format"] == SOURCE_BINDING
            and binding["payload_name"] == spec["payload"]
            and binding["manifest_sha256"] == payload.get("source_manifest_sha256")
            and type(payload.get("source_upload_job_id")) is int and payload.get("source_upload_job_id") == job_id,
            "source test payload binding missing or differs")
    debug = original_debug_entrypoint(observed.get("argv"), binding["profile"])
    if debug:
        require(observed.get("producer") == "python-test-result-observer" and observed.get("test_result_scope") == OUTER_UNITTEST_RESULT,
                "debug suite requires the original entrypoint runner results")
    elif binding["profile"] in PYTHON_FINDING_PROFILES:
        require(observed.get("producer") == "python-test-result-observer", "single-owner profile requires original Python observer")
        _finding_python_command(observed.get("argv"), binding["profile"])
    elif binding["profile"] == HOOK_REVIEW_SOURCE_PROFILE:
        require(observed.get("producer") == "python-test-result-observer", "hook review profile requires original Python observer")
        _hook_review_python_command(observed.get("argv"))
    elif binding["profile"] == Q02_SOURCE_PROFILE:
        require(observed.get("producer") == "python-test-result-observer", "Q02 source profile requires original Python observer")
        _q02_python_command(observed.get("argv"))
    elif binding["profile"] in PYTHON_COMPONENT_PROFILES:
        require(observed.get("producer") == "python-test-result-observer"
                and any(original_python_entrypoint(observed.get("argv"), script) for script in spec["scripts"]),
                "component source profile requires original Python observer")
    elif binding["profile"] == SDK_SOURCE_PROFILE:
        require(observed.get("producer") == "python-test-result-observer", "SDK source profile requires original Python observer")
        _sdk_python_command(observed.get("argv"))
    elif binding["profile"] != SOURCE_PROFILE:
        require(observed.get("producer") == "vitest-json-observer", "TS source profile requires original Vitest observer")
    record = payload.get("documents", {}).get(SOURCE_MANIFEST)
    validate_source_manifest(record, req, job_name, payload.get("members", []))
    require(record["profile"] == binding["profile"], "source test manifest profile differs")
    if debug and binding["profile"] == DEBUG_LOCKED_PROFILE:
        lock_sha = next(row["sha256"] for row in record["members"] if row["path"] == DEBUG_LOCK_PATH)
        require(observed.get("debug_runtime") == {"python": "3.14", "lock_sha256": lock_sha},
                "debug suite locked interpreter differs from retained source")
    require(next(row["sha256"] for row in payload["members"] if row["path"] == SOURCE_MANIFEST)
            == binding["manifest_sha256"], "source test manifest digest differs")


def source_component(profile, script, artifact_prefix, upload, member, cases):
    module = PurePosixPath(script).stem if script in (DEBUG_HANDOFF_SUITE, DEBUG_WORKFLOW_SUITE) else "__main__"
    return {"profile": profile, "script": script, "artifact_prefix": artifact_prefix,
            "upload": upload, "member": member,
            "selectors": sorted(f"python:{script}:{module}.{case}" for case in cases)}


def route_release_component(cases):
    return source_component(ROUTE_RELEASE_SOURCE_PROFILE, ROUTE_RELEASE_SOURCE_SCRIPT,
        "route-release-state-observation-", "Retain original release-state classifier observation",
        "route-release-state-observation.json", cases)


def route_compatibility_component(cases):
    return source_component(ROUTE_RELEASE_SOURCE_PROFILE, ROUTE_COMPATIBILITY_SCRIPT,
        "route-compatibility-observation-", "Retain original route compatibility observation",
        "route-compatibility-observation.json", cases)


def route_generator_component(cases):
    return source_component("hooks-single-owner-findings-v1", ROUTE_GENERATOR_SCRIPT,
        "python-source-observations-", "Retain original Python source-test observations",
        "python-route-generator-observation.json", cases)


ROUTE_RELEASE_COMPONENT = route_release_component((
    "ReleaseStateClassifierTest.test_absent_tag_and_absent_release_is_a_planned_candidate",
    "ReleaseStateClassifierTest.test_exact_non_draft_release_is_published",
    "ReleaseStateClassifierTest.test_tag_without_a_release_is_not_publication",
    "ReleaseStateClassifierTest.test_draft_release_is_not_publication",
    "ReleaseStateClassifierTest.test_api_unavailability_is_distinct_and_fail_closed",
    "ReleaseStateClassifierTest.test_release_tag_mismatch_is_not_publication",
    "ReleaseStateClassifierTest.test_release_target_mismatch_is_not_publication",
    "ReleaseStateClassifierTest.test_tag_payload_mismatch_is_not_publication",
    "ObserveIntegrationTest.test_exact_tags_payloads_and_release_responses_pass_end_to_end",
    "ObserveIntegrationTest.test_observer_refuses_missing_retirement_prerequisites_or_unknown_policy",
    "ObserveIntegrationTest.test_tag_only_response_fails_the_aggregate_end_to_end",
))
ROUTE_GENERATOR_REVIEW_COMPONENT = route_generator_component((
    "CommandCatalogTest.test_real_registry_taxonomy_and_host_gaps_are_frozen",
    "CommandCatalogTest.test_retirement_policy_is_closed_and_rendered_from_its_owner",
    "ReviewFeedbackRegressionTest.test_tribunal_lens_directory_matches_each_host_surface",
))


SOURCE_FINDING_COMPOSITIONS = {
    DEBUG_RESUBMISSION_FINDING: (
        source_component(DEBUG_LOCKED_PROFILE, DEBUG_HANDOFF_SUITE, "debug-reference-observation-",
            "Retain original locked debug reference observation", "debug-reference-observation.json", (
                "HandoffByteDecoderTest.test_utf8_byte_and_depth_limits_accept_exact_boundaries",
                "PrivateDebugEntryTest.test_corrected_resubmission_contract",
            )),
        source_component(DEBUG_HOOK_PROFILE, DEBUG_WORKFLOW_SUITE, "python-source-observations-",
            "Retain original Python source-test observations", "python-debug-workflow-observation.json", (
                "CorrectedResubmissionSurfaceTest.test_every_rendered_resource_allows_a_corrected_resubmission",
            )),
        source_component(RECOVERY_RUNTIME_PROFILE, DEBUG_RESUBMISSION_SCRIPT, "review-resubmission-observation-",
            "Retain original review resubmission observation", "review-resubmission-observation.json", (
                "ReviewResubmissionTest.test_changed_target_and_contract_are_captured_fresh_and_stale_child_cannot_pass",
                "ReviewResubmissionTest.test_changes_requested_and_block_are_never_success_by_resubmitting",
                "ReviewResubmissionTest.test_denied_unknown_and_arbitrary_terminal_failure_cannot_be_cleared",
                "ReviewResubmissionTest.test_exact_retry_after_each_persisted_boundary_never_creates_another_successor",
                "ReviewResubmissionTest.test_malformed_first_report_gets_fresh_linked_capture_without_mutating_original",
            )),
    ),
    SF13_CELL: (
        source_component(SOURCE_PROFILE, ".github/scripts/test_generated_output.py",
            "python-source-observations-", "Retain original Python source-test observations",
            "python-publisher-observation.json", (
            'GeneratedOutputTests.test_concurrent_writer_refuses_without_deleting_other_marker',
            'GeneratedOutputTests.test_consumers_refuse_any_pending_contract_publication',
            'GeneratedOutputTests.test_foreign_target_refuses_and_handwritten_files_survive',
            'GeneratedOutputTests.test_late_rename_failure_rolls_back_and_clean_rerun_converges',
            'GeneratedOutputTests.test_late_stage_failure_preserves_old_complete_set',
            'GeneratedOutputTests.test_rollback_failure_retains_explicit_unusable_marker_and_journal',
            'GeneratedOutputTests.test_second_host_render_failure_has_no_first_host_effect',
            'GeneratedOutputTests.test_surface_write_success_changes_only_owned_drift_and_preserves_equal_files',
            'GeneratedOutputTests.test_windows_junction_ancestor_and_owner_refuse_before_any_effect',
            )),
        source_component("hooks-single-owner-findings-v1", SF13_SYNC_SCRIPT,
            "python-source-observations-", "Retain original Python source-test observations",
            "python-sf13-sync-observation.json", (
            'TestSyncOwnerAcceptance.test_declared_inventory_excludes_host_adapter_and_nonpython_owners',
            'TestSyncOwnerAcceptance.test_invalid_real_descriptor_refuses_before_publication_or_other_effect',
            'TestSyncOwnerAcceptance.test_later_host_publish_fault_restores_complete_set_then_rerun_converges',
            )),
    ),
    "disposition:findings:C-F04": (
        source_component(Q02_SOURCE_PROFILE, ".github/scripts/test_release_workflow.py",
            "python-source-observations-", "Retain original Python source-test observations",
            "python-q02-release-observation.json", (
                "SourceSelectionTest.test_route_publication_is_observed_after_every_target_settles",
            )),
        ROUTE_RELEASE_COMPONENT,
    ),
    "disposition:findings:SF14": (
        route_generator_component(("CommandCatalogTest.test_retirement_policy_is_closed_and_rendered_from_its_owner",)),
        ROUTE_RELEASE_COMPONENT,
        route_compatibility_component((
            "CommandRouteCompatibilityTest.test_source_route_set_is_frozen_except_explicit_retirement",
            "CommandRouteCompatibilityTest.test_canonical_argument_hints_expose_modes_without_stealing_pr_titles",
            "CommandRouteCompatibilityTest.test_registry_has_the_verified_taxonomy_and_only_safe_replacements",
            "CommandRouteCompatibilityTest.test_package_descriptions_do_not_freeze_inventory_counts",
            "CommandRouteCompatibilityTest.test_ra11_governance_and_operator_prose_remains_unambiguous",
            "CommandRouteCompatibilityTest.test_legacy_bodies_are_byte_frozen_except_for_one_migration_notice",
            "CommandRouteCompatibilityTest.test_markdown_format_procedures_stay_byte_frozen_in_their_references",
            "CommandRouteCompatibilityTest.test_default_canonical_bodies_are_byte_frozen_except_for_additive_modes",
            "CommandRouteCompatibilityTest.test_status_recovery_projection_keeps_exact_read_only_bounded_contract",
            "CommandRouteCompatibilityTest.test_status_recovery_normalization_does_not_hide_unrelated_body_drift",
            "CommandRouteCompatibilityTest.test_mode_markers_and_notices_close_over_each_safe_replacement",
            "CommandRouteCompatibilityTest.test_compatibility_clock_starts_only_on_independent_publication",
            "CommandRouteCompatibilityTest.test_first_containing_declarations_are_stable_when_manifests_advance",
        )),
    ),
    CATALOG_FINDING_CELL: (
        source_component(CATALOG_SOURCE_PROFILE, CATALOG_SCRIPT,
            "command-catalog-observation-", "Retain original command catalog observation", "command-catalog-observation.json", (
                "CommandCatalogGuardTest.test_exact_catalog_passes",
                "CommandCatalogGuardTest.test_extra_catalog_route_fails",
                "CommandCatalogGuardTest.test_live_generated_catalog_is_exact",
                "CommandCatalogGuardTest.test_missing_catalog_route_fails",
            )),
        ROUTE_GENERATOR_REVIEW_COMPONENT,
        source_component(HOOK_REVIEW_SOURCE_PROFILE, HOOK_REVIEW_SOURCE_SCRIPT,
            "python-source-observations-", "Retain original Python source-test observations",
            "python-hook-review-observation.json", (
                selector.split(":__main__.", 1)[1] for selector in HOOK_REVIEW_FINDING_SELECTORS
            )),
    ),
    "disposition:findings:W-F09": (
        ROUTE_GENERATOR_REVIEW_COMPONENT,
        route_release_component((
            "ObserveIntegrationTest.test_observer_refuses_missing_retirement_prerequisites_or_unknown_policy",
            "ReleaseStateClassifierTest.test_api_unavailability_is_distinct_and_fail_closed",
            "ReleaseStateClassifierTest.test_draft_release_is_not_publication",
            "ReleaseStateClassifierTest.test_tag_without_a_release_is_not_publication",
        )),
        route_compatibility_component((
            "CommandRouteCompatibilityTest.test_compatibility_clock_starts_only_on_independent_publication",
            "CommandRouteCompatibilityTest.test_source_route_set_is_frozen_except_explicit_retirement",
        )),
    ),
}


def source_finding_profiles(cells):
    readiness.require(isinstance(cells, list) and all(type(cell) is str and (cell in SOURCE_FINDING_COMPOSITIONS
                                                                            or cell in RECOVERY_FINDING_CELLS) for cell in cells)
                      and cells == sorted(set(cells)), "invalid original source finding composition selection")
    return sorted({component["profile"] for cell in cells
                   for component in SOURCE_FINDING_COMPOSITIONS.get(cell, RECOVERY_COMPONENTS)})


def source_member_digest(rows):
    data = [[row["path"], row["bytes"], row["sha256"]] for row in rows]
    return readiness.digest(json.dumps(data, separators=(",", ":")).encode("utf-8"))


def source_finding_input_pins(cells, source, load):
    return {profile: source_profile_input_pin(profile, source, load) for profile in source_finding_profiles(cells)}


def source_profile_input_pin(profile, source, load):
    rows = []
    for path in sorted(source_profile(profile)["paths"]):
        raw = load(source, path)
        rows.append({"path": path, "bytes": len(raw), "sha256": readiness.digest(raw)})
    return source_member_digest(rows)


def source_component_archive(archive, member, *, source_paths=None, shared=False):
    limit = (64 if source_paths is not None else 8) * 1024 * 1024
    readiness.require(len(archive) <= limit, "original component archive exceeds bound")
    with zipfile.ZipFile(io.BytesIO(archive)) as zipped:
        entries = zipped.infolist()
        readiness.require(len(entries) <= 4096, "original component archive has too many members")
        names = [info.filename for info in entries if not info.is_dir()]
        readiness.require(len(set(names)) == len(names) and member in names
                          and sum(info.file_size for info in entries) <= limit,
                          "original component archive population or size differs")
        if source_paths is not None:
            readiness.require(set(names) == source_paths | {member}, "original component source archive membership differs")
        elif shared:
            readiness.require(len(names) <= 32 and all(name.startswith("python-") and name.endswith("-observation.json")
                              and "/" not in name for name in names), "original Python observation archive membership differs")
        else:
            readiness.require(names == [member], "original component observation archive membership differs")
        readiness.require(zipped.getinfo(member).file_size <= 1024 * 1024, "original component document exceeds bound")
        members = readiness.members(archive)
        return json.loads(zipped.read(member), object_pairs_hook=unique), members


def source_component_job(spec, run, jobs):
    matches = [job for job in jobs if job.get("name") == spec["job"]]
    readiness.require(len(matches) == 1, "exact original component job required")
    job = matches[0]
    readiness.require(type(job.get("id")) is int and job["id"] > 0 and job.get("run_id") == run["id"]
                      and job.get("run_attempt") == run["run_attempt"] and job.get("status") == "completed"
                      and job.get("conclusion") == "success", "original component job did not succeed in the selected attempt")
    return job


def source_component_evidence(component, req, run, artifacts, jobs, *, job_log=None, installation=None):
    profile = component["profile"]
    spec = source_profile(profile)
    job = source_component_job(spec, run, jobs)
    name = component["artifact_prefix"] + f"{req['source_commit']}-{run['id']}-{run['run_attempt']}"
    source = [artifact for artifact in artifacts if artifact.get("name") == spec["payload"]]
    captures = [artifact for artifact in artifacts if artifact.get("name") == name]
    readiness.require(len(source) == len(captures) == 1 and source[0].get("id") != captures[0].get("id"),
                      "exact original component artifact required")
    source, capture = source[0], captures[0]
    readiness.require(all(type(item.get("size_in_bytes")) is int and 0 < item["size_in_bytes"] <= limit
                          for item, limit in ((source, 64 << 20), (capture, 8 << 20))),
                      "original component archive metadata exceeds bound")
    log = readiness.api(f"actions/jobs/{job['id']}/logs", binary=True) if job_log is None else job_log
    readiness.validate_upload(job, source, spec["upload"], job_log=log)
    readiness.validate_upload(job, capture, component["upload"], job_log=log)
    source_archive = readiness.artifact_bytes(source, req)
    manifest, members = source_component_archive(source_archive, SOURCE_MANIFEST, source_paths=spec["paths"])
    validate_source_manifest(manifest, req, job["name"], members)
    readiness.require(manifest["profile"] == profile and source_member_digest(manifest["members"]) == req["source_finding_inputs"][profile],
                      "original component source bytes differ from the immutable source")
    capture_archive = readiness.artifact_bytes(capture, req)
    observed, _ = source_component_archive(capture_archive, component["member"],
                                           shared=component["artifact_prefix"] == "python-source-observations-")
    argv = observed.get("argv") if isinstance(observed, dict) else None
    script = component["script"]
    if script in (DEBUG_HANDOFF_SUITE, DEBUG_WORKFLOW_SUITE):
        command_matches = original_debug_entrypoint(argv, profile) and argv[3] == script
    else:
        command_matches = original_python_entrypoint(argv, script)
    readiness.require(isinstance(observed, dict) and observed.get("format") == OBSERVATION
                      and observed.get("source_commit") == req["source_commit"] and observed.get("source_tree") == req["source_tree"]
                      and type(observed.get("ci_run_id")) is int and observed["ci_run_id"] == run["id"]
                      and observed.get("clean") is True and observed.get("source_stable") is True
                      and observed.get("proof_kind") == "source-test" and observed.get("producer") == "python-test-result-observer"
                      and type(observed.get("exit_code")) is int and observed["exit_code"] == 0
                      and command_matches,
                      "original component observation is absent, stale, filtered or unsuccessful")
    admit_source_observation(observed, {"source_manifest_sha256": next(row["sha256"] for row in members
        if row["path"] == SOURCE_MANIFEST), "source_upload_job_id": job["id"], "members": members,
        "documents": {SOURCE_MANIFEST: manifest}}, req, job["name"], job["id"])
    if component["script"] == ROUTE_COMPATIBILITY_SCRIPT:
        readiness.require(observed.get("test_result_scope") == OUTER_UNITTEST_RESULT,
                          "route compatibility requires the original entrypoint runner results")
    tests = observed.get("tests")
    readiness.require(isinstance(tests, list) and len(tests) <= MAX_TESTS
                      and all(isinstance(test, dict) and set(test) == {"id", "result"}
                              and type(test["id"]) is str and 0 < len(test["id"].encode("utf-8")) <= MAX_TEST_ID_BYTES
                              for test in tests), "invalid or unbounded original component named outcomes")
    outcomes = {test["id"]: test["result"] for test in tests}
    readiness.require(len(outcomes) == len(tests) and all(outcomes.get(selector) == "passed" for selector in component["selectors"]),
                      "selected named test missing, repeated, skipped or failed in original component")
    binary_fields = {}
    if component["script"] in RECOVERY_INSTALLED_SCRIPTS:
        _, fixture = RECOVERY_INSTALLED_SCRIPTS[component["script"]]
        readiness.require(installation is not None and observed.get("workflow_recovery_installation") == {
            "format": "codearbiter.workflow-recovery-installation/1", "fixture": fixture, "platform": RECOVERY_NATIVE_PLATFORM,
            "installation": installation, "fixture_copy": installation,
            "hosts": dict.fromkeys(("claude", "codex", "pi"), installation),
        }, "workflow recovery consumed installation differs from the original native archive")
        binary_fields = {"consumed_native_installation": installation}
    return ({"job_id": job["id"], "run_attempt": run["run_attempt"], "source_artifact_id": source["id"],
             "observation_artifact_id": capture["id"], "observation_archive_sha256": readiness.digest(capture_archive),
             "selectors": component["selectors"], **binary_fields},
            {"artifact_id": source["id"], "archive_sha256": readiness.digest(source_archive), "members": members})


def source_finding_evidence(req, artifacts, jobs, *, run=None, producing=False):
    readiness.require(SF13_CELL not in req.get("cells", ()),
                      "SF13 requires both original Core and Docs evidence")
    cells = req.get("source_finding_composite_cells", [])
    profiles = source_finding_profiles(cells)
    if not cells:
        return {}, {}
    pins = req.get("source_finding_inputs")
    readiness.require(set(cells) <= set(req["cells"]) and isinstance(pins, dict) and set(pins) == set(profiles)
                      and all(type(pin) is str and readiness.DIGEST.fullmatch(pin) for pin in pins.values()),
                      "original component recipe lacks immutable source inputs")
    if run is None:
        run = readiness.api(f"actions/runs/{req['ci_run_id']}")
    readiness.validate_run(run, req, producing=producing)
    readiness.require(type(run.get("run_attempt")) is int and run["run_attempt"] > 0, "original component run attempt missing")
    rows, payloads = {}, {}
    recovery = None
    for cell in cells:
        if cell in RECOVERY_FINDING_CELLS:
            if recovery is None:
                recovery, recovery_payloads = workflow_recovery_evidence(req, run, artifacts, jobs)
                payloads.update(recovery_payloads)
            rows[cell] = {"cell": cell, "result": "PASSED", **recovery}
            continue
        components, owners, captures, capture_members = [], {}, {}, set()
        for component in SOURCE_FINDING_COMPOSITIONS[cell]:
            evidence, payload = source_component_evidence(component, req, run, artifacts, jobs)
            components.append(evidence)
            identity = (evidence["job_id"], payload["artifact_id"])
            readiness.require(owners.setdefault(component["profile"], identity) == identity,
                              "components under the same source profile must share original job and source payload")
            readiness.require(payloads.setdefault(payload["artifact_id"], payload) == payload,
                              "original source payload bytes differ between components")
            capture_role = (evidence["job_id"], component["artifact_prefix"], component["upload"])
            capture_member = (capture_role, component["member"])
            readiness.require(captures.setdefault(capture_role, evidence["observation_artifact_id"]) == evidence["observation_artifact_id"]
                              and capture_member not in capture_members,
                              "original shared observation archive member is ambiguous or repeated")
            capture_members.add(capture_member)
        identities = readiness.bounded_payload_ids(sorted(artifact_id for _, artifact_id in owners.values()),
                                                   limit=3 if cell in (CATALOG_FINDING_CELL, DEBUG_RESUBMISSION_FINDING) else 2)
        expected_jobs = {source_profile(profile)["job"] for profile in owners}
        readiness.require(len({job_id for job_id, _ in owners.values()}) == len(expected_jobs),
                          "original source profiles require their exact owning jobs")
        readiness.require(len({*identities, *captures.values()}) == len(identities) + len(captures),
                          "each original component requires distinct source and observation artifacts")
        rows[cell] = {"cell": cell, "result": "PASSED", "source_components": components,
                      "evidence_artifact_ids": identities}
    return rows, payloads


RECOVERY_RUNTIME_COMPONENT = source_component(
    RECOVERY_RUNTIME_PROFILE, RECOVERY_RUNTIME_SCRIPT, "workflow-recovery-runtime-observation-",
    "Retain original workflow recovery runtime observation", "workflow-recovery-runtime-observation.json", (
        "RecoveryRuntimeTest.test_denial_and_explicit_stop_are_not_cleared_by_correction",
        "RecoveryRuntimeTest.test_every_declared_producer_captures_before_terminal_effect",
        "RecoveryRuntimeTest.test_legacy_origin_in_archive_is_reused_without_recreating_work",
        "RecoveryRuntimeTest.test_multiprocess_claim_correct_and_settle_races_preserve_one_winner",
        "RecoveryRuntimeTest.test_pages_and_stale_cursor_never_claim_a_complete_empty_scan",
        "RecoveryRuntimeTest.test_partial_registration_retains_exact_completed_and_remaining_ids",
        "RecoveryRuntimeTest.test_process_crash_after_target_and_during_settlement_never_duplicates",
        "RecoveryRuntimeTest.test_process_crash_at_each_registration_commit_boundary",
        "RecoveryRuntimeTest.test_real_legacy_target_response_loss_reconciles_without_duplicate",
    ))
RECOVERY_COMPONENTS = (RECOVERY_RUNTIME_COMPONENT,
    source_component(RECOVERY_RUNTIME_PROFILE, ".github/scripts/test_workflow_recovery_cli.py",
        "workflow-recovery-cli-observation-", "Retain original workflow recovery CLI observation",
        "workflow-recovery-cli-observation.json", (
            "InstalledRecoveryTest.test_all_three_authenticated_helpers_capture_and_observe_same_local_store",
            "InstalledRecoveryTest.test_automatic_scan_child_environment_has_no_provider_credentials",
            "InstalledRecoveryTest.test_changed_native_project_and_dual_owner_hold_only_affected_obligation",
            "InstalledRecoveryTest.test_old_install_read_preserves_pending_recovery_and_targets",
            "InstalledRecoveryTest.test_real_native_work_effect_is_reconciled_after_actual_process_death",
            "InstalledRecoveryTest.test_real_stalled_optional_scan_child_is_killed_and_independent_code_continues",
            "InstalledRecoveryTest.test_unknown_helper_foreign_manifest_and_arbitrary_storage_argument_refuse",
        )),
    source_component(RECOVERY_RUNTIME_PROFILE, ".github/scripts/test_workflow_recovery_hosts.py",
        "workflow-recovery-hosts-observation-", "Retain original workflow recovery host observation",
        "workflow-recovery-hosts-observation.json", (
            "RecoveryHostTest.test_codex_pretool_context_does_not_synthesize_allow_or_change_block",
            "RecoveryHostTest.test_corrupt_inventory_notice_never_repairs_or_blocks_real_host_entry",
            "RecoveryHostTest.test_dormant_snapshot_and_missing_ledger_create_no_state",
            "RecoveryHostTest.test_pi_closed_snapshot_codec_reads_pending_state_without_any_effect",
            "RecoveryHostTest.test_real_startup_prompt_and_compaction_keep_notice_separate_from_persona",
        )),
)


def workflow_recovery_native_archive(req, run, artifacts, job, job_log):
    builds = [step for step in job.get("steps", []) if step.get("name") == "Qualify one native installation for workflow recovery"]
    readiness.require(len(builds) == 1 and builds[0].get("status") == "completed"
                      and builds[0].get("conclusion") == "success", "original workflow recovery native installation was not built")
    artifact_name = f"workflow-recovery-native-{req['source_commit']}-{run['id']}-{run['run_attempt']}"
    matches = [artifact for artifact in artifacts if artifact.get("name") == artifact_name]
    readiness.require(len(matches) == 1, "exact original workflow recovery native installation archive required")
    artifact = matches[0]
    limit = 64 * 1024 * 1024
    readiness.require(type(artifact.get("size_in_bytes")) is int and 0 < artifact["size_in_bytes"] <= limit,
                      "workflow recovery native archive metadata exceeds bound")
    readiness.validate_upload(job, artifact, "Upload original workflow recovery native installation", job_log=job_log)
    archive = readiness.artifact_bytes(artifact, req)
    readiness.require(len(archive) <= limit, "workflow recovery native archive exceeds bound")
    with zipfile.ZipFile(io.BytesIO(archive)) as zipped:
        entries = zipped.infolist()
        filenames = {"release.json", RECOVERY_NATIVE_BINARY}
        readiness.require(len(entries) == 2 and {entry.filename for entry in entries} == filenames
                          and sum(entry.file_size for entry in entries) <= limit
                          and zipped.getinfo("release.json").file_size <= 65536,
                          "workflow recovery native archive members differ or exceed bound")
        members = readiness.members(archive)
        with tempfile.TemporaryDirectory(prefix="recovery-native-identity-") as directory:
            for filename in filenames:
                (Path(directory) / filename).write_bytes(zipped.read(filename))
            identity = native_binding_owner.candidate_identity(Path(directory), RECOVERY_NATIVE_PLATFORM)
    return identity, {"artifact_id": artifact["id"], "archive_sha256": readiness.digest(archive), "members": members}


def workflow_recovery_evidence(req, run, artifacts, jobs):
    job = source_component_job(source_profile(RECOVERY_RUNTIME_PROFILE), run, jobs)
    log = readiness.api(f"actions/jobs/{job['id']}/logs", binary=True)
    installation, native_payload = workflow_recovery_native_archive(req, run, artifacts, job, log)
    captured = [source_component_evidence(component, req, run, artifacts, jobs, job_log=log, installation=installation)
                for component in RECOVERY_COMPONENTS]
    components = [evidence for evidence, _ in captured]
    source_payload = captured[0][1]
    readiness.require(all(payload == source_payload for _, payload in captured), "workflow recovery source component payloads differ")
    ids = readiness.bounded_payload_ids(sorted([source_payload["artifact_id"], native_payload["artifact_id"]]))
    readiness.require(len({*ids, *(value["observation_artifact_id"] for value in components)}) == 5,
                      "workflow recovery requires distinct original installation, source and observation artifacts")
    return ({"source_components": components, "evidence_artifact_ids": ids,
             "workflow_recovery_installation": {**installation, "artifact_id": native_payload["artifact_id"],
                                                "platform": RECOVERY_NATIVE_PLATFORM}},
            {payload["artifact_id"]: payload for payload in (source_payload, native_payload)})


def workflow_recovery_runtime_evidence(req, run, artifacts, jobs, load):
    """Read the legacy/runtime component for HOOK-B04 and W-F04."""
    readiness.validate_run(run, req)
    readiness.require(type(run.get("run_attempt")) is int and run["run_attempt"] > 0,
                      "workflow recovery original run attempt missing")
    pin = source_profile_input_pin(RECOVERY_RUNTIME_PROFILE, req["source_commit"], load)
    component_req = {**req, "source_finding_inputs": {RECOVERY_RUNTIME_PROFILE: pin}}
    evidence, payload = source_component_evidence(RECOVERY_RUNTIME_COMPONENT, component_req, run, artifacts, jobs)
    return {"schema": "codearbiter.workflow-recovery-runtime-component/1",
            "source_commit": req["source_commit"], "source_tree": req["source_tree"], "ci_run_id": req["ci_run_id"],
            "component": evidence, "source_payload": payload}


def locked_debug_runtime(repo):
    venv = Path(os.environ["RUNNER_TEMP"]).resolve(strict=True) / "artifact-conformance-venv"
    executable = venv / "bin/python"
    require(Path(os.environ["ARTIFACT_CONFORMANCE_PYTHON"]).absolute() == executable
            and Path(sys.executable).absolute() == executable and executable.is_file() and Path(sys.prefix).resolve(strict=True) == venv
            and Path(sys.base_prefix).resolve(strict=True) != venv and sys.version_info[:2] == (3, 14),
            "debug suite must retain the original Python 3.14 reference interpreter")
    return {"python": "3.14", "lock_sha256": readiness.digest(_source_file(repo, DEBUG_LOCK_PATH,
                                                                    source_profile(DEBUG_LOCKED_PROFILE)["paths"]))}


def observe_original_debug_suite(repo, argv, run_suite):
    profile = os.environ.get("MAJOR_DEBUG_SOURCE_PROFILE")
    role = DEBUG_RUNNERS.get(profile)
    require(role is not None and os.environ.get("GITHUB_JOB") == role[0], "debug suite observer job/profile differs")
    _, suite, source, output = role
    repo = Path(repo).resolve(strict=True)
    require(len(argv) == 3 and argv[1] == "--run-debug-suite"
            and Path(argv[0]).resolve(strict=True) == repo / DEBUG_LAUNCHER
            and Path(argv[2]).resolve(strict=True) == repo / suite,
            "debug suite observer requires the exact original launcher and suite")
    temp = Path(os.environ["RUNNER_TEMP"]).resolve(strict=True)
    return observe_python(repo, DEBUG_LAUNCHER, ["--run-debug-suite", suite], temp / output, temp / source,
                          profile, debug_runner=run_suite)


def observe_python(repo, script, arguments, output, source_payload=None, profile=SOURCE_PROFILE, *, debug_runner=None):
    """Run the original Python entry point once, observing actual TestResult calls."""
    repo = Path(repo).resolve(strict=True)
    script = (repo / script).resolve(strict=True)
    relative = script.relative_to(repo).as_posix()
    require(script.suffix == ".py" and not Path(output).exists() and not Path(output).is_symlink(),
            "new Python observation required")
    spec = source_profile(profile)
    debug_runtime = None
    if debug_runner is not None:
        require(relative == DEBUG_LAUNCHER and source_payload is not None
                and original_debug_entrypoint([sys.executable, relative, *arguments], profile),
                "debug suite requires the exact original unfiltered launcher")
        relative = arguments[1]
        expected_module = PurePosixPath(relative).stem
        if profile == DEBUG_LOCKED_PROFILE:
            debug_runtime = locked_debug_runtime(repo)
    elif profile in PYTHON_FINDING_PROFILES:
        require(arguments == [] and source_payload is not None, "single-owner profile requires its original unfiltered command and payload")
        _finding_python_command([sys.executable, relative], profile)
    elif profile == HOOK_REVIEW_SOURCE_PROFILE:
        require(relative == HOOK_REVIEW_SOURCE_SCRIPT and arguments == [] and source_payload is not None,
                "hook review profile requires its original unfiltered Python entry point and payload")
    elif profile == Q02_SOURCE_PROFILE:
        require(relative in Q02_SOURCE_SCRIPTS and arguments == [] and source_payload is not None,
                "Q02 source profile requires its original unfiltered Python entry point and payload")
    elif profile in PYTHON_COMPONENT_PROFILES:
        require(relative in spec["scripts"] and arguments == [] and source_payload is not None,
                "component source profile requires its original unfiltered Python entry point and payload")
    elif profile == SDK_SOURCE_PROFILE:
        require(relative == SDK_SOURCE_SCRIPT and arguments == [] and source_payload is not None,
                "SDK source profile requires its original unfiltered Python entry point and payload")
    else:
        require(profile == SOURCE_PROFILE, "Python observer requires a closed Python source profile")
    installation_output = None
    if profile == RECOVERY_RUNTIME_PROFILE and relative in RECOVERY_INSTALLED_SCRIPTS:
        role, _ = RECOVERY_INSTALLED_SCRIPTS[relative]
        installation_output = Path(output).with_name(f"workflow-recovery-{role}-installation.json")
        require(Path(os.environ.get(RECOVERY_INSTALLATION_ENV, "")) == installation_output
                and not installation_output.exists() and not installation_output.is_symlink(),
                "new owned workflow recovery installation observation required")
    before = source_identity(repo, profile)
    source_binding = source_observation_binding(repo, source_payload, before, profile) if source_payload else None
    rows, active = [], {}
    outer_only = debug_runner is not None or (profile == ROUTE_RELEASE_SOURCE_PROFILE and relative == ROUTE_COMPATIBILITY_SCRIPT)
    outer_result = None
    original_argv, original_path = sys.argv[:], sys.path[:]
    original_cwd = Path.cwd()

    def make_result(original):
        def wrapped(runner):
            nonlocal outer_result
            result = original(runner)
            if outer_result is None:
                outer_result = result
            return result
        return wrapped

    def start(original):
        def wrapped(result, test):
            if outer_only and result is not outer_result:
                return original(result, test)
            test_id = test.id()
            if debug_runner is not None:
                loaded = sys.modules.get(expected_module)
                require(test_id.startswith(expected_module + ".") and loaded is not None
                        and Path(loaded.__file__).resolve(strict=True) == repo / relative,
                        "debug named result did not originate from the approved discovered suite")
            require(isinstance(test_id, str) and 0 < len(test_id.encode("utf-8")) <= 2048
                    and len(rows) < MAX_TESTS, "Python named observation exceeds bound")
            row = {"id": "python:" + relative + ":" + test_id, "result": "unknown"}
            rows.append(row)
            active[id(test)] = row
            return original(result, test)
        return wrapped

    def outcome(original, name):
        def wrapped(result, test, *args, **kwargs):
            if (not outer_only or result is outer_result) and id(test) in active:
                active[id(test)]["result"] = name
            return original(result, test, *args, **kwargs)
        return wrapped

    def subtest(original):
        def wrapped(result, test, sub, error):
            if (not outer_only or result is outer_result) and error is not None and id(test) in active:
                active[id(test)]["result"] = "failed"
            return original(result, test, sub, error)
        return wrapped

    code = 0
    try:
        os.chdir(repo)
        sys.argv[:] = [str(script), *arguments]
        sys.path[0] = str(script.parent)
        with ExitStack() as stack:
            # In-process imports must leave the checked source tree clean,
            # even when the caller did not start Python with -B.
            stack.enter_context(mock.patch.object(sys, "dont_write_bytecode", True))
            if outer_only:
                # Nested TestResult calls are fixture controls. The entrypoint
                # runner alone owns the observed suite result.
                stack.enter_context(mock.patch.object(unittest.TextTestRunner, "_makeResult",
                                                      make_result(unittest.TextTestRunner._makeResult)))
            stack.enter_context(mock.patch.object(unittest.TestResult, "startTest", start(unittest.TestResult.startTest)))
            for name, state in (("addSuccess", "passed"), ("addFailure", "failed"), ("addError", "failed"),
                                ("addSkip", "skipped"), ("addExpectedFailure", "expected-failure"),
                                ("addUnexpectedSuccess", "failed")):
                stack.enter_context(mock.patch.object(unittest.TestResult, name, outcome(getattr(unittest.TestResult, name), state)))
            stack.enter_context(mock.patch.object(unittest.TestResult, "addSubTest", subtest(unittest.TestResult.addSubTest)))
            try:
                if debug_runner is None:
                    runpy.run_path(str(script), run_name="__main__")
                else:
                    code = debug_runner(Path(arguments[1]))
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
    if outer_only:
        require(outer_result is not None and rows, "original entrypoint runner outcomes missing")
        document["test_result_scope"] = OUTER_UNITTEST_RESULT
    if debug_runtime is not None:
        document["debug_runtime"] = debug_runtime
    if installation_output is not None and code == 0:
        require(installation_output.lstat().st_size <= 4096, "workflow recovery installation observation exceeds bound")
        document["workflow_recovery_installation"] = load_json(installation_output)
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
    require(expected.isdisjoint({*SOURCE_FINDING_COMPOSITIONS, *RECOVERY_FINDING_CELLS}),
            "composed source findings require all original owners and components")
    selected_groups = [g for g in groups if g["job"] == job_name and expected.intersection(g["cells"])]
    require({cell for g in selected_groups for cell in g["cells"]} == expected,
            "semantic cell mapping is missing, extra or assigned to another job")
    if HOOK_F02_CELL in expected:
        components = [group for group in selected_groups if HOOK_F02_CELL in group["cells"]]
        spec = source_profile("hooks-single-owner-findings-v1")
        require(len(components) == 2 and {group["observation"] for group in components} == set(HOOK_F02_COMPONENTS)
                and all(group["proof_kind"] == "source-test" and group["job"] == spec["job"]
                        and group["payload_name"] == spec["payload"] and set(group["cells"]) == {HOOK_F02_CELL}
                        for group in components),
                "HOOK-F02 requires both complete original source-test components exactly once under their owning job and payload")
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
                if profile in PYTHON_FINDING_PROFILES:
                    if cell == HOOK_F02_CELL:
                        component = HOOK_F02_COMPONENTS.get(group["observation"])
                        require(profile == "hooks-single-owner-findings-v1" and isinstance(component, dict)
                                and set(group["cells"]) == {cell} and set(group["selectors"]) == component["selectors"]
                                and job_name == spec["job"], "HOOK-F02 component script, job or complete finite selectors differ")
                        _finding_python_command(argv, profile, component["script"])
                    else:
                        recipe = PYTHON_FINDING_RECIPES.get(cell)
                        require(isinstance(recipe, dict) and recipe["profile"] == profile
                                and set(group["cells"]) == {cell} and set(group["selectors"]) == recipe["selectors"]
                                and group["observation"] == recipe["observation"] and job_name == spec["job"],
                                "single-owner profile requires its complete exact finite finding")
                        _finding_python_command(argv, profile, recipe["script"])
                elif profile == HOOK_REVIEW_SOURCE_PROFILE:
                    require(set(group["cells"]) == {HOOK_REVIEW_FINDING_CELL}
                            and set(group["selectors"]) == HOOK_REVIEW_FINDING_SELECTORS,
                            "hook finding profile requires its complete exact declarative finding composition")
                elif profile == Q02_SOURCE_PROFILE:
                    if cell in Q02_FINDING_RECIPES:
                        recipe = Q02_FINDING_RECIPES[cell]
                        require(set(group["cells"]) == {cell}
                                and set(group["selectors"]) == recipe["selectors"]
                                and job_name == Q02_SOURCE_JOB
                                and group["observation"] == recipe["observation"],
                                "Q02 profile requires the complete exact finite finding composition")
                        _q02_python_command(argv)
                        require(argv[1].replace("\\", "/") == recipe["script"]
                                or argv[1].replace("\\", "/").endswith("/" + recipe["script"]),
                                "Q02 finite finding requires its original release entry point")
                    else:
                        require(set(group["cells"]) <= Q02_SOURCE_CELLS
                                and set(group["selectors"]) <= Q02_REQUIRED_SELECTORS,
                                "Q02 implementation profile cannot qualify another task or scope")
                elif profile == SOURCE_PROFILE:
                    require(set(group["cells"]) <= SOURCE_PROFILE_CELLS, "Python profile cannot qualify another software scope")
                elif profile == SDK_SOURCE_PROFILE:
                    require(set(group["cells"]) <= SDK_SOURCE_CELLS, "SDK Python profile cannot qualify another software scope")
                elif profile in PYTHON_COMPONENT_PROFILES:
                    require(False, "source component observations require independent original admission")
                else:
                    if cell in TS_FINDING_RECIPES:
                        recipe = TS_FINDING_RECIPES[cell]
                        require(set(group["cells"]) == {cell} and profile == recipe["profile"]
                                and job_name == TS_PROFILE_JOBS[profile]
                                and set(group["selectors"]) == recipe["selectors"],
                                "TS profile requires its complete exact finite finding composition")
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
    parser.add_argument("--source-profile", default=SOURCE_PROFILE, choices=(SOURCE_PROFILE, SDK_SOURCE_PROFILE, Q02_SOURCE_PROFILE, HOOK_REVIEW_SOURCE_PROFILE, *PYTHON_COMPONENT_PROFILES, *TS_PROFILE_PATHS, *PYTHON_FINDING_PROFILES), help="closed prepare-source input profile")
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
        observations = {}
        for item in args.observation:
            key, path = item.split("=", 1)
            require(key not in observations, "duplicate observation key")
            observations[key] = load_json(path)
        payload_paths = {}
        for item in args.payload_root:
            name, path = item.split("=", 1)
            require(name not in payload_paths, "duplicate payload identity")
            payload_paths[name] = path

        cold = observations.get("cold")
        artifact_names = None
        if (len(observations) == 1 and isinstance(cold, dict)
                and cold.get("producer") == "retained-cold-package-observer-v1"
                and cold.get("proof_kind") == "retained-archive-cli"):
            artifact_names = ("artifact-host-payloads-" + source, "artifact-release-packages-" + source)
            require(set(payload_paths) == set(artifact_names), "cold report requires the exact original consumed payloads")
        req, _, artifacts, jobs = readiness.collect(
            args.repo, source, run_id, producing=True, allow_program_branch=True, producer_scope=True,
            artifact_names=artifact_names,
        )
        matching = [j for j in jobs if j["name"] == args.job_name and j.get("status") == "in_progress"]
        require(len(matching) == 1, "one current original owning job required")
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
        source_payload_names = {
            SOURCE_PAYLOAD, SDK_SOURCE_PAYLOAD, Q02_SOURCE_PAYLOAD, HOOK_REVIEW_SOURCE_PAYLOAD,
            *TS_PROFILE_PAYLOADS.values(),
            *(spec["payload"] for spec in PYTHON_FINDING_PROFILES.values()),
            "major-source-inputs-mapped-work-windows",
        }
        payloads = {}
        for name, path in payload_paths.items():
            found = [a for a in artifacts if a["name"] == name]
            require(len(found) == 1, "original consumed artifact missing or ambiguous")
            if mapped_keys and name == "ci20-native-tested-windows-2025":
                from mapped_work_observation import authenticate_native_consumption
                payloads[name] = authenticate_native_consumption(path, native_components[mapped_keys[0]])
                require(found[0].get("id") == payloads[name]["artifact_id"], "mapped native artifact API identity differs")
            else:
                payloads[name] = authenticated_payload(
                    found[0], req, path, source_job=matching[0] if name in source_payload_names else None,
                )
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
