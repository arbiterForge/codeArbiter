# test-fidelity — lens mandate

Executed by `tribunal-test-fidelity-reviewer`. Evidence-or-drop on every check. Report observable state only; do not assert "written because the producer was absent" unless a comment says so.

## Checklist
- Tests validating fiction: mocks/stubs/fabricated literals that should now be sourced from a real producer. Signals: `vi.mock`/`jest.mock`, `mockReturnValue`/`mockResolvedValue`/`mockImplementation`, `sinon.stub`, manual doubles, large inline domain-typed literals in fixtures/`beforeEach`.
- Type-escape hatches hiding drift from the compiler (`as any`, `as unknown as X`, `@ts-expect-error`, untyped fixtures).
- Temporariness confessions: `TODO`/`FIXME`/`HACK`, "stub until X exists/ready/implemented".
- Cross-reference: does a real producer now exist (factory/builder, serializer/DTO, query/seed, the real module behind the mock)? Side-by-side drift evidence — missing now-required field, stale enum, wrong nullability — raises confidence.

## Severity
`maintainability` by default; rises to `reliability` if the drift could let a real defect through — a test validating fiction actively masks regressions.

## Exposure
Count of test doubles/fixtures examined.

## Out of scope
Coverage gaps (coverage).
