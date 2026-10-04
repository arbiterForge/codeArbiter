# Author TDD workflow — non-negotiable, fixed order

Canonical for the author agents (`backend-author`, `frontend-author`, `infra-author`). Loaded via each agent's
Required Reading; the agent bodies do not restate it. This is the worker's execution order for
one task — the tdd skill's phase gates govern the lane above it.
Apply `{{PLUGIN_ROOT}}/includes/verification-boundary.md` throughout.

Use the Phase 1 checklist for the owning route. For a bug-origin `/fix`, carry the
current expectation, cited evidence, supported cause, and regression oracle into
the existing obligation ledger; confirm the original caller's repair authority and
source freshness through the fix owner. Do not fabricate a feature artifact. For
`/feature`, keep the approved spec and its criteria; for `/refactor`, keep its
approved surface and parity contract. An ADR remains a user-attributed decision
through `/adr`, never an author shortcut.

Fixed order. Do not skip or reorder.

1. **Map failing tests** — bind each Phase 1 obligation to a test ID. For `/fix`, assess an existing failing test against target red using the current regression oracle and evidence. Name the existing test ID in the ledger and reuse that named existing target-red test when its oracle is adequate and the assertion matches the defect. Do not duplicate a test because of its age or because it predates repair. Add tests only for uncovered obligations.
2. **Confirm tests are red for the right reason** — run the test command from `tech-stack.md`; the target failure must match the obligation. Record unrelated existing failures in the baseline; an unrelated failure is not target red. An import or setup error is not target red. Preserve and report their identities and outputs. Required commit gates remain blocked while required checks fail. Do not skip tests, suppress failures, or waive gates to proceed.
3. **Write minimum implementation** — only enough code to make the failing tests pass; no extra scope
4. **Run impact-bounded local suite** — rerun the same named target test for fresh green on the repaired source, with its assertions unchanged between red and green. Rerun fresh affected-contract tests on that source and record their results; exhaustive and cross-platform proof runs in exact-head hosted CI before merge
5. **Run lint and type-check** — both clean
6. **Stage for commit** — only after steps 1–5 complete

For a repair, observe target red on the broken source before minimum implementation. If a material fixture or setup change occurs after that observation, the earlier red no longer qualifies: repeat target red on the broken implementation with the changed fixture or setup before continuing the repair. Keep the test's assertions unchanged between red and green.

For an intermittent or timing defect, use a faithful deterministic seam when one exists. Otherwise define a finite repeated-trial oracle with its trial bound and pass/fail rule before running it. Record the stochastic sample limit; do not claim deterministic proof from a passing sample or retry until green. A failing trial must still match the target mechanism, and fresh green remains bounded by the stated oracle.
