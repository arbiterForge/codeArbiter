<!--
Copyright (c) 2026 suadtl
Author: suadtl
Created: 2026-05-14
File: README.md
-->

# codeArbiter Framework Design History

This directory holds **codeArbiter's own architectural decisions** — ADRs about how the framework itself was designed and why. These are framework-repo documentation, NOT consumer-project artifacts.

## Not to be confused with

`${PROJECT_ROOT}/.agents/projectContext/decisions/` is where a **consuming project** records ITS own architectural decisions via `/adr`. That directory is consumer-owned and ships pristine (only the directory README). A vendor consumer should not inherit framework design ADRs into their project's decision log.

## Scope

ADRs in this directory:
- Document choices made about codeArbiter's own structure, skills, agents, and protocols.
- Are not loaded by the orchestrator at runtime. The orchestrator's read surface is `${FRAMEWORK_ROOT}/.agents/**` and `${PROJECT_ROOT}/.agents/projectContext/**` — this `docs/` tree lives at the framework root, outside both.
- Are visible to consumers who browse the vendored framework repo (e.g. on GitHub), but do not affect routing, gates, or consumer state.

## Index

| ADR | Title | Status | Date | Body |
|---|---|---|---|---|
| ADR-001 | Ticketing design — in-repo scope-overflow inbox + optional Plane on-prem | proposed | 2026-05-12 | [body](001-ticketing-design.md) |
