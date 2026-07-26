# Maturity → minimum coverage

The single source of truth for the coverage threshold. Coverage scales with the maturity value
(`stage:` in `CONTEXT.md`) — a rigor knob, not a promotion gate. Referenced by `tdd` Phase 5 and
`refactor` Phase 2.

| maturity | minimum coverage |
|---|---|
| 1 | ≥ 60% |
| 2 | ≥ 70% |
| 3 | ≥ 85% |
| 4 | ≥ 90% |

## Which metric (issue #507)

**Lines and branches. Both must clear the threshold.** A report satisfying one and not the other
does not pass.

This was previously unstated, and the omission was load-bearing rather than cosmetic: a coverage
report gives four numbers that disagree, so "≥ 70%" without a column named is not a threshold anyone
can be held to. Measured on codeArbiter itself at the time of writing, one tree sat at 85.37% lines
and 78.73% branches — compliant at maturity 3, or not, depending purely on which column the reader
picked.

- **Lines** catches code no test reaches at all — a `catch` block with zero executions inside a
  passing suite, which no assertion is ever going to surface.
- **Branches** catches the untaken half of a condition a test does reach: the error arm of an `if`,
  the fallback of a `??`. Line coverage alone reports those as covered.
- **Statements** duplicates lines closely enough to add nothing. **Functions** is the noisiest
  column at small counts, where one uncovered helper moves it several points.

**The number is the floor, not the goal.** A test written only to move a percentage is worse than
the gap it closed, because it converts an honest red into a green that asserts nothing. When
backfilling to clear this bar, work the uncovered *report* — error and refusal paths first — and let
the number follow.

Where a surface has no coverage tooling at all, there is no numeric floor to check. Record that
explicitly; do not invent a command, and do not treat the phase as passed unexamined.
