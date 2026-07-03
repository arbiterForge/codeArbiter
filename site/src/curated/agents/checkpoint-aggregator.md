---
entity: agents/checkpoint-aggregator
related: [skills/dispatching-parallel-agents, finding-triage, commands/checkpoint]
---

## Role

Final stage of the checkpoint pipeline: reads the `finding-triage` report, ensures
`.codearbiter/checkpoints/` exists, and writes the dated checkpoint document. It composes rather than
judges — dispatched by `dispatching-parallel-agents` after `finding-triage` completes, once every
reviewer in the sweep has reported in.

## Why this model tier

Ships `model: haiku`. Assembling a templated document from an already-classified triage report is
composition, not judgment, so a fast, low-cost tier is sufficient.

## What it emits

Writes `.codearbiter/checkpoints/YYYY-MM-DD.md` directly (never overwriting an existing one — it
suffixes `-2`, `-3` on same-day reruns), reports the path back, and lists the report's DEFERRABLE
findings as harvest candidates for the orchestrator to route to `open-tasks.md`.
