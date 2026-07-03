---
entity: agents/map-structure
related: [skills/tribunal, map-deps]
---

## Role

Read-only extractor of a repository's structural inventory — file-tree shape, language breakdown,
entry points, core-logic locations, and churn via git history. It reports facts, never findings;
risk-ranking and trust-boundary marking are the orchestrator's Phase 1 judgment overlay, applied after
this report returns. Dispatched only by the `tribunal` skill's Phase 1, and only on a large or
sprawling repo, alongside `map-deps`.

## Why this model tier

Ships `model: inherit`, but the `tribunal` skill's own dispatch-time model guidance recommends Haiku
for this role, the same rationale as `map-deps` — high-volume extraction, not judgment.

## What it emits

A terse structured summary sized to fold directly into the tribunal run's `inventory.md`: a condensed
directory tree, a per-language breakdown, where the routes and entry files live, and a
most-active-files list, never raw file contents.
