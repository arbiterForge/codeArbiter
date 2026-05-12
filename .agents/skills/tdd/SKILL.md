# Skill: tdd

## Trigger

> *"This section lists conditions under which the orchestrator routes work to this skill. The skill itself does not 'trigger' — it is routed to."*

Invoke this skill before writing any implementation code. This skill MUST complete
Phase 1 before any code is written. No feature code, no bug fix, no refactor begins
without this skill completing Phase 1 first.

Triggers:
- User requests a new feature, bug fix, or refactor
- Any file under a source or library path is about to be modified with non-test code
- The `tdd` skill is referenced in the routing table

---

## Pre-Flight

Before Phase 1 begins, confirm:

1. `${PROJECT_ROOT}/.agents/projectContext/tech-stack.md` is readable — stop if missing.
2. `${PROJECT_ROOT}/.agents/projectContext/audit-spec.md` is readable — stop if missing.
3. `${PROJECT_ROOT}/.agents/projectContext/observability-spec.md` is readable — stop if missing.
4. `${PROJECT_ROOT}/.agents/projectContext/trust-zones.md` is readable — stop if missing.
5. Current stage is known — read `cat ${PROJECT_ROOT}/.agents/projectContext/stage`.

If any file is missing, surface the gap and stop. Do not guess at commands or thresholds.

---

## Phase 1: Obligation Scan

> **Definition — obligation.** A single verifiable claim about the planned change
> that becomes a required test in Phase 2. Each obligation has (a) a unique ID,
> (b) a source citation (`audit-spec`, `trust-zones`, API contract, or
> `observability-spec`), and (c) a status (OPEN → MAPPED → COVERED). Hand-wavy
> "we should test X" items are not obligations.

**Goal:** Identify every auditable action, API boundary, and trust zone crossing
introduced or modified by the planned change before any code is written.

**Inputs:**
- Description of the planned change (feature, fix, or refactor)
- `${PROJECT_ROOT}/.agents/projectContext/audit-spec.md` — authoritative list of auditable action
  categories, required emit fields, and sink routing rules
- `${PROJECT_ROOT}/.agents/projectContext/observability-spec.md` — authoritative list of observability signal categories, required labels, cardinality budgets, and emit module paths
- `${PROJECT_ROOT}/.agents/projectContext/trust-zones.md` — zone topology and crossing rules

**Actions:**

1. Read `${PROJECT_ROOT}/.agents/projectContext/audit-spec.md` in full. Identify which action
   categories apply to the planned change.
2. Read `${PROJECT_ROOT}/.agents/projectContext/trust-zones.md`. Flag every zone boundary the
   change will cross.
2b. Read `${PROJECT_ROOT}/.agents/projectContext/observability-spec.md` in full. Identify which signal categories apply to the planned change.
3. List every obligation produced:
   - Auditable actions that must emit (with required fields from audit-spec)
   - Trust zone assertions that must be tested
   - API contract invariants that must be covered
   - Observability signals that must emit (with required labels from observability-spec)
4. For each obligation, write its ID, source citation, and OPEN status. In
   Phase 2 author one failing test per obligation.

**Output:** Signed obligation checklist — every item has an ID and a status of OPEN.

**Gate:** BLOCK. No Phase 2 begins until the obligation list is complete and
reviewed by the user. Partial obligation lists are not acceptable.

---

## Phase 2: Red Test Gate

**Goal:** Write failing tests that cover every obligation from Phase 1. No
implementation code is written in this phase.

**Inputs:**
- Phase 1 obligation checklist
- `${PROJECT_ROOT}/.agents/projectContext/tech-stack.md` — test runner invocation, file layout
  conventions, and mock/stub patterns for this project

**Actions:**

1. For each obligation in Phase 1, write one or more failing tests. Map test IDs
   back to obligation IDs.
2. Tests MUST cover:
   - All auditable actions identified (emit called, required fields present)
   - All trust zone crossings (correct zone origin, correct destination)
   - All API contract invariants (input validation, error responses)
3. Run the test command specified in `${PROJECT_ROOT}/.agents/projectContext/tech-stack.md`.
   All new tests MUST fail (red). If a new test passes without implementation,
   the test is incorrect — fix it before continuing.
4. Existing tests MUST remain green. If any pre-existing test breaks at this
   step, stop and surface the conflict before continuing.

**Output:** Committed (or staged) test files with all new tests failing as
expected. Obligation checklist updated: each OPEN item has a mapped test ID.

**Gate:** BLOCK. MUST NOT write any implementation code before this gate clears.
The test runner must confirm new tests fail and existing tests pass.

---

## Phase 3: Green Pass

**Goal:** Write the minimum implementation needed to make Phase 2 tests pass.
No gold-plating, no speculative code.

**Inputs:**
- Failing tests from Phase 2
- `${PROJECT_ROOT}/.agents/projectContext/tech-stack.md` — build and test commands
- `${PROJECT_ROOT}/.agents/projectContext/coding-standards.md` — style, structure, and naming rules

**Actions:**

1. Read `${PROJECT_ROOT}/.agents/projectContext/coding-standards.md` before writing any code.
2. Write implementation code sufficient to satisfy the Phase 2 tests. No additional
   logic beyond what the tests require.
3. Run the full test suite using the test command from
   `${PROJECT_ROOT}/.agents/projectContext/tech-stack.md`. ALL tests (new and pre-existing) MUST be green.
4. If a pre-existing test breaks, treat it as a regression — fix before continuing,
   do not suppress or skip the failing test.

**Output:** Implementation code with all tests green.

**Gate:** BLOCK. Full test suite must be green before Phase 4 begins. No skipped
tests. No suppressed failures.

---

## Phase 4: Obligation Verification

**Goal:** Confirm every obligation from Phase 1 is covered by a test and that
no obligation was silently dropped.

**Inputs:**
- Phase 1 obligation checklist
- Test files from Phase 2
- Phase 3 green test run

**Actions:**

1. Walk the Phase 1 obligation list item by item. For each item, confirm a
   corresponding test exists and is green.
2. For features with complex audit emit logic, invoke the `coverage-auditor`
   agent to verify emit correctness before marking audit obligations complete.
3. Update checklist: each obligation moves from OPEN to COVERED (with test ID)
   or to MISSING (if no test covers it).
4. Any MISSING item is a blocking finding. Do not proceed to Phase 5 until
   all MISSING items are resolved.

**Output:** Obligation checklist with all items in COVERED status.

**Gate:** BLOCK. Any uncovered obligation (MISSING status) blocks Phase 5.
MUST NOT mark an obligation COVERED without an actual passing test.

---

## Phase 5: Coverage Gate

**Goal:** Confirm test coverage meets the threshold for the current project stage.

**Inputs:**
- `${PROJECT_ROOT}/.agents/projectContext/stage` — current stage value
- `${PROJECT_ROOT}/.agents/projectContext/tech-stack.md` — coverage command and report format

**Actions:**

1. Read the current stage: `cat ${PROJECT_ROOT}/.agents/projectContext/stage`.
2. Determine the required coverage threshold:

   | Stage | Minimum Coverage |
   |-------|-----------------|
   | 1     | ≥ 60%           |
   | 2     | ≥ 70%           |
   | 3     | ≥ 85%           |
   | 4     | ≥ 90%           |

3. Run the coverage command specified in `${PROJECT_ROOT}/.agents/projectContext/tech-stack.md`.
4. Check the reported coverage against the threshold for the current stage.
5. If coverage is below threshold, identify uncovered lines and add tests until
   the threshold is met. Do not adjust the threshold.

**Output:** Coverage report confirming threshold met for current stage.

**Gate:** BLOCK. Coverage below the stage threshold blocks Phase 6.
MUST NOT proceed with insufficient coverage. Threshold values are not
negotiable without a stage-recorded decision.

---

## Phase 6: Lint Gate

**Goal:** Confirm the codebase passes all lint and type-check rules with no errors.

**Inputs:**
- `${PROJECT_ROOT}/.agents/projectContext/tech-stack.md` — lint and type-check commands

**Actions:**

1. Run the lint command specified in `${PROJECT_ROOT}/.agents/projectContext/tech-stack.md`.
2. Run the type-check command specified in `${PROJECT_ROOT}/.agents/projectContext/tech-stack.md`
   (if the project uses static typing).
3. All errors MUST be resolved. Warnings that escalate to errors under the
   project's lint configuration MUST also be resolved.
4. MUST NOT suppress lint rules inline to pass this gate. If a suppression is
   genuinely needed, it requires a comment explaining why and must not be used
   to bypass a security-relevant rule.

**Output:** Clean lint and type-check output with zero errors.

**Gate:** BLOCK. Any lint or type error blocks the commit-gate skill from running.
"It mostly passes" is not a passing state.

---

## Decision Gates Summary

| Gate         | Condition                                         | Action if blocked         |
|--------------|---------------------------------------------------|---------------------------|
| Phase 1 exit | Obligation list incomplete or unreviewed          | Stop; surface to user     |
| Phase 2 exit | New tests not failing, or existing tests broken   | Stop; fix before continuing |
| Phase 3 exit | Any test not green                                | Stop; fix regression      |
| Phase 4 exit | Any obligation in MISSING status                  | Stop; write missing test  |
| Phase 5 exit | Coverage below stage threshold                    | Stop; add tests           |
| Phase 6 exit | Any lint or type error                            | Stop; fix errors          |

---

## Hard Rules

- MUST NOT write implementation code before Phase 1 obligation scan is complete.
- MUST NOT write implementation code before Phase 2 tests are written and failing.
- MUST NOT skip, suppress, or comment out a failing test to clear a gate.
- MUST NOT lower the coverage threshold without a recorded stage decision.
- MUST NOT inline-suppress a lint rule to pass Phase 6 without a documented reason.
- MUST NOT guess test runner or lint commands — always read `${PROJECT_ROOT}/.agents/projectContext/tech-stack.md`.
- MUST NOT proceed to the commit-gate skill until all six phases are green.

---

## Failure Modes

| Failure                                         | Response                                                      |
|-------------------------------------------------|---------------------------------------------------------------|
| `tech-stack.md` missing or unreadable           | Stop; surface gap to user; do not guess commands             |
| `audit-spec.md` missing                         | Stop; Phase 1 cannot complete without audit obligations       |
| Obligation identified with no matching test     | Add the test; do not mark obligation COVERED without evidence |
| Pre-existing test breaks in Phase 3             | Treat as regression; fix before continuing                    |
| Coverage drops below threshold after Phase 3    | Add tests in Phase 4/5 cycle; never suppress coverage         |
| Lint rule suppressed to clear Phase 6           | Flag as policy violation; require documented justification    |
