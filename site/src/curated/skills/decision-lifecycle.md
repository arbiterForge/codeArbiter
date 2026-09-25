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

1. Index existing records by full filename stem and select the next unused sequential number.
2. Author a new decision record from content you confirm — never inferred — and append a matching
   entry to the decision log, with your name as decider.
3. (Status mode) Report each full stem, stored governance status, derived delivery state and forward
   supersession, preserving ambiguous references and unresolved questions.

## Exits

Authoring leaves a new decision record on disk in `proposed` status with a matching log entry;
status reporting changes nothing. A decision with no clear user attribution, or one proposed as
the outcome of an ordinary finding rather than your explicit call, never gets recorded.

## Acceptance and delivery evidence

Stored `accepted` means **Accepted/Planned**. A sealed acceptance binding records the exact
committed ADR and its complete normative obligations in
`.codearbiter/decisions/adr-lifecycle.jsonl`. The acceptance commit must already exist before the
binding append; preserve its source ancestry through delivery.

Implemented and Verified are derived only from complete, current, input-bound evidence for all
sealed obligations. Verification includes an explicit repository proof contract, producer,
observation and expiry. An unsealed legacy baseline remains Accepted/Planned; changed inputs or
expired proof withhold a stronger current claim without deleting history. Repository proof does not
establish external installation, publication, support or legal claims.

[ADRs and the decision log](/concepts/adrs/) explains the separate files, full-stem identity,
partial supersession and practical evidence checks.
