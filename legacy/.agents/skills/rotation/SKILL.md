---
name: rotation
---

<!--
Copyright (c) 2026 suadtl
Author: suadtl
Created: 2026-05-12
File: SKILL.md
-->


# Skill: rotation

## Purpose

Enforce the lifecycle dimension of secret and key material — inventory, cadence,
controlled cutover, audit emission, and archival. Where `secret-handling` gates
storage paths and `crypto-compliance` gates primitives, `rotation` gates the
clock: every rotation-bearing artifact has a recorded last-rotation timestamp,
is within its cadence, and produces an auditable archival record when replaced.

A rotation event without an audit trail is indistinguishable from a key
compromise. This skill exists to make that distinction provable.

---

## Trigger

This section lists conditions under which the orchestrator routes work to this
skill. The skill itself does not "trigger" — it is routed to.

Routed when:

- A signing key, OIDC client secret, API token, TLS certificate, or service
  account credential is added, renewed, replaced, or revoked.
- A change touches the issuance path of any rotation-bearing artifact (new
  issuer, new key store binding, new dual-running window).
- A scheduled rotation review fires (cadence audit against
  `${PROJECT_ROOT}/.agents/projectContext/secrets-policy.md`).
- A subagent or skill detects an artifact with no recorded last-rotation
  timestamp.
- The routing table references this skill (lifecycle dimension of any
  `secret-handling` or `crypto-compliance` finding).

Not routed for:

- Read-only secret consumption with no lifecycle change — that is
  `secret-handling`.
- Primitive selection or TLS configuration with no key replacement — that is
  `crypto-compliance`.

---

## Pre-Flight

Before Phase 1 begins, confirm:

1. `${PROJECT_ROOT}/.agents/projectContext/secrets-policy.md` is readable. This file is the
   authoritative source for the project's rotation-bearing artifact list,
   cadence values, issuance paths, and archival location. Stop if missing.
2. `${PROJECT_ROOT}/.agents/projectContext/security-controls.md` is readable. This file
   provides the approved key store, approved primitives, and any compliance
   mode (FIPS, internal CA) constraints that govern rotation issuance. Stop
   if missing.
3. `${PROJECT_ROOT}/.agents/projectContext/audit-spec.md` is readable. Rotation MUST emit an
   audit event; the action string and required fields come from this file.
   Stop if missing.
4. Current stage is known — `cat ${PROJECT_ROOT}/.agents/projectContext/stage`.

If any file is missing, surface the gap and stop. Do not guess at cadence
defaults, store references, or audit action strings without confirming the
file is genuinely absent and recording that fact.

---

## Phase 1 — Inventory

**Goal:** Enumerate every rotation-bearing artifact in scope and confirm each
has a recorded last-rotation timestamp.

**Inputs:**
- The set of artifacts touched or implied by the change.
- `${PROJECT_ROOT}/.agents/projectContext/secrets-policy.md` — authoritative artifact list and
  recorded last-rotation timestamps per artifact.
- `${PROJECT_ROOT}/.agents/projectContext/security-controls.md` — approved key store reference
  format (used to identify artifacts by reference, not value).

**Actions:**

1. Read `${PROJECT_ROOT}/.agents/projectContext/secrets-policy.md` in full. Extract the project's
   authoritative list of rotation-bearing artifacts. The default categories
   that MUST be considered if the file does not narrow the list:
   - Signing keys (JWT signers, request signers, code signers)
   - OIDC client secrets (every relying party / IdP integration)
   - API tokens issued to or held by this service
   - TLS certificates (public-facing and internal)
   - Service account credentials (workload identity bindings, machine accounts)
2. For each artifact in scope, record:
   - Artifact identifier (reference format per `${PROJECT_ROOT}/.agents/projectContext/security-controls.md` — never
     the value).
   - Artifact category.
   - Last-rotation timestamp (ISO 8601, from `${PROJECT_ROOT}/.agents/projectContext/secrets-policy.md` or the
     approved key store).
   - Issuance path (where the next replacement comes from).
3. If `${PROJECT_ROOT}/.agents/projectContext/secrets-policy.md` does not record a last-rotation timestamp for an
   artifact in scope, mark that artifact `UNROTATED-UNKNOWN`. This is a BLOCK
   condition — an artifact with no recorded rotation history cannot be audited
   for cadence compliance.
4. Do not include the secret value, key material, or any string that would
   identify the value itself. Reference only.

**Output:** Artifact inventory table with identifier (reference), category,
last-rotation timestamp, and issuance path for every artifact in scope.

**Gate:** BLOCK if any artifact in scope has no recorded last-rotation
timestamp. BLOCK if the inventory contains any raw key material or secret
value rather than store references. No Phase 2 until every artifact is
identified by reference and has a timestamp.

---

## Phase 2 — Cadence Check

**Goal:** Compute each artifact's age against the project rotation cadence and
flag every artifact past its cadence as a BLOCK.

**Inputs:**
- Inventory from Phase 1.
- `${PROJECT_ROOT}/.agents/projectContext/secrets-policy.md` — project-specific cadence values
  per artifact category.

**Actions:**

1. Read cadence values from `${PROJECT_ROOT}/.agents/projectContext/secrets-policy.md`. If the file
   specifies a cadence per category, use that. If the file is silent on a
   category, apply the defaults below:

   | Category | Default Maximum Age |
   |---|---|
   | Signing keys | 1 year |
   | OIDC client secrets | 6 months |
   | TLS certificates | 90 days |
   | API tokens | per `${PROJECT_ROOT}/.agents/projectContext/secrets-policy.md`; if silent, treat as signing-key cadence (1 year) |
   | Service account credentials | per `${PROJECT_ROOT}/.agents/projectContext/secrets-policy.md`; if silent, treat as signing-key cadence (1 year) |

2. For each artifact, compute age = (today − last-rotation timestamp).
3. Compare age to the applicable cadence. Mark each artifact:
   - `WITHIN-CADENCE` — age < cadence.
   - `APPROACHING` — age ≥ 0.8 × cadence and < cadence (informational; not a
     block, but surfaced).
   - `PAST-CADENCE` — age ≥ cadence (BLOCK).
4. If the project applies stage-dependent cadence (e.g., tighter cadence at
   Stage 3+), apply the stage-appropriate value read from
   `${PROJECT_ROOT}/.agents/projectContext/secrets-policy.md`.
5. Do not silently reconcile a cadence ambiguity. If `${PROJECT_ROOT}/.agents/projectContext/secrets-policy.md` is
   silent on a category AND a default would not clearly apply, invoke
   `/surface-conflict` and stop.

**Output:** Cadence report — every artifact tagged `WITHIN-CADENCE`,
`APPROACHING`, or `PAST-CADENCE`, with the applicable cadence cited.

**Gate:** BLOCK on any artifact tagged `PAST-CADENCE`. No Phase 3 until every
`PAST-CADENCE` artifact either enters the rotation plan in Phase 3 or has a
documented exception in `${PROJECT_ROOT}/.agents/projectContext/open-questions.md` with a CONFIRM
placeholder.

---

## Phase 3 — Rotation Plan

**Goal:** For each artifact requiring rotation, produce a concrete plan with
issuance, dual-running, cutover, and archival paths defined before any
rotation begins.

**Inputs:**
- Artifacts tagged `PAST-CADENCE` or otherwise scheduled for rotation.
- `${PROJECT_ROOT}/.agents/projectContext/secrets-policy.md` — issuance paths, dual-running
  policy, archival location.
- `${PROJECT_ROOT}/.agents/projectContext/security-controls.md` — approved key store and
  primitive constraints for new credential issuance.

**Actions:**

1. For each artifact to rotate, write a plan with all four sections:

   - **New-credential issuance path** — the exact store and procedure that
     produces the replacement credential. Must reference the approved key
     store from `${PROJECT_ROOT}/.agents/projectContext/security-controls.md`. Primitive (algorithm, key size, curve)
     must satisfy `crypto-compliance` — do not propose a primitive without
     routing the primitive choice through the `crypto-compliance` skill.
   - **Dual-running window** — start time, end time, and the policy for
     accepting both old and new credentials during the window. Must be long
     enough for every consumer to cut over and short enough to bound exposure
     if the old credential is compromised. If `${PROJECT_ROOT}/.agents/projectContext/secrets-policy.md` specifies a
     window, use that; otherwise propose one and surface it for confirmation.
   - **Consumer cutover plan** — the list of consumers that hold or verify
     this credential, the order they cut over in, and how cutover is
     confirmed (health check, signed probe, manual verification). Every
     consumer must be enumerated; an unenumerated consumer is a silent
     dependency and a future incident.
   - **Archival path** — the destination where the old credential's record
     (not its value) is written when the rotation completes. Must match the
     archival location specified in `${PROJECT_ROOT}/.agents/projectContext/secrets-policy.md`. If no archival path
     is defined for this category, surface and stop — do not invent one.

2. The plan MUST identify the approver. Rotation without a named human
   approver is a BLOCK condition for any artifact at Stage 3+.

3. The plan MUST NOT propose deleting the old credential's record. Deletion
   prevents post-incident audit. Archival is the only acceptable disposition
   for the old record.

**Output:** A rotation plan per artifact with all four sections filled and an
approver named.

**Gate:** BLOCK if any rotation plan is missing the archival step — a rotation
with no archival cannot be audited and is treated as credential loss. BLOCK if
no approver is named at Stage 3+. BLOCK if the proposed primitive has not
been validated through `crypto-compliance`. BLOCK if the issuance path does
not use the approved key store from `${PROJECT_ROOT}/.agents/projectContext/security-controls.md`.

---

## Phase 4 — Audit Emit

**Goal:** Confirm each rotation emits a correctly constructed audit event
through the canonical audit sink, routed via the `audit-emit` skill.

**Inputs:**
- Rotation plans from Phase 3.
- `${PROJECT_ROOT}/.agents/projectContext/audit-spec.md` — action naming convention, required
  fields, canonical sink.
- The `audit-emit` skill — primary handler for the emit construction, sink
  routing, fail-closed, and test obligation phases.

**Actions:**

1. For each rotation, classify the action string per
   `${PROJECT_ROOT}/.agents/projectContext/audit-spec.md`. The default action is `key.rotate`; if the
   project's spec defines a different convention (for example
   `credential.rotate`, `cert.rotate`, or `secret.rotate` for distinct
   categories), use the spec's strings. Do not invent an action name.
2. Route to the `audit-emit` skill and run it end-to-end against the rotation
   event:
   - Phase 1 (Action Classification) — confirm the action is registered.
   - Phase 2 (Emit Construction) — populate required fields, including
     `subject.id` as the new-credential store reference (never the value),
     `actor.id` as the approver named in Phase 3, and `outcome` recording
     success or failure.
   - Phase 3 (Sink Routing) — confirm emit goes through the canonical audit
     module.
   - Phase 4 (Fail-Closed Check) — confirm error handling matches stage
     policy.
   - Phase 5 (Test Obligation) — confirm a test asserts the emit on
     rotation.
3. The emit payload MUST reference both the retired credential (by reference)
   and the replacement credential (by reference). Without both, the audit
   record cannot be replayed to verify the rotation chain.
4. MUST NOT emit through a general-purpose logger or a side channel. The
   canonical audit sink is the only acceptable path.

**Output:** A `key.rotate` (or project-defined equivalent) audit event
constructed, routed, fail-closed-validated, and test-covered through the
`audit-emit` skill.

**Gate:** BLOCK if the `audit-emit` skill's Phase 5 (Test Obligation) is
incomplete for the rotation event. BLOCK if the action name is unregistered.
BLOCK if the emit routes through any path other than the canonical sink
defined in `${PROJECT_ROOT}/.agents/projectContext/audit-spec.md`.

---

## Phase 5 — Archival

**Goal:** Write the archival record for every completed rotation, capturing
the four facts that allow a future auditor to reconstruct the rotation chain.

**Inputs:**
- Completed rotation event(s) from Phase 4.
- `${PROJECT_ROOT}/.agents/projectContext/secrets-policy.md` — archival destination and
  record format.

**Actions:**

1. For each rotation, write an archival record containing:
   - **Which credential was rotated** — the retired credential's store
     reference. Never the value. Never a fingerprint that would reveal the
     value.
   - **When it was rotated** — ISO 8601 timestamp, matching the timestamp in
     the audit event from Phase 4.
   - **What replaced it** — the replacement credential's store reference.
   - **Who approved** — the named human approver from Phase 3.
2. Write the record to the archival destination specified in
   `${PROJECT_ROOT}/.agents/projectContext/secrets-policy.md`. If the destination is append-only,
   confirm append-only semantics (no edit or delete) before writing. If the
   destination is missing, surface and stop — do not improvise.
3. Update `${PROJECT_ROOT}/.agents/projectContext/secrets-policy.md` (or the project's authoritative timestamp
   register) to record the new last-rotation timestamp for the artifact. This
   feeds Phase 1 of the next rotation cycle. An unupdated register makes the
   next cadence check fire incorrectly.
4. MUST NOT delete the retired credential's archival record. MUST NOT
   overwrite a prior archival record. Each rotation appends; nothing is
   removed.

**Output:** Archival record written to the project's archival destination
with all four facts present. Last-rotation timestamp updated in the project's
authoritative register.

**Gate:** BLOCK if the archival record is missing any of the four facts
(which / when / what / who). BLOCK if the last-rotation timestamp in
`${PROJECT_ROOT}/.agents/projectContext/secrets-policy.md` (or equivalent register) has not been updated. BLOCK if
the archival destination cannot be confirmed append-only when policy requires
it.

---

## Hard Rules

- MUST read `${PROJECT_ROOT}/.agents/projectContext/secrets-policy.md` and
  `${PROJECT_ROOT}/.agents/projectContext/security-controls.md` before Phase 1. BLOCK if either file
  is missing.
- MUST NOT proceed with a rotation against an artifact that has no recorded
  last-rotation timestamp. Inventory is a precondition, not an outcome.
- MUST NOT use cadence defaults without first checking whether
  `${PROJECT_ROOT}/.agents/projectContext/secrets-policy.md` defines project-specific cadence values.
- MUST NOT propose a rotation primitive without routing the primitive through
  the `crypto-compliance` skill.
- MUST NOT issue a replacement credential through any store other than the
  one approved in `${PROJECT_ROOT}/.agents/projectContext/security-controls.md`.
- MUST NOT skip the dual-running window for a credential with multiple
  consumers. A hard cutover without dual-running guarantees an outage and
  hides cutover bugs.
- MUST NOT delete the retired credential's archival record. MUST NOT
  overwrite a prior archival record.
- MUST NOT emit the rotation event through any path other than the canonical
  audit sink defined in `${PROJECT_ROOT}/.agents/projectContext/audit-spec.md`.
- MUST NOT include the credential value, key material, or any reversible
  derivation in the audit event or archival record. Store references only.
- MUST NOT mark a rotation complete until Phase 5 has written the archival
  record AND updated the last-rotation timestamp.
- MUST NOT resolve a cadence or archival ambiguity by guessing. Invoke
  `/surface-conflict` and stop.

---

## Decision Gates Summary

| Gate | Condition | Action if blocked |
|---|---|---|
| Phase 1 exit | Any artifact in scope has no recorded last-rotation timestamp | Record timestamp in `${PROJECT_ROOT}/.agents/projectContext/secrets-policy.md` or mark artifact for first-rotation flow before proceeding |
| Phase 1 exit | Inventory contains raw key material rather than store references | Replace with store references; never log or persist values |
| Phase 2 exit | Any artifact tagged `PAST-CADENCE` | Move artifact into Phase 3 rotation plan or open a CONFIRM in `${PROJECT_ROOT}/.agents/projectContext/open-questions.md` |
| Phase 2 exit | Cadence ambiguity not resolvable from `${PROJECT_ROOT}/.agents/projectContext/secrets-policy.md` | Invoke `/surface-conflict`; do not apply defaults silently |
| Phase 3 exit | Rotation plan missing archival step | Add archival path from `${PROJECT_ROOT}/.agents/projectContext/secrets-policy.md`; do not invent one |
| Phase 3 exit | No named approver at Stage 3+ | Name an approver; rotation cannot proceed |
| Phase 3 exit | Proposed primitive not validated through `crypto-compliance` | Route primitive through `crypto-compliance` first |
| Phase 4 exit | `audit-emit` Phase 5 (Test Obligation) incomplete | Complete test coverage of the rotation emit before proceeding |
| Phase 4 exit | Action name unregistered or emit bypasses canonical sink | Register action in `${PROJECT_ROOT}/.agents/projectContext/audit-spec.md`; reroute through canonical sink |
| Phase 5 exit | Archival record missing any of which / when / what / who | Add missing fact before recording rotation complete |
| Phase 5 exit | Last-rotation timestamp not updated in `${PROJECT_ROOT}/.agents/projectContext/secrets-policy.md` register | Update register; without it the next cadence check is wrong |

---

## Interactions with other skills

- **`secret-handling`** — `rotation` extends `secret-handling` with the
  lifecycle dimension. `secret-handling` gates where a secret lives, how it
  is read, and that it does not flow to forbidden sinks. `rotation` gates how
  long a secret may continue to live there, the controlled procedure for
  replacing it, and the archival record produced when it is retired. A
  `secret-handling` finding that includes the words "unrotated > N" is the
  canonical hand-off — that finding routes here.
- **`crypto-compliance`** — `rotation` extends `crypto-compliance` with the
  lifecycle dimension over primitives. `crypto-compliance` gates the
  algorithm, key size, curve, and TLS configuration of a new credential.
  `rotation` is the procedure for retiring the prior credential and bringing
  the new (compliant) credential into service. Phase 3 of this skill MUST
  route any new primitive through `crypto-compliance` before issuance.
- **`audit-emit`** — `rotation` Phase 4 routes to `audit-emit` in full.
  `audit-emit` owns action classification, emit construction, sink routing,
  fail-closed behavior, and test obligation. `rotation` supplies the action
  semantics (`key.rotate` or project-defined equivalent), the
  retired/replacement references, and the approver identity. Phase 4 cannot
  exit until `audit-emit` Phase 5 has completed.
- **`stage-gating`** — Stage value read in Pre-Flight feeds cadence selection
  (Phase 2) and approver requirement (Phase 3). Stage 3+ tightens both.
- **`decision-lifecycle`** — A `PAST-CADENCE` artifact with a justified
  exception is recorded as a CONFIRM in `${PROJECT_ROOT}/.agents/projectContext/open-questions.md`, not silently
  reconciled here. An exception that becomes permanent is an ADR candidate
  authored only via `/adr`.

---

## Subagents Invoked

None directly. `rotation` operates within the orchestrator context and hands
off to the `audit-emit` skill in Phase 4. The `auth-crypto-reviewer` agent
may be dispatched by the orchestrator when reviewing a rotation PR, but that
dispatch is owned by the routing table in `AGENTS.md`, not by this skill.
