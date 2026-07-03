---
entity: commands/threat-model
related: [checkpoint, skills/security-architecture]
gates:
  - gate: critical-gap stop
    when: a STRIDE category comes back GAP — exploitable now, high impact
    effect: the pass halts with a stated verdict of STOP naming the specific unmitigated threat; a lesser gap is surfaced as a constraint, not a halt
---

## What it does

An opt-in, lightweight STRIDE pass over a design before it's built — invoked deliberately, never
forced on an ordinary change. It maps the attack surface (new entry points, new egress, security
boundaries crossed against `.codearbiter/security-controls.md`, the data handled), then walks each
of the six STRIDE categories — spoofing, tampering, repudiation, information disclosure, denial of
service, elevation of privilege — marking each threat's mitigation `PRESENT`, `PLANNED`, or `GAP`.
It reads no code changes to review after the fact; for code already written, `/ca:review` or
`/ca:checkpoint` cover that ground instead.

## Usage

```
/ca:threat-model "<scope description>"
```

Name the feature or component, its data sensitivity, and the actors that reach it — that framing
becomes the scope of the STRIDE pass.

## Example

```text
> /ca:threat-model "new public webhook endpoint that receives partner payment notifications"

## Scope
Public webhook receiving partner payment notifications; no prior auth boundary here.

## STRIDE findings
| Threat | Category | Likelihood | Impact | Control |
|---|---|---|---|---|
| Unsigned payload accepted as genuine | Spoofing | H | H | GAP — no signature verification planned |
| Payload replay | Repudiation | M | M | PLANNED — nonce + timestamp window |

## Recommended controls before implementation
- HMAC signature verification on the webhook payload before any processing.

## Clearance
BLOCKED — resolve findings first
```

## When to reach for it

Before writing a sensitive feature — new external endpoints, new secrets-handling paths, new
auth/authz flows. Not a routine gate; skip it for ordinary changes.
