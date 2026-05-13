<!--
Copyright (c) 2026 suadtl
Author: suadtl
Created: 2026-05-10
File: fix.md
-->

# /fix "description of the bug"

## Purpose

Fix a confirmed bug. The only permitted path to begin bug-fix implementation work. Routes to the `tdd` skill with Phase 1 framed specifically around **confirming the bug with a failing regression test** before any fix code is written.

## Usage

```
/fix "clear description of the bug — what is happening vs. what should happen"
```

Include observed behavior and expected behavior. Include a stack trace or reproduction steps when available. Vague descriptions ("it's broken") will be rejected.

## Routes To

`tdd` skill (`${FRAMEWORK_ROOT}/.agents/skills/tdd/SKILL.md`) — all phases, Phase 1 framed for bug confirmation. Implementation agent (`backend-author`, `frontend-author`, or `infra-author`) selected by where the bug lives.

## Phase 1 framing for bug fixes (differs from /feature)

1. **Confirm the bug is real** — reproduce it consistently
2. **Identify the root cause** — which code path produces the wrong behavior
3. **Write a regression test** — fails in the current state for the exact wrong reason the bug causes (not just any failure)
4. **Confirm the regression test fails for the right reason** — failure message matches the described bug, not an unrelated error

Implementation begins only after steps 1–4 complete. If the bug cannot be confirmed with a failing test, STOP and surface the question.

## When NOT to Use

- **New features:** use `/feature`
- **Refactoring without a bug:** use `/feature` with a description of the refactor
- **Questions about why something behaves a certain way:** use `/btw`
- **Committing already-written fix code:** use `/commit` (Phase 1 gates still apply to the existing code)
