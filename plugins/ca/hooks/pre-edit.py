#!/usr/bin/env python3
# codeArbiter v2 — PreToolUse(Edit) guard. Audit-log + ADR authoring integrity.
# Python port of pre-edit.sh (#25): no jq, fails loud, blocks via exit 2.
#
# Edits to overrides.log are allowed only when they are pure appends (the new
# text starts with the old text) — that is how /override adds entries; any
# other Edit rewrites history and is blocked (H-05). Kept: H-11 (ADRs only via
# /adr). Paths are separator-normalized so the guards fire on Windows
# backslash paths too. Runs only in arbiter-enabled repos.

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from _hooklib import (  # noqa: E402
    arbiter_active, block, is_audit_log, is_decisions_path, marker_fresh,
    norm_path, project_root, read_input, tool_input, utf8_stdio,
)


def main():
    utf8_stdio()
    root = project_root()
    if not arbiter_active(root):
        sys.exit(0)
    payload = read_input()
    tool = payload.get("tool_name", "") or ""
    ti = tool_input(payload)
    fpath = norm_path(ti.get("file_path", "") or "")

    # H-05: the audit logs (and the /sprint decision record) are append-only — an
    # Edit must leave existing lines intact (new_string extends old_string), never
    # alter or delete them. (path set: _hooklib.is_audit_log)
    if is_audit_log(fpath):
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
    if is_decisions_path(fpath):
        marker = os.path.join(root, ".codearbiter", ".markers", "adr-authoring-active")
        if not os.path.isfile(marker):
            block("H-11", "ADR files are edited only via /adr (ORCHESTRATOR §3) — user "
                          "attribution required.")
        if not marker_fresh(marker, 30):
            block("H-11", "ADR authoring marker is stale (>30 min). Re-run /adr.")

    sys.exit(0)


if __name__ == "__main__":
    main()
