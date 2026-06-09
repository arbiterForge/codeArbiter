#!/usr/bin/env python3
# codeArbiter v2 — PreToolUse(Edit) guard. ADR authoring integrity.
# Python port of pre-edit.sh (#25): no jq, fails loud, blocks via exit 2.
#
# Editing overrides.log is intentionally allowed (append-mode edits are how
# /override adds entries). Kept: H-11 (ADRs only via /adr).

import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from _hooklib import block, marker_fresh, project_root, read_input, tool_input  # noqa: E402


def main():
    root = project_root()
    fpath = tool_input(read_input()).get("file_path", "") or ""

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
