# Deep review — `/ca:sprint --farm` (the farm execution backend)

- **Run:** 2026-06-26-farm
- **Scope:** `plugins/ca/tools/farm.ts` (1868 ln) + `includes/farm.md`, `SPRINT.md`,
  `skills/subagent-driven-development/references/farm-dispatch.md`,
  `skills/writing-plans/references/farm-plan.md`
- **Lens:** not a security audit. The brief is *autonomous code-completion accuracy* —
  "first-time-go" acceptance when a non-premium worker writes the code — plus "stop it doing
  things it shouldn't" on the path to agentic cross-model workers, plus token efficiency.
- **Posture going in:** the code is genuinely mature. Batches #132–#134 hardened containment,
  redaction, timeouts, drift, and the circuit breaker. There are **no manufactured security
  findings here** — the shipped blind HTTP worker is safe. The real improvement surface is
  *accuracy* and the *safe path to the agentic worker you actually want to build*.

---

## The one-paragraph thesis

Today's worker is a **single blind chat completion** (`httpWorker`, farm.ts:776) — one shot,
no file reading, no iteration, reset between attempts. The dispatcher wrapped around it is
excellent: a **deterministic gate that is a perfect green/red oracle**, per-task worktree
isolation, a concurrency scheduler, mutation + anti-gaming guards. That combination is the
ideal substrate for two well-known accuracy multipliers the farm **does not yet use** —
*best-of-N sampling against the oracle* and *rich automatic context* — and it is the safe seam
for the *agentic cross-model worker*, which is gated on one missing control (a real sandbox).

---

## Findings (calibrated by impact on first-time-go, not severity-of-defect)

### Track 1 — lift the SHIPPED blind worker's acceptance rate

**F1 — [HIGH] No best-of-N sampling against the deterministic gate.**
`runTask` runs strictly *sequential* attempts: one `worker.apply` per attempt, re-prompt only
on failure (farm.ts:1188–1342). But the gate (`runGate`, farm.ts:258) is a *perfect oracle* and
each task already runs in its own worktree. The canonical way to turn "cheap model, mediocre
first-pass" into "high acceptance" is to draw **K samples in parallel and take the first that
goes green** — the oracle makes selection free of judgment. The scheduler (farm.ts:1738) and
`FARM_CONCURRENCY` already prove the farm can fan out.
- *Impact:* the single biggest available lift in first-time-go, and it spends only the **cheap**
  axis (worker tokens), never premium.
- *Counter-argument:* K× worker tokens and K× gate runs per task. But worker tokens are exactly
  what the farm is designed to spend cheaply, a green-on-sample-2 *avoids* a premium
  re-dispatch (the expensive axis), and N can be adaptive (sample-then-fallback-to-retry).
- *Shape:* `FARM_SAMPLES` (default 1 = today's behavior); draw N concurrently per attempt under a
  sub-budget of `FARM_CONCURRENCY`; first green wins, losers' worktrees discarded; if none green,
  feed the *best* failure into the existing retry loop.

**F2 — [HIGH] The worker never sees its own prior attempt; retry feeds only the gate tail.**
On retry, `resetWorktree` wipes the worker's prior files (farm.ts:1189), `buildEnrichment`
re-reads the *baseline* (farm.ts:1206 → 444), and `priorFailure` carries only the gate stdout
tail (farm.ts:1266). So a failing cheap model **restarts from scratch every attempt** and tends
to oscillate rather than converge.
- *Impact:* wasted retries; tasks that were one fix away from green escalate to premium.
- *Counter-argument:* keeping prior output risks anchoring on a wrong approach. Mitigate by
  labeling it clearly ("your previous attempt, which failed as follows") and retaining the gate
  tail so the model has both the artifact and the error.
- *Shape:* before the inter-attempt reset, stash the prior attempt's **in-scope** file bodies;
  inject them as read-only context next attempt; still hard-reset out-of-scope drift.

**F3 — [HIGH] Enrichment injects in-scope files + the test, but never the read-only context the
impl must conform to.**
`buildEnrichment` (farm.ts:444–486) injects the test source and the current contents of
`filesInScope` only. The comment is explicit: "best-effort direct context — no deep import
resolution" (farm.ts:296–301). Everything the implementation must *call into* — imported types,
interfaces, sibling modules, the DTO/serializer it must match — is absent unless Claude
hand-writes it into the optional `context` field (`farm-plan.md`). A cheap model then **guesses
signatures**, which surfaces as a gate failure or as drift.
- *Impact:* a top root-cause of cheap-model failure; *also* the ask-#1 lever — auto-context means
  Claude writes far less hand-authored `context`, cutting premium token burn at plan time.
- *Counter-argument:* more bytes cross the trust boundary (cost + sovereignty). Bounded by the
  existing `FARM_ENRICH_MAX_BYTES` cap (farm.ts:412) and span-aware redaction (farm.ts:371),
  which already govern outbound content; this rides the same chokepoint.
- *Shape:* resolve the test's imports + the type/interface files referenced by `filesInScope`,
  inject them **read-only** through `capInjected`, ranked by relevance before truncation.

**F4 — [MEDIUM] No sampling parameters sent.**
`callApi` posts `{model, messages}` only (farm.ts:652–655) — no `temperature`, `max_tokens`, or
`stop`. There is no diversification across retries, and completion length is unbounded (cost +
truncation risk against the 120 s request budget).
- *Shape:* low temperature on attempt 1, raised on retries (and the *required* enabler for F1's
  parallel samples — N identical temperature-0 calls are wasted); cap `max_tokens`.

**F5 — [MEDIUM] Whole-file rewrite format.**
The prompt demands "complete file content here" per file (farm.ts:522–534). To change three lines
of a large in-scope file the worker must regenerate the whole file — high completion-token cost
and a real regression/drift surface (it silently drops unrelated code, caught only by burning a
gate attempt).
- *Counter-argument:* whole-file is the *safe* apply path; diffs fuzz-fail. Keep whole-file for
  new files; offer a search/replace block mode for edits to existing large files.

**F6 — [LOW] The response-format example is hard-coded `typescript`.**
`buildPrompt` shows a ```` ```typescript ```` example fence (farm.ts:529) regardless of project
language; a Python/Rust/Go worker is anchored on the wrong tag. Derive it from `tech-stack.md`
language threaded via `plan.meta`.

**F7 — [LOW] Canary measures only the smallest no-dep task.**
Model selection ranks candidates on the fewest-files, no-deps task (farm.ts:1597–1600) — a weak
proxy for plan-wide capability; a model that clears a trivial slice can still fail the real work.
Optionally probe the median-complexity (or hardest no-dep) task, configurable for canary cost.

### Track 2 — the agentic cross-model worker you want to build ("stop it doing things it shouldn't")

**F8 — [HIGH, roadmap-gating] The non-reporting-worker escape is unguarded — this is the
prerequisite control before any agentic worker ships.**
`postApplySweep` only inspects the worker's **reported** writes (farm.ts:831–851); `checkDrift`
only sees paths **inside** the worktree (farm.ts:789–805). The shipped `httpWorker` reports its
writes faithfully, so today is fully covered — and the code already says so honestly
([NEEDS-TRIAGE], farm.ts:819–825). But the agentic/cross-model worker the brief is about can hold
file tools and write **outside `cwd` without reporting it**, evading *both* guards.
- *Impact:* containment for an agentic worker cannot rest on the worker's honesty. This is THE
  gating safety item for Track 2, not an optional hardening.
- *Counter-argument:* none — the file itself defers the robust fix to "a process-level sandbox /
  cwd-jail," which is exactly right.
- *Shape:* execute the worker through the repo's **ca-sandbox** (cwd-jail + network limited to the
  model endpoint), so containment is OS-enforced. The existing post-hoc gate/drift/mutation guards
  remain, but stop being the *only* containment.

**F9 — [MEDIUM] Prompt "do not" instructions read as enforcement but are not.**
"Do not run git. Do not install global packages." (farm.ts:517) is inert for the blind worker
(it can't run anything) and non-binding for an agentic worker (it's prose). Keep as guidance, but
document that the *binding* controls for agentic workers are the sandbox (F8) + the post-hoc
guards — not the prompt line.

---

## Answer to ask #1 — "decrease the tokens to build the .ts script for farm"

`farm.ts` is a **static, committed tool** — it is not regenerated per run, so there is no
per-run token cost to "build" it. Premium (Claude) token spend in a `--farm` run lives entirely
in *plan time*: deriving obligations, writing each failing test, and emitting `plan.json` +ahead
the hand-authored `context` field. The levers that actually reduce that spend:
- **F3 auto-enrichment** removes most hand-written `context` (the largest discretionary chunk).
- The **one-MVP-slice-at-a-time** rule (`farm-plan.md`) already caps up-front test authoring —
  keep it; do not front-load the whole plan's tests.

So: as you suspected, there's little to win on "building the .ts" itself — the win is on the
*plan-authoring* tokens, and F3 is that win. Per your steer, the focus stays on Track 1/Track 2.

---

## The two step-change recommendations (if you do nothing else)

1. **F1 best-of-N against the gate** — the architecture is almost uniquely built for it (perfect
   oracle + worktree isolation + concurrency). Largest first-time-go lift, cheap-token-only.
2. **F3 automatic read-only context** — kills the #1 cheap-model failure cause (guessed
   signatures) *and* cuts premium plan-time tokens. Reuses the existing cap+redaction chokepoint.

And the gating item for the future you're excited about: **F8 sandbox the worker** before any
agentic/cross-model worker leaves the seam. The agentic worker subsumes F2/F3 (it reads and
iterates itself) but is unsafe without F8.

## Decisions deferred to you (not auto-resolvable)

- Which of Track 1 (F1/F2/F3/F4) to build first, and at what `FARM_SAMPLES`/budget defaults.
- Whether Track 2 (agentic worker) is in scope now — it changes CONFIRM-05's promotion bar.
- F5 (diff response mode) and F7 (canary breadth) are real but lower-priority; defer unless cheap.
