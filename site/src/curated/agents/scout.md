---
entity: agents/scout
related: [skills/decision-variance, skills/context-creation, skills/commit-gate]
---

## Role

Internal evidence-gatherer: scans an assigned code scope and reports file-path-and-line-number
evidence of architectural decisions, with no excerpts and no variance judgment — that stays with the
dispatching skill. Dispatched by `decision-variance` and `context-creation` when a single inline scan
would consume significant context, and by `subagent-driven-development`/`commit-gate` for scoped
evidence gathering elsewhere. Never dispatched directly by the orchestrator.

## Why this model tier

Ships `model: haiku`. High-volume, file:line evidence gathering with an explicit "no judgment, no
excerpts" mandate is exactly the workload a fast, cheap tier is built for.

## What it emits

A structured scout report: evidence locations (file, lines, git hash, a ≤20-word note) per decision
category, a strong/moderate/weak confidence rating per category, and an unlabeled anomalies section for
evidence that doesn't map to any passed category.
