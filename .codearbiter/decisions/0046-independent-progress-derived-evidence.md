---
status: accepted
date: 2026-11-12
title: Preserve independent progress and derive evidence applicability
decided-by: SUaDtL@users.noreply.github.com
supersedes: 0043-assistive-state-engine
governs: core/artifacts/**, core/surface/includes/artifacts.md, core/pysrc/_artifact*.py
---

# ADR-0046 — Preserve independent progress and derive evidence applicability

## Status
Accepted

The product owner made this choice on November 12, 2026 through Claude Code's decision question. The live program progress record retains the attribution and selected option. This is Accepted/Planned; delivery and qualification require separate evidence.

## Context
D-PROGRESS selected option B from the native SMARTS packet. ADR-0043 required progress/evidence separation without choosing its representation. Dependency invalidation had overwritten prior progress with STALE.

## Decision
1. Preserve recorded work progress independently of dependency and evidence invalidation. Keep actual user stops, adverse observations and historical evidence; an upstream change does not erase downstream progress or an independent stop.
2. Derive evidence applicability on demand from actual current inputs, separately from dependency readiness. An unavailable or incomplete basis remains unassessed or unknown; a label or receipt reference alone is not current proof.
3. Keep option A only as a temporary old-client reader bridge. Legacy STALE without trustworthy prior state remains legacy/unresolved with its raw value and reason retained. Never invent recovered progress or permit unsupported writes.

This selects ADR-0043's progress representation; its ordinary-work, host-permission and publication boundaries remain in force.

## Alternatives considered
- Compatibility overlay alone: retained only as the temporary reader bridge.
- Persisted assessments: not selected; option B derives applicability.

## Consequences
Mutators, dependency advice, contextual reads, renderers and compatible clients must agree on the selected semantics. Preserve historical progress while evidence currentness changes, and disclose unrecoverable legacy state.

## Risks
Incomplete assessment can be mistaken for current proof. Keep its actual basis and omissions visible and preserve adverse observations through reassessment.
