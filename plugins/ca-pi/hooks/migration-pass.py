#!/usr/bin/env python3
# codeArbiter — record a migration-review pass BOUND to the migration files it
# approved (H-14, issue #77).
#
# There was no commit-time migration gate before #77: a migration committed via
# bare /commit or the /feature small lane never reached migration-reviewer (the
# /review, /pr, /checkpoint, and sprint lanes did dispatch it). commit-gate now
# dispatches migration-reviewer when it classifies a staged migration and runs
# THIS script on PASS. It mirrors security-pass.py: it hashes the content of
# every staged migration file (detected by is_migration_path) and writes both
# their content digests and one complete path/content-set binding to
# .codearbiter/.markers/migration-gate-passed; pre-bash.py's H-14 then admits a
# commit only when the complete migration candidate matches the recorded set.
#
# Binding has no freshness window: it stays valid while every reviewed path and
# its content remain unchanged; an omission, addition, rename, or edit re-blocks.
#
# Invoked by skill prose as (interpreter resolved once by presence, never a
# `python3 X || python X` fold -- #577):
#   "$PY" "<plugin>/hooks/migration-pass.py"

import json
import os

from _gitexec import (active_index_recovery, read_head_blob_digest,
                      read_index_text, staged_changes)
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from _hooklib import (  # noqa: E402
    content_digest, is_migration_path, set_host, utf8_stdio, warn,
    migration_candidate_binding, worktree_marker_binding, write_text_atomic,
)

MAX_FILE_BYTES = 1_000_000  # a blob bigger than this is not a reviewable migration


def candidate_paths(root):
    """Exactly the staged migration paths supplied to migration-reviewer."""
    return staged_changes(root, preserve_index=True)


def reviewed_root(argv=None):
    args = list(sys.argv[1:] if argv is None else argv)
    if len(args) not in (0, 2) or (args and args[0] != "--root"):
        return None
    selected = args[1] if args else os.getcwd()
    if not os.path.isdir(selected):
        return None
    import hostapi  # noqa: PLC0415 - same-directory host seam
    top = hostapi.git_toplevel(selected)
    if not top:
        return None
    if args and os.path.normcase(os.path.realpath(top)) != os.path.normcase(
            os.path.realpath(selected)):
        return None
    return top


def main(argv=None):
    utf8_stdio()
    root = reviewed_root(argv)
    if root is None:
        warn("migration-gate pass refused: use --root <reviewed repository root> "
             "or run the standalone producer from that root")
        sys.exit(1)
    if not os.path.isdir(os.path.join(root, ".codearbiter")):
        warn("no .codearbiter/ here — migration-pass.py records nothing outside "
             "an initialized repo")
        sys.exit(1)
    index_recovery = active_index_recovery(root)
    if index_recovery:
        warn("migration-gate pass refused: " + index_recovery)
        sys.exit(1)
    candidates = candidate_paths(root)
    if candidates is None:
        warn("migration-gate pass refused: staged migration set is unreadable")
        sys.exit(1)
    migs = sorted(rel for rel in candidates if is_migration_path(rel, root))
    reviewed = []
    for rel in migs:
        status = candidates[rel]
        text = None if status == "D" else read_index_text(
            root, rel, MAX_FILE_BYTES, preserve_index=True)
        preimage = None if status == "A" else read_head_blob_digest(
            root, rel, MAX_FILE_BYTES)
        if status != "D" and text is None:
            warn("migration-gate pass refused: staged migration is unreadable: "
                 + json.dumps(rel, ensure_ascii=False))
            sys.exit(1)
        if status != "A" and preimage is None:
            warn("migration-gate pass refused: migration preimage is unreadable: "
                 + json.dumps(rel, ensure_ascii=False))
            sys.exit(1)
        reviewed.append((rel, status, text, preimage))
    digests = {content_digest(text) for _rel, _status, text, _preimage in reviewed
               if text is not None}
    # #604: same split as security-pass.py — candidate_paths(root)/index reads
    # above must stay bound to wherever this process is actually running (a
    # linked worktree's own tree), but the MARKER write goes through
    # marker_root(), which agrees with the H-14 guard's main-checkout-anchored
    # read (D-2) even when this process has no CLAUDE_PROJECT_DIR set.
    import hostapi  # noqa: PLC0415 - same-directory host seam
    write_root = hostapi.git_worktree_main_root(root) or root
    marker_dir = os.path.join(write_root, ".codearbiter", ".markers")
    os.makedirs(marker_dir, exist_ok=True)
    marker = os.path.join(marker_dir, "migration-gate-passed")
    digests = [worktree_marker_binding(root), migration_candidate_binding(reviewed),
               *sorted(digests)]
    # Atomic write (migration-002): a crash mid-write never leaves a half-written
    # marker, which the backstop would read as an unrecognized digest and force a
    # spurious gate re-run.
    write_text_atomic(marker, "\n".join(digests) + ("\n" if digests else ""))
    print(f"migration-gate pass recorded: {len(migs)} migration file(s) "
          f"bound to {os.path.relpath(marker, write_root)}")


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
    set_host(host)
    main(argv)
    return 0


if __name__ == "__main__":
    # hostapi is imported here (not at module top) so OB-S1's stdlib-import
    # scan of this producer keeps its exact allowlist; hostapi is the same-dir
    # host seam (ADR-0011), stdlib-only like _hooklib.
    import hostapi  # noqa: PLC0415
    sys.exit(run(hostapi.load_host()) or 0)
