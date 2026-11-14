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

Watches a pull request's CI checks to completion without polling by hand. One detached
`gh pr checks <PR> --watch` process waits; the GitHub CLI refreshes the check status itself on its
own interval, but no model call happens while checks run — arbiter is re-invoked exactly once, when
that process exits, not on a timer. On red, it retrieves the failing
job's logs and acts at a configured depth: `propose` names the likely cause and proposes a fix
without touching any tracked file (the fix itself routes through `/ca:fix` or `/ca:feature`);
`branch` additionally opens an unmergeable `spike/fix-*` branch carrying the proposed change for
review, leaving the default branch untouched. On green, it notifies and presents the merge command
as an offer — it never runs `gh pr merge` itself.

After the watcher exits, arbiter reads the current check states once and verifies
that they match the PR's current head before offering a merge. Exit zero alone is
not green: gh 2.93.0 can return zero with cancelled checks. Cancelled checks leave
verification incomplete; timed-out checks follow the red path. If the user stops
the watch, the host task times out, or the process is interrupted, arbiter reports
the stop without a green verdict or automatic restart. The refresh interval is
not a deadline, and this command sets no elapsed-time timeout. Stopping the local
watcher does not cancel GitHub workflow runs.

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
[gh refreshes the checks until every check finishes]

All checks passed.
Ready to merge:
  gh pr merge 231 --squash --delete-branch
Run it? (this command will not run it for you)
```

## When to use another command

Open the PR first with `/ca:pr`; apply a fix for a diagnosed red with `/ca:fix` or `/ca:feature`;
review a diff without watching CI with `/ca:review`.
