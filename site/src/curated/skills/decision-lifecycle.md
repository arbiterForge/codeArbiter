---
entity: skills/decision-lifecycle
related: [commands/adr, commands/adr-status, decision-variance]
gates:
  - gate: authoring
    when: recording a new decision
    effect: the decision content must come from you, not inference, and the record is never authored as the disposition of a routine finding
---

## What it does

One owner records architecture decisions you have already made and reports existing ADR
health. Natural-language requests and the explicit `adr` and `adr-status` entries reach
that owner. Choosing between competing options still belongs to decision-variance.

## Select the operation first

A status request reads existing records without loading the authoring procedure. It does
not create a missing decisions directory, arm a marker, change a status, append a log, or
repair missing evidence. A missing directory is reported as absent. `--adr N` must resolve
to exactly one full filename stem; shared numbers are reported as ambiguous.

An authoring request loads the owner's authoring reference only after explicit intent and
attribution are established. It indexes the records, selects an unused sequential number,
writes confirmed content, and appends the corresponding decision-log entry. The same
reference owns the separate, explicitly authorized acceptance and status transitions.
The shared ADR template and acceptance/delivery rules are unchanged.

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
