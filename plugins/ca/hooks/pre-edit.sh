#!/usr/bin/env bash
# codeArbiter v2 — PreToolUse(Edit) guard. ADR authoring integrity.
# No-op without jq.
#
# v2 prune: dropped H-04 (stage write-protect) and H-12 (ticket dispositions).
# Editing overrides.log is intentionally allowed (append-mode edits are how
# /override adds entries). Kept: H-11 (ADRs only via /adr).

which jq > /dev/null 2>&1 || exit 0
PROJECT_ROOT=$(git rev-parse --show-toplevel 2>/dev/null || pwd)
INPUT=$(cat)
FPATH=$(echo "$INPUT" | jq -r '.tool_input.file_path // ""')

# H-11: ADRs may only be edited via /adr.
if echo "$FPATH" | grep -qE '\.codearbiter/decisions/[0-9]+-.+\.md$'; then
  MARKER="$PROJECT_ROOT/.codearbiter/.markers/adr-authoring-active"
  if [ ! -f "$MARKER" ]; then
    echo "BLOCKED [H-11]: ADR files are edited only via /adr (ORCHESTRATOR §3) — user attribution required." >&2
    exit 1
  fi
  if [ -n "$(find "$MARKER" -mmin +30 2>/dev/null)" ]; then
    echo "BLOCKED [H-11]: ADR authoring marker is stale (>30 min). Re-run /adr." >&2
    exit 1
  fi
fi

exit 0
