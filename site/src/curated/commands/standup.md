---
entity: commands/standup
related: [status, task]
use_when: "You want the daily cleanup pass: fast-forward the current branch when it is clean and behind its upstream, clear merged branches and stale worktrees, and surface stashes, uncommitted changes and tasks that look done."
avoid_when: "A read-only snapshot, which is `/ca:status`; install health, which is `/ca:doctor`; transcript hygiene, which is `/ca:prune`; or committing staged work, which is `/ca:commit`."
asks: "A yes for each merged branch to delete, a yes for the stale worktrees (as one named group or one by one), and a named subset of long-done tasks to archive (all, some or none). Nothing is removed or archived without it."
produces: "A hygiene report with suggested next steps, and only the removals and archives you approved. The task board is never flipped for you."
gates:
  - gate: per-action confirmation
    when: pruning a merged branch or removing a stale worktree
    effect: branch deletions are confirmed one at a time; stale worktrees may be confirmed as one explicitly enumerated group naming every member, or individually if you'd rather keep some — either way declining leaves items in place, and nothing is ever an implied yes
  - gate: fast-forward-only pull
    when: the working tree is clean and the branch is behind upstream
    effect: a --ff-only pull is offered; a dirty tree withholds the pull and reports the dirty state instead, and a diverged branch is refused rather than merged
  - gate: one named subset per archive sweep
    when: sweeping long-done tasks off the board
    effect: the aged tasks are listed with their dates and you are asked once which ones to archive, and you may name all, some or none; only the IDs you name are archived, silence is never read as a yes, and an undated task is left out unless you ask for its exact ID
---

## What it does

The daily hygiene checklist, made routine and gated: fetch and offer a fast-forward pull of the
current branch, list
locally-merged branches for individual confirm-and-delete, list stale worktrees for either
confirm-and-delete as one named group or individually, surface stashes, uncommitted changes, and
un-pushed commits with a suggested next step, run a read-only advisory board-drift sweep comparing
recent merge history against `open-tasks.md`, and offer to archive long-done tasks as one named
subset that you choose. Nothing destructive happens without an explicit yes, and the task board is
never auto-flipped. On a legacy board, a drifted task is resolved only through `/ca:task done <id>`.
With native work the sweep reports that drift is not assessed.

A locally-merged branch that was squash-merged (its upstream already pruned to `: gone]`) will
typically refuse a plain `git branch -d`. When that happens, `standup` checks the merged PR record
for that branch; if it proves containment (the PR's `headRefOid` matching the branch's local tip),
`-D` is offered instead, with the proof and the branch name both stated in the confirmation.
Without that proof, a refusal is reported and left alone.

Stale worktrees are presented together with the evidence for each, then offered as one explicitly
enumerated group — naming every member — so a multi-lane day doesn't turn into four or five
identical yes prompts. Declining the group falls back to confirming each worktree on its own;
either way, the main worktree is never touched and nothing is removed without a yes.

The archival sweep exists because long-done tasks accumulate until the in-flight count stops
meaning anything. The sweep lists every aged task with its date and asks once for a named subset to
archive. You can pick all, some or none, and that one answer authorizes only the IDs you named.
Each task is then re-checked and moved by its own helper call, one at a time. On a legacy board the
record is appended to `done-tasks.md` *before* it is removed from `open-tasks.md`, so an
interrupted sweep leaves a duplicate the next run absorbs rather than a lost record. A selection is
one choice, not one atomic write: if a task is refused, or has changed since the list was shown,
the sweep reports what was archived and what remains. The archive is written in a fresh worktree on
its own branch, so it never mixes into your current work, and it goes through the normal PR path.

An item marked `[x]` with no `(done YYYY-MM-DD)` stamp can't be aged and is left out of the list;
it is archived only if you ask for its exact ID. Declining costs nothing: an unarchived task stays
exactly where it is.

## Usage

```
/ca:standup
```

Takes no arguments.

## Example

```text
Illustrative exchange on a legacy board project, not captured execution:
> /ca:standup

Fetched. Branch is 2 commits behind origin/main, tree clean — fast-forward pull? (y/n)
> y
Pulled 2 commits.

Locally-merged branches:
  fix/typo-in-readme — delete? (y/n)
> y
Deleted fix/typo-in-readme.

Board-drift sweep: 1 DRIFTED task (poc.docs.0001 merged but not marked [x] in open-tasks.md).
Resolve with /ca:task done poc.docs.0001. The sweep never auto-flips tasks.

Archival sweep: 3 done tasks older than the cutoff.
  poc.api.0004  "rate-limit the webhook"  (done 2026-05-02)
  poc.api.0007  "retry on 429"            (done 2026-05-11)
  poc.api.0009  "log the retry count"     (done 2026-05-12)
Which of these should be archived? Name any, all or none.
> poc.api.0004 poc.api.0009
Archived poc.api.0004 to done-tasks.md.
Archived poc.api.0009 to done-tasks.md.
Left poc.api.0007 on the board.
```
