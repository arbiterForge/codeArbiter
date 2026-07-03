---
entity: skills/decision-lifecycle
related: [commands/adr, commands/adr-status, decision-variance]
gates:
  - gate: authoring
    when: recording a new decision
    effect: the decision content must come from you, not inference, and the record is never authored as the disposition of a routine finding
---

## What it does

This is where architecture decisions get written down and tracked. The adr command routes here to
author a new, numbered, dated decision record with your explicit attribution; the status command
routes here to list every decision's health, read-only. It shares its scoring reference and log
format with the arbitration skill but owns a different half of the job: recording a decision you
have already made, not helping you make one.

## Phases

1. Index existing decision records and fix the next sequential number.
2. Author a new decision record from content you confirm — never inferred — and append a matching
   entry to the decision log, with your name as decider.
3. (Status mode) Report every indexed record's number, title, status, date, and whether a later
   record supersedes it, plus any unresolved open question found inside one.

## Exits

Authoring leaves a new decision record on disk in `proposed` status with a matching log entry;
status reporting changes nothing. A decision with no clear user attribution, or one proposed as
the outcome of an ordinary finding rather than your explicit call, never gets recorded.
