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

1. Load the available valid provenance records and compare concrete paths marked
   `drift_trigger: true` with their current hashes. An empty report is about those checked
   records, not every document or claim in the repository.
2. Report each stale document and the paths that changed under it.
3. For each stale document, offer a per-document choice — re-scout the drifted paths and update or
   propose changes, re-baseline without re-scouting when the underlying change was cosmetic, or
   defer it to reappear later — then summarize what was done.

## Exits

Whatever a re-scout or re-baseline produces rides your next commit through the normal commit gate
— this skill never stages or commits anything itself. Deferring changes nothing. Its mismatch remains eligible for a later drift report; that is not
a newly persisted follow-up or guaranteed alarm when records cannot be read. Invalid records,
interview-only records and unavailable hashes require separate interpretation.

[Provenance and context drift](/concepts/provenance-drift/) explains those limits with a real
disposable-helper observation. The read-time pointer budget is a different mechanism from this
manual maintenance workflow.
