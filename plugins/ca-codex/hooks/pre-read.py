#!/usr/bin/env python3
# codeArbiter — PreToolUse:Read hook: file-scoped just-in-time context injection.
#
# Thin entry point for the file-scoped-context-injection spec (AC-03, AC-10).
# All testable logic lives in _readinjectlib.py; this file wires the Claude Code
# hook protocol to the lib's compute_injection / allow_output helpers.
#
# Control flow:
#   1. utf8_stdio(); root = project_root().
#   2. If not arbiter_active(root): sys.exit(0) — dormant in non-opted-in repos.
#   3. Parse input: data = read_input(); extract file_path from tool_input(data);
#      session_id = data.get("session_id", "").
#   4. rel = repo_rel(file_path, root). If rel is falsy (outside repo): sys.exit(0).
#   5. ctx = compute_injection(root, session_id, rel) — handles the .codearbiter/
#      self-read guard (AC-10), per-(session, file) dedup (AC-09), four-tier index
#      lookup, budget assembly, and marker write internally.
#   6. If ctx non-empty: print allow_output(ctx) as JSON (AC-03) and exit 0.
#      If ctx empty (miss, self-read, or dedup): exit 0 with no output — silent allow.
#
# Design invariants:
#   - Always allows the Read — never emits a deny or block decision.
#   - Emits allow_output(ctx) ONLY when ctx is non-empty (AC-10: miss and self-read
#     must be silent; "Done looks like" requires no output on a non-governed Read).
#   - Fail-open (AC-12): any exception degrades to sys.exit(0) with no stdout
#     output. A hook crash must NEVER block or stall a Read. The outer
#     except Exception clause is the last-resort safety net; sys.exit(0) calls
#     inside the try block raise SystemExit (a BaseException, not an Exception)
#     so they propagate normally and are never swallowed by this clause.

import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import hostapi  # noqa: E402 — host seam (ADR-0011)
import _entrylib  # noqa: E402 — shared run() dispatch (jscpd dedup)
from _hooklib import (  # noqa: E402
    arbiter_active, project_root, read_input, repo_rel, set_host, tool_input,
    utf8_stdio,
)
from _readinjectlib import allow_output, compute_injection  # noqa: E402


def main():
    try:
        utf8_stdio()
        root = project_root()
        if not arbiter_active(root):
            sys.exit(0)
        data = read_input()
        file_path = tool_input(data).get("file_path", "")
        session_id = data.get("session_id", "")
        rel = repo_rel(file_path, root)
        if not rel:
            sys.exit(0)
        ctx = compute_injection(root, session_id, rel)
        if ctx:
            print(json.dumps(allow_output(ctx)))
        sys.exit(0)
    except Exception:  # noqa: BLE001 — AC-12: fail-open, never block a Read
        sys.exit(0)


def run(host, argv=None):
    """Host-seam entry point (ADR-0011): the __main__ guard calls this with the
    plugin's loaded Host. Wraps main() unchanged — main() still communicates
    via sys.exit/stdout/stderr, and its return value stays discarded exactly
    as the old bare `main()` guard discarded it (so the process still exits 0
    on a normal fall-through).

    Wires `host` live (#257): primes `_hooklib`'s process-cached Host via
    `set_host()` BEFORE main() runs, so any `get_host()` call downstream
    resolves to the SAME instance the caller passed here — no second
    `hostapi.load_host()`, and `run(fake_host)` genuinely exercises
    `fake_host`."""
    return _entrylib.dispatch(host, argv, main, set_host,
                               pass_argv=False, propagate_result=False)


if __name__ == "__main__":
    sys.exit(run(hostapi.load_host()) or 0)
