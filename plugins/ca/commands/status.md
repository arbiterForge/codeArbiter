---
description: Show the project's current state at a glance — stage, open tasks, open questions, overrides since the last checkpoint, current branch. Read-only.
argument-hint: (none)
---

# /ca:status — state snapshot

A read-only summary of `.codearbiter/` state. No skill is routed to; no file is modified.

## Flow

The orchestrator reads and presents:

1. **Stage** — the `stage:` maturity value from `${CLAUDE_PROJECT_DIR}/.codearbiter/CONTEXT.md` frontmatter.
2. **Open tasks** — the count from `${CLAUDE_PROJECT_DIR}/.codearbiter/open-tasks.md`.
3. **Open questions** — the count of unresolved `[CONFIRM-NN]` placeholders in
   `${CLAUDE_PROJECT_DIR}/.codearbiter/open-questions.md`.
4. **Overrides since last checkpoint** — entries in `${CLAUDE_PROJECT_DIR}/.codearbiter/overrides.log`
   newer than the marker in `${CLAUDE_PROJECT_DIR}/.codearbiter/last-checkpoint`.
5. **Current branch** — from git.

## Output

```
## Project status — YYYY-MM-DD

Stage:            N
Branch:           <current branch>
Open tasks:       N
Open questions:   N ([CONFIRM-NN] unresolved)
Overrides since last checkpoint: N
```

If `[CONFIRM-NN]` placeholders are open, surface them — do not resolve them here.

## When NOT to use

- A full cross-cutting review → `/ca:checkpoint`.
- A specific question → `/ca:btw`.

## Hard gate

Read-only. MUST NOT modify any file. MUST NOT resolve a `[CONFIRM-NN]` it surfaces. No skill is routed
to by this command.
