---
status: accepted
date: 2026-11-12
title: Require declared pre-tag checks
decided-by: SUaDtL@users.noreply.github.com
supersedes: 0040-independent-per-target-release-with-consumer-safety-gates
governs: .github/workflows/ci.yml, .github/workflows/release.yml, .github/actions/publish-target/*, .github/scripts/check_auto_release_candidate.py, core/pysrc/_releaselib.py, core/surface/skills/release/**
---

# ADR-0048 — Require declared pre-tag checks

## Status
Accepted

The product owner made this choice on November 12, 2026 through Claude Code's decision question. The live program progress record retains the attribution and selected option. This is Accepted/Planned; delivery and qualification require separate evidence.

## Context
D-GOV-PRETAG ratifies required enforcement. ADR-0040 clause 4 calls release-skill pre-tag proof advisory; current CI and release paths enforce the declared checks. The owner chose required checks rather than weakening enforcement.

## Decision
1. Declared target pre-tag checks are required. A failed declared check blocks the affected candidate or publication; it must not become a warning.
2. This supersedes only ADR-0040's advisory treatment of release-skill pre-tag proof. Its independent per-target release behavior and other advisory checks retain their separately applicable decisions and later successors.
3. The checks retain their existing declared-input, check-only, content-binding and clean-tree contracts. Success grants no merge or publication authority and establishes no unrelated installed-host qualification.

## Alternatives considered
- Restore advisory pre-tag behavior: not selected by the owner.

## Consequences
Declared targets, candidate preflight, the release owner and generated guidance must agree that these checks are required. Correct failing inputs or checks without silently removing the gate.

## Risks
A faulty check can block delivery. Preserve its actual failure and repair the owning implementation; bookkeeping success is not release evidence.
