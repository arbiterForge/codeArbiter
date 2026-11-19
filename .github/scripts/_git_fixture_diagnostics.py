"""Failure-only, closed diagnostics for owned local Git test fixtures."""
import hashlib
import json
import math
import os
from pathlib import Path
import stat
import subprocess
import time

MAX_TRACE_BYTES = 256 * 1024
MAX_LINES = 256
MAX_EVENTS = 32
MAX_NOTE_BYTES = 8192
# These commands prepare owned source fixtures, rather than measure a product
# latency contract. Hosted Windows indexing has exceeded the old 15s allowance.
FIXTURE_GIT_TIMEOUT_SECONDS = 60
EVENTS = frozenset(("version", "start", "cmd_ancestry", "cmd_name", "cmd_mode",
    "child_start", "child_exit", "region_enter", "region_leave", "data", "data_json",
    "exit", "atexit", "error", "signal", "exec"))
CATEGORIES = frozenset(("index", "cache_tree", "dir", "progress", "read_directory",
    "unpack_trees", "status", "setup", "maintenance", "child", "main", "fsmonitor",
    "config", "parallel", "pack", "read_cache"))
LABELS = frozenset(("do_read_index", "do_write_index", "preload", "refresh",
    "name-hash-init", "cache_tree_update", "read_directory", "write", "read",
    "ensure_full_index", "unpack_trees", "traverse_trees", "check_updates", "add_files"))


def _unique(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError("duplicate trace field")
        result[key] = value
    return result


def _constant(_value):
    raise ValueError("nonfinite trace value")


def _project(raw):
    result = {"status": "bounded", "bytes": len(raw),
              "sha256": hashlib.sha256(raw).hexdigest(), "events": [],
              "event_counts": {}, "dropped": 0, "unknown_sha256": []}
    lines = raw.splitlines()
    if len(lines) > MAX_LINES:
        result["status"] = "truncated"
    for line in lines[:MAX_LINES]:
        try:
            if len(line) > 8192:
                raise ValueError("trace line exceeds bound")
            event = json.loads(line, object_pairs_hook=_unique, parse_constant=_constant)
            if not isinstance(event, dict) or event.get("event") not in EVENTS:
                raise ValueError("unsupported trace event")
            row = {"event": event["event"]}
            for field, allowed in (("category", CATEGORIES), ("label", LABELS)):
                if field in event:
                    row[field] = event[field] if type(event[field]) is str and event[field] in allowed else "other"
            for field in ("t_abs", "t_rel", "nesting", "child_id"):
                if field in event:
                    value = event[field]
                    if type(value) not in (int, float) or not math.isfinite(value) or not 0 <= value <= 1_000_000:
                        raise ValueError("invalid numeric trace field")
                    row[field] = value
            result["event_counts"][row["event"]] = result["event_counts"].get(row["event"], 0) + 1
            if len(result["events"]) < MAX_EVENTS:
                result["events"].append(row)
            else:
                result["dropped"] += 1
            # Unknown fields/values are never reflected into the diagnostic.
            if any(key not in row or event[key] != row[key] for key in event):
                if len(result["unknown_sha256"]) < 8:
                    result["unknown_sha256"].append(hashlib.sha256(line).hexdigest())
        except (ValueError, TypeError, UnicodeError, RecursionError):
            result["status"] = "invalid"
            result["dropped"] += 1
            if len(result["unknown_sha256"]) < 8:
                result["unknown_sha256"].append(hashlib.sha256(line).hexdigest())
    result["dropped"] += max(0, len(lines) - MAX_LINES)
    return result


def _read_trace(path, owner):
    unavailable = {"status": "unavailable", "events": []}
    if path is None:
        return unavailable
    try:
        owner, path = Path(owner), Path(path)
        parent = owner.lstat()
        if not stat.S_ISDIR(parent.st_mode) or owner.is_symlink() or getattr(parent, "st_file_attributes", 0) & 0x400:
            return unavailable
        if path.parent.resolve(strict=True) != owner.resolve(strict=True):
            return unavailable
        info = path.lstat()
        if (not stat.S_ISREG(info.st_mode) or path.is_symlink() or info.st_nlink != 1
                or getattr(info, "st_file_attributes", 0) & 0x400):
            return unavailable
        if info.st_size > MAX_TRACE_BYTES:
            return {"status": "over_limit", "events": []}
        descriptor = os.open(path, os.O_RDONLY | getattr(os, "O_BINARY", 0) | getattr(os, "O_NOFOLLOW", 0))
        with os.fdopen(descriptor, "rb") as stream:
            opened = os.fstat(stream.fileno())
            if (not stat.S_ISREG(opened.st_mode) or opened.st_nlink != 1
                    or (opened.st_dev, opened.st_ino) != (info.st_dev, info.st_ino)):
                return unavailable
            raw = stream.read(MAX_TRACE_BYTES + 1)
            after = os.fstat(stream.fileno())
        if len(raw) > MAX_TRACE_BYTES:
            return {"status": "over_limit", "events": []}
        if (opened.st_size, opened.st_mtime_ns) != (after.st_size, after.st_mtime_ns):
            return unavailable
        return _project(raw)
    except (OSError, ValueError, TypeError):
        return unavailable


def _prepare_trace(owner, phase):
    owner = Path(owner)
    info = owner.lstat()
    if not stat.S_ISDIR(info.st_mode) or owner.is_symlink() or getattr(info, "st_file_attributes", 0) & 0x400:
        raise ValueError("fixture diagnostic owner unavailable")
    path = owner.resolve(strict=True) / ("fixture-git-" + phase + ".trace.jsonl")
    descriptor = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, "O_NOFOLLOW", 0), 0o600)
    os.close(descriptor)
    return path


def _failure_note(error, phase, started, trace, owner):
    failure = ("timeout" if isinstance(error, subprocess.TimeoutExpired) else
               "command_failed" if isinstance(error, subprocess.CalledProcessError) else
               "os_error" if isinstance(error, OSError) else "unknown")
    elapsed = (time.perf_counter() - started) * 1000 if started is not None else None
    if elapsed is not None and (not math.isfinite(elapsed) or not 0 <= elapsed <= 86_400_000):
        elapsed = None
    record = {"format": "codearbiter.fixture-git-diagnostic/1", "phase": phase,
              "failure": failure, "elapsed_ms": round(elapsed, 3) if elapsed is not None else None,
              "trace": _read_trace(trace, owner)}
    prefix = "Fixture Git diagnostic: "
    while len((prefix + json.dumps(record, separators=(",", ":"))).encode()) > MAX_NOTE_BYTES:
        record["trace"]["events"].pop()
        record["trace"]["dropped"] += 1
    return prefix + json.dumps(record, separators=(",", ":"))


def run_git_phase(argv, *, phase, trace_dir):
    """Run one owned fixture command with a bounded setup allowance; no retry."""
    phase = phase if phase in ("init", "index", "commit") else "unknown"
    trace, started, environment = None, None, None
    try:
        started = time.perf_counter()
        trace = _prepare_trace(trace_dir, phase)
        environment = dict(os.environ, GIT_TRACE2_EVENT=str(trace))
    except Exception:
        pass  # Diagnostics cannot prevent the original fixture command.
    try:
        return subprocess.run(argv, check=True, capture_output=True,
                              timeout=FIXTURE_GIT_TIMEOUT_SECONDS, env=environment)
    except Exception as error:
        try:
            error.add_note(_failure_note(error, phase, started, trace, trace_dir))
        except Exception:
            pass  # Preserve the original exception even when diagnostics fail.
        raise
