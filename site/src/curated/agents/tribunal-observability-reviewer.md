---
entity: agents/tribunal-observability-reviewer
related: [skills/tribunal, tribunal-performance-reviewer, tribunal-typesafety-reviewer]
---

## Role

Read-only observability lens for the `/ca:tribunal` deep-audit lane: reviews the assigned scope for
structured logging, tracing/correlation IDs, metrics on critical paths, and audit gaps. Dispatched only
by `tribunal`'s Phase 2 roster dispatch, against the checklist and exposure denominator in its own lens
reference.

## Why this model tier

Ships `model: inherit`, but `tribunal`'s own dispatch-time guidance recommends Sonnet at medium effort
for this lens — one of the five Tier-2 lenses the skill scopes to a lighter reasoning budget than the
adversarial-security and reliability lenses, and the first offered up for trimming under cost pressure.

## What it emits

One `finding/v1` JSON file per finding, written immediately to `findings/observability/` — never a
batched write — with severity, confidence, file:line locations, evidence, and a remediation shape. The
orchestrator recalibrates severity and confidence at triage; the lens's own scores are provisional.
