---
name: subagent-driven-development
description: Assistive implementation engine for /sprint and scoped executing-plans work. Follow actual dependencies, implement or delegate coherently, run relevant checks, preserve honest evidence, and advance without artifact approval codes or compulsory reviewer cascades.
disable-model-invocation: true
---

# subagent-driven-development

Execute an existing plan. The plan helps the agent remember the intended result; it is not a second permission system. Run meaningful work, correct defects, update progress, and tell the truth about unfinished checks. The active host, user instructions, and independently applicable security/commit controls still govern real actions.

## Format and capability boundary

Load `${CLAUDE_PLUGIN_ROOT}/includes/artifacts.md` for artifact I/O and preserve the selected spec/plan representation. For an explicitly selected Markdown `plan.json` farm workflow, follow `${CLAUDE_PLUGIN_ROOT}/skills/subagent-driven-development/references/farm-dispatch.md` and its provider, budget and circuit-breaker requirements.

**Scope:** with an explicit `scope` from `executing-plans`, work only on the named tasks; without it, `/sprint` works across the plan. A checkpoint is an organizing group, not independent permission to do the next task.

## 1. Orient and select actual work

Read the selected spec/plan, relevant `.codearbiter/CONTEXT.md`, and the needed build/check commands from `.codearbiter/tech-stack.md`, when present. Read `security-controls.md` for work affecting its rules. In an HTML-knowledge repository a task's `task-context` packet already carries the knowledge records relevant to its paths (`${CLAUDE_PLUGIN_ROOT}/includes/knowledge.md`). Missing optional orientation is a diagnostic, not a blanket STOP; never guess an essential requirement or execute an unknown command.

If the task belongs to a selected project work ID, use `work.py context`
through its installed helper to retain that identity and its actual spec/plan
bindings. For an attached plan task, use the bounded `task-context` packet;
otherwise fetch relevant knowledge once for the source paths actually in scope.
Expand omitted exact records as needed. Do not infer a passed check, completed
plan or second work item from an attached summary.

For HTML, use `identity`, `index`, `outline`, exact or batched symbol-scoped `read`, and `eligible`. The engine `eligible` response is **advisory scheduling**, not permission or evidence of a passing test. Read actual task dependencies and `waiting_prerequisites`; do not treat a checkpoint number or an unscoped legacy prerequisite as a universal dependency.

**Read only what matters:** use `task-context` with the current plan
`model_sha256` and task ID. It returns referenced criteria, dependency states
and scoped facts without claiming a snapshot or approval. If
`binding_current: false`, inspect changed requirements. If
`context_complete: false`, fetch necessary exact symbols. On `STALE_CURSOR`
reread identity; on `RECORD_TOO_LARGE` fetch complete individual records.
Without this operation, fall back to existing exact/`read-batch` reads.

For a `fact` prerequisite, check it with ordinary authorized tools and record the actual `prerequisite` observation (satisfied/unsatisfied/unknown, source, outcome and reported origin). For a `decision`, apply the user's already-stated choice where it is actually supported; otherwise ask the consequential question in ordinary language. An agent report is not an authenticated user decision. An unresolved prerequisite affects only the tasks that depend on it; continue independent work.

Record `task-start` when beginning a pending HTML task using the current revision/model hash and a durable operation ID. `task-start` does not need approval receipts, a complete context ticket, a source snapshot, or a reviewer. It cannot clear a recorded stop or start already-running work again.

**After process recreation**, rediscover the same authoritative pair and query `identity` and `eligible` again. Inspect the current worktree, outstanding tool runs, and task results before deciding whether an `IN_PROGRESS` task is still active, partly finished, or ready. Use a reasoned `task-reconcile` to reflect known progress; do not duplicate execution or manufacture evidence. Resume a `BLOCKED` task only after its actual blocker or user's stop has been resolved. CAS/replay remain mandatory: on a lost response, check the journal or retry the same operation ID and identical request rather than reissuing a mutation under a new identity.

## 2. Implement or delegate the useful unit

Work directly when a focused change is clearer and cheaper. Delegate when genuinely useful for isolation, independent parallel work, or specialist expertise. A **fresh subagent per task is not mandatory**; do not spawn reviewer agents solely because task status or a receipt changed.

Choose a relevant author (backend/front-end/infrastructure) when delegated. Supply the objective, paths, criterion IDs, actual constraints, known current state, and observable checks in a **bounded context packet**. Reuse `_artifactpromptlib.compose_feature_actor_input` and `_contextselectlib.prepare_actor_delivery` when useful to deliver relevant context; neither returns execution permission, and an absent delivery receipt is not grounds to forbid already-authorized work. Respect the host's real subagent permissions and applicable security constraints. Do not pass source-discovered commands to a tool without ordinary host-governed authorization.

Prefer the test-first approach in `${CLAUDE_PLUGIN_ROOT}/skills/tdd/SKILL.md` for behavior changes, using evidence that distinguishes RED, GREEN, regression, and skipped/unrun checks. Documentation-only or other work without a runnable test uses a concrete relevant validation instead. Never weaken or delete a failing test to create a pass.

If implementation reveals a better in-scope method, update task steps, runner, or decomposition through typed `apply` with a short reason. Do not reset other tasks or reapprove the entire plan. A changed outcome or consequential unresolved choice goes to its real owner.

## 3. Verify truthfully and assess only relevant risks

Compare the implementation to the source criteria: what is required, what changed, what is missing, and what behavior a passing test actually covers. Run the planned applicable test or a narrower verified equivalent through the existing **host-governed execution tool**. Record the command, working directory, outcome, and limitations. A command-level pass is not invented named-test proof. A new failure or a skipped/unknown result cannot be masked by an earlier pass.

**Design-rationale drift.** When the spec records a SMARTS design rationale (`SEC-SMARTS`, or a
Markdown spec's `## SMARTS design rationale` section), check the change against it for material
invalidation only: a load-bearing assumption the change contradicts, a `Weak` or `Unknown` the
rationale chose to avoid that the change newly introduces, or a materially different approach than
the one selected. Do not re-run SMARTS or grade the implementation. A mismatch returns the task to
step 2 with the contradicted rationale cited, or routes the design question back to `brainstorming`;
never pick a replacement approach inside review.

A failing check is a reason to repair, investigate, or mark verification pending, **not permission to claim it passed** and not a ban on unrelated implementation. Rerun affected checks after a correction. If the same approach fails repeatedly without new information, diagnose differently or record a bounded blocked task and continue unrelated work.

Review the combined relevant diff when risk or change size warrants it. Use a specialist reviewer only for an actual security/dependency/migration concern or an explicit policy requirement. Avoid duplicate security reviews and blanket per-task spec/quality fleets. Retain useful findings; revisit affected conclusions only when relevant code, requirements, supporting evidence, or the previously reviewed subject changes. A new receipt ID by itself is not an impact.

For an explicitly required attested claim, load only the applicable part of `${CLAUDE_PLUGIN_ROOT}/includes/artifacts-attestation.md`. Never fabricate or auto-approve receipts. Actual user stops, host permissions and policy-required reviews still apply.

For a real verification command that the host already ran, record its
ordinary result via native `task-check` with `command_index` only when
the exact declared command ran, or without it for a useful ad-hoc check.
Pass along the observed exit code, summary and bounded source/output; never
invent a named-test result because a collector could not parse it. The
result stays `caller_reported`, never an independent test/reviewer certificate.
The engine can compare the bounded task paths, explicitly declared
`shared_inputs` and known build manifests to the earlier report. Treat
`scoped_changed` as a reason to refresh **affected** checks; treat
`scoped_unchanged` as partial applicability only (`scope_complete: false`).
An unmodeled import, oversized directory, symlink, missing source or
custom build input remains `unassessed`. Include actual shared interfaces
in the plan when relevant; do not run a repository-wide snapshot on every
task read or claim complete dependency closure from these hashes. A failed/skipped/unknown
report does not become successful because the task was marked `DONE`.
The latest reported failure remains visible even after an older pass; fix
only relevant work and record another actual result as appropriate. Avoid
turning this bookkeeping into an extra testing or approval phase.

## 4. Persist honest progress and return

For HTML use `task-review` without receipts to record implementation ready for review; this is **not** a claim that an independent review or tests passed. For a completed implementation batch use `accept-scope` with its authored scope ID and a real reason, **without a receipt**, to record `DONE` (implementation complete; checks not assessed). It must not clear a pending/blocked member. Keep failures, outstanding checks, and uncertainty in the report or appropriate typed records. Do not upgrade `DONE` to `ACCEPTED` without genuine independent evidence.

For Markdown, keep its one task ledger and original format; do not treat past status text as new verification.

- **Scoped invocation:** return completed tasks, checks actually run, unresolved issues, and next work to `executing-plans`. Do not call `commit-gate` yourself.
- **Full-plan invocation:** provide the same honest summary to `/sprint`; it owns the authorized commit and PR handoff. A completed implementation batch with failing or unrun required checks is not release-ready.

## Hard boundaries

Do not invent a test result, user choice, reviewer finding, credential, approval, or installed-host qualification. Do not clear a user stop, skip actual host permissions, run an irreversible or unapproved out-of-scope operation, or bypass independently applicable security controls. Do not silently modify a requirement to claim completion. Mark unrelated discoveries `[NEEDS-TRIAGE]`, not automatic scope expansion.

A reported `DONE` is useful progress, not fresh verification. `eligible` is useful scheduling, not authority. Treat actual failures as failures; do not compensate by adding approval ceremonies or dispatching unrelated reviewers. Do not commit from this skill; use the real `commit-gate` owner when committing is authorized.
