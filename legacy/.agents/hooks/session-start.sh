#!/usr/bin/env bash
# Copyright (c) 2026 suadtl
# Author: suadtl
# Created: 2026-05-10
# File: session-start.sh

PROJECT_ROOT=$(git rev-parse --show-toplevel 2>/dev/null || pwd)
CONTEXT_FILE="$PROJECT_ROOT/.agents/projectContext/CONTEXT.md"

# Derive FRAMEWORK_ROOT by resolving this script's physical location.
#
# Vendored install (per /init-vendor): ${PROJECT_ROOT}/.agents/ is a REAL
# directory whose subdirs (skills/, agents/, commands/, hooks/, settings.json)
# are individually symlinked into vendor/codearbiter/.agents/. projectContext/
# is a real directory consumer-owned at PROJECT_ROOT — never in the vendor
# tree. So ${BASH_SOURCE[0]} is e.g. ${PROJECT_ROOT}/.agents/hooks/session-start.sh
# (the symlink path); `pwd -P` after cd resolves it to the physical path under
# vendor/codearbiter/.agents/hooks/ and we strip two levels to get FRAMEWORK_ROOT.
#
# Monolith install (this repo): no symlinks; physical path == invocation path
# and FRAMEWORK_ROOT collapses to PROJECT_ROOT.
HOOKS_DIR=$(cd "$(dirname "${BASH_SOURCE[0]}")" 2>/dev/null && pwd -P)
if [ -n "$HOOKS_DIR" ] && [ -f "$(dirname "$(dirname "$HOOKS_DIR")")/.agents/AGENTS-CODEARBITER-ROOT" ]; then
  FRAMEWORK_ROOT=$(dirname "$(dirname "$HOOKS_DIR")")
else
  FRAMEWORK_ROOT="$PROJECT_ROOT"
fi

# Phase 0 — Monolith Self-Edit Detection (per AGENTS.md §1 Phase 0).
# When the framework is being edited as source (not consumed as a vendored
# dependency), suppress the H-08 bootstrap nag. Validity requires BOTH:
#   (a) FRAMEWORK_ROOT == PROJECT_ROOT (this is the framework's own monolith
#       layout, not a vendored install where FRAMEWORK_ROOT diverges)
#   (b) ${FRAMEWORK_ROOT}/.agents/SELF-EDIT-MODE sentinel present
#       (gitignored; per-developer opt-in)
#   (c) ${FRAMEWORK_ROOT}/.agents/AGENTS-CODEARBITER-ROOT sentinel present
#       (committed; verifies this IS the codeArbiter installation root)
SELF_EDIT_ACTIVE=0
if [ "$FRAMEWORK_ROOT" = "$PROJECT_ROOT" ] \
   && [ -f "$FRAMEWORK_ROOT/.agents/SELF-EDIT-MODE" ] \
   && [ -f "$FRAMEWORK_ROOT/.agents/AGENTS-CODEARBITER-ROOT" ]; then
  SELF_EDIT_ACTIVE=1
  echo "STARTUP [SELF-EDIT]: Framework self-edit mode active. H-08 bootstrap nag suppressed. Routing treats \${FRAMEWORK_ROOT}/.agents/** as in-scope code (AGENTS.md §1 Phase 0)."
fi

if [ "$SELF_EDIT_ACTIVE" -eq 0 ] && { [ ! -f "$CONTEXT_FILE" ] || ! grep -qE '^[[:space:]]*<!--INITIALIZED-->[[:space:]]*$' "$CONTEXT_FILE" 2>/dev/null; }; then
  FIND_ARGS=(
    -not -path "$PROJECT_ROOT/.git/*"
    -not -path "$PROJECT_ROOT/.agents/*"
    -not -path "$PROJECT_ROOT/.claude/*"
    -not -name 'AGENTS.md'
    -not -name 'CLAUDE.md'
    -not -name 'README.md'
    -not -name 'LICENSE'
    -not -name '.gitignore'
    -not -name '.gitmodules'
  )
  if [ "$FRAMEWORK_ROOT" != "$PROJECT_ROOT" ]; then
    FIND_ARGS+=(-not -path "$FRAMEWORK_ROOT/*")
  fi
  SRC=$(find "$PROJECT_ROOT" "${FIND_ARGS[@]}" -type f 2>/dev/null | head -1)
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
