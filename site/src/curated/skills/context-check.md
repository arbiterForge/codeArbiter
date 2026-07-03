---
entity: skills/context-check
related: [commands/context-check]
---

## What it does

This is an optional, on-demand check for a specific bypass case: a merge or a hand edit changed a
tracked source file outside of a normal commit, so the routine auto-heal inside the commit gate
never had a chance to fire. It is not part of the everyday loop — the commit gate's own drift
detection covers that. Invoke this only when you know drift happened outside a commit.

## Phases

1. Compute drift by comparing every tracked document's recorded source hashes against the
   current ones, and report "no stale docs" if nothing has drifted.
2. Report each stale document and the paths that changed under it.
3. For each stale document, offer a per-document choice — re-scout the drifted paths and update or
   propose changes, re-baseline without re-scouting when the underlying change was cosmetic, or
   defer it to reappear later — then summarize what was done.

## Exits

Whatever a re-scout or re-baseline produces rides your next commit through the normal commit gate
— this skill never stages or commits anything itself. A deferred document simply resurfaces at
the next session start.
