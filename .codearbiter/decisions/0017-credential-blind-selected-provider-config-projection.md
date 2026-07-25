---
status: accepted
date: 2026-07-24
title: Permit credential-blind selected-provider configuration projection for isolated Pi children
decided-by: SUaDtL@users.noreply.github.com
supersedes: 0016
governs: .codearbiter/security-controls.md, .codearbiter/specs/pi-support.md, .codearbiter/plans/pi-support.md, plugins/ca-pi/**
---

# ADR-0017 — Permit credential-blind selected-provider configuration projection for isolated Pi children

## Status
Accepted — explicitly selected by SUaDtL@users.noreply.github.com on 2026-07-24 (option:
credential-blind selected-provider config projection).

Partial supersession of ADR-0016. This ADR amends exactly one clause of ADR-0016's Decision section —
the sentence *"No other provider record, Pi configuration, session, package state, or ambient home
data may enter the child boundary."* — and only insofar as that sentence names **Pi configuration**.
The rest of that sentence (no other provider record, no session, no package state, no ambient home
data) and every other word of ADR-0016, including the entire `auth.json` credential-projection
contract, remain in force unchanged. ADR-0016's file is not edited; supersession is forward-only.

## Context
ADR-0016 gave the isolated Pi child a private agent directory and permitted only the exact selected
provider's `auth.json` record to cross into it. Live verification against Pi 0.80.10 showed that Pi
also binds `models.json` to `getAgentDir()` (`dist/config.js:425`, `dist/core/model-runtime.js:58`)
with no separate environment override. A private agent directory therefore has no `models.json` at
all, so the child silently loses every operator-defined provider endpoint, protocol selection, and
model definition, and resolves the selected provider from Pi's **built-in** catalog instead. Observed
consequence: a child launched against a deterministic loopback provider instead contacted the real
`api.openai.com` and failed with `OpenAI API error (401)`. In production the same defect silently
breaks every gateway, proxy, Azure deployment map, and self-hosted model — and, worse, sends an
operator credential to an endpoint the operator did not configure.

The decisive fact is that in the canonical case `models.json` contains **no secret**. Its `apiKey` is
a `$VAR` template (for example `"$OPENAI_API_KEY"`) — a pointer Pi resolves from the process
environment, which the child already receives through ADR-0016's provider environment allowlist.
Endpoint configuration and credential transport are therefore separable, and restoring endpoint
parity does not require widening the credential boundary at all.

## Decision
Permit `ca-pi` to read the canonical operator-owned Pi `models.json` only when preparing an isolated
child, parse it under a strict size bound, and project into the private agent directory a
`models.json` containing **only the exactly-selected provider's record**, and within that record only
credential-blind configuration.

This amendment permits **configuration** projection. It does not permit **credential** projection.
Credential projection remains governed solely by ADR-0016's `auth.json` clause and is not widened
here by one byte.

Permitted inside the projected provider record: `baseUrl`, `api`, `name`, `oauth`, `authHeader`,
`compat`, `models[]`, `modelOverrides`, and equivalent non-secret structural or protocol
configuration recognized by the pinned Pi provider schema. `apiKey` and `headers` values are
permitted **only** when the entire value is a pure environment-reference template (`$NAME` or
`${NAME}`). Such a value carries no secret: it resolves inside the child from the already-allowlisted
child environment. A `baseUrl` crosses as an endpoint only: a URL embedding userinfo
(`https://operator:pw@gateway/v1`) is credential material wearing an endpoint's clothes and is
refused, as is any `baseUrl` that is not a parseable absolute URL.

The projection fails closed — the child is not launched, and a fixed, bounded degraded failure is
returned — when the selected record contains a **literal** (non-template) `apiKey` or header value,
because that would be credential transport; when any projected value uses Pi's **`!command`** form,
which Pi executes as a shell command (`dist/core/resolve-config-value.js`) and which ADR-0016
reserves to the user; or when the record carries any key outside the reviewed Pi provider schema,
whose secrecy cannot be established. No provider record other than the exactly-selected one is
projected. Nothing beyond the provider record is projected: no `settings.json`, no `trust.json`, no
sessions, no package state, no other ambient home data. An absent `models.json`, or one that simply
does not configure the selected provider, is not a failure — the child proceeds on Pi's built-in
catalog exactly as the operator's own parent would.

The bounded degraded diagnostic is extended by one further fixed identifier drawn from a closed
allowlist chosen by the runner. It never contains credential material, a configuration value, or a
filesystem path, so it cannot reveal operator layout.

All other ADR-0016 and ADR-0014 controls remain in force: exact provider/model with no fallback,
private ephemeral child roots, restrictive creation, retained-handle credential scrubbing,
fail-degraded cleanup, disabled ambient discovery/approval/context/session loading, enforcement-only
child activation, bounded stdin and RPC, whole-process-tree cleanup, fail-closed unknown tools,
project-trust separation, and the live final-argument-ordering promotion gate.

## Alternatives considered
- **Accept the parity loss** — isolated children work only with Pi's built-in provider catalog, and
  the live fixture is rewritten to match. Rejected: it does not merely lose a feature, it silently
  redirects the operator's credential to an endpoint they never configured.
- **Project the operator's `models.json` verbatim** — rejected: it would transport literal `apiKey`
  and header secrets and Pi-executed `!command` values, which is precisely the credential transport
  ADR-0016 forbids and this amendment refuses to widen.
- **Ask Pi's own loaded model registry for the resolved provider** (`provider-composer.js` composes
  the built-in, `models.json`, and extension layers) so `ca-pi` never parses an operator config file
  at all — the cleanest boundary and the long-term target, but it requires a parent/child
  request-shape change well beyond this lane. Deferred, not rejected.
- **Bind a separate `models.json` environment override** — rejected: Pi 0.80.10 exposes none, so it
  would require an upstream change codeArbiter does not control.

## Consequences
Isolated children regain full operator endpoint, protocol, and model parity while `ca-pi` gains no
new credential-transport authority — the secret-bearing surface is exactly what ADR-0016 already
sanctioned. The sanitizer's key allowlist is pinned to the reviewed Pi provider schema, so a Pi
release that adds a provider key degrades children until that key is reviewed: a deliberate
fail-closed cost, paid the same way the pinned help-contract drift check is paid. Operators who
embed a literal API key or a `!command` directly in `models.json` cannot use isolated children until
that value moves behind an environment reference; that is the intended, visible boundary rather than
a silent downgrade.

## Risks
A future Pi release may move credential resolution into a field this sanitizer treats as structural,
or may rebind `models.json` again. The key allowlist can drift from Pi's schema in the lenient
direction if it is widened without review. This decision is proven wrong if credential-blindness
cannot be maintained — that is, if endpoint parity ever comes to require transporting a literal
secret — or if the fail-closed rejections prove frequent enough in real operator configurations that
they are routed around instead of fixed.
