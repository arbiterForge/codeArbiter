---
entity: commands/adr-status
related: [adr, reconcile, skills/decision-lifecycle]
use_when: "You want a quick health check across every recorded ADR: ages, unchallenged proposals, supersession candidates and unresolved `[CONFIRM-NN]` placeholders."
avoid_when: "Recording a new decision, which is `/ca:adr`, or challenging and reconciling a specific decision in depth, which is `/ca:reconcile`."
asks: "Nothing. It only reads, and `--adr N` is optional if you want to look at one ADR."
produces: "A report in the conversation listing each ADR's title, governance status, delivery state and date, plus what needs attention. It changes no files."
---

## What it does

A read-only health scan of every recorded ADR under `.codearbiter/decisions/`. For each one it
reports full filename stem, title, stored governance status, derived delivery state, and date, then flags what needs attention: aged decisions,
`proposed` ADRs that were never challenged, supersession candidates where a newer ADR or code
pattern contradicts an older one, and any unresolved `[CONFIRM-NN]` placeholder left inside an ADR
body. Nothing is modified, and no `[CONFIRM-NN]` found during the scan is resolved here — it's
surfaced and left for you.

## Usage

```
/ca:adr-status [--adr N]
```

With no argument it scans every ADR. `--adr N` narrows the scan only when the number
resolves to exactly one full filename stem. No match or multiple matches is reported,
never guessed. The small entry selects the shared owner's read-only mode before any
authoring prerequisites. A missing directory is reported without creating it.

## Example

```text
Illustrative report, not a captured run:
> /ca:adr-status

## ADR Status — 2026-07-02

### Active
- ADR-0005-split-the-persona-register — Split the persona register — governance: accepted; delivery: Accepted/Planned (2026-06-18)
- ADR-0006-decline-a-commercial-vertical — Decline a commercial vertical — governance: accepted; delivery: Accepted/Planned (2026-06-20)
- ADR-0007-use-postgresql — Use PostgreSQL as the primary database — governance: proposed; delivery: no accepted binding (2026-07-01)

### Superseded
- ADR-0003-original-onboarding — Original onboarding — superseded by ADR-0006-decline-a-commercial-vertical

### Ambiguous supersession
None

### Unresolved CONFIRM-NN
- ADR-0007-use-postgresql — [CONFIRM-08]: connection-pool sizing not yet decided
```
