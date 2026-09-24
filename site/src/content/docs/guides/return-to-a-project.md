---
title: Return to a Project
description: "Orient to repository state, select the right existing lane, and resume work without restarting or treating a task-board label as proof."
journey:
  level: Practitioner
  time: "10 min"
  outcome: "A justified next action based on the actual branch, artifacts, questions and evidence."
  prerequisites:
    - An initialized repository open in a supported host
  proof: "You can name what is unfinished, what authority is missing, and why the next action is safe."
---

Start by understanding the existing work. You do not need to memorize a command catalog or
reinitialize a repository whenever you return. State your intent naturally; the orchestrator
routes understood work. Explicit commands are useful when you want a particular entry point.

## 1. Confirm where you are

In a native terminal, read `git rev-parse --show-toplevel`, `git branch --show-current`, and
`git status --short`. Confirm your coding host has that same checkout open. Preserve unrelated
changes and another person's work. Do not reset, clean or switch branches solely to make the
starting state resemble a tutorial.

Ask for a read-only project status. The explicit spellings are `/ca:status`, `$ca-status` and
`/ca-status` for Claude Code, Codex and Pi respectively. Look at stage, current branch, unfinished
pipelines, task counts, unresolved questions and overrides. If installation health is uncertain,
run the host's doctor command before starting changes.

## 2. Find the authoritative record

| Question | Inspect |
|---|---|
| What does this project intend to build? | Project context and, for greenfield work, the architecture, phased plan and backlog |
| What does this change promise? | Its specification and current acceptance criteria |
| What remains to implement or verify? | Its plan, dependencies, scope state and current evidence |
| What has been queued or assigned? | `open-tasks.md`, through the task command |
| Who must answer an unresolved fact? | The relevant `[CONFIRM-NN]` in `open-questions.md` |
| Which architectural choice governs this path? | Its accepted ADR, governing paths and supersession chain |

All these project records live under `.codearbiter/`. A task-board checkbox is not a substitute
for plan acceptance or current test evidence. For typed work, ask the coordinator for validated
artifact reads rather than inferring execution readiness from a filename or a textual status
summary. See [the artifact model](/concepts/artifacts/).

## 3. Choose the smallest fitting action

| Intent | Appropriate route or question |
|---|---|
| Understand something without changing files | Ask directly and state that the answer should remain read-only |
| Investigate an unexplained failure | Debug/investigation first, then a bounded fix once the defect is understood |
| Repair a reproduced defect | Fix, with a regression obligation |
| Add caller-visible behavior | Feature, or sprint for an explicitly bounded autonomous package |
| Preserve behavior while changing structure | Refactor, with parity obligations |
| Explore an uncertain approach | A time-boxed spike with a findings-only exit |
| Inspect a diff without creating a report | Review |
| Persist a periodic cross-cutting review | Checkpoint; tribunal is the separate deeper review |
| Resolve disagreement among architectural artifacts | Reconcile, not ordinary Git text-merge resolution |

Explicit entries are listed in [Reference](/reference/). Existing aliases still resolve, but
ordinary questions do not require the deprecated `btw` entry. Clear intent does not grant
missing authority for spending, destructive actions, overrides or merging.

## 4. Continue the existing work

Name the existing slug and ask the lane to report its last valid checkpoint before resuming.
Do not create a duplicate specification merely because the previous conversation is gone.
An approved spec may need planning; an interrupted task may need reconciliation; a finished
plan may still need fresh verification, review, commit or PR work.

For example: “Resume the saved-search export feature. First report the existing artifacts,
current branch, blocked decisions and next eligible work. Keep unrelated edits intact.”

The [recovery guide](/guides/resume-and-recover/) distinguishes stale reads, missing capability,
blocked tasks and uncertain transaction outcomes. A repeated failed approach should not consume
unbounded retries or silently reset a blocked task.

## 5. Finish with a legible handoff

Before stopping, ask for the artifact paths, accepted versus remaining work, unresolved decisions,
last verification and its source identity, and the next safe action. Confirm important records
actually reached disk. A conversation summary is useful orientation, not durable proof.

Use the task command for board transitions; use the owning lane for typed-plan transitions.
Do not hand-edit protected records to make them match a desired completion claim.
For a complete example, follow [Your first feature](/guides/first-feature/).
