#!/usr/bin/env python3
"""Portable producer for source-bound ADR acceptance and append-only repair."""

import argparse
from collections import Counter
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import re
import stat
import sys

import _adrlifecycle as al
import _adrlifecyclegit as lifecycle_git
from _hooklib import acquire_lock, audit_lock_key, release_lock


LEDGER_REL = ".codearbiter/decisions/adr-lifecycle.jsonl"
CANONICAL_STEM = re.compile(r"^[0-9]{4}-[a-z0-9]+(?:-[a-z0-9]+)*$")


def _git_commit(root, ref):
    result = lifecycle_git._git(root, "rev-parse", "--verify", "--end-of-options",
                                ref + "^{commit}")
    if result.returncode:
        raise ValueError("Git commit is unavailable: " + ref)
    return result.stdout.decode("ascii").strip()


def _ledger_path(root):
    path = Path(root) / ".codearbiter" / "decisions" / "adr-lifecycle.jsonl"
    for parent in (path.parent.parent, path.parent):
        if parent.is_symlink() or not parent.is_dir():
            raise ValueError("ADR decisions directory is absent or redirected")
    return path


def _file_bytes(path):
    if not path.exists() and not path.is_symlink():
        return None
    info = path.lstat()
    if (not stat.S_ISREG(info.st_mode) or path.is_symlink() or info.st_nlink != 1 or
            getattr(info, "st_file_attributes", 0) & 0x400):
        raise ValueError("lifecycle ledger is not a single-link regular file")
    return path.read_bytes()


def _events(raw):
    if raw is None:
        return []
    if raw and not raw.endswith(b"\n"):
        raise ValueError("lifecycle ledger does not end with LF")
    if raw.startswith(b"\xef\xbb\xbf") or b"\x00" in raw:
        raise ValueError("lifecycle ledger is not canonical UTF-8 text")
    return [json.loads(line) for line in raw.decode("utf-8").split("\n")
            if line.strip()]


def _append(path, before, line, root):
    lock = acquire_lock(audit_lock_key(root, path))
    if lock is None:
        raise ValueError("another writer holds the lifecycle ledger lock")
    descriptor = None
    try:
        if _file_bytes(path) != before:
            raise ValueError("lifecycle ledger changed during validation")
        flags = os.O_APPEND | os.O_WRONLY | getattr(os, "O_NOFOLLOW", 0)
        if hasattr(os, "O_BINARY"):
            flags |= os.O_BINARY
        if before is None:
            flags |= os.O_CREAT | os.O_EXCL
        descriptor = os.open(path, flags, 0o600)
        opened = os.fstat(descriptor)
        current = path.lstat()
        if (not stat.S_ISREG(opened.st_mode) or not stat.S_ISREG(current.st_mode) or
                opened.st_nlink != 1 or current.st_nlink != 1 or
                (opened.st_dev, opened.st_ino) != (current.st_dev, current.st_ino)):
            raise ValueError("lifecycle ledger changed identity before append")
        offset = 0
        while offset < len(line):
            count = os.write(descriptor, line[offset:])
            if count <= 0:
                raise ValueError("lifecycle ledger append made no progress")
            offset += count
        os.fsync(descriptor)
    finally:
        try:
            if descriptor is not None:
                os.close(descriptor)
        finally:
            release_lock(lock)


def append_acceptance(root, adr, source_commit, obligations, reviewed_by,
                      correction_reason=None):
    """Append one valid binding or correction without modifying historical bytes."""
    if not isinstance(adr, str) or not CANONICAL_STEM.fullmatch(adr):
        raise ValueError("invalid ADR stem")
    if not isinstance(source_commit, str) or not al.HEX40.fullmatch(source_commit):
        raise ValueError("source commit must be a full Git id")
    if (not isinstance(reviewed_by, str) or not reviewed_by.strip() or
            len(reviewed_by) > 500 or any(char in reviewed_by for char in "\r\n")):
        raise ValueError("independent obligation reviewer must be named")
    if (correction_reason is not None and
            (len(correction_reason) > 500 or any(char in correction_reason for char in "\r\n"))):
        raise ValueError("correction reason is malformed")
    root = Path(root).resolve()
    actual_root = lifecycle_git._git(str(root), "rev-parse", "--show-toplevel")
    if actual_root.returncode or Path(actual_root.stdout.decode("utf-8").strip()).resolve() != root:
        raise ValueError("--root must name the exact Git worktree root")
    path = _ledger_path(root)
    head = _git_commit(str(root), "HEAD")
    source = _git_commit(str(root), source_commit)
    if lifecycle_git._git(str(root), "merge-base", "--is-ancestor", source, head).returncode:
        raise ValueError("acceptance source is not an ancestor of HEAD")
    adr_rel = ".codearbiter/decisions/%s.md" % adr
    source_blob = lifecycle_git._git_blob(str(root), source, adr_rel)
    head_blob = lifecycle_git._git_blob(str(root), head, adr_rel)
    if source_blob is None or head_blob is None:
        raise ValueError("accepted ADR Git blob is unavailable")
    adr_path = root / ".codearbiter" / "decisions" / (adr + ".md")
    staged = lifecycle_git._git(str(root), "show", ":" + adr_rel)
    if (adr_path.is_symlink() or not adr_path.is_file() or
            adr_path.read_bytes() != head_blob or staged.returncode or
            staged.stdout != head_blob):
        raise ValueError("ADR worktree and index must match the committed source")
    current_status = al.parse_adr(head_blob)["status"]
    if (current_status not in ({"accepted"} if correction_reason is None
                              else {"accepted", "superseded", "rejected"}) or
            al.immutable_body(head_blob) != al.immutable_body(source_blob)):
        raise ValueError("current ADR differs from its acceptance source binding")
    committed = lifecycle_git._ledger_at(str(root), head)
    before = _file_bytes(path)
    if before != committed and (correction_reason is None or committed is None or
                                before is None or not before.startswith(committed)):
        raise ValueError("working lifecycle ledger differs from HEAD")
    staged_ledger = lifecycle_git._git(str(root), "show", ":" + LEDGER_REL)
    if ((committed is None and staged_ledger.returncode == 0) or
            (committed is not None and
             (staged_ledger.returncode != 0 or staged_ledger.stdout != committed))):
        raise ValueError("staged lifecycle ledger differs from HEAD")
    existing = _events(before)
    committed_events = _events(committed)
    if correction_reason is not None and any(
            not isinstance(item, dict) or item.get("event") != "acceptance-correction"
            for item in existing[len(committed_events):]):
        raise ValueError("uncommitted lifecycle suffix must contain only corrections")
    bound = [item for item in existing if isinstance(item, dict) and
             item.get("event") in ("acceptance", "baseline") and
             item.get("adr") == adr]
    now = datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")
    if correction_reason is None:
        if bound:
            raise ValueError("ADR already has an acceptance or baseline binding")
        event = al.acceptance_event(adr, source_blob, source, obligations, now,
                                    reviewed_by=reviewed_by)
    else:
        if not correction_reason.strip() or len(bound) != 1 or bound[0].get("event") != "acceptance":
            raise ValueError("correction requires one prior acceptance and a reason")
        original = bound[0]
        if original.get("source_commit") != source:
            raise ValueError("correction cannot change the source commit")
        replacement = al.acceptance_event(
            adr, source_blob, source, obligations, original.get("recorded_at"),
            reviewed_by=reviewed_by)
        event = {
            "schema": "adr-lifecycle/v1", "event": "acceptance-correction",
            "adr": adr, "recorded_at": now,
            "corrects_sha256": al.event_digest(original),
            "replacement": replacement, "reviewed_by": reviewed_by,
            "reason": correction_reason.strip(),
        }
    combined = existing + [event]
    stems = {item.get("adr") for item in combined if isinstance(item, dict) and
             isinstance(item.get("adr"), str)} | {adr}
    blobs = {stem: blob for stem in stems if (blob := lifecycle_git._git_blob(
        str(root), head, ".codearbiter/decisions/%s.md" % stem)) is not None}
    if correction_reason is not None:
        for prior_correction in existing[len(committed_events):]:
            target = prior_correction.get("adr")
            replacement = prior_correction.get("replacement")
            if not isinstance(target, str) or not isinstance(replacement, dict):
                raise ValueError("uncommitted correction has no valid replacement")
            target_errors = al.validate_events([replacement],
                                               {target: blobs[target]} if target in blobs else {})
            target_errors.extend(lifecycle_git.validate_committed_sources(
                str(root), [replacement]))
            if target_errors:
                raise ValueError("uncommitted correction retains invalid binding: " +
                                 "; ".join(target_errors))
    errors = al.validate_events(combined, blobs)
    errors.extend(lifecycle_git.validate_committed_sources(str(root), combined))
    if correction_reason is not None:
        prior = al.validate_events(committed_events, blobs)
        prior.extend(lifecycle_git.validate_committed_sources(str(root), committed_events))
        errors = list((Counter(errors) - Counter(prior)).elements())
    if errors:
        raise ValueError("lifecycle binding refused: " + "; ".join(errors))
    line = (json.dumps(event, sort_keys=True, separators=(",", ":"),
                       ensure_ascii=False) + "\n").encode("utf-8")
    _append(path, before, line, root)
    return event


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", required=True)
    parser.add_argument("--adr", required=True)
    parser.add_argument("--source-commit", required=True)
    parser.add_argument("--obligations-json", required=True)
    parser.add_argument("--reviewed-by", required=True)
    parser.add_argument("--correct", action="store_true")
    parser.add_argument("--reason")
    args = parser.parse_args(argv)
    if args.correct != bool(args.reason):
        parser.error("--correct and --reason must be supplied together")
    try:
        if os.path.getsize(args.obligations_json) > 1024 * 1024:
            raise ValueError("reviewed obligations file exceeds 1 MB")
        with open(args.obligations_json, encoding="utf-8") as handle:
            obligations = json.load(handle)
        event = append_acceptance(
            args.root, args.adr, args.source_commit, obligations,
            args.reviewed_by, args.reason if args.correct else None)
    except (OSError, TypeError, ValueError, lifecycle_git.GitPrerequisiteError) as exc:
        print("ADR acceptance refused: " + str(exc), file=sys.stderr)
        return 1
    print("appended %s for %s" % (event["event"], event["adr"]))
    return 0
