---
description: Exit maintainer dev mode — restore orchestration, remove the dev marker, log the exit.
argument-hint: (none)
---

# /ca:arbiter — restore orchestration

The exit door for `/ca:dev`. No-op if dev mode is not active.

## Flow

1. **Log exit** — append to `${CLAUDE_PROJECT_DIR}/.codearbiter/overrides.log` (append-only, `>>`):

   ```
   [ISO-8601 timestamp] | BY: <email> | DEV: exit
   ```

2. **Marker** — remove `${CLAUDE_PROJECT_DIR}/.codearbiter/.markers/dev-active`; the statusline
   returns to normal.
3. **Resume** — re-present the startup state (stage, blocking `CONFIRM-NN`, in-flight tasks) and
   await a slash command. Orchestration, routing, and all gates are back in force.

## Hard gate

MUST write the `DEV: exit` line to `overrides.log` and remove the `dev-active` marker before resuming
orchestration — the exit is on the audit trail like the entry. MUST NOT rewrite or truncate
`overrides.log` — the append-only rule has no dev exception, on entry or exit. If a prior session
ended mid-dev, SessionStart has already appended the synthetic `BY: session-cleanup | DEV: exit` close
line and cleared the marker (`session-start.py`, observability-001). In that case MUST NOT write a
second `DEV: exit` for that orphaned entry — the close is already on the trail.
