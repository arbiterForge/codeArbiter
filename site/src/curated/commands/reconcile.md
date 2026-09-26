---
entity: commands/reconcile
related: [adr, adr-status, conflict, skills/decision-variance]
gates:
  - gate: explicit choice per recorded variance
    when: recording an arbitration outcome, not returning a report
    effect: "Only your concrete choice is recorded. A choice you already supplied is carried forward without asking again; general delegation is not an arbitration decision."
---

## What it does

Compares architectural records with the scaffold and prior decisions using SMARTS.
The explicit command and a natural-language reconciliation request use the same
`decision-variance` owner. A variance-report request is read-only: it returns
findings and recommendations without recording decisions or starting an interview.
Report-only never enters the decision-capture phase.

A full pass locates `01-architecture-breakdown.md`, `02-phased-build-plan.md`, and
`03-task-backlog.md` by exact name. A named ADR, artifact, or area selects a scoped
pass; unrelated decomposition files are not prerequisites. Missing or unreadable
inputs remain visible coverage gaps, never a clean result. This comparison uses
Markdown architectural records; typed HTML feature specs/plans retain their
existing typed workflow owner, not Markdown section-hash handling.

## Usage

```text
/ca:reconcile [<ADR-id | artifact | scope>]
```

Leave the target empty for a full pass. ADR numbers must resolve to one full
filename stem; an ambiguous number is not silently assigned to the first match.

## Example

Illustrative read-only request:

```text
Show a variance report for 0004-cache-boundary. Do not change files.
```

The report identifies the selected record, evidence, unresolved choices and
coverage limits. It does not write an evidence-index file, update a decision hash,
create a question, or author an ADR.

During reconciliation, you choose ratify, supersede or defer. The choice is logged
with your attribution. Reaffirming a decision against a changed source section
appends a replacement binding with the current hash; it never edits the old entry.
A replacement ADR or implementation is a separately authorized continuation. An
already selected request passes to its owning procedure without another routing menu.

## When to reach for it

Use it to examine a real architectural variance. ADR recording and health use
`decision-lifecycle`; ordinary explanation does not require reconciliation. Routine
Git text conflicts stay with their existing workflow. Delegated sprint method
choices retain sprint's SMARTS scoring and do not inherit an arbitration interview.
