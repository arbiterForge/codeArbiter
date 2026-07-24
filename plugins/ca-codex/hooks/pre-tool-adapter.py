#!/usr/bin/env python3
"""Preserve shared exit-2 guards across Codex's Windows shell boundary.

Payload contract (#409): Codex delivers exactly ONE JSON *object* on stdin,
and the adapter routes it by `tool_name` to the shared pre-write / pre-bash
guard. Anything the adapter cannot route — a stream that never closed, an
empty stream, invalid JSON, a valid JSON top level that is not an object
(null / array / string / number / bool), or a present-but-wrong-typed
`tool_name` — goes through ONE bounded handling path: emit the documented
`decision: block` response, exit 0, dispatch no guard.

This fails CLOSED, matching the pre-existing timed-out-stdin leg below. Two
reasons, both specific to this file:

  * There is no safe guard to dispatch. Routing is a function of `tool_name`;
    without a readable one the adapter would have to guess between the write
    and exec gates, and the pre-fix code guessed pre-bash.py for every
    unreadable payload — so an unreadable `apply_patch` skipped the write
    gate entirely.
  * Dispatching anyway launders the failure into a silent allow.
    `_hooklib.read_input()` fails OPEN on an unparseable payload by explicit,
    documented design (warn + proceed without enforcement). That exception is
    correct at the GUARD layer, which has already been handed a payload the
    host produced. Feeding it input the adapter itself could not validate
    would convert "codeArbiter could not read this" into "codeArbiter allowed
    this", which is exactly the outcome the guards exist to prevent.

The emitted reason is a short deterministic diagnostic. It never carries the
payload text or an exception rendering: it is user-facing in Codex's UI, and
before this contract existed the failure surfaced as an AttributeError
traceback with no decision emitted at all.
"""

import json
import os
import subprocess
import sys
import threading


STDIN_TIMEOUT_SECONDS = 5

# tool_name values Codex reports for the apply_patch envelope (Write/Edit are
# matcher-only aliases carrying the same payload) — see hooks/_host.py.
WRITE_TOOLS = frozenset({"apply_patch", "Write", "Edit"})


def _read_stdin_bounded():
    result = []

    def read():
        result.append(sys.stdin.read())

    reader = threading.Thread(target=read, daemon=True)
    reader.start()
    reader.join(STDIN_TIMEOUT_SECONDS)
    return result[0] if result else None


def _decline(diagnostic):
    """Emit Codex's structured block decision; dispatch no guard. Always 0."""
    print(json.dumps({
        "decision": "block",
        "reason": f"Blocked by codeArbiter policy: {diagnostic}",
    }))
    return 0


def _route(raw):
    """(script, diagnostic) for the decoded payload — exactly one is None."""
    if raw is None:
        return None, "incomplete hook payload"
    if not raw.strip():
        return None, "empty hook payload"
    try:
        payload = json.loads(raw)
    except (TypeError, ValueError):
        return None, "unparseable hook payload"
    if not isinstance(payload, dict):
        # Bounded by construction: a type name, never the payload contents.
        return None, f"unexpected hook payload type: {type(payload).__name__}"
    tool_name = payload.get("tool_name", "")
    if not isinstance(tool_name, str):
        # Unhashable values raise from the WRITE_TOOLS membership test, and a
        # wrong-typed tool_name makes the write-vs-exec choice unknowable.
        return None, f"unexpected tool_name type: {type(tool_name).__name__}"
    return ("pre-write.py" if tool_name in WRITE_TOOLS else "pre-bash.py"), None


def main():
    raw = _read_stdin_bounded()
    script, diagnostic = _route(raw)
    if script is None:
        return _decline(diagnostic)
    result = subprocess.run(
        [sys.executable, os.path.join(os.path.dirname(__file__), script)],
        input=raw,
        text=True,
        capture_output=True,
    )
    if result.returncode == 2:
        reason = result.stderr.strip() or "Blocked by codeArbiter policy"
        print(json.dumps({"decision": "block", "reason": reason}))
        return 0
    sys.stdout.write(result.stdout)
    sys.stderr.write(result.stderr)
    return result.returncode


if __name__ == "__main__":
    raise SystemExit(main())
