# Skill: decision-lifecycle

## Trigger

> *"This section lists conditions under which the orchestrator routes work to this skill. The skill itself does not 'trigger' — it is routed to."*

Invoke this skill to audit the health of the project's decision record — ADRs,
open questions, and CONFIRM-NN placeholders. Also invoke whenever a new ADR is
added, an ADR ages past review threshold, or a CONFIRM-NN is encountered.

Triggers:
- User requests an ADR status review or decision health check
- A new ADR file is added to `${PROJECT_ROOT}/.agents/projectContext/decisions/`
- A CONFIRM-NN placeholder is found in any document or code
- The `decision-lifecycle` skill is referenced in the routing table
- Stage promotion is requested (decision health is a gate)

---

## Pre-Flight

Before Phase 1 begins, confirm:

1. `${PROJECT_ROOT}/.agents/projectContext/decisions/README.md` is readable — stop if missing.
2. `${PROJECT_ROOT}/.agents/projectContext/open-questions.md` is readable — stop if missing.
3. The agent has NOT resolved any CONFIRM-NN by assumption in the current
   session. If a guess was made, surface it immediately and stop.

If any file is missing, surface the gap and stop.

---

## Phase 1: Index Scan

**Goal:** Build a complete, current table of all ADRs and identify which require
attention.

**Inputs:**
- `${PROJECT_ROOT}/.agents/projectContext/decisions/README.md` — ADR index
- All ADR files under `${PROJECT_ROOT}/.agents/projectContext/decisions/`

**Actions:**

1. Read `${PROJECT_ROOT}/.agents/projectContext/decisions/README.md` to obtain the ADR index.
2. For each ADR listed, read the corresponding file and record:
   - ADR ID and title
   - Status (`proposed`, `accepted`, `superseded`, `deprecated`, or project-defined)
   - Date accepted or last reviewed
   - Whether a challenger agent review has been recorded
3. Compute the age of each ADR in weeks from the accepted or last-reviewed date.
4. Flag each ADR with one or more health tags:

   | Tag                  | Condition                                                    |
   |----------------------|--------------------------------------------------------------|
   | AGED                 | More than 12 weeks since accepted or last reviewed           |
   | UNCHALLENGED         | No challenger agent review recorded since last status change |
   | SUPERSESSION-CANDIDATE | Status or rationale may be contradicted by a newer ADR     |
   | HEALTHY              | None of the above apply                                      |

5. Record the complete ADR table with health tags.

Any ADR tagged AGED (>12 weeks) OR triggered by a stage promotion event MUST proceed to Phase 4 (challenge routing) — the challenge is no longer optional in those two cases.

**Output:** ADR health table with ID, title, status, age, and health tags.

**Gate:** BLOCK. Phase 2 does not begin until the ADR table is complete. A
partial scan is not acceptable — every ADR in the index must be reviewed.

---

## Phase 2: CONFIRM-NN Audit

**Goal:** Classify every open CONFIRM-NN placeholder and surface unresolved ones
to the user. MUST NOT guess resolutions.

**Inputs:**
- `${PROJECT_ROOT}/.agents/projectContext/open-questions.md` — authoritative list of CONFIRM-NN
  placeholders
- All ADR files under `${PROJECT_ROOT}/.agents/projectContext/decisions/`
- Any other project documents that may contain CONFIRM-NN references

**Actions:**

1. Read `${PROJECT_ROOT}/.agents/projectContext/open-questions.md` in full.
2. For each CONFIRM-NN entry, search for evidence of resolution:
   - An ADR that explicitly closes the question with a cited decision
   - A documented user decision recorded in the session or commit history
   - An updated status in `open-questions.md` itself with attribution
3. Classify each CONFIRM-NN as one of:

   | Status                  | Meaning                                                         |
   |-------------------------|-----------------------------------------------------------------|
   | RESOLVED-WITH-EVIDENCE  | Decision recorded; evidence (ADR or user attribution) cited     |
   | PARTIALLY-EVIDENCED     | Some evidence exists but the resolution is incomplete or ambiguous |
   | OPEN                    | No resolution evidence found                                    |

4. MUST NOT classify a CONFIRM-NN as RESOLVED-WITH-EVIDENCE without citing the
   specific evidence (file path, ADR ID, or session record).
5. Surface every OPEN and PARTIALLY-EVIDENCED CONFIRM-NN to the user with its
   ID and a brief description of what decision is needed.

**Output:** CONFIRM-NN classification table with status and evidence citations
for each entry.

**Gate:** BLOCK. MUST NOT guess the resolution of any CONFIRM-NN. If a
resolution cannot be evidenced, it remains OPEN. Do not proceed to Phase 3
without surfacing all OPEN items to the user.

---

## Phase 3: Supersession Check

**Goal:** Identify ADRs whose content may be contradicted or superseded by
newer ADRs, without silently changing their status.

**Inputs:**
- ADR health table from Phase 1
- All ADR files under `${PROJECT_ROOT}/.agents/projectContext/decisions/`

**Actions:**

1. For each ADR flagged AGED or whose domain overlaps with a more recent ADR,
   compare the rationale, constraints, and decisions of both ADRs.
2. If a newer ADR's decision contradicts or makes a prior ADR's decision
   obsolete, flag the older ADR as SUPERSESSION-CANDIDATE.
3. Record the newer ADR that triggers the flag as the potential superseding
   document.
4. MUST NOT silently change the status of any ADR. A SUPERSESSION-CANDIDATE
   flag is advisory — only the user or a recorded decision can change an ADR's
   formal status.
5. If two ADRs appear to conflict with no clear supersession direction, flag
   both as SUPERSESSION-CANDIDATE and surface the conflict to the user.

**Output:** List of SUPERSESSION-CANDIDATE ADRs with the potential superseding
document identified for each.

**Gate:** BLOCK if an ADR conflict is found and cannot be directionally resolved
by reading the documents. Surface the conflict to the user and stop until they
provide direction.

---

## Phase 4: Challenge Routing

**Goal:** Spawn challenge reviews for ADRs that are AGED or UNCHALLENGED, and
record confidence ratings.

**Inputs:**
- ADR health table from Phase 1 — specifically the AGED and UNCHALLENGED entries
- ADR files for each flagged decision

**Actions:**

1. For each ADR tagged AGED, UNCHALLENGED, or flagged by a stage-promotion event, dispatch the decision-challenger agent. AGED and stage-promotion challenges MUST execute; UNCHALLENGED follows existing logic.
2. The `decision-challenger` agent MUST return a confidence rating for each
   reviewed ADR:

   | Rating | Meaning                                                           |
   |--------|-------------------------------------------------------------------|
   | 3      | Decision still clearly valid; no change recommended               |
   | 2      | Decision likely valid but some uncertainty; re-review recommended |
   | 1      | Decision questionable; strong recommendation to revisit           |
   | 0      | Decision appears invalid or superseded; blocking finding          |

3. Record the confidence rating and the challenger agent's reasoning for each
   reviewed ADR.
4. ADRs with a confidence rating of 0 or 1 are escalated in the Phase 5 report.

**Output:** Challenge results table with ADR ID, confidence rating, and
challenger reasoning for each AGED or UNCHALLENGED ADR.

**Gate:** No ADR rated 0 may proceed silently. A rating of 0 is a blocking
finding that must be surfaced to the user and resolved before stage promotion.

---

## Phase 5: Lifecycle Report

**Goal:** Produce a complete, actionable decision health report with clear
findings and required actions.

**Inputs:**
- ADR health table from Phase 1
- CONFIRM-NN classification table from Phase 2
- SUPERSESSION-CANDIDATE list from Phase 3
- Challenge results from Phase 4

**Actions:**

1. Compile the report with exactly four sections:

   **Section 1 — Aged ADRs**
   List each ADR tagged AGED with its age in weeks, health tags, and the
   challenge result (confidence rating and reasoning).

   **Section 2 — Unresolved CONFIRMs**
   List each CONFIRM-NN in OPEN or PARTIALLY-EVIDENCED status with its ID,
   description, and what evidence would be needed to resolve it. Do not list
   RESOLVED-WITH-EVIDENCE items here.

   **Section 3 — Supersession Candidates**
   List each SUPERSESSION-CANDIDATE with the potential superseding ADR and a
   brief description of the conflict or overlap.

   **Section 4 — Challenge Results**
   List all challenge results from Phase 4, ordered by confidence rating
   (lowest first).

2. Any ADR with a confidence rating of ≤ 2 must include a recommended action
   (re-review, revise, or supersede).
3. If any confidence rating is ≤ 2, flag this in the report as a stage
   promotion blocker. A confidence rating of ≤ 2 blocks stage promotion until
   the ADR is formally revisited or confirmed by the user.

**Output:** Four-section lifecycle report delivered to the user.

**Gate:** Report is complete when all four sections are populated. An empty
section must be explicitly marked "None found" — not omitted. Any confidence
rating of ≤ 2 must be surfaced as a stage promotion blocker.

---

## Decision Gates Summary

| Gate         | Condition                                                    | Action if blocked                          |
|--------------|--------------------------------------------------------------|--------------------------------------------|
| Phase 1 exit | ADR index scan incomplete                                    | Complete scan; do not proceed with partial table |
| Phase 2 exit | CONFIRM-NN resolved by guessing                              | Stop; surface OPEN item to user            |
| Phase 3 exit | ADR conflict found with no directional resolution            | Surface conflict; stop until user provides direction |
| Phase 4 exit | ADR rated 0 by challenger agent                              | Escalate to user; block stage promotion    |
| Phase 4 entry | AGED ADR or stage-promotion event without dispatched challenge | BLOCK; dispatch challenger before continuing |
| Phase 5 exit | Report section missing or confidence ≤ 2 not flagged        | Complete report; flag blockers             |

---

## Hard Rules

- MUST read `${PROJECT_ROOT}/.agents/projectContext/decisions/README.md` before Phase 1.
- MUST NOT resolve a CONFIRM-NN by guessing. Surface OPEN items and stop.
- MUST NOT silently change the status of any ADR. Status changes require user
  attribution or a recorded decision.
- MUST NOT omit a report section. Empty sections are marked "None found".
- MUST NOT allow stage promotion if any confidence rating is ≤ 2 without user
  review.
- MUST NOT classify a CONFIRM-NN as RESOLVED-WITH-EVIDENCE without citing
  specific evidence.
- MUST NOT skip spawning the `decision-challenger` agent for AGED or
  UNCHALLENGED ADRs — the skill's challenge routing is not optional.
- MUST dispatch decision-challenger on every AGED ADR. The challenge is not optional after 12 weeks.
- MUST dispatch decision-challenger on all ADRs as part of any stage promotion (via /release or /stage).

---

## Failure Modes

| Failure                                              | Response                                                          |
|------------------------------------------------------|-------------------------------------------------------------------|
| `decisions/README.md` missing                        | Stop; surface gap; do not proceed without ADR index               |
| `open-questions.md` missing                          | Stop; surface gap; CONFIRM-NN audit cannot complete               |
| CONFIRM-NN with no evidence found                    | Classify as OPEN; surface to user; do not guess resolution        |
| Two ADRs in apparent conflict                        | Flag both as SUPERSESSION-CANDIDATE; surface to user              |
| `decision-challenger` agent unavailable              | Record challenge as DEFERRED; flag affected ADRs in report        |
| Confidence rating ≤ 2 found                          | Include in report as stage promotion blocker; surface to user     |
