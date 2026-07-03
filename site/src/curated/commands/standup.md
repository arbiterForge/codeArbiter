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
---

## What it does

The daily hygiene checklist, made routine and gated: fetch and offer a fast-forward pull, list
locally-merged branches and stale worktrees for individual confirm-and-delete, surface stashes,
uncommitted changes, and un-pushed commits with a suggested next step, and run an advisory
board-drift sweep comparing recent merge history against `open-tasks.md`. Nothing destructive
happens without an explicit per-item yes, and the task board is never auto-flipped — a drifted task
is resolved only through `/ca:task done <id>`.

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

Board-drift sweep: 1 DRIFTED task (2.3a merged but not marked [x] in open-tasks.md).
Resolve with /ca:task done 2.3a — not auto-flipped here.
```

## When to reach for it

The daily cleanup pass with your yes on each destructive step. For a read-only snapshot without
acting, use `/ca:status`; to actually flip the drifted task, use `/ca:task`.
