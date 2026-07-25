---
status: accepted
date: 2026-07-25
title: Auto-route unambiguous, non-destructive intent into its command
decided-by: SUaDtL@users.noreply.github.com
supersedes: none
governs: core/surface/includes/redirect.md, core/surface/includes/routing-table.md, plugins/ca/ORCHESTRATOR.md, plugins/ca-codex/ORCHESTRATOR.md, plugins/ca-pi/ORCHESTRATOR.md
---

# ADR-0022 — Auto-route unambiguous, non-destructive intent into its command

## Status
Accepted — explicitly decided by SUaDtL@users.noreply.github.com on 2026-07-25. Amends ORCHESTRATOR
§6; the §6 invariant itself is preserved, not relaxed (see Decision).

## Context
§6 read: *"All intent flows through a slash command … The user picks; nothing routes without their
command."* In practice the orchestrator would infer the intent, name the exact command, and then ask
the user to type it back — a redirect of the form *"for that action, run `/ca:fix <exactly what you
just asked for>`"*.

That is ceremony, not governance. Naming the command demonstrates the routing was already
understood; requiring it to be retyped adds friction without adding a decision.

The friction also produced harm rather than safety. Issue #308 records a post-merge cleanup where no
command owned the operation and the redirect loop produced **two incorrect routes — first to
`/ca:chore`, then to `/ca:override`.** An override for routine repository hygiene is exactly what
overrides exist to be rare for: a rule intended to ensure deliberate routing instead manufactured an
unjustified bypass.

## Decision
Route on understood intent, in three tiers:

1. **Unambiguous and non-destructive** — route directly into the command. Every gate runs exactly as
   if the user had typed it.
2. **Probable** — ask once, naming the command (*"did you mean `/ca:fix`?"*). One approval, then
   route. The user approves rather than retypes.
3. **Genuinely unclear** — present the candidate commands and let the user pick.

**The invariant §6 actually protects is preserved by construction.** §6 exists so that nothing
happens outside a gated command path — not so that the user does typing. Auto-routing *into* the
command satisfies it completely. What remains prohibited, and is the line this ADR draws, is the
orchestrator performing the work itself instead of routing: it routes the command, it does not
improvise the operation.

**Clarity and risk are separate axes.** Tier 1 requires BOTH unambiguous intent AND a
non-destructive command. Anything irreversible or gate-bypassing — `/ca:override`, merge to the
default branch, branch or worktree deletion, release and tag publication, `/ca:dev` entry — drops to
tier 2 and asks, even when the intent is obvious. There the confirmation is the gate, not friction.

## Alternatives considered
- **Keep §6 as written** — rejected. The dead end it produced was caused by no command owning the
  operation, and the redirect loop converted that gap into a wrong override rather than preventing
  one.
- **Auto-route anything unambiguous, destructive included** — rejected. The commands' own gates do
  stop and ask in most cases, but "clear intent" and "safe to perform without confirmation" are
  different properties, and conflating them puts the irreversible cases on the wrong side.
- **Declare the destructive set per-command in the routing table** — considered and deferred. It is
  more auditable and prevents a new command being auto-routed by omission; recorded here as the
  preferred refinement if the hardcoded set proves hard to keep current.

## Consequences
The redirect stops asking for a command it has already named. A user saying "go fix that" or "let's
run a checkpoint" reaches the routed skill with its gates intact.

Issue #308's other half ships alongside: a sanctioned owner for the merged-branch transition, which
proves the branch is an ancestor of the *fetched* default, classifies dirty artifacts as unique,
redundant, or superseded, and never discards unique or ambiguous data without per-item confirmation.
Closing that gap removes the cause the redirect loop was reacting to.

## Risks
"Unambiguous" is a judgement the orchestrator makes about its own routing, so a mis-classification
routes a command the user did not intend. Two things bound it: tier 1 excludes everything
irreversible, and the routed command's own gates still run — a wrongly routed `/ca:fix` stops at
`tdd` Phase 1 exactly as a typed one would.

The destructive set is enumerated in the orchestrator rather than declared per command, so a newly
added destructive command could be auto-routed by omission. That is the known weakness, and the
routing-table variant above is the fix if it bites.

This decision is proven wrong if auto-routing produces a command the user did not want with
consequences a gate did not catch, or if the destructive enumeration is found stale after a new
command ships.
