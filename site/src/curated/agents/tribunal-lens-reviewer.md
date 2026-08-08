---
entity: agents/tribunal-lens-reviewer
related: [skills/tribunal, commands/tribunal, architecture-drift-reviewer]
---

## Role

The single generic executor behind every tribunal audit lens. `/ca:tribunal`'s roster dispatch
sends this agent out once per active lens, and each dispatch carries an assignment: which lens to
run, which slice of the codebase to cover, and where the run's on-disk record lives. The agent
then loads that lens's card from disk and works through its checklist against the assigned scope,
strictly read-only, touching nothing outside the run directory.

## One body, eleven cards

This agent replaced eleven `tribunal-<lens>-reviewer` agents that were near-duplicates of each
other: identical dispatch, evidence, and reporting mechanics wrapped around a different checklist.
The per-lens substance now lives in eleven [lens cards](/reference/#tribunal-lenses), one card per
lens (starting with [appsec](/reference/tribunal-lenses/appsec/)), each carrying that lens's scope
weighting, required project reading, checklist, exposure denominator, and out-of-scope boundary.
Consolidating the shared machinery into one body means a mechanics fix lands once instead of
eleven times, and a lens's mandate changes by editing its card, not by rewriting an agent.

## Assignment mechanism

The dispatch prompt opens with an assignment block naming the lens slug, the scope slice, and the
run directory. The slug must resolve to a real card under the tribunal skill's lens references; if
no such card exists on disk the agent treats the dispatch as malformed and stops rather than
inventing its own mandate. It re-reads the card fresh on every dispatch instead of relying on any
remembered summary of it.

## Why this model tier

Ships `model: inherit` because the reasoning budget is chosen per lens, not per agent: the
tribunal skill's dispatch guidance runs the adversarial lenses (appsec, architecture, reliability)
on the highest-reasoning tier and scales the remaining lenses down to cheaper tiers. One body
serving all eleven lenses has to leave the tier to the caller.

## What it emits

Individual finding records under the run directory's per-lens findings folder, each persisted the
instant the defect is confirmed so an interrupted run loses nothing, with numbering continued from
whatever is already on disk. Severity and confidence in those records are provisional; the
orchestrator's triage pass recalibrates them. Back to the caller it returns only a compact
summary: severity counts, leading finding ids, and the lens's exposure figure.
