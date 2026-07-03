---
entity: agents/tribunal-architecture-reviewer
related: [skills/tribunal, tribunal-appsec-reviewer, tribunal-reliability-reviewer]
---

## Role

Read-only architecture lens for the `/ca:tribunal` deep-audit lane: reviews the assigned scope for
dead or orphan modules, pattern drift, cosmetic abstractions, dead code paths, god modules, and
monolith accretion. Distinct from `architecture-drift-reviewer`, which checks conformance to accepted
ADRs rather than structural health. Dispatched only by `tribunal`'s Phase 2 roster dispatch.

## Why this model tier

Ships `model: inherit`, but `tribunal`'s own dispatch-time guidance recommends the highest-reasoning
tier (Opus, high effort) for this lens — spotting structural drift and cosmetic abstractions across a
whole codebase is one of the three lenses the skill treats as needing the deepest reasoning.

## What it emits

One `finding/v1` JSON file per finding, written immediately to `findings/architecture/` — never a
batched write — with severity, confidence, file:line locations, evidence, and a remediation shape. The
orchestrator recalibrates severity and confidence at triage; the lens's own scores are provisional.
