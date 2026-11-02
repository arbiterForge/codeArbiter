---
entity: skills/debug
related: [commands/debug, tdd]
---

## Phases

1. Capture observed behavior, available expected behavior, reproduction state, caller scope,
   and the source and limits of the evidence. Unknown details stay unknown.
2. Name plausible mechanisms and a distinguishing observation for each. The evidence sets the
   number of hypotheses.
3. Assess each diagnostic action's target, effects, bounds, and authority before running it.
   Mark candidates confirmed, refuted, or inconclusive with applicable citations. If no safe
   useful discriminator is available, stop with `unresolved` and a resume condition.
4. Select one supported disposition for the case while preserving multiple supported causes
   and separate access or authority blockers.
5. Return the evidence, uncertainty, owner, next action, and actual continuation boundary.

## Exits

Each exit is one of the five results the command lists. The fix owner must observe the target
regression red before repair and independently confirm that the original caller authorized it. The
other exits return their owner, blocker or resume condition without an invented fix or decision.
