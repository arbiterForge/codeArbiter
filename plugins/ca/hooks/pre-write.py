#!/usr/bin/env python3
# codeArbiter v2 — PreToolUse(Write) guard. Audit-log + ADR authoring integrity.
# Python port of pre-write.sh (#25): no jq, fails loud, blocks via exit 2.
#
# Kept: H-05 (overrides.log append-only) and H-11 (ADRs only via /adr) — both
# guard the audit trail / decision record.

import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from _hooklib import block, marker_fresh, project_root, read_input, tool_input  # noqa: E402


def main():
    root = project_root()
    fpath = tool_input(read_input()).get("file_path", "") or ""

    # H-05: overrides.log is append-only — a Write is a full overwrite.
    if re.search(r"\.codearbiter/overrides\.log$", fpath):
        block("H-05", ".codearbiter/overrides.log is append-only. Use /override to add "
                      "entries (ORCHESTRATOR §7); use Edit to append, never Write.")

    # H-11: ADRs may only be authored via /adr (the skill drops the marker first).
    if re.search(r"\.codearbiter/decisions/[0-9]+-.+\.md$", fpath):
        marker = os.path.join(root, ".codearbiter", ".markers", "adr-authoring-active")
        if not os.path.isfile(marker):
            block("H-11", "ADR files are authored only via /adr (ORCHESTRATOR §3) — user "
                          "attribution required. Subagent-authored ADRs are prohibited.")
        if not marker_fresh(marker, 30):
            block("H-11", "ADR authoring marker is stale (>30 min). Re-run /adr.")

    sys.exit(0)


if __name__ == "__main__":
    main()
