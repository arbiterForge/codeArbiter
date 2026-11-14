---
status: accepted
date: 2026-11-12
title: Classify maintenance-only dependency risk as MEDIUM
decided-by: SUaDtL@users.noreply.github.com
supersedes: none
governs: core/surface/agents/dependency-reviewer.md, core/surface/agents/finding-triage.md, core/surface/agents/verdict-aggregator.md, core/surface/agents/INDEX.md
---

# ADR-0047 — Classify maintenance-only dependency risk as MEDIUM

## Status
Accepted

The product owner made this choice on November 12, 2026 through Claude Code's decision question. The live program progress record retains the attribution and selected option. This is Accepted/Planned; delivery and qualification require separate evidence.

## Context
D-HIGH resolves incompatible meanings of HIGH: a blocking severity and a maintenance-only dependency concern that did not block.

## Decision
1. Maintenance-only dependency risk, including an unmaintained or abandoned dependency without a separate security finding, is MEDIUM and non-blocking.
2. HIGH retains one meaning everywhere: it blocks the affected change.
3. A mixed maintenance and security finding retains its actual security severity; maintenance classification must not downgrade a security concern.

## Alternatives considered
- Keep maintenance-only concerns HIGH but non-blocking: rejected by the owner.

## Consequences
The dependency reviewer, triage funnel and generated role index must use the same severity and blocking rules. Record unresolved maintenance risk honestly.

## Risks
A security issue could be mislabeled maintenance-only. Classification must retain the independent security facts and their actual severity.
