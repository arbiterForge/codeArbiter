---
entity: skills/dispatching-parallel-agents
related: [subagent-driven-development, commands/review, commands/checkpoint]
gates:
  - gate: partition
    when: before any agent is dispatched
    effect: two units that would mutate the same file cannot share a batch — the collision is isolated or serialized first
  - gate: funnel
    when: after results are deduped
    effect: the caller only ever sees the aggregated verdict from triage plus aggregation; raw or merely-deduped agent output never reaches it directly
---

## What it does

This is the shared fan-out mechanism other parts of the system dispatch through whenever work
splits across independent units, each handled by its own agent — used inside the implementation
engine, an autonomous sprint, and a parallel code review. It owns the mechanics of dispatching
safely, not the judgment about what the units are: bound the concurrency, isolate each unit's
scope, collect every result even when one errors, remove duplicate findings, and only then let
the results reach whoever asked for the work.

## Phases

1. Partition the work into units with disjoint file paths, routing any unavoidable overlap
   through worktree isolation or serialization.
2. Dispatch one agent per unit in bounded waves, each agent seeing only its own unit's scope.
3. Collect every unit's terminal state — completed, errored, or halted — without letting one
   failure discard the rest of the batch.
4. Merge duplicate findings, surface contradictions instead of silently picking one, and verify
   any completion claim with a fresh proving run rather than trusting a self-report.
5. Route the deduped results through severity triage and then aggregation, and hand the caller
   only the resulting verdict.

## Exits

The caller receives one aggregated verdict — a pass, or a list of blocking findings — never the
raw agent output. Every dispatched unit terminates with a recorded state, so nothing dispatched
ever silently disappears from the batch.
