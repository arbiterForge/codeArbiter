---
entity: commands/reconcile
related: [adr, adr-status, conflict, skills/decision-variance]
use_when: "You have a real architectural variance to examine, such as records that disagree with the scaffold or with a prior decision, and you want a report or a recorded choice."
avoid_when: "Recording or checking ADRs, which are `/ca:adr` and `/ca:adr-status`; a rule conflict between sources, which is `/ca:conflict`; or a routine Git text conflict."
asks: "An optional ADR, artifact or area to scope the pass. When you reconcile, you choose to ratify, supersede or defer each variance; a report-only request asks you nothing."
produces: "A variance report with evidence, unresolved choices and coverage limits, and when you reconcile, your logged choice with your attribution. It never edits the artifacts or code itself."
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
existing typed workflow owner, not Markdown section-hash handling. In an
HTML-knowledge repository the full pass reads the decomposition records instead
(component and decision records for architecture, phase records for the plan,
work-item records for the backlog), citing their stable record IDs.

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
