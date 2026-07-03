---
entity: skills/context-creation
related: [commands/create-context, decompose]
gates:
  - gate: pre-flight confirmation
    when: before any scout is dispatched
    effect: the project must be an uninitialized brownfield codebase with real source present; if there is no source it routes to decompose instead
  - gate: gap interview
    when: after synthesis
    effect: every low-confidence inference must be resolved with you or explicitly deferred before project docs are written
  - gate: initialization lock
    when: at the end
    effect: the project is not marked initialized until every required document exists and is non-empty
---

## What it does

This is the brownfield back-fill: it wraps an existing codebase in project state without
guessing at it. Invoked by the create-context command, or automatically at startup when the
project has real source code but no initialized project state yet, it reads the codebase through
several parallel scouts, drafts the project's foundational documents from what they find, and
resolves anything uncertain with you before locking the project as initialized.

## Phases

1. Confirm the project is a genuine, uninitialized brownfield case with meaningful source present.
2. Dispatch six parallel scouts — tech stack, infrastructure, architecture, security posture,
   testing, and data model — each reporting file paths, line numbers, and named values only.
3. Synthesize every surviving project document from the scout reports, tagging each claim high,
   medium, or low confidence and turning any low-confidence gap into a numbered open question.
4. Resolve every open question with you, one targeted question at a time.
5. Write the finished documents to disk, along with a provenance record and a coarse concern map.
6. Lock the project as initialized and hand back to normal operation.

## Exits

A completed run leaves every foundational project document populated and the project marked
initialized, ready for feature work. It never proceeds past the interview with an unresolved gap,
and it refuses to run at all if the project is already initialized or has no real source to
extract from.
