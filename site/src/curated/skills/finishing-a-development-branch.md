---
entity: skills/finishing-a-development-branch
related: [commands/feature, commands/sprint, commands/pr]
gates:
  - gate: terminal choice
    when: after the commit gate clears
    effect: you choose exactly one of open a PR, merge via PR, or discard — direct merge to the default branch is never an option
  - gate: pushed-work confirmation
    when: discarding a branch
    effect: any commit that isn't pushed yet is reported as a loss before the discard is confirmed, never deleted silently
---

## What it does

This is the last step of a feature or a sprint, reached only once the commit gate has cleared.
It gathers the branch's state — what changed, what the gates found, what a plan still leaves
open — then presents exactly three ways to end the branch: open a pull request and stop, open one
and merge it once checks are green, or discard it. Under an autonomous sprint, "open a PR" is
chosen automatically and the merge decision is left to you.

## Phases

1. Assemble the branch, diff, gate-result, and plan-delta facts the decision needs.
2. Present the three terminal options and stop for your choice — or, under an autonomous sprint,
   auto-select opening a PR and surface the merge decision separately.
3. Carry out exactly the chosen option: open the PR, merge through it once green, or discard after
   confirming any unpushed work you'd lose.
4. Emit a short receipt — obligations covered, gates that caught something, decisions you made,
   secrets or regressions prevented, suite time — drawn only from what's already in hand.

## Exits

Opening or merging a PR lands the work through GitHub, never by a direct push to the default
branch. A discard only proceeds after you've confirmed it against a stated summary of anything
unpushed that would be lost.
