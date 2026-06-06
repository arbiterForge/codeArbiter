#!/usr/bin/env bash
# Copyright (c) 2026 suadtl
# Author: suadtl
# Created: 2026-05-10
# File: pre-write.sh

which jq > /dev/null 2>&1 || exit 0
PROJECT_ROOT=$(git rev-parse --show-toplevel 2>/dev/null || pwd)
INPUT=$(cat)
FPATH=$(echo "$INPUT" | jq -r '.tool_input.file_path // ""')
CONTENT=$(echo "$INPUT" | jq -r '.tool_input.content // ""')

# H-04: stage file is write-protected
if echo "$FPATH" | grep -qE '\.agents/projectContext/stage$'; then
  echo "BLOCKED [H-04]: .agents/projectContext/stage is write-protected. Use /stage command only (${FRAMEWORK_ROOT}/.agents/skills/stage-gating/SKILL.md)." >&2
  exit 1
fi

# H-05: overrides.log is append-only; Write = full overwrite = blocked
if echo "$FPATH" | grep -qE 'overrides\.log$'; then
  echo "BLOCKED [H-05]: overrides.log is append-only. Use /override to add entries (AGENTS.md §7). Use Edit to append, not Write." >&2
  exit 1
fi

# H-11: ADRs may only be authored via /adr (decision-lifecycle skill writes the marker)
if echo "$FPATH" | grep -qE '\.agents/projectContext/decisions/[0-9]+-.+\.md$'; then
  MARKER="$PROJECT_ROOT/.agents/.markers/adr-authoring-active"
  if [ ! -f "$MARKER" ]; then
    echo "BLOCKED [H-11]: ADR files may only be created via /adr (AGENTS.md §3). Run /adr to author an ADR with user attribution. Subagent-authored ADRs are prohibited." >&2
    exit 1
  fi
  # Stale marker (>30 min): treat as no marker
  if [ -n "$(find "$MARKER" -mmin +30 2>/dev/null)" ]; then
    echo "BLOCKED [H-11]: ADR authoring marker is stale (>30 min). Re-run /adr to refresh the authoring session." >&2
    exit 1
  fi
fi

# H-12: closed-ticket files may not carry adr-opened:* dispositions
if echo "$FPATH" | grep -qE '\.agents/projectContext/tickets/closed/.+\.md$'; then
  if echo "$CONTENT" | grep -qE '^disposition:[[:space:]]*adr-opened:'; then
    echo "BLOCKED [H-12]: 'adr-opened:*' is not a valid ticket disposition (AGENTS.md §3). Decision-worthy findings escalate to open-questions.md (CONFIRM-NN) or to the user. ADRs are authored only via /adr." >&2
    exit 1
  fi
fi

exit 0
