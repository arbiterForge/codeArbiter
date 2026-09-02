---
entity: agents/verdict-aggregator
related: [commands/review, commands/checkpoint, skills/dispatching-parallel-agents, finding-triage]
---

## Role

Terminal read-only synthesis for reviews and generic parallel batches. It receives the unified triage
report plus the batch completion record, checks that every dispatched unit has a terminal result, and
returns one in-memory outcome. It never writes a checkpoint or changes project state.

## Why this model tier

Ships `model: haiku`. The role applies a fixed decision table to an already-classified report, so it
does not need the broader judgment used by the specialist reviewers that produced the findings.

## What it emits

Exactly one of PASS, BLOCKING_FINDINGS, or INCOMPLETE, followed by disposition totals and every
triaged finding. Missing, errored, or unaccounted-for units force INCOMPLETE instead of allowing a
partial batch to look successful. An explicit checkpoint flow may pass this result to the separate
writer; ordinary review returns it directly to the caller.
