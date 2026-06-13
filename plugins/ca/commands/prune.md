---
description: Trim transcript clutter to extend session lifetime — analyze, prune a copy, or toggle the after-each-turn service. Dry-run by default; gains land at resume/compaction, not the current turn.
argument-hint: status | dry | run <path> | audit <path> | on | off
---

# /ca:prune — session transcript pruner

Long sessions die when the JSONL transcript fills the context window with bulk: `toolUseResult`
sidecars, oversized tool outputs, thinking blocks, MCP/shell noise, stale file reads. The pruner
trims that bulk at safe quiescence boundaries while leaving the `uuid`/`parentUuid` chain, every
line type (including unknown future types), and the K most recent tool-bearing turns verbatim.
Gains land at **`claude --resume` / restart** and the next compaction — not the current turn, because
the running CLI sends its in-memory history to the API, not the file.

## Argument

`$ARGUMENTS` is one of:

- `status` (default) — report cumulative reduction and service state for this session from
  `~/.codearbiter/prune-state.json`, and whether `CODEARBITER_PRUNE` is `on`/`dry`/`off`. When
  the service has run in `dry` mode, every would-be prune is also recorded — one JSONL row per
  decision, across all sessions — to the shared data-collection log
  `~/.codearbiter/metrics/prune-dry.jsonl` (override with `CODEARBITER_PRUNE_METRICS`). That log is
  the evidence base for the `dry`→`on` decision: a clean record (every row `verdict: dry-run`,
  `validation_errors: 0`) over a representative set of sessions is the signal that enabling is safe.
- `dry` — copy the live transcript to a scratch path and run a dry-run analysis; present the
  per-strategy reduction table. Never writes to the live file.
- `run <path>` — prune the target with `--execute`. Targets a **copy or an old/inactive
  transcript only** — the tool refuses a recently-modified file by construction.
- `audit <path>` — read-only integrity report: line-parse, uuid chain, tool-pair coverage,
  condensation markers.
- `on` / `off` — guidance on enabling or disabling the after-each-turn service.

## Flow

1. **status / dry / audit** — run the backing tool and present its output verbatim:
   ```
   python3 "${CLAUDE_PLUGIN_ROOT}/hooks/prune-transcript.py" <subcommand> [<path>]
   ```
   For `dry`, copy the live transcript to `<path>.copy.jsonl` first, then analyze the copy.

2. **run** — confirm the path is a copy or an inactive session, then:
   ```
   python3 "${CLAUDE_PLUGIN_ROOT}/hooks/prune-transcript.py" <path> --execute [--tier T]
   ```
   Present the per-strategy reduction report; follow with `audit` on the result.

3. **on/off** — explain the after-each-turn service: `UserPromptSubmit` and `PreCompact` hooks
   prune at safe quiescence points, always exit 0, and never block the prompt. Tiers: `gentle`
   (sidecar + oversize clamp), `standard` (+ reasoning fold, aged/MCP/shell), `aggressive`
   (+ stale-read, reminder dedup, image evict). Config via `CODEARBITER_PRUNE` (`off`|`dry`|`on`,
   ships **off**), `CODEARBITER_PRUNE_TIER`, `CODEARBITER_PRUNE_KEEP_RECENT` (the K most recent
   tool **turns** kept verbatim — each turn is an assistant tool_use plus its results),
   `CODEARBITER_PRUNE_MAXBYTES`. Enabling is the user's explicit choice — never set it unbidden.
   In `dry` mode the service writes no transcript but appends each would-be prune to
   `~/.codearbiter/metrics/prune-dry.jsonl` (path override: `CODEARBITER_PRUNE_METRICS`) for
   data collection; in `on` mode the executed prunes are recorded in `~/.codearbiter/prune.log`.
   If a prior service-mode prune was killed mid-write, the next run self-heals the transcript
   from the newest backup in `~/.codearbiter/prune-backups/` before doing anything else.

## When NOT to use

- Context bar nowhere near compaction — the most recent turns are protected anyway.
- Install health → `/ca:doctor`.
- Project progress → `/ca:status`.

## Hard gate

- MUST NOT run `--execute` against the **live** session's transcript — the tool refuses a
  recently-modified file by construction; manual `run` targets copies or old sessions only.
- MUST surface the resume-only-gains limitation whenever a user expects a live-context drop.
- MUST NOT enable the service (`CODEARBITER_PRUNE=on`) on behalf of the user — explain and let
  them decide.
