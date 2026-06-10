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
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from _hooklib import (  # noqa: E402
    arbiter_active, block, marker_fresh, norm_path, project_root, read_input,
    tool_input, utf8_stdio,
)


def main():
    utf8_stdio()
    root = project_root()
    if not arbiter_active(root):
        sys.exit(0)
    ti = tool_input(read_input())
    fpath = norm_path(ti.get("file_path", "") or "")

    # H-05: the audit logs are append-only — an Edit must leave existing lines
    # intact (new_string extends old_string), never alter or delete them.
    if re.search(r"\.codearbiter/(?:overrides|triage)\.log$", fpath):
        old = ti.get("old_string", "") or ""
        new = ti.get("new_string", "") or ""
        if not new.startswith(old):
            block("H-05", "The .codearbiter audit logs (overrides.log, triage.log) are "
                          "append-only (ORCHESTRATOR §7). This Edit alters existing audit "
                          "lines; only pure appends are permitted (new text must extend "
                          "the old text).")

    # H-11: ADRs may only be edited via /adr.
    if re.search(r"\.codearbiter/decisions/[0-9]+-.+\.md$", fpath):
        marker = os.path.join(root, ".codearbiter", ".markers", "adr-authoring-active")
        if not os.path.isfile(marker):
            block("H-11", "ADR files are edited only via /adr (ORCHESTRATOR §3) — user "
                          "attribution required.")
        if not marker_fresh(marker, 30):
            block("H-11", "ADR authoring marker is stale (>30 min). Re-run /adr.")

    sys.exit(0)


if __name__ == "__main__":
    main()
