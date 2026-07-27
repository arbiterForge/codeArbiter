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

## The no-tooling exemption — cite it, never assert it

Where a surface has no coverage tooling at all, there is no numeric floor to check. Record that
explicitly; do not invent a command, and do not treat the phase as passed unexamined.

**The record MUST quote the `tech-stack.md` Coverage section it read, and name the surface it found
no command for.** An agent that could not FIND the command is indistinguishable, from the inside,
from a surface that genuinely HAS none — and the two demand opposite responses: the first is a STOP,
the second is this exemption. Only the citation separates them, and it is what makes the exemption
falsifiable by a reviewer rather than a claim that closes a BLOCK gate on the word of the agent that
wanted through it.

So: no citation, no exemption. A phase that cannot produce the quoted section STOPs and surfaces the
gap instead — the same response the skills' hard rule already requires for a missing test or lint
command. This is deliberately the narrower reading: the failure mode being guarded is a gate that
reads as satisfied without executing, which is what issue #507 found in five suites at once.

Consumers of this rule: `tdd` Phase 5, `refactor` Phase 2 and Phase 6, and the `coverage-auditor`
agent. They MUST NOT restate the exemption's conditions locally — divergent copies are how Phase 2
and Phase 6 could start giving different answers about the same surface.
