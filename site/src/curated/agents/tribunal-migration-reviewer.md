---
entity: agents/tribunal-migration-reviewer
related: [skills/tribunal, tribunal-secrets-supply-reviewer, tribunal-test-fidelity-reviewer]
---

## Role

Read-only migration lens for the `/ca:tribunal` deep-audit lane: reviews the assigned scope for
migration safety, data-classification tagging, immutability, and schema-to-code drift across the whole
codebase. Distinct from the routine `migration-reviewer`, which checks a single new or modified
migration file rather than the whole migration history. Dispatched only by `tribunal`'s Phase 2 roster
dispatch.

## Why this model tier

Ships `model: inherit`, but `tribunal`'s own dispatch-time guidance recommends Sonnet at high effort
for this lens — one of three lenses the skill treats as needing careful, high-effort reasoning just
below the top tier, given the cost of missing a schema-integrity gap.

## What it emits

One `finding/v1` JSON file per finding, written immediately to `findings/migration/` — never a batched
write — with severity, confidence, file:line locations, evidence, and a remediation shape. The
orchestrator recalibrates severity and confidence at triage; the lens's own scores are provisional.
