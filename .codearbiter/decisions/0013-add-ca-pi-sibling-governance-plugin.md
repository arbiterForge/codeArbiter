---
status: accepted
date: 2026-07-13
title: Add ca-pi as a sibling governance plugin using the shared core and a thin Pi adapter
decided-by: SUaDtL@users.noreply.github.com
supersedes: none
governs: core/**, tools/sync-core.py, tools/build-surface.py, plugins/ca-pi/**, docs/parity.md
---

# ADR-0013 — Add `ca-pi` as a sibling governance plugin using the shared core and a thin Pi adapter

## Status
Accepted — approved 2026-07-13 by SUaDtL@users.noreply.github.com.

## Context
codeArbiter currently ships the shared governance kernel for Claude Code and Codex CLI. The Pi
coding-agent harness can install packages containing extensions and Agent Skills; its extension API
exposes session lifecycle events, prompt injection, blockable tool calls, and UI surfaces. These
capabilities can host the same governance rules, skills, and audit trail without creating another
hand-maintained copy of the kernel.

`.codearbiter/CONTEXT.md` limits governance hosts to Claude Code and Codex CLI and requires a new ADR
before adding another host. The maintainer chose to add Pi now, require behavioral parity and a green
test suite, and keep the complete implementation on one feature branch until those conditions are
met.

## Decision
Add `plugins/ca-pi/` as a sibling governance package named `ca-pi`. Generate its host-neutral Python
and markdown payloads from `core/pysrc/` and `core/surface/`, using the existing build-time shared-core
model. A thin Pi extension adapter translates Pi lifecycle events and tool-call shapes into the
canonical host contract. `ca-pi` shares each project's `.codearbiter/` state store with the Claude and
Codex hosts.

`ca-pi` versions independently. The implementation remains on one feature branch until automated
host-contract parity, the repository's full required suite, and live Pi verification pass. Any Pi
capability gap is recorded explicitly in `docs/parity.md`; no enforcement difference is silent.

## Alternatives considered
- **Project-scaffolded `.pi/` resources** — declined. Scaffolding makes every project own generated
  integration files and weakens package-level installation, updates, and parity checks.
- **Copy and adapt an existing plugin** — declined. A third hand-maintained kernel copy recreates the
  drift failure that the shared-core generators and byte-identity checks exist to prevent.
- **Separate repository** — declined. The adapter and generated payload share the same kernel and
  parity matrix; splitting repositories would turn atomic compatibility changes into cross-repo
  coordination.

## Consequences
Pi users gain the same command surface, gates, audit trail, and project-state store as the existing
hosts. Shared sources remain authoritative and host-specific behavior stays confined to a thin
adapter. The build and CI matrix grows to three governance targets, Pi API compatibility becomes a
standing maintenance obligation, and release work gains an independently versioned package.

## Risks
Pi extension API changes could invalidate adapter assumptions. Project trust could prevent the
extension from loading and silently remove enforcement. Mocked contract tests could report parity
while a live Pi session behaves differently. A documented minimum Pi version, host-contract tests,
doctor checks for package/trust activation, an explicit parity ledger, and required live verification
before the branch ships are the acceptance bar. This decision is proven wrong if Pi cannot enforce a
core gate without weakening it or if maintaining the third generated target causes recurring kernel
drift.
