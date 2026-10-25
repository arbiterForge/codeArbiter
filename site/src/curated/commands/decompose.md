---
entity: commands/decompose
related: [create-context, init, skills/decompose]
gates:
  - gate: greenfield check
    when: before the interview starts
    effect: meaningful implementation source routes to create-context; initialized projects return to normal work
  - gate: consequential decisions
    when: an unanswered choice affects the planned result
    effect: resolve that choice before its dependent output; retain other gaps as open questions
  - gate: initialization
    when: the records are confirmed and context is populated
    effect: the native engine checks that the knowledge documents exist and parse and the task board is well formed before recording initialization
---

## What it does

Develops context for a project without meaningful implementation source. The interview covers
vision, users and flows, functional scope, technical shape, integrations, and risks. It asks for
missing facts and consequential choices, using answers already recorded.

Each question is saved as a decomposition record when it is asked, and your answer is saved as
soon as you give it, so a closed session loses nothing. Answered questions stay settled: a
resumed interview continues with the open question that matters most for what you want to do
next, not a fixed first-unfinished step. A restart retires earlier records; it never deletes them.

## What you receive and review

New projects keep decomposition in one native HTML document,
`.codearbiter/decomposition/project.html`, whose records have stable IDs:

| Record | Job |
|---|---|
| `capability` | What the product does, with its initiators, inputs and outputs |
| `component` | Intended parts, responsibilities, connections and integrations |
| `phase` | MVP and later phases with measurable completion |
| `work_item` | Bounded tasks with roles, dependencies and time-boxed spikes |

Review the synthesized records. Corrections and your actual confirmation are recorded before
context population. Unresolved consequential choices hold their dependent output; open questions
stay visible. These records describe intended architecture, never existing code, and are distinct
from typed feature plans.

Population adds records to five HTML knowledge documents under `.codearbiter/context/`. Unknown
facts stay `unknown` records and planned commands stay proposed and unrun. Each approved work item
is promoted once to the task board. Initialization checks that the documents exist and parse and
that the task board is well formed; open questions do not prevent it. It does not establish
passing tests, installed-host qualification, or permission to merge.

## Repositories that keep the Markdown format

A repository scaffolded before HTML knowledge, or one whose owner keeps the Markdown format,
follows the unchanged procedure. Completed layers persist under `.codearbiter/plans/decomposition/`
and `_session.md` records the current phase, open questions and actual confirmations. Existing
confirmation covers unchanged artifacts. Decomposition writes `01-architecture-breakdown.md`,
`02-phased-build-plan.md` and `03-task-backlog.md` under `.codearbiter/plans/`. Review all three
planning documents. The native context writer then prepares and applies five
document/provenance pairs, and `--context-finalize` validates all required outputs and records
initialization. Conversion to HTML is a separate, explicit `knowledge.py convert` workflow:
read the listed files, record their meaning, then finish with its token.

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

Recorded as an answered question. The records will include pending and confirmed signup states.
```

Use [Plan a new project](/guides/plan-a-new-project/) for preparation, review and safe resumption.
If meaningful source already exists, use `/ca:create-context` instead.
