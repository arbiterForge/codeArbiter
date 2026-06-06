---
name: subagent-driven-development
description: The autonomous execution engine. Routed to by /sprint to drive a plan to completion, and optionally by /feature for parallel work. One fresh subagent per plan task — test-first via tdd — followed by a two-pass review (spec-compliance, then quality) and fresh-run verification. No single context accumulates drift, and nothing is accepted on a subagent's word.
---

# subagent-driven-development

One task, one fresh subagent, two reviews, proof on a fresh run. Routed to by `/sprint`; optionally
by `/feature` for parallel work. The loop processes the plan task-by-task and never trusts a self-report.

## Pre-flight

Read these, or STOP and surface the gap — never guess scope, command, or obligation:

- `${CLAUDE_PROJECT_DIR}/.codearbiter/CONTEXT.md` — the `stage:` frontmatter (the maturity value) and project context.
- `${CLAUDE_PROJECT_DIR}/.codearbiter/plans/<slug>.md` — the approved plan. Each task carries an exact path set and a verification command. This is the task source.
- `${CLAUDE_PROJECT_DIR}/.codearbiter/specs/<slug>.md` — the approved spec. Each task's obligation traces to it. The spec-compliance review measures against it.
- `${CLAUDE_PROJECT_DIR}/.codearbiter/tech-stack.md` — build, test, and verification invocations; file layout; the scope-to-author mapping.
- `${CLAUDE_PROJECT_DIR}/.codearbiter/security-controls.md` — only when a task touches a security boundary (auth, crypto, secrets, a trust boundary).

## Phase 1 — Task selection · gate: BLOCK

Pull the next unblocked task from the plan in dependency order. A task is one verifiable unit of work
with a path set, a spec obligation, and a verification command.

- Confirm every dependency task is `ACCEPTED` before selecting.
- Confirm no unresolved `[CONFIRM-NN]` blocks the task. One that does halts the loop — see Hard rules.

Gate: exactly one task selected, dependency-clean, with its spec obligation and verification command in hand.

## Phase 2 — Implementation dispatch · gate: BLOCK

Dispatch ONE fresh subagent for the selected task — `backend-author`, `frontend-author`, or
`infra-author` by the scope mapping in `tech-stack.md`
(`${CLAUDE_PLUGIN_ROOT}/agents/<name>.md`). A fresh context per task is the whole point: no carried-over
assumptions, no accumulated drift.

The subagent works test-first by routing through the `tdd` skill — no implementation code before
`tdd` Phase 1. Brief it with the task's path set, its spec obligation, and its verification command.
Nothing else from prior tasks leaks in.

Gate: the subagent reports `tdd` complete — all six phases green. A `tdd` BLOCK halts the loop; do not
re-dispatch around it.

## Phase 3 — Spec-compliance review · gate: BLOCK

Did the change satisfy the task's obligation? Measure the result against the spec line the task
traces to — not against whether tests merely pass.

- Every acceptance claim in the task's obligation is met by the change.
- Scope is clean: nothing implemented beyond the task; nothing required by it omitted.
- Out-of-scope work the subagent noticed is recorded with an inline `[NEEDS-TRIAGE]` marker — never
  acted on inside this task.

Gate: the obligation is fully satisfied and scope is clean. A shortfall returns the task to Phase 2
with a corrective brief.

## Phase 4 — Quality review · gate: BLOCK

Dispatch `grader` (`${CLAUDE_PLUGIN_ROOT}/agents/grader.md`) for the quality pass, then
`finding-triage` (`${CLAUDE_PLUGIN_ROOT}/agents/finding-triage.md`) to classify every finding by
severity. For a security-relevant task, also dispatch `security-reviewer`
(`${CLAUDE_PLUGIN_ROOT}/agents/security-reviewer.md`).

- A security CRITICAL finding halts the loop — see Hard rules.
- A HIGH finding returns the task to Phase 2.
- MEDIUM and LOW findings are recorded; the user decides whether they block.

Gate: no CRITICAL, no HIGH. The quality bar for the task's severity profile is met.

## Phase 5 — Verification · gate: BLOCK

Verification-before-completion: run the task's verification command from the plan **fresh**, in a
clean invocation. Read the actual output and the exit code. A subagent's "done" is not evidence —
proof is.

- Run the command yourself; do not accept a logged result from Phase 2.
- A non-zero exit, or output that does not demonstrate the obligation, returns the task to Phase 2.

Gate: the verification command exits clean and its output demonstrates the obligation. Only then.

## Phase 6 — Accept and advance · gate: BLOCK

Mark the task `ACCEPTED` only when both reviews passed AND verification passed on a fresh run.
Record acceptance and any `[NEEDS-TRIAGE]` markers to the plan and the `.codearbiter/` audit trail.

- Tasks remain → return to Phase 1.
- Plan complete → hand the branch to `commit-gate`, then to the caller's finishing step. The loop does
  not commit on its own authority.

Gate: every plan task `ACCEPTED`, the suite green, ready for `commit-gate`.

## Hard rules

- MUST dispatch a fresh subagent per task — never reuse one context across tasks.
- MUST NOT write implementation code before the task's `tdd` Phase 1 completes.
- MUST accept a task only when both reviews pass AND verification passes on a fresh run.
- MUST NOT accept a task on a subagent's self-report — run the verification command and read its exit code.
- MUST halt and surface to the user on a `tdd` BLOCK, a security CRITICAL finding, or an unresolved `[CONFIRM-NN]` inside the loop — and on a `commit-gate` failure at the finish handoff — even under `/sprint`. These never auto-proceed.
- MUST NOT commit — hand the accepted branch to `commit-gate`.
- MUST mark out-of-scope findings with an inline `[NEEDS-TRIAGE]` marker and never act on them inside the task.
