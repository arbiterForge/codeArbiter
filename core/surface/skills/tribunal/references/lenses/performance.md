# performance — lens mandate

Executed by `tribunal-lens-reviewer` under the `performance` assignment. Write contract + evidence discipline: `finding-record.md`; flag a signature only where the path is plausibly hot — no speculative micro-optimization.

## Scope emphasis
The assigned path slice, weighted to hot paths and data access.

## Required reading
- `{{PROJECT_DIR}}/.codearbiter/tech-stack.md` — data layer, ORM, and cache conventions.

## Checklist
- N+1 queries and per-iteration IO in loops.
- Redundant hot-path work; recomputation that could be hoisted or memoized.
- Query/index shape: filters/sorts on unindexed columns; over-fetching.
- Missing or incorrect caching; cache keys that never invalidate or collide.
- Blocking IO on latency-critical paths.

## Exposure
Count of hot-path/data-access sites inspected.

## Out of scope
Correctness of the logic itself (reliability).
