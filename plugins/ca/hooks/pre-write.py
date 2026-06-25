#!/usr/bin/env python3
# codeArbiter v2 — PreToolUse(Write) guard. Audit-log + ADR authoring integrity.
# Python port of pre-write.sh (#25): no jq, fails loud, blocks via exit 2.
#
# Kept: H-05 (overrides.log append-only) and H-11 (ADRs only via /adr) — both
# guard the audit trail / decision record. Paths are separator-normalized so
# the guards fire on Windows backslash paths too. Runs only in arbiter-enabled
# repos.

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
    fpath = norm_path(tool_input(read_input()).get("file_path", "") or "")

    # H-05: the audit logs (and the /sprint decision record) are append-only —
    # a Write is a full overwrite. (path set: _hooklib.is_audit_log)
    if is_audit_log(fpath):
        block("H-05", "The .codearbiter audit logs (overrides.log, triage.log, sprint-log.md) "
                      "are append-only (ORCHESTRATOR §7). Append with Edit or '>>', never Write.")

    # H-11: ADRs may only be authored via /adr (the skill drops the marker first).
    # Any .md anywhere under decisions/ is covered — a non-numbered draft or a
    # nested path is still an immutable decision artifact. (set: is_decisions_path)
    if is_decisions_path(fpath):
        marker = os.path.join(root, ".codearbiter", ".markers", "adr-authoring-active")
        if not os.path.isfile(marker):
            block("H-11", "ADR files are authored only via /adr (ORCHESTRATOR §3) — user "
                          "attribution required. Subagent-authored ADRs are prohibited.")
        if not marker_fresh(marker, 30):
            block("H-11", "ADR authoring marker is stale (>30 min). Re-run /adr.")

    sys.exit(0)


if __name__ == "__main__":
    main()
