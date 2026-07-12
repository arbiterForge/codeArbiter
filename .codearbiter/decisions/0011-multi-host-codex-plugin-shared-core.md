---
status: accepted
date: 2026-07-08
title: Multi-host support — third sibling plugin ca-codex via shared core + thin host adapters
decided-by: SUaDtL@users.noreply.github.com
supersedes: none
governs: core/*, tools/sync-core.py, tools/build-surface.py, plugins/ca-codex/*, .agents/plugins/*
---

# ADR-0011 — Multi-host support: third sibling plugin `ca-codex` via shared core + thin host adapters

## Status
Accepted — ratified 2026-07-08 by SUaDtL@users.noreply.github.com ("I approve the adr"), after
plan approval the same day (`.codearbiter/plans/codex-support.md`).

## Context
`CONTEXT.md` has stated "Claude Code only" since v2 deleted v1's multi-host machinery (the AGENTS.md
chain, `.agents/`↔`.claude/` symlinks, `@import` shims, dual-root sentinel) in favor of the single
SessionStart injection. That deletion targeted the *mechanism* — runtime vendoring that drifted —
not the goal of reaching users on other hosts. As of Codex CLI v0.142.x (July 2026), OpenAI's agent
has structural parity with the extension points codeArbiter depends on: a plugin system
(`.codex-plugin/plugin.json`, marketplace catalogs) bundling hooks (Claude-Code-like `hooks.json`,
blocking via exit 2 + stderr), skills in Anthropic's SKILL.md format, and MCP servers; SessionStart /
PreToolUse / PostToolUse events with JSON stdin payloads; and repo-shippable subagents with per-role
`sandbox_mode`. codeArbiter's enforcement chain (stdlib-Python hook logic, ADR-0004) is already
host-neutral except for a thin invocation layer, and the `.codearbiter/` store is host-neutral by
design. The maintainer approved a full-parity port on 2026-07-08.

## Decision
1. The repo/marketplace hosts a **third sibling plugin `plugins/ca-codex/`** — the same governance
   kernel targeting Codex CLI hosts. `CONTEXT.md`'s "Claude Code only" scope statement is amended
   to "Claude Code and Codex CLI hosts; one shared governance kernel."
2. Architecture is **shared core + thin adapters, bound at build time**: host-neutral Python moves
   to `core/pysrc/` (hook entries as importable `run(host)` functions; a `hostapi.py` seam for
   project-root resolution, tool-name normalization, and tool-input shape translation); markdown
   surfaces move to `core/surface/` templates (`{{PLUGIN_ROOT}}`, `{{PROJECT_DIR}}`, `{{CMD:x}}`).
   Stdlib-only generators (`tools/sync-core.py`, `tools/build-surface.py`) materialize byte-exact
   vendored copies into each plugin; **CI enforces byte-identity** between `core/` and every
   vendored copy, and clean surface regeneration. No runtime cross-plugin imports, no symlinks, no
   dual root — the v1 failure mode (unguarded drift between copies) is answered by a mechanical CI
   guard, not runtime indirection.
3. `ca-codex` versions **independently from 0.1.0** (per-plugin SemVer and path-scoped CI per
   ADR-0007; a `core/**` change triggers both plugins' suites). ADR-0004's stdlib-only posture
   binds `core/pysrc/` and both adapters.
4. **Beta until live-fire verification.** The maintainer has no Codex subscription until
   ~2026-07-09; spike items answerable from the open-source `openai/codex` tree proceed now, but
   `ca-codex` ships labeled beta (Feature Forge preview) until stdout injection, trust review, and
   exit-2 blocking are confirmed on a live Codex session.
5. **Parity exceptions are ledgered, not silent**: statusline (no Codex analogue) and the
   prune-transcript backend (undocumented `~/.codex/sessions` format) are recorded in
   `docs/parity.md`. Codex skills carry a `ca-` prefix (Codex has no plugin command namespace).
   If Codex plugins cannot ship subagents, `ca-init` scaffolds generated `.codex/agents/*.toml`
   into target repos with a doctor staleness check.

## Alternatives considered
- **Sibling plugin by copy-and-adapt** — declined. Two hand-maintained copies of gate logic is the
  exact drift v1 died of, now without even a guard.
- **Build-time generation from `plugins/ca/` as canonical** — declined. Makes the Claude layout
  load-bearing for Codex semantics; a neutral `core/` keeps both hosts as peers and the generators
  simple.
- **Runtime shared core (cross-plugin imports/symlinks)** — declined. Couples to both hosts'
  marketplace-clone layouts; resurrects v1's fragility.
- **Separate repository for ca-codex** — declined. Both payloads are generated from one core;
  splitting repos forces cross-repo sync of the very thing the architecture exists to unify.

## Consequences
Easier: one kernel, two hosts, one `.codearbiter/` store per project regardless of which agent the
user runs; parity is provable by a shared contract-test verdict matrix run against both adapters.
Harder: the repo's identity grows again (CONTEXT.md and the marketplace descriptions must say so);
every enforcement change now regenerates two payloads (the CI consistency jobs are load-bearing and
may never be made optional); Codex moves fast, so a minimum-version pin and re-verification on Codex
releases become standing maintenance. ADR-0007's risk note ("not a precedent for arbitrary
co-location") is honored in spirit: this is a second *deliberate, recorded* exception, and it is the
kernel itself on a second host, not new scope.

## Risks
The linchpin assumption — SessionStart hook stdout injected into Codex context — is docs-confirmed
but not live-verified; the pre-approved fallback is a single generated, staleness-checked AGENTS.md
carrying the persona (8.2 KB, under the 32 KiB cap) with the hook emitting live state only. Codex
tool names and `apply_patch` input shapes drive the whole gate surface and must be source- then
live-verified. Trust-review friction (users must approve plugin hooks once) could suppress adoption;
doctor must detect the un-trusted state. This decision is proven wrong if the CI byte-identity guard
proves insufficient to hold the two payloads together (constant cross-host regressions), at which
point per-host repos or dropping a host reopens.
