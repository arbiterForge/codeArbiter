#!/usr/bin/env python3
# codeArbiter — restore the committed current side of a legacy code-map conflict.
#
# Fixed target and source only. Inspection binds the real merge, all index bytes,
# conflict rendering and legacy provenance. Application rechecks that identity,
# retains all three index stages, and never adopts or edits native-owned context.
# Ordinary H-22 writes remain blocked. No import-time I/O or caller content.
#
# Public API:
#   inspect(root) -> dict                   read-only recovery binding
#   restore_head(root, expected) -> dict    restore exact HEAD blob, never stage
#   main(argv=None) -> int                  bounded JSON CLI

import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import stat
import subprocess
import sys

from _appendonlyconflictlib import ResolutionError, _validate_conflicted_worktree, _write_bytes_atomic
from _artifactlib import ArtifactError, _decode, _open_pinned_regular, _trusted_directory
from _gitexec import git_executable, root_bound_git_env
from _protectedstatelib import _committed_context_journal
from _provenancelib import valid_provenance_record


TARGET = ".codearbiter/code-map.md"
PROVENANCE = ".codearbiter/.provenance/code-map.json"
MAX_BYTES = 8 << 20
OID = r"[0-9a-f]{40}(?:[0-9a-f]{24})?"


def _require(condition, reason):
    if not condition:
        raise ResolutionError(reason)


def _hash(raw):
    return hashlib.sha256(raw).hexdigest()


def _git(root, *args):
    env = root_bound_git_env()
    env.update(GIT_OPTIONAL_LOCKS="0", GIT_TERMINAL_PROMPT="0", GIT_NO_REPLACE_OBJECTS="1")
    result = subprocess.run(
        [git_executable(), "--no-pager", "--no-lazy-fetch", "-c", "core.fsmonitor=false",
         "-c", "core.untrackedCache=false", *args],
        cwd=root, env=env, capture_output=True, shell=False, timeout=30)
    _require(result.returncode == 0 and len(result.stdout) <= MAX_BYTES, "Git conflict evidence unavailable")
    return result.stdout


def _read(path):
    _trusted_directory(path.parent, "UNSAFE_CONTEXT_PATH")
    descriptor = _open_pinned_regular(path)
    try:
        info = os.fstat(descriptor)
        _require(stat.S_ISREG(info.st_mode) and not getattr(info, "st_file_attributes", 0) & 0x400
                 and info.st_size <= MAX_BYTES, "context evidence must be a bounded regular file")
        with os.fdopen(descriptor, "rb", closefd=False) as handle:
            raw = handle.read(MAX_BYTES + 1)
        _require(len(raw) <= MAX_BYTES, "context evidence is oversized")
        return raw
    finally:
        os.close(descriptor)


def _legacy(raw):
    record = _decode(raw)
    _require(valid_provenance_record(record) and record["schema"] == 1
             and record["doc"] == "code-map", "legacy code-map provenance required; native ownership is not recoverable here")


def _snapshot(requested_root):
    root = _trusted_directory(requested_root, "UNSAFE_CONTEXT_ROOT")
    actual = Path(_git(root, "rev-parse", "--show-toplevel").decode().strip()).resolve(strict=True)
    _require(actual == root, "explicit repository root required")
    git_dir = _trusted_directory(
        _git(root, "rev-parse", "--absolute-git-dir").decode().strip(), "UNSAFE_GIT_DIRECTORY")
    index = Path(_git(root, "rev-parse", "--path-format=absolute", "--git-path", "index").decode().strip())
    head = _git(root, "rev-parse", "--verify", "HEAD^{commit}").decode().strip()
    incoming = _read(git_dir / "MERGE_HEAD").decode().strip()
    _require(re.fullmatch(OID, head) and re.fullmatch(OID, incoming), "one current merge head required")
    records = _git(root, "ls-files", "--unmerged", "-z", "--", TARGET).split(b"\0")
    stages = []
    for raw in records:
        if raw:
            matched = re.fullmatch(r"100644 (" + OID + r") ([123])\t" + re.escape(TARGET), raw.decode())
            _require(matched is not None, "regular code-map conflict stages required")
            stages.append((matched[2], matched[1]))
    _require([stage for stage, _oid in stages] == ["1", "2", "3"], "complete three-stage code-map conflict required")
    base = _git(root, "merge-base", "--all", head, incoming).decode().strip()
    _require(re.fullmatch(OID, base), "one unambiguous merge base required")
    for revision, (_stage, oid) in zip((base, head, incoming), stages):
        _require(_git(root, "rev-parse", revision + ":" + TARGET).decode().strip() == oid,
                 "index conflict no longer matches the current merge")
    current = _read(root / TARGET)
    ours = _git(root, "cat-file", "blob", stages[1][1])
    theirs = _git(root, "cat-file", "blob", stages[2][1])
    # Reuse the existing single-conflict renderer check. Unsupported renderings
    # (including a non-empty diff3 base) refuse rather than discarding human text.
    _validate_conflicted_worktree(current, b"", ours, theirs)
    provenance = _read(root / PROVENANCE)
    _legacy(provenance)
    for revision in (base, head, incoming):
        _legacy(_git(root, "cat-file", "blob", revision + ":" + PROVENANCE))
    for relative in (".codearbiter/.artifacts", ".codearbiter/.artifacts/transactions"):
        if os.path.lexists(root / relative):
            _trusted_directory(root / relative, "UNSAFE_CONTEXT_JOURNAL")
    _require(_committed_context_journal(root, "code-map", TARGET) is False,
             "native or uncertain context ownership requires its writer")
    binding = {"root": str(root), "git_dir": str(git_dir), "head": head, "merge_head": incoming,
               "stages": stages, "index_sha256": _hash(_read(index)),
               "worktree_sha256": _hash(current), "provenance_sha256": _hash(provenance)}
    digest = _hash(json.dumps(binding, sort_keys=True, separators=(",", ":")).encode())
    return root, index, current, ours, {"target": TARGET, "head": head, "merge_head": incoming,
                                        "head_sha256": _hash(ours), "binding": digest}


def inspect(root):
    return _snapshot(root)[-1]


def restore_head(root, expected):
    _require(isinstance(expected, str) and re.fullmatch(r"[0-9a-f]{64}", expected), "exact inspection binding required")
    root, index, _before, _ours, initial = _snapshot(root)
    _require(initial["binding"] == expected, "stale context conflict binding; inspect again")
    # Git's own lock blocks cooperative index writers during replacement. It is
    # removed on exit; the index itself and all unmerged stages stay byte-identical.
    lock_path = Path(str(index) + ".lock")
    descriptor = os.open(lock_path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    try:
        root, _index, before, ours, fresh = _snapshot(root)
        _require(fresh["binding"] == expected, "stale context conflict binding; inspect again")
        _write_bytes_atomic(root / TARGET, ours, expected=before)
    finally:
        os.close(descriptor)
        lock_path.unlink()
    return {**fresh, "status": "restored", "staged": False}


def main(argv=None):
    parser = argparse.ArgumentParser(description="Recover only the exact HEAD-side legacy code-map in a current Git conflict.")
    parser.add_argument("--root", required=True)
    operations = parser.add_subparsers(dest="operation", required=True)
    operations.add_parser("inspect")
    restore = operations.add_parser("restore-head")
    restore.add_argument("--expected", required=True)
    args = parser.parse_args(argv)
    try:
        result = inspect(args.root) if args.operation == "inspect" else restore_head(args.root, args.expected)
    except (OSError, ValueError, RuntimeError, ArtifactError, subprocess.SubprocessError):
        print("context conflict recovery refused: absent, changed, unsafe or unsupported conflict evidence", file=sys.stderr)
        return 1
    print(json.dumps(result, sort_keys=True))
    return 0
