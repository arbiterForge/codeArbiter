# codeArbiter farm — setup and configuration

`farm.ts` is the zero-LLM-token dispatcher: Claude writes specs, failing tests, and a `plan.json`;
the farm runs cheap Zen workers in isolated git worktrees to make each test pass; Claude reviews
and merges. The cheap model cannot redefine the gates — only pass them.

## Required

### `FARM_API_KEY`

Your OpenCode Zen API key (or a compatible OpenAI-compatible provider key). Set it in one of:

- Shell environment: `export FARM_API_KEY=sk-...` (recommended for CI and development)
- Local `.env` at `plugins/ca/tools/.env` (dev convenience, never committed)
- `${CLAUDE_PROJECT_DIR}/.claude/settings.local.json` `env` block (gitignored by default)

Never commit this key. It must not appear in `.codearbiter/` audit files.

### `FARM_API_BASE_URL`

The OpenAI-compatible endpoint base URL. Defaults to `https://api.opencode.ai/v1` if set in `.env`.
Override for DeepSeek direct (`https://api.deepseek.com/v1`), Ollama (`http://localhost:11434/v1`), etc.

## Model selection — automatic at dispatch time

`FARM_MODEL` is normally **not set**. Before each `/ca:sprint --farm` run, `subagent-driven-development`
performs a fresh websearch to identify the current best free model on Zen's roster:

1. Searches for the current free model list and any opaque codenames (e.g. "Big Pickle").
2. Researches community consensus on each codename's underlying model and coding ability.
3. Surfaces the selection and rationale for user confirmation before dispatching.

This research runs fresh before each farm run so the model selection never goes stale.

## Optional overrides

| Variable | Default | Purpose |
|---|---|---|
| `FARM_MODEL` | _(unset)_ | Skip model research and use this model ID directly. Power-user/CI override. |
| `FARM_API_BASE_URL` | _(from plan.json or .env)_ | Override the endpoint URL. |
| `FARM_CONCURRENCY` | `4` | Max concurrent task workers. |
| `FARM_MAX_RETRIES` | `2` | Max gate retries per task before escalating. |
| `FARM_BASE_BRANCH` | `main` | Branch the integration branch is cut from. |

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
- `farm-report.json` — structured results (status, attempts, worktree, note per task)
- `farm-report.md` — human-readable summary table

Escalated tasks leave their worktrees at `.farm/worktrees/<task-id>/` for inspection.
