# Verification quality — shared by coverage and test-fidelity

Preserve both historical lens names and URLs. They execute the same evidence
discipline with complementary ownership:

- **coverage owns behavioral obligations and oracle strength**: missing risk-path
  cases, no-op assertions, forbidden behavior left unchecked, and expectations
  that merely repeat the implementation's own mistaken interpretation.
- **test-fidelity owns test-boundary fidelity**: stale or impossible doubles,
  fixtures, adapters, timing and error models that differ from the relied-on
  producer/consumer contract and thereby conceal a defect.

When both describe the same failure, the lens establishing the root mechanism
owns the finding; the sibling supplies a lead or corroboration. A weak assertion
alone belongs to coverage; a wrong mocked response that makes the assertion
misleading belongs to test-fidelity. Neither duplicates a proved product defect
owned by semantic-contract, reliability, appsec, or another domain lens.

## Establish an independent oracle

Find the expected behavior in a current requirement, accepted decision, public
contract, or supported pre-existing behavior. The expected value must have an
independent contract basis, not merely reproduce the code under test. Compare a
plausible wrong implementation: would the assertion fail, or does it check only
that execution completed, a mock was called, or the implementation's output was
copied into a snapshot? Interaction assertions can be strong when the interaction
itself is the contract; a smoke check can honestly serve a limited smoke purpose.

Check relevant negative and forbidden behavior, error translation, boundary
values, concurrency/order, cancellation, partial failure and compatibility.
Choose cases from actual risk and obligations, not a universal test checklist.
Tests and code from the same implementation trajectory may share the same wrong
interpretation; demonstrate that agreement against an independent expectation
instead of inferring quality from who wrote either artifact.

## Check the seam, not the existence of a mock

A faithful mock or double is valid when it models the contract the test depends
on. Compare shape, variants/nullability, side effects, timing/order, errors and
resource lifecycle with the actual producer and consumer. A smaller fixture can
deliberately omit irrelevant fields. A double may isolate an unavailable,
expensive or nondeterministic collaborator without weakening the tested claim.

Show a specific contract mismatch and the real regression it could hide before
filing. The existence of a real producer, use of generated tests, a TODO, a cast,
or a mock library is not evidence that a test validates fiction. Do not assert
the historical reason for a fixture from its present shape.

## Strengthen proof proportionately

Inspect existing test and coverage results as evidence; commands still require
the authorization in review-risk.md. Where authorized and cheap, a focused
mutation, differential, property or metamorphic check can demonstrate whether
the oracle distinguishes the wrong behavior. Name the fault and expected failed
assertion. Do not equate a coverage percentage, test count, passing sample, or
an unexecuted suggested mutation with that proof.

For a missing-test claim, record the searched test suites, integration/contract
checks and alternate harnesses, then trace which boundary owns the obligation.
For a double claim, include test, producer and consumer evidence. If the source
contract or boundary cannot be resolved, retain a bounded investigation lead.
