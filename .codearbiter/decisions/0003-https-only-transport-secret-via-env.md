---
status: proposed
date: 2026-06-13
title: Outbound HTTPS-only API transport with loopback exception; FARM_API_KEY via env only
decided-by: SUaDtL@users.noreply.github.com
supersedes: none
governs: plugins/ca/tools/farm.ts
---

# ADR-0003 — Outbound HTTPS-only API transport with loopback exception; FARM_API_KEY via env only

## Status
Proposed

## Context
`farm.ts` sends an `Authorization: Bearer ${FARM_API_KEY}` header on outbound API calls. The
2026-06-13 checkpoint found that the parse-time `https://` validation covered only
`plan.meta.apiBaseUrl`, so a `FARM_API_BASE_URL` env override could resolve to `http://` and
send the secret over cleartext. Remediated this sprint by validating the resolved URL.

## Decision
All outbound API calls use HTTPS. The **resolved** `apiBaseUrl` — after the `FARM_API_BASE_URL`
env override, `plan.meta.apiBaseUrl`, and the built-in default are applied in that precedence —
is validated by `assertSecureBaseUrl` before every outbound call: `https://` only, with a
documented loopback `http://` exception (`127.0.0.1` / `localhost`, no userinfo) for test mocks,
implemented with WHATWG `URL` parsing (the same parser `fetch` uses for connection targeting, so
there is no parser-differential bypass). `FARM_API_KEY` is read only from `process.env` and flows
only into the `Authorization` header.

## Alternatives considered
- **Parse-time-only validation (status quo ante)** — the env-override bypass that caused the
  cleartext-leak finding.
- **Regex-based scheme/host check** — workable but risks parser-differential edge cases between
  the guard and `fetch`; URL parsing eliminates that class.

## Consequences
Easier: a documented, enforced protection against sending the Bearer secret over cleartext, on
every fetch path; loopback test mocks continue to work without TLS.

## Risks
The loopback `http://` exception is a deviation from a strict no-HTTP rule, mitigated by the
same-parser guarantee (a host normalizing to loopback connects to loopback) and the
boundary-table declaration. **Residual, tracked and deferred:** `FARM_API_KEY` is still passed in
the environment of spawned child processes (a LOW finding not in this sprint's scope) — close it
in a later change.
