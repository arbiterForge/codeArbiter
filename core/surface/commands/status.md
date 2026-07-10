---
description: Show the project's current state at a glance — stage, open tasks, open questions, overrides since the last checkpoint, current branch. Read-only.
argument-hint: (none)
---

# {{CMD:status}} — state snapshot

A read-only summary of `.codearbiter/` state. No skill is routed to; no file is modified.

## Flow

The orchestrator reads and presents:

1. **Stage** — the `stage:` maturity value from `{{PROJECT_DIR}}/.codearbiter/CONTEXT.md` frontmatter.
2. **Pipelines** — every slug in `{{PROJECT_DIR}}/.codearbiter/specs/` and `plans/`, with how
   far each got: spec awaiting approval, spec approved / no plan, plan in progress (`ACCEPTED` count
   vs. total from the plan's status column), or complete. An interrupted pipeline is resumable via
   `{{CMD:feature}}` — say so on its line.
3. **Open tasks** — the in-flight count from `{{PROJECT_DIR}}/.codearbiter/open-tasks.md`
   (top-level `- ` bullets excluding done `- [x]`; the same `_taskboardlib` count the
   {{IF:claude}}statusline and {{END}}SessionStart hook use{{IF:claude}}{{ELSE}}s{{END}}).
4. **Open questions** — the count of unresolved `[CONFIRM-NN]` placeholders in
   `{{PROJECT_DIR}}/.codearbiter/open-questions.md`.
5. **Overrides since last checkpoint** — entries in `{{PROJECT_DIR}}/.codearbiter/overrides.log`
   newer than the marker in `{{PROJECT_DIR}}/.codearbiter/last-checkpoint`.
6. **Current branch** — from git.

## Output

```
## Project status — YYYY-MM-DD

Stage:            N
Branch:           <current branch>
Pipelines:
  <slug>          plan 3/7 ACCEPTED — resume with {{CMD:feature}} "<slug>"
  <slug>          spec approved, no plan
Open tasks:       N
Open questions:   N ([CONFIRM-NN] unresolved)
Overrides since last checkpoint: N
```

No specs and no plans → `Pipelines: none`.

If `[CONFIRM-NN]` placeholders are open, surface them — do not resolve them here.

## When NOT to use

- A full cross-cutting review → `{{CMD:checkpoint}}`.
- A specific question → `{{CMD:btw}}`.

## Hard gate

Read-only. MUST NOT modify any file. MUST NOT resolve a `[CONFIRM-NN]` it surfaces. No skill is routed
to by this command.
