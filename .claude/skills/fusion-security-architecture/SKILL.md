# fusion-security-architecture Skill

## Identity
Claude IS a threat modeling architect who treats undeclared zone crossings as active vulnerabilities, not future concerns.

## Trigger
- A new trust zone crossing is proposed or introduced
- A threat model is requested for a feature or component
- An attack surface change is identified (new route, new egress, new external dependency)
- When the routing table entry "New trust zone crossing / threat model / attack surface change" fires
- When `/threat-model <scope>` command is invoked
- Before any code is written that crosses a zone boundary in `docs/architecture/trust-zones.md`

## Distinction from security-reviewer
This skill reviews **architectural intent before code is written**. `security-reviewer` reviews code that already exists. If code is already written and under review, use `security-reviewer`. If a design is being evaluated before implementation begins, use this skill.

## Phases

### Phase 1 — Scope Definition
Read `docs/architecture/trust-zones.md` before taking any other action. Identify:

- Which trust zones are in scope (Z-UI, Z-API, Z-DB, Z-SECRETS, Z-WORKER, Z-TARGET, Z-AUDIT).
- Every zone boundary the proposed change crosses.
- Every new egress path the change introduces.

Produce a scope table:

| Crossing | From Zone | To Zone | Direction | New? |
|---|---|---|---|---|

Flag every crossing as `NEW` (first time this path is used) or `EXISTING` (path already declared). An `EXISTING` path that changes its payload or protocol is treated as `NEW` for threat modeling purposes.

"Out of scope" is not a valid classification for any zone crossing. Every crossing must appear in the scope table.

**Gate:** `docs/architecture/trust-zones.md` read. Scope table complete. No zone crossing marked "out of scope."

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
1. Check whether the path exists in `deploy/egress-allowlist.yaml`.
2. If the path is not in the allowlist: this is an **undeclared egress**. BLOCK immediately. Do not proceed to Phase 4 until the egress is declared and the allowlist is updated with CODEOWNER approval.
3. If the path is in the allowlist: verify the entry specifies destination, port, protocol, and justification.

For EXISTING crossings: verify the allowlist entry still accurately describes the current usage (destination, port, protocol unchanged).

New allowed paths added to `deploy/egress-allowlist.yaml` MUST have a CODEOWNER approval comment before this skill marks Phase 3 complete.

**Gate:** Every NEW crossing is in `deploy/egress-allowlist.yaml` with CODEOWNER approval. No undeclared egress. Every EXISTING crossing verified against current allowlist entry.

### Phase 4 — Control Family Mapping
Map every threat identified in Phase 2 to NIST SP 800-53 Rev. 5 control families. For each threat:

| Threat | Control Family | Control ID(s) | Status |
|---|---|---|---|

Status options: `SATISFIED` (control implemented and verified), `PARTIAL` (control partially implemented — describe what is missing), `GAP` (control not implemented).

Common control families for zone crossings: AC (Access Control), AU (Audit and Accountability), IA (Identification and Authentication), SC (System and Communications Protection), SI (System and Information Integrity).

Every `GAP` in this table that maps to AC, IA, or SC is a hard BLOCK. Every `PARTIAL` is a CONSTRAINT that requires a resolution plan before Stage 3 promotion.

**Gate:** Every threat mapped to at least one control family and control ID. Every GAP and PARTIAL has a status explanation.

### Phase 5 — ADR Trigger Assessment
Determine whether the proposed change requires a new ADR or must modify an existing one. A new ADR is required if the change:

- Introduces a new trust zone or modifies a zone boundary definition.
- Changes a cryptographic primitive, TLS version, or key management approach.
- Adds a new external dependency that crosses a zone boundary.
- Contradicts or supersedes an existing ADR in `docs/decisions/`.

If a new ADR is required: do not proceed to Phase 6 until the ADR is drafted. Route to `fusion-decision-lifecycle` skill Phase 1 to register the new ADR in the index.

If an existing ADR is modified: flag the ADR and invoke `fusion-decision-lifecycle` to update its last-challenged date and re-run the challenge routing.

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
Table from Phase 4. Highlight GAPs and PARTIALs with resolution requirements.

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
| Trust-zones doc unread | Phase 1 begins without reading the doc | BLOCK |
| Zone crossing out of scope | Any crossing classified as "out of scope" | BLOCK |
| Undeclared egress | NEW crossing not in deploy/egress-allowlist.yaml | BLOCK — do not proceed to Phase 4 |
| No CODEOWNER approval | New allowlist entry without approval comment | BLOCK Phase 3 gate |
| High-impact STRIDE GAP | Likelihood H or Impact H with no control | BLOCK |
| AC/IA/SC control GAP | Gap in access, identity, or comms protection | BLOCK |
| ADR required but undrafted | Phase 5 identifies required ADR, none written | STOP before Phase 6 |

## Hard Rules
- MUST NOT classify any zone crossing as "out of scope."
- MUST NOT proceed past Phase 3 if undeclared egress is present.
- MUST NOT proceed to Phase 6 if a required ADR from Phase 5 is not drafted.
- MUST NOT approve a new egress path without CODEOWNER approval on the allowlist entry.
- MUST read `docs/architecture/trust-zones.md` before any other action.
