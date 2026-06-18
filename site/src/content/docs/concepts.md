---
title: Concepts
description: The core ideas behind codeArbiter — gated lanes, SMARTS, ADRs, checkpoints, and the persona-register split.
---

These are the ideas the lanes are built on.

## The gated-lane model

Every kind of work has a **lane**: a sanctioned path with gates scaled to its
risk. A lane is not a suggestion — it is the only way that kind of change ships.
`/ca:fix` and `/ca:feature` run test-first through the `tdd` gate; `/ca:refactor`
must prove behavioral parity through *unmodified* pre-existing tests; `/ca:chore`
carries lighter gates because prose and dependency bumps don't demand TDD.

Gates come in two strengths. **Soft gates** surface a decision and wait for the
user. **Hard gates** are true stops that are never auto-decided, even under
autonomous execution: anything in the security controls, auth/crypto/secret
changes, irreversible operations, a gate bypass, an unresolved decision, or a
merge to the default branch. Hard gates are rare by design — when they trip
often, that's a signal the spec was too thin, not an obstacle to grind past.

## SMARTS

When codeArbiter must weigh options — and especially when `/ca:sprint` decides
"as the user" during an autonomous run — it doesn't pick on vibes. It runs a
structured, multi-lens scoring rubric called **SMARTS** and records the verdict:
the options weighed, the lens scores, the chosen option, and a confidence flag.
Low-confidence calls are exactly what the user reviews afterward. Nothing is
hidden behind autonomy — every auto-decision lands in an append-only sprint log.

## ADRs and the decision log

Architecturally significant choices are written down as **Architecture Decision
Records** — numbered, dated, and attributed to the user who made them, stored
under the project's decision log. codeArbiter never authors an ADR as its own
judgment; every record carries explicit user attribution. The decision-lifecycle
skill maintains supersede chains (a newer ADR can replace an older one) and can
report decision health — which records are aging, unchallenged, or in conflict.

## Checkpoints

A **checkpoint** is a periodic, read-only sweep of the whole codebase by the
reviewer fleet. The findings are consolidated, classified by severity, and
triaged into a single dated report — the ones that block the current change are
called out, the rest recorded. Checkpoints are how drift and latent issues get
caught between feature work, without blocking any single change.

## The persona-register split

codeArbiter speaks with more than one voice, deliberately. The **orchestrator**
persona is terse and decisive — it routes, gates, and states. The **author** and
**reviewer** agents each carry their own focused register and tools, scoped to
their job. Splitting the persona register keeps each role sharp: the orchestrator
isn't trying to also be a backend engineer, and a security reviewer isn't trying
to also be a copywriter. Each agent loads only the context its role needs, which
is also what keeps the standing footprint small.

## Auditability

Taken together, these concepts make a codeArbiter repository auditable after the
fact: ADRs say *why*, the sprint log says *what was auto-decided and how
confidently*, checkpoints say *what the sweeps found*, and an append-only override
trail records every sanctioned bypass. The governance record can be assembled for
any range of work on demand.

For the concrete catalog of what runs in each lane, see the auto-generated
[Reference](/reference/).
