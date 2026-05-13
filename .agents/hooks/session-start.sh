#!/usr/bin/env bash
# Copyright (c) 2026 suadtl
# Author: suadtl
# Created: 2026-05-10
# File: session-start.sh

PROJECT_ROOT=$(git rev-parse --show-toplevel 2>/dev/null || pwd)
CONTEXT_FILE="$PROJECT_ROOT/.agents/projectContext/CONTEXT.md"

if [ ! -f "$CONTEXT_FILE" ] || ! grep -qE '^[[:space:]]*<!--INITIALIZED-->[[:space:]]*$' "$CONTEXT_FILE" 2>/dev/null; then
  SRC=$(find "$PROJECT_ROOT" \
    -not -path "$PROJECT_ROOT/.agents/*" \
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

# H-15: surface tickets open more than 7 days
TICKET_DIR="$PROJECT_ROOT/.agents/projectContext/tickets/open"
if [ -d "$TICKET_DIR" ]; then
  STALE=$(find "$TICKET_DIR" -maxdepth 1 -name '*.md' -mtime +7 2>/dev/null | sort)
  if [ -n "$STALE" ]; then
    COUNT=$(echo "$STALE" | wc -l | tr -d ' ')
    echo "STARTUP [H-15]: $COUNT open ticket(s) idle >7 days. Run '/ticket list' to triage:"
    echo "$STALE" | while read -r f; do
      ID=$(basename "$f" .md)
      echo "  - $ID"
    done
  fi
fi

exit 0
