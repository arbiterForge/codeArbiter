#!/usr/bin/env python3
"""Bounded verifier subprocesses with an explicit cleanup outcome (R-07).

A verifier phase that waits on a child (an install command, a readiness line)
must have a deadline, keep whatever partial output arrived, and report two
separate facts when the deadline passes:

  * the phase TIMED OUT (a qualification failure), and
  * what cleanup established about the child's process tree (containment).

A timeout is never evidence that the child is quiescent. Containment follows
the platform contract the Pi runtime already uses (process-tree.ts/bridge.ts):

  POSIX    the child leads its own session/process group; cleanup signals the
           whole group (SIGTERM, then SIGKILL) and confirms the group is gone.
  Windows  the child gets its own process group; cleanup runs the absolute
           System32 taskkill /T /F against its PID and confirms the child exited.
           Windows reports `terminated` only when taskkill succeeded.

Outcomes: `exited` (finished on its own), `terminated` (tree confirmed gone),
`unconfirmed` (cleanup ran but quiescence could not be confirmed).
"""
from __future__ import annotations

import os
import queue
import signal
import subprocess
import threading
import time
from dataclasses import dataclass
from pathlib import Path

GRACE_SECONDS = 3.0


@dataclass
class Bounded:
    returncode: int | None
    stdout: str
    stderr: str
    timed_out: bool
    containment: str  # exited | terminated | unconfirmed

    def diagnostic(self, label: str, seconds: float) -> str:
        if not self.timed_out:
            return ""
        tail = (self.stderr or self.stdout).strip()[-400:]
        return (f"{label} timed out after {seconds:g}s; child containment={self.containment}"
                + (f"; partial output: {tail}" if tail else ""))


def _popen_flags() -> dict:
    if os.name == "nt":
        return {"creationflags": subprocess.CREATE_NEW_PROCESS_GROUP}
    return {"start_new_session": True}


def start(argv, **kwargs) -> subprocess.Popen:
    """Start a child that can later be terminated as a whole tree."""
    return subprocess.Popen(argv, **_popen_flags(), **kwargs)


def _taskkill() -> str | None:
    root = os.environ.get("SystemRoot") or os.environ.get("SYSTEMROOT")
    if not root:
        return None
    candidate = Path(root) / "System32" / "taskkill.exe"
    return str(candidate) if candidate.is_file() else None


def _group_alive(pgid: int) -> bool:
    try:
        os.killpg(pgid, 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        return True
    return True


def terminate_tree(process: subprocess.Popen, grace: float = GRACE_SECONDS) -> str:
    """Terminate `process` and its descendants; return the containment outcome."""
    if os.name == "nt":
        taskkill = _taskkill()
        killed = False
        if taskkill and process.poll() is None:
            try:
                done = subprocess.run([taskkill, "/pid", str(process.pid), "/t", "/f"],
                                      capture_output=True, timeout=10)
                killed = done.returncode == 0
            except (OSError, subprocess.SubprocessError):
                killed = False
        if process.poll() is None:
            process.kill()
        try:
            process.wait(timeout=grace)
        except subprocess.TimeoutExpired:
            return "unconfirmed"
        return "terminated" if killed else "unconfirmed"
    pgid = process.pid
    for sig in (signal.SIGTERM, signal.SIGKILL):
        try:
            os.killpg(pgid, sig)
        except ProcessLookupError:
            break
        deadline = time.monotonic() + grace
        while time.monotonic() < deadline and _group_alive(pgid):
            process.poll()
            time.sleep(0.05)
        if not _group_alive(pgid):
            break
    try:
        process.wait(timeout=grace)
    except subprocess.TimeoutExpired:
        return "unconfirmed"
    return "unconfirmed" if _group_alive(pgid) else "terminated"


def run(argv, *, timeout: float, **kwargs) -> Bounded:
    """subprocess.run with a whole-tree deadline and partial-output retention."""
    process = start(argv, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True,
                    encoding="utf-8", errors="replace", **kwargs)
    try:
        stdout, stderr = process.communicate(timeout=timeout)
        return Bounded(process.returncode, stdout, stderr, False, "exited")
    except subprocess.TimeoutExpired as expired:
        partial_out = _text(expired.stdout)
        partial_err = _text(expired.stderr)
        containment = terminate_tree(process)
        try:
            rest_out, rest_err = process.communicate(timeout=GRACE_SECONDS)
        except (subprocess.TimeoutExpired, ValueError):
            rest_out, rest_err = "", ""
        # communicate() retries return the full buffered stream, including the
        # prefix carried by TimeoutExpired. Keep the prefix only if cleanup
        # could not finish communication; concatenating would invent output.
        return Bounded(None, rest_out if rest_out else partial_out,
                       rest_err if rest_err else partial_err,
                       True, containment)


def _text(value) -> str:
    if value is None:
        return ""
    return value.decode("utf-8", "replace") if isinstance(value, bytes) else value


def readline(process: subprocess.Popen, timeout: float) -> tuple[str | None, str]:
    """Read one stdout line within `timeout`.

    Returns (line, "") on success, (None, reason) on timeout, and ("", reason)
    when the child closed stdout first. A line without its newline is returned
    as read; the caller decides whether it is valid.
    """
    found: queue.Queue = queue.Queue(maxsize=1)

    def reader():
        try:
            found.put(process.stdout.readline())
        except (OSError, ValueError) as error:
            found.put(error)

    threading.Thread(target=reader, daemon=True).start()
    try:
        line = found.get(timeout=timeout)
    except queue.Empty:
        return None, f"no line within {timeout:g}s"
    if isinstance(line, Exception):
        return "", f"stream failed: {line}"
    if line == "":
        return "", "stream closed before a line"
    return line, ""
