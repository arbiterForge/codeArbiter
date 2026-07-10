# Claude / Codex parity ledger

Status of every codeArbiter surface on each host (ADR-0011, codex-support
campaign). The `ca` plugin targets Claude Code; the `ca-codex` sibling targets
OpenAI Codex CLI (minimum rust-v0.134.0, the first release with plugin-bundled
hooks on by default). Both plugins vendor the same `core/pysrc/` Python core
byte-for-byte (`tools/sync-core.py --check` is the CI gate); the only per-host
Python file is each plugin's `hooks/_host.py`.

`ca-codex` is BETA (0.2.0): every shipped behavior is test-covered
(`.github/scripts/test_codex_adapter.py`), but the live-fire items from the M0
spike (stdout persona injection, trust-review walkthrough, exit-2 stderr
feedback on a real install) remain pending a live Codex verification pass.

## Enforcement surface

| Claude surface | Codex status | Notes |
|---|---|---|
| SessionStart persona injection (ORCHESTRATOR.md + startup state) | SHIPPED (M2) | Same core entry `session-start.py`. Statusline heal is skipped via the `has_statusline=False` capability flag. Live stdout-injection verification pending. |
| PreToolUse Bash gate (`pre-bash.py`: H-01/02/03/05/09b/10b/11/14/18/19/20) | SHIPPED (M2) | Codex's exec tool is also named `Bash` with the same `{command}` payload; the entry is byte-identical. |
| PreToolUse Write gate (`pre-write.py`: H-05/11/18/19) | SHIPPED (M2) | Registered for `apply_patch\|Write\|Edit`. The apply_patch envelope is parsed into per-file ops mirroring Codex's lenient parser (CRLF and whitespace-indented markers included); each op hits the same guards as a Claude Write. An envelope the adapter cannot decompose blocks outright (H-21 opaque, fail-closed) rather than passing unguarded. |
| PreToolUse Edit gate (`pre-edit.py`, incl. H-05 tail-anchored append) | LEDGERED OUT on Codex | Codex has no separate edit tool: every edit arrives as an `apply_patch` hunk, which is positional and cannot be verified as a pure tail append. Patch ops against append-only audit logs therefore BLOCK outright on Codex (append via shell `>>` instead, which `pre-bash.py` permits). Strictly more conservative than Claude, never less. |
| PreToolUse Read injection (`pre-read.py`, H-12 governed-file notices on Read) | LEDGERED OUT | Codex has no read tool (source-verified, spike item 2): file reads happen via shell, so there is no Read event to hook. The H-12 notice still fires post-write via `post-write-edit.py`. |
| PostToolUse Write/Edit nudges (`post-write-edit.py`: H-07/09/10/12/13/15/16/17) | SHIPPED (M2) | Registered for `apply_patch\|Write\|Edit`; nudges run per patched file over its added lines. |
| prune-transcript: prune ENGINE (PreCompact + the UserPromptSubmit prune path) | LEDGERED OUT | Locked out of parity by the campaign decision record: the pruner rewrites Claude-Code-format transcript JSONL, a format Codex does not share. Gated off via `has_prunable_transcript=False`; PreCompact is not registered. |
| prune-transcript: audit staleness-warn (CONFIRM-09, UserPromptSubmit) | SHIPPED (M2) | Host-neutral (reads `.codearbiter` audit logs, not the transcript), so it IS registered on Codex UserPromptSubmit; the same entry returns before the prune engine on hosts without a prunable transcript. |
| statusline (renderer, heal, `/ca:statusline`) | LEDGERED OUT | No statusline surface exists on Codex. `governance_line()` stays in core for the startup briefing, which Codex does get. |
| `.git/hooks` git-enforce backstop (`_githooks.py`) | SHIPPED (M2) | Host-agnostic; installed by `session-start.py` on both hosts. |
| Update-available notice | DEGRADED on Codex | `_updatelib.installed_version` reads `.claude-plugin/plugin.json`; `ca-codex` ships `.codex-plugin/plugin.json`, so the notice silently self-suppresses. Revisit in M5 (release/distribution). |

## Payload and packaging

| Claude surface | Codex status | Notes |
|---|---|---|
| `.claude-plugin/plugin.json` (ca 2.8.x) | SHIPPED: `plugins/ca-codex/.codex-plugin/plugin.json`, independent SemVer from 0.1.0 (ADR-0007 precedent) | Codex also accepts the `.claude-plugin/` manifest path, but the native path is used. |
| `hooks/hooks.json` dual `python3` + probe-fallback registration | SHIPPED: single registration per event with a `commandWindows` variant (`python` instead of `python3`) | Codex's hook schema is Claude-compatible plus `commandWindows`/`timeout`/`statusMessage` (spike item 5). A `\|\|`-chained fallback inside ONE command would re-run the gate against drained stdin on a legitimate exit-2 block and swallow it, so the Windows variant is a plain `python` invocation (stock Windows `python3` is often the Store stub). |
| `.claude-plugin/marketplace.json` | SHIPPED: `.agents/plugins/marketplace.json` | The catalog shape mirrors the Claude marketplace schema, which Codex accepts per the spike's loader reading; the exact native catalog schema could not be re-verified offline during M2, so any live-install mismatch lands on the live-verification pass. |

## Command/skill surface (SHIPPED, M3 — generated from `core/surface/`)

Both plugins' markdown surfaces are rendered from one template tree by
`tools/build-surface.py`; CI (`surface` job, `--check`) fails on drift in
either direction. Runtime-emitted command references (startup briefing, gate
messages, doctor, the init scaffold) flow through the same per-host seam
(`Host.cmd_ref`), so briefings and docs agree.

| Claude surface | Codex status | Notes |
|---|---|---|
| 39 commands (`/ca:*`) | SHIPPED (M3): 37 generated `ca-`-prefixed entry skills (`skills/ca-*/SKILL.md`) + a generated `skills/INDEX.md` catalog | `ca-init` gives Codex-only users standalone opt-in (DECISION-0013, #287). The two exceptions are ledgered below. |
| `/ca:statusline` | LEDGERED OUT | No statusline surface exists on Codex; no `ca-statusline` skill renders. Cross-references are host-conditional in the templates. |
| `/ca:prune` | LEDGERED OUT | The prune ENGINE is already ledgered out (above); with no engine there is no command to ship. The audit staleness-warn half runs hook-side without one. |
| 22 skills (orchestrator routines) | SHIPPED (M3): rendered to `routines/` | Kept out of the Codex skill-discovery root so routine bodies never register as unprefixed user-invocable skills (and six names collide with commands). |
| `includes/`, `COMMANDS.md`, `SPRINT.md`, `ORCHESTRATOR.md` | SHIPPED (M3) | ORCHESTRATOR.md now deliberately diverges per host (Codex persona speaks `$ca-` skill vocabulary); the byte-identity guard (#262) is retired in favor of the generator's `--check`. `includes/codex-host-notes.md` is Codex-only (tool mapping, degraded paths, sandbox caveats). |
| descriptive statusline genre mention (`includes/anti-slop-design/medium-cli.md`) | SHIPPED as-is | Design guidance about statuslines as a CLI output genre — host-neutral prose, not an instruction to use a Codex statusline. |
| `--farm` execution backend (`tools/farm.js`, `tools/plan.schema.json`) | PENDING (M5) | The farm worker files are not vendored into ca-codex; `--farm` degrades to the premium-subagent path (see `includes/codex-host-notes.md`). Packaging is an M5 distribution decision. |
| `${CLAUDE_PLUGIN_ROOT}` in skill PROSE | LIVE-PENDING | Hooks receive the env var (source-verified); whether Codex expands it in skill body prose is unverified until the live pass. Fallback: plugin-relative paths, one renderer rule. |

## Pending milestones

| Claude surface | Codex status |
|---|---|
| 28 agents + review chains (checkpoint/tribunal/SDD) | M4: `.codex/agents/*.toml` scaffolded by `ca-init` with a doctor staleness check (plugins cannot ship subagents on Codex, spike item 7); dispatch batching under `max_threads 6` / `max_depth 1`. Until M4, review/author roles run inline per `includes/codex-host-notes.md` — never skipped. |
| doctor live-fire probe, trust-state detection | M2 exit test is defined; the doctor probe extension and the trust-review walkthrough need the live install. |
| release workflow / CI path filters for `plugins/ca-codex/` | Largely landed early (release-codex, version-bump-codex, cold-install matrix, adapter suite, and — with M3 — `prose-codex` + the `surface` job); remaining M5: distribution docs, update-notice fix (above), farm packaging. |
