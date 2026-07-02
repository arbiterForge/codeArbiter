# coverage — lens mandate

Executed by `tribunal-coverage-reviewer`. Evidence-or-drop on every check.

## Checklist
- Coverage gaps on risk paths (auth, money, data-mutation, error handling).
- Missing edge-case/property coverage; the empty/null/single-item and zero-value cases.
- Tests asserting implementation detail rather than observable behavior.

## Exposure
Count of risk paths examined (`inventory.md` risk overlay).

## Out of scope
Tests validating fiction (test-fidelity); the underlying bug itself (reliability).
