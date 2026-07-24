---
status: accepted
date: 2026-07-22
title: Permit bounded selected-provider credential projection for isolated Pi children
decided-by: SUaDtL@users.noreply.github.com
supersedes: 0014
governs: .codearbiter/security-controls.md, .codearbiter/specs/pi-support.md, .codearbiter/plans/pi-support.md, plugins/ca-pi/**
---

# ADR-0016 — Permit bounded selected-provider credential projection for isolated Pi children

## Status
Accepted — explicitly selected by SUaDtL@users.noreply.github.com on 2026-07-22 (conflict option 1).

## Context
ADR-0014 made Pi authentication completely opaque to `ca-pi` while requiring fresh child processes
to retain host-native provider authentication. Live implementation showed those requirements cannot
both hold: an isolated child with a private home cannot see the operator's stored provider session,
while a child that inherits the operator's home can read every credential and mutate operator-owned
Pi state. Tribunal issue #372 exposed that whole-store access as a critical credential-boundary defect.

The maintainer resolved the resulting Level 1 conflict in favor of preserving stored-auth parity
through a bounded, selected-provider projection into private ephemeral child storage.

## Decision
Permit `ca-pi` to read the canonical operator-owned Pi `auth.json` only when preparing an isolated
child, parse it under a strict size bound, and project only the exact provider record selected for
that child. No other provider record, Pi configuration, session, package state, or ambient home data
may enter the child boundary. Environment authentication remains limited to the selected provider's
declared allowlist, with unrelated codeArbiter and provider secrets excluded.

The projection must live under a fresh private child root with private home, agent, session, and
package paths. The credential file is created exclusively with restrictive permissions, never
appears in argv, prompts, results, logs, telemetry, or `.codearbiter/`, and is retained by an open
handle so cleanup does not follow a child-replaced path. Success and every failure path must scrub
the retained credential and remove the isolated root; inability to prove cleanup returns a fixed,
bounded degraded failure.

All other ADR-0014 controls remain in force: exact provider/model with no fallback, disabled ambient
discovery/approval/context/session loading, enforcement-only child activation, bounded stdin and
RPC, whole-process-tree cleanup, fail-closed unknown tools, project-trust separation, and the live
final-argument-ordering promotion gate. User-owned credential commands remain outside this narrow
projection authority unless a later explicit decision defines a comparably bounded mechanism.

## Alternatives considered
- **Keep authentication fully opaque and require environment-only child auth** — rejected because it
  removes stored-session and subscription parity that ADR-0014 explicitly intended to preserve.
- **Reopen or remove isolated Pi subagents** — rejected because private child storage plus exact-record
  projection provides the required parity with a smaller, testable credential surface.
- **Continue inheriting the operator's Pi home** — rejected because it exposes all providers and lets a
  child mutate operator-owned auth, package, configuration, and session state.

## Consequences
Stored-auth children retain native provider parity without receiving the operator's full Pi home.
`ca-pi` now owns a deliberately narrow secret-transport boundary, so provider selection, file bounds,
permissions, cleanup, path-replacement resistance, and error redaction are release-blocking security
contracts. Adding a provider does not widen stored-auth access beyond that provider's exact record.

## Risks
A future Pi auth-store format may make exact-record projection invalid or insufficient. A child may
replace private credential paths or resist cleanup, and platform filesystem semantics may degrade
removal. This decision is proven wrong if projection cannot remain exact-provider-only, ephemeral,
non-observable, and fail-degraded under adversarial lifecycle tests, or if Pi exposes a safer native
delegation mechanism that provides equivalent stored-auth parity without adapter-managed transport.
