---
entity: agents/tribunal-coverage-reviewer
related: [skills/tribunal, tribunal-infra-reviewer, coverage-auditor]
---

## Role

Read-only coverage lens for the `/ca:tribunal` deep-audit lane: reviews the assigned scope for
risk-path coverage gaps, edge/property gaps, and implementation-coupled tests across the whole
codebase. Distinct from the routine `coverage-auditor`, which checks a single change against its TDD
obligations rather than the codebase's risk paths at large. Dispatched only by `tribunal`'s Phase 2
roster dispatch.

## Why this model tier

Ships `model: inherit`, but `tribunal`'s own dispatch-time guidance recommends Sonnet at medium effort
for this lens — one of the five Tier-2 lenses the skill scopes to a lighter reasoning budget than the
adversarial-security and reliability lenses, and the first offered up for trimming under cost pressure.

## What it emits

One `finding/v1` JSON file per finding, written immediately to `findings/coverage/` — never a batched
write — with severity, confidence, file:line locations, evidence, and a remediation shape. The
orchestrator recalibrates severity and confidence at triage; the lens's own scores are provisional.
