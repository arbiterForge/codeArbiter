#!/usr/bin/env python3
# codeArbiter v2 — PreToolUse(Bash|PowerShell) guard. Thin entry point (#320):
# reads stdin, dispatches to _bashguardlib.run_guards() for the actual
# command-parsing / H-NN gate logic, exit code. Python port of pre-bash.sh
# (issues #24, #25): no jq, fails loud, blocks via exit 2.
#
# All guards run only in arbiter-enabled repos (the plugin.json activation
# contract); elsewhere this exits 0 immediately.

import os
import sys
import traceback

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import hostapi  # noqa: E402 — host seam (ADR-0011)
import _entrylib  # noqa: E402 — shared run() dispatch (jscpd dedup)
from _hooklib import (  # noqa: E402
    arbiter_active, block, get_host, project_root, read_input, set_host,
    tool_input, utf8_stdio,
)
import _bashguardlib  # noqa: E402 — guard logic lives here (#320)

# Backward-compat re-exports: pre-existing tests load this module directly
# (importlib) and reach into it by name — kept resolving exactly as they did
# before the #320 extraction, rather than editing those tests.
#   .github/scripts/test_hook_guards.py: pre_bash._strip_heredoc_bodies,
#     pre_bash.commit_pathspecs (now _bashguardlib's implementations)
#   plugins/ca/hooks/tests/test_repo_resolution.py: pre_bash.git_cwd
_strip_heredoc_bodies = _bashguardlib._strip_heredoc_bodies
commit_pathspecs = _bashguardlib.commit_pathspecs
git_cwd = _bashguardlib.git_cwd


def _run(root):
    # tool_input()/get_host() are resolved HERE (module-level names on this
    # entry file), not inside _bashguardlib, so that
    # test_guard_crash_failclosed.py's `self.mod.tool_input = <raiser>`
    # monkeypatch — which replaces the attribute on THIS module object —
    # still reaches the call (module-level rebinding is invisible to a name
    # already imported into a different module's namespace).
    payload = read_input()
    ti = get_host().normalize_tool_input(payload.get("tool_name", "") or "",
                                         tool_input(payload))
    _bashguardlib.run_guards(payload, root, ti)


def main():
    utf8_stdio()
    root = project_root()
    if not arbiter_active(root):
        sys.exit(0)
    # reliability-002 (#189): everything past this point runs only in an
    # arbiter-enabled repo, so a dormant/non-codeArbiter repo can never be
    # bricked by a crash here. An uncaught exception in the scan path below
    # (H-01/H-03/H-05/H-09b/H-10b/H-11/H-14/H-18/H-19/H-20) must fail CLOSED (exit 2,
    # a BLOCK) rather than exit 1 — a non-2 exit is a NON-blocking error under
    # the Claude Code hook contract (_hooklib.py:11-15), which would silently
    # ALLOW the very tool call this guard exists to scan. read_input()'s
    # documented fail-OPEN behavior on malformed stdin is unaffected: it catches
    # its own parse errors internally and returns {} before this wrapper is
    # ever reached.
    try:
        _run(root)
    except SystemExit:
        raise
    except Exception:  # noqa: BLE001 — the fail-closed backstop of last resort
        traceback.print_exc(file=sys.stderr)
        block("H-00", "pre-bash guard crashed while scanning this command — failing "
                      "closed (ORCHESTRATOR §2) rather than silently allowing an "
                      "unscanned command. See the traceback above; retry, or report it.")


def run(host, argv=None):
    """Host-seam entry point (ADR-0011): the __main__ guard calls this with the
    plugin's loaded Host. Wraps main() unchanged — main() still communicates
    via sys.exit/stdout/stderr, and its return value stays discarded exactly
    as the old bare `main()` guard discarded it (so the process still exits 0
    on a normal fall-through).

    Wires `host` live (#257): primes `_hooklib`'s process-cached Host via
    `set_host()` BEFORE main() runs, so main()'s `get_host()` call resolves
    to the SAME instance the caller passed here — no second
    `hostapi.load_host()`, and `run(fake_host)` genuinely exercises
    `fake_host`."""
    return _entrylib.dispatch(host, argv, main, set_host,
                               pass_argv=False, propagate_result=False)


if __name__ == "__main__":
    sys.exit(run(hostapi.load_host()) or 0)
