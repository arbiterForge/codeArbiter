#!/usr/bin/env python3
# codeArbiter v2 — PreToolUse(Edit|MultiEdit|NotebookEdit) guard. Activation +
# audit-log + marker + ADR integrity. Python port of pre-edit.sh (#25): no jq,
# fails loud, blocks via exit 2.
#
# Guards (arbiter-enabled repo only), symlink-resolved via classify_protected
# (#162 — raw path AND realpath-resolved repo-relative form):
#   H-18  CONTEXT.md may not be edited to drop `arbiter: enabled` (#159).
#   H-19  .codearbiter/.markers/* are never edited via the Edit tools (#160).
#   H-05  audit-log Edits must be pure, tail-anchored appends: old_string must
#         be the file's REAL current trailing content, new_string must extend
#         it, and replace_all is rejected outright (reliability-003, #172).
#   H-11  ADRs under decisions/ are edited only via /adr.
#
# NotebookEdit is guarded too (a notebook has no append/frontmatter semantics, so
# a protected target is refused outright) — defense in depth; none of the
# protected files is a .ipynb, but the tool must not be a hole.
#
# Host seam (ADR-0011, #261): this file reasons entirely over the canonical
# per-file ops from hostapi.Host.iter_file_ops (the same seam pre-write.py
# already routes through) — it never branches on a native tool name
# ("MultiEdit", "NotebookEdit"). The properties that used to be read off the
# raw tool_input (old_string, replace_all, "this is a MultiEdit batch entry",
# "this is a notebook with no content semantics") are host-neutral op fields
# (old_string, replace_all, batched, notebook) instead — a future host whose
# edit tool shares those same shapes gets the same guard semantics without
# pre-edit.py knowing its tool names.

import os
import sys
import traceback

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import hostapi  # noqa: E402 — host seam (ADR-0011)
import _entrylib  # noqa: E402 — shared run() dispatch (jscpd dedup)
from _hooklib import (  # noqa: E402
    arbiter_active, block, classify_protected, frontmatter_enabled_text,
    get_host, is_tail_append, marker_fresh, project_root, read_input,
    set_host, utf8_stdio,
)


def _read_real_text(root, fpath):
    """Best-effort current on-disk content of `fpath` (symlink-resolved), or
    "" if unreadable. Shared by the #159 CONTEXT.md replay and the H-05
    tail-anchor check (reliability-003, #172) — both need the file's REAL
    current content, not just an edit op's own old_string, to verify what the
    edit actually does to the file."""
    path = fpath if os.path.isabs(fpath) else os.path.join(root, fpath)
    try:
        with open(os.path.realpath(path), encoding="utf-8", errors="replace") as f:
            return f.read()
    except Exception:  # noqa: BLE001
        return ""


def _resulting_context(root, fpath, ops):
    """Best-effort resulting content of CONTEXT.md after ALL of `ops` (one or
    more canonical edit ops targeting the same file — a MultiEdit call fans
    out to several, applied as one atomic batch) are replayed in order, so
    the #159 guard can vet whether the FULL call keeps the repo
    arbiter-enabled. Reads the real (symlink-resolved) file and replays each
    op's old_string/added_text/replace_all against the running text, exactly
    as the pre-seam per-tool replay did — driven off op fields instead of a
    native tool_input shape. An old_string that isn't present leaves the text
    unchanged (the tool would error anyway) — harmless for the check."""
    text = _read_real_text(root, fpath)
    for op in ops:
        old = op.get("old_string", "") or ""
        new = op.get("added_text", "") or ""
        if op.get("replace_all"):
            text = text.replace(old, new)
        else:
            text = text.replace(old, new, 1)
    return text


def _run(root):
    payload = read_input()
    # Host seam (ADR-0011, M2/#261): iter_file_ops maps this host's native
    # payload to canonical per-file ops. Under Claude Code, Edit/NotebookEdit
    # map to exactly one op and MultiEdit fans to one op per edits[] entry —
    # all sharing the SAME file_path, since each of these tools targets one
    # file per call. Codex does not register this entry at all — its edits
    # arrive as apply_patch and are guarded per-op by pre-write.py
    # (docs/parity.md).
    ops = list(get_host().iter_file_ops(payload))
    if not ops:
        sys.exit(0)

    fpath = ops[0].get("file_path", "") or ""
    classes = classify_protected(fpath, root)

    # The tag that names each protected class, in message priority order.
    _CLASS_TAG = (("marker", "H-19"), ("context", "H-18"),
                  ("audit", "H-05"), ("decisions", "H-11"))

    # H-21: an "opaque" op is a host's signal that it could not map this
    # payload to a known per-file shape at all (e.g. a FailClosedHost, or a
    # future host's unparseable envelope) — ambiguity resolves CLOSED
    # (ORCHESTRATOR §2), mirroring pre-write.py's opaque handling.
    if any(op.get("kind") == "opaque" for op in ops):
        block("H-21", "This edit could not be decomposed into per-file operations, so its "
                      "targets cannot be guarded. Failing closed. Retry, or report it.")

    # A "notebook" op (NotebookEdit): its target has no append/frontmatter
    # semantics to reason about — refuse any protected target outright with a
    # class-appropriate tag (defense in depth). A notebook call always fans to
    # exactly one op, so checking ops[0] speaks for the whole call.
    if ops[0].get("notebook"):
        for cls, tag in _CLASS_TAG:
            if cls in classes:
                block(tag, "NotebookEdit may not target a protected .codearbiter artifact "
                           "(CONTEXT.md, audit logs, ADRs, or markers) — use the sanctioned "
                           "skill path.")
        sys.exit(0)

    # H-19: markers are never edited via the Edit tools (#160) — the sanctioned
    # producers write them; an Edit is tampering. Block outright.
    if "marker" in classes:
        block("H-19", "The .codearbiter/.markers/ gate tokens are not editable via the Edit "
                      "tools (#160) — editing one forges or tampers with a security/migration/ADR "
                      "gate pass. Markers are recorded only by the sanctioned gate producers.")

    # H-18: an edit to CONTEXT.md may not drop `arbiter: enabled` or corrupt the
    # frontmatter (#159) — replay every op against the file in order (a
    # MultiEdit's edits apply as one atomic batch; the resulting text after
    # ALL of them is what matters, not any single intermediate op) and
    # require the FINAL result stays enabled.
    if "context" in classes:
        enabled, malformed = frontmatter_enabled_text(_resulting_context(root, fpath, ops))
        if malformed or not enabled:
            block("H-18", "This Edit would remove or alter the `arbiter: enabled` frontmatter in "
                          ".codearbiter/CONTEXT.md (#159) — the activation switch every enforcement "
                          "hook reads. Disabling it from inside the repo would make every gate "
                          "dormant. Keep `arbiter: enabled` in a well-formed frontmatter block.")

    # H-05: the audit logs (and the /sprint decision record) are append-only — an
    # Edit must be a verifiable TAIL-ANCHORED append: old_string must be the
    # file's REAL current trailing content, and new_string must extend it.
    # (path set: _hooklib.is_audit_log)
    if "audit" in classes:
        # A batched op (MultiEdit's edits[] fan) applies as part of a batch and
        # no single entry's old_string/new_string can express a verifiable
        # pure append to an append-only file — the sanctioned append path is a
        # single Edit (or '>>'). Block it outright rather than reason about
        # the batch.
        if any(op.get("batched") for op in ops):
            block("H-05", "MultiEdit cannot guarantee a pure append to an append-only "
                          ".codearbiter audit log (overrides.log, triage.log, sprint-log.md) "
                          "(ORCHESTRATOR §7). Append with a single Edit or '>>'.")
        # Exactly one non-batched op reaches this point (Edit).
        op = ops[0]
        # reliability-003 (#172): replace_all can never be a verifiable append —
        # it rewrites EVERY occurrence of old_string, not just the tail (a
        # single-occurrence replace_all is indistinguishable from a targeted
        # rewrite, and a multi-occurrence one alters interior lines outright).
        # Reject it outright before even looking at old_string/new_string.
        if op.get("replace_all"):
            block("H-05", "An Edit with replace_all=true on an append-only .codearbiter "
                          "audit log (overrides.log, triage.log, sprint-log.md) cannot be a "
                          "verifiable pure append (ORCHESTRATOR §7) — replace_all rewrites "
                          "every matching occurrence, not just the file's tail. Append with "
                          "'>>', or a single non-replace_all Edit whose old_string is the "
                          "file's current trailing content.")
        old = op.get("old_string", "") or ""
        new = op.get("added_text", "") or ""
        # migration-003: `new.startswith("")` is ALWAYS True, so an empty
        # old_string defeats the append check entirely — it could prepend or
        # replace arbitrary content with the guard never firing. An empty
        # old_string can never be a verifiable append (there is no existing tail
        # to extend); block it outright.
        if not old:
            block("H-05", "An Edit with an empty old_string on an append-only .codearbiter "
                          "audit log (overrides.log, triage.log, sprint-log.md) cannot be a "
                          "verifiable pure append (ORCHESTRATOR §7) — every string starts with "
                          "the empty string. Append with '>>', or a single Edit whose old_string "
                          "is the file's current trailing content.")
        if not new.startswith(old):
            block("H-05", "The .codearbiter audit logs (overrides.log, triage.log, "
                          "sprint-log.md) are append-only (ORCHESTRATOR §7). This Edit alters "
                          "existing audit lines; only pure appends are permitted (new text "
                          "must extend the old text).")
        # reliability-003 (#172): new.startswith(old) alone is not enough — an
        # old_string that matches an INTERIOR line (not the file's actual
        # trailing content) still satisfies startswith, but inserts content
        # BETWEEN existing lines rather than truly appending at the end.
        # Tail-anchor against the REAL on-disk content: old_string must be
        # exactly what the file currently ends with.
        current = _read_real_text(root, fpath)
        if not is_tail_append(current, old, new):
            block("H-05", "The .codearbiter audit logs (overrides.log, triage.log, "
                          "sprint-log.md) are append-only (ORCHESTRATOR §7). This Edit's "
                          "old_string is not the file's current TRAILING content — a mid-file "
                          "insertion reorders the audit record even though new_string extends "
                          "old_string. Append with '>>', or a single Edit whose old_string is "
                          "exactly the file's current tail.")

    # H-11: ADRs may only be edited via /adr — any .md anywhere under decisions/
    # (a non-numbered draft or a nested path is still an immutable decision).
    # (path set: _hooklib.is_decisions_path)
    if "decisions" in classes:
        marker = os.path.join(root, ".codearbiter", ".markers", "adr-authoring-active")
        if not os.path.isfile(marker):
            block("H-11", "ADR files are edited only via /adr (ORCHESTRATOR §3) — user "
                          "attribution required.")
        if not marker_fresh(marker, 30):
            block("H-11", "ADR authoring marker is stale (>30 min). Re-run /adr.")

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
    # hook contract (_hooklib.py:11-15) and would silently ALLOW the Edit.
    # read_input()'s documented fail-OPEN parse behavior is unaffected: it
    # catches its own errors and returns {} before this wrapper is reached.
    try:
        _run(root)
    except SystemExit:
        raise
    except Exception:  # noqa: BLE001 — the fail-closed backstop of last resort
        traceback.print_exc(file=sys.stderr)
        block("H-00", "pre-edit guard crashed while scanning this Edit — failing "
                      "closed (ORCHESTRATOR §2) rather than silently allowing an "
                      "unscanned edit. See the traceback above; retry, or report it.")


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
