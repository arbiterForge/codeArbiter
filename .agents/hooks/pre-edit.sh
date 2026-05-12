#!/usr/bin/env bash
which jq > /dev/null 2>&1 || exit 0
PROJECT_ROOT=$(git rev-parse --show-toplevel 2>/dev/null || pwd)
INPUT=$(cat)
FPATH=$(echo "$INPUT" | jq -r '.tool_input.file_path // ""')
NEW=$(echo "$INPUT" | jq -r '.tool_input.new_string // ""')

# H-04: stage file is write-protected even via Edit
# Note: Edit on overrides.log is intentionally allowed (append-mode edits are fine per AGENTS.md §7)
if echo "$FPATH" | grep -qE '\.agents/projectContext/stage$'; then
  echo "BLOCKED [H-04]: .agents/projectContext/stage is write-protected. Use /stage command only (${FRAMEWORK_ROOT}/.agents/skills/stage-gating/SKILL.md)." >&2
  exit 1
fi

# H-11: ADRs may only be authored via /adr (decision-lifecycle skill writes the marker)
if echo "$FPATH" | grep -qE '\.agents/projectContext/decisions/[0-9]+-.+\.md$'; then
  MARKER="$PROJECT_ROOT/.agents/.markers/adr-authoring-active"
  if [ ! -f "$MARKER" ]; then
    echo "BLOCKED [H-11]: ADR files may only be edited via /adr (AGENTS.md §3). Run /adr to author or revise an ADR with user attribution." >&2
    exit 1
  fi
  if [ -n "$(find "$MARKER" -mmin +30 2>/dev/null)" ]; then
    echo "BLOCKED [H-11]: ADR authoring marker is stale (>30 min). Re-run /adr to refresh the authoring session." >&2
    exit 1
  fi
fi

# H-12: closed-ticket files may not carry adr-opened:* dispositions (Edit may insert one)
if echo "$FPATH" | grep -qE '\.agents/projectContext/tickets/closed/.+\.md$'; then
  if echo "$NEW" | grep -qE '^disposition:[[:space:]]*adr-opened:'; then
    echo "BLOCKED [H-12]: 'adr-opened:*' is not a valid ticket disposition (AGENTS.md §3). Decision-worthy findings escalate to open-questions.md (CONFIRM-NN) or to the user. ADRs are authored only via /adr." >&2
    exit 1
  fi
fi

exit 0
