---
name: writing-plans
description: The spec-to-plan bridge. Routed to by /feature once the brainstormed spec is approved, and by /sprint before execution. Decomposes the spec into 2–5 minute tasks, each carrying its exact file path(s) and a concrete verification step that maps to a tdd obligation. Writes the plan to .codearbiter/plans/<slug>.md, ordered with dependencies flagged and an MVP slice identifiable. Nothing executes until every task has a path and a verification and the task set covers every acceptance criterion.
---

# writing-plans

Turn an approved spec into an executable plan. Routed to by `/feature` (after spec approval) and `/sprint`.

## Pre-flight

Read these, or STOP and surface the gap — never plan against an unapproved or missing spec:

- `${CLAUDE_PROJECT_DIR}/.codearbiter/specs/<slug>.md` — the approved brainstorming spec. The single source of acceptance criteria. Absent or unapproved → STOP and route back to `/feature`.
- `${CLAUDE_PROJECT_DIR}/.codearbiter/CONTEXT.md` — the `stage:` frontmatter (the maturity value) and project context.
- `${CLAUDE_PROJECT_DIR}/.codearbiter/tech-stack.md` — file layout, build/test/lint invocations. A verification step cites a real command from here, never a guess.
- `${CLAUDE_PROJECT_DIR}/.codearbiter/coding-standards.md` — structure and naming, so a task names the right path.

**If `--farm` was requested:** check that `FARM_API_KEY` is set in the environment (or `.env` at `${CLAUDE_PLUGIN_ROOT}/tools/.env`). If absent, BLOCK immediately — cite `${CLAUDE_PLUGIN_ROOT}/includes/farm.md` for setup instructions. Do not proceed; the farm dispatcher cannot run without an API key. Model selection happens later (at dispatch time in `subagent-driven-development`), so no model research is needed here.

## Phase 1 — Criterion extraction · gate: BLOCK

Lift every acceptance criterion from the spec verbatim and assign each a stable ID (`AC-01`,
`AC-02`, …). This list is the coverage ledger for the whole plan — Phase 4 checks the task set
against it.

A criterion the spec leaves ambiguous is a `[CONFIRM-NN]` against
`${CLAUDE_PROJECT_DIR}/.codearbiter/open-questions.md` — surface it, do not invent the intent.

Gate: every acceptance criterion in the spec captured as a numbered `AC-NN`. A partial ledger does
not pass.

## Phase 2 — Task decomposition · gate: BLOCK

Break the work into the smallest honest units. Each **task** is ~2–5 minutes of work and carries:

- **id** — `T-01`, `T-02`, … stable.
- **path(s)** — the exact file(s) the task touches, resolved against `coding-standards.md`. "Some files" is not a path.
- **verification** — one concrete command or observable that proves the task done (e.g., `<test cmd> -k test_token_expiry passes`, `endpoint returns 401 on missing header`). It cites a real `tech-stack.md` invocation or a directly observable behavior — never "looks right".
- **maps-to** — the `tdd` obligation this verification corresponds to. The verification *maps to* a tdd obligation; it does NOT replace tdd's own gates. `tdd` Phase 1 still derives and Phase 4 still verifies obligations against passing tests.
- **covers** — the `AC-NN`(s) this task advances.

Split anything that won't fit ~5 minutes or touches unrelated paths. Reject the trap of one
monolithic "implement the feature" task — that defeats the plan.

Gate: every task has at least one path AND a verification AND a `maps-to`. A task missing any of the
three blocks the plan.

## Phase 3 — Order & MVP slice · gate: BLOCK

Order tasks so each runs only after what it depends on. Flag every dependency explicitly
(`T-07 depends on T-03`). A cycle is a decomposition error — return to Phase 2 and split.

Group the ordered tasks so the **MVP slice** is identifiable: the minimal contiguous task set that
satisfies the spec's core acceptance criteria and is shippable on its own. Everything past the slice
is incremental.

Gate: a complete dependency order with no cycle, and an explicitly marked MVP slice.

## Phase 4 — Coverage proof & write · gate: BLOCK

Cross the ledger against the task set, both directions:

- Every `AC-NN` is covered by at least one task's `covers`. An uncovered criterion blocks — author the missing task.
- Every task advances at least one `AC-NN`. A task that covers nothing is scope creep — cut it or surface it.

Then write the plan to `${CLAUDE_PROJECT_DIR}/.codearbiter/plans/<slug>.md` — `<slug>` matching the
spec — with the `AC-NN` ledger, the ordered task table (id · path(s) · verification · maps-to ·
covers · depends-on), the marked MVP slice, and any out-of-scope item tagged inline `[NEEDS-TRIAGE]`.

Gate: bijective coverage proven — no criterion without a task, no task without a criterion — and the
plan written to disk. This clears the path to execution: `executing-plans` (checkpointed, via
`/feature`) or `subagent-driven-development` (autonomous, via `/sprint`) — each routes every task
through `tdd`. The plan never hands off to `tdd` directly.

### Phase 4-farm extension (only when `--farm` was requested)

After the bijective coverage gate passes and the `.md` plan is written, produce the machine artifact
the farm dispatcher needs — **one MVP slice at a time, not the whole plan up front.** Front-loading
every failing test for the entire plan would be the waterfall this skill otherwise rejects (Phase 3),
and it maximizes the cost of a mid-flight spec change. So the farm artifact is scoped to the **current
slice** (the MVP slice on the first pass; the next contiguous group on later passes). For each task in
the current slice, in dependency order:

1. Route through `tdd` Phase 1 (derive obligations) + Phase 2 (write the failing test). The test file
   must exist on disk and fail before continuing. Record the test file path for this task.
2. Confirm the test is actually failing (run the gate command from `tech-stack.md`; it must exit non-zero).
   A test that passes before implementation means the obligation is wrong — STOP and revisit Phase 2.

Then write `${CLAUDE_PROJECT_DIR}/.codearbiter/plans/<slug>.plan.json` (the current slice's tasks only)
conforming to `${CLAUDE_PLUGIN_ROOT}/tools/plan.schema.json`:

- `meta.name` ← slug
- `meta.repo` ← project name from CONTEXT.md
- `meta.model` and `meta.apiBaseUrl` — **leave unset**. These are written by `subagent-driven-development`'s model research step at dispatch time. Writing them here would bake in a potentially stale selection.
- Per task: `id` ← T-NN (normalized to kebab-case), `description` ← task description,
  `filesInScope` ← path(s) from the task table, `test.path` ← the failing test written above,
  `gate.commands` ← verification command from task table plus full-suite and lint/typecheck from
  `tech-stack.md`, `deps` ← dependency ids (empty array if none), `context` ← a minimal slice of
  relevant types/interfaces (omit if the test file plus task description is self-contained), `maxRetries` ← omit to use the farm default.
- **`gate.commands[0]` MUST be the task's narrow behavioral test** (the command that runs just
  `test.path`), with the full suite and lint/typecheck following. The farm's mutation guard re-runs
  `gate.commands[0]` per mutant; if the first command were the full suite, mutation testing would be
  prohibitively slow.

Validate the JSON against the schema before writing (load the schema from `${CLAUDE_PLUGIN_ROOT}/tools/plan.schema.json` and check). A schema-invalid plan BLOCKS.

Gate: all failing tests written and confirmed failing; `plan.json` written and schema-valid. Both artifacts exist before handing off to `subagent-driven-development`.

## Hard rules

- MUST NOT plan against an absent or unapproved spec — STOP and route back to `/feature`.
- MUST NOT emit a task without an exact path AND a concrete verification step.
- MUST NOT let a task's verification stand in for a `tdd` gate — it maps to a tdd obligation, it does not replace one.
- MUST NOT write the plan while any acceptance criterion is uncovered or any task covers nothing.
- MUST NOT guess a verification command — cite `tech-stack.md` or STOP.
- MUST NOT resolve an ambiguous criterion by guessing — raise a `[CONFIRM-NN]`.
- MUST NOT emit `plan.json` in `--farm` mode without writing and confirming each failing test first.
- MUST NOT set `meta.model` or `meta.apiBaseUrl` in `plan.json` — these belong to the dispatch step.
- MUST NOT proceed with `--farm` if `FARM_API_KEY` is absent — cite `${CLAUDE_PLUGIN_ROOT}/includes/farm.md` and BLOCK.
