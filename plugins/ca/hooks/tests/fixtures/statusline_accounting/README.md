# Statusline accounting fixtures

These are sanitized **structural** fixtures of real Claude Code transcript shapes. They back the
accounting spec `.codearbiter/specs/claude-statusline-accounting-integrity.md` (observations 1–10,
AC-51).

## Provenance

- **Capture date:** 2026-09-27, from Claude Code 2.1.283 transcripts on one Windows machine.
- **Every identifier is replaced** with a stable fixture token:
  - `requestId` becomes `req_fx_NNN`;
  - `message.id` becomes `msg_fx_NNN`;
  - `uuid`/`parentUuid` become `uuid-fx-NNN`;
  - session IDs become `sess-fx-NNN`;
  - agent IDs become `fxagentNNN`.

  The mapping is consistent within a capture, so shared IDs stay shared. That is what makes the fork
  replay observable.
- **All conversation content is removed:**
  - assistant `content` keeps only block `type` (plus `name` for `tool_use`);
  - user `content` is replaced with a fixed fixture label.
- **Usage objects are copied verbatim**, since they are the subject under test.
- **Environment fields are never copied:** paths, `cwd`, `gitBranch`, `version`, hostnames, user
  names and emails. `test_accounting_fixtures.py` enforces this.

## Shapes

| File | Shape |
|---|---|
| `fork_replay/parent.jsonl` + `fork_replay/parent/subagents/agent-fxchild{1,2}.jsonl` | Two forked children. Each starts with `fork-context-ref`, followed by a copy of the parent's spawning assistant message. The copy has the same `requestId`/`message.id`, `isSidechain:true`, and an earlier partial streaming snapshot. The layout mirrors `<transcript stem>/subagents/`. |
| `advisor_iterations.jsonl` | Every streaming representation of one request whose `usage.iterations` has `message` / `advisor_message` (own `model`) / `message`. The top-level counters equal the `message` iterations only. The top-level `cache_creation` split reflects only the first iteration, while the per-iteration splits sum to the aggregate. |
| `streaming_snapshots.jsonl` | Several representations of one request whose `output_tokens` grow. |
| `synthetic.jsonl` | `<synthetic>` records with all-zero usage. One has no `requestId`. |
| `modifiers.jsonl` | One record lacking `speed` (an older host) and one with `speed:"standard"`. Both have `service_tier:"standard"` and `inference_geo:"not_available"`. |
| `cost_state.jsonl` | The host's own cumulative `cost-state` record: per-model usage, including a Haiku side-query model absent from every transcript usage record. This is host evidence only, never reconstructed usage. |
| `nonusage_types.jsonl` | One record of every observed non-usage type, plus an `attachment` task-notification whose `usage` summary (`totalTokens`/`toolUses`/`durationMs`) must never be counted. |

## Recorded assumptions and gaps

- **`inference_geo:"not_available"`** is the only value observed. The spec (D-27) treats it as
  standard routing. That is an assumption, not documented host behavior.
- **No nested (`spawnDepth > 1`) child was observed.** All 92 captured children had depth 1 and sat
  flat in `<session>/subagents/`.
- **No non-zero `server_tool_use` counter, `speed:"fast"`, or `inference_geo:"us"` was
  observed.** Tests that need those values build synthetic records and label them as synthetic.
