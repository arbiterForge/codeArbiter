---
status: accepted
date: 2026-07-25
title: Broker Pi child inference instead of projecting a credential into the child
decided-by: SUaDtL@users.noreply.github.com
supersedes: 0016
governs: .codearbiter/security-controls.md, plugins/ca-pi/tools/src/inference-broker.ts, plugins/ca-pi/tools/src/child-env.ts, plugins/ca-pi/**
---

# ADR-0019 — Broker Pi child inference instead of projecting a credential into the child

## Status
Accepted — explicitly decided by SUaDtL@users.noreply.github.com on 2026-07-25, and authoring
explicitly approved by the maintainer on the same date.

Partial supersession of ADR-0016. This ADR supersedes ADR-0016's **credential-projection clause**
and nothing else; ADR-0016's private-child-root, scrubbing, and fail-closed-cleanup contracts remain
in force, and ADR-0017's configuration-projection clause and ADR-0018's endpoint-acceptance and
value-shape rules are unaffected except that the projected `apiKey` is now a broker token rather
than an environment reference to an operator credential. ADR-0016's file is not edited;
supersession is forward-only.

## Context
ADR-0016 permitted `ca-pi` to project the operator's selected-provider `auth.json` record into an
isolated child's private agent directory. That placed a **reusable, exfiltratable credential inside
a process running model-authored code**. The child holds ordinary `bash`, `read`, `edit` and `write`
tools, and `cat`/`Get-Content` is on the inspection allowlist, so a prompt-injected child could read
the credential it was given and encode it — Base64, hex, splitting — into its final assistant
message. Exact-value result matching cannot distinguish that from ordinary output, and the class of
encoding transforms is unbounded, so no blacklist closes it.

The residual was initially bounded by one control: a governed child has no network egress. Its tool
set is exactly `{bash, read, edit, write}`, network commands are classified and gated, and the
inspection allowlist excludes shell metacharacters so chaining is blocked. That control is a
property of the current tool set, not a guarantee. With network-capable tools (WebFetch and
similar) on the roadmap, the residual would silently change from "credential surfaces in the
operator's own transcript" to "credential surfaces at an attacker-chosen endpoint", and nothing
would force a revisit. Accepting a residual whose compensating control a future feature removes is
how a documented risk becomes a breach.

## Decision
The child receives **no provider credential in any form**.

The parent binds a per-child loopback broker on `127.0.0.1:0`, projects a provider configuration
whose `baseUrl` names that listener and whose `apiKey` references a per-child ephemeral token, and
exchanges that token for the real credential on the way upstream. The `auth.json` projection is
**deleted, not disabled**; its reintroduction fails a test.

Providers a bearer-substituting broker cannot serve — `amazon-bedrock` and `google-vertex`
(per-request SDK signing), `github-copilot` and `openai-codex` (OAuth refresh inside the child's
Pi), any record carrying `oauth`, and any provider with neither an operator `baseUrl` nor a pinned
built-in endpoint — **fail the launch closed** rather than falling back to a credential in the
child. Parent and child requests name an exact provider and model; silent fallback stays prohibited.

Request headers cross by allowlist, not denylist. Response headers and body are filtered against
the child's sensitive-value set before delivery, with `identity` encoding forced so compression
cannot blind the filter. The per-child broker is closed in the same `try`/`finally` that guarantees
isolation-root cleanup, so neither a stranded root nor a surviving listener can outlive the child.

## Alternatives considered
- **Narrow the threat contract and document the residual** — rejected: its safety rested entirely on
  the absence of network egress, a property a roadmapped feature would silently remove.
- **Fail stored-auth child launches closed** — rejected: it sacrifices the stored-auth parity
  ADR-0016 was created to preserve, and provider environment variables would remain readable by the
  child's own `bash` regardless.
- **Tunnel inference over the existing bounded JSONL bridge**, so nothing binds a port — strictly
  tighter and deliberately deferred: Pi expects an HTTP endpoint, so a shim is needed anyway, and it
  would mean reimplementing streaming, tool-call and SSE semantics per provider. Named as the
  successor if same-user socket exposure ever becomes a live concern.
- **Detect encoded credentials in child output** — rejected on principle: the transform class is
  unbounded, and a detector that can be defeated by `base64` teaches false confidence.

## Consequences
`cat auth.json` in a compromised child yields a token that dies with the child and is worthless
off-host, so the entire encoding-transform class is retired rather than one instance of it. #414 and
#415 are closed by this decision — there is no projected credential file left to harden.

Operators on the unsupported providers above lose isolated children until a mechanism exists for
them; that is intentional and loud, failing closed rather than silently degrading to a credential in
the child.

## Risks
**Primary residual, stated as the corrected claim rather than the original one.** A listening
loopback socket is reachable by any process running as the same OS user, and the token is the only
thing in front of it. The token is worthless **off-host** — the listener binds `127.0.0.1` only. It
is **not** worthless to a second process: the token binds to the minting *broker*, not to a process,
the handler compares the token and nothing else, and no peer, pid, or connection binding is
available over a loopback socket. An adversarial probe drove a genuinely separate same-user process,
holding only the token, to HTTP 200 with the operator's real credential forwarded upstream.

The accepted residual is therefore: **any same-user process that obtains the token can *use* the
operator's credential — use, not read — for as long as the owning child lives, replaying it freely
within that window.** The token is deliberately not single-use. This is accepted because a process
running as the operator can already read the operator's credential store directly, so brokering adds
no exposure such an attacker did not already have, and it is strictly narrower than the projected
credential file it replaces, which handed that same process the raw exfiltratable key. The gain is
use instead of disclosure, bounded by the child's lifetime and by the host.

**Second residual.** Clean response bytes are forwarded eagerly, because holding a window back
deadlocks incremental streaming. A sensitive value split across chunk boundaries therefore has its
leading fragment already delivered when the following chunk completes the match. The complete value
is never delivered, and the stream is left truncated rather than terminated.

This decision is proven wrong if the threat model expands beyond same-user trust, if a supported
provider requires the broker to relay headers or response bytes it cannot inspect, or if the
per-child listener proves to be a materially wider surface than the credential file it replaced.
