---
title: Concepts
description: "The core ideas behind codeArbiter: gated lanes, the Feature Forge, SMARTS, ADRs, and checkpoints."
---

These are the ideas the lanes are built on.

## The gated-lane model

Every kind of work has a **lane**: a sanctioned path with gates scaled to its risk. A lane
is not a suggestion. It is the only way that kind of change ships. `/ca:fix` and
`/ca:feature` run test-first through the `tdd` gate. `/ca:refactor` must prove behavioral
parity through *unmodified* pre-existing tests. `/ca:chore` carries lighter gates, because
prose edits and dependency bumps don't demand TDD.

Gates come in two strengths. **Soft gates** surface a decision and wait for the user.
**Hard gates** are true stops, never auto-decided, even under autonomous execution:
anything in the security controls, auth/crypto/secret changes, irreversible operations, a
gate bypass, an unresolved decision, or a merge to the default branch. Hard gates are rare
by design. When they trip often, that's a signal the spec was too thin, not an obstacle to
grind past.

<figure class="ca-diagram">
  <img src="/codeArbiter/diagrams/gate-model.svg" alt="Gate model. A soft gate surfaces a decision bubble and waits for the user. A hard gate is a closed cross-bar that is never auto-decided." loading="lazy" />
  <figcaption>Soft gates surface and wait. Hard gates stop, and only the user can clear them.</figcaption>
</figure>

## The Feature Forge

SemVer answers one question: did the plugin payload change? A version bump means every user
gets the new payload. It says nothing about whether a given feature inside that payload is
ready to trust by default.

The **Feature Forge** answers the second question, per feature. A feature can ship in
**preview**: opt-in, dormant, off by default. It rides along in a release without changing
anyone's behavior until they turn it on. Once real-world evidence shows it holds up, it gets
promoted to **stable** and becomes on by default. The version says the whole payload moved;
the forge says which individual features have earned trust.

That is the two-axis model. Read them together and a release is legible: SemVer governs the
whole payload, the Feature Forge governs each feature's maturity.

<figure class="ca-diagram">
  <img src="/codeArbiter/diagrams/two-axis-model.svg" alt="Two-axis labeling model. SemVer governs the whole plugin payload; the Feature Forge governs each feature as preview (opt-in, dormant) or stable (on by default, evidence-promoted)." loading="lazy" />
  <figcaption>Two axes: SemVer for the whole payload, the Feature Forge for per-feature maturity.</figcaption>
</figure>

<div class="ca-callout ca-callout--preview">
  <p class="ca-callout__label">Preview</p>
  <code>/ca:sprint --farm</code> is a preview feature. It ships dormant, off until you opt
  in, and stays preview until evidence promotes it. The promotion bar is a deliberate owner
  decision tracked in the project's decision log, not a switch the plugin flips on its own.
</div>

Promotion is driven by evidence, not by a calendar. A preview feature graduates when its
real-world use shows it is safe to default on, and that judgment is recorded as a tracked
decision rather than assumed. The forge keeps the cost of trying something new low and the
cost of trusting it honest.

## SMARTS

When codeArbiter must weigh options, and especially when `/ca:sprint` decides "as the user"
during an autonomous run, it doesn't pick on vibes. It runs a structured, multi-lens scoring
rubric called **SMARTS** and records the verdict: the options weighed, the lens scores, the
chosen option, and a confidence flag. Low-confidence calls are exactly what the user reviews
afterward. Nothing hides behind autonomy. Every auto-decision lands in an append-only sprint
log.

## ADRs and the decision log

Architecturally significant choices are written down as **Architecture Decision Records**:
numbered, dated, and attributed to the user who made them, stored under the project's
decision log. codeArbiter never authors an ADR as its own judgment; every record carries
explicit user attribution. The decision-lifecycle skill maintains supersede chains, so a
newer ADR can replace an older one, and it can report decision health: which records are
aging, unchallenged, or in conflict.

## Checkpoints

A **checkpoint** is a periodic, read-only sweep of the whole codebase by the reviewer fleet.
The findings are consolidated, classified by severity, and triaged into a single dated
report. The ones that block the current change are called out, the rest recorded.
Checkpoints are how drift and latent issues get caught between feature work, without
blocking any single change.

## The persona-register split

codeArbiter speaks with more than one voice, deliberately. The **orchestrator** persona is
terse and decisive; it routes, gates, and states. The **author** and **reviewer** agents
each carry their own focused register and tools, scoped to their job. Splitting the persona
register keeps each role sharp. The orchestrator isn't trying to also be a backend engineer,
and a security reviewer isn't trying to also be a copywriter. Each agent loads only the
context its role needs, which is also what keeps the standing footprint small.

## Provenance & context drift

Every derived document under `.codearbiter/` traces its claims to source files in the repo. codeArbiter records this mapping as **provenance**: which files back a given doc, and the `git hash-object` hash of each file at the time the doc was authored. When a tracked source changes, the stored hash no longer matches. That mismatch is **context drift**.

Drift is surfaced once, passively, as a single line at SessionStart. It does not interrupt work. `.codearbiter/code-map.md` provides a coarse orientation map: it names the main source files and the docs that depend on them. `/ca:context-check` runs the same detection on demand, as a manual audit.

When a commit lands, the **commit-gate auto-heal** step checks whether any staged source files have drifted their dependent docs. If they have, it re-baselines the provenance in the same commit or proposes a doc update to accompany the work. A drifted claim is suppressed rather than surfaced as if fresh. A stale assertion cannot appear as current fact.

<figure class="ca-diagram">
  <img src="/codeArbiter/diagrams/provenance-drift-flow.svg" alt="Context-drift provenance flow: a tracked source change is detected by a git hash-object mismatch, surfaced at SessionStart, and healed by commit-gate which re-baselines or proposes a doc update with the work commit." loading="lazy" />
  <figcaption>Provenance tracks source hashes. A mismatch is detected at SessionStart and healed when the commit lands.</figcaption>
</figure>

## Just-in-time context injection

When any agent reads a file, a `PreToolUse:Read` hook fires first. It checks whether the file is governed by any knowledge document and, if so, injects a short pointer capped at a 150-token budget. The Read always proceeds. The hook is fail-open and never blocks it.

The check follows a four-tier priority map. Each tier is evaluated in order; the first match wins:

1. **Security controls:** if the file path is a security-entry point in `security-controls.md`, that document governs it.
2. **Accepted ADRs:** any accepted ADR whose `governs:` glob matches the path.
3. **Approved specs:** any spec carrying a `**Governs:**` header line whose glob matches the path. A spec opts in by adding that line.
4. **Provenance claims:** a provenance claim whose stored `git hash-object` hash still matches the current file.

A file that matches none of these tiers is non-governed. The hook injects nothing and makes no git call. Injection is deduplicated once per session and file, so repeated reads of the same file do not accumulate pointer tokens.

<figure class="ca-diagram">
  <img src="/codeArbiter/diagrams/four-tier-map.svg" alt="The four-tier file-to-knowledge map: a Read is matched against security-controls.md, accepted ADRs, approved specs, and provenance in priority order, and the highest-priority match's pointer is injected within a 150-token budget." loading="lazy" />
  <figcaption>Four tiers, evaluated in priority order. The highest match governs; a non-governed Read injects nothing.</figcaption>
</figure>

## Auditability

Taken together, these concepts make a codeArbiter repository auditable after the fact. ADRs
say *why*. The sprint log says *what was auto-decided and how confidently*. Checkpoints say
*what the sweeps found*. An append-only override trail records every sanctioned bypass. The
governance record can be assembled for any range of work on demand.

For the concrete catalog of what runs in each lane, see the auto-generated
[Reference](../reference/).
