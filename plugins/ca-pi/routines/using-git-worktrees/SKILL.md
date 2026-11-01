---
name: using-git-worktrees
description: OPTIONAL per-task isolation for autonomous parallel work. Routed to only on explicit opt-in by subagent-driven-development or dispatching-parallel-agents, so parallel units mutate files without colliding. Stands up one worktree per unit, works it in isolation, then integrates each unit back onto the caller's working branch for the caller's single commit-gate + finishing-a-development-branch exit. Never on the default path; it does not bypass a gate or finish per unit.
disable-model-invocation: true
---

# using-git-worktrees

OPTIONAL. Per-task filesystem isolation for parallel agent work — opt-in only, never the default path.
Routed to by `subagent-driven-development` and `dispatching-parallel-agents` when, and only when, the
caller requests isolation. If no isolation is requested, this skill does not run; parallel units share
the working tree under their own discipline.

Isolation lets concurrent units edit files without collision. It changes
nothing about the gates — the consolidated work still clears `commit-gate` and the single
`finishing-a-development-branch` terminal step, run by the caller. What it MUST NOT do is multiply
that terminal step into one PR per unit.

## Pre-flight

Read these, or STOP and surface the gap — never guess:

- `<project-root>/.codearbiter/CONTEXT.md` — confirm the repo is a git repo and the base/working branch.
- The discovered authoritative spec/plan pair for the caller's pipeline. Use its
  exact selected plan for the parallel unit list. Re-run the private bridge resolver
  `_resolve_workflow_pair` with the trusted project root and pipeline slug rather
  than reconstructing either path. For an HTML pair, load
  `<plugin-root>/includes/artifacts.md` and obtain
  HTML task and path records only through the installed engine `identity`, `index`, and symbol-scoped `read`
  operations. For a Markdown pair, use its existing Markdown task table. Worktree
  planning must not create, convert, or consult a counterpart.

Confirm the caller selected isolation within its current authorized scope AND supplied the parallel unit list
from the exact selected plan. Absent either, do not stand up worktrees. A selected isolation method is
not new authority to discard a branch or worktree.

## Phase 1 — Provision · gate: BLOCK

Stand up one worktree per parallel unit. For each unit, create a worktree on a fresh branch off the
current base, under a dedicated parent directory outside the main working tree
(e.g. `../.codearbiter-worktrees/<slug>`):

- One worktree, one branch, one unit. Never share a worktree across units.
- Branch name MUST be unique and traceable to its unit's task ID.
- Retain the integration owner, base, branch, path ownership and each worktree path in the existing handoff record; update `.codearbiter/.worktrees.json` where that scratch manifest is already supported. Do not introduce a mandatory new schema to make ordinary isolation possible.

Gate: every unit has a distinct worktree on a distinct branch, all rooted at the same verified base and recorded for resumption. Preserve unrelated dirty paths by creating a new worktree rather than cleaning, resetting, stashing or overwriting them.

## Phase 2 — Isolated work · gate: BLOCK

Each parallel unit works entirely inside its own worktree. Dispatch is unchanged — the caller still
dispatches its author and reviewer agents; they simply operate on the isolated path.

- A unit MUST NOT read or write outside its assigned worktree.
- A unit MUST NOT touch `main` or any other unit's branch.
- All implementation inside a worktree still flows through `tdd` — isolation is not a TDD bypass.

Gate: each unit's work is contained to its own worktree, with no cross-worktree or base-branch writes.

## Phase 3 — Fold back · gate: BLOCK

Integrate each isolated unit's work back onto the caller's single working branch — do NOT finish each
unit on its own. Per unit, in order:

1. Confirm the unit was accepted by the caller under its applicable completion and check contract.
   Inspect accessible command, cwd, source/input identity, output and exit status; reuse valid evidence
   and rerun only missing or affected checks. An explicit review batch retains its triaged verdict.
   An unaccepted unit does not fold back.
2. Integrate its branch onto the caller's working branch (merge or rebase), resolving any conflict
   here, in the open. Never integrate onto `main` or the default branch.

The consolidated working branch then takes the caller's normal single exit — ONE `commit-gate` pass
and ONE `finishing-a-development-branch` decision, run by the caller, not per unit. This skill
integrates; it never opens N PRs or finishes N branches. A unit that cannot integrate cleanly is
surfaced as a conflict for resolution — never force-merged, never dropped silently.

Gate: every accepted unit integrated onto the caller's working branch with conflicts resolved; no
per-unit PR or finish was opened.

## Phase 4 — Cleanup handoff · gate: BLOCK

Record which worktrees and branches remain after fold-back. Route any actual deletion through
`post-merge-cleanup` and its fetched-containment proof and explicit confirmation naming each item.
Do not auto-delete an integrated, unaccepted or abandoned unit merely to close this skill.
Keep its handoff/manifest entry until the selected cleanup action succeeds.

Gate: every remaining worktree is accounted for; no unreviewed work or user data is discarded.

## Hard rules

- MUST NOT run on the default path — isolation requires an explicit caller opt-in.
- MUST NOT share a worktree or a branch across parallel units.
- MUST NOT let a unit read or write outside its assigned worktree, or touch `main`.
- MUST NOT open a per-unit PR or run `finishing-a-development-branch` per unit — integrate accepted units onto the caller's working branch, which takes the single `commit-gate` + finishing exit.
- MUST NOT delete a branch or worktree without the separately required per-item confirmation and cleanup proof (ADR-0036). Retain and report worktrees awaiting that action.
