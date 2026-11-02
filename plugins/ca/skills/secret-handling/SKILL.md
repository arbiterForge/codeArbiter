---
name: secret-handling
description: The secret-source gate. Routed to when changed code reads, writes, or passes a secret — API key, token, password, connection string, signing key, certificate, or any value that grants access. Validates that every secret comes from the approved store and never lands in source, log, test fixture, error response, image, or LLM prompt. The auth-crypto-reviewer agent is dispatched as the reviewer.
disable-model-invocation: true
---

# secret-handling

The secret-source gate. Routed to when changed code reads, writes, generates, stores, or passes a secret. If a value's secret status is uncertain, treat it as a secret.

## Pre-flight

Read these, or STOP and surface the gap — never guess the policy:

- The complete format-selected `security-controls` policy, read by `${CLAUDE_PLUGIN_ROOT}/includes/knowledge.md` ("Read security policy before a security decision") — the approved originating store, access method, runtime transport, exposure limits, and required reference format when one applies. If the required policy is absent or unreadable, BLOCK the affected flow; do not infer approval from scope blocks or a variable name.

## Phase 1 — Identify · gate: BLOCK

Scan the changed code for secret-bearing names: `password`, `secret`, `token`, `key`, `credential`, `api_key`, `apikey`, `private`, `cert`, `passphrase`. For each match, record its source (where the value originates) and every sink (where it flows). No candidate may remain unclassified.

Gate: every candidate secret is listed with its source and sinks.

## Phase 2 — Source · gate: BLOCK

For each secret, distinguish where it originates from how the owning process receives it. Compare both the source and access method with the complete `security-controls` policy. An environment variable may be the policy-approved source or a bounded runtime transport from an approved release store; reading `process.env` alone neither approves nor rejects the flow. The following sources BLOCK:

- A hardcoded credential, secret literal, or token-shaped dummy value in changed source or committed configuration. Non-secret fixture labels are not credentials; dummy credential values must still arrive through the policy-approved runtime source/transport.
- A committed secret-bearing `.env` file or any other committed secret-bearing configuration. `.env` files MUST be gitignored and secrets-scanned on every PR.
- A database column holding the raw value (a stored *reference* is allowed — see Phase 3).
- An environment or store endpoint not approved for that secret and access method by the active policy. An approved parent environment does not authorize passing the value to an unrelated child.

**Stakes:** a hardcoded or unapproved-source secret ships to every clone, every CI log, and the
history; rotation is the only fix once it lands. State that when you block, not just "unapproved
source." A genuine catch the user then rotates earns **exactly one** warm sentence at the close (per
the orchestrator register), never on a clean pass.

Gate: every secret's origin, access method and runtime transport are approved for that flow by the active policy. A missing, unreadable or genuinely contradictory policy blocks the affected flow with the precise unresolved point; independent work continues.

## Phase 3 — Sinks and persistence · gate: BLOCK

Trace each secret to all sinks. These are prohibited regardless of project, with no log-redaction excuse:

- Any logger call, at any level.
- Client-facing error messages or HTTP response bodies.
- Telemetry, metrics, tracing, span attributes.
- Any LLM prompt or agent context — treat the provider as out-of-boundary; verify shape with length, prefix, or hash, never the value.
- Serialized state, session storage, or JWT payload.
- A database column, except the store *reference* (path, ID, ARN) in the format `security-controls.md` requires. A migration adding a reference column without a format check constraint BLOCKs.

Keep each secret only for the lifetime and exposure boundary approved for its access method. A request-scoped secret ends with its request. Policy-approved owning-process runtime input may remain only for that bounded process/workflow lifetime; it is not permission for a module-level cache, unrelated child environment, serialized state, or longer-lived copy. Check the actual child argv and environment before treating an injection as approved.

Dispatch the `auth-crypto-reviewer` agent (`${CLAUDE_PLUGIN_ROOT}/agents/auth-crypto-reviewer.md`) to confirm these findings against `security-controls.md`.

Gate: no secret reaches a prohibited sink or persists beyond its policy-approved lifetime.

**On pass — record the gate:** follow `${CLAUDE_PLUGIN_ROOT}/includes/security-gate-record.md` (the shared record mechanism). For this gate the relevant commit hook is **H-10b** (secrets). On any BLOCK, do NOT record the pass.

**Out-of-scope finding:** do not act on it and do not author an ADR (ADRs are user-attributed, via `/adr` only). Mark it inline with `[NEEDS-TRIAGE]`; never silently drop it.

## Hard rules

- MUST read the complete format-selected `security-controls` policy for the approved store before Phase 2 — BLOCK if it cannot be read.
- MUST classify secret origin, access method, runtime transport, sinks and lifetime against the complete active policy; `process.env` alone is neither approval nor prohibition.
- MUST NOT source a secret from a hardcoded credential, committed secret-bearing file, or unapproved store or environment.
- MUST NOT let a secret reach a logger, error response, telemetry, LLM prompt, serialized state, or session/JWT payload.
- MUST NOT store a secret value in the database — store the approved-store reference only, with a format check constraint.
- MUST NOT let a secret persist beyond its policy-approved request or owning-process boundary, or pass to an unrelated child.
- MUST record the `security-gate-passed` marker (via `hooks/security-pass.py`) ONLY when the gate genuinely passes — the marker is what unblocks the commit (hook H-10b), so a premature or unconditional recording defeats the gate.
