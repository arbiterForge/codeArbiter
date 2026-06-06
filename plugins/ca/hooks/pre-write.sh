#!/usr/bin/env bash
# codeArbiter v2 — PreToolUse(Write) guard. Audit-log + ADR authoring integrity.
# No-op without jq.
#
# v2 prune: dropped H-04 (stage file write-protect — stage is now a frontmatter
# config value, not a gated file) and H-12 (ticket dispositions — ticketing cut).
# Kept: H-05 (overrides.log append-only) and H-11 (ADRs only via /adr) — both
# guard the audit trail / decision record, which v2 keeps.

which jq > /dev/null 2>&1 || exit 0
PROJECT_ROOT=$(git rev-parse --show-toplevel 2>/dev/null || pwd)
INPUT=$(cat)
FPATH=$(echo "$INPUT" | jq -r '.tool_input.file_path // ""')

# H-05: overrides.log is append-only — a Write is a full overwrite.
if echo "$FPATH" | grep -qE '\.codearbiter/overrides\.log$'; then
  echo "BLOCKED [H-05]: .codearbiter/overrides.log is append-only. Use /override to add entries (ORCHESTRATOR §7); use Edit to append, never Write." >&2
  exit 1
fi

# H-11: ADRs may only be authored via /adr (the skill drops the marker first).
if echo "$FPATH" | grep -qE '\.codearbiter/decisions/[0-9]+-.+\.md$'; then
  MARKER="$PROJECT_ROOT/.codearbiter/.markers/adr-authoring-active"
  if [ ! -f "$MARKER" ]; then
    echo "BLOCKED [H-11]: ADR files are authored only via /adr (ORCHESTRATOR §3) — user attribution required. Subagent-authored ADRs are prohibited." >&2
    exit 1
  fi
  if [ -n "$(find "$MARKER" -mmin +30 2>/dev/null)" ]; then
    echo "BLOCKED [H-11]: ADR authoring marker is stale (>30 min). Re-run /adr." >&2
    exit 1
  fi
fi

exit 0
