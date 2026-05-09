# Logging, Telemetry & Audit

Three streams, separate sinks, separate retention. The agent MUST NOT mix them.

| Stream | Sink | Retention | Integrity |
|---|---|---|---|
| Application logs | stdout → Loki/CloudWatch | 30 d [S1], 90 d [S2], 1 y [S3+] | none required |
| Metrics | OpenTelemetry → Prometheus | 30 d [S1], 1 y [S3+] | none required |
| Audit events | Append-only sink (Z-AUDIT) | 1 y online + 6 y archive [S3+] | hash-chain [S3+], WORM [S4] |

Audit sink technology: see `[CONFIRM-05]` in `docs/open-questions.md`.

Schema standard: OCSF-aligned with ECS-compatible field naming.
Decision: `docs/decisions/0003-adopt-ocsf-audit-schema.md`.
Machine-readable schema (single source of truth): `schemas/audit-event.schema.json`.

---

## Canonical Field Reference

The JSON Schema in `schemas/audit-event.schema.json` is authoritative.
This table is a human-readable summary. When they conflict, the JSON Schema wins.

| Field | Type | Required | Constraint | Notes |
|---|---|---|---|---|
| `ts` | string (ISO-8601 UTC) | Always | ms precision | Example: `2026-05-04T14:32:01.123Z` |
| `event_id` | string (UUIDv7) | Always | uuid format | Monotonically increasing, time-ordered |
| `action` | string | Always | `verb.noun` pattern, max 64 | See action registry below |
| `actor.id` | string | Always | max 256 | OIDC `sub` claim |
| `actor.type` | enum | Always | `user\|service\|agent` | |
| `actor.session_id` | string | Optional | max 128 | OIDC session ID when available |
| `subject.type` | enum | Always | See enum below | Resource type acted on |
| `subject.id` | string | Always | max 256 | Stable resource identifier |
| `subject.name` | string | Optional | max 256 | Denormalized human-readable name |
| `outcome` | enum | Always | `success\|failure\|denied` | |
| `reason` | string | When outcome ≠ success | max 512 | MUST NOT contain secrets or PII |
| `source.request_id` | string | Always | max 128 | X-Request-ID correlation handle |
| `source.ip` | string | Optional | — | Caller IP as seen by Z-API |
| `source.user_agent` | string | Optional | max 512 | HTTP User-Agent |
| `classification` | enum | Always | `none\|cui\|secret_ref` | Data class of subject at event time |
| `git_sha` | string | See note | 40-char hex | Required for `deploy.*`, `signature.verify` |
| `environment` | enum | Optional [S1], Required [S2+] | See enum below | Enables multi-stage sink filtering |
| `class_uid` | integer | Optional [S1], Required [S2+] | OCSF class enum | Stable SIEM detection contract |
| `severity_id` | integer | Optional [S1], Required [S2+] | 1–5 | 1=Info 2=Low 3=Medium 4=High 5=Critical |
| `metadata.schema_version` | string (semver) | Always | `"1.0.0"` | Consumers reject on major mismatch |
| `metadata.product` | string | Always | `"fusion-core"` | Constant |
| `metadata.emit_version` | string | Optional | max 64 | Audit library version |

### subject.type enum

`solution` · `node` · `adapter` · `secret_ref` · `role` · `schema` · `key` · `config`

### environment enum

`prototype` · `internal-mvp` · `hardened-pilot` · `production`

---

## Action Registry

All `action` values MUST follow `verb.noun` pattern (`^[a-z][a-z0-9_]*\.[a-z][a-z0-9_]*$`).

| Action | class_uid | Default severity_id | git_sha required |
|---|---|---|---|
| `authn.success` | 3001 | 1 | No |
| `authn.failure` | 3001 | 3 | No |
| `authz.denied` | 3002 | 3 | No |
| `deploy.solution` | 6001 | 2 | Yes |
| `teardown.solution` | 6001 | 2 | Yes |
| `read.secret` | 6002 | 2 | No |
| `config.change` | 6003 | 2 | No |
| `role.change` | 6003 | 3 | No |
| `key.rotate` | 6003 | 2 | No |
| `schema.migrate` | 6004 | 2 | No |
| `signature.verify` | 6004 | 2 | Yes |

New actions MUST be added to this registry before use. Adding a new action is
not a breaking schema change (no major version bump required).

---

## Emit Interface Contract

Application code MUST call `audit.emit(event: AuditEvent)` exclusively.
Direct sink calls are prohibited. Rationale: AU-2, AU-9, AU-12.
Verification: Semgrep rule `no-audit-events-in-app-logger`.

The implementation behind `audit.emit()` is transport-agnostic:

| Stage | Implementation |
|---|---|
| S1 | Direct HTTP POST to configured sink endpoint |
| S2 | NATS JetStream persistent stream (preferred) |
| S3 | Kafka if deployment environment is already Kafka-native; else NATS |
| S4 | WORM-locked sink + hash-chain (see `[CONFIRM-05]`) |

Swapping transport at stage promotion requires only an implementation change
behind the interface — no caller changes, no schema changes.

---

## Rules

- Audit emit failure MUST cause the originating request to fail closed at [S3+].
  Rationale: AU-5. Verification: `tests/security/test_audit_fail_closed.py`.
- `reason` MUST NOT contain secrets, tokens, passwords, or PII. The backend
  validator enforces this at emit time via a blocklist scan.
- Events that fail JSON Schema validation MUST be rejected at emit time with a
  `500` response and an application log entry (not an audit event — avoid loops).
- The TypeScript `AuditEvent` type in the frontend MUST be derived from
  `schemas/audit-event.schema.json`, never defined independently.

---

## Auditable Event Minimum Set (AU-2)

authn success/failure · authz denial · secret read · deployment start/end ·
teardown · schema migration · config change · role change · signature verification
result · key rotation
