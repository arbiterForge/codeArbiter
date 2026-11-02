---
entity: skills/brainstorming
related: [commands/feature, commands/sprint, writing-plans]
runs_inside: "`/ca:feature` and `/ca:sprint`, as the step that turns your request into a specification. `/ca:spike` findings can seed it too."
produces: "A saved specification with stable criterion IDs, observable acceptance criteria and any genuinely open decisions, returned to the planning step."
gates:
  - gate: consequential choice
    when: the requested outcome conflicts with a requirement or leaves a material product decision unresolved
    effect: ask the actual decision owner while continuing independent work; preserve already settled choices and explicit user stops
  - gate: source integrity
    when: saving the specification
    effect: use the selected representation and typed writer for HTML; conflicting writes and structural failures must be resolved before claiming the artifact was saved
---

## What it does

Refines feature or sprint intent into a useful specification under the existing authorization.
Start from the requested outcome and answers already recorded. Clarify consequential product
choices, accepted ADR conflicts and explicit exclusions; choose reversible implementation methods
within the agreed scope without repeating an interview.

Acceptance criteria name the trigger, expected behavior and relevant boundary conditions, covered
by one or more named tests where behavior is executable. Coverage can be many-to-many. Ask what
would remain broken if every criterion passed so that a consistent list does not hide missing intent.

## Phases

1. State the problem, observable result, scope and exclusions.
2. Consider genuine trade-offs and recommend a viable approach. Ask only about unresolved
   consequential choices, preserving current owner decisions.
3. Make acceptance observable, recording meaningful parameters and genuinely open decisions.
4. Save the selected specification through its native representation. For HTML, retain stable
   criterion IDs and use typed writes and readback.
5. Review the saved result for consistency, exclusions and plausible failure modes, then return
   its identity, criteria and open decisions to the planning owner.

## Exits

The caller continues its useful planning sequence. A user-requested review pause still applies,
but maintaining a spec does not require separate artifact approval. Draft readiness describes
structure and coverage; it does not prove implementation or grant commit, merge or publication
authority. Resume an existing spec at its unfinished step.

[Review specifications and plans](/guides/review-artifacts/) explains the documents to inspect.
[The Evidence Behind the Persona](/concepts/persona-research-basis/) provides the research context.
