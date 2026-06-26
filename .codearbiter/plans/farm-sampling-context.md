# Plan — farm first-time-go accuracy (best-of-N + retry feedback + auto-context)

Spec: `.codearbiter/specs/farm-sampling-context.md`. Each task is test-first via `tdd`.
Status ledger: `PENDING` → `RED` (failing test in) → `GREEN` → `ACCEPTED` (reviewed + verified).
All paths relative to repo root. Tools cwd = `plugins/ca/tools/`.

## Landing structure

**One PR per slice.** Slice 1 lands first (`feat/farm-best-of-n` off `main`); Slice 2 is planned
**after** Slice 1 merges, with the merged code in hand (MVP-slice rule — Slice 2 is stubbed below, not
detailed yet). Each slice: full `tech-stack.md` gate + `farm.js` rebuild + `plugin.json` version bump,
one commit-gate, one PR; the merge decision is surfaced to the user.

---

## SLICE 1 — iterative best-of-N  (`feat/farm-best-of-n`)

### Group F4 — sampling parameters

- **TF4-1** `[PENDING]` — RED: unit test asserting the chat request body includes `temperature` (from
  `FARM_TEMPERATURE`, default `0`) and includes `max_tokens` **iff** `FARM_MAX_TOKENS` > 0. Drives an
  exported body-builder (e.g. `buildChatBody(model, messages)`) or captures the body via the injectable
  fetch seam. Files: `plugins/ca/tools/farm.unit.test.ts`. Verify: fails (no params today). Maps: AC-F4.1, AC-F4.3.
- **TF4-2** `[PENDING]` — GREEN: add `FARM_TEMPERATURE`/`FARM_MAX_TOKENS` to `ENV`; build the request
  body with `temperature` always and `max_tokens` when > 0; usage-summing unchanged. Files: `farm.ts`.
  Verify: TF4-1 green; suite green. Maps: AC-F4.1, AC-F4.2, AC-F4.3.

### Group F2 — iterative retries (worker sees its own prior output)

- **TF2-1** `[PENDING]` — RED: unit test for the prompt/enrichment builder given a `priorAttempt`
  in-scope-files input — assert the rendered prompt contains that prior output labeled read-only
  ("previous attempt (failed)"), passed through `redactSecrets`, and that nothing out-of-scope is
  included. Files: `farm.unit.test.ts`. Verify: fails (builder has no prior-attempt param). Maps: AC-F2.1, AC-F2.3.
- **TF2-2** `[PENDING]` — GREEN: thread an optional `priorAttempt` (in-scope file bodies) through
  `buildEnrichment`/`buildPrompt` via the existing `renderInjectedFile` chokepoint (redaction + cap);
  in `runTask`, capture the failed attempt's **in-scope** `filesWritten` contents BEFORE
  `resetWorktree`, and feed them into the next attempt. Out-of-scope drift is still reset, never carried.
  Files: `farm.ts`. Verify: TF2-1 green; a `RunTaskDeps`-stub test shows the retry prompt carries prior
  in-scope output but not drift. Maps: AC-F2.1, AC-F2.2, AC-F2.3.

### Group F1 — best-of-N, first-green-wins

- **TF1-1** `[PENDING]` — RED: unit test for a shared worker-budget semaphore (extract a small
  `limiter(n)`): with n=2, at most 2 concurrent acquisitions are live across interleaved acquires.
  Files: `farm.unit.test.ts`. Verify: fails (no limiter). Maps: AC-F1.4.
- **TF1-2** `[PENDING]` — GREEN: implement the shared limiter sized to `FARM_CONCURRENCY`; route every
  `worker.apply` through it and refactor the scheduler so task-dispatch **and** per-task sampling both
  acquire from the one budget (no `FARM_CONCURRENCY × FARM_SAMPLES` blow-up). Files: `farm.ts`. Verify:
  TF1-1 green; existing scheduler/`runTask` tests green (back-compat). Maps: AC-F1.4. **(highest-risk task — scheduler refactor; keep the existing single-task concurrency behavior intact at `FARM_SAMPLES=1`.)**
- **TF1-3** `[PENDING]` — RED: unit test for per-attempt sample-and-select — a stubbed multi-sample
  runner returning `[gate-fail, gate-green]` → the green candidate is accepted, losers discarded;
  all-fail → the best failure (first-settled non-green, carrying its in-scope output) is returned to
  seed retry; `FARM_SAMPLES=1` → exactly one candidate (regression path). Files: `farm.unit.test.ts`.
  Verify: fails. Maps: AC-F1.1, AC-F1.2, AC-F1.5.
- **TF1-4** `[PENDING]` — GREEN: implement per-attempt best-of-N in `runTask` — draw
  `min(FARM_SAMPLES, budget)` candidates concurrently into isolated sample worktrees (`farm/<id>-s<k>`)
  cut from integration HEAD, gate each, first green wins (cancel/discard losers, remove their
  worktrees); no-pass → best failure seeds `priorFailure` (composes with F2). `FARM_SAMPLES=1` is the
  unchanged single-candidate path. Files: `farm.ts`. Verify: TF1-3 green; the `FARM_SAMPLES=1`
  regression test (TF-REG) green. Maps: AC-F1.1, AC-F1.2, AC-F1.5. **(high-risk — worktree lifecycle.)**
- **TF1-5** `[PENDING]` — GREEN: auto-bump temperature when `FARM_SAMPLES>1` and `FARM_TEMPERATURE=0`
  (logged note); sum prompt+completion tokens across ALL samples into the `Result`, and surface
  accepted-sample vs total-sample tokens in `farm-report.json` / `farm-results.jsonl`. Files: `farm.ts`.
  Verify: unit tests for the bump (with note) and the token split. Maps: AC-F1.3, AC-F1.6.

### Regression + docs + land

- **TF-REG** `[PENDING]` — RED→GREEN: unit test pinning that `FARM_SAMPLES=1` + `FARM_CONTEXT_AUTO=off`
  + default knobs drives a single `worker.apply` and the same gate→commit→merge sequence as today
  (via `RunTaskDeps` stubs). Files: `farm.unit.test.ts`. Verify: green after TF1-4. Maps: AC-F1.1 / regression hard rule.
- **TF-DOC** `[PENDING]` — docs: `plugins/ca/includes/farm.md` documents `FARM_SAMPLES`,
  `FARM_TEMPERATURE`, `FARM_MAX_TOKENS` (defaults + the N×-tokens-for-acceptance tradeoff + interaction
  with `FARM_CONCURRENCY`). Files: `plugins/ca/includes/farm.md`. Verify: knobs table updated; refs resolve. Maps: AC-F1.7, AC-F4 docs.
- **TF-LAND** `[PENDING]` — build + land: bump `plugins/ca/.claude-plugin/plugin.json` version (+ README
  badge + dated `CHANGELOG.md` section, derived from the ca-scoped window); `npm ci && npm run typecheck
  && npm test && npm run build`; assert `git diff --quiet -- farm.js`; commit-gate; open PR off `main`.
  Maps: cross-cutting hard rules / release invariants.

---

## SLICE 2 — auto-context enrichment (F3)  `[PLANNED AFTER SLICE 1 MERGES]`

Detailed at the next planning pass with Slice 1's merged code in hand (MVP-slice rule). Shape: a RED
test for a 1-level TS/JS import resolver that locates relative-import sources and injects them read-only
through the existing denylist+redaction+cap chokepoint (graceful degrade on unsupported langs); GREEN
the resolver + `buildEnrichment` wiring; `FARM_CONTEXT_AUTO`/`FARM_CONTEXT_MAX_FILES` knobs; docs +
data-egress note; build/bump/land. Trust-boundary gate fires here — surfaced to the user.

---

## Execution order (Slice 1)

One branch off `main`. Test-first throughout. Order: **F4 (TF4-1/2) → F2 (TF2-1/2) → F1 limiter
(TF1-1/2) → F1 best-of-N (TF1-3/4) → F1 finish (TF1-5) → TF-REG → TF-DOC → TF-LAND.** TF1-2 and TF1-4
are the load-bearing tasks (scheduler + worktree lifecycle); everything else is additive. Single final
land: one typecheck/test/build + `git diff --quiet -- farm.js`, one commit-gate, one PR. The morning
Receipt lists the PR + its merge decision.

## Coverage check (Slice 1 ACs → tasks)

F4.1→TF4-1/2, F4.2→TF4-2, F4.3→TF4-1/2; F2.1→TF2-1/2, F2.2→TF2-2, F2.3→TF2-1/2; F1.1→TF1-3/4+TF-REG,
F1.2→TF1-3/4, F1.3→TF1-5, F1.4→TF1-1/2, F1.5→TF1-3/4, F1.6→TF1-5, F1.7→TF-DOC. Regression hard
rule→TF-REG. Release invariants→TF-LAND. ✔  (Slice-2 F3 ACs covered in the Slice-2 plan.)
