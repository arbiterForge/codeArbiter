# Sprint spec — farm first-time-go accuracy (best-of-N + retry feedback + auto-context)

**Status:** approved (Phase 1 gate) — 2026-06-26, user (brennonhuff@gmail.com); F2 kept in Slice 1
**Mode:** `/ca:sprint` (premium subagent path — NOT `--farm`; we are improving the farm tool itself)
**Author attribution:** user (brennonhuff@gmail.com), 2026-06-26
**Origin:** `docs/reports/2026-06-26-farm/report.md` (deep review). Findings F1/F3/F4/F2 in scope; F8
descoped to an ADR by user decision at the gate; F5/F6/F7 deferred.
**Surface:** `plugins/ca/tools/farm.ts` (+ rebuilt `farm.js`), `plugins/ca/tools/farm.unit.test.ts`,
`plugins/ca/includes/farm.md`, `plugins/ca/.claude-plugin/plugin.json` (version bump).
**Landing:** one PR per slice (Slice 1, then Slice 2); MVP-slice order, plan the next slice with the
merged code in hand.

**Thesis.** The farm's worker is a single blind chat completion wrapped in an excellent deterministic
gate (a perfect green/red oracle), worktree isolation, and a concurrency scheduler. That substrate is
ideal for two accuracy multipliers it does not yet use — **best-of-N sampling against the oracle** and
**rich automatic context** — plus making **retries actually iterative**. None of these touch the
premium token axis; the cost is the cheap worker axis the farm exists to spend.

---

## Slice 1 (MVP) — iterative best-of-N against the gate

Three tightly-coupled changes to the worker-call + retry path. Build order within the slice:
F4 (params) → F2 (retry feedback) → F1 (best-of-N), since F1's sampling needs F4's temperature and
composes with F2's feedback loop.

### F4 — send sampling parameters (`callApi`)

**Root.** `callApi` posts `{model, messages}` only (farm.ts:652) — no `temperature`, no `max_tokens`.
No diversification is possible across samples/retries, and completion length is unbounded.

- **AC-F4.1** — `callApi` includes `temperature` (from `FARM_TEMPERATURE`, default `0`) in the request
  body, and `max_tokens` when `FARM_MAX_TOKENS` > 0 (default `0` = omit, preserving today's behavior).
- **AC-F4.2** — Token-usage accounting (`prompt_tokens`/`completion_tokens` summing) is unchanged.
- **AC-F4.3** — The request-body construction is unit-testable without network (assert `temperature`/
  `max_tokens` presence and values given env), via the existing injectable-fetch seam or a small
  exported body-builder.

### F2 — make retries iterative (the worker sees its own prior attempt)

**Root.** On retry, `resetWorktree` wipes the prior files (farm.ts:1189), `buildEnrichment` re-reads
the *baseline* (farm.ts:1206), and only the gate tail feeds `priorFailure` (farm.ts:1266). The worker
restarts from scratch each attempt and oscillates instead of converging.

- **AC-F2.1** — On a retry (attempt > 1, or after a failed best-of-N round), the worker prompt includes
  the **prior attempt's own in-scope file output** — the files it wrote that failed the gate — labeled
  read-only as "your previous attempt (failed)", in addition to the existing gate-failure tail.
- **AC-F2.2** — Out-of-scope drift from the prior attempt is still hard-reset and never carried
  forward; only the prior **in-scope** output is re-shown as context.
- **AC-F2.3** — Prior-attempt context flows through the SAME redaction + `FARM_ENRICH_MAX_BYTES` cap
  chokepoint as all other injected content (no new boundary path).

> *Added at review (was a "supporting" HIGH finding, not in the originally-named set). It directly
> amplifies F1 — without it, the retry after a failed sampling round restarts blind. Cut it for a
> tighter slice if you prefer; flagged for your call at the gate.*

### F1 — best-of-N sampling, first-green-wins

**Root.** `runTask` runs strictly sequential attempts: one worker call per attempt (farm.ts:1188).
The gate is a perfect oracle, so N parallel cheap samples with first-green-wins is a step-change in
first-time-go at linear cheap-token cost.

- **AC-F1.1** — New env `FARM_SAMPLES` (default `1`). With `FARM_SAMPLES=1`, each attempt performs
  exactly one worker completion and the task lifecycle is **behaviorally identical to today** (single
  candidate, gated, merged) — the regression guard.
- **AC-F1.2** — With `FARM_SAMPLES=N>1`, each attempt draws up to N candidate implementations
  **concurrently**, each applied + gated in an isolated per-sample worktree cut from the same
  integration HEAD as the task. The **first candidate to pass the full gate** is accepted and merged;
  remaining in-flight samples are cancelled/discarded.
- **AC-F1.3** — When `FARM_SAMPLES > 1` and `FARM_TEMPERATURE` is `0`, the temperature is auto-bumped
  to a diversifying default (with a logged note) — N identical deterministic samples is a misconfig.
- **AC-F1.4** — Total concurrent worker calls (across all tasks AND their samples) never exceed
  `FARM_CONCURRENCY` — sampling shares the global worker budget via a semaphore; it does not multiply
  it. (No `FARM_CONCURRENCY × FARM_SAMPLES` blow-up.)
- **AC-F1.5** — If no sample passes the gate in an attempt, the best failure (first-settled non-green,
  carrying its in-scope output per F2) seeds `priorFailure` and the existing retry loop runs as today —
  sampling **composes with** retries, it does not replace them.
- **AC-F1.6** — Per-task token spend in `farm-report.json` / `farm-results.jsonl` sums ALL samples
  (prompt+completion) and distinguishes accepted-sample tokens from total-sample tokens, so best-of-N's
  real cost is visible, never hidden.
- **AC-F1.7** — `farm.md` documents `FARM_SAMPLES` (the N× worker-token-for-higher-acceptance
  tradeoff), default 1, and its interaction with `FARM_CONCURRENCY` and `FARM_TEMPERATURE`.

---

## Slice 2 — automatic read-only context enrichment (F3)

**Root.** `buildEnrichment` injects only the test + in-scope files (farm.ts:444); the imported types/
interfaces the impl must conform to are absent unless Claude hand-writes the `context` field. The cheap
model guesses signatures → gate-fail/drift.

- **AC-F3.1** — Enrichment resolves the **direct imports** of the test file and of existing in-scope
  files, locates the referenced sources in the worktree, and injects their contents **read-only**.
- **AC-F3.2** — Resolution is language-scoped: TS/JS `import … from '…'` and `require('…')` (relative
  specifiers) are resolved this slice; unsupported languages or unresolvable specifiers degrade
  **silently** to today's behavior — no crash, hand-`context` still works.
- **AC-F3.3** — Import-following is bounded to **1 level** (direct imports only, no transitive walk).
- **AC-F3.4** — Auto-resolved context uses the SAME chokepoint as existing injected files: the
  secret-bearing-filename denylist (never read), span-aware redaction, and the `FARM_ENRICH_MAX_BYTES`
  total cap. Test + in-scope files retain budget priority; auto-context fills the remainder and is the
  first to be truncated/dropped.
- **AC-F3.5** — Auto-resolved files are injected read-only and are **NOT** added to `filesInScope`; the
  drift guard and write-allowlist are unchanged (the worker still cannot write them).
- **AC-F3.6** — A knob gates it: `FARM_CONTEXT_AUTO` (default `on`) and a `FARM_CONTEXT_MAX_FILES` cap;
  `off` → exactly today's enrichment.
- **AC-F3.7** — `farm.md` documents auto-context: language scope, the read-only/denylist/cap
  guarantees, and the data-egress note (more repo content crosses the boundary; cap + redaction +
  `FARM_MODEL` sovereignty knob are the controls).

---

## Cross-cutting hard rules (apply to every task)

- **Regression guard:** `FARM_SAMPLES=1` + `FARM_CONTEXT_AUTO=off` + default knobs MUST be behaviorally
  equivalent to today. A unit test pins the single-sample path.
- **Trust-boundary touch (F3):** Slice 2 widens the repo content crossing to the third-party endpoint.
  The trust-boundary / security-reviewer gate WILL fire in execution — this is expected and surfaced,
  not hidden. The existing redaction, secret-filename denylist, and `FARM_ENRICH_MAX_BYTES` cap are the
  controls and **MUST NOT be weakened**; a task that weakens any of them is a hard-gate STOP.
- `assertSecureBaseUrl` and the secret-redaction/denylist paths are not weakened by any task.
- Every task is test-first via `tdd`; the failing test is written and shown red before impl.
- Every PR's gate runs the full `tech-stack.md` tools sequence: `npm ci && npm run typecheck &&
  npm test && npm run build`, then `git diff --quiet -- farm.js` (a stale bundle blocks).
- `plugins/ca/**` changed → bump `plugins/ca/.claude-plugin/plugin.json` version (+ README badge +
  CHANGELOG), per the release invariant; derive the bump from the ca-scoped commit window only.
- `/ca:sprint` never merges and never discards — each slice's PR merge decision is surfaced to you.
- Every non-hard-gate auto-decision is logged to `.codearbiter/sprint-log.md` with a confidence flag.

## Out of scope (noted, not done)

- **F8 — worker process-sandboxing** → its own ADR + threat-model for agentic-worker containment,
  designed against the real agentic worker when Track 2 is scoped (ties to CONFIRM-05). `ca-sandbox`'s
  Docker/clone-into-container model does not fit farm's host-worktree architecture; forcing it now would
  add a Docker dependency to a preview feature to protect a consumer that does not yet exist. *(User
  decision at the Phase 1 gate, 2026-06-26.)*
- **F5** — diff/search-replace worker response mode for large-file edits (efficiency; whole-file stays
  the safe default).
- **F6** — language-derived response-format example fence (currently hard-coded `typescript`).
- **F7** — canary breadth (median/hardest no-dep task instead of smallest).
- The non-reporting-worker path-containment sandbox (existing `[NEEDS-TRIAGE]`, farm.ts:819) — folded
  into the F8 ADR.
