# coverage — lens mandate

Executed by `tribunal-lens-reviewer` under the `coverage` assignment. Write contract + evidence discipline: `finding-record.md`.

## Scope emphasis
Source-and-test pairs on risk paths in the assigned slice (auth, money, data-mutation, error handling).

## Required reading
- `<project-root>/.codearbiter/tech-stack.md` — test and coverage invocations; `inventory.md` in the run dir — the risk overlay.

## Checklist
- Coverage gaps on risk paths (auth, money, data-mutation, error handling).
- Missing edge-case/property coverage; the empty/null/single-item and zero-value cases.
- Tests asserting implementation detail rather than observable behavior.

## Exposure
Count of risk paths examined (`inventory.md` risk overlay).

## Out of scope
Tests validating fiction (test-fidelity); the underlying bug itself (reliability).
