---
entity: commands/watch
related: [pr, review]
gates:
  - gate: no auto-merge
    when: CI turns green
    effect: notifies and offers the ready-to-run merge command; never runs it itself
  - gate: default-branch merge
    when: the offered merge targets the default branch
    effect: routes through the merge-to-default hard gate — the offer cannot bypass it
---

## What it does

Watches a pull request's CI checks to completion without polling by hand. The wait is a real
server-side block (`gh pr checks <PR> --watch`), so it costs nothing while checks run — arbiter is
re-invoked exactly once, when that process exits, not on a timer. On red, it retrieves the failing
job's logs and acts at a configured depth: `propose` names the likely cause and proposes a fix
without touching any tracked file (the fix itself routes through `/ca:fix` or `/ca:feature`);
`branch` additionally opens an unmergeable `spike/fix-*` branch carrying the proposed change for
review, leaving the default branch untouched. On green, it notifies and presents the merge command
as an offer — it never runs `gh pr merge` itself.

`CODEARBITER_BABYSIT` (default off) governs whether `/ca:pr` auto-attaches a watcher to the PR it
opens; `/ca:watch <PR>` itself works ad-hoc regardless of that flag.

## Usage

```
/ca:watch <PR number | url | branch>
```

Defaults to the current branch's PR when the argument names none of those.

## Example

```text
> /ca:watch 231

watching PR #231 checks... (gh pr checks 231 --watch)
[blocks server-side until every check finishes]

All checks passed.
Ready to merge:
  gh pr merge 231 --squash --delete-branch
Run it? (this command will not run it for you)
```

## When to reach for it

Open the PR first with `/ca:pr`; apply a fix for a diagnosed red with `/ca:fix` or `/ca:feature`;
review a diff without watching CI with `/ca:review`.
