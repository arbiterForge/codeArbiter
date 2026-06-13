---
status: accepted
date: 2026-06-13
title: Database-free architecture; Python hooks are stdlib-only
decided-by: SUaDtL@users.noreply.github.com
supersedes: none
governs: plugins/ca/hooks/*
---

# ADR-0004 — Database-free architecture; Python hooks are stdlib-only

## Status
Accepted — ratified 2026-06-13 by SUaDtL@users.noreply.github.com

## Context
codeArbiter has no datastore. Project state is file-based prose artifacts under `.codearbiter/`,
a TypeScript/Node farm dispatcher, and Python hooks. `tech-stack.md` asserts a database-free,
stdlib-only design as prose, but it was never recorded as a deliberate decision — the 2026-06-13
checkpoint's migration and dependency reviewers both keyed off this assumption.

## Decision
codeArbiter remains database-free: no datastore, ORM, or schema layer; project state is file-based
prose artifacts. All hook files under `plugins/ca/hooks/` use the Python standard library only — no
third-party dependencies, ever. Hooks must run on a stock Python install with nothing added.

## Alternatives considered
- **Introduce a datastore** — adds operational weight, migration machinery, and supply-chain
  surface for no benefit at the current scale.
- **Allow third-party hook dependencies** — breaks the stock-Python-install guarantee and the
  zero-friction install posture; expands the supply-chain attack surface of code that runs on
  every tool call.

## Consequences
Easier: zero install friction for hooks, no migration tooling, trivial portability, a small and
auditable dependency surface (only the TS toolchain's devDependencies). Harder: complex state must
be expressed in files; no relational queries or transactional guarantees beyond append-only files.

## Risks
A future feature requiring transactional or relational state would force a reversal of this
decision. **Revisit if project state outgrows what file-based artifacts can safely represent.**
