---
entity: skills/using-git-worktrees
related: [subagent-driven-development, dispatching-parallel-agents]
gates:
  - gate: provisioning
    when: setting up isolated units
    effect: every parallel unit must land on its own distinct worktree and branch off the same clean base, recorded in a manifest, before any isolated work begins
  - gate: teardown
    when: after fold-back
    effect: every worktree this skill created must be removed and the manifest cleared before the skill returns — an orphaned worktree counts as a failure
---

## What it does

This is optional, per-task filesystem isolation for parallel agent work — it only runs when the
implementation engine or the parallel-dispatch primitive explicitly opts into it, never by
default. It gives concurrent units their own working tree each so they can edit files without
colliding, then folds every accepted unit's work back onto the caller's single working branch,
which still takes exactly one pass through the commit gate and the branch-finishing step.

## Phases

1. Stand up one worktree and one branch per parallel unit, all rooted at the same clean base, and
   record each in a manifest.
2. Let each unit do its work entirely inside its own worktree, still routed through the test-first
   gate — isolation changes nothing about that requirement.
3. Integrate every accepted unit's branch back onto the caller's single working branch, resolving
   any conflict in the open rather than force-merging.
4. Remove every worktree this skill created and clear the manifest.

## Exits

The consolidated working branch goes through the caller's usual single exit path — a single pass
through the commit gate followed by a single branch-finishing decision, never one of either per
unit. This skill never opens a pull request or finishes a branch on its own; it only provisions,
folds back, and tears down.
