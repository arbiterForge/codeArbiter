#!/usr/bin/env python3
# codeArbiter - fail-closed resolution of genuine H-05 append-only conflicts.
#
# The public entry point is resolve-append-only-conflict.py.  This module keeps
# Git inspection, byte validation, deterministic union construction, atomic
# replacement, and explicit staging testable and host-neutral.
#
# Public API:
#   resolve(target, reason, cwd=None) -> str  resolve and return repo-relative path
#   main(argv=None) -> int                    CLI contract

from __future__ import annotations

import argparse
from datetime import datetime, timezone
import os
from pathlib import Path
import stat
import subprocess
import sys
import tempfile

from _hooklib import acquire_lock, audit_lock_key, release_lock
from _gitexec import git_executable
from _protectedlib import classify_protected


BOM = b"\xef\xbb\xbf"
MAX_REASON = 500
SUPPORTED_AUDIT_PATHS = frozenset(
    {".codearbiter/overrides.log", ".codearbiter/gate-events.log"}
)


class ResolutionError(RuntimeError):
    """A surfaced, non-mutating refusal of the conflict-resolution contract."""


class ConcurrentAppendError(ResolutionError):
    """A displaced original inode changed and was restored before refusal."""

    def __init__(self, path, restored, observed=None):
        super().__init__(f"concurrent append detected while replacing '{Path(path).name}'")
        self.path = Path(path)
        self.restored = restored
        self.observed = observed


def _git(cwd, *args, input_bytes=None, check=True):
    try:
        result = subprocess.run(
            [git_executable(), *args],
            cwd=cwd,
            input=input_bytes,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            check=False,
        )
    except OSError as error:
        raise ResolutionError(f"git unavailable: {error}") from error
    if check and result.returncode != 0:
        detail = result.stderr.decode("utf-8", errors="replace").strip()
        raise ResolutionError(f"git {' '.join(args)} failed: {detail or 'unknown error'}")
    return result


def _repository_root(cwd):
    result = _git(cwd, "rev-parse", "--show-toplevel")
    try:
        raw = result.stdout.decode("utf-8", errors="strict").strip()
    except UnicodeDecodeError as error:
        raise ResolutionError("git returned an invalid UTF-8 repository root") from error
    if not raw:
        raise ResolutionError("git returned an empty repository root")
    return Path(raw).resolve()


def _relative_target(root, target):
    candidate = Path(target)
    if candidate.is_absolute():
        raise ResolutionError("target must be a repository-relative supported append-only path")
    normalized = Path(os.path.normpath(str(candidate)))
    if normalized == Path(".") or ".." in normalized.parts:
        raise ResolutionError("target must be a contained supported append-only path")
    path = root / normalized
    try:
        path.resolve(strict=False).relative_to(root)
    except ValueError as error:
        raise ResolutionError("target escapes the repository root") from error
    relative = normalized.as_posix()
    if relative not in SUPPORTED_AUDIT_PATHS or "audit" not in classify_protected(
        str(path), str(root)
    ):
        raise ResolutionError(f"'{relative}' is not a supported append-only H-05 path")
    try:
        mode = path.lstat().st_mode
    except OSError as error:
        raise ResolutionError(f"cannot inspect '{relative}': {error}") from error
    if not stat.S_ISREG(mode) or path.is_symlink():
        raise ResolutionError(f"'{relative}' is not a regular non-link file")
    return relative, path


def _validate_bytes(label, raw):
    if BOM in raw:
        raise ResolutionError(f"{label} contains a UTF-8 BOM")
    if b"\x00" in raw:
        raise ResolutionError(f"{label} contains a NUL byte")
    if b"\r" in raw:
        raise ResolutionError(f"{label} is not canonical LF text")
    try:
        raw.decode("utf-8", errors="strict")
    except UnicodeDecodeError as error:
        raise ResolutionError(f"{label} is not valid UTF-8") from error
    if raw and not raw.endswith(b"\n"):
        raise ResolutionError(f"{label} does not end with LF")


def _marker_run(line, marker):
    if not line.endswith(b"\n"):
        return 0
    body = line[:-1]
    size = 0
    while size < len(body) and body[size : size + 1] == marker:
        size += 1
    if size < 7 or (len(body) > size and body[size : size + 1] != b" "):
        return 0
    return size


def _validate_conflicted_worktree(raw, base, ours_suffix, theirs_suffix):
    """Prove the worktree is only Git's rendering of the three index stages."""
    # Git for Windows may render conflict markers and checked-out blob lines as
    # CRLF even though every index blob is canonical LF. Normalize only complete
    # CRLF pairs for comparison; lone CR remains invalid and the original bytes
    # stay untouched for rollback.
    normalized = raw.replace(b"\r\n", b"\n")
    _validate_bytes("conflicted worktree", normalized)
    if not normalized.startswith(base):
        raise ResolutionError("conflicted worktree does not preserve the merge-base prefix")
    lines = normalized[len(base) :].splitlines(keepends=True)
    starts = [(index, _marker_run(line, b"<")) for index, line in enumerate(lines)]
    starts = [(index, size) for index, size in starts if size]
    if len(starts) != 1:
        raise ResolutionError("conflicted worktree is not one recognized Git conflict rendering")
    start, marker_size = starts[0]
    separator_line = (b"=" * marker_size) + b"\n"
    separators = [index for index, line in enumerate(lines) if line == separator_line]
    ends = [
        index
        for index, line in enumerate(lines)
        if _marker_run(line, b">") == marker_size
    ]
    base_markers = [
        index
        for index, line in enumerate(lines)
        if _marker_run(line, b"|") == marker_size
    ]
    if len(separators) != 1 or len(ends) != 1 or len(base_markers) > 1:
        raise ResolutionError("conflicted worktree has ambiguous Git conflict markers")
    separator = separators[0]
    end = ends[0]
    base_marker = base_markers[0] if base_markers else None
    ours_end = base_marker if base_marker is not None else separator
    if not (start < ours_end <= separator < end):
        raise ResolutionError("conflicted worktree has out-of-order Git conflict markers")
    if base_marker is not None and b"".join(lines[base_marker + 1 : separator]):
        raise ResolutionError("conflicted worktree has unexpected merge-base conflict bytes")

    common_prefix = b"".join(lines[:start])
    ours_body = b"".join(lines[start + 1 : ours_end])
    theirs_body = b"".join(lines[separator + 1 : end])
    common_suffix = b"".join(lines[end + 1 :])
    if ours_suffix != common_prefix + ours_body + common_suffix:
        raise ResolutionError("conflicted worktree differs from the current-branch index stage")
    if theirs_suffix != common_prefix + theirs_body + common_suffix:
        raise ResolutionError("conflicted worktree differs from the incoming-branch index stage")


def _unmerged(root, relative, *, allow_resolved=False):
    result = _git(root, "ls-files", "-u", "-z", "--", relative)
    records = []
    for item in result.stdout.split(b"\0"):
        if not item:
            continue
        try:
            metadata, encoded_path = item.split(b"\t", 1)
            mode, oid, stage = metadata.decode("ascii").split(" ")
            path = encoded_path.decode("utf-8", errors="strict")
            records.append((mode, oid, int(stage), path))
        except (ValueError, UnicodeDecodeError) as error:
            raise ResolutionError("malformed unmerged index record") from error
    if allow_resolved and not records:
        return []
    if len(records) != 3 or [record[2] for record in records] != [1, 2, 3]:
        raise ResolutionError("target is not in a complete three-stage conflict")
    if any(record[3] != relative for record in records):
        raise ResolutionError("unmerged index path does not match the requested target")
    if any(record[0] != "100644" for record in records):
        raise ResolutionError("append-only conflict stages must all be regular 100644 blobs")
    return records


def _tracked_index(root, relative):
    result = _git(root, "ls-files", "--stage", "-z", "--", relative)
    records = []
    for item in result.stdout.split(b"\0"):
        if not item:
            continue
        try:
            metadata, encoded_path = item.split(b"\t", 1)
            mode, oid, stage = metadata.decode("ascii").split(" ")
            path = encoded_path.decode("utf-8", errors="strict")
            records.append((mode, oid, int(stage), path))
        except (ValueError, UnicodeDecodeError) as error:
            raise ResolutionError("malformed tracked index record") from error
    return records


def _blob(root, oid, label):
    result = _git(root, "cat-file", "blob", oid)
    raw = result.stdout
    _validate_bytes(label, raw)
    return raw


def _authorization(root, reason):
    reason = reason.strip()
    if not reason:
        raise ResolutionError("--reason must contain a non-empty reason")
    if len(reason) > MAX_REASON or "|" in reason or "\n" in reason or "\r" in reason:
        raise ResolutionError("--reason must be at most 500 characters with no pipes or newlines")
    result = _git(root, "config", "--get", "user.email", check=False)
    if result.returncode != 0:
        raise ResolutionError("git config user.email is required for the attributed override")
    try:
        identity = result.stdout.decode("utf-8", errors="strict").strip()
    except UnicodeDecodeError as error:
        raise ResolutionError("git config user.email is not valid UTF-8") from error
    if not identity or len(identity) > 254 or "|" in identity or "\n" in identity or "\r" in identity:
        raise ResolutionError("git config user.email is not a valid override identity")
    timestamp = datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")
    return f"[{timestamp}] | BY: {identity} | GATE: H-05 | REASON: {reason}\n".encode("utf-8")


def _append_parts(root, records):
    base = _blob(root, records[0][1], "merge base")
    ours = _blob(root, records[1][1], "current branch")
    theirs = _blob(root, records[2][1], "incoming branch")
    if not ours.startswith(base):
        raise ResolutionError("current branch is not append-only relative to the merge base")
    if not theirs.startswith(base):
        raise ResolutionError("incoming branch is not append-only relative to the merge base")
    ours_suffix = ours[len(base) :]
    theirs_suffix = theirs[len(base) :]
    if not ours_suffix or not theirs_suffix:
        raise ResolutionError("both conflict sides must append non-empty history")
    return base, ours_suffix, theirs_suffix


def _build_union(root, records):
    base, ours_suffix, theirs_suffix = _append_parts(root, records)
    merged = base + ours_suffix + theirs_suffix
    _validate_bytes("resolved output", merged)
    return merged


def _sync_parent(path):
    if os.name == "nt":
        return False
    flags = os.O_RDONLY
    if hasattr(os, "O_DIRECTORY"):
        flags |= os.O_DIRECTORY
    parent_fd = os.open(path.parent, flags)
    try:
        os.fsync(parent_fd)
    finally:
        os.close(parent_fd)
    return True


def _write_bytes_atomic(path, raw, *, expected=None):
    original_mode = stat.S_IMODE(path.stat().st_mode)
    fd, temporary = tempfile.mkstemp(dir=path.parent, prefix=path.name + ".", suffix=".tmp")
    witness = None
    try:
        with os.fdopen(fd, "wb") as handle:
            handle.write(raw)
            handle.flush()
            os.fsync(handle.fileno())
        os.chmod(temporary, original_mode)
        if expected is not None:
            witness_fd, witness = tempfile.mkstemp(
                dir=path.parent, prefix=path.name + ".", suffix=".witness"
            )
            os.close(witness_fd)
            os.remove(witness)
            os.link(path, witness)
            observed = Path(witness).read_bytes()
            if observed != expected:
                raise ConcurrentAppendError(path, restored=True, observed=observed)
        os.replace(temporary, path)
        temporary = None
        _sync_parent(path)
        if witness is not None:
            displaced = Path(witness).read_bytes()
            if displaced != expected:
                restored = False
                try:
                    os.replace(witness, path)
                    witness = None
                    _sync_parent(path)
                    restored = True
                finally:
                    raise ConcurrentAppendError(path, restored=restored, observed=displaced)
            os.remove(witness)
            witness = None
    except Exception:
        if temporary is not None:
            try:
                os.remove(temporary)
            except OSError:
                pass
        if witness is not None:
            try:
                os.remove(witness)
            except OSError:
                pass
        raise


def _restore_index(root, relative, records):
    removed = _git(root, "update-index", "--force-remove", "--", relative, check=False)
    if removed.returncode != 0:
        detail = removed.stderr.decode("utf-8", errors="replace").strip()
        raise ResolutionError(f"could not clear staged resolution during rollback: {detail}")
    index_info = b"".join(
        f"{mode} {oid} {stage}\t{path}\n".encode("utf-8")
        for mode, oid, stage, path in records
    )
    _git(root, "update-index", "--index-info", input_bytes=index_info)


def resolve(target, reason, cwd=None):
    root = _repository_root(cwd or os.getcwd())
    relative, path = _relative_target(root, target)
    records = _unmerged(root, relative)
    authorization = _authorization(root, reason)
    base, ours_suffix, theirs_suffix = _append_parts(root, records)
    proposed = base + ours_suffix + theirs_suffix
    _validate_bytes("resolved output", proposed)
    changes = {relative: proposed}
    paths = {relative: path}
    originals = {relative: path.read_bytes()}
    _validate_conflicted_worktree(originals[relative], base, ours_suffix, theirs_suffix)
    index_records = {relative: records}
    override_relative = ".codearbiter/overrides.log"
    if relative == override_relative:
        changes[relative] += authorization
    else:
        override_relative, override_path = _relative_target(root, override_relative)
        if _unmerged(root, override_relative, allow_resolved=True):
            raise ResolutionError("the override audit sink is itself unmerged")
        for diff_args in (("diff", "--quiet"), ("diff", "--cached", "--quiet")):
            clean = _git(root, *diff_args, "--", override_relative, check=False)
            if clean.returncode != 0:
                raise ResolutionError("the override audit sink must be clean before resolution")
        override_raw = override_path.read_bytes()
        _validate_bytes("override audit sink", override_raw)
        changes[override_relative] = override_raw + authorization
        paths[override_relative] = override_path
        originals[override_relative] = override_raw
        index_records[override_relative] = _tracked_index(root, override_relative)
    try:
        common_raw = _git(root, "rev-parse", "--git-common-dir").stdout.decode(
            "utf-8", errors="strict"
        ).strip()
    except UnicodeDecodeError as error:
        raise ResolutionError("git returned an invalid UTF-8 common directory") from error
    if not common_raw:
        raise ResolutionError("git returned an empty common directory")
    common = Path(common_raw)
    if not common.is_absolute():
        common = root / common
    lock = acquire_lock(str(common.resolve() / "codearbiter-append-only-conflict"))
    if lock is None:
        raise ResolutionError("another append-only conflict resolution holds the repository lock")
    path_locks = []
    try:
        for changed_relative in sorted(changes):
            path_lock = acquire_lock(audit_lock_key(root, paths[changed_relative]))
            if path_lock is None:
                raise ResolutionError(
                    f"another writer holds the audit path lock for '{changed_relative}'"
                )
            path_locks.append(path_lock)
        if _unmerged(root, relative) != records or path.read_bytes() != originals[relative]:
            raise ResolutionError("conflict state changed during validation; retry from fresh evidence")
        try:
            for changed_relative, raw in changes.items():
                if paths[changed_relative].read_bytes() != originals[changed_relative]:
                    raise ResolutionError("protected state changed during validation; retry")
                _write_bytes_atomic(
                    paths[changed_relative], raw, expected=originals[changed_relative]
                )
            staged = _git(root, "add", "--", *changes.keys(), check=False)
            if staged.returncode != 0:
                detail = staged.stderr.decode("utf-8", errors="replace").strip()
                raise ResolutionError(f"git add failed: {detail or 'unknown error'}")
            if _unmerged(root, relative, allow_resolved=True):
                raise ResolutionError("git add did not clear the three-stage conflict")
            for changed_relative, raw in changes.items():
                index_blob = _git(root, "show", f":0:{changed_relative}").stdout
                if index_blob != raw:
                    raise ResolutionError(
                        f"staged blob does not match validated output for {changed_relative}"
                    )
        except Exception as error:
            # The replacement is atomic; if staging or verification fails, put
            # the exact conflict-marker worktree bytes and three index stages
            # back.  This also covers a successful `git add` followed by a
            # failed staged-blob verification.
            for changed_relative, raw in originals.items():
                if isinstance(error, ConcurrentAppendError) and paths[changed_relative] == error.path:
                    if error.restored:
                        continue
                    if error.observed is not None:
                        raw = error.observed
                _write_bytes_atomic(paths[changed_relative], raw)
            for changed_relative, prior_records in index_records.items():
                _restore_index(root, changed_relative, prior_records)
            raise
    finally:
        for path_lock in reversed(path_locks):
            release_lock(path_lock)
        release_lock(lock)
    return relative


def main(argv=None):
    parser = argparse.ArgumentParser(
        description="Resolve one genuine H-05 append-only Git conflict without weakening the guard."
    )
    parser.add_argument("target", help="repository-relative protected append-only path")
    parser.add_argument("--reason", required=True, help="specific immediate H-05 override reason")
    args = parser.parse_args(argv)
    try:
        relative = resolve(args.target, args.reason)
    except (OSError, ResolutionError) as error:
        print(f"append-only conflict resolution refused: {error}", file=sys.stderr)
        return 1
    print(f"resolved and staged append-only conflict: {relative}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
