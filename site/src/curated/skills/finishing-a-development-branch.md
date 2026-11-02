---
entity: skills/finishing-a-development-branch
related: [commands/feature, commands/sprint, commands/pr]
gates:
  - gate: current-head verification
    when: preparing a PR or terminal branch action
    effect: verify the actual branch diff with applicable checks, secrets scanning and required specialized review
  - gate: terminal choice
    when: current-head verification is assembled and no action is selected
    effect: choose open PR, merge via PR, or discard; preserve an already selected action
  - gate: discard confirmation
    when: discarding a branch
    effect: confirm the named branch and report any unpushed work that would be lost before discarding
---

## Branch disposition

Prepares a PR or carries out the selected branch disposition using current-head evidence,
deriving obligations from the explicit base-to-HEAD diff. Reuse applicable results only while their
source and inputs match, and run missing or affected checks without creating an unnecessary commit.

Authorized uncommitted work goes through the commit owner. `DONE` describes implementation
progress; unfinished work, missing tests and unresolved decisions remain visible.

A direct open-PR request keeps that selection; an autonomous sprint selects open PR only.
If no action is selected, it presents exactly three ways to finish: open a PR, merge through a PR,
or discard. `pr --watch` and `pr --cleanup` dispatch directly to their own owners.

## Phases

1. Assemble the actual branch/base, diff, current-head checks, review findings and plan delta.
2. If the request or caller has not selected an action, present the three terminal options.
   Otherwise retain the existing selection.
3. Carry out the chosen option, requiring exact-head hosted CI before an authorized merge and
   confirming any unpushed work that would be lost before discarding the named branch.
4. Report observed commit/PR identities, implemented scope, checks, review and remaining work.
   Keep implementation, verification, merge and publication distinct.

## Exits

Opening a PR leaves it open; only an authorized merge through that PR lands the work. Preserve
required ADR source ancestry and the reviewed head. Never force-push or directly push to the
default branch. Missing, failed or inapplicable checks remain pending.
