---
name: ca-standup
description: Daily repo hygiene — review the day's repo state, then perform the cleanups under per-action confirmation. Fast-forward only, never destructive without a yes.
argument-hint: (none)
---

# /ca-standup — daily hygiene

The best-practice checklist you run when you sit down to code, made routine and
gated. The SessionStart briefing *reports* hygiene state read-only; this command is
where the *actions* happen — each one confirmed individually, none taken unbidden.
Arbiter gathers and proposes; you decide every mutation.

## Flow

The orchestrator reads the current repo state (reusing the briefing's read-only
computation — branch, ahead/behind, dirty tree, stashes, prune-candidate branches,
stale worktrees) and presents it, then offers each applicable action in turn. Skip
an action that has no candidates; never bundle confirmations across different
actions or items — branch deletions always stay per-item, and the sole exception
is step 3's explicitly enumerated worktree group, which is still one confirmation
that names every member, never an implied yes.

1. **Fetch + fast-forward pull** — kick `git fetch`, then offer a **`--ff-only`**
   pull of the current branch. Eligibility is the briefing summary's
   `ff_pull_eligible` flag (SH-6: clean working tree AND behind upstream) — the same
   pure helper the SessionStart briefing computes, not a condition re-derived here.
   On a dirty tree the pull is withheld and the dirty state is reported instead. A
   diverged branch (would need a merge) is refused with a diverged-branch message —
   never a merge commit.
2. **Prune merged local branches** — list local branches already merged on remote
   (the `: gone]` upstream set), excluding the current branch and the default
   (`main`). Delete a listed branch only after an explicit per-branch confirmation;
   declining leaves it in place.

   A `: gone]` branch that was squash-merged will typically **refuse** plain
   `git branch -d` — its upstream is already pruned, so `-d` has nothing to test
   reachability against. Before reporting that as a stop, check for a merged PR
   record: `gh pr list --head <branch> --state merged --json headRefOid`. When a
   `MERGED` PR's `headRefOid` equals that branch's local tip, containment is
   proven and `git branch -D` is permitted — with the proof stated and the
   branch named in the confirmation — mirroring the `post-merge-cleanup` Phase 5
   contract. Without that proof, a refusal stays a report-and-stop; never guess.
3. **Remove stale worktrees** — list stale/merged worktrees (branch gone-or-merged,
   or path missing on disk), never the main worktree. Present the full stale list
   together with each item's evidence, then offer removal as an explicitly
   **enumerated group** — one confirmation that names every member — as well as
   per-item confirmation for anyone who wants to keep some. Declining the group
   falls back to per-item confirmation, and declining any item leaves it intact.
4. **Surface stashes / dirty / un-pushed** — list stashes, uncommitted changes, and
   un-pushed commits, each with a suggested next step (`/ca-commit`, `git push`,
   `git stash show`). Report-and-route only: never discard a stash, reset, or push.
5. **Advisory board-drift sweep** — run `git log` over the recent merge window
   (since the last `ca`-scoped tag, or a rolling 30-day window when no tag exists)
   and pipe that text to
   `python3 "<plugin-root>/hooks/boardsync.py" reconcile || python "<plugin-root>/hooks/boardsync.py" reconcile`.
   Display the advisory drift report as-is: DRIFTED tasks (work merged but board
   state not `[x]`) and informational UNKNOWN ids (in the log but absent from the
   board). This step is read-only and best-effort — the dotted-id grep can miss a
   task never named in a commit. The board is never mutated here; `open-tasks.md`
   is never written. Any drifted task must be resolved explicitly through
   `/ca-task done <id>` — the only blessed board writer. State this clearly to the
   user; do not auto-flip.

6. **Archival sweep — proposed per item, never batched** (B-24). Long-done tasks
   accumulate on the board and inflate the in-flight count until it stops meaning
   anything. List the done items older than the cutoff, then ask about **each one
   separately** and archive only the ones the user says yes to:
   `python3 "<plugin-root>/hooks/taskwrite.py" archive <id> || python "<plugin-root>/hooks/taskwrite.py" archive <id>`.

   One confirmation per item, one helper call per item — the two map 1:1 on
   purpose. A batched "archive all 12?" turns twelve decisions into one, and the
   helper's own per-item ordering (append to `done-tasks.md` first, then remove
   from `open-tasks.md`) is what makes an interrupted sweep recoverable; a batch
   loop that answered once would throw that away.

   An item marked `[x]` with **no `(done YYYY-MM-DD)` stamp** cannot be aged, so
   it is never in the proposed set. Offer it only if the user asks, and only with
   `--allow-undated` — both `/ca-task done` and the board classifier require
   the stamp, so an unstamped entry is legacy or override-era and its real age is
   unknown.

   Declining is always available and costs nothing: an unarchived task stays
   exactly where it is. Never archive without a yes.

Present a one-line summary of what was done and what was declined.

## When NOT to use

- A read-only state snapshot without acting → `/ca-status`.
- Install health (interpreter, payload, hooks) → `/ca-doctor`.
- Committing staged work → `/ca-commit`.

## Hard gate

- MUST pull with `--ff-only` and ONLY on a clean working tree — never a merge
  commit, never on a dirty tree, never a rebase.
- MUST exclude the current branch and the default branch from branch pruning, and
  the main worktree from worktree cleanup.
- MUST confirm branch deletions individually — no batched or implied yes.
  Worktree removals MAY be confirmed as one explicitly enumerated group (naming
  every member) or individually; either way there is no implied yes, and
  declining the group falls back to per-item confirmation rather than removing
  anything.
- MUST treat stash / dirty / un-pushed state as report-and-route only — never
  discard, reset, force, or push on the user's behalf.
- MUST NOT write to or force-push the default branch.
- MUST NOT auto-flip any board entry during the drift sweep — the sweep is advisory
  and read-only; resolving a drifted task is the user's decision and routes
  exclusively through `/ca-task done <id>`.
