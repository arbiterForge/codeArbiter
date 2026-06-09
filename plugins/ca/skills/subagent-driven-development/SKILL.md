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

**Farm path (when `<slug>.plan.json` exists alongside the `.md` plan):** skip the subagent dispatch
loop below and follow the farm path instead. The farm path replaces Phases 2–6 for ALL tasks in the
plan simultaneously.

### Phase 2-farm — Farm dispatch and model selection

**Step 1 — Model selection.** If `FARM_MODEL` env var is set, use it directly and skip the research
steps. Otherwise:

1. Websearch `"OpenCode Zen free models <current month year>"` and the OpenCode model catalog page.
2. For any opaque codename (e.g. "Big Pickle"), follow up: `"<codename> model underlying LLM coding benchmark site:reddit.com OR site:news.ycombinator.com"` — community consensus on the underlying model and its coding ability is the only reliable signal; model IDs change without notice.
3. Select the best available free model for single-file code generation. Surface the selection to the user: "Selected `<model-id>` — community reports `<underlying model>`, `<coding assessment>`. Source: `<link>`. Proceed, or set `FARM_MODEL` to override."
4. Gate: model selected and identity understood. BLOCK if no free models are identifiable (community has no consensus) — the user must set `FARM_MODEL` manually.
5. Write `meta.model` and `meta.apiBaseUrl` into the `plan.json` file before dispatching (this records what actually ran in the plan artifact).

**Step 2 — Farm dispatch.** Invoke the farm dispatcher:

```
node "${CLAUDE_PLUGIN_ROOT}/tools/farm.js" "${CLAUDE_PROJECT_DIR}/.codearbiter/plans/<slug>.plan.json"
```

The dispatcher runs all tasks concurrently (up to `FARM_CONCURRENCY`, default 4), enforces gates, and writes:
- `${CLAUDE_PROJECT_DIR}/.farm/farm-report.json` — structured results (status per task)
- `${CLAUDE_PROJECT_DIR}/.farm/farm-report.md` — human-readable summary

Collect both reports. Exit code 0 = all green; exit code 2 = some tasks escalated.

**Step 3 — Escalation handler (Phase 2.5).** Read `farm-report.json`. For each result:

- **status `green`** — task accepted. Advance directly to Phase 6 (Accept and advance) for this task.
- **status `escalate`, note starts with `"drift:"`** — the cheap model touched files outside `filesInScope`. This indicates spec-gap or ambiguity. Raise a `[CONFIRM-NN]` in `open-questions.md` describing which files were written and why the worker strayed. HALT the loop — do not re-dispatch until the user resolves the ambiguity.
- **status `escalate`, note is a gate failure message** — the cheap model failed to make the test pass after retries. Re-dispatch via normal Phase 2 (author subagent + `tdd`), seeding the brief with: the farm worktree path (`result.worktree` from the report), the gate failure note, and the task's `test.path`. The left-in-place worktree shows what the cheap model attempted; the author subagent can inspect it.
- **status `escalate`, note is `"merge conflict vs integration branch"`** — re-order the task after its conflicting sibling and re-dispatch via Phase 2.
- **blocked** tasks (dependency escalated) — treat as gate failure of the upstream task first; once the upstream is resolved, re-queue the blocked task normally.

Gate: all tasks either green or re-dispatched via Phase 2 and accepted. No task may advance to commit-gate while any sibling is unresolved.

---

**Normal path (no `plan.json`):** dispatch ONE fresh subagent for the selected task — `backend-author`, `frontend-author`, or
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
- MUST NOT invoke `farm.js` before writing `meta.model` and `meta.apiBaseUrl` into `plan.json` — the dispatcher fails loudly if neither is set.
- MUST NOT skip model selection research (Step 1) when `FARM_MODEL` is not set — a blind invocation with an unknown model ID is a waste of compute and fails unpredictably.
- MUST raise a `[CONFIRM-NN]` and HALT on a drift escalation — do not silently re-dispatch a task where the cheap model strayed outside `filesInScope`; that signals a spec ambiguity, not an implementation gap.
