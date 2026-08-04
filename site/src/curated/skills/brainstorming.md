---
entity: skills/brainstorming
related: [commands/feature, commands/sprint, writing-plans]
gates:
  - gate: frame the problem
    when: at the start of a new feature idea
    effect: the one-line idea must resolve to a stated problem, caller, and out-of-scope boundary — and to exactly one feature, with bundles split — before any refinement begins
  - gate: spec approval
    when: after the spec is drafted and self-reviewed
    effect: hard stop until you (or, under an autonomous sprint, a logged auto-approval) sign off on a spec presented with its own adversarial findings; no code and no handoff to test-first work happens before that
---

## What it does

This is where a feature starts before any code exists. `/feature` opens here, and `/sprint`'s
planning stage runs the same interview. Given a one-line idea, it drives a Socratic
back-and-forth until the idea is concrete enough to build from: a named problem, a named
caller, an explicit boundary of what the feature does not do, a chosen approach with its
trade-off stated, and a set of acceptance criteria specific enough that each one maps to a
single test. Routine parameter choices are decided for you and recorded in the spec where you
review them; genuine forks are asked in full, with a recommendation, and batched where the
answers are independent — you decide the forks, not the ceremony. Anything genuinely
unresolved becomes a numbered open question on record rather than a guess.

## Phases

1. The problem, its caller, and the out-of-scope boundary are pinned down, checked against the
   project's existing context for a contradiction, and an idea bundling several independent
   concerns is split before any refinement effort is spent.
2. The genuine candidate approaches are laid out with their trade-offs and one recommendation;
   you choose (or a sprint's scored auto-decision does, on the record).
3. A refinement loop closes every vague term, surfaces hidden complexity, and forces any real
   trade-off to a resolution or a recorded open question — with a breaker that stops a
   non-converging loop and forces one adjudication instead of circling.
4. The agreed spec — problem, approach, scope, decided parameters, testable acceptance
   criteria, open questions — is written to disk.
5. The spec is self-reviewed mechanically, challenged adversarially (the strongest case
   against the design travels with it), and then approved — by you directly, or by a logged
   automatic approval under an autonomous sprint — before anything moves on to test-first
   implementation.

## Exits

Approval hands the spec to the test-first gate, where each acceptance criterion becomes one
obligation to prove. A spec carrying an unresolved blocking question never reaches that handoff —
it stops for your decision instead.
