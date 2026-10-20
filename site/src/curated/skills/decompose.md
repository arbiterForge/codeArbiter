---
entity: skills/decompose
related: [commands/decompose, context-creation]
gates:
  - gate: recorded decisions
    when: synthesizing project plans
    effect: review the three documents and record actual confirmation; existing confirmation covers unchanged artifacts
  - gate: native population
    when: writing protected context
    effect: inspect and apply native previews that bind each document to its retained sources and v2 provenance
  - gate: initialization
    when: population is complete
    effect: validate the five document/provenance pairs and independent board/audit outputs before the native writer records the initialized marker
---

## What it does

Develops greenfield context from a durable interview. It resumes existing answers and asks about
missing facts or consequential choices across six areas: vision, users and flows, functional
scope, technical shape, integrations, and risks.

## Deliverables and their continuing role

The three planning documents are `01-architecture-breakdown.md`, `02-phased-build-plan.md` and
`03-task-backlog.md` under `.codearbiter/plans/`. Review all three before context population.
They remain Markdown and are the inputs used by later reconciliation.

Completed interview layers stay under `.codearbiter/plans/decomposition/`; `_session.md` records
progress and actual confirmations. Existing confirmation covers unchanged artifacts. An
unfinished answer is not necessarily on disk. A restart preserves prior interview and decision
history. User-decided architectural choices go through the decision-lifecycle owner; unresolved
choices remain unresolved.

## Phases

1. Inspect the repository and retained interview, then resume the first unfinished step.
2. Capture missing facts and choices, persisting each completed layer. Resolve consequential
   gaps before their dependent output; record other open questions.
3. Synthesize the three planning documents, apply corrections and record actual user confirmation.
4. Use `--context-draft` and `--context-apply` to populate five protected document/provenance pairs
   from retained sources. Populate tasks through their writer and preserve questions and audit history.
5. Use `--context-finalize`, inspect its preview, and apply it through the native writer. Read back
   the result and retain the interview and plans. Remove only unreferenced temporary drafts.

## Exits

Return the populated files, outstanding choices and observed checks, then resume authorized work.
The initialized marker records completed population. Semantic correctness, passing tests and host
enforcement need their own evidence. As implementation arrives, refresh selected context against
actual source.

[Plan a new project](/guides/plan-a-new-project/) explains document review and resumption.
[Compare workflow routes](/concepts/workflow-routes/) shows the connected initialization path.
