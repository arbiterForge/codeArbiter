#!/usr/bin/env bash
which jq > /dev/null 2>&1 || exit 0
INPUT=$(cat)
FPATH=$(echo "$INPUT" | jq -r '.tool_input.file_path // ""')

# H-04: stage file is write-protected
if echo "$FPATH" | grep -qE '\.agents/projectContext/stage$'; then
  echo "BLOCKED [H-04]: .agents/projectContext/stage is write-protected. Use /stage command only (stage-gating/SKILL.md)." >&2
  exit 1
fi

# H-05: overrides.log is append-only; Write = full overwrite = blocked
if echo "$FPATH" | grep -qE 'overrides\.log$'; then
  echo "BLOCKED [H-05]: overrides.log is append-only. Use /override to add entries (AGENTS.md §7). Use Edit to append, not Write." >&2
  exit 1
fi

exit 0
