---
entity: skills/brainstorming
related: [commands/feature, commands/sprint, writing-plans]
gates:
  - gate: frame the problem
    when: at the start of a new feature idea
    effect: the one-line idea must resolve to a stated problem, caller, and out-of-scope boundary before questioning begins
  - gate: spec approval
    when: after the spec is drafted
    effect: hard stop until you (or, under an autonomous sprint, a logged auto-approval) sign off; no code and no handoff to test-first work happens before that
---

## What it does

This is where a feature starts before any code exists. `/feature` opens here, and `/sprint`'s
planning stage runs the same interview. Given a one-line idea, it drives a Socratic
back-and-forth — one question at a time — until the idea is concrete enough to build from: a
named problem, a named caller, an explicit boundary of what the feature does not do, and a set
of acceptance criteria specific enough that each one maps to a single test. Anything genuinely
unresolved becomes a numbered open question on record rather than a guess.

## Phases

1. The problem, its caller, and the out-of-scope boundary are pinned down and checked against
   the project's existing context for a contradiction.
2. A question-at-a-time refinement loop closes every vague term, surfaces hidden complexity, and
   forces any real trade-off to a resolution or a recorded open question.
3. The agreed spec — problem, scope, testable acceptance criteria, open questions — is written to
   disk.
4. The spec is approved (by you directly, or by a logged automatic approval under an autonomous
   sprint) before anything moves on to test-first implementation.

## Exits

Approval hands the spec to the test-first gate, where each acceptance criterion becomes one
obligation to prove. A spec carrying an unresolved blocking question never reaches that handoff —
it stops for your decision instead.
