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
import errno
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


class _VerifierProcess(subprocess.Popen):
    """Keep one buffered-stream owner after a readiness line has been requested."""
    def __init__(self, *args, **kwargs):
        self._line_capture = None
        self._capture_lock = threading.Lock()
        super().__init__(*args, **kwargs)

    def communicate(self, input=None, timeout=None):
        capture = self._line_capture
        if capture is None:
            return super().communicate(input=input, timeout=timeout)
        return capture.communicate(input, timeout)


def start(argv, **kwargs) -> subprocess.Popen:
    """Start a child with whole-tree cleanup and a single text-reader lifecycle."""
    return _VerifierProcess(argv, **_popen_flags(), **kwargs)


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
    process.poll()  # Reap an already exited leader before signalling its group.
    signalled = False
    for sig in (signal.SIGTERM, signal.SIGKILL):
        try:
            os.killpg(pgid, sig)
            signalled = True
        except ProcessLookupError:
            break
        except PermissionError:
            # macOS can refuse an already exited group's signal. This is a
            # cleanup fact, not permission to replace the primary phase error.
            process.poll()
            continue
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
    if _group_alive(pgid):
        return "unconfirmed"
    return "terminated" if signalled else "exited"


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


class _StreamCapture:
    """The same workers own buffered streams through readiness, EOF and cleanup.

    POSIX Popen.communicate reads file descriptors directly. Mixing that with
    TextIO.readline loses completion bytes already prefetched into TextIO.
    Workers also drain stderr during readiness so neither pipe is abandoned.
    """
    def __init__(self, process):
        self.process = process
        self.empty = "" if process.text_mode else b""
        self.condition = threading.Condition()
        self.pending = {"stdout": [], "stderr": []}
        self.done = {"stdout": False, "stderr": False}
        self.errors = {}
        self.completed = None
        self.input_started = False
        self.input_done = False
        self.input_error = None
        for name in self.pending:
            threading.Thread(target=self._read, args=(name,), daemon=True).start()

    def _read(self, name):
        stream = getattr(self.process, name)
        try:
            if stream is not None:
                for line in iter(stream.readline, self.empty):
                    with self.condition:
                        self.pending[name].append(line)
                        self.condition.notify_all()
        except (OSError, ValueError) as error:
            with self.condition:
                self.errors[name] = error
        finally:
            if stream is not None:
                stream.close()
            with self.condition:
                self.done[name] = True
                self.condition.notify_all()

    def readline(self, timeout):
        deadline = time.monotonic() + timeout
        with self.condition:
            while not self.pending["stdout"] and not self.done["stdout"]:
                remaining = deadline - time.monotonic()
                if remaining <= 0:
                    return None, f"no line within {timeout:g}s"
                self.condition.wait(remaining)
            if self.pending["stdout"]:
                return self.pending["stdout"].pop(0), ""
            if "stdout" in self.errors:
                return self.empty, f"stream failed: {self.errors['stdout']}"
            return self.empty, "stream closed before a line"

    def _write_input(self, data):
        """One writer owns input and EOF, including across timeout retries."""
        stream = self.process.stdin
        error = None
        try:
            if data is not None:
                if self.process.text_mode:
                    if not isinstance(data, str):
                        raise TypeError("text stdin requires a string")
                else:
                    data = memoryview(data).cast("B")
                offset = 0
                while offset < len(data):
                    written = stream.write(data[offset:])
                    if not written:
                        raise OSError("stdin pipe made no progress")
                    offset += written
        except BrokenPipeError:
            pass  # communicate tolerates a child that closes its input early.
        except OSError as exc:
            if exc.errno != errno.EINVAL:  # Windows can use EINVAL for a closed pipe.
                error = exc
        except Exception as exc:
            error = exc
        finally:
            try:
                stream.close()  # input=None must still deliver EOF.
            except BrokenPipeError:
                pass
            except OSError as exc:
                if exc.errno != errno.EINVAL and error is None:
                    error = exc
            except Exception as exc:
                if error is None:
                    error = exc
            with self.condition:
                self.input_error = error
                self.input_done = True
                self.condition.notify_all()

    def communicate(self, data, timeout):
        deadline = None if timeout is None else time.monotonic() + timeout
        with self.condition:
            if self.input_started and data:
                raise ValueError("Cannot send input after starting communication")
            if not self.input_started:
                self.input_started = True
                self.process._communication_started = True
                if self.process.stdin is None:
                    self.input_done = True
                else:
                    threading.Thread(target=self._write_input, args=(data,), daemon=True).start()
            if self.completed is not None:
                return self.completed
            while not (all(self.done.values()) and self.input_done):
                if self.input_error is not None:
                    raise self.input_error
                remaining = None if deadline is None else deadline - time.monotonic()
                if remaining is not None and remaining <= 0:
                    raise subprocess.TimeoutExpired(
                        self.process.args, timeout, output=self.empty.join(self.pending["stdout"]),
                        stderr=self.empty.join(self.pending["stderr"]))
                self.condition.wait(remaining)
            if self.input_error is not None:
                raise self.input_error
            if self.errors:
                raise OSError("verifier buffered stream failed") from next(iter(self.errors.values()))
            output = (self.empty.join(self.pending["stdout"]), self.empty.join(self.pending["stderr"]))
        remaining = None if deadline is None else max(0, deadline - time.monotonic())
        self.process.wait(timeout=remaining)
        with self.condition:
            self.completed = output
            self.pending = {"stdout": [], "stderr": []}
        return output


def readline(process: subprocess.Popen, timeout: float) -> tuple[str | bytes | None, str]:
    """Read one stdout line within `timeout` from a child created with start().

    The same capture owns subsequent communicate() calls, retaining prefetched
    bytes/text and partial diagnostics, matching Popen's selected mode. A
    timeout does not start a competing reader.
    A line without its newline is returned for the caller's validation.
    """
    with process._capture_lock:
        if process._line_capture is None:
            process._line_capture = _StreamCapture(process)
        capture = process._line_capture
    return capture.readline(timeout)
