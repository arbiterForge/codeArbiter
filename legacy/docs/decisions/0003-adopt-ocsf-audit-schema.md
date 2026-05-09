# ADR 0003 — Adopt OCSF-Aligned Audit Event Schema with Abstract Emit Interface

**Status:** Accepted  
**Date:** 2026-05-04  
**Author:** Brennon Huff  
**Stage scope:** S1+  
**Tradeoff level:** 3 — Maintainability & Reviewability  

---

## Context

FUSION's `docs/audit-spec.md` defines required audit event fields for Z-AUDIT but
did not specify a formal schema standard, a schema version contract, or the
transport layer between producers and the audit sink. As the Audit Log UI and
backend `audit.emit()` interface were about to be built, three decisions needed
to be made together:

1. Which industry schema standard to align to
2. What fields to add, constrain, or type beyond the initial spec
3. Whether to couple producers directly to the sink or introduce a bus

Evaluated options: OCSF, Elastic Common Schema (ECS), roll-our-own.

---

## Decision

### 1. Schema standard: OCSF-aligned, ECS-named where they overlap

Adopt the **Open Cybersecurity Schema Framework (OCSF)** structural skeleton:
`metadata` block (version, product, schema_version), `class_uid`, `category_uid`,
`severity_id`, and the `activity_id` enum pattern.

Retain the existing FUSION field names (`actor.*`, `subject.*`, `action`,
`outcome`, `source.*`, `classification`, `git_sha`) because they already follow
ECS dot-notation conventions and are referenced throughout the codebase and UI.
Where OCSF and ECS name the same concept differently, prefer ECS naming for
readability; the OCSF `class_uid` provides machine-stable identity regardless.

This gives FUSION:
- An open, vendor-neutral standard for ATO documentation (no Elastic dependency)
- A stable `class_uid` contract that SIEM detection rules can pin to
- JSON Schema validation (`schemas/audit-event.schema.json`) without writing
  a custom validator
- A clear upgrade path: OCSF has a published NIST 800-53 control mapping that
  the ATO package can reference directly

### 2. Abstract emit interface — transport is swappable

`audit.emit(event: AuditEvent)` is the only call site in application code.
The implementation behind it is hidden behind an interface:

```
S1 (Prototype):   direct HTTP POST to sink (CloudWatch or Postgres table)
S2 (Internal MVP): NATS JetStream persistent stream  [preferred]
S3 (Hardened):    Kafka (Confluent or AWS MSK)        [if S3 env is Kafka-native]
S4 (ATO-Ready):   WORM-locked sink + hash-chain        [CONFIRM-05]
```

Kafka was evaluated and rejected for Stage 1-2 on SMART grounds:
- **Maintainability**: single-binary NATS JetStream has equivalent delivery
  guarantees with far lower operational surface on K3s
- **Reliability**: a single-broker Kafka setup has no HA advantage over a
  persistent NATS stream; a cluster adds Stage 1 out-of-scope complexity
- **Testability**: NATS JetStream has first-class Testcontainers support;
  Kafka adds JVM overhead to the test environment

Kafka remains the Stage 3+ option if the deployment environment is already
Confluent- or MSK-native (avoid running two event buses).

### 3. Schema versioning

`metadata.schema_version` is required (`"1.0.0"` at launch). Consumers MUST
reject events where `schema_version` major version does not match their compiled
expectation. Breaking field changes increment the major version and require a
new ADR entry.

---

## SMART Assessment

| Dimension | Assessment |
|---|---|
| **Scalability** | OCSF `class_uid` system scales to hundreds of event types without schema drift; the emit interface scales to high-throughput sinks without caller changes |
| **Maintainability** | Community-maintained standard; schema changes tracked via ADR; JSON Schema in `schemas/` is the single source of truth for backend, frontend, and tests |
| **Availability** | Schema lives in code/docs — zero runtime dependency; sink swap requires only implementation change behind the interface |
| **Reliability** | `class_uid` + required-field validation at emit time means malformed events are rejected before they reach the sink, not after |
| **Testability** | `schemas/audit-event.schema.json` enables `jsonschema.validate()` assertions in a single line; every audit test can assert schema conformance, not just field presence |

---

## NIST 800-53 Rev. 5 Control Mapping

| Control | How this ADR serves it |
|---|---|
| AU-2 | Auditable event minimum set defined in `audit-spec.md`; `class_uid` maps each event type |
| AU-3 | All required fields (who, what, when, where, outcome) enforced by JSON Schema |
| AU-5 | Emit failure = request fails closed at S3+ (interface contract, not sink contract) |
| AU-9 | Append-only sink; WORM at S4; hash-chain at S3+ |
| AU-12 | Every auditable action calls `audit.emit()` — Semgrep rule enforces no bypass |
| SC-28 | Classification field on every event; sink encryption is a separate transport concern |

---

## Consequences

- `schemas/audit-event.schema.json` is now a protected file — changes require
  an ADR entry and a major version bump if breaking.
- `docs/audit-spec.md` is updated to reference this schema as authoritative.
- `backend/audit/events.py` (when written) MUST validate against the JSON Schema
  before emitting. Test: `tests/test_audit_schema.py`.
- The Audit Log UI reads events that conform to this schema; the frontend
  `AuditEvent` TypeScript type MUST be derived from it (source of truth flows
  one direction: schema → types, never types → schema).
- `CONFIRM-05` (sink technology) remains open; this ADR is deliberately
  sink-agnostic to avoid blocking on that answer.

---

## References

- OCSF specification: https://schema.ocsf.io
- OCSF → NIST 800-53 mapping: OCSF GitHub `mappings/` directory
- Elastic Common Schema field reference: https://www.elastic.co/guide/en/ecs/
- NATS JetStream docs: https://docs.nats.io/nats-concepts/jetstream
- Supersedes: nothing (first audit schema decision)
- See also: `docs/audit-spec.md`, `schemas/audit-event.schema.json`
