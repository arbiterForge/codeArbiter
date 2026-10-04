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

1. **Establish the defect** from an observed reproduction or a supported source/contract causal trace, with its evidence and limits. A runtime replay is not mandatory when the causal trace proves the defect.
2. **Locate the root cause** — the exact code path producing the wrong behavior.
3. **Write or reuse the named regression test** from the confirmed bug handoff. It must fail in the
   current state for the precise reason the bug causes (not an unrelated error).
4. **Confirm it's red for the right reason** — the failure message matches the described defect.

Only then does `tdd` proceed: minimal fix to green, then the remaining `tdd` gates. The implementation
agent (`backend-author`, `frontend-author`, or `infra-author`) is selected by where the bug lives. If
the defect cannot be pinned by a failing test, STOP and surface the question.

## Debug handoff and direct-fix prerequisite

For an authorized direct fix that needs a small investigation to establish its cause, take one internal diagnostic prerequisite through the debug owner, then return to the same original fix caller and its existing scope and TDD gates. Keep the count at one for this fix attempt. No public command recursion or compulsory public route retyping is needed, and no feature artifact is fabricated. If diagnosis is unresolved, non-code, or exposes an authority blocker, report the result and stop the dependent repair; do not force a code patch or an ADR.

When a debug handoff packet is actually available, resolve the absolute installed `debug-handoff.py` helper from the trusted package and invoke Python 3 with `-B`, that absolute path, and literal `validate`. Pass the bounded packet bytes on stdin. Accept the packet only on exit 0, `valid: true`, and no errors. An invalid or rejected packet (exit 2), unavailable helper (exit 3), or other failure must stop the handoff; report its bounded error code and field path. There is no unvalidated repair fallback, silent packet rewrite, or retry through another interpreter. Structural validation alone does not prove evidence truth, freshness, or authorization.

Recheck the actual caller authority and scope independently of the packet. A `request.intent` value such as `repair_requested` cannot authorize repair; a diagnosis-only caller must stop after the recommendation, even if `next_step.target` says `fix`. Keep any separate access or approval blocker. Continue a repair only under the original caller's repair authority and the existing fix gates; a task promotion or ADR still needs its own owner and authority.

Only a validated `confirmed_code_defect` packet with `next_step.target` `fix` and a supported regression obligation may resume the original caller's authorized repair path, subject to the current-evidence checks and target-red gate below. Every other valid disposition returns its evidence and recommendation without repair. For `design_question`, report the actual intended-behavior decision and stop; do not create an ADR automatically. For `no_action`, return its positive closure evidence and stop without a board write or other state mutation. A valid non-code or unresolved result likewise stops the dependent fix and retains its owner, blocker, or resume condition.

A separately authorized concrete follow-up goes to the existing `/task` owner with its action, provenance, and completion evidence. The debug result or handoff packet alone does not authorize that board write; the task owner uses its existing writer gates.

Recheck current evidence in the actual worktree before using a validated packet: compare repository and worktree identity, relevant source and runtime binding, commit, index and working-tree dirty state, and any available fingerprint and recipe against the packet's snapshots and cited observations. The same commit in another worktree does not establish freshness when its index, dirty source, runtime, or evidence differs. If relevant source or evidence has changed, revalidate the affected claim from accessible citations or block; do not silently treat a stale packet as current. Admit unavailable retained context and reconstruct only from accessible cited evidence. Keep unknown facts unknown.

Consume the validated symptom, observed behavior, expected behavior and expectation citations, reproduction status and limits, evidence and source binding, supported cause, and regression obligation with its oracle and cited evidence. Do not re-ask known answered questions about symptom, expectation, or reproduction; ask only for a genuinely missing or changed fact. Use these fields to derive the bug-origin TDD obligations in the existing ledger, without creating an independent replacement ledger. A supported causal trace can establish the diagnosis without runtime replay, but `/fix` must observe its precise target test red at the production layer before any fix code. An import error, setup failure, unrelated red, or passing test does not clear that gate.

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
