---
entity: skills/finishing-a-development-branch
related: [commands/feature, commands/sprint, commands/pr]
gates:
  - gate: terminal choice
    when: after the commit gate clears, when no action is selected
    effect: you choose exactly one of open a PR, merge via PR, or discard — direct merge to the default branch is never an option
  - gate: pushed-work confirmation
    when: discarding a branch
    effect: any commit that isn't pushed yet is reported as a loss before the discard is confirmed, never deleted silently
---

## What it does

For PR creation and branch disposition, this owner runs after the current-head commit
gate. A direct open-PR request already selects that action, without a repeated terminal
menu. `pr --watch` and `pr --cleanup` dispatch to their existing owners before these
creation prerequisites. They do not create a PR or inherit its unrelated gates.

At the end of a feature or sprint, this is the finishing step.
It gathers the branch state: what changed, what the gates found, and what the plan still
leaves open. If no action is selected, it presents exactly three ways to finish: open a PR
and stop, merge through a PR after the required checks, or discard with confirmation.
A direct open-PR request keeps that selection; an autonomous sprint selects open PR only
and leaves the merge decision to you.

## Phases

1. Assemble the branch, diff, gate-result, and plan-delta facts the decision needs.
2. If the request or caller has not selected an action, present the three terminal options
   and stop for your choice. Otherwise retain the selected action; sprint's selection is
   open PR only, with the merge decision surfaced separately.
3. Carry out exactly the chosen option: open the PR, merge through it once green, or discard after
   confirming any unpushed work you'd lose.
4. Emit a short receipt — obligations covered, gates that caught something, decisions you made,
   secrets or regressions prevented, suite time — drawn only from what's already in hand.

## Exits

Opening a PR leaves it open; only an authorized merge through that PR lands the work.
Neither path directly pushes to the default branch. A discard only proceeds after you've confirmed it against a stated summary of anything
unpushed that would be lost.
