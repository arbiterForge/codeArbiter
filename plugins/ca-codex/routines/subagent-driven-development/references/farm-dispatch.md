# Farm dispatch — reference for subagent-driven-development's farm path

Loaded from `subagent-driven-development` Phase 2 when `<slug>.plan.json` exists alongside the `.md`
plan. The farm is a pluggable execution backend — its value is deterministic, gated, parallel, isolated
execution. The farm path replaces only the *authoring* step for the plan's tasks — a worker implements
under hard gates instead of a premium subagent. The `Worker` seam admits cheap, premium, and agentic
implementations; only the cheap HTTP-chat worker ships today (premium and agentic are what the seam is
designed for — roadmap, not built). It does **not** replace review: every task the farm reports green is
still routed through Phases 3, 4, and 5 before acceptance. Swapping the worker only changes who *writes*
the code, never whether it is *reviewed*. See `${CLAUDE_PLUGIN_ROOT}/includes/farm.md` for setup.

## Step 1 — Model selection

If `FARM_MODEL` env var is set, use it directly and skip selection. Otherwise, prefer a **measured**
choice over web hearsay:

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

## Step 2 — Farm dispatch

Invoke the farm dispatcher:

```
node "${CLAUDE_PLUGIN_ROOT}/tools/farm.js" "<project-root>/.codearbiter/plans/<slug>.plan.json"
```


Run it with cwd set to `<project-root>` (the dispatcher resolves `.farm/` and git worktrees
against the current directory). It runs tasks concurrently (up to `FARM_CONCURRENCY`, default 4),
enforces gates and a zero-token anti-gaming guard, and writes to `<project-root>/.farm/`:
- `farm-report.json` / `farm-report.md` — per-task status, attempts, files, worker token spend, warnings
- `farm-results.jsonl` — the incremental stream: one `Result` JSON object per line, appended the moment
  each task settles (drives completion-order consumption — see Step 2.6)
- `diffs/<task-id>.patch` — the actual change per task, for audit

Exit code 0 = all green; exit code 2 = some tasks escalated, blocked, or the run was aborted.

## Step 2.5 — Circuit-breaker abort

If `farm-report.json` has `aborted: true`, the dispatcher tripped its escalation-rate breaker — the
chosen model is likely not capable of this slice. This is a hard-gate surface: STOP and tell the user,
recommending the premium path or a different `FARM_MODEL`. Do not silently re-dispatch every task to
premium Phase 2 (that defeats the backend's purpose and hides a bad signal).

## Step 2.6 — Streaming consumption contract

The dispatcher writes two artifacts (D7): the incremental `farm-results.jsonl` stream and the final
`farm-report.json` summary. The escalation/acceptance handler (Step 3) MUST consume the stream in
**completion order** — read `farm-results.jsonl` line by line (one `Result` JSON object per line) and
process each task the moment it settles, rather than waiting to parse only the final report. Each
`green` task is routed through **Phase 3 (spec-compliance) + Phase 5 (verification)** as it lands.

- **Per-green-task = Phase 3 + Phase 5 only.** Only the spec-compliance and fresh-verification reviews
  run per green task as it streams in.
- **Phase 4 stays a once-per-scope barrier.** The quality review (Phase 4) MUST NOT be pipelined per
  task — it still runs ONCE over the combined diff of the whole scope, after every task has cleared
  Phase 3 and Phase 5. The streaming rail moves Phase 3 + Phase 5 earlier; it does NOT move Phase 4.
- **`farm-report.json` is authority on abort (D7).** `farm-report.json` is always written in the
  dispatcher's `finally` — even on a circuit-breaker abort or crash — and remains the AUTHORITATIVE
  final summary. On an abort or crash, reconcile settled-task state against `farm-report.json`, NOT the
  partial `.jsonl` stream. The stream is an append-only progress feed; the report is the source of truth.
- **Temporal overlap is roadmap, not today.** `farm.js` runs in the foreground, so the consumer
  processes the stream in completion order *after* the run returns — true *temporal* overlap (running
  review WHILE the farm is still executing) requires backgrounding `farm.js` and is explicitly a
  future/roadmap item. The streaming rail is the enabling primitive, not the full overlap yet.

## Step 3 — Escalation handler (Phase 2.5)

Consume `farm-results.jsonl` in completion order (Step 2.6); `farm-report.json` is the authoritative
reconciliation source on abort. For each result:

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
