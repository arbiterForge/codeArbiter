---
name: executing-plans
description: The checkpoint coordinator for /feature. Routed to by /feature once a writing-plans plan exists. Uses authored HTML checkpoints or bounded legacy batches, delegates each scope to subagent-driven-development (fresh author agent per task, full review chain, fresh verification), then stops for a human checkpoint before the next batch. The checkpointed counterpart to /sprint's autonomous run.
disable-model-invocation: true
---

# executing-plans

## Structured-artifact format boundary

New full-lane workflows default to HTML through the installed engine. Existing
HTML pairs use the same path. Load
`{{PLUGIN_ROOT}}/includes/artifacts.md` before HTML artifact I/O;
its typed identity, binding, receipt, contextual-read, and scope-state rules
replace rendered-document parsing and direct status-cell edits. Existing
authoritative Markdown pairs stay on their exact legacy path without conversion.
A missing, invalid, or unqualified HTML capability must fail closed rather than
fall back to new Markdown authority. HTML `--farm` dispatch remains disabled.
Keep every other workflow gate, including human checkpoints, unchanged.


Coordinate the plan in small, user-acknowledged batches. Routed to by `/feature` after
`writing-plans` has produced a plan. Each batch is executed by `subagent-driven-development` — fresh
author agent per task, spec-compliance review, quality review, fresh verification — and the user
checkpoints between batches. The orchestrator never implements; it schedules and checkpoints.
An HTML checkpoint is an acceptance scope, not a new user checkpoint in `/sprint`. Sprint routes
directly to `subagent-driven-development` and does not inherit this attended coordinator's pauses.

## Pre-flight

Read these, or STOP and surface the gap — never guess a path, a command, or a task boundary:

- The discovered authoritative spec/plan pair. Existing Markdown pairs retain
  their current ledger. For an HTML pair, load
  `{{PLUGIN_ROOT}}/includes/artifacts.md`, retain the exact artifact identities
  and engine-written receipts, and obtain task, scope, dependency, and binding
  state only through `identity`, `index`, `outline`, symbol-scoped `read`, and
  `eligible`. The engine `eligible` response is authoritative; the coordinator
  must not infer authority from rendered text, checkboxes, status words,
  digests, or caller-supplied labels, and must not read or write a shadow
  Markdown ledger.
- `{{PROJECT_DIR}}/.codearbiter/CONTEXT.md` — the `stage:` frontmatter (the maturity value) and project context.
- `{{PROJECT_DIR}}/.codearbiter/tech-stack.md` — the exact verification, test, and build invocations.

## Phase 1 — Batch plan · gate: BLOCK

For Markdown, group remaining tasks into small batches; the three-to-five task ceiling is legacy
presentation guidance, not a reason to rewrite typed scope. For HTML, read the authored checkpoint partition
through the installed engine. Build the sequence from the plan's exact checkpoint membership and ordering,
retaining each checkpoint's full task-ID set as its acceptance scope. Skip a checkpoint only when current
engine evidence establishes its accepted state. Do not remove `REVIEW` tasks from an unfinished checkpoint:
they still need the combined review and whole-scope acceptance. Likewise, do not drop `BLOCKED` members:
excluding one does not make the checkpoint complete. Resume it only through the supported reconciliation path
and refreshed eligibility. Respect explicit dependencies in either format.

A smaller display grouping must not split an HTML acceptance scope, combine checkpoints, or change their
membership to fit a task-count ceiling. Execute and accept one authored scope at a time. If the partition
itself is unsuitable, return the actual problem to `writing-plans` for the existing amendment/approval path;
do not mutate scope identity in the coordinator or add a new batching registry.

**Resume is the normal re-entry.** For Markdown, a task already `ACCEPTED` in
the plan's status column was verified before an earlier interruption. For HTML,
derive resume from current `eligible` evidence and the authored checkpoint partition above.
For Markdown, exclude accepted tasks from new batches. For HTML, retain checkpoint membership while
selecting only eligible work, and say which current accepted checkpoints are already complete.
Stale proof requires its existing reconciliation and revalidation, not automatic reimplementation.
Never restart the pipeline at brainstorming merely because the session died mid-plan.

After process recreation on an HTML pair, rediscover the same authoritative pair
and query `identity` and `eligible` again. An `IN_PROGRESS` task is not proof of
completion. Use the installed reconciliation adapter in `{{PLUGIN_ROOT}}/includes/artifacts.md` for the exact task,
including its genuine host-observed decision and exact stored retry identity; do not construct
an authority event in this coordinator. A supported `task-reconcile` transition must precede
redispatch through `task-start` with a fresh complete context ticket. A task in `REVIEW` still requires fresh evidence and the current
scope review before `accept-scope`; conversation memory cannot advance it.

For each task, confirm the plan names its exact target paths and its verification command. A task
missing either is underspecified — return it to `writing-plans`, do not improvise the gap.

Present the batch breakdown to the user as information, not a question: which tasks land in batch 1,
and what follows. Do NOT stop for a separate acknowledgment — the user approved the plan in
`writing-plans`, and the first Phase 3 checkpoint arrives after batch 1; a breakdown objection
surfaces there (or the user interrupts). Each unresolved unknown is a `[CONFIRM-NN]` in
`open-questions.md` — surface it, do not guess past it.

Gate: a batch sequence exists and every task has a target path and a verification command.
Missing current authority or capability, a stale prerequisite, or a `[CONFIRM-NN]` blocking the
first scope is a gate failure. Follow the existing diagnostic or reconciliation owner; do not
invent a plan, drop blocked members, or restart the interview to clear it.

## Phase 2 — Execute batch · gate: BLOCK

Invoke `subagent-driven-development` (`{{PLUGIN_ROOT}}/skills/subagent-driven-development/SKILL.md`) with `scope = [current batch task IDs]`. Pass the plan slug and
spec slug so it can read its own pre-flight files. Do not implement anything here — the author agents,
review chain, and verification all run inside that skill.

For HTML, pass the selected spec/plan identities and the complete task-ID set for one authored checkpoint;
do not pass a partial or cross-checkpoint task set. Labels and presentation batches do not confer acceptance.
The nested workflow uses engine eligibility to select work inside that scope, records dispatch with `task-start`, records
the separate verification and spec-review receipts with `task-review`, and
records whole-scope acceptance once with `accept-scope`. Preserve every returned
identity and receipt for the checkpoint and later commit proof.

`subagent-driven-development` returns when every task in the scope is `ACCEPTED` (Phase 3–5 green,
verification passed on a fresh run). A `tdd` BLOCK, a security CRITICAL finding, or an unresolved
`[CONFIRM-NN]` surfaced inside that skill halts the loop — surface it to the user and do not proceed.

Gate: `subagent-driven-development` signals batch complete with all scoped tasks `ACCEPTED`. Any
unresolved halt from inside the skill is a gate failure here.

## Phase 3 — Checkpoint · gate: STOP

Every task in the batch is done and verified. STOP and checkpoint with the user before any further
work:

- **Landed** — the tasks completed this batch, each verified by `subagent-driven-development` Phase 5.
- **Next** — the tasks in the upcoming batch.
- **Open** — any `[NEEDS-TRIAGE]` marker raised inside the batch, any `[CONFIRM-NN]` still blocking.

Do not begin the next batch until the user acknowledges. This gate is the point of `/feature` — the
human checkpoint that separates it from `/sprint`'s autonomous run.

Gate: the user has acknowledged the checkpoint. On acknowledgement, loop to Phase 2 for the next
batch. When the final batch is acknowledged and the plan is fully verified, route to `commit-gate` —
do not commit from here.

Before claiming that an HTML plan's final batch completed, use the installed
bridge's `_preflight_current_acceptance` with the exact route returned by
`_resolve_workflow_pair`, the repository-bound client, and the engine-returned
spec and plan artifact IDs. Pass no caller status, digest, receipt, or label.
Retain the returned engine identities and receipt set for `commit-gate`. Any
refusal leaves the batch incomplete and blocks the handoff.

## Hard rules

- MUST NOT execute tasks inline — delegate every batch to `subagent-driven-development` with an explicit `scope`.
- MUST NOT advance past a checkpoint the user has not acknowledged.
- MUST NOT call `commit-gate` until all batches are acknowledged and every plan
  task is accepted; for HTML this means a fresh `eligible` result reports
  `all_accepted_and_current: true` for the selected plan identity.
- MUST surface any halt from `subagent-driven-development` (tdd BLOCK, CRITICAL, CONFIRM-NN) to the user — do not swallow it or re-dispatch around it.
- MUST NOT absorb scope the plan does not name — mark it `[NEEDS-TRIAGE]`.
- MUST NOT commit; route to `commit-gate` when the plan is fully verified.
- MUST return an underspecified task (missing path or verification command) to `writing-plans` — do not improvise the gap.
- MUST surface a plan-versus-code conflict via `/conflict`, never silently reconcile it.
