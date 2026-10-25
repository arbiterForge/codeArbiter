---
entity: skills/decompose
related: [commands/decompose, context-creation]
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

## Deliverables and their continuing role

Decomposition is one native HTML document, `.codearbiter/decomposition/project.html`. Its
`question` records hold the interview; `capability`, `component`, `phase` and `work_item`
records hold the intended architecture, phased plan and backlog. Later reconciliation reads these
records by their stable IDs. User-decided architectural choices go through the decision-lifecycle
owner and are linked from `decision` records; unresolved choices remain open questions.

## Phases

1. Create any missing knowledge documents and read the decomposition records. Answered questions
   are settled; resume with the open question that matters most.
2. Save each question when it is asked and each actual answer as soon as it is given. Resolve
   consequential gaps before their dependent output.
3. Synthesize capability, component, phase and work-item records, show them, apply corrections and
   record the user's actual confirmation.
4. Add knowledge records for what is known, promote each approved work item once with
   `knowledge.py promote`, and preserve questions and audit history.
5. Run `knowledge.py initialize`. A refusal names the document to repair.

A repository that keeps the Markdown format follows the unchanged procedure in the skill's
`references/markdown-format.md`: interview layers under `.codearbiter/plans/decomposition/` with
`_session.md` recording progress and actual confirmations (existing confirmation covers unchanged
artifacts), three planning documents under `.codearbiter/plans/`, five document/provenance pairs
and `--context-finalize`.

## Exits

Return the populated records, outstanding choices and observed checks, then resume authorized
work. The initialized marker records completed population. Semantic correctness, passing tests
and host enforcement need their own evidence. As implementation arrives, `context-check` adds what
the code actually contains to the code map.
