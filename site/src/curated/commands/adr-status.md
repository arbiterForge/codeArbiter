---
entity: commands/adr-status
related: [adr, reconcile, skills/decision-lifecycle]
---

## What it does

A read-only health scan of every recorded ADR under `.codearbiter/decisions/`. For each one it
reports number, title, status, and date, then flags what needs attention: aged decisions,
`proposed` ADRs that were never challenged, supersession candidates where a newer ADR or code
pattern contradicts an older one, and any unresolved `[CONFIRM-NN]` placeholder left inside an ADR
body. Nothing is modified, and no `[CONFIRM-NN]` found during the scan is resolved here — it's
surfaced and left for you.

## Usage

```
/ca:adr-status [--adr N]
```

With no argument it scans every ADR; `--adr N` narrows the scan to a single ADR.

## Example

```text
> /ca:adr-status

## ADR Status — 2026-07-02

### Active
- ADR-0005 — Split the persona register — accepted (2026-06-18)
- ADR-0006 — Decline a commercial vertical — accepted (2026-06-20)
- ADR-0007 — Use PostgreSQL as the primary database — proposed (2026-07-01)

### Superseded
- ADR-0003 — Original watch-strangers onboarding — superseded by ADR-0006

### Unresolved CONFIRM-NN
- ADR-0007 — [CONFIRM-08]: connection-pool sizing not yet decided
```

## When to reach for it

A quick health check across all ADRs. To record a new decision, use `/ca:adr`; to challenge or
reconcile a specific ADR in depth, use `/ca:reconcile`.
