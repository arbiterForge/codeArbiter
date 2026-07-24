---
arbiter: enabled
stage: 2
---
<!--INITIALIZED-->

# Project: codeArbiter

The orchestration framework itself, plus siblings. This repo contains
**four sibling plugins** (ADR-0007, ADR-0011, ADR-0013): `ca`, the governance/orchestration
plugin for Claude Code; `ca-codex`, the same governance kernel for Codex CLI;
`ca-pi`, the same kernel for Pi; and `ca-sandbox`, an infrastructure plugin. The
first three are the **three governance hosts**. This `.codearbiter/` directory is the v2
project-state store — root-level, outside `.claude/`, so it survives even if the
codeArbiter plugin is uninstalled. The `arbiter: enabled` frontmatter above is the
single activation flag: it gates both the SessionStart persona injection and the
arbiter statusline segments.

## Identity
Four sibling plugins in one repository (ADR-0007, ADR-0011, ADR-0013):

- **`ca` (governance)** — the kernel. A Claude Code plugin that routes work through
  gated skills and reviewer agents, enforces spec-driven TDD and commit gates,
  decides via SMARTS, and keeps an append-only audit trail. Decisive, terse,
  high-authority. Its identity and gates are unchanged by the siblings.
- **`ca-codex` (governance, Codex CLI host)** — the same kernel targeting Codex CLI.
  Generated from shared sources (`core/pysrc/`, `core/surface/`) alongside `ca`;
  CI enforces byte-identity between `core/` and each plugin's vendored copy. One
  `.codearbiter/` store per project serves all three governance hosts. Beta until
  live-Codex verification (ADR-0011).
- **`ca-pi` (governance, Pi host)** — the same generated kernel behind a thin
  TypeScript extension and the shared stdlib-only Python core. The Git-installed
  package is independently versioned, requires Node 22.19+ and Python 3, and
  shares the project's `.codearbiter/` store with Claude Code and Codex CLI.
- **`ca-sandbox` (infrastructure)** — a locally-hosted GitHub-Codespace equivalent
  that pulls an untrusted repo into an ephemeral, isolated container (no host-FS
  access; configurable network), explore, tear down. Infrastructure, not governance —
  arbiter knows about it and integrates with it, but it is not part of the governance
  kernel. Independent of `ca`: CI is path-scoped and version bumps are per-plugin.

## Scope
- `ca` framework source: `plugins/ca/` — `ORCHESTRATOR.md`, `skills/`, `commands/`,
  `agents/`, `hooks/`, `tools/`.
- Shared kernel sources: `core/pysrc/` (host-neutral hook logic) and `core/surface/`
  (markdown templates), materialized into `plugins/ca/`, `plugins/ca-codex/`, and
  `plugins/ca-pi/` by `tools/sync-core.py` / `tools/build-surface.py` (ADR-0011).
- `ca-codex` host adapter: `plugins/ca-codex/` — `.codex-plugin/` manifest, hook shims,
  generated skills/agents payloads.
- `ca-pi` host adapter: `plugins/ca-pi/` — Git package metadata, generated policy
  payloads, thin Python host shim, TypeScript extension sources, and built parent,
  child, and Windows containment artifacts.
- `ca-sandbox` infrastructure source: `plugins/ca-sandbox/` — `tools/`, `skills/`,
  `commands/`. Adds host deps (Docker, nixpacks) scoped to this plugin only.
- Shared project state lives here in `.codearbiter/`.

## NOT this project
Not a runtime-vendored framework — multi-host support is build-time generation from one
core with CI-enforced byte-identity (ADR-0011), never v1's symlink/dual-root machinery.
Not an enterprise compliance suite. Governance hosts are Claude Code, Codex CLI,
and Pi; further hosts require a new ADR. Solo developer. `ca-sandbox` (ADR-0007),
`ca-codex` (ADR-0011), and `ca-pi` (ADR-0013) are deliberate, recorded exceptions,
not precedent for arbitrary co-location.
See `legacy/ASSESSMENT.md` for the v2 cut list.
