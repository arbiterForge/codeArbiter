#!/usr/bin/env bash
# codeArbiter v2 — SessionStart activation hook (the linchpin).
#
# Detects an arbiter-enabled repo and injects the orchestrator persona +
# startup state into context. A plugin has no CLAUDE.md to load an always-on
# persona, so the SessionStart hook does it: in a repo whose
# `.codearbiter/CONTEXT.md` frontmatter sets `arbiter: enabled`, this prints
# ORCHESTRATOR.md (+ live state) to stdout, which Claude Code adds to context.
#
# Injection is via PLAIN STDOUT, not hookSpecificOutput.additionalContext:
# additionalContext from a plugin-scoped hook is unreliable (claude-code #16538),
# whereas plain stdout is added to context dependably.
#
# In any repo WITHOUT the flag, the hook exits silently (dormant) — the plugin
# can be installed globally and stays out of the way everywhere else.

set -u

# Project root: git toplevel is reliable; ${CLAUDE_PROJECT_DIR} is buggy in
# plugin hooks (claude-code #9354), so do not depend on it.
PROJECT_ROOT=$(git rev-parse --show-toplevel 2>/dev/null || pwd)
# Plugin root: ${CLAUDE_PLUGIN_ROOT} is reliable in hooks; fall back to this
# script's own location for local/dogfood runs.
PLUGIN_ROOT="${CLAUDE_PLUGIN_ROOT:-$(cd "$(dirname "${BASH_SOURCE[0]}")/.." 2>/dev/null && pwd)}"

CTX="$PROJECT_ROOT/.codearbiter/CONTEXT.md"

# Activation gate: `arbiter: enabled` inside the leading YAML frontmatter block.
arbiter_enabled() {
  [ -f "$CTX" ] || return 1
  awk '
    NR==1 { sub(/^\357\273\277/, "") }        # tolerate a leading UTF-8 BOM
    NR==1 && $0!="---" { exit 1 }             # no opening delimiter -> not enabled
    NR==1 { next }
    $0=="---" { code = (found?0:1); decided=1; exit code }   # closing delimiter -> decide here
    tolower($0) ~ /^arbiter:[[:space:]]*enabled[[:space:]]*$/ { found=1 }
    # exit re-enters END, so compute the verdict there: honor a real decision
    # (closing --- seen); treat EOF-with-no-close as invalid frontmatter -> not enabled.
    END { exit (decided ? code : 1) }
  ' "$CTX" 2>/dev/null
}

if ! arbiter_enabled; then
  exit 0   # dormant
fi

# --- Arbiter active: inject persona ---
if [ -f "$PLUGIN_ROOT/ORCHESTRATOR.md" ]; then
  cat "$PLUGIN_ROOT/ORCHESTRATOR.md"
  echo
fi

# --- Inject live startup state (Phase 3 / §1 of the persona) ---
echo "=== codeArbiter startup state ==="

# Initialization check: CONTEXT.md must carry a real body, not just the flag.
if ! grep -qE '<!--[[:space:]]*INITIALIZED[[:space:]]*-->' "$CTX" 2>/dev/null; then
  # Distinguish greenfield (no source) from brownfield (source exists).
  SRC=$(find "$PROJECT_ROOT" \
        -not -path "$PROJECT_ROOT/.git/*" \
        -not -path "$PROJECT_ROOT/.codearbiter/*" \
        -not -path "$PROJECT_ROOT/.claude/*" \
        -not -path "$PROJECT_ROOT/legacy/*" \
        -not -name 'README.md' -not -name 'LICENSE' -not -name '.gitignore' \
        -not -name 'AGENTS.md' -not -name 'CLAUDE.md' -not -name '.gitmodules' \
        -type f 2>/dev/null | head -1)
  if [ -n "$SRC" ]; then
    echo "NOT INITIALIZED: source exists but .codearbiter/CONTEXT.md is a stub. Run /create-context before any other command."
  else
    echo "NOT INITIALIZED: empty project. Run /decompose to begin."
  fi
  echo "Type /ca:commands for the catalog."
  exit 0
fi

# stage = a single maturity config value carried in frontmatter (stage-gating's
# 4-stage promotion machinery was cut; maturity is just a number now).
STAGE=$(awk -F':[[:space:]]*' '/^stage:[[:space:]]*[0-9]/ {print $2; exit}' "$CTX" 2>/dev/null | tr -d '[:space:]')
[ -z "$STAGE" ] && STAGE="—"
echo "stage: $STAGE"

OQ="$PROJECT_ROOT/.codearbiter/open-questions.md"
if [ -f "$OQ" ]; then
  QN=$(grep -cE 'CONFIRM-[0-9]+' "$OQ" 2>/dev/null | tr -d '[:space:]'); [ -z "$QN" ] && QN=0
  if [ "$QN" -gt 0 ] 2>/dev/null; then
    echo "BLOCKING questions (CONFIRM-NN): $QN — must resolve before dependent work proceeds:"
    grep -E 'CONFIRM-[0-9]+' "$OQ" 2>/dev/null | sed 's/^/  /'
  else
    echo "open questions: 0"
  fi
fi

OT="$PROJECT_ROOT/.codearbiter/open-tasks.md"
if [ -f "$OT" ]; then
  TN=$(grep -cE '^- ' "$OT" 2>/dev/null | tr -d '[:space:]'); [ -z "$TN" ] && TN=0
  echo "in-flight tasks: $TN"
fi

echo "Present this state, then await a slash command. Type /ca:commands for the catalog."
exit 0
