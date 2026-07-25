#!/usr/bin/env python3
"""Preserve shared exit-2 guards across Codex's Windows shell boundary.

Payload contract (#409): Codex delivers exactly ONE JSON *object* on stdin,
and the adapter routes it by `tool_name` to the shared pre-write / pre-bash
guard. Anything the adapter cannot route — a stream that never closed, an
empty stream, invalid JSON, a valid JSON top level that is not an object
(null / array / string / number / bool), or a present-but-wrong-typed
`tool_name` — goes through ONE bounded handling path: emit the documented
`decision: block` response, exit 0, dispatch no guard.

That path runs ONLY in an arbiter-enabled repo. codeArbiter is dormant
wherever `.codearbiter/CONTEXT.md` does not carry `arbiter: enabled`, and the
contract for a dormant repo is total inaction — no exit 2, no stdout, no
decision. Every guard enforces that itself as its first statement; this
adapter short-circuits BEFORE any guard runs, so on the unroutable path it is
the only process left to apply the check and must apply it (see
`_arbiter_active` below). Without it, installing the plugin would make a
tool that is supposed to be inert start declining tool calls in projects that
never opted in, the first time the Windows shell boundary this shim exists to
paper over hands over an empty or truncated stream.

Inside an arbiter-enabled repo the unroutable path fails CLOSED, matching the
pre-existing timed-out-stdin leg below. Two reasons, both specific to this
file:

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
# matcher-only aliases carrying the same payload). This is a deliberate local
# copy of CodexHost._PATCH_TOOLS / the "WRITE" entries of CodexHost.TOOL_MAP
# (hooks/_host.py): routing happens before — and without — the shared library
# import, so the adapter cannot ask the Host for it. The copy is held to the
# canonical set by TestPreToolAdapterWriteToolSet in
# .github/scripts/test_codex_adapter.py, which fails if the two ever diverge.
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


def _arbiter_active():
    """Did this repo opt into codeArbiter (`arbiter: enabled` in CONTEXT.md)?

    Answered through the SHARED helpers every guard uses, never a local copy
    of the frontmatter parser: core/activation-contract.json names
    `_hooklib.frontmatter_enabled_text` the ONE canonical parser, and a second
    implementation here could disagree with the guards about what "enabled"
    means — exactly the drift that contract exists to prevent.

    Takes no payload, and MUST be called before stdin is read — see main().

    An INDETERMINATE answer — the shared library or the plugin's Host will not
    import, i.e. a broken install — counts as ACTIVE, so the caller fails
    closed. The guards this adapter dispatches import those very same modules,
    so an install that cannot answer the activation question cannot enforce
    anything either; returning False there would convert a broken install into
    a silent allow, which is the "silent dormancy" failure mode the whole hook
    layer (and .github/scripts/test_hooks_cold_install.py) exists to prevent.
    """
    try:
        sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
        from _hooklib import arbiter_active, project_root  # noqa: PLC0415
        return arbiter_active(project_root())
    except Exception:  # noqa: BLE001 — indeterminate == active; see docstring
        return True


def main():
    # Resolved BEFORE stdin is touched, and deliberately without the payload.
    # Two constraints force it here:
    #
    #   * project_root() spawns `git rev-parse`. Once the bounded read below
    #     times out, its reader thread is STILL blocked on stdin, and a child
    #     that inherits that stdin then never returns — measured on Windows:
    #     `git rev-parse --show-toplevel` hangs until its own timeout fires
    #     instead of finishing in ~20ms. So the leg that most needs the
    #     activation answer (an incomplete stream) is the one leg that cannot
    #     obtain it afterwards.
    #   * the timeout leg must also leave NO descendant process behind
    #     (TestPreToolAdapterLifecycle), which spawning git after the fact
    #     would violate.
    #
    # Dropping the payload's `cwd` leg costs nothing here: Codex runs its hooks
    # IN the session cwd and merely repeats that cwd in the payload
    # (hooks/_host.py), so CodexHost.project_root's payload leg and its
    # process-cwd leg climb to the same git toplevel.
    active = _arbiter_active()
    raw = _read_stdin_bounded()
    script, diagnostic = _route(raw)
    if script is None:
        # A dormant repo — one that never opted in — sees NO action at all: no
        # decision, no guard, no output. Failing closed is a promise made to
        # repos that opted in, not a licence to interfere with the rest.
        return _decline(diagnostic) if active else 0
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
