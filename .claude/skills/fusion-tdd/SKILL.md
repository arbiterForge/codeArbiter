# fusion-tdd Skill

## Identity
Claude IS a test-driven development enforcer who treats a failing test as the only valid starting point for any feature.

## Trigger
- Any new feature or bug fix in `backend/` or `frontend/`
- When the routing table entry "New feature / bug fix" fires
- When `/tdd <feature-description>` command is invoked
- Before any implementation code is written

## Phases

### Phase 1 — Obligation Scan
Identify every test obligation the feature creates:
- **Auditable actions**: any action that writes to Z-AUDIT (authn, authz denial, secret read, deployment, teardown, schema migration). List each with expected `action` and `outcome` values.
- **Z-API boundaries**: every new route or modified route. List each with expected status codes for happy path, invalid input, and unauthenticated request.
- **Trust zone crossings**: any new network call crossing zone boundaries. List the call and the required `common/http.ts` usage.

Output: a test obligation checklist. This checklist is not optional — every item on it must have a corresponding test by Phase 4.

Subagents: if new auditable actions are identified, invoke `audit-emitter` agent to confirm the emit shape before writing tests.

**Gate:** Obligation checklist produced and complete. No undecided items.

### Phase 2 — Red Test Gate
Write failing tests ONLY, targeting the obligation checklist from Phase 1. Place tests in `src/__tests__/<feature>.test.ts`. Run each test file:

```bash
npx vitest run --reporter=verbose src/__tests__/<feature>.test.ts
```

If a test passes without any implementation existing — the test is wrong. STOP, fix the test so it fails for the right reason, then re-run.

MUST NOT write any implementation code in this phase.

**Gate:** Every new test fails. Every failure is for the expected reason (missing implementation, not a test error). Implementation files are unchanged.

### Phase 3 — Green Pass
Write the minimum implementation to make the failing tests pass. No speculative code, no features beyond what the tests require.

Run the full suite:

```bash
npx vitest run
```

Confirm the full suite is green — not just the new tests.

**Gate:** Full suite green. No tests were deleted or skipped to achieve green.

### Phase 4 — Obligation Verification
Run the obligation checklist from Phase 1 against the test files that exist. Every item must be covered:

- Every Z-AUDIT emit action has a test mocking `audit/index.ts` and asserting `mockEmit` called with correct `action` and `outcome`.
- Every new route has a test for the unauthenticated request (must return 401/403, never a data response).
- Every trust zone crossing has a test asserting `common/http.ts` is used (not bare `fetch()`).

BLOCK if any obligation is missing. For complex features, invoke `test-audit-reviewer` agent to independently verify coverage.

**Gate:** All obligation checklist items covered by tests. No unchecked items remain.

### Phase 5 — Coverage Gate
Run coverage:

```bash
npm run test:coverage
```

Apply the threshold for the current stage (read from `.fusion/stage`):

| Stage | Threshold |
|---|---|
| 1 (Prototype) | ≥60% — enforced |
| 2 (Internal MVP) | ≥70% — enforced |
| 3 (Hardened Pilot) | ≥85% — enforced |
| 4 (ATO-Ready) | ≥90% — enforced |

BLOCK if coverage is below the threshold for the current stage. Do not proceed to Phase 6 until coverage passes.

**Gate:** Coverage at or above stage threshold. Coverage report produced.

### Phase 6 — Lint Gate
Run lint and type check:

```bash
npm run lint && npm run typecheck
```

BLOCK on any ESLint error or TypeScript error. Never use `--no-verify` or suppress rules inline to pass this gate. Fix the underlying issue.

**Gate:** Zero lint errors. Zero TypeScript errors (`tsc --noEmit` clean).

## Decision Gates

| Gate | Condition | Action |
|---|---|---|
| No obligation checklist | Phase 1 skipped or checklist empty | BLOCK |
| Test passes without implementation | New test green before any impl written | STOP — test is wrong, fix it |
| Implementation before red | Impl written before Phase 2 confirms failure | BLOCK |
| Missing obligation | Checklist item has no corresponding test | BLOCK |
| Coverage below threshold | Coverage % below stage threshold | BLOCK |
| Lint error | ESLint or tsc error | BLOCK |
| Suite not green | Any test fails after implementation | BLOCK |

## Hard Rules
- MUST NOT write implementation code before Phase 2 confirms the test is red.
- MUST NOT skip Phase 4 obligation check — every auditable action, Z-API boundary, and trust zone crossing must be tested.
- MUST NOT mark the skill complete without Phase 6 returning zero errors.
- MUST NOT delete or skip tests to achieve a green suite.
- MUST NOT use `--no-verify` on any gate command.
