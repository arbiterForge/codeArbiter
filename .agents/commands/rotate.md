# /rotate "artifact-id"

## Purpose

Rotate a single rotation-bearing artifact — signing key, OIDC client secret,
TLS certificate, API token, or service account credential — through the full
inventory → cadence → plan → audit-emit → archival lifecycle. No replacement
credential is issued and no audit event is emitted before every phase gate
clears. A rotation without an archival record is treated as credential loss.

## Usage

```
/rotate "artifact-id"
```

The `artifact-id` is the artifact's store reference as recorded in
`projectContext/secrets-policy.md` — never the credential value, never a
fingerprint of the value. Acceptable identifier forms:

- Signing key name (e.g., `jwt-signer-2025`)
- OIDC client ID (e.g., `oidc-client-partner-portal`)
- TLS certificate subject (e.g., `CN=api.example.internal`)
- Service-account ID (e.g., `sa-worker-ingest`)

## Routes To

`rotation` skill (`.agents/skills/rotation/SKILL.md`) — Phases 1 through 5:

1. **Inventory** — confirm the artifact has a recorded last-rotation timestamp.
2. **Cadence Check** — confirm the artifact is not past its cadence (or move
   it into the rotation plan if it is).
3. **Rotation Plan** — issuance path, dual-running window, consumer cutover,
   archival path, named approver.
4. **Audit Emit** — routes to the `audit-emit` skill for action classification,
   emit construction, sink routing, fail-closed check, and test obligation.
5. **Archival** — append the four-fact record (which / when / what / who) to
   the archival destination and update the last-rotation timestamp.

The `rotation` skill extends `secret-handling` (storage-path dimension) and
`crypto-compliance` (primitive dimension) with the lifecycle dimension. Phase
3 routes the proposed replacement primitive through `crypto-compliance`
before issuance. Phase 4 routes the rotation event through `audit-emit` in
full — Phase 4 cannot exit until `audit-emit` Phase 5 (Test Obligation) has
completed.

## Hard Gates (BLOCK conditions)

- **No last-rotation timestamp** — artifact has no recorded rotation history
  in `projectContext/secrets-policy.md`. Cadence cannot be audited; rotation
  cannot proceed until inventory is repaired or the artifact is marked for
  first-rotation flow.
- **Past cadence** — artifact age exceeds the applicable cadence from
  `secrets-policy.md` (or the documented default). The artifact MUST enter
  the rotation plan or be recorded as a `CONFIRM-NN` exception in
  `open-questions.md`; silent reconciliation is prohibited.
- **No archival path** — `secrets-policy.md` does not define an archival
  destination for this artifact category. The command stops and surfaces the
  gap — no archival path is invented at the command layer.
- **Missing audit-emit** — the `audit-emit` skill has not completed Phase 5
  (Test Obligation) for the rotation event, or the emit routes through any
  path other than the canonical sink in `projectContext/audit-spec.md`.
- **Missing archival record** — Phase 5 has not written the four-fact record,
  or the last-rotation timestamp has not been updated in the authoritative
  register. The rotation is NOT marked complete until both are present.

A `/rotate` invocation that hits any gate halts at the failing phase and
surfaces the specific block reason. The orchestrator does not retry past a
gate without the underlying condition being repaired.

## Orchestrator-Triggered Invocation

`/rotate` is user-invokable and also orchestrator-triggered:

- The `/checkpoint` command's reviewer pass MAY surface an aged artifact
  (`PAST-CADENCE` or `APPROACHING`). When it does, the orchestrator routes to
  this command with the artifact id supplied. The user-confirmation step is
  preserved — the orchestrator does not silently rotate.
- A scheduled cadence audit may also surface aged artifacts; the same routing
  applies.

In both auto-triggered paths, the same Phase 1–5 sequence and the same hard
gates apply. There is no "fast path" — auto-trigger only changes who supplied
the artifact id, not what gates fire.

## Example Invocations

```
/rotate "jwt-signer-2025"
/rotate "oidc-client-partner-portal"
/rotate "CN=api.example.internal"
/rotate "sa-worker-ingest"
/rotate "api-token-vendor-acme"
```

## When NOT to Use

- **Read-only secret consumption with no lifecycle change** — use the normal
  feature / fix path; that is `secret-handling` territory, not `rotation`.
- **Primitive selection or TLS configuration with no key replacement** — that
  is `crypto-compliance` territory; route via `/feature` or `/fix` instead.
- **Adding a new dependency or container image** — use `/add-dep`.
- **Discussion / questions about rotation policy** — use `/btw`.

## See Also

- `/add-dep` — vet a new third-party dependency through `dependency-reviewer`.
- `/checkpoint` — the orchestrator pass that may surface an aged artifact and
  auto-route to `/rotate`.
