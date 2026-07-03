---
entity: agents/tribunal-reliability-reviewer
related: [skills/tribunal, tribunal-appsec-reviewer, tribunal-architecture-reviewer]
---

## Role

Read-only reliability lens for the `/ca:tribunal` deep-audit lane: reviews the assigned scope for async
correctness, error propagation, races, resource lifecycle, boundary conditions, and orphan state.
Dispatched only by `tribunal`'s Phase 2 roster dispatch, against the checklist and exposure
denominator in its own lens reference.

## Why this model tier

Ships `model: inherit`, but `tribunal`'s own dispatch-time guidance recommends the highest-reasoning
tier (Opus, high effort) for this lens — tracing races and resource-lifecycle bugs is one of the three
lenses the skill treats as needing the deepest reasoning.

## What it emits

One `finding/v1` JSON file per finding, written immediately to `findings/reliability/` — never a
batched write — with severity, confidence, file:line locations, evidence, and a remediation shape. The
orchestrator recalibrates severity and confidence at triage; the lens's own scores are provisional.
