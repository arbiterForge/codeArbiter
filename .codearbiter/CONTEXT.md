---
arbiter: enabled
stage: 2
---
<!--INITIALIZED-->

# Project: codeArbiter

The orchestration framework itself, plus siblings. This repo is a
**marketplace of three plugins** (ADR-0007, ADR-0011): `ca`, the governance/orchestration
plugin for Claude Code; `ca-codex`, the same governance kernel for Codex CLI (beta until
live-Codex verification, ADR-0011); and `ca-sandbox`, an infrastructure plugin. This `.codearbiter/` directory is the v2
project-state store — root-level, outside `.claude/`, so it survives even if the
codeArbiter plugin is uninstalled. The `arbiter: enabled` frontmatter above is the
single activation flag: it gates both the SessionStart persona injection and the
arbiter statusline segments.

## Identity
Sibling plugins in one marketplace (ADR-0007, ADR-0011):

- **`ca` (governance)** — the kernel. A Claude Code plugin that routes work through
  gated skills and reviewer agents, enforces spec-driven TDD and commit gates,
  decides via SMARTS, and keeps an append-only audit trail. Decisive, terse,
  high-authority. Its identity and gates are unchanged by the siblings.
- **`ca-codex` (governance, Codex CLI host)** — the same kernel targeting Codex CLI.
  Generated from shared sources (`core/pysrc/`, `core/surface/`) alongside `ca`;
  CI enforces byte-identity between `core/` and each plugin's vendored copy. One
  `.codearbiter/` store per project serves both hosts. Beta until live-Codex
  verification (ADR-0011).
- **`ca-sandbox` (infrastructure)** — a locally-hosted GitHub-Codespace equivalent
  that pulls an untrusted repo into an ephemeral, isolated container (no host-FS
  access; configurable network), explore, tear down. Infrastructure, not governance —
  arbiter knows about it and integrates with it, but it is not part of the governance
  kernel. Independent of `ca`: CI is path-scoped and version bumps are per-plugin.

## Scope
- `ca` framework source: `plugins/ca/` — `ORCHESTRATOR.md`, `skills/`, `commands/`,
  `agents/`, `hooks/`, `tools/`.
- Shared kernel sources: `core/pysrc/` (host-neutral hook logic) and `core/surface/`
  (markdown templates), materialized into `plugins/ca/` and `plugins/ca-codex/` by
  `tools/sync-core.py` / `tools/build-surface.py` (ADR-0011).
- `ca-codex` host adapter: `plugins/ca-codex/` — `.codex-plugin/` manifest, hook shims,
  generated skills/agents payloads.
- `ca-sandbox` infrastructure source: `plugins/ca-sandbox/` — `tools/`, `skills/`,
  `commands/`. Adds host deps (Docker, nixpacks) scoped to this plugin only.
- Shared project state lives here in `.codearbiter/`.

## NOT this project
Not a runtime-vendored framework — multi-host support is build-time generation from one
core with CI-enforced byte-identity (ADR-0011), never v1's symlink/dual-root machinery.
Not an enterprise compliance suite. Hosts are Claude Code and Codex CLI only; further
hosts require a new ADR. Solo developer. `ca-sandbox` (ADR-0007) and `ca-codex`
(ADR-0011) are deliberate, recorded exceptions, not precedent for arbitrary co-location.
See `legacy/ASSESSMENT.md` for the v2 cut list.
