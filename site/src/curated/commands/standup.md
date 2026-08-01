---
entity: commands/standup
related: [status, task]
gates:
  - gate: per-action confirmation
    when: pruning a merged branch or removing a stale worktree
    effect: each candidate is confirmed individually before it's deleted — declining leaves it in place, and nothing is batched into one implied yes
  - gate: fast-forward-only pull
    when: the working tree is clean and the branch is behind upstream
    effect: a --ff-only pull is offered; a dirty tree withholds the pull and reports the dirty state instead, and a diverged branch is refused rather than merged
  - gate: one confirmation per archived task
    when: sweeping long-done tasks off the board
    effect: each aged item is proposed on its own and archived only on its own yes — never a batched "archive all 12?", and an undated item is never proposed at all because it cannot be aged
---

## What it does

The daily hygiene checklist, made routine and gated: fetch and offer a fast-forward pull, list
locally-merged branches and stale worktrees for individual confirm-and-delete, surface stashes,
uncommitted changes, and un-pushed commits with a suggested next step, run a read-only advisory
board-drift sweep comparing recent merge history against `open-tasks.md`, and offer to archive
long-done tasks one at a time. Nothing destructive happens without an explicit per-item yes, and
the task board is never auto-flipped — a drifted task is resolved only through
`/ca:task done <id>`.

The archival sweep exists because long-done tasks accumulate until the in-flight count stops
meaning anything. Each aged item is proposed separately and moved by its own helper call: the
record is appended to `done-tasks.md` *before* it is removed from `open-tasks.md`, so an
interrupted sweep leaves a duplicate the next run absorbs rather than a lost record. That ordering
is why the confirmations aren't batched — one yes, one move. An item marked `[x]` with no
`(done YYYY-MM-DD)` stamp can't be aged and is never proposed; it can only be archived deliberately
on request. Declining costs nothing: an unarchived task stays exactly where it is.

## Usage

```
/ca:standup
```

Takes no arguments.

## Example

```text
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
  poc.api.0004 — "rate-limit the webhook" (done 2026-05-02) — archive? (y/n)
> y
Archived poc.api.0004 to done-tasks.md.
  poc.api.0007 — "retry on 429" (done 2026-05-11) — archive? (y/n)
> n
Left poc.api.0007 on the board.
```

## When to reach for it

The daily cleanup pass with your yes on each destructive step. For a read-only snapshot without
acting, use `/ca:status`; to actually flip the drifted task, use `/ca:task`.
