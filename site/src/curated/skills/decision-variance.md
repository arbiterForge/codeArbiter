---
entity: skills/decision-variance
related: [commands/reconcile, decision-lifecycle]
gates:
  - gate: stale-decision surfacing
    when: an in-scope prior decision has an artifact-section hash
    effect: changed or missing evidence is reported without rewriting history or stopping independent report analysis
  - gate: user-attributed resolution
    when: recording a reconciliation choice
    effect: the specific choice must come from you; an unchanged choice already supplied is not requested again
---

## What it does

Owns architectural reconciliation and read-only variance reporting. Its concise
entry metadata routes to one procedure; the detailed analysis card has no discovery
frontmatter and loads only for an actual pass. The card compares selected records
with scaffold evidence, scores disagreements with SMARTS, and returns a report.

## Phases

1. Select explanation, report-only, or reconciliation intent and scope before
   loading analysis. Explanation needs no reconciliation card.
2. Locate exact inputs and check relevant decision history. Full passes require
   the three decomposition records; scoped passes read only necessary sources.
3. Classify evidence and generate SMARTS recommendations, including unresolved
   same-level conflicts. Unknown categories and stale decisions remain visible.
4. In reconciliation only, capture your concrete choices in the append-only log.
   Report-only returns before this phase without file changes or a decision interview.
5. Return requested downstream-readiness recommendations and the original caller's
   separately authorized continuation. No automatic commit, PR or branch cleanup follows.

## Exits

Ratification, supersession and explicit deferral retain their own log records.
A stale source hash is never repaired in place: an authorized reaffirmation appends
a new entry that references the prior decision. Resume rechecks current history
and does not duplicate a choice whose append already succeeded.

The owner never edits the artifacts, scaffold or code to fix a variance itself.
Replacement ADRs use `decision-lifecycle` with the user's decision and attribution;
authoring and implementation need their own direction, not a repeated command spelling.
This interactive arbitration boundary does not restrict delegated sprint methods.
