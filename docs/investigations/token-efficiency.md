# Investigation Plan — Stretching the Max Subscription Across arbiter Use

## Context

**Goal:** get more out of the Max subscription across **all** arbiter use — the everyday interactive
turns (`/ca:fix`, `/ca:feature`, `/ca:refactor`, `/ca:debug`, `/ca:review`, …) *and* the nightly
`/ca:sprint` ritual (start a long sprint, go to bed; it grinds low-risk turns autonomously and
exercises the plan allowance). The currency is usage-limit headroom and context quality, not dollars.
The levers below are deliberately cross-cutting: model tiering, pruning, reviewer yield, and `/clear`
discipline each pay off on every fan-out command during the day, not only inside a sprint. `/sprint`
matters here only as the single longest, highest-burn *session class* — the place a regression shows
up first — not as the sole target.

**Why this plan exists, and why it differs from the input brief.** The input brief was written by
Claude-for-desktop with only a *general* idea of what arbiter is, so several of its mechanics are
wrong. This plan re-grounds every line against the actual plugin at
`/home/user/codeArbiter/plugins/ca/`. Two corrections drive everything below:

1. **Model tier is the dominant lever, and it applies to the premium path you use most.** Confirmed
   from lived experience: Opus ≫ Sonnet ≫ Haiku in burn (Fable could drain a 5-hour window in ~17
   minutes). The ca agents currently set **no `model:`** in frontmatter, so they all *inherit the
   session model* — when you're on Opus, your reviewers, your finding-triage, your checkpoint-doc
   writer are **all Opus**, including mechanical work that doesn't need it. Pinning cheap/mechanical
   subagents to a lower tier is a **config lever, not a code rewrite** — and it's independent of farm.
2. **`--farm` is a supplement, not the savior** — "a little extra juice." Its shape is: Claude spends
   its (subscription) tokens on **thinking** — specs, failing tests, review judgment — while cheap
   external models do the **labor** of making tests pass. It moves only the *authoring grunt-work* off
   the Anthropic pool, behind the same gates. It stays a *tracked secondary experiment*; you'll be in
   normal premium mode a lot even once farm works, which is exactly why lever #1 is primary.

**Deliverable:** a representative measurement of where sprint burn concentrates, then a small set of
*user-gated* changes — subagent model tiering, statusline on, pruner `dry`→`on`, context discipline —
each justified by measurement, plus a go/no-go read on `--farm`.

---

## Ground-truth corrections to the brief (read this first)

| Brief claim | Reality in the code / verified | Consequence for the plan |
|---|---|---|
| §3 Downgrade `backend-author` via a per-agent `model:` field that's already there | **No `model:` field is set on any of the 16 agents** (`plugins/ca/agents/*.md`) — they inherit the session model. But Claude Code **does support** `model:` in agent frontmatter (`sonnet`/`opus`/`haiku`/`fable`/full-id/`inherit`, default `inherit`). | The field isn't *set*, but the lever is real and supported. Becomes **Step 2 (primary)** — not a dead end. |
| (implicit) downgrading subagents saves subscription | Confirmed by user experience: lower tier = materially less burn. Docs don't detail Max's all-model vs Sonnet-only weekly-cap accounting, but raw 5-hour-window + active-compute burn drops regardless. | Tiering directly buys session/weekly headroom. Sonnet possibly *also* draws a separate weekly bucket (unconfirmed bonus). |
| §3 "cheaper tier for authors" is the only/main saver | **`--farm` is a *supplement*:** it offloads authoring *grunt-work* to an external OpenAI-compatible endpoint (`FARM_API_KEY`, OpenCode Zen) — a billing source separate from the Max pool — while Claude still spends its tokens on specs/tests/review (`includes/farm.md`, `SPRINT.md`). | Not the savior; "extra juice." `preview`/off/"not validated on real runs" (`CONFIRM-05`). **Secondary, tracked.** |
| §4 Pruner may do "gate-aware retention" | Pruner **exists** (`hooks/_prunelib.py`, `commands/prune.md`) but is **recency-only**: protects the K most recent tool turns + latest assistant msg, trims older bulk. **Not** gate-aware. Ships **off**. | §4 "is it gate-aware?" is answered (no). Its value is *session lifetime at resume/compaction*, provable via its `dry` metrics log. |
| §4 Pruner trims the *live* context mid-sprint | Gains land at `--resume`/restart/next compaction, **not the current turn** (`commands/prune.md:12`). | Pruner lets a sprint *resume* further; it doesn't lower live burn mid-turn. |
| §2 MCP residency / resident overhead is a primary line | **No MCP infra or `ENABLE_TOOL_SEARCH` in the plugin.** Standing context is **exactly one file** — `ORCHESTRATOR.md` on `arbiter: enabled`; all skills/agents/routing load **on demand per reached node** (`docs/architecture.md` "Context minimization"; `docs/patterns/lazy-load-bundles.md`). | No resident footprint to trim. Cost is per-*session* accumulation (interactive or sprint) + authoring, not residency. |
| §5 Sprint fans out the full reviewer set on every change | Quality review runs **once per scope** over the combined diff, **reviewers selected by what the diff touches** "by path matrix" (`subagent-driven-development/SKILL.md` Phase 4; `docs/architecture.md`). | Fan-out already engineered down. Re-frame §5 as a *yield* measurement that also feeds tiering. |
| §6 "instrument visibility / first-pass rate" needs building | `/ca:statusline` already renders rate limits, context, tokens, API-equiv cost, per-call burn. Farm writes per-task attempts/escalations to `.farm/farm-report.json`. | Instrumentation exists; turn it on and sample. |

---

## The investigation, in priority order

### Step 0 — Confirm the billing source (gate; invalidates everything if wrong)
- Verify subscription auth, not a shadowing `ANTHROPIC_API_KEY`: `env | grep -i ANTHROPIC` + `/status`.

### Step 1 — Turn on visibility, then sample (zero risk, prerequisite for all measurement)
- `/ca:statusline install` (it surfaces the resolved command and asks before editing
  `~/.claude/settings.json` — backing script `hooks/wire-statusline.py`).
- **Sample across several sessions of both kinds** — ordinary daytime interactive sessions *and* the
  nightly sprint — not one day (the brief's basis was a single day the tool flagged as "not a
  breakdown"). Record per session: context-bar peak, cumulative tokens, per-call burn, which
  5-hour/weekly cap bites first (`/status`, `/usage`). Note which command classes fan out subagents
  most — that's where Step 2 pays off.
- Proceed to the cost-concentration steps only if "subagent fan-out + long-context" reproduces.

### Step 2 — Subagent model tiering (PRIMARY — biggest premium-path lever)
The premium path runs every subagent at the session model. Tier the cheap/mechanical ones down, keep
the high-judgment ones strong, and measure that quality holds. **This is the all-day lever:** every
fan-out command pays for it — `/ca:fix`, `/ca:feature`, `/ca:refactor`, `/ca:checkpoint`, `/ca:pr`,
the nightly sprint — anywhere arbiter dispatches an author, a reviewer, or an aggregator.

**2a — First, settle how to apply tiers to *plugin* agents (one quick empirical test).** Claude Code's
`model:` frontmatter is documented for user/project agents, but **whether it's honored for
plugin-bundled agents is undocumented.** Test it: add `model: haiku` to one low-risk agent (e.g.
`checkpoint-aggregator`), dispatch it, and confirm via the statusline's per-call model which model
actually ran. Resolution order is **`CLAUDE_CODE_SUBAGENT_MODEL` env → per-invocation → frontmatter →
session model**, which gives three ways to apply tiers, in increasing surgical precision:
  - **Blunt/global:** `CLAUDE_CODE_SUBAGENT_MODEL=sonnet` puts *all* subagents on Sonnet in one line —
    easiest experiment, but also downgrades security reviewers (see governance caveat).
  - **Surgical via frontmatter** (if the test shows plugin agents honor it): set `model:` per agent.
  - **Surgical guaranteed:** shadow the specific agents into `.claude/agents/` with a `model:` line
    (overrides the plugin copy) — works for sure, but carries drift-from-plugin maintenance cost.

**2b — Proposed tier map** (validate each downgrade against its kill criterion before keeping it):
  - **Keep strong (inherit/Opus) — high-judgment or governance-critical:** `security-reviewer`,
    `auth-crypto-reviewer`, `migration-reviewer`, `decision-challenger`, `grader` (SMARTS scoring).
  - **Sonnet candidates — real work, bounded by a gate:** the authors (`backend/frontend/infra-author`)
    implement against a spec + a failing test, so a cheaper author is checked by the gate; the
    user-facing `design-quality-reviewer`.
  - **Haiku candidates — mechanical/low-judgment:** `checkpoint-aggregator` (writes a dated doc),
    `finding-triage` (severity classification), `architecture-drift-reviewer` (informational, never
    blocks), `coverage-auditor` (counts untested files / threshold checks), `scout` (evidence
    gathering). This is the "don't burn Opus to write a line in `open-tasks.md`" class.

**2c — Kill criteria (downgrade only survives if quality holds):**
  - *Authors:* metric is **first-pass-through-gate rate**. A cheaper author that needs extra TDD
    cycles to go green — and extra premium re-reviews — can net *more* burn. Baseline the current
    author first-pass rate (Step 1 data) before changing anything; revert any author whose rate drops.
  - *Reviewers/aggregators:* **replay equivalence** — re-run a past scope (from any command, sprint or
    interactive) with the reviewer downgraded; it must produce the *same* findings/severities. Any miss
    on a governance reviewer reverts immediately. (This is why security/auth/migration stay strong
    until proven, not before.)
  - Step 4's yield data tells you which reviewers are safest to try first.

**2d — Possible repo deliverable:** if the 2a test shows plugin frontmatter is honored, the cleanest
durable outcome is to add `model:` lines to the ca agents in `plugins/ca/agents/*.md` (a small,
reviewable change to this repo) rather than per-user shadow copies. Gate that on the test result.
*(Pre-staged on this branch as a separate, droppable commit — keep only if 2a passes.)*

### Step 3 — Decide pruner `dry`→`on` from the ledger you ALREADY have (session-lifetime lever)
The collection phase is done: `CODEARBITER_PRUNE=dry` has already run across several `standard`
sessions and a couple of `aggressive` ones, so `~/.codearbiter/metrics/prune-dry.jsonl` exists
**on the local machine** (not the fresh remote container — the analysis runs where the data lives).
- **Analyze, don't re-collect:** `/ca:prune status` reports cumulative reduction + service state and
  reads the ledger. The go/no-go signal is the framework's own bar: **every row `verdict: dry-run`,
  `validation_errors: 0`** across the accumulated sessions. Also read the per-strategy reduction to see
  where the bytes actually come from on real sessions (it helps any long session, daytime or sprint).
- **Expected caveat (you flagged it):** the `aggressive`-only strategies (`stale-read`, `reminder
  dedup`, `image evict`) only fire when those conditions occur, so the couple of aggressive sessions
  may show little aggressive-specific data — that's an inconclusive aggressive-vs-standard comparison,
  not a failure. `standard` is the tier with real coverage; decide on that, treat aggressive as TBD.
- **Then, user's explicit choice only** (the framework refuses to enable it unbidden):
  `CODEARBITER_PRUNE=on` at the tier the ledger validates (likely `standard`). Measure how much further
  a *resumed* long session (sprint or a deep interactive thread) gets before the context bar forces a stop.
- Files: `commands/prune.md`, `hooks/_prunelib.py`, `hooks/prune-transcript.py`, `hooks/hooks.json`.

### Step 4 — Reviewer dispatch *yield* (the narrowed §5 — find unnecessary review)
- Dispatch is already once-per-scope and diff-conditional, so the only waste is a reviewer that
  **fires when nothing in its purview meaningfully changed** (e.g. a comment-only touch to a security
  file still trips `security-reviewer`).
- **Metric: dispatch-to-finding yield per reviewer** — from `sprint-log.md` (sprints) and the
  per-command `finding-triage` output (interactive commands like `/ca:fix`, `/ca:pr`, `/ca:checkpoint`),
  how often each reviewer is dispatched vs. returns any finding. Near-zero yield on trivial touches →
  candidate for a tighter trigger (semantic change in domain, not mere path-touch) **and** a safer
  model downgrade in Step 2.
- **Tooling:** `python3 tools/reviewer-yield.py` computes this from `.codearbiter/checkpoints/*.md`.
- **Governance constraint:** output is at most a *more precise trigger*, never a removed reviewer.
- Files: `subagent-driven-development/SKILL.md` (Phase 4 triggers), `docs/architecture.md` (path-matrix
  map, kept in lockstep with `includes/routing-table.md`), `agents/*-reviewer.md`, `agents/finding-triage.md`.

### Step 5 — Context discipline (free, safe — and most relevant to *daytime* use)
- `/clear` between *unrelated* tasks and `/compact` mid-task. This bites hardest in interactive use,
  where a day's worth of unrelated `/ca:fix` / `/ca:feature` / `/ca:debug` turns pile up in one session
  that a `/clear` would reset; a single coherent sprint accumulates less *unrelated* context. Investigate
  where context actually goes stale, and measure the >150k-context usage share before/after the habit.

### Step 6 — `--farm` as a tracked experiment (secondary supplement — "Claude thinks, cheap models labor")
- The right mental model, not "the savior": Claude keeps spending its tokens on the high-judgment work
  (specs, failing tests, the review chain) and hands the *labor* of making tests pass to cheap external
  models. The win is marginal extra monthly juice, not a wholesale offload. It's `preview`/off/
  unvalidated and uses external (often Chinese-origin) free models, gated by mutation + full review.
- **The one real test (agreed to run):** `--farm` on a *low-sensitivity* sprint after setting
  `FARM_API_KEY`; framework auto-selects a model by canary probe (`includes/farm.md` §"Model selection").
- **Kill criterion:** **first-pass / escalation rate** from `.farm/farm-report.json`. High escalation
  or a circuit-breaker trip (`FARM_ABORT_ESCALATION_RATE`) means re-dispatches land back on the Max
  pool → the "labor" quietly becomes Claude's again, erasing the juice. **Sovereignty:** pin
  `FARM_MODEL` to a clean model on anything sensitive.
- **Tooling:** `python3 tools/farm-first-pass.py` computes first-pass/escalation from the report.
- Files: `includes/farm.md`, `tools/farm.ts`, `skills/subagent-driven-development/references/farm-dispatch.md`,
  `SPRINT.md` (§"Execution backend").

---

## Explicitly out of scope (debunked or non-arbiter)
- **Blanket "cheapest model for *all* subagents"** — would silently downgrade the governance reviewers.
  Tiering is *selective* (Step 2), gated by replay equivalence; security/auth/migration stay strong.
- **MCP residency / `ENABLE_TOOL_SEARCH`** — no MCP infra in the plugin; a harness concern.
- **Resident-overhead reduction** — standing context is one file; the rest is lazy-loaded. Nothing to trim.
- **Peak-hour timing** — conflicting public reports; verify via `/usage` only if it ever bites.

---

## Verification / how we'll know each step worked
- **Step 1:** statusline renders; `/ca:statusline status` confirms it's arbiter's with a backup. Multi-session sample captured.
- **Step 2:** the 2a test shows which application mechanism actually changes a subagent's model (read it off the statusline's per-call model). Each downgrade passes its kill criterion — authors hold first-pass rate; downgraded reviewers/aggregators produce identical findings on a replayed scope. Net burn drops vs. the all-Opus baseline across both interactive commands and the sprint.
- **Step 3:** `/ca:prune status` over the *already-accumulated* ledger shows every row `verdict: dry-run`, `validation_errors: 0` (clean across the `standard` sessions); after flipping `on`, a resumed long session reaches further before the context bar forces a stop.
- **Step 4:** a per-reviewer dispatch-vs-finding table (across sprint + interactive scopes); any trigger change replays an old scope to the *same* findings set (no governance regression).
- **Step 5:** measured drop in the >150k-context usage share across sampled sessions (esp. daytime interactive).
- **Step 6:** `farm-report.json` first-pass/escalation rate on a real slice; net Max-pool burn (incl. premium re-dispatches) vs. a premium-only run of a comparable slice.

## Note on this plan's own method
This is an *investigation* plan: most steps are measurements and user-gated config toggles (`model:`
frontmatter / `CLAUDE_CODE_SUBAGENT_MODEL`, `/ca:statusline install`, `CODEARBITER_PRUNE`), with one
optional repo change (Step 2d) gated on the plugin-frontmatter test. The framework refuses to enable
the pruner or statusline on the user's behalf — every "turn it on" step is the user's explicit call.

---

## Findings — local execution (2026-06-18)
- **Step 0:** no `ANTHROPIC_API_KEY` in env → burn draws on the Max subscription. Gate passes.
- **Step 1:** statusline already installed and wired to codeArbiter (backup recorded).
- **Step 2a — RESOLVED: plugin frontmatter `model:` IS honored, at session start.** Proven by
  self-report dispatch after `/exit` + `--resume`: `coverage-auditor` (haiku) ran as Haiku,
  `backend-author` (sonnet) ran as Sonnet, both with no override. A mid-session cache patch did
  *not* take (ran Opus) — defs load once at session start and are held in memory. Per-invocation
  override also works and *beats* frontmatter (verified: haiku frontmatter + `sonnet` override → Sonnet).
  - **Verdict:** keep commit 2 as the durable automatic baseline tier map; reserve per-invocation
    override for dynamic exceptions. `.claude/agents/` shadow copies rejected — they inflate the
    resident agent roster (a real cost off the ~27k floor); frontmatter does not.
  - **Precedence gotcha:** `CLAUDE_CODE_SUBAGENT_MODEL` (env) beats per-invocation, so it can't be a
    "Sonnet floor" without dragging governance reviewers down. No env var; rely on per-agent frontmatter.
  - Kill criteria (2c) still apply before each downgrade is trusted: authors hold first-pass rate;
    downgraded reviewers/aggregators must replay to identical findings.
- **Step 3:** local `prune-dry.jsonl` = 9 sessions, every row `verdict: dry-run`, `validation_errors: 0`.
  standard ~33% avg (4 sessions), aggressive ~32% (5) with its extra strategies barely firing
  (`repeat-reminder-fold`/`inline-image-evict` never triggered) → aggressive inconclusive. Wins come
  from `sidecar-collapse` + `aged-result-condense` (both standard). Justified to flip `on@standard`
  (user toggle). Aggressive: TBD.
- **Step 4 — reviewer yield (n=2 checkpoints, thin):** no actionable trigger change at this sample.
  Found and fixed a data-quality bug first: the auth-crypto sub-reviewer was logged under two names
  (`auth-crypto-reviewer` / `auth-reviewer`), splitting its row and mis-reading as 0% — actually ~50%
  (4 findings). `tools/reviewer-yield.py` now canonicalizes that alias. After the merge, the only
  genuine 0%-yield reviewer is `migration-reviewer` (2 disp / 0 found) — but it's governance (held
  `inherit`) and n=2, so per the governance constraint the most it could ever justify is a *tighter
  trigger*, never a downgrade/removal, and not on this sample. **Action: accumulate checkpoints; watch
  `migration-reviewer`.** Deeper fix: canonical reviewer names at checkpoint-authoring time.
- **Step 5 — context discipline (advisory; longitudinal):** habit = `/clear` between *unrelated* tasks,
  `/compact` mid-task. The before/after >150k-context usage share needs `/usage` sampling across days;
  not measurable in one session. Ledger corroborates large transcripts (9 sessions est. 270k–585k
  tokens) but those are transcript sizes, not live-window peaks.
- **Step 6 — `--farm` (user-gated; not run):** no `FARM_API_KEY`, no `.farm/` (never run). Instrument
  `tools/farm-first-pass.py` confirmed working (clean no-data path). Protocol: set `FARM_API_KEY`, run
  one low-sensitivity `/ca:sprint --farm`, judge on first-pass/escalation from `.farm/farm-report.json`;
  pin `FARM_MODEL` on anything sensitive.

## Branch artifacts (for resuming locally)
This branch (`claude/investigate-token-efficiency-bbf17t`) carries:
- `tools/reviewer-yield.py`, `tools/farm-first-pass.py`, `tools/README.md` — the analysis aids (Steps 4 & 6).
- `plugins/ca/agents/*.md` `model:` lines — the **gated** Step 2d tiering (separate commit; keep only if the 2a test confirms plugin frontmatter is honored).
- this plan doc.

Local resume: `git pull`, then run the runbook from Step 0 in your terminal Claude Code (statusline, prune ledger, the 2a test, sampling, and — when ready — the `--farm` test all need the live local session).
