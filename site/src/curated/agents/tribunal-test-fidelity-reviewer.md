---
entity: agents/tribunal-test-fidelity-reviewer
related: [skills/tribunal, tribunal-secrets-supply-reviewer, tribunal-migration-reviewer]
---

## Role

Read-only test-fidelity lens for the `/ca:tribunal` deep-audit lane: reviews the assigned scope for
tests that validate fiction — a mock, stub, or fixture that has drifted from a now-existing real
producer. Dispatched only by `tribunal`'s Phase 2 roster dispatch, against the recipe, severity rule,
and exposure denominator in its own lens reference.

## Why this model tier

Ships `model: inherit`, but `tribunal`'s own dispatch-time guidance recommends Sonnet at high effort
for this lens — one of three lenses the skill treats as needing careful, high-effort reasoning just
below the top tier, given how easily a fixture-drift bug hides behind a passing suite.

## What it emits

One `finding/v1` JSON file per finding, written immediately to `findings/test-fidelity/` — never a
batched write — with severity, confidence, file:line locations, evidence, and a remediation shape. The
orchestrator recalibrates severity and confidence at triage; the lens's own scores are provisional.
