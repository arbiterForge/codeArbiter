---
description: Morning hygiene — review the day's repo state, then perform the cleanups under per-action confirmation. Fast-forward only, never destructive without a yes.
argument-hint: (none)
---

# /ca:standup — daily hygiene

The best-practice checklist you run when you sit down to code, made routine and
gated. The SessionStart briefing *reports* hygiene state read-only; this command is
where the *actions* happen — each one confirmed individually, none taken unbidden.
Arbiter gathers and proposes; you decide every mutation.

## Flow

The orchestrator reads the current repo state (reusing the briefing's read-only
computation — branch, ahead/behind, dirty tree, stashes, prune-candidate branches,
stale worktrees) and presents it, then offers each applicable action in turn. Skip
an action that has no candidates; never bundle confirmations.

1. **Fetch + fast-forward pull** — kick `git fetch`, then offer a **`--ff-only`**
   pull of the current branch. Offered ONLY on a clean working tree and only when
   the branch is behind upstream. On a dirty tree the pull is withheld and the dirty
   state is reported instead. A diverged branch (would need a merge) is refused with
   a diverged-branch message — never a merge commit.
2. **Prune merged local branches** — list local branches already merged on remote
   (the `: gone]` upstream set), excluding the current branch and the default
   (`main`). Delete a listed branch only after an explicit per-branch confirmation;
   declining leaves it in place.
3. **Remove stale worktrees** — list stale/merged worktrees (branch gone-or-merged,
   or path missing on disk), never the main worktree. Remove one only after explicit
   per-item confirmation; declining leaves it intact.
4. **Surface stashes / dirty / un-pushed** — list stashes, uncommitted changes, and
   un-pushed commits, each with a suggested next step (`/ca:commit`, `git push`,
   `git stash show`). Report-and-route only: never discard a stash, reset, or push.

Present a one-line summary of what was done and what was declined.

## When NOT to use

- A read-only state snapshot without acting → `/ca:status`.
- Install health (interpreter, payload, hooks) → `/ca:doctor`.
- Transcript hygiene to extend the session → `/ca:prune`.
- Committing staged work → `/ca:commit`.

## Hard gate

- MUST pull with `--ff-only` and ONLY on a clean working tree — never a merge
  commit, never on a dirty tree, never a rebase.
- MUST exclude the current branch and the default branch from branch pruning, and
  the main worktree from worktree cleanup.
- MUST confirm each destructive action (branch delete, worktree remove)
  individually before performing it — no batched or implied yes.
- MUST treat stash / dirty / un-pushed state as report-and-route only — never
  discard, reset, force, or push on the user's behalf.
- MUST NOT write to or force-push the default branch.
