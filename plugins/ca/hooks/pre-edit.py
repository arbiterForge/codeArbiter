#!/usr/bin/env python3
# codeArbiter v2 — PreToolUse(Edit|MultiEdit|NotebookEdit) guard. Activation +
# audit-log + marker + ADR integrity. Python port of pre-edit.sh (#25): no jq,
# fails loud, blocks via exit 2.
#
# Guards (arbiter-enabled repo only), symlink-resolved via classify_protected
# (#162 — raw path AND realpath-resolved repo-relative form):
#   H-18  CONTEXT.md may not be edited to drop `arbiter: enabled` (#159).
#   H-19  .codearbiter/.markers/* are never edited via the Edit tools (#160).
#   H-05  audit-log Edits must be pure appends (new_string extends old_string).
#   H-11  ADRs under decisions/ are edited only via /adr.
#
# NotebookEdit is guarded too (a notebook has no append/frontmatter semantics, so
# a protected target is refused outright) — defense in depth; none of the
# protected files is a .ipynb, but the tool must not be a hole.

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from _hooklib import (  # noqa: E402
    arbiter_active, block, classify_protected, frontmatter_enabled_text,
    marker_fresh, project_root, read_input, tool_input, utf8_stdio,
)


def _resulting_context(root, fpath, tool, ti):
    """Best-effort resulting content of an Edit/MultiEdit applied to CONTEXT.md,
    so the #159 guard can vet whether the edit keeps the repo arbiter-enabled.
    Reads the real (symlink-resolved) file and replays the edit(s) the way the
    tool would. An old_string that isn't present leaves the text unchanged (the
    tool would error anyway) — harmless for the check."""
    path = fpath if os.path.isabs(fpath) else os.path.join(root, fpath)
    try:
        with open(os.path.realpath(path), encoding="utf-8", errors="replace") as f:
            text = f.read()
    except Exception:  # noqa: BLE001
        text = ""
    if tool == "MultiEdit":
        edits = ti.get("edits", []) or []
    else:
        edits = [ti]
    for e in edits:
        old = (e.get("old_string", "") or "")
        new = (e.get("new_string", "") or "")
        if e.get("replace_all"):
            text = text.replace(old, new)
        else:
            text = text.replace(old, new, 1)
    return text


def main():
    utf8_stdio()
    root = project_root()
    if not arbiter_active(root):
        sys.exit(0)
    payload = read_input()
    tool = payload.get("tool_name", "") or ""
    ti = tool_input(payload)
    # NotebookEdit carries `notebook_path`; Edit/MultiEdit carry `file_path`.
    fpath = ti.get("file_path", "") or ti.get("notebook_path", "") or ""
    classes = classify_protected(fpath, root)

    # The tag that names each protected class, in message priority order.
    _CLASS_TAG = (("marker", "H-19"), ("context", "H-18"),
                  ("audit", "H-05"), ("decisions", "H-11"))

    # NotebookEdit: a notebook is never one of the protected text artifacts, and
    # cell edits have no append/frontmatter semantics to reason about — refuse any
    # protected target outright with a class-appropriate tag (defense in depth).
    if tool == "NotebookEdit":
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

    # H-18: an Edit to CONTEXT.md may not drop `arbiter: enabled` or corrupt the
    # frontmatter (#159) — replay the edit and require the result stays enabled.
    if "context" in classes:
        enabled, malformed = frontmatter_enabled_text(_resulting_context(root, fpath, tool, ti))
        if malformed or not enabled:
            block("H-18", "This Edit would remove or alter the `arbiter: enabled` frontmatter in "
                          ".codearbiter/CONTEXT.md (#159) — the activation switch every enforcement "
                          "hook reads. Disabling it from inside the repo would make every gate "
                          "dormant. Keep `arbiter: enabled` in a well-formed frontmatter block.")

    # H-05: the audit logs (and the /sprint decision record) are append-only — an
    # Edit must leave existing lines intact (new_string extends old_string), never
    # alter or delete them. (path set: _hooklib.is_audit_log)
    if "audit" in classes:
        # MultiEdit applies a batch of edits and cannot express a verifiable pure
        # append to an append-only file — the sanctioned append path is a single
        # Edit (or '>>'). Block it outright rather than reason about the batch.
        if tool == "MultiEdit":
            block("H-05", "MultiEdit cannot guarantee a pure append to an append-only "
                          ".codearbiter audit log (overrides.log, triage.log, sprint-log.md) "
                          "(ORCHESTRATOR §7). Append with a single Edit or '>>'.")
        old = ti.get("old_string", "") or ""
        new = ti.get("new_string", "") or ""
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


if __name__ == "__main__":
    main()
