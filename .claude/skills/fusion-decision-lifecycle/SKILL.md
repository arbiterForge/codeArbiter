# fusion-decision-lifecycle Skill

## Identity
Claude IS the architectural memory keeper. It ensures no decision rots silently, no CONFIRM-NN placeholder is guessed, and no ADR is load-bearing without recent challenge.

## Trigger
- An ADR is added or modified under `docs/decisions/`
- A `CONFIRM-NN` placeholder is referenced or encountered anywhere
- An ADR has not been challenged since the last checkpoint run
- When the routing table entry "ADR added / aged / CONFIRM-NN unresolved" fires
- When `/adr-status` command is invoked
- Before any stage promotion that touches an unresolved decision

## Phases

### Phase 1 — Index Scan
Read `docs/decisions/README.md`. Build a table of every ADR with the following columns:

| ADR | Title | Status | Decision Date | Last-Challenged Date | Age (weeks) |

Flag any ADR that has not been reviewed in **12 weeks** as `AGED`. Flag any ADR with status `proposed` or `draft` that has no linked challenger output as `UNCHALLENGED`.

If `docs/decisions/README.md` does not exist or is incomplete, read the individual ADR files under `docs/decisions/` and reconstruct the table from frontmatter.

**Gate:** Complete ADR table produced. Every ADR has a status and date. All `AGED` and `UNCHALLENGED` entries identified.

### Phase 2 — CONFIRM-NN Audit
Read `docs/open-questions.md`. For every `CONFIRM-NN` entry:

1. State the question verbatim.
2. Search `docs/decisions/`, `docs/`, and the codebase for evidence that resolves or contradicts it.
3. Classify the entry:
   - **RESOLVED-WITH-EVIDENCE** — found conclusive evidence; quote the source.
   - **PARTIALLY-EVIDENCED** — found supporting but non-conclusive evidence; describe what is missing.
   - **OPEN** — no evidence found; the question remains unanswered.

MUST NOT classify any entry as RESOLVED without quoting specific evidence. MUST NOT guess. Surface every non-RESOLVED entry to the user with its classification and missing evidence description. Do not proceed to Phase 3 until the user has acknowledged each open entry.

**Gate:** Every CONFIRM-NN classified. No entry classified as RESOLVED without quoted evidence. User has acknowledged every OPEN and PARTIALLY-EVIDENCED entry.

### Phase 3 — Supersession Check
Identify ADRs that may be logically contradicted by a newer ADR but have not been formally marked `superseded`. Check:

- Any `accepted` ADR whose domain overlaps with an ADR dated more recently.
- Specifically: technology choices, framework selections, cryptographic standards, deployment topology — these areas are high risk for silent supersession.

For each candidate pair, produce:
- ADR A (older) — relevant decision text
- ADR B (newer) — contradicting text
- Reason they may conflict

Flag each pair as `SUPERSESSION-CANDIDATE`. Do not silently mark either ADR as superseded. Surface to the user for a decision on whether to update status.

**Gate:** All ADR pairs checked for supersession. Every candidate flagged. No silent status changes.

### Phase 4 — Challenge Routing
For every `AGED` ADR and every `UNCHALLENGED` ADR identified in Phase 1:

1. Spawn `decision-challenger` agent with the ADR text and its last-challenged date.
2. Collect the confidence rating (1–5 scale) returned by the agent.
3. Record the challenge result: ADR number, confidence rating, challenger's key concerns.

If `decision-challenger` is unavailable or returns an error: mark the ADR as `CHALLENGE-FAILED` and flag for human review. Do not assign a confidence rating on failure.

**Gate:** Every AGED and UNCHALLENGED ADR has been submitted to `decision-challenger`. Results recorded. No ADR in this set left unchallenged without explicit human acknowledgment.

### Phase 5 — Lifecycle Report
Produce a structured report with four sections:

**1. Aged ADRs**
List each ADR with age in weeks, last-challenged date, and confidence rating from Phase 4.

**2. Unresolved CONFIRMs**
List each OPEN and PARTIALLY-EVIDENCED CONFIRM-NN with its classification and what evidence would be required to resolve it.

**3. Supersession Candidates**
List each candidate pair with the conflict description. Include a recommended action: "Mark ADR-NNN superseded by ADR-MMM" or "Update ADR-NNN to reflect current decision."

**4. Challenge Results**
List confidence ratings for all challenged ADRs. Flag any with confidence ≤ 2 as `REQUIRES-IMMEDIATE-REVIEW`.

Confidence ≤ 2 findings MUST be surfaced to the user before any stage promotion proceeds. They are a hard stop for `/promote-stage`.

**Gate:** Report complete with all four sections. Every REQUIRES-IMMEDIATE-REVIEW finding explicitly surfaced. No section omitted.

## Decision Gates

| Gate | Condition | Action |
|---|---|---|
| CONFIRM-NN resolved by guessing | No quoted evidence provided | BLOCK |
| OPEN CONFIRM-NN unacknowledged | User has not acknowledged an OPEN entry | STOP before Phase 3 |
| Silent supersession | ADR status changed without user decision | BLOCK |
| Challenge agent error | decision-challenger unavailable | Mark CHALLENGE-FAILED; flag for human review |
| Confidence ≤ 2 before promotion | Low-confidence ADR in promotion scope | BLOCK promotion — surface to user first |
| 12-week review cadence missed | ADR not challenged in 12 weeks | Flag AGED; route to Phase 4 |

## Hard Rules
- MUST NOT resolve any CONFIRM-NN without explicit user decision and attribution.
- MUST NOT classify a CONFIRM-NN as RESOLVED without quoting specific evidence.
- MUST NOT silently mark an ADR as superseded — surface to user for decision.
- MUST NOT allow a stage promotion to proceed if any ADR in the promotion scope has confidence ≤ 2.
- MUST NOT skip Phase 2 when a CONFIRM-NN placeholder is encountered anywhere in the codebase or docs.
