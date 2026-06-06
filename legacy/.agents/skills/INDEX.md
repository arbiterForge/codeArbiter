<!--
Copyright (c) 2026 suadtl
Author: suadtl
Created: 2026-05-14
File: INDEX.md
-->

# Skills Index

<!-- Auto-maintained surface scan. Skill bodies are read ONLY when routed to. -->
<!-- See AGENTS.md §3 and §6: bulk reads of `${FRAMEWORK_ROOT}/.agents/skills/*.md` are prohibited. -->
<!-- Use this index for routing decisions; open bodies on routing only. -->

## Read-on-invocation guarantee

This `INDEX.md` is the only sanctioned surface scan of `${FRAMEWORK_ROOT}/.agents/skills/`. Routing decisions in AGENTS.md §4 and §5 reference skills by name; their `SKILL.md` bodies are loaded only when the named skill is routed to (per §0.1 `route` verb).

## Invocation classes

| Class | Meaning |
|---|---|
| `user → /cmd` | Entered via a user-invoked slash command. Primary command listed in the row. |
| `condition` | Routed automatically when the scope listed in §5 is touched (code emits/should emit X, file path matches Y, etc.). No direct user command. |
| `internal` | Only routed from inside another skill (sub-flow). No direct user entry point. |

A skill MAY be in multiple classes (e.g. `user → /adr` AND `condition` for "ADR added / aged"). The index lists the primary class first.

## Index

| Skill | One-line role | Invocation class | Body |
|---|---|---|---|
| `audit-emit` | Verifies and authors audit-event emission for state-changing actions per `${PROJECT_ROOT}/.agents/projectContext/audit-spec.md` | `condition` (code emits or should emit an audit event) | [body](audit-emit/SKILL.md) |
| `commit-gate` | Multi-phase pre-commit gate: tests green, hooks pass, no unauthored ADRs, no broken signals | `user → /commit` | [body](commit-gate/SKILL.md) |
| `context-creation` | Brownfield bootstrap of `${PROJECT_ROOT}/.agents/projectContext/` for an existing codebase | `user → /create-context` | [body](context-creation/SKILL.md) |
| `crypto-compliance` | Validates crypto / hashing / signing / TLS / random against `${PROJECT_ROOT}/.agents/projectContext/security-controls.md` approved primitives | `condition` (code uses crypto / hashing / signing / TLS / random) | [body](crypto-compliance/SKILL.md) |
| `debug` | Investigate-then-decide root cause analysis; outcomes route to `/fix`, `/ticket`, or `/adr` | `user → /debug` | [body](debug/SKILL.md) |
| `decision-lifecycle` | Author a new ADR, register it, queue it for `decision-challenger` review; also handles ADR aging, status promotion, supersede chains | `user → /adr` AND `condition` (ADR added / aged / CONFIRM-NN unresolved) | [body](decision-lifecycle/SKILL.md) |
| `decision-variance` | Reconcile project artifacts against scaffold; arbitrate ADR conflicts via SMARTS analysis (never decides alone — user attribution required for every choice) | `user → /decision-variance` | [body](decision-variance/SKILL.md) |
| `decompose` | Greenfield interview (6 layers, ~60–110 Q/A) producing the three decomposition artifacts and a populated `projectContext/`. Compaction-resilient via per-layer disk drafts and immediate DRAFT ADRs (Phase 2.5 + Phase 4 disk rehydrate) | `user → /decompose` | [body](decompose/SKILL.md) |
| `doc-review-gate` | Forces re-read of the gated `${PROJECT_ROOT}/.agents/projectContext/*.md` doc for a domain area before action proceeds | `condition` (`projectContext/` file modified or domain area referenced before acting) | [body](doc-review-gate/SKILL.md) |
| `observability-emit` | Verifies and authors metric / trace / alert / SLO emission per `${PROJECT_ROOT}/.agents/projectContext/observability-spec.md`; enforces label cardinality budgets | `condition` (code emits or should emit an observability signal) | [body](observability-emit/SKILL.md) |
| `onboard` | Engineer onboarding tour; full or scoped to one domain area | `user → /onboard` | [body](onboard/SKILL.md) |
| `refactor` | Behavior-preserving change with parity-coverage proof gate | `user → /refactor` | [body](refactor/SKILL.md) |
| `release` | 7-phase release workflow: SemVer bump, changelog, tag, deployment readiness | `user → /release` | [body](release/SKILL.md) |
| `rotation` | Rotate a secret / key / OIDC client / TLS cert / service token with cadence + audit + archival gates | `user → /rotate` AND `condition` (rotation due) | [body](rotation/SKILL.md) |
| `secret-handling` | Validates secret read / write / pass against `${PROJECT_ROOT}/.agents/projectContext/secrets-policy.md` approved store paths | `condition` (code reads / writes / passes a secret) | [body](secret-handling/SKILL.md) |
| `security-architecture` | Pre-implementation threat model; new trust-zone crossings; attack-surface change review | `user → /threat-model` AND `condition` (new trust zone crossing / threat model / attack surface change) | [body](security-architecture/SKILL.md) |
| `skill-author` | Author a new skill after gap validation; enforces phase / gate / failure-modes structure | `user → /new-skill` | [body](skill-author/SKILL.md) |
| `stage-gating` | Stage 1–4 promotion with named-approver requirement; reads `${PROJECT_ROOT}/.agents/projectContext/stage` | `user → /stage` AND `condition` (code has stage-conditional behavior) | [body](stage-gating/SKILL.md) |
| `tdd` | 6-phase TDD workflow: obligation checklist → failing test → minimal implementation → green → refactor → integration. Dispatches `backend-author`, `frontend-author`, or `infra-author` agent | `user → /feature, /fix` | [body](tdd/SKILL.md) |
| `ticketing-router` | Routes out-of-scope subagent findings to in-repo tickets or Plane (variant per `${PROJECT_ROOT}/.agents/projectContext/ticketing-config.md`); BLOCKs on `adr-*` dispositions and `incorporated-to:*` without target-doc edit | `user → /ticket` AND `condition` (subagent raises out-of-scope finding) | [body](ticketing-router/SKILL.md) |

## Cross-references

- Per-skill phase counts and gate definitions: see each `SKILL.md` body.
- User-invoked commands (slash commands) and their argument shapes: `${FRAMEWORK_ROOT}/COMMANDS.md`.
- Agent dispatch matrix (which skills dispatch which agents): `${FRAMEWORK_ROOT}/.agents/agents/INDEX.md`.
- Routing table (cue → skill mapping): AGENTS.md §5 (stub) → full body at `${FRAMEWORK_ROOT}/.agents/commands/_routing-table.md`.

## Maintenance

When adding a new skill, append a row to this index. The body MUST live at `${FRAMEWORK_ROOT}/.agents/skills/<name>/SKILL.md`. New skills are authored via `/new-skill`, which routes to the `skill-author` skill — that skill enforces the phase / gate / failure-modes structure and updates this index as part of its workflow.
