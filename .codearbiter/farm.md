# codeArbiter farm — setup and configuration

`farm.ts` is the zero-LLM-token dispatcher: Claude writes specs, failing tests, and a `plan.json`;
the farm runs cheap Zen workers in isolated git worktrees to make each test pass; Claude reviews
and merges. The cheap model cannot redefine the gates — only pass them.

**The arbitrage is in who writes the code, never in whether it's reviewed.** Every task the farm
reports green is still routed through the normal spec-compliance, quality, and fresh-verification
gates (`subagent-driven-development` Phases 3–5) before acceptance. The dispatcher additionally runs a
zero-token anti-gaming guard (rejects an impl that hard-codes the test's asserted value), protects the
failing test from being modified, contains all worker writes inside the worktree, and trips a circuit
breaker if too many tasks escalate (a sign the model isn't capable of the slice).

## Required

### `FARM_API_KEY`

Your OpenCode Zen API key (or a compatible OpenAI-compatible provider key). Set it in one of:

- Shell environment: `export FARM_API_KEY=sk-...` (recommended for CI and development)
- Local `.env` at `plugins/ca/tools/.env` (dev convenience, never committed)
- `${CLAUDE_PROJECT_DIR}/.claude/settings.local.json` `env` block (gitignored by default)

Never commit this key. It must not appear in `.codearbiter/` audit files.

### `FARM_API_BASE_URL`

The OpenAI-compatible endpoint base URL. Resolution order: `FARM_API_BASE_URL` env → `plan.meta.apiBaseUrl`
→ a built-in default of `https://api.opencode.ai/v1`. Override for DeepSeek direct
(`https://api.deepseek.com/v1`), Ollama (`http://localhost:11434/v1`), etc.

## Model selection — measured at dispatch time

`FARM_MODEL` is normally **not set**. Before a `/ca:sprint --farm` run, `subagent-driven-development`
picks a model by *measurement*, not hearsay:

1. **Cache check** — reuse `.farm/model-cache.json` if it holds a model chosen in the last 7 days with
   an acceptable canary pass-rate. Otherwise re-select.
2. **Discovery** — websearch the current free Zen roster to enumerate candidate ids (codenames included).
   This finds *candidates*; it does not judge quality.
3. **Canary** — `farm.js --canary` runs the plan's smallest task against each candidate and ranks them by
   measured pass-rate / attempts / latency (`FARM_CANDIDATE_MODELS` carries the list). The top passer wins.
4. **Surface** — the choice is presented with its measured basis (and a one-line websearched identity note
   for the audit log), then written to `plan.meta.model` + `.farm/model-cache.json`.
5. **Fallback ladder** — if the canary can't run or none pass: cached model → unmeasured websearch pick
   (with a warning) → only then BLOCK for a manual `FARM_MODEL`. A noisy websearch never halts the feature.

## Optional overrides

| Variable | Default | Purpose |
|---|---|---|
| `FARM_MODEL` | _(unset)_ | Skip selection and use this model id directly. Power-user/CI override. |
| `FARM_API_BASE_URL` | `https://api.opencode.ai/v1` | Endpoint URL (env → plan.json → this default). |
| `FARM_CANDIDATE_MODELS` | _(unset)_ | Comma-separated ids for `--canary` probing. Set by the dispatch skill. |
| `FARM_CONCURRENCY` | `4` | Max concurrent task workers. |
| `FARM_MAX_RETRIES` | `2` | Max gate retries per task before escalating. |
| `FARM_BASE_BRANCH` | `main` | Branch the integration branch is cut from. |
| `FARM_REQUEST_TIMEOUT_MS` | `120000` | Per-request hard timeout (prevents worker-slot deadlock). |
| `FARM_API_MAX_RETRIES` | `3` | Transport retries for 429/5xx (honors `Retry-After`). |
| `FARM_ABORT_ESCALATION_RATE` | `0.5` | Circuit breaker: abort once escalations exceed this fraction… |
| `FARM_ABORT_MIN_TASKS` | `3` | …after at least this many tasks have settled. |

## Sovereignty note

`FARM_MODEL` is the one-line control for model provenance on sensitivity-relevant projects.
Many free Zen models are Chinese-origin (DeepSeek variants, GLM, etc.). Set `FARM_MODEL` to a
sovereignty-clean model (e.g. a Mistral or Llama variant) when project sensitivity requires it.
The dispatch skill surfaces the underlying model identity so you can make an informed choice.

## Invocation

Direct (dev): `cd plugins/ca/tools && npm run farm -- <plan.json>`
Via plugin: `node "${CLAUDE_PLUGIN_ROOT}/tools/farm.js" <plan.json>`
Normal use: `/ca:sprint --farm` — the skill handles model selection and dispatch automatically.

## Report artifacts

After a run, the farm writes to `${CLAUDE_PROJECT_DIR}/.farm/`:
- `farm-report.json` — structured results: per-task status, attempts, files written, worker token spend,
  warnings (gaming-risk), and an `aborted` flag; plus a `blocked[]` array with reasons.
- `farm-report.md` — human-readable summary table.
- `diffs/<task-id>.patch` — the actual change each task produced, for audit.
- `canary-report.json` — model-probe ranking (when `--canary` was run).
- `model-cache.json` — last selected model + timestamp + canary pass-rate.

Escalated tasks leave their worktrees at `.farm/worktrees/<task-id>/` for inspection.

Run `/ca:sprint --farm`, or invoke directly: `node "${CLAUDE_PLUGIN_ROOT}/tools/farm.js" <plan.json>`
(with cwd at the project root). Canary: `FARM_CANDIDATE_MODELS=a,b,c farm.js --canary <plan.json>`.
