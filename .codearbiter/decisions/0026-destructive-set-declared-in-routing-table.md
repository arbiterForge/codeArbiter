---
status: accepted
date: 2026-08-07
title: Destructive operations declared in the routing table
decided-by: SUaDtL@users.noreply.github.com
supersedes: 0022-auto-route-unambiguous-safe-intent-into-its-command
governs: core/surface/ORCHESTRATOR.md, core/surface/includes/routing-table.md, plugins/*/ORCHESTRATOR.md, plugins/*/includes/routing-table.md
---

# ADR-0026 — Destructive operations declared in the routing table

## Status
Accepted — explicitly ratified by SUaDtL@users.noreply.github.com on 2026-08-07 ("accept both").
Decision content approved the same day in the `recorded-intent-kernel-campaign` sprint spec (rev 2).

## Context

ADR-0022 hardcoded the destructive set (the operations that force tier-2 confirmation regardless
of intent clarity) as an enumeration inside ORCHESTRATOR §6, and recorded its own preferred
refinement: declare destructiveness in the routing table so a newly added destructive command
cannot be auto-routed by omission ("the routing-table variant above is the fix if it bites",
ADR-0022 §Risks). Current-generation models reliably execute load-then-check steps, making the
declared-registry form viable. Adversarial review (2026-08-07) killed the naive per-row-flag
mechanism: two of the five set members (`/override`, `/dev` entry) have no routing-table row at
all; "merge to the default branch" is an operation inside several lanes, not a cue; and flagging
the `standup`/`cleanup` rows would re-demote the very cues ADR-0022 existed to unblock (#308).

## Decision

**Partial supersession of ADR-0022 — one clause only.** The three-tier routing decision and the
tier-1 requirement (unambiguous AND non-destructive) remain in force unchanged. Superseded is
only the placement clause "the destructive set is enumerated in the orchestrator":

- `routing-table.md` gains an **operation-scoped block** — `## Destructive operations (tier-2
  regardless of cue)` — as the authoritative registry. Operations, not cues: `/override`, merge
  to the default branch, branch or worktree deletion, release and tag publication, `/dev` entry.
  Optional per-row flags only for rows that are wholly destructive (release). No new table
  column: `check_routing_index_parity.py` reads cells by position, and a column shift would
  silently vacate its validation.
- ORCHESTRATOR §6 **keeps a resident copy** of the set — tier classification happens before any
  file load, so the kernel cannot defer it — and CI checks the resident copy item-for-item
  against the routing-table block (same pattern as the #618 INDEX/routing-surface invariant).
  The consistency check is proven by a seeded mismatch with its failing log captured.
- Adding a destructive command henceforth means adding it to the routing-table block; CI failure
  on kernel/table divergence replaces reviewer memory as the update mechanism.

## Alternatives considered

- **Keep the hardcoded §6 enumeration only (status quo)** — rejected: a new destructive command
  is auto-routable by omission until a human remembers the kernel list; ADR-0022 already named
  this its known weakness.
- **Per-row destructive flag column** — rejected (adversarial review): cannot express 2 of 5
  members, distorts cue-scoped rows into operation semantics, re-demotes #308's cleanup cues,
  and breaks the position-based parity checker.
- **Registry as the ONLY copy (drop the §6 resident set)** — rejected: tier classification is a
  pre-load decision; a kernel without the resident set would have to load the routing table on
  every off-channel instruction, defeating the lazy-load design.

## Consequences

The destructive set gains a single authority with mechanical drift detection; the kernel copy
becomes a CI-checked projection. The routing table's contract widens from trigger→route to also
carrying operation-scoped safety declarations — its header prose must say so. Test pin
`test_routing_and_cleanup_surface.py:79` (per-item §6 enumeration) is repointed to assert both
surfaces and their consistency.

## Risks

Two copies with a checker is still two copies — a CI outage window could admit drift (bounded:
the check runs on every PR). The block's item wording must stay byte-comparable between surfaces
or the checker needs normalization logic that itself can rot. Proven wrong if a destructive
command ships in the table block but the kernel projection lags a release, or if the
consistency check's normalization admits a semantic mismatch it reads as equal.
