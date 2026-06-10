---
description: Maintainer override — suspend orchestration to edit codeArbiter itself. Env-gated (CODEARBITER_DEV=1), entry/exit logged to overrides.log.
argument-hint: "[note]"
---

# /ca:dev — maintainer override

Suspends orchestration for working ON codeArbiter — skill, agent, command, and hook bodies,
`ORCHESTRATOR.md`, settings. Not for project work; for that, use the normal commands or
`/ca:override`.

## Flow

1. **Env gate** — check the `CODEARBITER_DEV` environment variable. Not set to `1` → refuse in one
   line ("dev mode requires CODEARBITER_DEV=1") and remain in orchestration. This keeps the mode a
   deliberate maintainer posture, not a casual bypass.
2. **Log entry** — detect identity from `git config user.email`; append to
   `${CLAUDE_PROJECT_DIR}/.codearbiter/overrides.log` (append-only, `>>`):

   ```
   [ISO-8601 timestamp] | BY: <email> | DEV: enter | NOTE: <note or —>
   ```

3. **Marker** — drop `${CLAUDE_PROJECT_DIR}/.codearbiter/.markers/dev-active` (gitignored UI flag);
   the statusline turns alarm-red so dev mode is unmistakable.
4. **Mode** — plain, direct coding assistant: no routing, no skills, no gates, no `[CONFIRM-NN]`
   surfacing, no redirect. Persists until `/ca:arbiter` or a new session.

## Hard gate

MUST refuse without `CODEARBITER_DEV=1`. MUST write the `DEV: enter` log line before suspending
orchestration. Even in dev mode, `overrides.log` is never rewritten — the append-only rule has no
dev exception.

## When NOT to use

- Bypassing a single gate on project work → `/ca:override "reason"`.
- Asking a question → `/ca:btw`.
