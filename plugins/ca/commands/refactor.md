---
description: Restructure code with behavioral parity proven through unmodified pre-existing tests, then refactor. No behavior change.
argument-hint: "<surface and motivation>"
---

# /ca:refactor — behavior-preserving restructure

The only permitted entry to refactor work. A refactor that cannot prove parity through unmodified pre-existing tests is a feature change in disguise and routes to `/ca:feature`. Two required parts: the **surface** (exact files, functions, classes, or methods — vague surfaces like "the auth module" are rejected) and the **motivation** (why the restructure is worth doing).

## Routes to

The `refactor` skill (`${CLAUDE_PLUGIN_ROOT}/skills/refactor/SKILL.md`) — six gated phases: surface
identification, parity coverage proof, conditional red parity tests, implementation, parity
verification, lint/coverage gate. The skill is canonical for its phases and gates; they are not
restated here.

## When NOT to use

- New behavior — a new branch, error path, side effect, public method beyond a Phase 3 seam, or a
  change to what any input maps to → `/ca:feature`.
- A change motivated by "the current behavior is wrong" → `/ca:fix`.
- Questions or discussion → `/ca:btw`.
- Persisting an already-completed refactor → `/ca:commit`.

## Hard gate

No refactor proceeds without behavioral-parity coverage proof in Phase 2; if the surface is
under-covered, the skill halts and routes to `tdd` Phase 1 to backfill before resuming. A Phase 4 diff
that would classify as `feat`, or a Phase 5 verification that depends on edits to a pre-existing test,
terminates the refactor and re-routes to `/ca:feature` or `/ca:fix`.
