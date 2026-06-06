#!/usr/bin/env bash
# codeArbiter v2 — PreToolUse(Bash) guard. Branch/push/staging safety.
# No-op without jq. These are core safety rules; they survive the v2 cut.

which jq > /dev/null 2>&1 || exit 0
INPUT=$(cat)
CMD=$(echo "$INPUT" | jq -r '.tool_input.command // ""')

# H-01: no commit directly to main/master
if echo "$CMD" | grep -qE 'git\s+commit'; then
  BRANCH=$(git branch --show-current 2>/dev/null)
  if [ "$BRANCH" = "main" ] || [ "$BRANCH" = "master" ]; then
    echo "BLOCKED [H-01]: Direct commit to $BRANCH is prohibited (ORCHESTRATOR §3). Create a feature branch." >&2
    exit 1
  fi
fi

# H-02: no force-push
if echo "$CMD" | grep -qE 'git\s+push.*(--force|-f)(\s|$)'; then
  echo "BLOCKED [H-02]: Force-push is prohibited (ORCHESTRATOR §3)." >&2
  exit 1
fi

# H-03: no wildcard git staging — stage explicitly (commit-gate)
if echo "$CMD" | grep -qE 'git\s+add\s+(-A|\.)(\s|$)'; then
  echo "BLOCKED [H-03]: 'git add -A' / 'git add .' are prohibited. Stage files explicitly (commit-gate skill)." >&2
  exit 1
fi

exit 0
