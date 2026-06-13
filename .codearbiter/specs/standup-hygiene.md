# Spec: standup-hygiene

**Status:** APPROVED — 2026-06-13 (user: brennonhuff@gmail.com)
**Feature 1 of 2** in the "session hygiene" brainstorm (the other: `pr-babysitter`).

## Problem

Sitting down for a day of coding, you have no fast, trustworthy picture of repo
hygiene — what's dirty, stashed, un-pushed, merged-but-not-pruned, or rotting in
open questions — so the best-practice morning checklist gets skipped or done ad
hoc. codeArbiter should gather that picture and offer to act on it, without ever
acting unbidden.

## Scope

**In:**
- A SessionStart-driven **read-only hygiene briefing** (no mutation, never blocks
  on the network).
- A **background, non-blocking `git fetch`** kicked from the hook; results land on
  the next read. Offline is tolerated silently.
- A new gated command **`/ca:standup`** that performs cleanups, each confirmed
  individually at run time:
  1. Fetch + **fast-forward-only** pull of the current branch — clean tree only.
  2. Prune local branches already merged on remote.
  3. Remove stale/merged git worktrees.
  4. Surface stashes, uncommitted changes, and un-pushed commits with a suggested
     next step.

**Out of scope (the boundary that keeps this honest):**
- The hook NEVER mutates git state and NEVER makes a blocking network call.
- No auto-pull, auto-prune, auto-discard, or auto-anything — every mutation is a
  `/ca:standup` action gated behind an explicit per-action confirmation.
- `/ca:standup` NEVER merges (only fast-forward), NEVER force-anything, NEVER
  touches `main`/default destructively, NEVER deletes the current branch, NEVER
  drops a stash without confirmation, NEVER pushes.
- Not a replacement for `/ca:doctor` (install health) — this is *workflow* health.

## Behavior detail

- **Cadence:** on the **first session of the local calendar day**, emit the full
  briefing. On every later session that day, emit a **single offer line** only if
  something is actionable (dirty tree, stashes, un-pushed commits, prunable
  branches/worktrees, or behind upstream); otherwise stay silent. The
  "first-of-day" marker lives under `.codearbiter/.markers/` (gitignored), keyed by
  local date.
- **Background fetch:** the hook spawns a detached `git fetch` with a short timeout
  and returns immediately; it never delays stdout injection and never errors the
  session on a slow/offline network. The briefing reports ahead/behind from the
  most recent *completed* fetch and notes when that data is stale.
- **Briefing contents (read-only display):** current branch + ahead/behind;
  dirty/untracked summary; stash count; un-pushed commits; local branches merged
  on remote (prune candidates); stale worktrees; and a reuse of already-computed
  signals — overrides-since-last-checkpoint and aging open `CONFIRM-NN` /
  open-tasks counts. Display only; no action taken on any of these.
- **Activation:** briefing and command appear only in an `arbiter: enabled` repo,
  consistent with every other hook.

## Acceptance criteria

1. In an `arbiter: enabled` repo with no first-of-day marker for the local date,
   the SessionStart hook emits the full briefing AND writes the marker; given a
   marker already present for today, it does NOT emit the full briefing.
2. With today's marker present and at least one actionable condition true (e.g. a
   stash exists), a later session emits exactly one offer line; with the marker
   present and zero actionable conditions, it emits nothing.
3. In a repo without `arbiter: enabled`, the hook emits neither briefing nor offer
   line (dormant, like every other hook).
4. The hook completes and returns its stdout without waiting on the network: with
   `git fetch` stubbed to hang, the hook still returns within its timeout budget
   and the briefing renders from last-completed-fetch data marked stale.
5. The hook performs no git mutation: after a session start, `git status
   --porcelain`, branch list, stash list, and worktree list are byte-for-byte
   unchanged from before.
6. `/ca:standup` offers the ff-pull action only on a clean working tree; on a
   dirty tree the pull action is withheld and the dirty state is reported instead.
7. `/ca:standup` ff-pull uses `--ff-only`: given a current branch that has
   diverged (would require a merge), the pull is refused with a diverged-branch
   message and no merge commit is created.
8. `/ca:standup` branch-prune lists only branches merged on remote, excludes the
   current branch and `main`/default, and deletes a listed branch only after an
   explicit per-branch confirmation; declining leaves the branch present.
9. `/ca:standup` worktree-cleanup lists stale/merged worktrees and removes one
   only after explicit confirmation; declining leaves it intact.
10. `/ca:standup` stash/dirty/un-pushed surfacing is report-and-route only: it
    never discards a stash, never resets, never pushes — it lists state and the
    suggested next command.

## Open questions

None blocking. Design defaults chosen above (local-date day boundary; marker under
`.codearbiter/.markers/`; stale-data noting on the briefing) are sane and
revisable; no `[CONFIRM-NN]` raised.
