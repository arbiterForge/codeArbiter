# Spike — Codex CLI extension surface for ca-codex (M0)

**Question:** does Codex CLI provide the extension points the governance kernel needs, and
what are the exact contracts? **Method:** source verification against `openai/codex` main
@ rust-v0.143.0 (2026-07-08) — no live install available until ~2026-07-09, so everything
below is SOURCE-CONFIRMED with file paths unless marked LIVE-PENDING. Feeds
`.codearbiter/plans/codex-support.md` (ADR-0011).

## Verdict

GO. Every load-bearing assumption holds at the source level. Minimum Codex version:
**rust-v0.134.0** (first release with plugin-bundled hooks on by default; discovery landed
0.128.0 behind a flag, flag removed for 0.134.0). Two design corrections fall out
(pre-read, subagents — below).

## Confirmed contracts

1. **Hook stdin payload** (`codex-rs/hooks/src/schema.rs`, `events/pre_tool_use.rs`):
   snake_case JSON on stdin — `session_id`, `turn_id` (Codex extension), `transcript_path`,
   `cwd`, `hook_event_name`, `model`, `permission_mode`; PreToolUse adds `tool_name`,
   `tool_input`, `tool_use_id`; PostToolUse adds `tool_response`; SessionStart adds
   `source` (`startup|resume|clear|compact`), no `turn_id`. Ten events incl. SessionStart,
   PreToolUse, PostToolUse, UserPromptSubmit, PreCompact, Stop.
2. **Tool names** (`core/src/tools/hook_names.rs`): exec = canonical **`Bash`**
   (`tool_input: {"command": ...}`); file writes/edits = **`apply_patch`**, with `Write` and
   `Edit` as *matcher-only aliases* (payload unchanged); MCP tools = `mcp__<server>__<tool>`.
   **There is no read tool** — file reads happen via shell (hooks see `Bash`) or
   `view_image`. Matchers: exact-split on `|` for `[A-Za-z0-9_|]` patterns, else unanchored
   regex; `*`/empty = match-all.
3. **SessionStart stdout → context** (`events/session_start.rs` L237–302,
   `core/src/hook_runtime.rs`): on exit 0, plain non-JSON stdout is injected verbatim as
   model context (camelCase `hookSpecificOutput.additionalContext` JSON also accepted).
   **The linchpin holds — no AGENTS.md fallback needed** (fallback stays pre-approved in
   ADR-0011 should live behavior differ).
4. **Blocking** (`events/pre_tool_use.rs` L208–285): exit 2 + **non-empty stderr** blocks,
   stderr fed back to the model. Exit 2 with empty stderr = hook failure, NOT a block —
   `_hooklib.block()` must always write a reason (it does). Other non-zero exits do not
   block. JSON `{"decision":"block"}` parsed only on exit 0.
5. **Plugin hooks.json** (`config/src/hook_config.rs`, `core-plugins/src/loader.rs`):
   default `hooks/hooks.json` under plugin root; **Claude-Code-compatible schema**, plus
   `timeout` (default 600 s), **`commandWindows`** (the JSON form has the Windows override —
   the dual `python3 || python` registration may be replaceable by it), `statusMessage`.
   Each handler runs as its own process with its own stdin copy (dual registration also
   works). Manifest path: `.codex-plugin/plugin.json` — **`.claude-plugin/plugin.json` is
   also accepted** (`utils/plugins/src/plugin_namespace.rs`).
6. **Env vars** (`hooks/src/engine/discovery.rs` L227–235): plugin hooks receive
   `PLUGIN_ROOT`, **`CLAUDE_PLUGIN_ROOT`** (explicit compat alias), `PLUGIN_DATA`,
   `CLAUDE_PLUGIN_DATA`. No project-dir var — hooks run in the session cwd and get `cwd`
   in the payload; `hostapi.project_root()` resolves payload-`cwd` → `git rev-parse`.
7. **Plugin components** (`core-plugins/src/manifest.rs`): skills, MCP servers, apps,
   hooks. **No agents component — subagents are NOT plugin-shippable.** M4's `ca-init`
   scaffold path (ADR-0011 §5) is the confirmed design, not a fallback.
8. **Skills discovery** (`core-skills/src/loader.rs` L290–410): repo `.codex/skills` and
   `.agents/skills` both live; user `~/.agents/skills` is the non-deprecated location;
   plugin skill roots included. Plugin `version` field is informational; no
   min-Codex-version compat field exists — pin the minimum in docs, and doctor should
   probe it at runtime.

## Design corrections adopted

- **pre-read has no Codex analogue** (no read tool): the file-scoped context injection
  (H-12-style governed-file notices on Read) cannot fire on Codex reads. Ledger as a
  parity exception alongside statusline/prune, or route the notice through PostToolUse on
  `Bash`; decide in M2.
- **Subagents ship via `ca-init` scaffold** into target repos' `.codex/agents/*.toml`
  with a doctor staleness check (now the primary design).
- **Trust gate**: plugin hooks run only after user approval of the handler hash
  (`discovery.rs` L527–545). "Hooks silently don't run" on a clean install ⇒ untrusted
  hash is the first suspect; doctor must detect the un-trusted state.

## LIVE-PENDING (needs the ~2026-07-09 Codex subscription)

- Trust-review UX walkthrough (`startup_hooks_review.rs`) — what the approval prompt
  shows for ~16 hook entries; may motivate consolidating registrations.
- End-to-end fire: persona injection, a real blocked `git commit --no-verify`, exit-2
  stderr surfaced to the model, `commandWindows` behavior on a real Windows install.
- Subagent spawn-from-skill-prose reliability and `max_depth 1` / `max_threads 6`
  implications for the review chains (M4 gate).
