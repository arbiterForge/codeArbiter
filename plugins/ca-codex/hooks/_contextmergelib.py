#!/usr/bin/env python3
# codeArbiter — bounded legacy code-map recovery and metadata claim refresh.
#
# Fixed target and source only. Inspection binds the real merge, all index bytes,
# conflict rendering and legacy provenance. Application rechecks that identity,
# retains all three index stages, and never adopts or edits native-owned context.
# Ordinary H-22 writes remain blocked. No import-time I/O or caller content.
#
# Public API:
#   inspect(root) -> dict                   read-only recovery binding
#   restore_head(root, expected) -> dict    restore exact HEAD blob, never stage
#   inspect_claims(root) -> dict            bind existing metadata and sources
#   refresh_claims(root, expected, claims) -> dict  selected metadata only
#   inspect_blocks(root) -> dict            bind genuine Git conflict blocks
#   resolve_blocks(root, expected, choices) -> dict  finite ours/theirs choices
#   main(argv=None) -> int                  bounded JSON CLI

import argparse
import datetime
import hashlib
import json
import os
from pathlib import Path
import re
import stat
import subprocess
import sys
import tempfile

from _appendonlyconflictlib import ResolutionError, _validate_conflicted_worktree, _write_bytes_atomic
from _artifactlib import ArtifactError, _decode, _open_pinned_regular, _trusted_directory
from _gitexec import git_executable, root_bound_git_env
from _protectedstatelib import _committed_context_journal
from _provenancelib import valid_provenance_record


TARGET = ".codearbiter/code-map.md"
PROVENANCE = ".codearbiter/.provenance/code-map.json"
MAX_BYTES = 8 << 20
OID = r"[0-9a-f]{40}(?:[0-9a-f]{24})?"
VERSION = r"(?:0|[1-9][0-9]{0,8})\.(?:0|[1-9][0-9]{0,8})\.(?:0|[1-9][0-9]{0,8})"
MANIFESTS = {
    "ca_version": "plugins/ca/.claude-plugin/plugin.json",
    "codex_version": "plugins/ca-codex/.codex-plugin/plugin.json",
    "pi_version": "plugins/ca-pi/package.json",
}
CLAIM_PATTERNS = {
    "ca_version": rb"^- `plugins/ca/` \(v(" + VERSION.encode() + rb")(?=\))",
    "codex_version": rb"^- `plugins/ca-codex/` \(v(" + VERSION.encode() + rb")(?=\))",
    "pi_version": rb"^- `plugins/ca-pi/` \(v(" + VERSION.encode() + rb")(?=[,)])",
    "metadata_date": rb"metadata refreshed on ([0-9]{4}-[0-9]{2}-[0-9]{2})(?=\.)",
}


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


def _read(path, *, single_link=False):
    _trusted_directory(path.parent, "UNSAFE_CONTEXT_PATH")
    descriptor = _open_pinned_regular(path)
    try:
        info = os.fstat(descriptor)
        _require(stat.S_ISREG(info.st_mode) and not getattr(info, "st_file_attributes", 0) & 0x400
                 and info.st_size <= MAX_BYTES, "context evidence must be a bounded regular file")
        _require(not single_link or info.st_nlink == 1, "linked claim evidence is not supported")
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


def _snapshot(requested_root, *, blocks=False):
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
    payload = ours
    rendered = None
    if blocks:
        payload, rendered = _git_conflict_blocks(root, current,
                                               _git(root, "cat-file", "blob", stages[0][1]), ours, theirs)
    else:
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
    if blocks:
        binding["resolution"] = {"operation": "resolve-blocks", "rendering": rendered,
                                 "blocks": len(payload[0])}
    digest = _hash(json.dumps(binding, sort_keys=True, separators=(",", ":")).encode())
    result = {"target": TARGET, "head": head, "merge_head": incoming,
              "head_sha256": _hash(ours), "binding": digest}
    if blocks:
        result.update(blocks=len(payload[0]), rendering=rendered,
                      sides=[{"ours_sha256": _hash(part["ours"]),
                              "theirs_sha256": _hash(part["theirs"])} for part in payload[0]])
    return root, index, current, payload, result


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


def _claim_matches(raw):
    text = raw.decode("utf-8", "strict")
    _require(re.match(r"^# Code map(?:[ \t][^\r\n]*)?\r?\n", text) is not None
             and "\0" not in text and re.search(r"^(?:<{7,}|={7,}|>{7,}|\|{7,})", text, re.M) is None,
             "a resolved UTF-8 code map is required")
    fields = {}
    for field, pattern in CLAIM_PATTERNS.items():
        matches = list(re.finditer(pattern, raw, re.M))
        _require(len(matches) <= 1, "ambiguous metadata claim")
        if matches:
            fields[field] = matches[0]
    return fields


def _claim_snapshot(requested_root):
    root = _trusted_directory(requested_root, "UNSAFE_CONTEXT_ROOT")
    actual = Path(_git(root, "rev-parse", "--show-toplevel").decode().strip()).resolve(strict=True)
    _require(actual == root, "explicit repository root required")
    git_dir = _trusted_directory(
        _git(root, "rev-parse", "--absolute-git-dir").decode().strip(), "UNSAFE_GIT_DIRECTORY")
    index = Path(_git(root, "rev-parse", "--path-format=absolute", "--git-path", "index").decode().strip())
    head = _git(root, "rev-parse", "--verify", "HEAD^{commit}").decode().strip()
    _require(re.fullmatch(OID, head), "current Git head required")
    _require(not _git(root, "ls-files", "--unmerged", "--", TARGET, PROVENANCE),
             "resolve context and provenance conflicts before claim refresh")
    tracked = _git(root, "ls-files", "--stage", "-z", "--", TARGET, PROVENANCE).split(b"\0")
    indexed = {}
    for raw in tracked:
        if raw:
            matched = re.fullmatch(r"100644 (" + OID + r") 0\t(.+)", raw.decode())
            _require(matched is not None and matched[2] in {TARGET, PROVENANCE},
                     "regular tracked legacy context required")
            indexed[matched[2]] = matched[1]
    _require(set(indexed) == {TARGET, PROVENANCE}, "tracked document and provenance required")
    current = _read(root / TARGET, single_link=True)
    fields = _claim_matches(current)
    provenance = _read(root / PROVENANCE, single_link=True)
    _legacy(provenance)
    _legacy(_git(root, "cat-file", "blob", head + ":" + PROVENANCE))
    _legacy(_git(root, "cat-file", "blob", indexed[PROVENANCE]))
    merge = None
    if os.path.lexists(git_dir / "MERGE_HEAD"):
        merge = _read(git_dir / "MERGE_HEAD").decode().strip()
        _require(re.fullmatch(OID, merge), "one current merge head required")
        _legacy(_git(root, "cat-file", "blob", merge + ":" + PROVENANCE))
    for relative in (".codearbiter/.artifacts", ".codearbiter/.artifacts/transactions"):
        if os.path.lexists(root / relative):
            _trusted_directory(root / relative, "UNSAFE_CONTEXT_JOURNAL")
    _require(_committed_context_journal(root, "code-map", TARGET) is False,
             "native or uncertain context ownership requires its writer")
    sources = {}
    for field, relative in MANIFESTS.items():
        raw = _read(root / relative, single_link=True)
        manifest = _decode(raw)
        version = manifest.get("version") if isinstance(manifest, dict) else None
        _require(isinstance(version, str) and re.fullmatch(VERSION, version),
                 "literal current source manifest version required")
        sources[field] = {"version": version, "sha256": _hash(raw)}
    binding = {"root": str(root), "git_dir": str(git_dir), "head": head, "merge_head": merge,
               "index_sha256": _hash(_read(index)), "target_sha256": _hash(current),
               "provenance_sha256": _hash(provenance), "sources": sources,
               "claims": {field: matched[1].decode("ascii") for field, matched in fields.items()},
               "inspection_date": datetime.date.today().isoformat()}
    digest = _hash(json.dumps(binding, sort_keys=True, separators=(",", ":")).encode())
    return root, index, current, sources, {**binding, "target": TARGET, "binding": digest}


def inspect_claims(root):
    return _claim_snapshot(root)[-1]


def _selected_claim_bytes(current, sources, inspection_date, claims):
    _require(type(claims) is list and 1 <= len(claims) <= 4, "select one to four existing metadata claims")
    matches = _claim_matches(current)
    edits = []
    seen = set()
    for claim in claims:
        _require(type(claim) is dict and set(claim) == {"field", "before", "after"}, "typed metadata claims required")
        field, before, after = claim["field"], claim["before"], claim["after"]
        _require(type(field) is str and field in matches and field not in seen
                 and type(before) is str and type(after) is str and before != after,
                 "select each existing metadata claim once")
        seen.add(field)
        matched = matches[field]
        _require(matched[1].decode() == before, "exact claim preimage required")
        if field == "metadata_date":
            datetime.date.fromisoformat(before)
            _require(after == inspection_date, "refresh date must be the actual inspection date")
        else:
            _require(re.fullmatch(VERSION, after) and after == sources[field]["version"],
                     "claim must match the current source manifest")
        edits.append((*matched.span(1), after.encode("ascii")))
    for start, end, replacement in sorted(edits, reverse=True):
        current = current[:start] + replacement + current[end:]
    return current


def refresh_claims(root, expected, claims):
    _require(isinstance(expected, str) and re.fullmatch(r"[0-9a-f]{64}", expected), "exact inspection binding required")
    root, index, current, sources, initial = _claim_snapshot(root)
    _require(initial["binding"] == expected, "stale claim binding; inspect again")
    _selected_claim_bytes(current, sources, initial["inspection_date"], claims)
    lock_path = Path(str(index) + ".lock")
    descriptor = os.open(lock_path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    try:
        root, _index, before, sources, fresh = _claim_snapshot(root)
        _require(fresh["binding"] == expected, "stale claim binding; inspect again")
        proposed = _selected_claim_bytes(before, sources, fresh["inspection_date"], claims)
        _write_bytes_atomic(root / TARGET, proposed, expected=before)
    finally:
        os.close(descriptor)
        lock_path.unlink()
    return {**fresh, "status": "refreshed", "staged": False, "after_sha256": _hash(proposed)}


def _marker(line):
    matched = re.fullmatch(rb"([<|=>]{7,32})(?: ([^\r\n]{1,256}))?\r?\n", line)
    if matched is None or len(set(matched[1])) != 1:
        return None
    return matched[1][:1], len(matched[1]), matched[2] or b""


def _parse_conflict_blocks(raw):
    text = raw.decode("utf-8", "strict")
    _require("\0" not in text, "UTF-8 text conflict required")
    lines = raw.splitlines(keepends=True)
    pieces, labels, marker_size = [], None, None
    cursor = 0
    prefix = []
    while cursor < len(lines):
        marker = _marker(lines[cursor])
        if marker is None:
            prefix.append(lines[cursor])
            cursor += 1
            continue
        _require(marker[0] == b"<" and marker[2] == b"HEAD", "recognized Git HEAD conflict required")
        size = marker[1]
        side_labels = [marker[2], b"base", None]
        part = {"prefix": b"".join(prefix), "ours": b"", "base": None, "theirs": b""}
        prefix = []
        cursor += 1
        side, content = "ours", []
        while cursor < len(lines):
            marker = _marker(lines[cursor])
            if marker is None:
                content.append(lines[cursor])
                cursor += 1
                continue
            _require(marker[1] == size, "consistent conflict marker size required")
            if marker[0] == b"|" and side == "ours":
                _require(marker[2], "Git base label required")
                part[side] = b"".join(content)
                side_labels[1] = marker[2]
                side, content = "base", []
            elif marker[0] == b"=" and side in {"ours", "base"}:
                _require(not marker[2], "plain Git separator required")
                part[side] = b"".join(content)
                side, content = "theirs", []
            elif marker[0] == b">" and side == "theirs":
                _require(marker[2], "Git incoming label required")
                part[side] = b"".join(content)
                side_labels[2] = marker[2]
                cursor += 1
                break
            else:
                raise ResolutionError("ambiguous or nested conflict markers")
            cursor += 1
        _require(side_labels[2] is not None, "complete conflict block required")
        if labels is None:
            labels, marker_size = side_labels, size
        _require(side_labels == labels and size == marker_size, "one consistent Git rendering required")
        pieces.append(part)
        _require(len(pieces) <= 32, "at most 32 conflict blocks supported")
    _require(pieces, "Git conflict blocks required")
    return (pieces, b"".join(prefix)), labels, marker_size


def _git_conflict_blocks(root, current, base, ours, theirs):
    payload, labels, size = _parse_conflict_blocks(current)
    modes = (("diff3", "--diff3"), ("zdiff3", "--zdiff3")) if payload[0][0]["base"] is not None else (("merge", None),)
    env = root_bound_git_env()
    env.update(GIT_OPTIONAL_LOCKS="0", GIT_TERMINAL_PROMPT="0", GIT_NO_REPLACE_OBJECTS="1")
    # Git itself must reproduce all hunk bodies and all unconflicted text from
    # the real three stages. Labels are only the current bounded marker labels;
    # no caller content, custom merge driver or arbitrary revision is executed.
    with tempfile.TemporaryDirectory(prefix="codearbiter-context-merge-") as temporary:
        paths = [Path(temporary) / name for name in ("ours", "base", "theirs")]
        for path, raw in zip(paths, (ours, base, theirs)):
            path.write_bytes(raw)
        for name, flag in modes:
            # Retain merge-file's historical default and reproduce ORT's
            # histogram alignment, still requiring the complete exact rendering.
            for algorithm in (None, "histogram"):
                args = [git_executable(), "--no-pager", "--no-lazy-fetch", "-c", "core.fsmonitor=false",
                        "-c", "core.untrackedCache=false", "-c", "merge.conflictStyle=merge",
                        "merge-file", "--stdout", "--marker-size=" + str(size)]
                if flag:
                    args.append(flag)
                if algorithm:
                    args.append("--diff-algorithm=" + algorithm)
                for label in labels:
                    args.extend(("-L", label.decode("utf-8", "strict")))
                result = subprocess.run([*args, *(str(path) for path in paths)], cwd=root, env=env,
                                        capture_output=True, shell=False, timeout=30)
                _require(len(result.stdout) <= MAX_BYTES, "Git conflict rendering is oversized")
                if 1 <= result.returncode <= 127 and result.stdout.replace(b"\r\n", b"\n") == current.replace(b"\r\n", b"\n"):
                    return payload, name
    raise ResolutionError("worktree is not Git's current three-stage rendering")


def inspect_blocks(root):
    return _snapshot(root, blocks=True)[-1]


def _choose_blocks(payload, choices):
    parts, suffix = payload
    _require(type(choices) is list and len(choices) == len(parts)
             and all(type(choice) is str and choice in {"ours", "theirs"} for choice in choices),
             "one explicit ours/theirs choice per conflict block required")
    return b"".join(part["prefix"] + part[choice] for part, choice in zip(parts, choices)) + suffix


def resolve_blocks(root, expected, choices):
    _require(isinstance(expected, str) and re.fullmatch(r"[0-9a-f]{64}", expected), "exact inspection binding required")
    root, index, _before, payload, initial = _snapshot(root, blocks=True)
    _require(initial["binding"] == expected, "stale conflict binding; inspect again")
    _choose_blocks(payload, choices)
    lock_path = Path(str(index) + ".lock")
    descriptor = os.open(lock_path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    try:
        root, _index, before, payload, fresh = _snapshot(root, blocks=True)
        _require(fresh["binding"] == expected, "stale conflict binding; inspect again")
        proposed = _choose_blocks(payload, choices)
        _write_bytes_atomic(root / TARGET, proposed, expected=before)
    finally:
        os.close(descriptor)
        lock_path.unlink()
    return {**fresh, "status": "resolved", "staged": False, "after_sha256": _hash(proposed)}


def main(argv=None):
    parser = argparse.ArgumentParser(description="Bounded fixed-target legacy code-map recovery and metadata refresh.")
    parser.add_argument("--root", required=True)
    operations = parser.add_subparsers(dest="operation", required=True)
    operations.add_parser("inspect")
    restore = operations.add_parser("restore-head")
    restore.add_argument("--expected", required=True)
    operations.add_parser("inspect-claims")
    refresh = operations.add_parser("refresh-claims")
    refresh.add_argument("--expected", required=True)
    refresh.add_argument("--claims", required=True)
    operations.add_parser("inspect-blocks")
    resolve = operations.add_parser("resolve-blocks")
    resolve.add_argument("--expected", required=True)
    resolve.add_argument("--choices", required=True)
    args = parser.parse_args(argv)
    try:
        if args.operation == "inspect":
            result = inspect(args.root)
        elif args.operation == "restore-head":
            result = restore_head(args.root, args.expected)
        elif args.operation == "inspect-claims":
            result = inspect_claims(args.root)
        elif args.operation == "refresh-claims":
            result = refresh_claims(args.root, args.expected, _decode(args.claims.encode("utf-8")))
        elif args.operation == "inspect-blocks":
            result = inspect_blocks(args.root)
        else:
            result = resolve_blocks(args.root, args.expected, _decode(args.choices.encode("utf-8")))
    except (OSError, ValueError, RuntimeError, ArtifactError, subprocess.SubprocessError):
        print("context conflict recovery refused: absent, changed, unsafe or unsupported conflict evidence", file=sys.stderr)
        return 1
    print(json.dumps(result, sort_keys=True))
    return 0
