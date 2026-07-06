---
description: Deep, rarely-convened whole-codebase audit — eleven specialist lenses, a resumable on-disk audit log, findings filed as GitHub issues on approval. Expensive; estimates cost and STOPs before running. Never a required gate.
argument-hint: "[scope-path] [--tag <label>]"
---
# /ca:tribunal — deep codebase audit

The deepest, most expensive review codeArbiter offers, convened rarely and on demand. Routes to the tribunal skill. Eleven lenses judge the codebase; every finding persists to its own file (plus append-only triage/run logs) under `.codearbiter/reports/<run-id>/`, so an interrupted run resumes from disk. Never a required gate — critical/high are blocking-severity findings, not a pipeline halt.

Cost first — this lane routinely costs millions of tokens on a large repo. Phase 0 sizes the codebase, prints a token-cost band, recommends the highest-reasoning model, and STOPs for your acknowledgement before dispatching anything. Nothing runs unacknowledged.

## Flow

Load and follow the tribunal skill (`${CLAUDE_PLUGIN_ROOT}/skills/tribunal/SKILL.md`) — seven gated
phases: cost/model/resume (STOP), map, lens dispatch in waves, per-wave triage, report,
approval + filing, opt-in telemetry (STOP). The skill is canonical for its phases and gates; they
are not restated here.

## Arguments

`"scope-path"` — focus the audit on a subtree (default: repository root). The full lens roster still runs; only the scope narrows.

`--tag <label>` — freeform run label recorded in telemetry (see `references/telemetry.md`).

## Routes to

`${CLAUDE_PLUGIN_ROOT}/skills/tribunal/SKILL.md` — dispatches the eleven tribunal-* reviewers (and, on a large repo, the optional map-structure / map-deps mappers).

## When NOT to use

- A review of the current diff → `/ca:review` (gate-blocking, fast).
- A lean periodic sweep → `/ca:checkpoint` (cheap, frequent; tribunal is its rare, deep counterpart).
- An adversarial STRIDE pass on one sensitive feature → `/ca:threat-model`.
- A governance packet for a window → `/ca:audit`.
- Anything on a schedule or in a hot loop — tribunal is a rare, deliberate, expensive convening, not a routine gate.

## Hard gate

MUST NOT dispatch any lens before you acknowledge the Phase 0 cost estimate. MUST NOT act as a required gate or block a merge/commit. MUST NOT file an issue or send telemetry without explicit authorization. Read-only on project code until the filing gate; findings file as GitHub issues, never the task board.
