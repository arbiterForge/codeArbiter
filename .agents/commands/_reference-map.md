<!--
Copyright (c) 2026 suadtl
Author: suadtl
Created: 2026-05-14
File: _reference-map.md

This file is an INTERNAL on-demand include extracted from AGENTS.md §4.
Underscore prefix denotes "not a user command — load only when deciding which
projectContext/ doc to read before acting on a scope-touch."
-->

# §4: Reference Map

> **Loaded when:** any scope-touch decision — i.e. before acting on code that
> falls into one of the rows below, load this file to look up which
> `${PROJECT_ROOT}/.agents/projectContext/*.md` doc must be read first and which
> skill or agent is the primary route. AGENTS.md keeps a one-sentence stub
> pointing here; the body lives here so the per-row table doesn't load on every
> session.

Read the listed file before acting. The skill or agent listed is the primary route when scope applies.

| If task touches… | Read first | Invoke |
|---|---|---|
| Any code change | `${PROJECT_ROOT}/.agents/projectContext/coding-standards.md` | `tdd` skill |
| Stack / dependencies | `${PROJECT_ROOT}/.agents/projectContext/tech-stack.md`, `${PROJECT_ROOT}/.agents/projectContext/dependency-policy.md` | `dependency-reviewer` agent |
| Auth, crypto, secrets | `${PROJECT_ROOT}/.agents/projectContext/security-controls.md`, `${PROJECT_ROOT}/.agents/projectContext/secrets-policy.md` | `crypto-compliance` skill; `secret-handling` skill |
| Logging / telemetry | `${PROJECT_ROOT}/.agents/projectContext/audit-spec.md` | `audit-emit` skill |
| Metrics / traces / alerts / SLOs | `${PROJECT_ROOT}/.agents/projectContext/observability-spec.md` | `observability-emit` skill |
| Data model / migrations | `${PROJECT_ROOT}/.agents/projectContext/tech-stack.md` | `migration-reviewer` agent |
| Networking / deployment | `${PROJECT_ROOT}/.agents/projectContext/trust-zones.md` | `security-architecture` skill |
| New domain concept or component | `${PROJECT_ROOT}/.agents/projectContext/CONTEXT.md` | `doc-review-gate` skill |
| Failure / retry logic | `${PROJECT_ROOT}/.agents/projectContext/tech-stack.md` | — |
| CI/CD / branch settings | `${PROJECT_ROOT}/.agents/projectContext/tech-stack.md` | — |
| Risks / ADRs | `${PROJECT_ROOT}/.agents/projectContext/open-questions.md`, `${PROJECT_ROOT}/.agents/projectContext/decisions/` | `decision-lifecycle` skill |
| Checkpoint / stage promotion | `${PROJECT_ROOT}/.agents/projectContext/stage` | `stage-gating` skill |
| Architectural reconciliation | `${PROJECT_ROOT}/.agents/projectContext/decomposition/` | `decision-variance` skill (`/decision-variance`) |
| Subagent encounters out-of-scope finding | `${PROJECT_ROOT}/.agents/projectContext/ticketing-config.md` | `ticketing-router` skill (router) |
