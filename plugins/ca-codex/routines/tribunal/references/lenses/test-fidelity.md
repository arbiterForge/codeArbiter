# test-fidelity — lens mandate

Executed by `tribunal-lens-reviewer` under the `test-fidelity` assignment.

## Purpose / failure family
Find doubles, fixtures and simulated boundaries that misrepresent the relied-on
contract and conceal real failures. Test-fidelity owns test-boundary fidelity.

## Applicability
Tests replace a producer, external system, clock, scheduler or lifecycle with a
model whose accuracy matters to their behavioral claim.

## Skip conditions
No relevant substituted boundary or fixtures. Do not require a real external
service merely to replace a faithful, bounded test double.

## Scope emphasis
Test seams and their actual producer/consumer contracts: serialized shapes,
variants, error behavior, side effects, ordering, cancellation and cleanup.

## Required reading
- Finding record ([routines/tribunal/references/finding-record.md](../finding-record.md)) and review risk ([routines/tribunal/references/review-risk.md](../review-risk.md)).
- Verification quality ([routines/tribunal/references/verification-quality.md](../verification-quality.md)) — shared oracle discipline and complementary ownership.
- `<project-root>/.codearbiter/tech-stack.md` — mock/factory conventions and
  test harnesses; the actual producer, consumer and relevant public contract.

## Deterministic probes
Locate substituted modules and fixtures; compare their fields, variants, error
shapes and timing assumptions with producer signatures, schemas and contract
tests. Inspect casts and TODOs as leads, never as defect classifiers.

## Review questions
- Can the real producer return a state or failure the double makes impossible?
- Does the consumer rely on ordering, cancellation, side effects or cleanup that
  the fake silently omits?
- Does a stale fixture or cast bypass an invariant and let a real regression pass?
- Is any reduced fixture intentionally narrow enough for the tested obligation?

## False-positive guards / non-findings
Faithful mocks and purpose-built minimal fixtures are legitimate. A real producer
existing does not invalidate a double. Generated tests, casts and temporary
comments do not prove drift or explain who authored the fixture.

## Evidence requirements
Show the exact test/producer/consumer mismatch and the regression it hides.
For an absent contract check, state the search universe including alternate
harnesses and trace the owner; missing data irrelevant to the test is not drift.

## Exposure metric
Count of distinct substituted contracts examined, not mock-library call sites.

## Escalation / cross-lens handoff
Coverage owns missing behavioral cases and weak assertions without a seam
mismatch. Route product type-boundary defects to typesafety and runtime failures
to their domain lens; preserve one finding per root mechanism.

## Out of scope
Blanket replacement of mocks, author-intent inference, generic test counts and
implementation of new fixtures or tests.
