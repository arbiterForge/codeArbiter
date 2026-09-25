# codeArbiter farm — setup and configuration

> **Feature Forge `preview`.** The `--farm` backend ships off by default; the premium subagent path is
> the blessed default. Historical runs informed the design but count as zero current qualification
> evidence. Promotion requires the complete fresh-evidence bar below.

## Stable opt-in promotion bar

Qualification starts at zero on 2026-09-16. Runs before that date are historical development evidence
only and earn no promotion credit. Before promotion, one durable qualification packet must bind all
evidence to exact farm revisions and show:

- at least five completed farm slices across at least three distinct repositories;
- at least 50 dispatched implementation tasks;
- completed evidence from Windows and a POSIX host, spanning at least two selected model identities;
- at least 85% direct farm completion, no more than 15% premium escalation, and no more than 1.5
  average attempts per dispatched task;
- zero circuit-breaker trips, gate escapes, security incidents, supply-chain incidents, or unresolved
  HIGH findings;
- the ordinary integrated suite, full review chain, and fresh verification passing for every slice;
- at least 25% lower premium implementation-token consumption than comparable premium execution,
  counting escalations and review rather than treating worker tokens as the whole cost.

All qualifying runs must use the then-current farm implementation and provider model set. A material
farm implementation change or provider/model-set change before promotion invalidates the affected
evidence and requires it to be rerun. Promotion means **stable opt-in** only: it does not make farm the
default, remove any external-dispatch trust gate, or enable typed-HTML farm projection. The typed-HTML
path remains blocked until its own integration and qualification are complete.

`farm.ts` is the pluggable execution backend: Claude writes specs, failing tests, and a `plan.json`;
the farm runs workers in isolated git worktrees to make each test pass; Claude reviews and merges. Its
value is deterministic, gated, parallel, isolated execution — a worker cannot redefine the gates, only
pass them. The `Worker` interface seam admits cheap, premium, and agentic worker implementations behind
the same hard gates; **only the cheap HTTP-chat worker ships today** — premium (e.g. a top-tier hosted
model) and agentic (a worker that reads files and iterates) are what the seam is designed for, roadmap
not built. Cost arbitrage is one worker policy, not the definition.

The worker prompt is enriched with the failing-test source and current in-scope file contents, byte-capped
(`FARM_ENRICH_MAX_BYTES`) and secret-redacted before transmission to the endpoint.

**Swapping the worker changes who writes the code, never whether it's reviewed.** Every task the farm
reports green is still routed through the normal spec-compliance, quality, and fresh-verification
gates (`subagent-driven-development` Phases 3–5) before acceptance. The dispatcher additionally runs two
zero-token guards (below), protects the failing test from being modified, contains all worker writes
inside the worktree, and trips a circuit breaker if too many tasks escalate (a sign the model isn't
capable of the slice).

### Zero-token quality guards

1. **Literal-leak** — flags repeated whole, same-kind string or numeric spellings in a small
   implementation (`return 42` for `expect(f()).toBe(42)`). A number inside an identifier, a larger
   number/string, or a conventional source comment is not a match. String `"42"` and number `42`
   are distinct. The existing five-code-line boundary determines rejection versus warning; a
   rejection names the actual small-file match, not an earlier substantial-file match.
2. **Mutation** — after the gate is green, mutates the worker's in-scope impl (operator flips, return
   replacement, boolean inversion) and re-runs **only the task's narrow test** (`gate.commands[0]`). A
   surviving mutant is an implementation change the test command did not reject. It can indicate
   weak tests, dead code or an equivalent change; it does not by itself prove gaming. Bare nonzero
   exits do not establish valid, assertion-killed mutants. Built-in positive rejection ratios remain
   unverified bounds, not measured scores; see the accounting rule below. A low result attaches a
   **warning that rides into Phase 3** for independent review; only the existing near-zero result
   with sufficient evaluated evidence rejects the candidate. Screening is sampled and time-boxed. Set
   `FARM_MUTATION_CMD` to swap the built-in text mutator for a real per-language framework (Stryker,
   mutmut, …); it runs in the worktree with `FARM_MUTATION_FILES` / `FARM_MUTATION_TEST_PATH` /
   `FARM_MUTATION_TEST_CMD` set. A measured hook score requires successful completion (exit 0,
   no timeout, verified timeout cleanup when needed) and a trailing stdout JSON report with a finite
   `score` in `[0, 1]`. A wrapper around a percentage-based framework must normalize its measurement;
   stderr diagnostics are not the score channel. Optional counts and survivors remain absent unless
   the hook actually reports them.

The literal check is a bounded lexical heuristic, not an assertion parser or proof of intent. It
ignores conventional slash comments in recognized C-family source suffixes and hash comments in
Python; other suffixes do not acquire a guessed comment grammar. Plain quote delimiters and numeric
spellings are compared without evaluating escapes or constant expressions. Dynamic templates are not
constant-string evidence; only unambiguous expression-start regex forms are skipped. Language-specific
prefixes, JSX and other ambiguous grammar are not fully interpreted. Test labels, inputs and legitimate
shared constants can still match. Normal independent review remains authoritative; an absent lexical
match neither skips the mutation check nor accepts the work.

A configured hook that fails, times out, or reports invalid output supplies diagnostics, not a
measured `mutationScore`. Ordinary unavailable measurements retain the existing warning policy and
continue through normal independent review; this does not add a user checkpoint. Do not hide adverse
evidence: a failed hook's parseable stdout report at or below the existing near-zero floor, with at
least five explicitly reported evaluated mutants, still rejects that candidate pending successful
remeasurement. It is not published as a valid score. No evaluated count is invented from absence or a
survivor list. A retained alternative can qualify under the same rules before another model round.

If timeout cleanup cannot establish that the mutation process tree stopped, qualification is fatal
for that task: no further candidate, retry, commit or integration may run against a possibly live
writer. Existing task reporting retains known spend and cleanup diagnostics. Neither an adverse
report nor failed process containment can be converted into acceptance by scoring prose.

The built-in text mutator bounds each test launch by the remaining mutation budget and any shorter
configured gate timeout. Zero mutation budget launches no tests; disabling the general gate timeout
does not disable this budget. Mutant writes count against the trial budget. Verified process teardown
and defensive restoration can take additional time and must finish or refuse safely before work
advances. An interrupted trial is not a killed mutant: stop screening, restore the worker's output,
and return diagnostics without a measured score. Completed observations before the interruption stay
explicitly unverified; the existing near-zero/five-completed-reruns floor still rejects an adverse
candidate. A clean timeout otherwise warns through independent review, without another default
user checkpoint. Unverified process cleanup retains the fatal containment boundary above.

A completed nonzero rerun is an **unclassified gate rejection**, not a proved mutant kill. The
built-in runner cannot distinguish a compiler, loader, infrastructure or assertion failure from an
arbitrary command's exit status. Diagnostic wording and printed score-like JSON do not grant that
classification. Preserve a bounded, redacted first-rejection witness and completed/pass counts;
do not publish a positive `mutationScore` from these exits. For real language-specific measurements,
use the existing explicitly configured external framework hook rather than another public command.

For at least three completed reruns, retain `R / (S + R)` as an **unverified gate-rejection upper
bound**, where `R` is completed nonzero reruns and `S` is successful reruns. Treating every rejected
trial as a valid kill is the most favorable interpretation of those observations; excluding invalid
rejections cannot increase that fraction. This is not a language-aware mutation score and does not
classify equivalent or unexercised changes. Preserve the existing near-zero/five-completed-reruns
rejection floor even on this bound: uncertainty cannot erase an already adverse result. Otherwise
retain the ordinary warning and independent review, without spending another model round or adding a
user checkpoint solely because the measurement is unavailable.

With no rejected or interrupted trial, at least three successful reruns still produce the existing
zero screening score and survivor list. A shorter all-pass run stays too thin to score; a short
nonzero run reports its diagnostic without inventing a usable evaluated count. A budget ending
between trials follows these same rules; interruption never publishes a partial measured score.
Language-aware validity and semantic interpretation of literal overlap remain separate work. None
of these screening outcomes is task or scope acceptance proof.

Note: `writing-plans --farm` MUST place the task's narrow behavioral test first in `gate.commands` —
the mutation guard runs `gate.commands[0]` as the per-mutant test (running an exhaustive suite per mutant
would be too slow).

### Best-of-N sampling and iterative retries

By default the farm draws one worker completion per task attempt (`FARM_SAMPLES=1`). With
`FARM_SAMPLES=N`, it draws **N candidates** in isolated scratch worktrees from the task's frozen
baseline. Total in-flight worker calls share `FARM_CONCURRENCY`; sampling does not multiply that cap.

Sample gate success is only a shortlist. In deterministic sample-index order, each shortlisted
candidate is materialized into the task worktree and receives the same containment, immutable-test,
drift, task-gate, literal-risk and mutation checks as the single-worker path. Alternatives remain
available until one passes those checks. A gate or high-risk rejection tries the next existing
candidate before spending another model round. An integrity failure or an unusable reset/setup
stops that task rather than disguising the failure with an unrelated passing candidate.

Between candidates, tracked and non-ignored worker changes are reset to the task baseline and the
existing setup phases are reapplied. Ignored dependency caches retain their existing policy. Cleanup
is attempted for every sample, including exception paths; unresolved cleanup is reported. The same
selection applies to detached canary work, which still stops before commit or merge.

`farm-report.json` records summed known sample usage (`promptTokens`/`completionTokens`) separately from
the selected candidate's own tokens (`acceptedPromptTokens`/`acceptedCompletionTokens`). Qualification
makes no additional model requests, but can run local gates and mutation checks for multiple
candidates. It is not comparative quality ranking or a measured savings claim. Normal independent
reviews and acceptance still follow. With `FARM_SAMPLES>1` and no explicit temperature, sampling
defaults to `0.7`; `FARM_TEMPERATURE` remains the operator override. An explicit
`FARM_TEMPERATURE=0` is respected even with multiple samples and disables this automatic
bump. Leave the override unset or choose a supported nonzero temperature when seeking
more varied candidates; a temperature setting is not a guarantee of distinct outputs.

On a **retry** — a failed gate, or a sampling round with no qualified candidate — the worker is shown its own previous
in-scope output, not just the gate-failure tail, so it refines rather than restarts blind. That prior
output rides the same byte-cap (`FARM_ENRICH_MAX_BYTES`) and secret-redaction chokepoint as all other
injected context; out-of-scope drift is never carried forward.
If the retry cannot reset its worktree, the task escalates without another model call.
Its report retains the completed attempts' known token usage, last output/risk evidence,
and any unresolved sample cleanup outcomes; a failed reset cannot erase them.

A decoded provider response can contain reported usage even when its output is
rejected. The worker preserves valid counters through malformed message content,
read-only or escaping paths, and guarded-write refusals, including any already
written file list. A malformed non-text response becomes an ordinary worker
failure under the existing retry/selection policy, not an unhandled parser error.
Counters must be explicitly reported nonnegative safe integers; validate prompt
and completion independently. Explicit zero is valid; missing, invalid or
undecodable counts stay absent at the worker boundary. The existing report sums
known counts, so its total is not proof of complete usage or verified billing.
No extra provider request is made to recover a missing counter. HTTP failures,
transport retries without usable usage and provider pricing remain outside this
accounting correction. Output rejection still enforces the original write,
test, gate and independent-review requirements.

## Required

### `FARM_API_KEY`

Your OpenCode Zen API key, or any OpenAI-compatible provider key. Set it in one of:

- Shell environment: `export FARM_API_KEY=sk-...` (recommended for CI and development)
- Local `.env` at `plugins/ca/tools/.env` (dev convenience, never committed)
- `${CLAUDE_PROJECT_DIR}/.claude/settings.local.json` `env` block (gitignored by default)


Never commit this key. It must not appear in `.codearbiter/` audit files.

### `FARM_API_BASE_URL`

The OpenAI-compatible endpoint base URL. Resolution order: `FARM_API_BASE_URL` env → `plan.meta.apiBaseUrl`
→ a built-in default of `https://opencode.ai/zen/v1` (the live OpenCode Zen host). Override for DeepSeek direct
(`https://api.deepseek.com/v1`), Ollama (`http://localhost:11434/v1`), etc.

## Model selection — measured at dispatch time

`FARM_MODEL` is normally **not set**. Before a `/ca:sprint --farm` run, `subagent-driven-development`
picks a model by *measurement*, not hearsay:

1. **Cache check** — reuse `.farm/model-cache.json` if it holds a model chosen in the last 7 days with
   an acceptable canary pass-rate. Otherwise re-select.
2. **Discovery** — websearch the current free Zen roster to enumerate candidate ids (codenames included).
   This finds *candidates*; it does not judge quality.
3. **Canary** — `farm.js --canary` runs the plan's smallest no-dependency task against each candidate
   and ranks that task's gate result / attempts / latency (`FARM_CANDIDATE_MODELS` carries the list).
   It freezes the configured base commit before probing, uses separate detached scratch worktrees
   for each model and sample, and records `baseCommit` in `.farm/canary-report.json`. Candidate
   selection overrides `task.model` for the trial only; normal dispatch keeps its task override.
   Worker containment, immutable tests, drift and verification checks still apply. Evaluation stops
   before staging, committing or merging: it does not reset or advance an existing integration
   branch. Existing task branches and worktrees are not its scratch. The top passer wins only after
   verified cleanup; retained scratch is reported and exits nonzero without recursively erasing it.
   A single task's result is not a general model pass-rate or promotion qualification.
4. **Surface** — the choice is presented with its measured basis (and a one-line websearched identity note
   for the audit log), then written to `plan.meta.model` + `.farm/model-cache.json`.
5. **Fallback ladder** — if the canary can't run or none pass: cached model → unmeasured websearch pick
   (with a warning) → only then BLOCK for a manual `FARM_MODEL`. A noisy websearch never halts the feature.

## Optional overrides

| Variable | Default | Purpose |
|---|---|---|
| `FARM_MODEL` | _(unset)_ | Skip selection and use this model id directly. Power-user/CI override. |
| `FARM_API_BASE_URL` | `https://opencode.ai/zen/v1` | Endpoint URL (env → plan.json → this default). |
| `FARM_CANDIDATE_MODELS` | _(unset)_ | Comma-separated ids for `--canary` probing. Set by the dispatch skill. |
| `FARM_CONCURRENCY` | `4` | Max concurrent task workers — and the shared ceiling on TOTAL in-flight worker calls, including best-of-N samples. |
| `FARM_SAMPLES` | `1` | Best-of-N: candidates drawn per attempt; first in index order to pass task-worktree gates and risk qualification is selected. `1` keeps the single-worker path. Shares `FARM_CONCURRENCY`; known reported usage from all candidates is summed. |
| `FARM_TEMPERATURE` | `0` (one sample); `0.7` (multiple, unset) | Sampling temperature sent to the worker. Defaults to `0` when `FARM_SAMPLES=1` and `0.7` when `FARM_SAMPLES>1`. Any explicit value, including `0`, overrides the automatic default. |
| `FARM_MAX_TOKENS` | _(unset)_ | Max completion tokens per worker call. `0`/unset = provider default (today's unbounded behavior). |
| `FARM_MAX_RETRIES` | `2` | Max gate retries per task before escalating. |
| `FARM_BASE_BRANCH` | `main` | Branch the integration branch is cut from. |
| `FARM_REQUEST_TIMEOUT_MS` | `120000` | Per-request hard timeout; also caps an individual provider-directed retry wait. |
| `FARM_API_MAX_RETRIES` | `3` | Transport retries for 429/5xx. Bounded `Retry-After` is honored; exhaustion defers new authoring for that task. |
| `FARM_ENTITLEMENT_PROBE_TIMEOUT_MS` | `35000` | Per-candidate wall-clock cap for the `--canary` entitlement pre-screen (drops 401 promo-expired models). |
| `FARM_ENRICH_MAX_BYTES` | `131072` | Cap on bytes of test-source + in-scope file context injected into the worker prompt (data-minimization; redacted for secrets). |
| `FARM_ABORT_ESCALATION_RATE` | `0.5` | Circuit breaker: abort once escalations exceed this fraction… |
| `FARM_ABORT_MIN_TASKS` | `3` | …after at least this many tasks have settled. |
| `FARM_MUTATION` | `on` | Mutation guard on/off. |
| `FARM_MUTATION_SAMPLE` | `15` | Max mutants per task (sampled). |
| `FARM_MUTATION_BUDGET_MS` | `30000` | Per-task mutation time box. |
| `FARM_MUTATION_WARN_BELOW` | `0.5` | Score below this attaches a warning into Phase 3. |
| `FARM_MUTATION_ESCALATE_BELOW` | `0.1` | Score at/below this (≥5 mutants) hard-escalates. |
| `FARM_MUTATION_CMD` | _(unset)_ | Pluggable external mutation framework hook. |
| `FARM_RUN_ID` | _(random)_ | Pin this run's id — also the name of its artifact directory (`.farm/runs/<run-id>/`). Must be 1–64 chars of `[A-Za-z0-9._-]`; anything else is refused at startup. Reusing an id publishes over that directory's receipts, so pin a fresh one per run. |

## Per-worktree setup (dependency hook)

Each task runs in an isolated git worktree cut from the integration HEAD. Gitignored directories —
`node_modules`, a Python `venv`, `target/`, etc. — are **not** present in a fresh worktree, so a gate
that needs them (`vitest`, `pytest`, `cargo test`) can fail for environmental reasons. (Node's
up-tree module resolution often papers over this for JS because the worktree lives under the repo
root; languages without up-tree resolution get nothing.)

Set **`meta.setup`** in `plan.json` — a list of shell commands the dispatcher runs **in each worktree
before the worker**, **once per worktree**:

```json
{ "meta": { "name": "my-sprint", "setup": ["npm ci"] }, "tasks": [ … ] }
```

- A per-task **`task.setup`** overrides `meta.setup` for that task; otherwise `meta.setup` applies to all.
- Setup runs through the same shell + exit-code path as `gate.commands`. A **non-zero setup command
  escalates the task immediately** (it is environmental, not a worker failure) — the worker is not invoked.
- **Setup-produced files must be gitignored.** Anything setup writes that is *not* ignored and *not* in
  the task's `filesInScope` is correctly flagged as drift and escalates.
- Cost: **`setup` runs once per worktree, not once per retry.** The inter-attempt reset is
  `git reset --hard` + `git clean -fd` (no `-x`), which *preserves* ignored paths — so the gitignored
  dependency tree the contract above requires survives the reset and does not need reinstalling. For
  JS, leaving `setup` unset and relying on root `node_modules` up-tree resolution is the cheaper path
  when it works; `setup` is the portable, explicit alternative.

### When setup output *does* go stale — `setupEachAttempt`

`setup` is for one-time dependency restore. Commands that regenerate ignored output **from tracked
source** (codegen, a build step) genuinely do go stale when the reset rolls the tracked files back.
Declare those separately — they rerun before every attempt, after `setup`:

```json
{ "meta": { "name": "my-sprint", "setup": ["npm ci"], "setupEachAttempt": ["npm run codegen"] } }
```

`task.setupEachAttempt` overrides `meta.setupEachAttempt` the same way. A non-zero command escalates
the task identically.

### Invalidating the once-per-worktree cache — `setupInputs`

The cache is a fingerprint of the `setup` commands plus the content hashes of any paths listed in
**`setupInputs`** (relative, no `..`), scoped to exactly one worktree. List your lockfile there when
a moved baseline must force a reinstall — regenerate-on-conflict resets a task worktree onto a *new*
integration HEAD, which can carry a different lockfile:

```json
{ "meta": { "name": "my-sprint", "setup": ["npm ci"], "setupInputs": ["package-lock.json"] } }
```

## Sovereignty note

`FARM_MODEL` is the one-line control for model provenance on sensitivity-relevant projects.
Many free Zen models are Chinese-origin (DeepSeek variants, GLM, etc.). Set `FARM_MODEL` to a
sovereignty-clean model (e.g. a Mistral or Llama variant) when project sensitivity requires it.
The dispatch skill surfaces the underlying model identity so you can make an informed choice.

## Invocation

Direct (dev): `cd "${CLAUDE_PLUGIN_ROOT}/tools" && npm run farm -- <plan.json>`
Via plugin: `node "${CLAUDE_PLUGIN_ROOT}/tools/farm.js" <plan.json>`

Normal use: `/ca:sprint --farm` — the skill handles model selection and dispatch automatically.

## Report artifacts

Every run owns an artifact directory keyed by its run id — `${CLAUDE_PROJECT_DIR}/.farm/runs/<run-id>/` — and
that directory is the **durable receipt**, written by that run alone. Two farm processes against one
repository therefore cannot overwrite each other's *evidence* (see the concurrency caveat below — the
receipts are isolated, the git state is not):
- `farm-report.json` — structured results: per-task status, attempts, files written, known reported worker usage,
  warnings (gaming-risk), and an `aborted` flag; plus a `blocked[]` array with reasons, and an
  `artifacts` block stating whether the streaming rail was complete and which tasks' diff evidence is
  unavailable.
- `farm-report.md` — human-readable summary table.
- `farm-results.jsonl` — this run's incremental settlement stream.
- `diffs/<task-id>.patch` — the actual change each task produced, for audit.

The historical top-level paths remain as a **latest** convenience pointer, republished from the run's
own artifacts: `.farm/farm-report.json`, `.farm/farm-report.md`, `.farm/farm-results.jsonl`,
`.farm/diffs/<task-id>.patch`. Under concurrency the pointer is last-writer-wins — always a complete
artifact, never a truncated one, but attributable only via its `run_id`. Reconcile against the run
directory when it matters. Also in `.farm/`:
- `canary-report.json` — model-probe ranking, frozen `baseCommit`, and any cleanup failures
  (when `--canary` was run). This is evaluation evidence, not task acceptance or integration proof.
- `model-cache.json` — last selected model + timestamp + canary pass-rate.

Every report write is atomic (same-directory temp file, then rename), so a reader of a report path sees
either the previous complete artifact or the new one — never a truncated one, and never a half-written
file left by a crash mid-publication. (Atomicity, not crash durability: the rename itself is not
fsynced, so a host power-loss immediately after publication can still lose it.) If the run's
**authoritative, run-scoped** report cannot be published in full, the run **exits 3** and suppresses the
success `Report:` breadcrumb — a receipt failure is reported distinctly from a task failure (exit 2),
never as success. Failing to refresh the *latest* pointer is **not** exit 3: it is non-authoritative, so
it prints a warning naming what was not refreshed and the run still settles on its task outcome.

### Concurrency: what is and is not safe

Run-scoped receipts make concurrent runs non-destructive to each other's **artifacts**. They do not make
the **git state** concurrent. At default settings a second simultaneous run fails at startup with
`cannot lock ref 'refs/heads/farm/integration'`, because every run claims the same integration branch.
To run two farms against one repository at the same time, give each process:
- a distinct `FARM_INTEGRATION_BRANCH` (default `farm/integration` is shared and single-claim);
- a distinct `FARM_WORKTREE_ROOT` (default `.farm/worktrees`), unless the plans' task ids are disjoint —
  per-task worktrees are `<FARM_WORKTREE_ROOT>/<task-id>`;
- plans whose **task ids do not overlap**: each task's branch is `farm/<task-id>` regardless of run id,
  so two runs carrying the same task id fight over one branch. There is no env var for this — rename
  the tasks.

Escalated tasks leave their worktrees at `.farm/worktrees/<task-id>/` for inspection.

Canary ranking: `FARM_CANDIDATE_MODELS=a,b,c farm.js --canary <plan.json>` (cwd at the project root).

### Transport retry boundaries

A 429 or server failure retries the HTTP request within `FARM_API_MAX_RETRIES`, not a fresh
implementation. Recognized `Retry-After` delay-seconds and HTTP-date values are honored only when
the wait fits the existing `FARM_REQUEST_TIMEOUT_MS` budget and the runtime timer range. An excessive
valid cooldown is not shortened or allowed to park a worker indefinitely. Missing or malformed fields
use the existing exponential backoff capped at 16 seconds; explicit zero or a past valid date permits
an immediate retry. Request deadlines still cover headers and successful body reads; between-request
waits are separate. Discarded error streams are aborted before waiting or returning.

Once that HTTP retry budget is exhausted, or a valid cooldown cannot fit locally, the worker returns
an explicit non-retryable transport disposition. The task does not spend another authoring attempt
against the same unavailable provider. Already-produced candidates may still qualify, independently
eligible tasks can continue under the existing circuit breaker, and dependent work remains unaccepted.
This is a reported task deferral, not a new user-approval gate or automatic delayed-resume service.
Network/body failures and ordinary implementation failures otherwise retain their existing retry
policy. This does not introduce a provider-wide cooldown coordinator, a new setting, or a spend claim.
