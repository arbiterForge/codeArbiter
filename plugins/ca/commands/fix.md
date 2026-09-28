---
description: "Fix a confirmed bug: a failing regression test first, then a minimal fix, then the rest of the tdd gates."
argument-hint: "<what's happening vs. what should happen>"
---

# /ca:fix — regression-first bug fix

The only permitted entry to bug-fix work. No fix code is written before a regression test reproduces the defect and goes red for the right reason. Give the observed behavior and the expected behavior, plus a stack trace or reproduction when you have one.

**Orientation:** if `.codearbiter/code-map.md` is present, read it before diagnosing — a coarse concern→path→role map that helps locate the defect. Absent is fine; it is read-on-demand.

For a confirmed bug, the owning coordinator gathers the current scoped map,
provenance, command declarations and collector observations, applicable
constraints, and host-effective instructions. Before the fix author mutates or
executes a discovered command, call `_contextselectlib.compose_fix_or_test_actor_input`
with `route='fix'`, `caller='fix'`, the actual task paths, and the observed,
expected, reproduction, cited evidence, and named regression test from the
bug-origin handoff. Send its returned `input` to the actual author. A directly
confirmed bug may supply the same evidence without re-entering `debug`. Keep
command cwd and verification state; a historical pass does not prove a current
run. The packet is orientation with `requires_actor_check`, never permission to
change code. Resolve applicable critical context before material action.
Call `_contextselectlib.prepare_actor_delivery` for that returned packet and
the actual author/task/worktree/current epochs. Send its bounded
`delivery_text` to the author on `deliver`, retain the attempt, and stop the
material action on `blocked`. Re-select after resume, compaction or scope
change; a shared session marker is not an author receipt.

## Flow

Routes to the `tdd` skill, bug variant — Phase 1 is framed around confirming the defect, not building
new behavior:

1. **Reproduce** the bug consistently.
2. **Locate the root cause** — the exact code path producing the wrong behavior.
3. **Write or reuse the named regression test** from the confirmed bug handoff. It must fail in the
   current state for the precise reason the bug causes (not an unrelated error).
4. **Confirm it's red for the right reason** — the failure message matches the described defect.

Only then does `tdd` proceed: minimal fix to green, then the remaining `tdd` gates. The implementation
agent (`backend-author`, `frontend-author`, or `infra-author`) is selected by where the bug lives. If
the defect cannot be pinned by a failing test, STOP and surface the question.

## Routes to

`tdd` (`${CLAUDE_PLUGIN_ROOT}/skills/tdd/SKILL.md`) — all phases, Phase 1 framed for bug confirmation.

## When NOT to use

- New behavior → `/ca:feature`.
- A behavior-preserving restructure → `/ca:refactor`.
- "Why does it do this?" → `/ca:btw`.
- Persisting fix code already written → `/ca:commit` (the gates still apply).

## Hard gate

MUST NOT write fix code before the regression test is red for the right reason. MUST NOT accept a test
that passes against the broken state as proof of the defect.
