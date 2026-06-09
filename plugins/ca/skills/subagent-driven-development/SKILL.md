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
loop below and follow the farm path instead. The farm path replaces only the *authoring* step (Phase 2)
for the plan's tasks — it does NOT replace review. Every task the farm reports green is still routed
through Phases 3, 4, and 5 before acceptance. The cost arbitrage is in who *writes* the code, never in
whether it is *reviewed*: a cheap model is more likely to game a narrow test, so its output gets the
SAME scrutiny a premium subagent's would, not less.

### Phase 2-farm — Farm dispatch and model selection

**Step 1 — Model selection.** If `FARM_MODEL` env var is set, use it directly and skip selection.
Otherwise, prefer a **measured** choice over web hearsay:

1. Read `.farm/model-cache.json` if present. If it records a model chosen within the last 7 days whose
   last canary pass-rate was acceptable, reuse it (skip to Step 2). Re-research only on a stale or
   missing cache.
2. Websearch `"OpenCode Zen free models <current month year>"` + the OpenCode model catalog to enumerate
   the *candidate* free model ids (codenames included). This step is candidate **discovery**, not a
   quality judgment.
3. Run a canary probe to judge quality objectively: set `FARM_CANDIDATE_MODELS=<comma-separated ids>`
   and invoke `node "${CLAUDE_PLUGIN_ROOT}/tools/farm.js" --canary "<plan.json>"`. It runs the plan's
   smallest task against each candidate and writes `.farm/canary-report.json` ranked by measured
   pass-rate / attempts / latency. Pick the top passing model.
4. Surface the choice with its measured basis: "Selected `<model-id>` — canary passed in `<n>` attempts,
   `<ms>`ms (vs. `<alternatives>`). Proceed, or set `FARM_MODEL` to override." For any opaque codename,
   add one line of websearched identity context (e.g. "community reports GLM4-based") for the audit log.
5. Fallback ladder if the canary can't run or none pass: (a) the cached model from Step 1; (b) a
   websearch-selected model with a clear warning that the choice is unmeasured; (c) only if all fail,
   BLOCK and ask the user to set `FARM_MODEL`. Halting the whole feature on a noisy websearch is wrong —
   exhaust the ladder first.
6. Write the chosen `meta.model` + `meta.apiBaseUrl` into `plan.json`, and update `.farm/model-cache.json`
   (model + timestamp + canary pass-rate) before dispatching.

**Step 2 — Farm dispatch.** Invoke the farm dispatcher:

```
node "${CLAUDE_PLUGIN_ROOT}/tools/farm.js" "${CLAUDE_PROJECT_DIR}/.codearbiter/plans/<slug>.plan.json"
```

Run it with cwd set to `${CLAUDE_PROJECT_DIR}` (the dispatcher resolves `.farm/` and git worktrees
against the current directory). It runs tasks concurrently (up to `FARM_CONCURRENCY`, default 4),
enforces gates and a zero-token anti-gaming guard, and writes to `${CLAUDE_PROJECT_DIR}/.farm/`:
- `farm-report.json` / `farm-report.md` — per-task status, attempts, files, worker token spend, warnings
- `diffs/<task-id>.patch` — the actual change per task, for audit

Exit code 0 = all green; exit code 2 = some tasks escalated, blocked, or the run was aborted.

**Step 2.5 — Circuit-breaker abort.** If `farm-report.json` has `aborted: true`, the dispatcher tripped
its escalation-rate breaker — the chosen model is likely not capable of this slice. This is a hard-gate
surface: STOP and tell the user, recommending the premium path or a different `FARM_MODEL`. Do not
silently re-dispatch every task to premium Phase 2 (that erases the arbitrage and hides a bad signal).

**Step 3 — Escalation handler (Phase 2.5).** Read `farm-report.json`. For each result:

- **status `green`** — the test gate + anti-gaming guard passed, but it is NOT yet accepted. Route the
  task through **Phase 3 (spec-compliance), Phase 4 (quality review), and Phase 5 (fresh verification)**
  exactly as a premium subagent's output would be, measuring the merged change against the spec line the
  task traces to. A green result carrying a `warning` (gaming-risk) gets extra attention in Phase 3.
  Only after Phases 3–5 pass does the task reach Phase 6.
- **status `escalate`, note starts with `"drift:"`** — the cheap model wrote outside `filesInScope`
  even after a hardened-prompt retry. First occurrence on a task → treat as model incapacity, not a spec
  gap: re-dispatch via premium Phase 2 (the worktree at `result.worktree` shows the attempt). Only when
  **multiple tasks drift onto the same out-of-scope path** does it signal a genuine decomposition/spec
  gap — then raise `[CONFIRM-NN]` and halt.
- **status `escalate`, note starts with `"gaming:"`** — the model hard-coded the test's asserted value.
  Re-dispatch via premium Phase 2; do not accept the farm output.
- **status `escalate`, note starts with `"tampered test:"`** — the model altered the failing test.
  Re-dispatch via premium Phase 2; the test is the gate's integrity anchor.
- **status `escalate`, gate-failure note** — the model couldn't pass the test after retries. Re-dispatch
  via premium Phase 2, seeding the brief with `result.worktree`, the gate note, and `test.path`.
- **status `escalate`, note starts with `"merge failed"`** — re-order after the conflicting sibling and
  re-dispatch via Phase 2.
- **blocked** tasks (`farm-report.json` `blocked[]` array, each with a `reason`) — resolve the upstream
  escalation first, then re-queue.

Gate: every task is green AND passed Phases 3–5, or was re-dispatched via premium Phase 2 and accepted.
No task advances to commit-gate while any sibling is unresolved.

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

Dispatch the reviewers applicable to what the change touches, then `finding-triage`
(`${CLAUDE_PLUGIN_ROOT}/agents/finding-triage.md`) to classify every finding by severity. Select
reviewers by the diff, not blanket — dispatching an irrelevant reviewer wastes a context:

- `security-reviewer` (`${CLAUDE_PLUGIN_ROOT}/agents/security-reviewer.md`) — any security-relevant path (authn/authz, deploy, CI, trust boundary).
- `auth-crypto-reviewer` (`${CLAUDE_PLUGIN_ROOT}/agents/auth-crypto-reviewer.md`) — auth, crypto, key, or secret changes.
- `dependency-reviewer` (`${CLAUDE_PLUGIN_ROOT}/agents/dependency-reviewer.md`) — `package.json` / lockfile / base-image changes.
- `migration-reviewer` (`${CLAUDE_PLUGIN_ROOT}/agents/migration-reviewer.md`) — DB migration add/modify.

(Do NOT dispatch `grader` or `scout` — they are INTERNAL to `decision-variance` and must never be
dispatched here.) If the change touches none of the above domains, the quality bar is `tdd`'s own gates
plus `coverage-auditor` (already run in `tdd` Phase 4) — record that and proceed.

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
- MUST NOT invoke `farm.js` before writing `meta.model` into `plan.json` (or setting `FARM_MODEL`) — the dispatcher fails loudly otherwise.
- MUST NOT skip model selection (Step 1) when `FARM_MODEL` is not set — exhaust the canary→cache→websearch fallback ladder before BLOCKing; never blind-invoke with an unknown model id.
- MUST route every green farm task through Phases 3–5 before acceptance — the farm replaces authoring, never review. A cheap model gets the same scrutiny as a premium subagent, not less.
- MUST treat a single task's drift/gaming/tampered-test escalation as model incapacity (re-dispatch via premium Phase 2); raise `[CONFIRM-NN]` and HALT only when multiple tasks drift onto the same out-of-scope path (a real spec gap).
- MUST treat a `farm.js` circuit-breaker abort (`aborted: true`) as a hard-gate STOP — surface to the user; do not silently re-dispatch the whole slice to premium.
- MUST NOT dispatch `grader` or `scout` in Phase 4 — they are INTERNAL to `decision-variance`.
