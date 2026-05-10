#!/usr/bin/env bash
CONTEXT_FILE=".agents/projectContext/CONTEXT.md"

if [ ! -f "$CONTEXT_FILE" ] || ! grep -q '<!--INITIALIZED-->' "$CONTEXT_FILE" 2>/dev/null; then
  SRC=$(find . \
    -not -path './.agents/*' \
    -not -name 'AGENTS.md' \
    -not -name 'CLAUDE.md' \
    -not -name 'README.md' \
    -not -name '.gitignore' \
    -type f 2>/dev/null | head -1)
  if [ -n "$SRC" ]; then
    echo "STARTUP [H-08]: projectContext not initialized but source code exists. Run /create-context before any other command (AGENTS.md §1 Phase 2)."
  else
    echo "STARTUP [H-08]: No projectContext and no source code. Run /decompose to begin (AGENTS.md §1 Phase 1)."
  fi
fi

exit 0
