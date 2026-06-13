---
status: proposed
date: 2026-06-13
title: Adopt a hybrid ADR + living-docs governance model
decided-by: SUaDtL@users.noreply.github.com
supersedes: none
governs: .codearbiter/tech-stack.md, .codearbiter/security-controls.md, .codearbiter/decisions/*
---

# ADR-0001 — Adopt a hybrid ADR + living-docs governance model

## Status
Proposed

## Context
Governance decisions currently live as prose in `.codearbiter/tech-stack.md` and
`.codearbiter/security-controls.md`. No ADRs exist and the `.codearbiter/decisions/`
directory was absent until this record. The 2026-06-13 checkpoint sweep flagged that
load-bearing architecture/security decisions are not pinned as auditable, attributed
records, and the project's commercialization-promotability constraint requires an
ADR/decision-log trail that survives trimming of ceremony.

## Decision
Load-bearing architecture, security, and governance decisions are pinned as numbered,
immutable, user-attributed ADRs under `.codearbiter/decisions/`. `tech-stack.md` and
`security-controls.md` remain living reference documents that describe current state.
ADRs record the *why* and the decision moment; the living docs record *what-is-now*.

## Alternatives considered
- **Prose-only governance (keep docs, no ADRs)** — Maintainable-strong (one living surface)
  but provides no immutable, attributed decision trail; fails the audit/promotability requirement.
- **Full migration of governance docs into ADRs** — produces two surfaces that drift; the
  living "current state" reference is lost. Maintainable-weak.

## Consequences
Easier: auditable decision history, explicit attribution, a promotable governance trail,
and `governs:`-driven edit-time pushback. Harder: a small ceremony cost per load-bearing
decision; discipline required to ADR the decisions that warrant it.

## Risks
ADRs and living docs could drift if not cross-referenced. Mitigated by `governs:` path globs
(edit-time notices) and the periodic checkpoint architecture-drift review. Proven wrong if the
ceremony cost suppresses decision-recording rather than improving it.
