---
entity: skills/tdd
related: [commands/feature, commands/fix, commands/refactor, commit-gate]
gates:
  - gate: obligation scan
    when: before any code is written
    effect: every verifiable claim about the change — spec, contract, or security — must be listed with a source and status before implementation starts
  - gate: red
    when: before implementation
    effect: a failing test must exist for every obligation, failing for the right reason, with every pre-existing test still green
  - gate: obligation verify
    when: after the implementation is green
    effect: every obligation must move to a genuinely covered state backed by a real passing test, or the workflow loops back to write one
---

## What it does

This is the test-first gate — no feature code exists before it clears its first phase. The
feature command routes here after your spec is approved, and the fix and refactor commands route
here directly. It turns the spec (or the fix's regression obligation) into a list of concrete,
verifiable claims, forces a failing test for each one before any implementation, then verifies
coverage and cleanliness before the change is eligible for the commit gate.

## Phases

1. Derive every obligation the change must satisfy from the spec, the contract, and — where
   relevant — the security boundary, before any code is written.
2. Write a failing test for each obligation, confirming it fails for the right reason and that
   every pre-existing test still passes.
3. Write the minimum implementation that satisfies those tests, without weakening any assertion.
4. Walk the obligation list again, moving each to genuinely covered by a real passing test, or
   looping back to write one for anything missing.
5. Confirm coverage meets the project's current maturity-scaled threshold.
6. Run lint and type-checking with zero errors outstanding.

## Exits

A clean run leaves every obligation covered, coverage at threshold, and lint clean — clearing the
path to the commit gate. Any obligation that cannot be tied to a real test, or any test whose
assertion had to be weakened to pass, keeps the change from moving forward.
