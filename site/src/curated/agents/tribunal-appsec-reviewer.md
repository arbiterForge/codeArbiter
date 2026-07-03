---
entity: agents/tribunal-appsec-reviewer
related: [skills/tribunal, tribunal-architecture-reviewer, tribunal-reliability-reviewer]
---

## Role

Read-only application-security lens for the `/ca:tribunal` deep-audit lane: reviews the assigned scope
for injection, resource-level authorization/IDOR, input validation, JWT handling, CORS, and SSRF.
Dispatched only by `tribunal`'s Phase 2 roster dispatch, against the checklist and exposure
denominator in its own lens reference.

## Why this model tier

Ships `model: inherit`, but `tribunal`'s own dispatch-time guidance recommends the highest-reasoning
tier (Opus, high effort) for this lens — appsec is one of three lenses the skill treats as needing the
deepest adversarial reasoning, alongside architecture and reliability.

## What it emits

One `finding/v1` JSON file per finding, written immediately to `findings/appsec/` — never a batched
write — with severity, confidence, file:line locations, evidence, and a remediation shape. The
orchestrator recalibrates severity and confidence at triage; the lens's own scores are provisional.
