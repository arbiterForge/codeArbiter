---
name: subagent-driven-development
description: Assistive implementation engine for /sprint and scoped executing-plans work. Follow actual dependencies, implement or delegate coherently, run relevant checks, preserve honest evidence, and advance without artifact approval codes or compulsory reviewer cascades.
disable-model-invocation: true
---

# subagent-driven-development

Execute an existing plan. The plan helps the agent remember the intended result; it is not a second permission system. Run meaningful work, correct defects, update progress, and tell the truth about unfinished checks. The active host, user instructions, and independently applicable security/commit controls still govern real actions.

## Format and capability boundary

New full-lane workflows default to HTML through the installed engine. Existing authoritative Markdown pairs remain in their original format without automatic conversion. Load `${CLAUDE_PLUGIN_ROOT}/includes/artifacts.md` before HTML I/O; use the pinned native writer, typed operations, and symbol-bound records. Do not scrape HTML or maintain a shadow Markdown ledger. If the HTML writer is unavailable or an artifact write fails, say precisely what was not saved; do not invent a fallback artifact or report success. Safe authorized inspection and repair can continue where the missing artifact is not needed.

HTML `--farm` is disabled. An explicitly selected, existing Markdown `plan.json` farm workflow retains its separate dispatch procedure in `${CLAUDE_PLUGIN_ROOT}/skills/subagent-driven-development/references/farm-dispatch.md`, including its real provider/budget/circuit-breaker protections. This assistive default does not silently switch backends or imply farm qualification.

**Scope:** with an explicit `scope` from `executing-plans`, work only on the named tasks; without it, `/sprint` works across the plan. A checkpoint is an organizing group, not independent permission to do the next task.

## 1. Orient and select actual work

Read the selected spec/plan, relevant `.codearbiter/CONTEXT.md`, and the needed build/check commands from `.codearbiter/tech-stack.md`, when present. Read `security-controls.md` for work affecting its rules. Missing optional orientation is a diagnostic, not a blanket STOP; never guess an essential requirement or execute an unknown command.

For HTML, use `identity`, `index`, `outline`, exact or batched symbol-scoped `read`, and `eligible`. The engine `eligible` response is **advisory scheduling**, not permission or evidence of a passing test. Read actual task dependencies and `waiting_prerequisites`; do not treat a checkpoint number or an unscoped legacy prerequisite as a universal dependency.

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

A failing check is a reason to repair, investigate, or mark verification pending, **not permission to claim it passed** and not a ban on unrelated implementation. Rerun affected checks after a correction. If the same approach fails repeatedly without new information, diagnose differently or record a bounded blocked task and continue unrelated work.

Review the combined relevant diff when risk or change size warrants it. Use a specialist reviewer only for an actual security/dependency/migration concern or an explicit policy requirement. Avoid duplicate security reviews and blanket per-task spec/quality fleets. Retain useful findings; revisit affected conclusions only when relevant code, requirements, supporting evidence, or the previously reviewed subject changes. A new receipt ID by itself is not an impact.

An explicit receipt-backed review/verification claim remains available under the historical attestation section of `includes/artifacts.md` **only when an actual caller requires such proof**. Never create, auto-approve, relabel, or simulate a receipt to move ordinary progress. Host security controls, actual deny/stop instructions, and policy-required reviews are independent of the artifact status engine.

## 4. Persist honest progress and return

For HTML use `task-review` without receipts to record implementation ready for review; this is **not** a claim that an independent review or tests passed. For a completed implementation batch use `accept-scope` with its authored scope ID and a real reason, **without a receipt**, to record `DONE` (implementation complete; checks not assessed). It must not clear a pending/blocked member. Keep failures, outstanding checks, and uncertainty in the report or appropriate typed records. Do not upgrade `DONE` to `ACCEPTED` without genuine independent evidence.

For Markdown preserve its canonical ledger and meaningful statuses. Do not equate an old Markdown `ACCEPTED` status with a new native receipt, or change representation as a shortcut.

- **Scoped invocation:** return completed tasks, checks actually run, unresolved issues, and next work to `executing-plans`. Do not call `commit-gate` yourself.
- **Full-plan invocation:** provide the same honest summary to `/sprint`; it owns the authorized commit and PR handoff. A completed implementation batch with failing or unrun required checks is not release-ready.

## Hard boundaries

Do not invent a test result, user choice, reviewer finding, credential, approval, or installed-host qualification. Do not clear a user stop, skip actual host permissions, run an irreversible or unapproved out-of-scope operation, or bypass independently applicable security controls. Do not silently modify a requirement to claim completion. Mark unrelated discoveries `[NEEDS-TRIAGE]`, not automatic scope expansion.

A reported `DONE` is useful progress, not fresh verification. `eligible` is useful scheduling, not authority. Treat actual failures as failures; do not compensate by adding approval ceremonies or dispatching unrelated reviewers. Do not commit from this skill; use the real `commit-gate` owner when committing is authorized.
