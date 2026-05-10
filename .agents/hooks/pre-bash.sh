#!/usr/bin/env bash
which jq > /dev/null 2>&1 || exit 0
INPUT=$(cat)
CMD=$(echo "$INPUT" | jq -r '.tool_input.command // ""')

# H-01: no commit directly to main/master
if echo "$CMD" | grep -qE 'git\s+commit'; then
  BRANCH=$(git branch --show-current 2>/dev/null)
  if [ "$BRANCH" = "main" ] || [ "$BRANCH" = "master" ]; then
    echo "BLOCKED [H-01]: Direct commit to $BRANCH is prohibited (AGENTS.md §3). Create a feature branch." >&2
    exit 1
  fi
fi

# H-02: no force-push
if echo "$CMD" | grep -qE 'git\s+push.*(--force|-f)(\s|$)'; then
  echo "BLOCKED [H-02]: Force-push is prohibited (AGENTS.md §3)." >&2
  exit 1
fi

# H-03: no wildcard git staging
if echo "$CMD" | grep -qE 'git\s+add\s+(-A|\.)(\s|$)'; then
  echo "BLOCKED [H-03]: git add -A and git add . are prohibited. Stage files explicitly (commit-gate/SKILL.md Phase 6)." >&2
  exit 1
fi

exit 0
