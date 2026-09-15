---
arbiter: enabled
stage: 2
---
<!--INITIALIZED-->

# Project: codeArbiter

The orchestration framework itself, plus its host adapters and infrastructure sibling.
The canonical governance kernel lives in `core/`; generated payloads carry it into the
Claude Code adapter (`ca`), Codex adapter (`ca-codex`), and Pi adapter (`ca-pi`). A
fourth sibling, `ca-sandbox`, is an infrastructure plugin (ADR-0007, ADR-0011,
ADR-0013). The first three are the **three governance hosts**. This `.codearbiter/`
directory is the v2
project-state store — root-level, outside `.claude/`, so it survives even if the
codeArbiter plugin is uninstalled. The `arbiter: enabled` frontmatter above is the
single activation flag: it gates both the persona injection and the arbiter
statusline segments, and every enforcement hook reads it — never the persona.

## Identity
One canonical governance kernel, three generated host adapters, and one infrastructure
sibling in the repository (ADR-0007, ADR-0011, ADR-0013):

- **`core/` (governance)** — the canonical governance kernel: shared stdlib-only
  Python and generated markdown sources. It is an internal source boundary, not a
  separately published or runtime package (ADR-0031).
- **`ca` (governance, Claude Code host)** — the Claude Code adapter. It routes work through
  gated skills and reviewer agents, enforces spec-driven TDD and commit gates,
  decides via SMARTS, and keeps an append-only audit trail. Decisive, terse,
  high-authority. Its host-native identity and gates are unchanged by the siblings.
- **`ca-codex` (governance, Codex CLI host)** — the Codex adapter. Generated from
  shared sources (`core/pysrc/`, `core/surface/`) alongside `ca`; it packages the
  shared role charters as resources for host-provided thread dispatch rather than
  registering native plugin agents.
  CI enforces byte-identity between `core/` and each plugin's vendored copy. One
  `.codearbiter/` store per project serves all three governance hosts (ADR-0011).
- **`ca-pi` (governance, Pi host)** — the Pi adapter: the same generated kernel behind a thin
  TypeScript extension and the shared stdlib-only Python core. The Git-installed
  package is independently versioned, requires Node 22.19+ and Python 3, and
  shares the project's `.codearbiter/` store with Claude Code and Codex CLI.
- **`ca-sandbox` (infrastructure)** — a locally-hosted GitHub-Codespace equivalent
  that pulls an untrusted repo into an ephemeral, isolated container (no host-FS
  access; configurable network), explore, tear down. Infrastructure, not governance —
  arbiter knows about it and integrates with it, but it is not part of the governance
  kernel. Independent of `ca`: CI is path-scoped and version bumps are per-plugin.

## Scope
- Claude Code adapter: `plugins/ca/` — `arbiter.md` (the arbiter mode's body, formerly
  `ORCHESTRATOR.md`), `includes/safety-core.md`, `skills/`, `commands/`, `agents/`, `hooks/`,
  `tools/`.
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

## Domain vocabulary
- **`mode`** — the orchestration posture a session is in, and the term that selects which
  persona body is injected. Exactly three: **`arbiter`** (the governed default — routing,
  skills, and gates in force), **`dangerous`** (a gates-off posture for local exploratory
  work in any repo), and **`ops`** (arbiter, narrowed to permit starting, observing, and
  exercising a running system in-channel). The canonical spelling is `_modelib.MODES`;
  these names must match it exactly. A mode is **session-scoped and transient** — it is not
  committed, and it never persists across sessions. Changing the mode changes only which
  prose the model carries: **no enforcement hook reads the mode**, so every gate fires
  identically in all three (ADR-0030).
- **`mode body`** — the per-mode markdown injected after `safety-core.md` to form the
  persona. `arbiter.md` is the arbiter mode's body, not an always-on kernel.

## NOT this project
Not a runtime-vendored framework — multi-host support is build-time generation from one
core with CI-enforced byte-identity (ADR-0011), never v1's symlink/dual-root machinery.
Not an enterprise compliance suite. Governance hosts are Claude Code, Codex CLI,
and Pi; further hosts require a new ADR. Solo developer. `ca-sandbox` (ADR-0007),
`ca-codex` (ADR-0011), and `ca-pi` (ADR-0013) are deliberate, recorded exceptions,
not precedent for arbitrary co-location.
See `legacy/ASSESSMENT.md` for the v2 cut list.
