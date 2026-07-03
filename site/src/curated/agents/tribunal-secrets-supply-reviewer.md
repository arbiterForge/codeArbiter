---
entity: agents/tribunal-secrets-supply-reviewer
related: [skills/tribunal, tribunal-migration-reviewer, tribunal-test-fidelity-reviewer]
---

## Role

Read-only secrets/supply-chain lens for the `/ca:tribunal` deep-audit lane: reviews the assigned scope
for hardcoded secrets, weak crypto, cleartext data, secrets in logs, and dependency/supply-chain
hygiene. Dispatched only by `tribunal`'s Phase 2 roster dispatch, against the checklist and exposure
denominator in its own lens reference.

## Why this model tier

Ships `model: inherit`, but `tribunal`'s own dispatch-time guidance recommends Sonnet at high effort
for this lens — one of three lenses the skill treats as needing careful, high-effort reasoning just
below the top tier, given the cost of missing a real secret exposure.

## What it emits

One `finding/v1` JSON file per finding, written immediately to `findings/secrets-supply/` — never a
batched write — with severity, confidence, file:line locations, evidence, and a remediation shape. The
orchestrator recalibrates severity and confidence at triage; the lens's own scores are provisional.
