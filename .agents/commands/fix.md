# /fix "description of the bug"

## Purpose

Fix a confirmed bug. The only permitted path to begin bug-fix implementation work. Phase 1 of the `tdd` skill is framed specifically around **confirming the bug with a failing regression test** before any fix code is written. If the bug cannot be confirmed with a failing test, stop and surface the question to the user.

## Usage

```
/fix "clear description of the bug — what is happening vs. what should happen"
```

Include observed behavior and expected behavior. If a stack trace or reproduction steps are available, include them. Vague descriptions like "it's broken" will be rejected — codeArbiter will ask for a reproduction case.

## Routes To

`tdd` skill (`.agents/skills/tdd/SKILL.md`) — all 6 phases, with Phase 1 framed for bug confirmation.

## Implementation Agent

After Phase 1 completes, codeArbiter routes to:

- `backend-author` — for backend/server-side bugs
- `frontend-author` — for UI/frontend bugs
- `infra-author` — for infrastructure/deployment bugs

Agent selection is based on where the bug lives. If the bug spans layers (e.g., a frontend display issue caused by a backend response shape problem), agents are coordinated sequentially — fix the root cause layer first, then the surface layer.

## Phase 1 for Bug Fixes (Different from /feature)

Phase 1 is specifically framed as:

1. **Confirm the bug is real** — can it be reproduced consistently?
2. **Identify the root cause** — which code path produces the wrong behavior?
3. **Write a regression test** — a test that fails in the current state for the exact wrong reason the bug causes (not just any failure)
4. **Confirm the regression test fails for the right reason** — the failure message must match the described bug, not an unrelated error

Only after steps 1-4 are complete does implementation begin.

## What Happens Step by Step

1. Phase 1 — bug confirmed, root cause identified, regression test written and verified failing for the right reason
2. Implementation agent selected based on where the bug lives
3. Agent reads `projectContext/tech-stack.md` and `projectContext/coding-standards.md`
4. Agent writes minimum fix to make the regression test pass — no extra scope
5. Full test suite runs — regression test now green, no previously passing tests broken
6. Lint and type-check run — must pass
7. Phase 6 (commit readiness) — hands off to `/commit`

## Hard Gates

- MUST NOT write fix code before the regression test is written and confirmed failing for the right reason
- Regression test MUST fail because of the described bug — not for an unrelated reason
- Fix MUST NOT change behavior outside the bug's scope (no scope creep in a fix)
- Full test suite MUST be green — no regressions allowed
- If the fix touches auth, crypto, secrets, middleware, or audit code: `security-reviewer` and `auth-crypto-reviewer` are invoked before the commit gate

## When NOT to Use

- **New features:** use `/feature`
- **Refactoring without a bug:** use `/feature` with a description of the refactor
- **Questions about why something behaves a certain way:** use `/btw`
- **Committing already-written fix code:** use `/commit` (but Phase 1 gates still apply to the existing code)
