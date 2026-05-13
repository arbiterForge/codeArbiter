#!/usr/bin/env bash
# Copyright (c) 2026 suadtl
# Author: suadtl
# Created: 2026-05-12
# File: statusline.sh

# codeArbiter custom statusline for Claude Code.
# Renders: [init] stage:N │ tasks:N q:N │ ⎇ branch[*] │ over:N
# Docs: .agents/hooks/STATUSLINE.md
# Toggle: set CODEARBITER_STATUSLINE=off

if [ "${CODEARBITER_STATUSLINE:-}" = "off" ]; then
  exit 0
fi

ROOT="${CLAUDE_PROJECT_DIR:-$PWD}"

# Claude pipes a JSON session blob (model, context_window, cost, rate_limits, …).
# Capture once so we can fan it out to the usage helper.
STDIN=$(cat 2>/dev/null || true)

GREEN=$'\033[32m'
YELLOW=$'\033[33m'
RED=$'\033[31m'
DIM=$'\033[2m'
RESET=$'\033[0m'

CONTEXT_FILE="$ROOT/.agents/projectContext/CONTEXT.md"
STAGE_FILE="$ROOT/.agents/projectContext/stage"
TASKS_FILE="$ROOT/.agents/projectContext/open-tasks.md"
QUESTIONS_FILE="$ROOT/.agents/projectContext/open-questions.md"
OVERRIDES_FILE="$ROOT/.agents/projectContext/overrides.log"

# Sentinel must be on its own line (the placeholder CONTEXT.md mentions the
# marker inside descriptive text, so a loose grep would false-positive).
if [ -f "$CONTEXT_FILE" ] && grep -qE '^[[:space:]]*<!--INITIALIZED-->[[:space:]]*$' "$CONTEXT_FILE" 2>/dev/null; then
  INIT="${GREEN}●${RESET}"
else
  INIT="${YELLOW}○${RESET}"
fi

if [ -f "$STAGE_FILE" ]; then
  STAGE=$(tr -d '[:space:]' < "$STAGE_FILE" 2>/dev/null)
fi
[ -z "${STAGE:-}" ] && STAGE="?"

TASKS=0
if [ -f "$TASKS_FILE" ]; then
  TASKS=$(grep -cE '^- ' "$TASKS_FILE" 2>/dev/null | tr -d '[:space:]')
fi
[ -z "$TASKS" ] && TASKS=0

QS=0
if [ -f "$QUESTIONS_FILE" ]; then
  QS=$(grep -cE 'CONFIRM-[0-9]+' "$QUESTIONS_FILE" 2>/dev/null | tr -d '[:space:]')
fi
[ -z "$QS" ] && QS=0

if [ "$TASKS" -gt 0 ] 2>/dev/null; then
  TASKS_OUT="${YELLOW}tasks:${TASKS}${RESET}"
else
  TASKS_OUT="${DIM}tasks:0${RESET}"
fi

if [ "$QS" -gt 0 ] 2>/dev/null; then
  QS_OUT="${RED}q:${QS}${RESET}"
else
  QS_OUT="${DIM}q:0${RESET}"
fi

BRANCH=$(git -C "$ROOT" branch --show-current 2>/dev/null)
if [ -z "$BRANCH" ]; then
  BRANCH_OUT="${DIM}⎇ —${RESET}"
elif [ -n "$(git -C "$ROOT" status --porcelain 2>/dev/null)" ]; then
  BRANCH_OUT="${YELLOW}⎇ ${BRANCH}*${RESET}"
else
  BRANCH_OUT="${GREEN}⎇ ${BRANCH}${RESET}"
fi

OVERRIDES=0
if [ -f "$OVERRIDES_FILE" ]; then
  OVERRIDES=$(grep -cvE '^(#|[[:space:]]*$)' "$OVERRIDES_FILE" 2>/dev/null | tr -d '[:space:]')
fi
[ -z "$OVERRIDES" ] && OVERRIDES=0

if [ "$OVERRIDES" -gt 0 ] 2>/dev/null; then
  OV_OUT="${RED}over:${OVERRIDES}${RESET}"
else
  OV_OUT="${DIM}over:0${RESET}"
fi

SEP=" ${DIM}│${RESET} "

USAGE_OUT=""
if [ -n "$STDIN" ] && command -v python3 >/dev/null 2>&1; then
  USAGE_OUT=$(printf '%s' "$STDIN" | python3 "$ROOT/.agents/hooks/statusline-tokens.py" 2>/dev/null || true)
fi

if [ -n "$USAGE_OUT" ]; then
  printf '%s stage:%s%s%s %s%s%s%s%s%s%s\n' \
    "$INIT" "$STAGE" "$SEP" \
    "$TASKS_OUT" "$QS_OUT" "$SEP" \
    "$BRANCH_OUT" "$SEP" \
    "$OV_OUT" "$SEP" "$USAGE_OUT"
else
  printf '%s stage:%s%s%s %s%s%s%s%s\n' \
    "$INIT" "$STAGE" "$SEP" \
    "$TASKS_OUT" "$QS_OUT" "$SEP" \
    "$BRANCH_OUT" "$SEP" \
    "$OV_OUT"
fi
