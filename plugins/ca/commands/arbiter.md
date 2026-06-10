---
description: Exit maintainer dev mode — restore orchestration, remove the dev marker, log the exit.
argument-hint: ""
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
