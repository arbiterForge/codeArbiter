#!/usr/bin/env python3
"""Fail-closed, cooperatively locked append for mandatory override records."""

from __future__ import annotations

import argparse
from datetime import datetime, timezone
import os
from pathlib import Path
import re
import stat
import subprocess
import sys

from _gitexec import git_executable
from _hooklib import acquire_lock, audit_lock_key, release_lock


MAX_FIELD = 500
GATE_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:-]{0,127}$")


class OverrideAppendError(RuntimeError):
    """The mandatory audit row could not be safely and durably appended."""


def _git(cwd, *args):
    try:
        result = subprocess.run(
            [git_executable(), *args], cwd=cwd, stdout=subprocess.PIPE,
            stderr=subprocess.PIPE, check=False,
        )
    except OSError as error:
        raise OverrideAppendError(f"git unavailable: {error}") from error
    if result.returncode != 0:
        detail = result.stderr.decode("utf-8", errors="replace").strip()
        raise OverrideAppendError(f"git {' '.join(args)} failed: {detail or 'unknown error'}")
    return result.stdout


def _root(cwd):
    try:
        raw = _git(cwd, "rev-parse", "--show-toplevel").decode("utf-8", errors="strict").strip()
    except UnicodeDecodeError as error:
        raise OverrideAppendError("git returned an invalid UTF-8 repository root") from error
    if not raw:
        raise OverrideAppendError("git returned an empty repository root")
    return Path(raw).resolve()


def _field(label, value):
    if not value or len(value) > MAX_FIELD or any(char in value for char in "|\r\n"):
        raise OverrideAppendError(
            f"{label} must be non-empty, at most {MAX_FIELD} characters, and contain no pipe or newline"
        )
    return value


def _identity(root):
    try:
        value = _git(root, "config", "user.email").decode("utf-8", errors="strict").strip()
    except UnicodeDecodeError as error:
        raise OverrideAppendError("git config user.email is not valid UTF-8") from error
    _field("git config user.email", value)
    if len(value) > 254 or any(char.isspace() for char in value):
        raise OverrideAppendError("git config user.email is not a valid override identity")
    return value


def _validate_file_type(path):
    try:
        mode = path.lstat().st_mode
    except OSError as error:
        raise OverrideAppendError(f"cannot inspect overrides.log: {error}") from error
    if not stat.S_ISREG(mode) or path.is_symlink():
        raise OverrideAppendError("overrides.log is not a regular non-link file")


def _validate_existing(path, raw):
    _validate_file_type(path)
    if raw.startswith(b"\xef\xbb\xbf") or b"\x00" in raw or b"\r" in raw:
        raise OverrideAppendError("overrides.log is not canonical UTF-8 LF text")
    try:
        raw.decode("utf-8", errors="strict")
    except UnicodeDecodeError as error:
        raise OverrideAppendError("overrides.log is not valid UTF-8") from error
    if raw and not raw.endswith(b"\n"):
        raise OverrideAppendError("overrides.log does not end with LF")


def append_override(*, gate=None, security_finding=None, reason, cwd=None):
    root = _root(cwd or os.getcwd())
    path = root / ".codearbiter" / "overrides.log"
    _validate_file_type(path)
    before = path.read_bytes()
    _validate_existing(path, before)
    identity = _identity(root)
    reason = _field("reason", reason)
    timestamp = datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")
    if gate is not None:
        if not GATE_RE.fullmatch(gate):
            raise OverrideAppendError("gate must be a compact gate identifier")
        body = f"GATE: {gate}"
    else:
        body = f"SECURITY-OVERRIDE | FINDING: {_field('security finding', security_finding)}"
    line = f"[{timestamp}] | BY: {identity} | {body} | REASON: {reason}\n".encode("utf-8")

    lock = acquire_lock(audit_lock_key(root, path))
    if lock is None:
        raise OverrideAppendError("another writer holds the overrides.log audit path lock")
    fd = None
    try:
        if path.read_bytes() != before:
            raise OverrideAppendError("overrides.log changed during validation; retry")
        flags = os.O_APPEND | os.O_WRONLY
        if hasattr(os, "O_BINARY"):
            flags |= os.O_BINARY
        fd = os.open(path, flags)
        offset = 0
        while offset < len(line):
            written = os.write(fd, line[offset:])
            if written <= 0:
                raise OverrideAppendError("override audit append made no progress")
            offset += written
        os.fsync(fd)
    except OSError as error:
        raise OverrideAppendError(f"override audit append failed: {error}") from error
    finally:
        try:
            if fd is not None:
                os.close(fd)
        finally:
            release_lock(lock)
    return path


def main(argv=None):
    parser = argparse.ArgumentParser(description="Append one mandatory override audit row safely.")
    kind = parser.add_mutually_exclusive_group(required=True)
    kind.add_argument("--gate", help="gate identifier for an ordinary override")
    kind.add_argument("--security-finding", help="specific acknowledged security finding")
    parser.add_argument("--reason", required=True, help="specific justification")
    args = parser.parse_args(argv)
    try:
        path = append_override(
            gate=args.gate,
            security_finding=args.security_finding,
            reason=args.reason,
        )
    except (OSError, OverrideAppendError) as error:
        print(f"override audit append refused: {error}", file=sys.stderr)
        return 1
    print(f"appended mandatory override audit row: {path}")
    return 0
