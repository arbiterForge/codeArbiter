---
name: executing-plans
description: The checkpoint coordinator for /feature. Routed to by /feature once a writing-plans plan exists. Groups tasks into batches, delegates each batch to subagent-driven-development (fresh author agent per task, full review chain, fresh verification), then stops for a human checkpoint before the next batch. The checkpointed counterpart to /sprint's autonomous run.
---

# executing-plans

Coordinate the plan in small, user-acknowledged batches. Routed to by `/feature` after
`writing-plans` has produced a plan. Each batch is executed by `subagent-driven-development` — fresh
author agent per task, spec-compliance review, fresh verification, one quality review per scope — and the user
checkpoints between batches.

## Pre-flight

Read these, or STOP and surface the gap — never guess a path, a command, or a task boundary:

- `${CLAUDE_PROJECT_DIR}/.codearbiter/plans/<slug>.md` — the approved plan. The ordered task list and each task's verification command are the contract. No plan, no execution.
- `${CLAUDE_PROJECT_DIR}/.codearbiter/specs/<slug>.md` — the spec the plan implements.
- `${CLAUDE_PROJECT_DIR}/.codearbiter/CONTEXT.md` — the `stage:` frontmatter (the maturity value) and project context.
- `${CLAUDE_PROJECT_DIR}/.codearbiter/tech-stack.md` — the exact verification, test, and build invocations.

## Phase 1 — Batch plan · gate: BLOCK

Group the plan's tasks into small batches. Keep batches tight — three to five tasks is a ceiling, not
a target. Respect the plan's ordering and dependencies: a task never lands before the task it depends on.

**Resume is the normal re-entry.** A task already `ACCEPTED` in the plan's status column was verified
before an earlier interruption — exclude it from batching and say so ("resuming: T-01–T-03 already
ACCEPTED"). Batch only the non-`ACCEPTED` tasks, starting at the first. Never re-execute an `ACCEPTED`
task, and never restart the pipeline at brainstorming because the session died mid-plan.

For each task, confirm the plan names its exact target paths and its verification command. A task
missing either is underspecified — return it to `writing-plans`, do not improvise the gap.

Present the batch breakdown to the user as information, not a question: which tasks land in batch 1,
and what follows. Do NOT stop for a separate acknowledgment — the user approved the plan in
`writing-plans`, and the first Phase 3 checkpoint arrives after batch 1; a breakdown objection
surfaces there (or the user interrupts). Each unresolved unknown is a `[CONFIRM-NN]` in
`open-questions.md` — surface it, do not guess past it.

Gate: a batch sequence exists and every task has a target path and a verification command. A
`[CONFIRM-NN]` that blocks batch 1 is the only reason to stop here.

## Phase 2 — Execute batch · gate: BLOCK

Invoke `subagent-driven-development` with `scope = [current batch task IDs]`. Pass the plan slug and
spec slug so it can read its own pre-flight files. Do not implement anything here — the author agents,
review chain, and verification all execute inside that skill.

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

## Hard rules

- MUST clear every phase gate; a skipped phase is a hard-rule violation.
- MUST NOT execute tasks inline — delegate every batch to `subagent-driven-development` with an explicit `scope`.
- MUST NOT commit; route to `commit-gate` only after every batch is acknowledged and every plan task is `ACCEPTED`.
- MUST NOT swallow or re-dispatch around a halt from `subagent-driven-development` (tdd BLOCK, CRITICAL, CONFIRM-NN) — surfacing it to the user is the only path.
- MUST NOT absorb scope the plan does not name — mark it `[NEEDS-TRIAGE]`.
- MUST surface a plan-versus-code conflict via `/conflict`, never silently reconcile it.
