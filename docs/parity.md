# Claude / Codex parity ledger

Status of every codeArbiter surface on each host (ADR-0011, codex-support
campaign). The `ca` plugin targets Claude Code; the `ca-codex` sibling targets
OpenAI Codex CLI (minimum rust-v0.134.0, the first release with plugin-bundled
hooks on by default). Both plugins vendor the same `core/pysrc/` Python core
byte-for-byte (`tools/sync-core.py --check` is the CI gate); the only per-host
Python file is each plugin's `hooks/_host.py`.

`ca-codex` is BETA (0.1.0): every shipped behavior is test-covered
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
| prune-transcript (UserPromptSubmit/PreCompact backend) | LEDGERED OUT | Locked out of parity by the campaign decision record: the pruner rewrites Claude-Code-format transcript JSONL, a format Codex does not share. Not registered in `ca-codex/hooks/hooks.json`. |
| statusline (renderer, heal, `/ca:statusline`) | LEDGERED OUT | No statusline surface exists on Codex. `governance_line()` stays in core for the startup briefing, which Codex does get. |
| `.git/hooks` git-enforce backstop (`_githooks.py`) | SHIPPED (M2) | Host-agnostic; installed by `session-start.py` on both hosts. |
| Update-available notice | DEGRADED on Codex | `_updatelib.installed_version` reads `.claude-plugin/plugin.json`; `ca-codex` ships `.codex-plugin/plugin.json`, so the notice silently self-suppresses. Revisit in M5 (release/distribution). |

## Payload and packaging

| Claude surface | Codex status | Notes |
|---|---|---|
| `.claude-plugin/plugin.json` (ca 2.8.x) | SHIPPED: `plugins/ca-codex/.codex-plugin/plugin.json`, independent SemVer from 0.1.0 (ADR-0007 precedent) | Codex also accepts the `.claude-plugin/` manifest path, but the native path is used. |
| `hooks/hooks.json` dual `python3` + probe-fallback registration | SHIPPED: single registration per event with a `commandWindows` variant (`python` instead of `python3`) | Codex's hook schema is Claude-compatible plus `commandWindows`/`timeout`/`statusMessage` (spike item 5). A `\|\|`-chained fallback inside ONE command would re-run the gate against drained stdin on a legitimate exit-2 block and swallow it, so the Windows variant is a plain `python` invocation (stock Windows `python3` is often the Store stub). |
| `.claude-plugin/marketplace.json` | SHIPPED: `.agents/plugins/marketplace.json` | The catalog shape mirrors the Claude marketplace schema, which Codex accepts per the spike's loader reading; the exact native catalog schema could not be re-verified offline during M2, so any live-install mismatch lands on the live-verification pass. |

## Pending milestones

| Claude surface | Codex status |
|---|---|
| 44 commands (`/ca:*`) | M3: generated `ca-`-prefixed Codex skills from `core/surface/` templates. Until then the injected persona still names `/ca:*` commands that do not exist on Codex; `/ca-init` opt-in is likewise M3. |
| 23 skills | M3: same SKILL.md format, `ca-` prefixed. |
| 30 agents + review chains (checkpoint/tribunal/SDD) | M4: `.codex/agents/*.toml` scaffolded by `ca-init` with a doctor staleness check (plugins cannot ship subagents on Codex, spike item 7); dispatch batching under `max_threads 6` / `max_depth 1`. |
| doctor live-fire probe, trust-state detection | M2 exit test is defined; the doctor probe extension and the trust-review walkthrough need the live install. |
| release workflow / CI path filters for `plugins/ca-codex/` | M5. `check-plugin-refs.py` extension to ca-codex is also M5. |
