---
entity: agents/architecture-drift-reviewer
related: [commands/checkpoint, commands/review, finding-triage]
---

## Role

Read-only checkpoint reviewer: for every ADR marked `accepted` in `.codearbiter/decisions/`, it scans
the codebase for evidence the decision is being followed or contradicted. It is dispatched as part of
the reviewer fleet by `/ca:checkpoint` and `/ca:review`, and its output feeds `finding-triage` on the
way to `checkpoint-aggregator`. It never edits code — this review is informational, pairing with the
`decision-variance` skill's append-only decision record rather than gating a change.

## Why this model tier

Ships `model: haiku`. Matching a known ADR against grep/glob evidence in the codebase is a high-volume,
pattern-matching check rather than open-ended judgment, which fits a fast, low-cost tier.

## What it emits

A CONFIRMED / PARTIAL DRIFT / DRIFT / INSUFFICIENT EVIDENCE classification per ADR, plus a
CRITICAL–LOW severity finding with file:line for every drift or partial-drift case. All output is
informational — it never blocks a change.
