# performance — lens mandate

Executed by `tribunal-performance-reviewer`. Evidence-or-drop on every check; flag a signature only where the path is plausibly hot — no speculative micro-optimization.

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
