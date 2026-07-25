---
status: accepted
date: 2026-07-25
title: Accept endpoints by bounded structure rather than case, and pin projected value shapes
decided-by: SUaDtL@users.noreply.github.com
supersedes: 0017
governs: .codearbiter/security-controls.md, plugins/ca-pi/tools/src/child-env.ts, plugins/ca-pi/**
---

# ADR-0018 — Accept endpoints by bounded structure rather than case, and pin projected value shapes

## Status
Accepted — explicitly approved by SUaDtL@users.noreply.github.com on 2026-07-25.

Partial supersession of ADR-0017. This ADR amends three clauses of ADR-0017 — its `baseUrl`
acceptance rule, its fail-closed list, and its Consequences paragraph — and nothing else. Every
other word of ADR-0017 remains in force, including the whole credential-blindness contract, and
ADR-0016's `auth.json` credential-projection contract is untouched by both. ADR-0017's file is not
edited; supersession is forward-only.

## Context
ADR-0017 was ratified before its implementation was adversarially probed. Two reviews of the
shipped code found the prose incomplete in one direction and the code over-strict in another.

**The endpoint rule was incomplete and the first implementation of it leaked.** ADR-0017 said only
that a `baseUrl` embedding userinfo is refused. An adversarial probe proved that a credential in a
query string, path, or fragment projected verbatim into the child — and that is the *dominant*
real-world shape (Azure uses `?api-key=`, Google uses `?key=`), so the rule as written closed the
rare case and left the common one open. It also proved the projected value was invisible to the two
controls that assume the projection holds no secret: it was absent from the child's sensitive-value
scrub set, so echo-suppression would not have caught a child repeating it.

**The corrective rule then over-corrected.** The remediation added a lowercase-only constraint on
route segments. Measurement showed that constraint was not a credential control at all:
`sk-querysecret999` (17 bytes, lowercase) satisfies it, while `GPT4-Prod` — an ordinary
operator-chosen Azure deployment name — does not. The bound that actually refuses realistic key
material is the per-segment byte limit; provider keys run well past 32 bytes. So the case rule cost
an operator their isolated children entirely while buying no protection.

**Key names alone proved not to be a pin.** ADR-0017's fail-closed list named keys outside the
reviewed Pi provider schema. But Pi types the *values* too (`oauth` is `Type.Literal("radius")`,
`authHeader` is `Type.Boolean()`), so a record satisfying the name allowlist but not the declared
type projected successfully and then died mutely inside Pi's own `validateModelsConfig` — a silent
child death instead of the intended fail-closed refusal.

## Decision
Accept a projected `baseUrl` by **bounded structure, not by character case**, and pin projected
**value shapes** as well as key names.

A `baseUrl` crosses only when it is a parseable absolute `http`/`https` URL with **no userinfo, no
query, and no fragment at all**, no percent-encoding, and a route of at most 8 segments of at most
32 bytes each, every segment matching `^[A-Za-z0-9]+(?:[._-][A-Za-z0-9]+)*$`. Query and fragment are
refused outright because a provider endpoint needs neither — Pi's own Azure provider carries
`api-version` in `AZURE_OPENAI_API_VERSION`, not in `baseUrl`. Acceptance is positive rather than a
blocklist of credential-bearing parameter names, which is an unbounded list.

Route segments are deliberately **case-insensitive**. A short path segment cannot be distinguished
from a legitimate route, so the controls that bind are the ones that do not require guessing intent:
no userinfo, no query, no fragment, no percent-encoding, a bounded segment length, and a bounded
segment count.

Whatever is accepted is **also registered in the child's sensitive-value scrub set** and retained
behind a scrub handle, so an endpoint that is bounded-but-not-provably-credential-free is not
invisible to the controls that depend on it.

The fail-closed list extends from keys to **keys and value shapes**: a record satisfying the name
allowlist but not the declared Pi type refuses instead of projecting. Where Pi's own schema leaves
an interior open-ended (`compat.chatTemplateKwargs`, `openRouterRouting`, `vercelGatewayRouting`),
the member name is pinned and the interior keeps the bounded structural check — depth, node, key and
byte caps, reserved keys rejected, every `!command` form refused.

## Alternatives considered
- **Keep the lowercase-only route rule** — rejected on measurement: it refuses `GPT4-Prod` while
  admitting `sk-querysecret999`, so it imposes a real operator cost for no security gain.
- **Blocklist credential-bearing query parameter names** (`api-key`, `key`, `token`, `sig`, …) —
  rejected: an unbounded list, and each omission is a silent leak. Refusing query and fragment
  outright is bounded and complete.
- **Relax case AND tighten the segment bound to ~24 bytes** — considered; rejected as unnecessary
  tightening that would refuse more legitimate endpoints without a demonstrated threat, since 32
  bytes already refuses realistic key material.
- **Pin only key names, as ADR-0017 did** — rejected: it converts a fail-closed refusal into a mute
  child death inside Pi's validator, which is strictly worse to diagnose.

## Consequences
Operators with a mixed-case Azure deployment or Cloudflare AI Gateway name keep isolated children,
which ADR-0017's implementation had taken from them. Operators whose `baseUrl` carries a query
string, a fragment, percent-encoding, a non-`http(s)` scheme, or a route exceeding the segment
bounds lose isolated children until they reconfigure — intentional and loud, failing closed with the
fixed `isolation-config` stage identifier, never a silent drop, but a real behavioural narrowing
relative to what Pi itself accepts.

The value-shape pin makes an unreviewed Pi schema addition degrade children until it is reviewed —
the same deliberate fail-closed cost the pinned help-contract drift check already pays.

Residual, recorded rather than fixed: the scrub-set registration covers **endpoints**. Other
projected free-string leaves — `provider.name`, `provider.api`, `models[].id`, `thinkingLevelMap`
keys, and the open-ended `compat` interiors — cross verbatim and are **not** in the scrub set, so a
child echoing one into its final assistant message would not be suppressed. None carries a
real-world credential convention, and the disk half is covered regardless because the scrub handle
truncates the whole projected document.

## Risks
A future Pi release may introduce a provider whose legitimate endpoint requires a query parameter,
or a deployment naming scheme that exceeds the segment bounds; either would make the fail-closed
refusals frequent enough to be routed around instead of fixed. The byte bound is a heuristic, not a
proof: a short high-entropy path segment is still accepted, which is why registration in the scrub
set — not the acceptance rule alone — carries the residual. This decision is proven wrong if
operators begin widening the bounds to make ordinary configurations work, or if a credential is
shown to cross in a projected field that is neither an endpoint nor scrub-registered.
