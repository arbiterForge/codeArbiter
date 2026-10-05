# coverage — lens mandate

Executed by `tribunal-lens-reviewer` under the `coverage` assignment.

## Purpose / failure family
Find missing behavioral verification or weak oracles that let a plausible wrong
implementation pass. Coverage owns obligations and oracle strength.

## Applicability
Assigned behavior has a concrete correctness, security, compatibility or recovery
obligation whose verification can be examined.

## Skip conditions
No applicable executable behavior or verifiable obligation. Lack of a particular
test framework or numerical coverage report is not itself a finding.

## Scope emphasis
Risk-path source/test pairs: authorization, persistent mutation, error ownership,
boundary behavior, concurrency, cancellation and compatibility where relevant.

## Required reading
- Finding record (`{{PLUGIN_ROOT}}/skills/tribunal/references/finding-record.md`) and review risk (`{{PLUGIN_ROOT}}/skills/tribunal/references/review-risk.md`).
- Verification quality (`{{PLUGIN_ROOT}}/skills/tribunal/references/verification-quality.md`) — shared oracle discipline and complementary ownership.
- `{{PROJECT_DIR}}/.codearbiter/tech-stack.md` — test suites, alternate harnesses
  and declared coverage model; current requirements and inventory risk paths.

## Deterministic probes
Inspect source/test relationships, assertion targets, existing coverage reports
and test-selection rules. Locate integration/contract checks before claiming a
unit has no protection; execution counts alone do not reveal oracle strength.

## Review questions
- Which independent expectation would a realistic wrong implementation violate?
- Does an assertion detect it, or only execution, a call count or copied output?
- Are relevant forbidden behavior, error, boundary and compatibility cases checked?
- Could a focused mutation, property, differential or metamorphic check cheaply
  discriminate the suspected fault under authorized verification?

## False-positive guards / non-findings
A limited smoke test is valid for a smoke obligation. Interaction assertions can
test a real protocol. Low percentages, small test counts and generated tests do
not establish a gap; good behavioral coverage can live in another harness.

## Evidence requirements
Name the obligation, plausible fault and missing or ineffective assertion. State
the searched suites and alternate harnesses and trace ownership of the behavior.
Distinguish a reasoned surviving-fault example from an actually executed mutation;
never claim the latter without captured results.

## Exposure metric
Count of distinct risk-path obligations whose case selection and oracle were
examined, with unexamined obligations reported separately.

## Escalation / cross-lens handoff
Test-fidelity owns mismatched doubles/fixtures; send it a lead when that is the
root mechanism. Send proved product defects to their domain lens and corroborate
the root cause rather than count both the defect and its missing test as duplicates.

## Out of scope
Mock presence, fixture-contract fidelity, implementing tests, and claiming that a
coverage percentage proves correctness.
