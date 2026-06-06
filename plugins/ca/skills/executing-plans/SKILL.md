---
name: executing-plans
description: The inline, checkpointed plan executor. Routed to by /feature once a writing-plans plan exists, to work that plan in the main session WITH human checkpoints between batches. Each task routes implementation through tdd and is proven done by a fresh verification run — never an assumption. The non-autonomous counterpart to subagent-driven-development (which /sprint uses to work the same plan without per-batch checkpoints).
---

# executing-plans

Work the plan in the open, in small batches, and stop at every checkpoint. Routed to by `/feature`
after `writing-plans` has produced a plan.

## Pre-flight

Read these, or STOP and surface the gap — never guess a path, a command, or a task boundary:

- `${CLAUDE_PROJECT_DIR}/.codearbiter/plans/<slug>.md` — the approved plan. The ordered task list and each task's verification command are the contract. No plan, no execution.
- `${CLAUDE_PROJECT_DIR}/.codearbiter/specs/<slug>.md` — the spec the plan implements; the obligation source `tdd` Phase 1 consumes per task.
- `${CLAUDE_PROJECT_DIR}/.codearbiter/CONTEXT.md` — the `stage:` frontmatter (the maturity value) and project context.
- `${CLAUDE_PROJECT_DIR}/.codearbiter/tech-stack.md` — the exact verification, test, and build invocations. The plan cites them; resolve them here.
- `${CLAUDE_PROJECT_DIR}/.codearbiter/coding-standards.md` — style and structure, enforced per task through `tdd`.
- `${CLAUDE_PROJECT_DIR}/.codearbiter/security-controls.md` — only when a task touches a security boundary (auth, crypto, secrets). Optional; absent on most plans.

## Phase 1 — Batch plan · gate: BLOCK

Group the plan's tasks into small batches — a batch is the work you can land and prove before the
user reasonably wants a status. Keep batches tight; three to five tasks is a ceiling, not a target.
Respect the plan's ordering and dependencies — a task never lands before the task it depends on.

For each task, confirm the plan names its exact target paths and its verification command. A task
missing either is underspecified — return it to `writing-plans`, do not improvise the gap.

Present the batch breakdown to the user: which tasks land in batch 1, and what follows. Each
unresolved unknown is a `[CONFIRM-NN]` in `open-questions.md` — surface it, do not guess past it.

Gate: a batch sequence exists, every task has a target path and a verification command, and the user
has acknowledged the breakdown. A batch built on a missing path or command does not pass.

## Phase 2 — Execute task · gate: BLOCK

Take the next task in the current batch. Route its implementation through the `tdd` skill — test
first, every phase, no exception. `tdd` Phase 1 reads the obligations for this task from the spec;
no implementation code is written before that phase clears.

Implement the task and nothing beyond it. Scope creep is a finding, not a feature: work that the
plan does not name gets an inline `[NEEDS-TRIAGE]` marker and is left for triage — never silently
absorbed into the task. A genuine conflict between the plan and the code halts work and routes to
`/surface-conflict`.

Gate: `tdd` reports all phases green for this task. A task whose `tdd` pass is incomplete is not
done — it does not advance to verification.

## Phase 3 — Verify task · gate: BLOCK

Run the task's verification command from the plan, **fresh**, in this session. Read the actual
output and the exit code. "Done" is a claim backed by a clean run you just watched — never an
inference from "the code looks right" or "the tests should pass."

A non-zero exit, or output that does not show the task's behavior actually working, returns the task
to Phase 2. Do not edit the verification to make it pass; fix the code.

Gate: the verification command exits zero on a fresh run and its output proves the task's behavior.
Mark the task done in the plan only then. Loop to Phase 2 for the next task in the batch.

## Phase 4 — Checkpoint · gate: STOP

Every task in the batch is done and verified. STOP and checkpoint with the user before any further
work:

- **Landed** — the tasks completed this batch, each with the verification that proved it.
- **Next** — the tasks in the upcoming batch.
- **Open** — any `[NEEDS-TRIAGE]` marker raised, any `[CONFIRM-NN]` still blocking.

Do not begin the next batch until the user acknowledges. This is the line that separates this skill
from `subagent-driven-development` — the human gate is the point, not an obstacle.

Gate: the user has acknowledged the checkpoint. On acknowledgement, loop to Phase 2 for the next
batch. When the final batch is acknowledged and the plan is fully verified, the work is ready for
`commit-gate`; route there — do not commit from here.

## Hard rules

- MUST NOT write feature code for a task before that task's `tdd` Phase 1 completes.
- MUST NOT mark a task done without a fresh verification run whose exit code is zero and whose output proves the behavior.
- MUST NOT claim a task or batch done on assumption, on "the suite should pass," or on a prior run's result.
- MUST NOT advance past a checkpoint the user has not acknowledged.
- MUST NOT execute a task the plan does not specify; absorb no scope it does not name — mark it `[NEEDS-TRIAGE]`.
- MUST NOT edit a verification command to make a task pass — fix the code.
- MUST NOT commit; route to `commit-gate` when the plan is fully verified.
- MUST NOT guess a verification, test, or build command — read `tech-stack.md`/the plan or STOP.
- MUST surface a plan-versus-code conflict via `/surface-conflict`, never silently reconcile it.
