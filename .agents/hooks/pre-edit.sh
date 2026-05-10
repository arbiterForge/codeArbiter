#!/usr/bin/env bash
which jq > /dev/null 2>&1 || exit 0
INPUT=$(cat)
FPATH=$(echo "$INPUT" | jq -r '.tool_input.file_path // ""')

# H-04: stage file is write-protected even via Edit
# Note: Edit on overrides.log is intentionally allowed (append-mode edits are fine per AGENTS.md §7)
if echo "$FPATH" | grep -qE '\.agents/projectContext/stage$'; then
  echo "BLOCKED [H-04]: .agents/projectContext/stage is write-protected. Use /stage command only (stage-gating/SKILL.md)." >&2
  exit 1
fi

exit 0
