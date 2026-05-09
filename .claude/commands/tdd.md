---
description: Primary entry point for any development work. Invokes fusion-tdd skill Phase 1–6 to enforce test-first implementation.
argument-hint: "<feature-description> [path/to/existing/test.test.ts]"
---

Primary entry point for any feature or bug fix. This command invokes the
`fusion-tdd` skill and MUST be run before any implementation code is written.

Arguments:
- `${1:?feature description required}` — plain-English description of the feature or fix
- `${2:-}` — optional path to an existing test file to extend (leave blank to create new)

## Pre-flight

1. Read `CLAUDE.md` §3 (hard rules) and §5 (routing table) in full.
2. Read `.fusion/stage` — note the current stage for coverage thresholds.
3. Read `docs/coding-standards.md` — required before any code change.
4. If the feature touches audit, crypto, or secrets: read the corresponding
   gated doc from CLAUDE.md §4 Reference Map before proceeding.

## Invoke fusion-tdd Skill

Invoke the `fusion-tdd` skill with the following context:

```
Feature: ${1}
Existing test file (if any): ${2:-none}
Current stage: [read from .fusion/stage]
```

The skill will execute Phases 1–6 in sequence:

1. **Phase 1 — Obligation Scan**: Identify all auditable actions, Z-API boundaries, and trust zone crossings. Produce test obligation checklist.
2. **Phase 2 — Red Test Gate**: Write failing tests only. Confirm each fails for the right reason.
3. **Phase 3 — Green Pass**: Write minimum implementation. Confirm full suite green.
4. **Phase 4 — Obligation Verification**: Verify every obligation checklist item has a test.
5. **Phase 5 — Coverage Gate**: Confirm coverage meets stage threshold.
6. **Phase 6 — Lint Gate**: Confirm zero lint and TypeScript errors.

## Hard Stops

MUST NOT proceed to Phase 3 until Phase 2 confirms a red test.
MUST NOT mark this command complete without Phase 6 returning zero errors.

If the feature involves an auditable action identified in Phase 1: invoke
`audit-emitter` agent before writing the Phase 2 tests to confirm the emit shape.

If the feature touches `backend/src/middleware/`, `lib/audit/`, any crypto, or
key management: after Phase 6, invoke `security-reviewer` agent and block on
its verdict before reporting complete.

## Completion Report

After all 6 phases pass, report:
- SHA of the last commit (if committed via fusion-commit-gate)
- Test file path(s) written
- Coverage percentage achieved vs. stage threshold
- Any obligation checklist items that required `audit-emitter` or `security-reviewer`

Do NOT commit. Committing is fusion-commit-gate skill's job — invoke it
separately when the user explicitly requests a commit.
