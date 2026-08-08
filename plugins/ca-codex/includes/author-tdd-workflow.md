# Author TDD workflow — non-negotiable, fixed order

Canonical for the author agents (`backend-author`, `frontend-author`). Loaded via each agent's
Required Reading; the agent bodies do not restate it. This is the worker's execution order for
one task — the tdd skill's phase gates govern the lane above it.

Fixed order. Do not skip or reorder.

1. **Write failing tests** — one test per obligation in the Phase 1 checklist
2. **Confirm tests fail for the right reason** — run the test command from `tech-stack.md`; the failure must match the obligation, not an unrelated error
3. **Write minimum implementation** — only enough code to make the failing tests pass; no extra scope
4. **Run full suite** — every test green
5. **Run lint and type-check** — both clean
6. **Stage for commit** — only after steps 1–5 complete
