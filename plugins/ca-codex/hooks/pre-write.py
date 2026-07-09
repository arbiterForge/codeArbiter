#!/usr/bin/env python3
# codeArbiter v2 — PreToolUse(Write) guard. Activation + audit-log + marker + ADR
# integrity. Python port of pre-write.sh (#25): no jq, fails loud, blocks via
# exit 2.
#
# Guards (all on the arbiter-enabled repo only):
#   H-18  .codearbiter/CONTEXT.md is the activation switch every hook gates on
#         (#159) — a Write may not flip `arbiter: enabled` off or corrupt the
#         frontmatter, which would make every gate dormant.
#   H-19  .codearbiter/.markers/* are the gate-pass tokens that turn a hard-gate
#         BLOCK into an allow (#160) — never writable via the Write tool.
#   H-05  audit logs (overrides.log, triage.log, sprint-log.md) are append-only.
#   H-11  ADRs under decisions/ are authored only via /adr.
#
# Every protected-path decision resolves symlinks (#162): classify_protected()
# checks the raw path AND its realpath-resolved repo-relative form, so a symlink
# alias whose visible path lacks `.codearbiter/` can't launder a write past a
# guard.

import os
import sys
import traceback

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import hostapi  # noqa: E402 — host seam (ADR-0011)
from _hooklib import (  # noqa: E402
    arbiter_active, block, classify_protected, frontmatter_enabled_text,
    get_host, marker_fresh, project_root, read_input, utf8_stdio,
)


def _guard_op(root, op):
    """Run the four protected-path guards against ONE canonical file op
    (hostapi.Host.iter_file_ops). Under Claude Code this receives exactly the
    one "write" op its Write payload maps to, so every check, message, and
    check ORDER below is byte-identical to the pre-seam single-payload body.
    The "edit"/"delete" kinds arrive only from a host whose write tool batches
    per-file operations (Codex's apply_patch, ADR-0011 M2) — a patch hunk's
    resulting content cannot be replayed the way pre-edit.py replays an Edit,
    so those kinds resolve CLOSED on the content-sensitive guards."""
    fpath = op.get("file_path", "") or ""
    kind = op.get("kind", "write")

    # H-21: an "opaque" op is a host's signal that a write-batching payload
    # carried a recognizable envelope the adapter could NOT decompose into
    # per-file ops (e.g. an apply_patch variant outside the mirrored grammar).
    # Whatever it touches is unknowable here, so it can never pass unguarded —
    # ambiguity resolves CLOSED (ORCHESTRATOR §2). Claude Code never emits
    # this kind; its Write payload always maps to exactly one "write" op.
    if kind == "opaque":
        block("H-21", "This patch envelope could not be decomposed into per-file operations, "
                      "so its targets cannot be guarded. Failing closed. Re-issue the change "
                      "as a plain patch in the documented apply_patch grammar (or split it "
                      "into smaller single-file patches).")

    classes = classify_protected(fpath, root)

    # H-19: the gate-pass markers are the mechanism that turns a hard-gate BLOCK
    # into an allow (#160). They are recorded only by the sanctioned producers
    # (security-pass.py / migration-pass.py) and the /adr `touch` — a Write here
    # is a hand-forged marker. Block outright (any kind: write, edit, delete).
    if "marker" in classes:
        block("H-19", "The .codearbiter/.markers/ gate tokens are not writable via the Write "
                      "tool (#160) — a hand-written marker forges a security/migration/ADR gate "
                      "pass. Markers are recorded only by the sanctioned gate producers.")

    # H-18: CONTEXT.md is the master switch arbiter_active() reads (#159). A Write
    # is a full overwrite, so vet the RESULTING content: allow only if it still
    # carries a well-formed `arbiter: enabled` frontmatter. Disabling arbiter
    # from inside the repo it governs is exactly the kill-switch this closes (a
    # human can still opt out by editing the file outside the agent's tools).
    if "context" in classes:
        if kind == "write":
            enabled, malformed = frontmatter_enabled_text(op.get("content", "") or "")
            if malformed or not enabled:
                block("H-18", "This Write would remove or alter the `arbiter: enabled` frontmatter in "
                              ".codearbiter/CONTEXT.md (#159) — the activation switch every enforcement "
                              "hook reads. Disabling it from inside the repo would make every gate "
                              "dormant. Keep `arbiter: enabled` in a well-formed frontmatter block.")
        else:
            # A patch edit's resulting frontmatter cannot be verified from its
            # hunks, and a delete removes the activation switch outright —
            # ambiguity resolves CLOSED (ORCHESTRATOR §2). /ca:override is the
            # sanctioned escape hatch.
            block("H-18", "This patch operation edits or deletes .codearbiter/CONTEXT.md (#159) — "
                          "the activation switch every enforcement hook reads — and its resulting "
                          "frontmatter cannot be verified from patch hunks. Failing closed; use the "
                          "sanctioned init path (or /ca:override).")

    # H-05: the audit logs (and the /sprint decision record) are append-only —
    # a Write is a full overwrite. (path set: _hooklib.is_audit_log)
    if "audit" in classes:
        if kind == "write":
            block("H-05", "The .codearbiter audit logs (overrides.log, triage.log, sprint-log.md) "
                          "are append-only (ORCHESTRATOR §7). Append with Edit or '>>', never Write.")
        # A patch edit is positional (it can rewrite interior lines) and a
        # patch delete destroys the trail — neither can be a verifiable pure
        # append the way pre-edit.py's tail-anchored Edit can.
        block("H-05", "The .codearbiter audit logs (overrides.log, triage.log, sprint-log.md) "
                      "are append-only (ORCHESTRATOR §7). A patch cannot express a verifiable "
                      "pure append; append with '>>' instead.")

    # H-11: ADRs may only be authored via /adr (the skill drops the marker first).
    # Any .md anywhere under decisions/ is covered — a non-numbered draft or a
    # nested path is still an immutable decision artifact. (set: is_decisions_path)
    if "decisions" in classes:
        if kind == "delete":
            block("H-11", "ADR files under .codearbiter/decisions/ are immutable history "
                          "(ORCHESTRATOR §6) — deleting one is prohibited, marker or not.")
        marker = os.path.join(root, ".codearbiter", ".markers", "adr-authoring-active")
        if not os.path.isfile(marker):
            block("H-11", "ADR files are authored only via /adr (ORCHESTRATOR §3) — user "
                          "attribution required. Subagent-authored ADRs are prohibited.")
        if not marker_fresh(marker, 30):
            block("H-11", "ADR authoring marker is stale (>30 min). Re-run /adr.")


def _run(root):
    # The host seam (ADR-0011, M2): iter_file_ops maps this host's native
    # payload to canonical per-file ops. Claude's Write payload maps to exactly
    # one "write" op (same fields the pre-seam body read straight off
    # tool_input), so the Claude verdict path is unchanged; Codex's apply_patch
    # envelope fans out to one op per touched file, each hitting the same
    # guards.
    for op in get_host().iter_file_ops(read_input()):
        _guard_op(root, op)
    sys.exit(0)


def main():
    utf8_stdio()
    root = project_root()
    if not arbiter_active(root):
        sys.exit(0)
    # reliability-002 (#189): scoped to arbiter-enabled repos only (above), so a
    # dormant/non-codeArbiter repo can never be bricked by a crash here. An
    # uncaught exception in the scan below must fail CLOSED (exit 2 = BLOCK),
    # not exit 1 — a non-2 exit is a NON-blocking error under the Claude Code
    # hook contract (_hooklib.py:11-15) and would silently ALLOW the Write.
    # read_input()'s documented fail-OPEN parse behavior is unaffected: it
    # catches its own errors and returns {} before this wrapper is reached.
    try:
        _run(root)
    except SystemExit:
        raise
    except Exception:  # noqa: BLE001 — the fail-closed backstop of last resort
        traceback.print_exc(file=sys.stderr)
        block("H-00", "pre-write guard crashed while scanning this Write — failing "
                      "closed (ORCHESTRATOR §2) rather than silently allowing an "
                      "unscanned write. See the traceback above; retry, or report it.")


def run(host, argv=None):
    """Host-seam entry point (ADR-0011): the __main__ guard calls this with the
    plugin's loaded Host. Wraps main() unchanged — main() still communicates
    via sys.exit/stdout/stderr, and its return value stays discarded exactly
    as the old bare `main()` guard discarded it (so the process still exits 0
    on a normal fall-through)."""
    main()
    return 0


if __name__ == "__main__":
    sys.exit(run(hostapi.load_host()) or 0)
