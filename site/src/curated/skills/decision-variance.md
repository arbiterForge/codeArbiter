---
entity: skills/decision-variance
related: [commands/reconcile, decision-lifecycle]
gates:
  - gate: stale-decision surfacing
    when: a decision log exists
    effect: any prior decision whose cited artifact section has since changed is flagged for you to re-evaluate, keep, or supersede before new variances are generated
  - gate: user-attributed resolution
    when: presenting each variance
    effect: nothing is recorded to the decision log without your explicit choice; the skill only recommends
---

## What it does

This is the arbitration pass over the project's architectural artifacts — invoked by the reconcile
command when the written plan and the actual codebase disagree, or an existing decision record
conflicts with either. It builds an evidence index comparing what the plans say against what the
code shows, scores each disagreement through a shared six-lens framework, and presents every one
to you for a decision, one area at a time, logging your choice as it's made.

## Phases

1. Locate the project's three architectural artifacts and the decision log, and surface any prior
   decision whose cited section has since changed for you to dispose of.
2. Build an evidence index classifying every architectural decision as agreeing, disagreeing,
   silent on one side, or silent on both.
3. Generate a scored report for every disagreement, each carrying a recommendation and citing
   relevant precedent from the existing log.
4. Present the variances area by area and record your resolution to the decision log immediately,
   never batched in memory; you may pause and resume at any point.
5. Report which downstream documents the current decision state is ready to support.

## Exits

Each resolved variance lands as a user-attributed entry in the append-only decision log. The skill
never edits the artifacts, the scaffold, or the codebase to fix a variance itself, and it never
produces a downstream document without your explicit direction to do so.
