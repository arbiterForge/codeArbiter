---
entity: skills/refactor
related: [commands/refactor, tdd]
gates:
  - gate: authorized surface
    when: before any coverage work begins
    effect: inspect and name the exact files, symbols and signatures; proceed under existing authorization and ask only about a consequential missing scope decision
  - gate: parity coverage
    when: before implementation
    effect: every public method needs at least one direct test; passing characterization tests can establish missing baseline coverage before restructuring
  - gate: parity verification
    when: after implementation
    effect: baseline parity tests pass with preserved behavioral assertions; necessary mechanical import or symbol-reference updates retain the same oracle
---

## Phases

1. Inspect and name the exact files, symbols and signatures covered by the request. Present the
   scope table and continue without duplicate signoff when the existing authorization covers it.
2. Prove pre-existing tests already cover that surface well enough to catch a behavior change,
   adding passing characterization tests before restructuring if they don't. Record the
   post-backfill baseline and its behavioral assertions.
3. Where the refactor exposes a genuinely new seam, pin its contract with a failing test first.
4. Apply the restructure with no added behavior. Maintain the table for necessary in-scope
   consumer updates; obtain authorization for a materially broader outcome.
5. Run the baseline parity tests locally. Preserve behavioral assertions; necessary import or
   symbol-reference updates must retain the same oracle. Require exhaustive exact-head hosted CI
   before merge.
6. Run lint, type-checking, and coverage, confirming no regression on the touched surface.

## Exits

A clean run clears the path to the commit gate with behavioral parity proven, not asserted. Any
diff that turns out to add a behavior, branch, or side effect is redirected to the test-first gate
instead of continuing as a refactor.
