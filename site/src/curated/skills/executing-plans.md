---
entity: skills/executing-plans
related: [commands/feature, subagent-driven-development, writing-plans]
runs_inside: "`/ca:feature`, for a full plan that still has work remaining. It hands each batch of tasks to the implementation step."
produces: "The current plan state, the verification actually observed and the remaining work after each batch, with `DONE` recorded as implementation progress only."
gates:
  - gate: actual prerequisite
    when: selecting the next batch
    effect: preserve real dependencies and blockers while allowing independent authorized tasks to proceed
  - gate: explicit pause
    when: the user requested an attended review point or a consequential decision remains unresolved
    effect: respect that stop for affected work; routine progress reports do not require acknowledgment
---

## What it does

Coordinates an authorized feature plan. It selects meaningful batches, passes the named task
scope to the implementation owner, and reports actual work and checks. Checkpoints organize
progress. The coordinator respects a user-requested pause and otherwise continues within the
existing authorization.

## Phases

1. Read the selected plan and actual dependencies. For HTML, query current identity and advisory
   eligibility. Inspect in-progress workers on resume so work is neither duplicated nor assumed done.
2. Select a coherent task scope, preserve blocked members, and continue independent work. Earlier
   checkpoint numbering alone is not a dependency.
3. Hand that scope to the implementation owner, which can use direct work or useful delegation
   and checks appropriate to the change.
4. Record implementation progress and actual checks, including failures and unrun verification.
   `DONE` records implementation; it does not establish passing tests or independent review.
5. Report the result and next work, continuing unless a real decision, user stop or applicable
   host/security boundary prevents the affected action.

## Exits

Return current plan state, observed verification and remaining work. Invoke the commit owner only
when committing is authorized. Never invent results, clear a user's stop, or restart the whole
specification merely because a session ended or an advisory receipt is missing.
