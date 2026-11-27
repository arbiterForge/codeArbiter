---
status: accepted
date: 2026-11-16
title: Require HTTPS outside bounded loopback
decided-by: User during this Codex conversation
supersedes: 0018-endpoint-acceptance-and-value-shape-pinning
governs: .codearbiter/context/security-controls.html, plugins/ca-pi/tools/src/child-env.ts, plugins/ca-pi/tools/src/inference-broker.ts, plugins/ca-pi/tools/src/*.test.ts
---

# ADR-0049 — Require HTTPS outside bounded loopback

## Status
Accepted

The user explicitly selected "Require HTTPS outside loopback; supersede the older endpoint rule" on 2026-11-16 in response to the Pi transport-policy question. Acceptance records the governance decision as Accepted/Planned, not implementation or qualification.

## Context
CON-004 requires HTTPS except narrowly bounded loopback test/broker paths. ADR-0018 allowed structurally bounded absolute HTTP or HTTPS endpoints, and ADR-0019 retained that endpoint rule while replacing credential projection with a parent broker. The user resolved this conflict in favor of HTTPS outside bounded loopback.

## Decision
Provider endpoints outside narrowly bounded loopback must use HTTPS; external HTTP endpoints are refused.

HTTP remains limited to the existing narrowly bounded loopback test and parent-broker paths.

This decision replaces only the plain-HTTP endpoint allowance of ADR-0018 as inherited by ADR-0019. Their other endpoint-shape, credential-blindness, scrubbing, TLS-verification and broker-lifetime requirements remain in force.

Partial supersession is forward-only. ADRs 0018 and 0019 remain unchanged as historical records; the clause replaced here is their broader allowance of HTTP provider endpoints.

## Alternatives considered
- **Require HTTPS outside bounded loopback** — selected explicitly by the user.
- **Keep HTTP-compatible provider endpoints and document an exception** — offered in the same question and not selected.

## Consequences
Existing external HTTP provider configurations require HTTPS before they can be admitted. The existing bounded loopback test and parent-broker flows remain possible. No provider fallback or publication authority follows from this decision.

## Risks
External HTTP-only configurations lose compatibility under the selected policy. This record does not establish implementation or transport qualification; those require source-bound behavior and refusal evidence. The existing same-user loopback residual described by ADR-0019 is unchanged.
