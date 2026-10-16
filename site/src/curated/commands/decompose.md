---
entity: commands/decompose
related: [create-context, init, skills/decompose]
gates:
  - gate: greenfield check
    when: before the interview starts
    effect: meaningful implementation source routes to create-context; initialized projects return to normal work
  - gate: consequential decisions
    when: an unanswered choice affects the planned result
    effect: resolve that choice before its dependent output; retain other gaps on the question board
  - gate: initialization
    when: the planning documents are confirmed and context is populated
    effect: the native writer validates current document/provenance pairs and board/audit outputs before recording initialization
---

## What it does

Develops context for a project without meaningful implementation source. The interview covers
vision, users and flows, functional scope, technical shape, integrations, and risks. It asks for
missing facts and consequential choices, using answers already recorded.

Completed layers persist under `.codearbiter/plans/decomposition/`. `_session.md` records the
current phase, open questions and actual user confirmations. Resume the first unfinished step;
existing confirmation covers unchanged artifacts. Restart preserves interview and decision history.

## What you receive and review

Decomposition writes three project-planning documents under `.codearbiter/plans/`:

| File | Job |
|---|---|
| `01-architecture-breakdown.md` | Components, boundaries, integrations and unresolved architectural choices |
| `02-phased-build-plan.md` | Phase outcomes, deferrals, risks and measurable completion |
| `03-task-backlog.md` | Prioritized tasks, roles, dependencies and time-boxed spikes |

Review all three planning documents. Corrections and your actual confirmation are recorded before
context population. Unresolved consequential choices hold their dependent output; explicitly
retained questions stay visible. These Markdown files are distinct from typed feature plans.

The native context writer prepares and applies five document/provenance pairs, then
`--context-finalize` validates all required outputs and records initialization. Retain the
interview, plans and decision history as source evidence. Initialization does not establish
passing tests, installed-host qualification, or permission to merge.

## Usage

```
/ca:decompose
```

`init --greenfield` is the preferred strategy selector; this command remains its compatibility
entry. Supply existing requirements or a sketch so the interview can focus on unanswered choices.

## Example

```text
Illustrative exchange, not captured execution:
> /ca:decompose

I found the recorded purpose and primary users. The next unresolved choice is whether a garden
plot signup is confirmed immediately or requires an organizer's decision.
> An organizer confirms it.

Recorded in the user-flow layer. The plan will include pending and confirmed signup states.
```

Use [Plan a new project](/guides/plan-a-new-project/) for preparation, review and safe resumption.
If meaningful source already exists, use `/ca:create-context` instead.
