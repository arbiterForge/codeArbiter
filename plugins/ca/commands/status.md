---
description: Show the project's current state at a glance — stage, open tasks, open questions, overrides since the last checkpoint, current branch. Read-only.
argument-hint: "(none) | drift"
---

# /ca:status — state snapshot

A read-only summary of `.codearbiter/` state. No skill is routed to; no file is modified.

<!-- catalog-command-modes:start -->
## Drift mode

<!-- command-mode:drift legacy-route:context-check -->
With the exact argument `drift`, load and follow
`${CLAUDE_PLUGIN_ROOT}/skills/context-check/SKILL.md`. The audit begins read-only; re-scout or re-baseline may
write only after the user's explicit selection. In drift mode the `context-check` contract governs;
the opening summary and Hard gate below apply only to the no-argument snapshot. With no argument,
continue with the unchanged read-only snapshot below. Reject other arguments rather than treating
them as drift mode.

An initialized refresh is a separate explicit scoped or full selection handled
by that existing owner after its read-only report. Neither this argument nor an
ordinary status snapshot authorizes a write, a create-context retry or marker
reset.
<!-- catalog-command-modes:end -->

## Flow

The orchestrator reads and presents:

1. **Stage** — the `stage:` maturity value from `${CLAUDE_PROJECT_DIR}/.codearbiter/CONTEXT.md` frontmatter.
2. **Pipelines** — every slug in `${CLAUDE_PROJECT_DIR}/.codearbiter/specs/` and `plans/`, preserving
   its existing representation. For HTML, use the installed engine's bounded structured reads
   (`identity`, `index`, symbol-scoped `read`, or `task-context`) through
   `${CLAUDE_PLUGIN_ROOT}/includes/artifacts.md`; do not read rendered markup or execute verification
   to obtain status. For Markdown, read its actual status ledger without creating a counterpart.
   Report a spec with no plan, implementation in progress, or implementation complete. Count
   `DONE` and historical `ACCEPTED` toward implementation completion while retaining their
   distinct labels. Show verification separately: pending, failed, unknown, or the recorded result
   and its applicability when available. Completion alone does not establish a passing check,
   current acceptance, review, or release. Report missing/unreadable state as unknown, not complete.
   A draft spec or plan is not awaiting permission. Show a genuine unresolved product decision,
   explicit user checkpoint, or `BLOCKED` stop with its actual reason; status never clears it.
   An interrupted pipeline is resumable via `/ca:feature` — say so on its line.
3. **Open tasks** — the in-flight count from `${CLAUDE_PROJECT_DIR}/.codearbiter/open-tasks.md`
   (top-level `- ` bullets excluding done `- [x]`; the same `_taskboardlib` count the
   statusline and SessionStart hook use).
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
  <slug>          implementation 3/7 complete (2 DONE, 1 historical ACCEPTED); verification unknown — resume with /ca:feature "<slug>"
  <slug>          spec present, no plan
Open tasks:       N
Open questions:   N ([CONFIRM-NN] unresolved)
Overrides since last checkpoint: N
```

No specs and no plans → `Pipelines: none`.

If `[CONFIRM-NN]` placeholders are open, surface them — do not resolve them here.

## When NOT to use

- A full cross-cutting review → `/ca:checkpoint`.
- A specific question → ask it directly; no command needed.

## Hard gate

Read-only. MUST NOT modify any file. MUST NOT resolve a `[CONFIRM-NN]` it surfaces. No skill is routed
to by this command.
