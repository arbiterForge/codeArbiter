# Spec — farm: pluggable execution backend (v1)

status: APPROVED — 2026-06-14, by repo owner (after blind third-party spec review)
slug: farm-pluggable-backend
created: 2026-06-14
lane: full
relates-to: [CONFIRM-05] (Feature Forge promotion bar for `--farm`) — this feature *produces evidence*
toward that bar (lower escalation rates on real runs); it does **not** resolve it. Promotion stays a
separate owner decision.

## Problem

The `/ca:sprint --farm` backend (`plugins/ca/tools/farm.ts`) is well-engineered and well-tested at the
mechanism level, but its single worker implementation is a **blind, single-shot HTTP chat call**: the
worker is told *where* the failing test is but never given its contents, cannot read sibling files, and
emits whole files from a description. That maximizes avoidable escalations on anything past leaf-node
tasks, and it hard-couples the harness to one execution style — blocking the obvious future where a
**premium or agentic** worker does the same work behind the same gates. Secondary friction: sibling
tasks with overlapping file scope collide at merge time and escalate; and review (Phases 3–5) only
begins after the *entire* farm run finishes.

## Goals (this slice)

A coherent first slice that (a) lands the structural spine, (b) takes the biggest escalation-rate win,
and (c) shapes — but does not build — cross-model family support.

1. **Worker interface (item 1).** Extract a `Worker` seam so the safety gates wrap *any* worker
   implementation; the current HTTP-chat path becomes one implementation. Behavior-preserving.
2. **Prompt enrichment (item 2).** Stop sending the worker in blind — inject the read-only test source
   and current in-scope file contents, bounded and secret-safe.
3. **Scope-aware scheduling (item 4).** Treat overlapping-scope tasks as implicit dependencies and
   regenerate-on-conflict instead of immediate abort+escalate.
4. **Pipeline the review handoff — streaming rail (item 5).** Emit per-task results incrementally and
   consume them in completion order (Phase 3 + Phase 5 per green; Phase 4 stays the once-per-scope
   barrier by design).
5. **Reframe positioning.** "Cost arbitrage / cheap Zen workers" → "pluggable execution backend
   (cheap / premium / agentic)." Prose only; the name `farm` and `Feature Forge preview` status are
   preserved (§0.1 terminology lock).

## Non-goals / roadmap (captured, deliberately deferred)

- **Cross-model build (item 3):** a second provider (OpenAI/GPT-5.5), the cheap→premium escalation
  ladder, per-task cost telemetry. Designed-for here (Goal 1 + AC-02), built later — it pulls new-secret
  handling, supply-chain vetting, and the sovereignty trade-off into hard-gate territory.
- **Temporal review overlap:** running farm.js in the background so review executes *while* farm grinds.
  This slice lays the streaming rail that enables it; backgrounding is the follow-up.
- **Item 6 grab-bag:** schema-validated structured output (vs fence-scraping), adversarial second-model
  verify on green-with-warning tasks, budget-scaled depth, per-task resume/journaling, live progress
  streaming. Each is independently shippable on top of the Worker seam.

## Decisions & trade-offs (resolve at approval; object here if wrong)

- **D1 — Governed feature, not /ca:dev.** Lands via PR with version bump + CI, like PRs #55–59.
- **D2 — Phase 4 stays a barrier.** Pipelining overlaps Phase 3 + Phase 5 only; the combined-diff
  quality review remains once-per-scope, per `subagent-driven-development` Phase 4's stated rationale.
- **D3 — Streaming rail this slice; backgrounding later.** farm.js stays foreground; it gains
  incremental emission so the data model is pipeline-ready and consumption is completion-ordered. The
  headline "review while farm runs" latency win needs backgrounding and is roadmap.
- **D4 — Regenerate-on-conflict spends one retry from the existing `maxRetries` budget**; exhaustion
  escalates exactly as today. No new unbounded loop.
- **D5 — Enrichment is bounded + secret-safe by default.** More repo content now leaves the trust
  boundary to the third-party endpoint; that is a real new exposure and must be guarded (AC-05).
- **D6 — The `Worker` seam owns *apply*, not just the *call* (reviewer-surfaced; confirm at approval).**
  The interface returns/produces files written **into the worktree**, with the HTTP impl doing
  `extractFileBlocks` + write internally — so an agentic/premium worker that writes its own files fits
  the same seam later. Consequence: containment (`isInside`) and the read-only-test guard move from
  inside `runWorker`'s write loop to a **post-apply sweep** in `runTask` that runs regardless of worker
  type. This is load-bearing for item-3 readiness and expensive to re-cut, so it shapes where AC-01 cuts
  the seam. *If rejected,* AC-01 cuts a thinner call-only seam and item-3/agentic becomes a larger
  follow-up.
- **D7 — Two artifacts, one source of truth on settlement.** `.farm/farm-results.jsonl` is the
  incremental, append-only record of settled tasks (drives completion-order consumption);
  `farm-report.json` (always written in the `finally`, even on abort) remains the authoritative final
  summary. On a circuit-breaker abort or crash, the consumer reconciles against `farm-report.json`, not
  the partial stream.

## Acceptance criteria

Worker interface (item 1)
- **AC-01** — `farm.ts` defines a `Worker` interface and refactors the existing HTTP-chat author into
  one implementation behind it; `runTask` depends on the interface, not on `callApi` directly. Proven
  behavior-preserving: the entire existing `farm.test.ts` + `farm.unit.test.ts` suite passes unchanged.
- **AC-02** *(design-for cross-model)* — the interface receives the resolved model/config, and an
  optional `task.model` is added to `plan.schema.json` + the `Task` type, resolved as
  `task.model ?? meta.model`. Absent → identical current behavior. No second provider is implemented.
  Note for the planner: the task object in `plan.schema.json` is `additionalProperties: false`, so the
  new field must be declared in the task `$defs` or schema validation (`writing-plans` Phase 4-farm,
  SKILL.md:111) will reject it. Also reconcile, or explicitly leave, the pre-existing divergence
  between the schema's kebab-case `id` pattern and farm.ts's broader `SAFE_TASK_ID` — do not widen it
  silently.

Prompt enrichment (item 2)
- **AC-03** — the outgoing worker request includes the read-only source of `task.test.path`.
- **AC-04** — the outgoing worker request includes the current contents of in-scope files that already
  exist on disk in the worktree (direct imports best-effort). A test asserts the test source AND an
  existing sibling file's contents appear in the request body.
- **AC-05** — injected context is byte-capped (configurable env; default chosen with
  `FARM_REQUEST_TIMEOUT_MS` and token spend in mind) and run through a **new** redaction pass over the
  `tech-stack.md` secret-pattern set (`api[_-]?key|token|secret|password|BEGIN.*PRIVATE|sk-ant`,
  case-insensitive); matches are redacted/omitted before transmission. (There is no existing in-code
  secret sweep to reuse — the repo's sweep is the manual/hook layer; this is new code.) A test plants a
  secret-shaped string in an in-scope file and asserts it is NOT in the outgoing request body.

Scope-aware scheduling (item 4)
- **AC-06** — a task whose `filesInScope` intersects an *unfinished* sibling's is **removed from
  readiness** (not merely merge-serialized) until that sibling is `green` and merged — i.e. it does not
  appear in `ready()` and is not dispatched, so when it finally cuts its worktree it cuts from the
  post-merge integration HEAD. This is derived ordering, not a declared `deps` edge (so it cannot create
  a plan-validation cycle); mutual overlap between two ready tasks is broken deterministically by task
  `id`. Test: two scope-overlapping tasks both reach green with no merge conflict, and the second's
  worktree contains the first's merged change.
- **AC-07** — on a merge conflict against integration (the residual case where overlap wasn't caught,
  e.g. a shared import edit outside `filesInScope`), the task resets to the new integration HEAD and
  re-runs the worker (consuming one retry per D4) before escalating, rather than immediate
  abort+escalate. Implementation note: this requires moving the post-loop merge step (farm.ts:727–747)
  into the attempt loop so a merge failure can re-enter regeneration — not just adding a branch. Test: a
  forced same-file conflict yields a regeneration attempt, not an instant escalate.

Pipeline — streaming rail (item 5)
- **AC-08** — `farm.js` emits a per-task result the moment each task settles (append to
  `.farm/farm-results.jsonl`), in addition to the final `farm-report.json`. Test: after a two-task run
  the stream holds both results in completion order.
- **AC-09** — `farm-dispatch.md` + `subagent-driven-development` document the contract: consume results
  in completion order, run Phase 3 + Phase 5 per green as it lands, Phase 4 preserved as the
  once-per-scope combined-diff barrier (D2). Temporal overlap noted as roadmap. `check-plugin-refs.py`
  passes.

Reframe (positioning)
- **AC-10** — `farm.md`, the `ORCHESTRATOR.md` `/sprint --farm` section, `SPRINT.md`, and
  `farm-dispatch.md` reframe the backend as pluggable (cheap / premium / agentic); the term `farm` and
  the `preview` status are preserved. No reference graph breaks (`check-plugin-refs.py`).

Cross-cutting (release invariants, from `tech-stack.md`)
- **AC-11** — `farm.js` is rebuilt from `farm.ts` with no stale build (`git diff --quiet -- farm.js`
  clean after `npm run build`); `npm run typecheck` + full `npm test` green; `plugin.json` `version`
  bumped and kept in sync across `plugin.json`, the README badge, and a dated `CHANGELOG.md` section.

## Risks / security

- **Trust-boundary data exposure (primary).** Enrichment increases what is sent to the third-party Zen
  endpoint. Mitigated by AC-05 (cap + secret sweep). Phase 4 MUST dispatch `security-reviewer`; the
  change is security-relevant.
- **Refactor regression.** The Worker extraction is behavior-preserving and fully covered by the
  existing suite (AC-01) — the suite is the safety net.
- **Scheduling deadlock/starvation.** Scope-overlap ordering is *derived at schedule time* (a readiness
  filter), never written as a `deps` edge — so it cannot create a plan-validation cycle, and mutual
  overlap is broken deterministically by `id` (AC-06). Starvation is bounded because every overlap
  resolves the moment the blocking sibling settles.
- **Duplicated file reads.** `antiGamingCheck` (farm.ts:419) and `mutationCheck` (farm.ts:552) already
  read `test.path` and in-scope files; enrichment (AC-03/04) reads the same. The planner should factor a
  shared read helper rather than grow a parallel read path.

## Out-of-scope items noticed

- [NEEDS-TRIAGE] `farm.js` backgrounding for true temporal review overlap (roadmap).
- [NEEDS-TRIAGE] cross-model second provider + cost telemetry + escalation ladder (item 3 roadmap).
- [NEEDS-TRIAGE] item-6 grab-bag (schema output, adversarial verify, budget depth, journaling).
