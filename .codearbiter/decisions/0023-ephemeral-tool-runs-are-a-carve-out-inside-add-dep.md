---
status: accepted
date: 2026-07-26
title: Ephemeral tool runs are a carve-out inside /ca:add-dep, not a command of their own
decided-by: SUaDtL@users.noreply.github.com
supersedes: none
governs: core/surface/commands/add-dep.md, core/surface/includes/routing-table.md, plugins/*/commands/add-dep.md, plugins/*/includes/routing-table.md
---

# ADR-0023 — Ephemeral tool runs are a carve-out inside /ca:add-dep, not a command of their own

## Status
Accepted — explicitly decided by SUaDtL@users.noreply.github.com on 2026-07-26, who chose the
carve-out over a new command projected to all three hosts, and over closing the issue unaddressed.

## Context
`/ca:add-dep` applied whenever an agent needed to download and execute a third-party package. That
conflated two different actions: **adopting** something into the dependency graph, which must update
and review a manifest and lockfile, and **running** a pinned developer tool once to inspect the
repository, which changes nothing.

Issue #346 records the harm. A duplicate-code investigation was interrupted and pushed toward
project-dependency review for `jscpd`, despite an explicit instruction that it was not required by
codeArbiter and must never be listed as a dependency. With no command owning the action, the routing
loop then reached for `/ca:override` — a logged bypass — for an operation that adds no risk at all.

ORCHESTRATOR §6 closes both escapes: nothing may be performed unowned, and a missing owner is a
routing gap to surface rather than a reason to override (ADR-0022). So the action needed a home, and
the only open question was which.

Two of the issue's four acceptance criteria were already satisfied when this was written: the
routing table, the review matrix, and the `dependency-reviewer` frontmatter were all already scoped
to manifest and lockfile changes. What was missing was a sanctioned path for the other case.

## Decision
Add a bounded **Ephemeral tool run** section inside `/ca:add-dep`, plus a routing-table row pointing
at it. Do not create a new command.

The distinguishing test is the dependency **graph**, not the download. Anything entering
`package.json`, a lockfile, or a base image is the existing review, unchanged. A pinned tool run once
against the repository, adopting nothing, is the carve-out.

The carve-out keeps the part of supply-chain review that still applies at full strength — an exact
pinned version and the approved registry — and drops the part that does not, since there is no
manifest to review and no artifact to ship. It requires one confirmation rather than a review,
because the operator has already made the adoption decision, and that decision is "no".

**The load-bearing constraint is verified, not trusted.** A tool that writes a manifest or a lockfile
has performed an adoption, so the run stops and takes the full review. `git status --porcelain` over
those paths after the run is what establishes that, rather than the tool's own claim.

## Alternatives considered
- **A new command projected to all three hosts** — rejected. It would add a public surface (the
  command catalog, the Pi command catalog, the README badges and counts, the site sidebar) to govern
  an action whose entire definition is that it changes nothing. The governance would outweigh the
  governed act, and every future host would inherit the cost.
- **Leave `/ca:add-dep` as it was** — rejected; that is the status quo that produced the wrong
  `/ca:override`.
- **Route it through `/ca:chore`** — rejected. `/ca:chore` accepts docs, dependency bumps, and
  reverts; a tool execution is none of those, and issue #308 already recorded `/ca:chore` refusing a
  neighbouring case before the loop reached for an override.

## Consequences
The ephemeral case has an owner, so the routing loop terminates and `/ca:override` stays rare. The
distinction is written where someone actually hits it — inside the command they were already routed
to — rather than in a separate document they would have to know exists.

Because it is prose in the shared surface, it projects to all three hosts through `build-surface`
with no per-host work, and the `governs:` globs above cover both the canonical source and the
generated projections, so an edit to either surfaces this decision at write time.

## Risks
"Ephemeral" is a judgement, and a tool that quietly writes a lockfile would be adoption wearing the
carve-out's clothes. The post-run `git status` check is what bounds that, and it fails toward the
full review.

Living inside `/ca:add-dep` also means the section can be missed by someone scanning the command list
for a tool-execution owner. The routing-table row exists to catch exactly that reader.

This decision is proven wrong if the carve-out is used to run something that turns out to have been a
dependency, or if operators cannot find it and reach for `/ca:override` again — in which case the
rejected alternative, a command of its own, becomes the remedy.
