---
status: accepted
date: 2026-06-16
title: Broad-adoption OSS posture, optimizing for adoption over a commercial vertical
decided-by: SUaDtL@users.noreply.github.com
supersedes: none
governs: README.md, docs/*
---

# ADR-0006 — Broad-adoption OSS posture

## Status
Accepted — ratified 2026-06-16 by SUaDtL@users.noreply.github.com

## Context
The 2026-06 market-readiness evaluation (issue #70) scored distribution 4/10 and recommended
re-targeting the project to a regulated/audited commercial vertical, on the reasoning that the
audit trail, attribution, and SMARTS machinery have no single-player payoff and read as
compliance features. The maintainer rejected that framing: codeArbiter is open source, it is
already in daily use by the maintainer's own team who rely on it, and the goal is broad public
adoption of a tool with demonstrated value. The real and only hard problem is getting the
public to try proven-internally software.

## Decision
codeArbiter remains broad open-source software optimized for public adoption. It does not
re-target to a regulated or otherwise narrow commercial vertical ICP. The strategic objective
is maximizing the number of people who adopt and benefit from the tool, grounded in the
existing proof that a real team adopts it and depends on it daily.

## Alternatives considered
- **Re-target to a regulated/commercial vertical (the eval's #70 recommendation)** — declined.
  It trades a frictionless OSS install for a slow enterprise sales motion the maintainer does
  not want, and discards the broad-adoption goal that is the actual intent.
- **Agent-fleet/team-scale ICP** — declined. It wants shared-state infrastructure that ADR-0004
  (database-free, stdlib-only) deliberately excludes, and still narrows away from broad adoption.

## Consequences
Easier: a single, honest positioning story. The adoption bottleneck is now named as
time-to-first-value plus visible proof, which makes the priority order concrete:
cold-install observation (#70 move 1), a demo above the fold (#71), a zero-onboarding dry run
(#81 `/ca:preview`), and README positioning that surfaces real adoption proof (#72). Harder:
no revenue motion funds the work; adoption must be earned through the product and its first
five minutes, not a sales channel. The audit-trail/SMARTS machinery stays — it is a quality
and trust feature for the broad audience, not only a compliance one.

## Risks
Broad-adoption-without-revenue can stall on maintainer bandwidth. The eval's distribution
critique remains valid even under this posture: choosing OSS does not by itself produce users.
This decision is proven wrong if, after time-to-first-value and proof work ships, external
adoption still does not move — at which point the vertical-ICP question legitimately reopens.
