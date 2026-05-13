<!--
Copyright (c) 2026 suadtl
Author: suadtl
Created: 2026-05-10
File: SKILL.md
-->

# security-architecture Skill

## Identity
Claude IS a threat modeling architect who treats undeclared zone crossings as active vulnerabilities, not future concerns.

## Trigger

> *"This section lists conditions under which the orchestrator routes work to this skill. The skill itself does not 'trigger' — it is routed to."*

- A new trust zone crossing is proposed or introduced
- A threat model is requested for a feature or component
- An attack surface change is identified (new route, new egress, new external dependency)
- When the routing table entry "New trust zone crossing / threat model / attack surface change" applies
- When `/threat-model <scope>` command is invoked
- Before any code is written that crosses a zone boundary defined in `${PROJECT_ROOT}/.agents/projectContext/trust-zones.md`

## Distinction from security-reviewer
This skill reviews **architectural intent before code is written**. `security-reviewer` reviews code that already exists. If code is already written and under review, use `security-reviewer`. If a design is being evaluated before implementation begins, use this skill.

## Phases

### Phase 1 — Scope Definition
Read `${PROJECT_ROOT}/.agents/projectContext/trust-zones.md` before taking any other action. BLOCK if this file cannot be read. Identify:

- Which trust zones are in scope (zones are defined in `${PROJECT_ROOT}/.agents/projectContext/trust-zones.md`).
- Every zone boundary the proposed change crosses.
- Every new egress path the change introduces.

Produce a scope table:

| Crossing | From Zone | To Zone | Direction | New? |
|---|---|---|---|---|

Flag every crossing as `NEW` (first time this path is used) or `EXISTING` (path already declared). An `EXISTING` path that changes its payload or protocol is treated as `NEW` for threat modeling purposes.

"Out of scope" is not a valid classification for any zone crossing. Every crossing must appear in the scope table.

**Gate:** `${PROJECT_ROOT}/.agents/projectContext/trust-zones.md` read. Scope table complete. No zone crossing marked "out of scope."

### Phase 2 — Threat Model
For every zone crossing in the scope table, perform a STRIDE analysis:

| Threat | Category | Description | Likelihood (H/M/L) | Impact (H/M/L) |
|---|---|---|---|---|

STRIDE categories: Spoofing, Tampering, Repudiation, Information Disclosure, Denial of Service, Elevation of Privilege.

For each threat, identify:
- The specific control or mechanism expected to mitigate it.
- Whether that control exists today (`IMPLEMENTED`), is planned (`PLANNED`), or is absent (`GAP`).

A `GAP` finding with High likelihood or High impact is automatically a BLOCK. A `GAP` with Medium/Medium or lower is a CONSTRAINT that must appear in the report.

**Gate:** STRIDE analysis complete for every zone crossing. All GAP findings classified by likelihood and impact. No crossing skipped.

### Phase 3 — Zero Trust Validation
Verify that default-deny is maintained across every zone boundary in the scope.

For every NEW crossing identified in Phase 1:
1. Check whether the path exists in the egress allowlist. The location of the egress allowlist is defined in `${PROJECT_ROOT}/.agents/projectContext/trust-zones.md` (look for an `egress-allowlist` path or similar reference in that file; if the file is silent, use `deploy/egress-allowlist.yaml` as the default).
2. If the path is not in the allowlist: this is an **undeclared egress**. BLOCK immediately. Do not proceed to Phase 4 until the egress is declared and the allowlist is updated with CODEOWNER approval.
3. If the path is in the allowlist: verify the entry specifies destination, port, protocol, and justification.

For EXISTING crossings: verify the allowlist entry still accurately describes the current usage (destination, port, protocol unchanged).

New allowed paths added to the egress allowlist MUST have a CODEOWNER approval comment before this skill marks Phase 3 complete.

**Gate:** Every NEW crossing is in the egress allowlist with CODEOWNER approval. No undeclared egress. Every EXISTING crossing verified against current allowlist entry.

### Phase 4 — Control Family Mapping
Read `${PROJECT_ROOT}/.agents/projectContext/security-controls.md` to determine the compliance framework in use for this project (e.g., NIST SP 800-53, ISO 27001, SOC 2). Map every threat identified in Phase 2 to the applicable control families. For each threat:

| Threat | Control Family | Control ID(s) | Status |
|---|---|---|---|

Status options: `SATISFIED` (control implemented and verified), `PARTIAL` (control partially implemented — describe what is missing), `GAP` (control not implemented).

Reference the control family identifiers from the compliance framework specified in `${PROJECT_ROOT}/.agents/projectContext/security-controls.md`. If the file specifies no framework, use control categories generically (Access Control, Audit and Accountability, Identification and Authentication, System and Communications Protection, System and Information Integrity) and note that no specific compliance framework is declared.

Every `GAP` in this table that maps to access control, identity and authentication, or system and communications protection is a hard BLOCK. Every `PARTIAL` is a CONSTRAINT that requires a resolution plan before the next stage promotion.

**Gate:** Every threat mapped to at least one control family and control ID (or generic control category). Every GAP and PARTIAL has a status explanation.

### Phase 5 — ADR Trigger Assessment
Determine whether the proposed change requires a new ADR or must modify an existing one. A new ADR is required if the change:

- Introduces a new trust zone or modifies a zone boundary definition.
- Changes a cryptographic primitive, TLS version, or key management approach.
- Adds a new external dependency that crosses a zone boundary.
- Contradicts or supersedes an existing ADR in `${PROJECT_ROOT}/.agents/projectContext/decisions/`.

If a new ADR is required: do not proceed to Phase 6 until the ADR is drafted. Route to `decision-lifecycle` skill Phase 1 to register the new ADR in the index.

If an existing ADR is modified: flag the ADR and invoke `decision-lifecycle` to update its last-challenged date and re-run the challenge routing.

If no ADR is required: document the rationale (one sentence per trigger checked) in the report.

**Gate:** ADR trigger assessment complete with documented rationale. Any required ADR drafted before Phase 6.

### Phase 6 — Report
Produce a structured security architecture report with the following sections:

**1. Scope Summary**
Zone crossings table from Phase 1. Highlight NEW crossings.

**2. STRIDE Findings**
All threats with GAP or CONSTRAINT status. IMPLEMENTED threats are summarized in an appendix, not the main body.

**3. Zero Trust Status**
Egress allowlist verification results. Any undeclared egress (should already be BLOCKED, documented here for record).

**4. Control Family Coverage**
Table from Phase 4. Highlight GAPs and PARTIALs with resolution requirements. Note the compliance framework referenced.

**5. ADR Actions**
New ADRs required, existing ADRs modified, or explicit statement that no ADR action is needed.

**6. Verdict**
One of three verdicts:
- `PROCEED` — no GAPs, no undeclared egress, no required ADR outstanding.
- `PROCEED-WITH-CONSTRAINTS` — CONSTRAINT findings present; list each constraint and its resolution owner.
- `STOP-NEEDS-ADR` — Required ADR not yet drafted, or HIGH-impact GAP present.

**Gate:** Report complete with all six sections. Verdict stated. Every BLOCK-level finding from prior phases is reflected in the verdict.

## Decision Gates

| Gate | Condition | Action |
|---|---|---|
| Trust-zones doc unread | Phase 1 begins without reading `${PROJECT_ROOT}/.agents/projectContext/trust-zones.md` | BLOCK |
| Zone crossing out of scope | Any crossing classified as "out of scope" | BLOCK |
| Undeclared egress | NEW crossing not in the project egress allowlist | BLOCK — do not proceed to Phase 4 |
| No CODEOWNER approval | New allowlist entry without approval comment | BLOCK Phase 3 gate |
| High-impact STRIDE GAP | Likelihood H or Impact H with no control | BLOCK |
| Access/identity/comms control GAP | Gap in access control, identity, or communications protection | BLOCK |
| ADR required but undrafted | Phase 5 identifies required ADR, none written | STOP before Phase 6 |

## Hard Rules
- MUST NOT classify any zone crossing as "out of scope."
- MUST NOT proceed past Phase 3 if undeclared egress is present.
- MUST NOT proceed to Phase 6 if a required ADR from Phase 5 is not drafted.
- MUST NOT approve a new egress path without CODEOWNER approval on the allowlist entry.
- MUST read `${PROJECT_ROOT}/.agents/projectContext/trust-zones.md` before any other action. BLOCK if the file cannot be read.
- MUST read `${PROJECT_ROOT}/.agents/projectContext/security-controls.md` before Phase 4 to determine the applicable compliance framework.
