---
entity: skills/decompose
related: [commands/decompose, context-creation]
use_when: "You are planning a project that has no meaningful source yet, or recording the target and next phases of an initialized one, through a resumable interview."
avoid_when: "An uninitialized repository that already has source, which is `/ca:create-context`."
asks: "The missing facts and consequential choices across vision, users and flows, functional scope, technical shape, integrations and risks. You also review the synthesized records and confirm them before context is populated."
produces: "A decomposition document of capabilities, components, phases and work items, five populated context documents, and each approved work item promoted once to the task board."
gates:
  - gate: recorded decisions
    when: synthesizing the intended project
    effect: show the synthesized records and record actual confirmation; a wording refinement needs no fresh confirmation
  - gate: record-level population
    when: writing project context
    effect: each knowledge record carries its basis; unknowns stay unknown and planned commands stay proposed and unrun
  - gate: initialization
    when: population is complete
    effect: the native engine checks that the knowledge documents exist and parse and the task board is well formed before recording the initialized marker
---

## What it does

Develops greenfield context from a resumable interview. It asks about missing facts or
consequential choices across six areas: vision, users and flows, functional scope, technical
shape, integrations, and risks, in whatever order the conversation makes natural.

Each question you answer is saved as an answered decomposition record with your actual answer. A
question that is unanswered or deferred is not a decomposition record. It is kept in
`open-questions.md`, which tracks its live status, and the decomposition links to it by identity.
A closed session therefore keeps the unanswered question there, where it can be found and resumed.
Answered questions stay settled: a resumed interview continues with the open question that matters
most for what you want to do next, not a fixed first-unfinished step. A restart retires earlier
records; it never deletes them.

## Usage

```text
/ca:decompose
```

`init --greenfield` is the preferred strategy selector; this command remains its compatibility
entry. Supply existing requirements or a sketch so the interview can focus on unanswered choices.
If meaningful source already exists in an uninitialized repository, use `/ca:create-context`
instead.

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

## Deliverables and their continuing role

Decomposition is one native HTML document, `.codearbiter/decomposition/project.html`. Its
`question` records hold the answered interview questions; `capability`, `component`, `phase` and `work_item`
records hold the intended architecture, phased plan and backlog. Later reconciliation reads these
records by their stable IDs. User-decided architectural choices go through the decision-lifecycle
owner and are linked from `decision` records; unresolved choices stay in `open-questions.md`.

| Record | Job |
|---|---|
| `capability` | What the product does, with its initiators, inputs and outputs |
| `component` | Intended parts, responsibilities, connections and integrations |
| `phase` | MVP and later phases with measurable completion |
| `work_item` | Bounded tasks with roles, dependencies and time-boxed spikes |

Review the synthesized records. Corrections and your actual confirmation are recorded before
context population. Unresolved consequential choices hold their dependent output; open questions
stay visible. These records describe intended architecture, never existing code, and are distinct
from typed feature plans. Initialization checks that the knowledge documents exist and parse and
that the task board is well formed; open questions do not prevent it. It does not establish
passing tests, installed-host qualification, or permission to merge.

## Phases

1. Create any missing knowledge documents and read the decomposition records. Answered questions
   are settled; resume with the open question that matters most.
2. Save each answered question, with your actual answer, as a decomposition record, and keep each
   unanswered or deferred question in `open-questions.md`. Resolve consequential gaps before their
   dependent output.
3. Synthesize capability, component, phase and work-item records, show them, apply corrections and
   record the user's actual confirmation.
4. Add knowledge records for what is known, promote each approved work item once with
   `knowledge.py promote`, and preserve questions and audit history.
5. Run `knowledge.py initialize`. A refusal names the document to repair.

## Repositories that keep the Markdown format

A repository scaffolded before HTML knowledge, or one whose owner keeps the Markdown format,
follows the unchanged procedure in the skill's `references/markdown-format.md`. Completed layers
persist under `.codearbiter/plans/decomposition/` and `_session.md` records the current phase,
open questions and actual confirmations. Existing confirmation covers unchanged artifacts.
Decomposition writes `01-architecture-breakdown.md`, `02-phased-build-plan.md` and
`03-task-backlog.md` under `.codearbiter/plans/`. Review all three planning documents. The native
context writer then prepares and applies five document/provenance pairs, and `--context-finalize`
validates all required outputs and records initialization. Conversion to HTML is a separate,
explicit `knowledge.py convert` workflow: read the listed files, record their meaning, then finish
with its token.

## Exits

Return the populated records, outstanding choices and observed checks, then resume authorized
work. The initialized marker records completed population. Semantic correctness, passing tests
and host enforcement need their own evidence. As implementation arrives, `context-check` adds what
the code actually contains to the code map.
