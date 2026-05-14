<!--
Copyright (c) 2026 suadtl
Author: suadtl
Created: 2026-05-14
File: _routing-table.md

This file is an INTERNAL on-demand include extracted from AGENTS.md §5.
Underscore prefix denotes "not a user command — load on user invocation cue
match." Loaded effectively on every /command and on any condition-triggered
scope match. The table is large enough to deserve its own file rather than
costing ~280 tokens every session preamble.
-->

# §5: Routing Table

> **Loaded when:** any user invocation cue match (every `/command` invocation
> needs to look up its primary route here) and on any condition-triggered scope
> change (code touches auth, migration file added, etc.). AGENTS.md keeps a
> one-sentence stub pointing here.

When a trigger fires, follow the primary route. Gates are hard stops — not suggestions.

## Invocation-class annotations (within the table)

The "Primary Route" column annotates each route with one of:
- `(/cmd)` — a user-invoked slash command exists for this route
- `(condition-triggered, no command)` — routed automatically when scope is touched
- `[OPTIONAL PLUGIN]` — agent body is consumer-supplied, not framework core

A skill MAY appear with both a `/cmd` annotation AND condition-triggered behavior elsewhere.

## Routing table

| Invocation cue | Primary Route | Also Dispatch | Hard Gate |
|---|---|---|---|
| New feature | `tdd` skill (`/feature`) | `backend-author`, `frontend-author`, or `infra-author` agent | No implementation before Phase 1 checklist complete |
| Bug fix | `tdd` skill bug variant (`/fix`) | Same implementation agents | No implementation before Phase 1 checklist complete |
| Refactor (behavior-preserving) | `refactor` skill (`/refactor`) | `tdd` skill (Phase 1 only, for new test seams) | No refactor without behavioral-parity coverage proof |
| Unknown defect / investigation | `debug` skill (`/debug`) | (Phase 4 routes to `/fix`, `/ticket`, or `/adr`) | No code change inside debug skill; investigation only |
| "commit" / "commit this" / "go ahead and commit" | `commit-gate` skill (`/commit`) | — | No commit without all phase gates green |
| "PR" / "open a PR" / "pull request" | `/pr` command | Reviewer agents per path matrix | No PR draft until all BLOCK-level reviews clear |
| Stage promotion | `/stage` command | — | No `${PROJECT_ROOT}/.agents/projectContext/stage` change without named approver |
| Release / version bump / tag | `/release` command | `commit-gate`, `decision-lifecycle`, `stage-gating` skills | No tag without all 7 release-skill phases green |
| "checkpoint" | `/checkpoint` command | — | All 7 reviewers must complete; no skipping |
| Code touches auth, crypto, keys, audit | `auth-crypto-reviewer` agent | `security-reviewer` agent | BLOCK on any CRITICAL finding |
| Migration file added or changed | `migration-reviewer` agent | `audit-emitter` agent | BLOCK if classification annotation missing |
| `package.json` or lock file modified | `dependency-reviewer` agent | — | BLOCK on denied license |
| Schema definition file added or modified | `schema-validator` agent **[OPTIONAL PLUGIN]** — agent body is provided by consumer plugins, NOT framework core. Row is no-op when plugin not installed. | — | BLOCK if schema validation fails (only when plugin installed; otherwise inert) |
| Code emits or should emit an audit event | `audit-emit` skill *(condition-triggered, no command)* | `audit-emitter` agent | BLOCK if emit missing or fields wrong |
| Code emits or should emit an observability signal (metric/trace/alert/SLO) | `observability-emit` skill *(condition-triggered, no command)* | `observability-emitter` agent (if defined) | BLOCK if emit missing, labels wrong, or cardinality unbounded |
| Code uses crypto / hashing / signing / TLS / random | `crypto-compliance` skill *(condition-triggered, no command)* | `auth-crypto-reviewer` agent | BLOCK on any banned primitive |
| Code reads / writes / passes a secret | `secret-handling` skill *(condition-triggered, no command)* | `auth-crypto-reviewer` agent | BLOCK if secret outside approved store path |
| Rotation due / signing key, OIDC secret, TLS cert, service token | `rotation` skill (`/rotate`) | `secret-handling`, `crypto-compliance` skills; `audit-emit` skill | BLOCK on rotation past cadence, missing archival, or missing rotate audit emit |
| Code has stage-conditional behavior | `stage-gating` skill (`/stage`) | — | Read `${PROJECT_ROOT}/.agents/projectContext/stage` first; no exceptions |
| Arbitration / variance / ADR reconciliation | `decision-variance` skill (`/decision-variance`) | `decision-challenger` agent | No decisions without user attribution |
| Rule conflict (AGENTS.md vs. code or docs) | `/surface-conflict` command | — | STOP all other work immediately |
| ADR added / aged / CONFIRM-NN unresolved | `decision-lifecycle` skill (`/adr`) | `decision-challenger` agent | No CONFIRM-NN resolved by guessing |
| New trust zone crossing / threat model / attack surface change | `security-architecture` skill (`/threat-model`) | `security-reviewer` + `trust-zone-reviewer` | No undeclared egress |
| `projectContext/` file modified or domain area referenced before acting | `doc-review-gate` skill *(condition-triggered, no command)* | — | No action in domain without reading gated doc first |
| Subagent raises out-of-scope finding | `ticketing-router` skill | — | When ticketing disabled, finding inlines with `[NEEDS-TRIAGE]` marker. Disposition MUST NOT be `adr-*` |
| Ticket close requested | `ticketing-router` skill (variant per config) | — | BLOCK on `adr-*` dispositions. BLOCK if `incorporated-to:*` recorded without target-doc edit in session |
