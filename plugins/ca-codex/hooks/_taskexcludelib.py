#!/usr/bin/env python3
# codeArbiter — locally exclude the retained task-board OS-lock sidecar.
#
# The board lock is intentionally never removed: unlinking a locked inode lets
# another process acquire a different lock. Only Git's common info/exclude is
# changed, through its own exclusive create/replace lockfile protocol. Existing
# bytes and modes survive; no tracked file or Git index is written.
# Static Git-metadata link/reparse aliases and observed concurrent edits fail closed. This
# cooperates with writers honoring exclude.lock; it is not a sandbox against a
# hostile same-user process swapping paths between filesystem operations.
#
# Public API:
#   ensure_task_lock_excluded(root, required=False) -> str | None
#       "added" / "already present", or None for optional non-Git scaffolding.
#       Raises TaskExclusionError with a surfaced diagnostic on unsafe/failing IO.

import os
from pathlib import Path
import stat
import subprocess

from _gitexec import git_executable, root_bound_git_env


LOCK_PATH = ".codearbiter/open-tasks.md.lock"
EXCLUDE_RULE = b"/" + LOCK_PATH.encode("ascii")
MAX_EXCLUDE_BYTES = 2 * 1024 * 1024
_REPARSE = getattr(stat, "FILE_ATTRIBUTE_REPARSE_POINT", 0x400)


class TaskExclusionError(RuntimeError):
    pass


def _version(info):
    # Windows Python can expose creation time via lstat().st_ctime but change
    # time via fstat().st_ctime. Compare the common birth-time field there;
    # identity, size, mtime, mode/link count and byte rereads still bind edits.
    change = getattr(info, "st_birthtime_ns", 0) if os.name == "nt" else info.st_ctime_ns
    return (info.st_dev, info.st_ino, info.st_size, info.st_mtime_ns,
            change, info.st_mode, info.st_nlink)


def _regular(info):
    return (stat.S_ISREG(info.st_mode) and info.st_nlink == 1
            and not getattr(info, "st_file_attributes", 0) & _REPARSE)


def _directories(path):
    for directory in (*reversed(path.parents), path):
        info = directory.lstat()
        if not stat.S_ISDIR(info.st_mode) or getattr(info, "st_file_attributes", 0) & _REPARSE:
            raise TaskExclusionError("unsafe directory in task lock exclusion path")


def _git(root, *args, input_bytes=None):
    return subprocess.run([git_executable(), "-C", str(root), *args],
                          env=root_bound_git_env(), capture_output=True, timeout=5,
                          input=input_bytes)


def _git_path(root, *args):
    result = _git(root, "rev-parse", *args)
    value = os.fsdecode(result.stdout).rstrip("\r\n")
    if result.returncode or not value or not os.path.isabs(value) or "\n" in value:
        raise TaskExclusionError("cannot bind task lock exclusion to selected Git")
    return Path(value)


def _same_path(left, right):
    return os.path.normcase(os.path.abspath(left)) == os.path.normcase(os.path.abspath(right))


def _binding(root, required):
    # A failed Git probe in an actual checkout is never mistaken for non-Git.
    markers = [item / ".git" for item in (root, *root.parents)]
    has_marker = any(os.path.lexists(path) for path in markers)
    try:
        top = _git_path(root, "--show-toplevel")
    except (OSError, RuntimeError, subprocess.SubprocessError):
        if not required and not has_marker:
            return None
        raise TaskExclusionError("cannot resolve repository root for task lock exclusion") from None
    # Git reports physical roots: /var aliases and Windows 8.3 names can differ
    # from the caller. Resolve only this identity, never metadata paths whose
    # unresolved link/reparse attributes the checks below must inspect.
    root = Path(os.path.realpath(root))
    if not _same_path(os.path.realpath(top), root):
        raise TaskExclusionError("task lock exclusion requires the exact repository root")
    _directories(root)
    marker = root / ".git"
    info = marker.lstat()
    if (not (stat.S_ISDIR(info.st_mode) or _regular(info))
            or getattr(info, "st_file_attributes", 0) & _REPARSE):
        raise TaskExclusionError("unsafe Git marker for task lock exclusion")
    common = _git_path(root, "--path-format=absolute", "--git-common-dir")
    exclude = _git_path(root, "--path-format=absolute", "--git-path", "info/exclude")
    if not _same_path(exclude, common / "info/exclude"):
        raise TaskExclusionError("task lock exclusion common-directory mismatch")
    _directories(common)
    return exclude


def _read_exclude(path):
    try:
        before = path.lstat()
    except FileNotFoundError:
        return b"", None
    if not _regular(before):
        raise TaskExclusionError("task lock exclusion is not a regular single-link file")
    fd = os.open(path, os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0))
    with os.fdopen(fd, "rb") as handle:
        opened = os.fstat(handle.fileno())
        if not _regular(opened) or _version(opened) != _version(before):
            raise TaskExclusionError("task lock exclusion changed while opening")
        data = handle.read(MAX_EXCLUDE_BYTES + 1)
        if len(data) > MAX_EXCLUDE_BYTES:
            raise TaskExclusionError("task lock exclusion exceeds size limit")
        if _version(os.fstat(handle.fileno())) != _version(before):
            raise TaskExclusionError("task lock exclusion changed while reading")
    if _version(path.lstat()) != _version(before):
        raise TaskExclusionError("task lock exclusion path changed while reading")
    return data, before


def _check_conflicts(root):
    tracked = _git(root, "ls-files", "--error-unmatch", "--", LOCK_PATH)
    if tracked.returncode == 0:
        raise TaskExclusionError("task lock sidecar is tracked; local exclusion cannot untrack it")
    if tracked.returncode != 1:
        raise TaskExclusionError("cannot check tracked task lock sidecar")
    # A file can serve both global and per-directory roles. For this conflict
    # probe only, disable the lower-priority global source without changing
    # repository configuration. Effectiveness checks below use actual config.
    ignored = _git(root, "-c", "core.excludesFile=", "check-ignore", "--no-index", "-z", "-v", "--stdin",
                   input_bytes=LOCK_PATH.encode("ascii") + b"\0")
    if ignored.returncode not in (0, 1):
        raise TaskExclusionError("cannot check task lock exclusion precedence")
    fields = ignored.stdout.split(b"\0")
    # Git reports the target's per-directory sources relative to the -C root.
    if len(fields) == 5 and fields[0].replace(b"\\", b"/") in (
            b".gitignore", b".codearbiter/.gitignore") \
            and fields[2].startswith(b"!"):
        raise TaskExclusionError("a .gitignore negation overrides local task lock exclusion")


def _ensure(root, required):
    # Retain the caller spelling so publication-time binding detects retargeting.
    root = Path(os.path.abspath(root))
    exclude = _binding(root, required)
    if exclude is None:
        return None
    # mkdir is exclusive and never follows a preexisting info alias.
    try:
        exclude.parent.mkdir()
    except FileExistsError:
        pass
    _directories(exclude.parent)
    lock = exclude.with_name("exclude.lock")
    fd = None
    owned = None
    try:
        try:
            fd = os.open(lock, os.O_WRONLY | os.O_CREAT | os.O_EXCL
                         | getattr(os, "O_NOFOLLOW", 0), 0o666)
        except FileExistsError:
            raise TaskExclusionError("exclude.lock already exists; another writer may own it") from None
        info = os.fstat(fd)
        owned = info.st_dev, info.st_ino
        before, snapshot = _read_exclude(exclude)
        _check_conflicts(root)
        if EXCLUDE_RULE in before.splitlines():
            ignored = _git(root, "check-ignore", "-q", "--", LOCK_PATH)
            if ignored.returncode == 0:
                return "already present"
            if ignored.returncode != 1:
                raise TaskExclusionError("cannot verify task lock exclusion")
        newline = b"\r\n" if b"\r\n" in before else b"\n"
        data = before + (newline if before and not before.endswith(b"\n") else b"")
        data += EXCLUDE_RULE + newline
        if len(data) > MAX_EXCLUDE_BYTES:
            raise TaskExclusionError("task lock exclusion output exceeds size limit")
        with os.fdopen(fd, "wb") as handle:
            fd = None
            handle.write(data)
            handle.flush()
            os.fsync(handle.fileno())
        if snapshot is not None:
            os.chmod(lock, stat.S_IMODE(snapshot.st_mode))
        latest, current = _read_exclude(exclude)
        if latest != before or ((snapshot is None) != (current is None)) \
                or snapshot is not None and _version(snapshot) != _version(current):
            raise TaskExclusionError("task lock exclusion changed before publication")
        if _binding(root, True) != exclude:
            raise TaskExclusionError("task lock exclusion binding changed before publication")
        _directories(exclude.parent)
        info = lock.lstat()
        if not _regular(info) or (info.st_dev, info.st_ino) != owned:
            raise TaskExclusionError("exclude.lock ownership changed before publication")
        os.replace(lock, exclude)
        owned = None
        if _git(root, "check-ignore", "-q", "--", LOCK_PATH).returncode != 0:
            raise TaskExclusionError("local rule added but task lock exclusion is not effective")
        return "added"
    finally:
        if fd is not None:
            os.close(fd)
        if owned is not None:
            try:
                info = lock.lstat()
                if (info.st_dev, info.st_ino) == owned:
                    lock.unlink()  # Only OUR Git transaction file, NEVER the board OS lock.
            except FileNotFoundError:
                pass


def ensure_task_lock_excluded(root, required=False):
    try:
        return _ensure(root, required)
    except TaskExclusionError:
        raise
    except (OSError, RuntimeError, subprocess.SubprocessError) as exc:
        raise TaskExclusionError(f"task lock exclusion failed ({type(exc).__name__})") from None
