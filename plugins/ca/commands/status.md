---
description: Show the project's current state at a glance — stage, open tasks, open questions, overrides since the last checkpoint, current branch. Read-only.
argument-hint: (none)
---

# /ca:status — state snapshot

A read-only summary of `.codearbiter/` state. No skill is routed to; no file is modified.

## Flow

The orchestrator reads and presents:

1. **Stage** — the `stage:` maturity value from `${CLAUDE_PROJECT_DIR}/.codearbiter/CONTEXT.md` frontmatter.
2. **Pipelines** — every slug in `${CLAUDE_PROJECT_DIR}/.codearbiter/specs/` and `plans/`, with how
   far each got: spec awaiting approval, spec approved / no plan, plan in progress (`ACCEPTED` count
   vs. total from the plan's status column), or complete. An interrupted pipeline is resumable via
   `/ca:feature` — say so on its line.
3. **Open tasks** — the count from `${CLAUDE_PROJECT_DIR}/.codearbiter/open-tasks.md`.
4. **Open questions** — the count of unresolved `[CONFIRM-NN]` placeholders in
   `${CLAUDE_PROJECT_DIR}/.codearbiter/open-questions.md`.
5. **Overrides since last checkpoint** — entries in `${CLAUDE_PROJECT_DIR}/.codearbiter/overrides.log`
   newer than the marker in `${CLAUDE_PROJECT_DIR}/.codearbiter/last-checkpoint`.
6. **Current branch** — from git.

## Output

```
## Project status — YYYY-MM-DD

Stage:            N
Branch:           <current branch>
Pipelines:
  <slug>          plan 3/7 ACCEPTED — resume with /ca:feature "<slug>"
  <slug>          spec approved, no plan
Open tasks:       N
Open questions:   N ([CONFIRM-NN] unresolved)
Overrides since last checkpoint: N
```

No specs and no plans → `Pipelines: none`.

If `[CONFIRM-NN]` placeholders are open, surface them — do not resolve them here.

## When NOT to use

- A full cross-cutting review → `/ca:checkpoint`.
- A specific question → `/ca:btw`.

## Hard gate

Read-only. MUST NOT modify any file. MUST NOT resolve a `[CONFIRM-NN]` it surfaces. No skill is routed
to by this command.
