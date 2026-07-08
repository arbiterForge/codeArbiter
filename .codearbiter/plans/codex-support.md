# Codex CLI Support — Shared Core + Thin Host Adapters, Full Parity

## Context

codeArbiter today enforces its rigor only under Claude Code: the `ca` plugin's stdlib-Python hooks (SessionStart persona injection, exit-2 blocking PreToolUse gates), 44 commands, 23 skills, and 30 agents. The goal is to enforce the **same rigor under OpenAI Codex CLI**, sharing the **same `.codearbiter/` project context folder** — one governance store, two hosts.

This is newly feasible: Codex v0.142.x (verified July 2026) has near-parity extension points — a plugin system (`.codex-plugin/plugin.json` + marketplace catalogs) bundling **hooks (Claude-Code-like `hooks.json`, blocking via exit 2 + stderr), skills (Anthropic's SKILL.md format), and MCP servers**; SessionStart/PreToolUse/PostToolUse/UserPromptSubmit events; project-scoped `.codex/config.toml`; repo-shippable subagents (`.codex/agents/*.toml`, `sandbox_mode` per role). Custom prompts are deprecated in favor of skills. No statusline analogue.

**User decisions (locked):** full parity as the end state · shared core + thin adapters packaging · prune-transcript ledgered out of parity (like statusline) · AGENTS.md fallback acceptable if SessionStart stdout injection fails on Codex · `ca-` prefix for all Codex skill names · independent SemVer for `ca-codex` starting 0.1.0 (ADR-0007 precedent). Agent-scaffolding via `ca-init` is the default if plugins can't ship subagents (user expressed no preference; spike-contingent).

**Governance prerequisite:** `.codearbiter/CONTEXT.md` currently declares "Claude Code only" as a scope statement. An ADR must amend it before anything user-visible ships (M0). → Recorded as ADR-0011 (2026-07-08).

**Approval caveat (2026-07-08):** approved as **beta only** — the maintainer has no Codex subscription until ~2026-07-09, so live-fire spike items (stdout injection, trust review, exit-2 feedback) are deferred to a live-verification pass; source-level verification against `openai/codex` proceeds immediately. `ca-codex` carries a beta / Feature Forge preview label until live verification completes.

## Architecture

### Python core — `core/pysrc/`, vendored at build time

- Move all `plugins/ca/hooks/_*lib.py` shared modules to `core/pysrc/`; extract entry-script logic into importable `core/pysrc/entries/*.run(host)` functions (session_start, pre_exec, pre_write, pre_edit, pre_read, post_write_edit, git_enforce, doctor, init_codearbiter, …).
- `tools/sync-core.py` (stdlib) copies `core/pysrc/` byte-for-byte into `plugins/ca/hooks/_core/` and `plugins/ca-codex/hooks/_core/`; **CI fails if any vendored copy differs** (regenerate-and-diff, same pattern as `check_badge_consistency.py`). Checked-in copies keep each installed plugin self-contained — no runtime cross-plugin imports, no v1 symlink/dual-root resurrection. ADR-0004 stdlib-only posture unchanged.
- Each plugin's `hooks/*.py` entry scripts become ~10-line shims: sys.path insert of `_core`, construct host from the plugin's `_host.py`, call the entry's `run(host)`.

### The host seam — `core/pysrc/hostapi.py` + per-plugin `_host.py`

`_host.py` is the ONLY per-host Python file. It provides:
- `project_root()` — host env var (`CLAUDE_PROJECT_DIR`; Codex equivalent TBD by spike) → stdin payload `cwd` → `git rev-parse` → `os.getcwd()`. Strict generalization of `_hooklib.project_root()`.
- `plugin_root()` — `CLAUDE_PLUGIN_ROOT` / Codex equivalent → `__file__`-relative fallback (already exists in session-start.py).
- `normalize_tool()` → `{EXEC, WRITE, EDIT, READ, OTHER}`. Claude: `Bash|PowerShell→EXEC`, `Write→WRITE`, `Edit|MultiEdit|NotebookEdit→EDIT`, `Read→READ`. Codex: actual tool names from spike (`shell`/`apply_patch`/…).
- **Input-shape translation** — Codex's `apply_patch` payload differs from Claude's `Write/Edit` (`file_path`/`old_string`/`new_string`); the Codex `_host.py` translates to the canonical shape core expects. This is the largest genuine adapter body.
- Blocking contract stays exit-2 + stderr on both hosts (docs-confirmed on Codex; verify in spike).

### Markdown surface — `core/surface/`, dev-time generation, checked-in output

Canonical templates in `core/surface/{commands,skills,agents,includes}/` with three tokens:

| Token | Claude render | Codex render |
|---|---|---|
| `{{PLUGIN_ROOT}}` | `${CLAUDE_PLUGIN_ROOT}` | Codex plugin-root convention (spike; fallback: skill-relative paths) |
| `{{PROJECT_DIR}}` | `${CLAUDE_PROJECT_DIR}` | "the project root" / cwd convention |
| `{{CMD:commit}}` | `/ca:commit` | `$ca-commit` (skill mention) |

`tools/build-surface.py` (stdlib) renders both plugin trees; outputs checked in; CI verifies clean regeneration. Coupling counts (measured): 73 files reference `${CLAUDE_PLUGIN_ROOT}`, 79 `${CLAUDE_PROJECT_DIR}`, all 44 commands use `/ca:`, only 8 skills do. Skills are near-verbatim; commands/agents carry the bulk of substitutions.

## Full-parity mapping (key rows)

| Claude surface | Codex equivalent |
|---|---|
| `.claude-plugin/plugin.json` (ca 2.8.x) | `plugins/ca-codex/.codex-plugin/plugin.json`, independent SemVer from 0.1.0 |
| SessionStart stdout persona (ORCHESTRATOR.md, 8.2 KB) | Same mechanism; verified fallback = generated staleness-checked AGENTS.md (fits 32 KiB cap) + hook emits live state only |
| PreToolUse gates (pre-bash/write/edit/read) | PreToolUse on Codex tool names via adapter; pre-write/pre-edit may merge if Codex funnels edits through one tool |
| prune-transcript (UserPromptSubmit/PreCompact) | **Ledgered out** — Codex-safe stub; `docs/parity.md` records why |
| statusline (+ heal, `/ca:statusline`) | **Ledgered out** — no Codex analogue; `governance_line()` stays in core for the briefing |
| `_githooks.py` git backstop | Identical, host-agnostic; add idempotence test for dual-plugin installs |
| 44 commands | 44 generated Codex skills `ca-commit`, `ca-feature`, … (skills are un-namespaced; prefix prevents collisions) |
| 23 skills | Same SKILL.md format, `ca-` prefixed, near-verbatim after tokens |
| 30 agents (`tools:` allowlist) | Generated `.codex/agents/*.toml`; reviewers `sandbox_mode="read-only"` (mechanically STRONGER than Claude's Bash-permitting allowlist), authors `workspace-write`. Shipped in-plugin if possible, else scaffolded by `ca-init` with doctor staleness check |
| Review chains (checkpoint/tribunal/SDD) | Codex subagents; batch dispatch under `max_threads 6` (tribunal has 11 lenses); `max_depth 1` may force the orchestrator to drive tdd phases instead of nesting |
| doctor | Shared core + per-host probe list (trust state, hooks live-fire, `.codex/agents` staleness, config.toml wiring) |
| marketplace | `.agents/plugins/marketplace.json` at repo root alongside the existing `.claude-plugin/marketplace.json` |
| farm | Reused as-is (already host-orthogonal) |

`.codearbiter/` stays host-neutral and **shared** — one store, both hosts, same repo. Reword the `CLAUDE_PROJECT_DIR` mentions in `security-controls.md` and the `init-codearbiter.py` scaffold templates host-neutrally.

## Milestones

**M0 — Spike + governance (gates everything).**
- `/ca:spike` on a live Codex install answering: ① SessionStart stdout→context semantics (linchpin — decides persona design); ② actual tool names + `tool_input` shapes for exec/write/edit/read; ③ plugin `hooks.json` format compatibility + per-entry stdin (the `python3 || python` Windows fallback depends on it) + Windows registration form; ④ exit-2 stderr actually fed back to the model post trust-review; ⑤ trust-review UX for ~16 hook scripts (may motivate consolidating registrations); ⑥ can plugins ship subagents, and does prose reliably spawn a named subagent; `max_depth 1` implications; ⑦ env vars available to Codex hooks; ⑧ dual-host coexistence in one repo (git-hook shim install race).
- **ADR-0011**: amend CONTEXT.md scope (Claude Code only → multi-host), authorize `ca-codex` third plugin with independent versioning (extends ADR-0007), record shared-core + generated-payload architecture incl. CI byte-identity contract, reaffirm ADR-0004 for `core/pysrc/`.

**M1 — Shared-core extraction (pure refactor, `/ca:refactor` lane).** `core/pysrc/` + `hostapi.py` + Claude `_host.py` with today's exact values; `sync-core.py` + CI byte-identity job; ca entry scripts become shims. Existing test suites (`plugins/ca/hooks/tests/` ~36 files, `.github/scripts/test_*.py`) green — subprocess entry-script contract preserved; only import paths change in tests that import libs directly.

**M2 — Codex enforcement core.** Scaffold `plugins/ca-codex/` (`.codex-plugin/plugin.json`, `hooks/hooks.json` per M0 findings, `_host.py`, vendored `_core/`). Wire session-start (persona + state + git-hook install + briefing; no statusline heal), pre-exec, pre-write/edit/read, post-write-edit, git-enforce, init, doctor; prune stub. `.agents/plugins/marketplace.json`; install + trust-review walkthrough. **Exit test:** Codex session in an arbiter-enabled repo → persona injects; editing `overrides.log` by hand and `git commit --no-verify` are BLOCKED; doctor live-fire probe passes.

**M3 — Command/skill surface.** Markdown → `core/surface/` templates; `build-surface.py`; regenerated `plugins/ca/{commands,skills,includes}` **byte-identical to today** (CI-diff proves zero Claude-side change), plus the Codex skill tree. Extend `check-plugin-refs.py` (already plugin-parameterized) to `ca-codex`; Codex COMMANDS.md analogue.

**M4 — Agents + review chains.** Agent templates → Claude `agents/*.md` (unchanged) + Codex TOMLs; ship-in-plugin vs `ca-init` scaffold per M0 finding ⑥. Validate checkpoint/tribunal/subagent-driven-development under `max_threads 6`/`max_depth 1`; adapt dispatch batching in affected skills.

**M5 — Distribution/release/docs.** Parameterize `.github/workflows/release.yml` over plugin (currently hard-coded to `plugins/ca/`); `_releaselib.py` bump-guard path-scoped to `plugins/ca-codex/`; CI path filters — `core/**` triggers **both** plugin suites (new rule). Site/README/install docs; **`docs/parity.md` ledger** (statusline, prune-transcript, M0-discovered gaps).

## Critical files

- `plugins/ca/hooks/_hooklib.py` — the host seam to generalize (project_root / read_input / block)
- `plugins/ca/hooks/session-start.py` — linchpin injection + git-hook install + statusline heal to split by host
- `plugins/ca/hooks/hooks.json` — registration shape to mirror in `.codex-plugin` form
- `.github/scripts/check-plugin-refs.py` — extends to ca-codex; models the regenerate-and-diff consistency pattern
- `.github/workflows/release.yml` + `.github/scripts/_releaselib.py` — per-plugin release parameterization
- New: `core/pysrc/` (moved `_*lib.py` + `entries/` + `hostapi.py`), `core/surface/`, `tools/sync-core.py`, `tools/build-surface.py`, `plugins/ca-codex/`

## Verification

- **M1:** full existing suite green unmodified (behavioral-parity proof for the refactor); CI byte-identity job passes.
- **M2:** live Codex exit test above, on Windows and one POSIX OS; cold-install matrix (`test_hooks_cold_install.py` REAL/STUB/NONE python) extended to ca-codex entries.
- **M3:** regeneration-clean CI job; Claude tree byte-identical pre/post templating.
- **Adapter contract tests (new, the parity proof):** canonical scenario table (block no-verify commit, block audit-log rewrite, allow tail-append, dormant repo no-op, malformed stdin fail-open) run as real subprocess invocations of BOTH plugins' entry scripts with host-shaped payload fixtures (Codex fixtures captured during M0); same verdict matrix must hold for both hosts.
- **CI matrix:** existing 3-OS coverage; path-scoped jobs per plugin; `core/**` → both. Live-Codex integration stays manual (stretch: doctor live-fire under `codex exec` in CI).

## Risks

1. SessionStart stdout injection unverified on Codex — fallback (AGENTS.md persona) is pre-approved, but decide only after the spike.
2. Codex tool names / `apply_patch` input shape — the whole gate surface keys off this; spike item ②.
3. Trust-review friction — every Codex user must approve the hooks once; docs must walk it, doctor must detect un-trusted state.
4. Codex is moving fast (hooks/plugins are recent); pin a minimum Codex version in the plugin docs and re-verify on Codex releases.
5. Two-payload maintenance cost is real even with generation — the CI consistency jobs are the load-bearing defense; none of them may be optional.
