---
name: dispatching-parallel-agents
description: "Parallel fan-out for authors, scouts and reviewers. Collect every result; only explicit review batches use finding-triage and verdict-aggregator."
disable-model-invocation: true
---

# dispatching-parallel-agents

Fan out and collect every result. The caller's existing agent kind and completion contract determine whether this is author/scout work or an explicit review batch. This routing adds no receipt, approval mode or extra review requirement. The primitive owns parallel discipline, not domain logic.

## Pre-flight

The caller supplies the work. Confirm it, or STOP and surface the gap — never invent units or pick an agent on a hunch:

- **The unit list** — N discrete, independently-completable units of work, each with its scope and target paths.
- **The agent kind** — which agent kind to dispatch per unit (e.g. `backend-author`, `frontend-author`, `scout`, `security-reviewer` at [agents/<name>.md](../../agents/<name>.md)). One kind per batch.
- **The completion contract** — what each agent must return: a structured result, its unit ID, pass/fail/error status, required checks and any findings or unfinished obligations. Self-reports are claims, not evidence (see Phase 4). Preserve whether the caller requested authors/scouts or an explicit reviewer batch.

## Phase 1 — Partition · gate: BLOCK

Split the work into units that do not collide. A unit owns a distinct file or path set; two units in one batch MUST NOT mutate the same path.

- **Independent paths** — units touch disjoint files. Dispatch directly. This is the common, fast case.
- **Shared paths unavoidable** — units must mutate the same file or tree. Do NOT dispatch into the conflict. Route to `using-git-worktrees` ([routines/using-git-worktrees/SKILL.md](../using-git-worktrees/SKILL.md)) to give each unit an isolated working tree, or serialize the colliding units into one sequential unit. A shared-path collision in a parallel batch is a corruption, not a merge.

Tag each unit with its ID, scope, target paths, and the agent kind. Read-only batches (review, scout) skip the collision check — they mutate nothing.

Gate: every unit has a disjoint path set, or its overlap is resolved by worktree isolation or serialization. An unresolved collision does not pass.

## Phase 2 — Dispatch · gate: BLOCK

Dispatch one agent per unit, bounded.

- **Concurrency bound** — dispatch in waves of at most a fixed width (default 4 concurrent agents; the caller MAY override). Do not fan out unbounded; a hundred agents at once starves the batch and corrupts nothing useful.
- **Fresh and isolated** — each agent gets only its own unit's scope and the completion contract. No agent sees another's working state. No shared mutable context between units in flight.
- **Hard-stop propagation** — a `tdd` BLOCK, a `commit-gate` failure, a security CRITICAL, or a `[CONFIRM-NN]` inside any unit halts that unit and surfaces immediately; it does not get silently swallowed by the batch.

Gate: every unit is dispatched or explicitly deferred. No unit is dropped silently at dispatch.

## Phase 3 — Collect · gate: BLOCK

Wait for the full wave, then the next, until every unit has terminated. Record each unit's terminal state: `DONE` (returned a result), `ERRORED` (the agent failed), or `DEFERRED` (a hard-stop surfaced).

An `ERRORED` unit is not complete. Preserve its diagnostic output and any still-inspectable changed paths for diagnosis; do not apply its unreviewed partial changes as a finished unit. **One errored unit MUST NOT corrupt or discard the batch.** The remaining units' results stand. Record errors and deferrals for the caller, and for the review funnel when this is an explicit review batch; do not retry blindly.

Gate: every unit has a terminal state and `DONE` results are captured intact. A still-running or unaccounted unit prevents a complete batch result; partial diagnostic evidence remains visible.

## Phase 4 — Dedupe · gate: BLOCK

Parallel agents over adjacent units may report the same defect or contradict each other. Reconcile the actual overlap before the coordinator uses the result.

- Merge findings that name the same defect at the same location into one, keeping the highest severity reported.
- Reconcile contradictory results across units (two units that disagree on the same fact) into a single surfaced conflict, not a silent pick.
- Inspect any "done" claim that gates real work: command, cwd, relevant source/input identity, output and exit code. Reuse accessible applicable passing evidence when those inputs still match; run a missing, changed, insufficient or unresolved check. A success sentence without accessible evidence is not proof. Follow [includes/fresh-verification.md](../../includes/fresh-verification.md).

Gate: overlapping findings are deduped, contradictions surfaced, and completion claims inspected against applicable evidence. No failed or unknown result becomes a pass because another unit succeeded.

## Phase 5 — Return by the caller's contract · gate: STOP

**Author/scout batches return inspected results directly** to their coordinator: unit IDs, changed paths or source observations, accessible checks, errors, deferrals, contradictions and remaining obligations. The coordinator reviews implementation and applies only accepted units through its normal task and worktree contract. It does not dispatch `finding-triage` or `verdict-aggregator` merely to collect author/scout work. This result is not an independent reviewer certificate.

**Explicit review batches use finding-triage then verdict-aggregator** in order:

1. Dispatch `finding-triage` ([agents/finding-triage.md](../../agents/finding-triage.md)) over the complete deduped reviewer result set and batch contract. It classifies severity and marks out-of-scope items with inline `[NEEDS-TRIAGE]`. Every reviewer finding reaches the verdict; only non-finding transport metadata may be omitted. `ERRORED`, `DEFERRED` and missing reviewer units remain incomplete-result findings.
2. Hand the complete triage report to the read-only `verdict-aggregator` ([agents/verdict-aggregator.md](../../agents/verdict-aggregator.md)). It returns `PASS`, `BLOCKING_FINDINGS`, or `INCOMPLETE`; incompleteness takes precedence without suppressing blocking findings.

Gate: the caller gets its selected completion result. An explicit review cannot bypass the funnel; an author/scout batch cannot claim a review verdict.

## Hard rules

- MUST NOT dispatch two units that mutate the same path in one batch; isolate via `using-git-worktrees` or serialize.
- MUST NOT fan out unbounded; dispatch within the concurrency bound.
- MUST NOT let one `ERRORED` unit discard or corrupt the rest of the batch, or apply its unreviewed partial changes as complete.
- MUST use the `finding-triage` → `verdict-aggregator` funnel for every explicit review batch and preserve every finding, contradiction and incomplete unit.
- MUST NOT require that reviewer funnel for an author/scout batch whose caller requested direct results.
- MUST NOT trust a subagent's self-reported completion; inspect accessible proving evidence and rerun only missing or affected checks.
- MUST NOT silently drop a unit — every unit terminates with a visible result, error or deferral.
