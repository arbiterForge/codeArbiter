---
arbiter: enabled
stage: 2
---
<!--INITIALIZED-->

# Project: codeArbiter

The orchestration framework itself, plus an infrastructure sibling. This repo is a
**marketplace of two plugins** (ADR-0007): `ca`, the governance/orchestration plugin,
and `ca-sandbox`, an infrastructure plugin. This `.codearbiter/` directory is the v2
project-state store — root-level, outside `.claude/`, so it survives even if the
codeArbiter plugin is uninstalled. The `arbiter: enabled` frontmatter above is the
single activation flag: it gates both the SessionStart persona injection and the
arbiter statusline segments.

## Identity
Two sibling plugins in one marketplace (ADR-0007):

- **`ca` (governance)** — the kernel. A Claude Code plugin that routes work through
  gated skills and reviewer agents, enforces spec-driven TDD and commit gates,
  decides via SMARTS, and keeps an append-only audit trail. Decisive, terse,
  high-authority. Its identity and gates are unchanged by the sibling.
- **`ca-sandbox` (infrastructure)** — a locally-hosted GitHub-Codespace equivalent
  that pulls an untrusted repo into an ephemeral, isolated container (no host-FS
  access; configurable network), explore, tear down. Infrastructure, not governance —
  arbiter knows about it and integrates with it, but it is not part of the governance
  kernel. Independent of `ca`: CI is path-scoped and version bumps are per-plugin.

## Scope
- `ca` framework source: `plugins/ca/` — `ORCHESTRATOR.md`, `skills/`, `commands/`,
  `agents/`, `hooks/`, `tools/`.
- `ca-sandbox` infrastructure source: `plugins/ca-sandbox/` — `tools/`, `skills/`,
  `commands/`. Adds host deps (Docker, nixpacks) scoped to this plugin only.
- Shared project state lives here in `.codearbiter/`.

## NOT this project
Not a vendored/multi-platform framework. Not an enterprise compliance suite.
Claude Code only. Solo developer. `ca-sandbox` is the deliberate, recorded
infrastructure exception (ADR-0007), not a precedent for arbitrary co-location of a
third plugin. See `legacy/ASSESSMENT.md` for the v2 cut list.
