---
entity: skills/refactor
related: [commands/refactor, tdd]
gates:
  - gate: surface sign-off
    when: before any coverage work begins
    effect: the exact files, symbols, and signatures being restructured must be named precisely and confirmed with you — a vague description does not pass
  - gate: parity coverage
    when: before implementation
    effect: every public method in the named surface needs at least one direct pre-existing test, backfilled via the test-first gate if missing
  - gate: parity verification
    when: after implementation
    effect: the full suite must pass with zero modifications to any pre-existing test — a changed test is treated as evidence the behavior itself changed
---

## What it does

This is the behavior-preserving restructure path, invoked by the refactor command for a rename,
extract, inline, move, dedup, or internal-implementation swap. It proves — through unmodified
pre-existing tests, not inspection — that the code's externally observable behavior is identical
before and after. Anything that turns out to add behavior gets redirected to the test-first gate
as a feature or fix instead of proceeding as a refactor.

## Phases

1. Name the exact files, symbols, and signatures the refactor will touch, and get it confirmed.
2. Prove pre-existing tests already cover that surface well enough to catch a behavior change,
   backfilling through the test-first gate if they don't.
3. Where the refactor exposes a genuinely new seam, pin its contract with a failing test first.
4. Apply the restructure, confined strictly to the named surface, with no added behavior.
5. Run the full suite and confirm zero pre-existing tests were modified to make it pass.
6. Run lint, type-checking, and coverage, confirming no regression on the touched surface.

## Exits

A clean run clears the path to the commit gate with behavioral parity proven, not asserted. Any
diff that turns out to add a behavior, branch, or side effect is redirected to the test-first gate
instead of continuing as a refactor.
