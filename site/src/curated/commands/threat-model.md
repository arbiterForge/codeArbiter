---
entity: commands/threat-model
related: [checkpoint, skills/security-architecture]
use_when: "You are about to build something sensitive, such as a new external endpoint, a secrets-handling path or an auth flow, and want threats found before code exists."
avoid_when: "Ordinary changes, and code that is already written, which `/ca:review` or `/ca:checkpoint` cover instead."
asks: "A scope description: the feature or component, how sensitive its data is and who can reach it."
produces: "A STRIDE report with the attack surface, threats and their mitigations, recommended controls and a verdict of PROCEED, PROCEED-WITH-CONSTRAINTS or STOP. It changes no project files."
---

## What it does

An opt-in, lightweight STRIDE pass over a design before it's built — invoked deliberately, never
forced on an ordinary change. It maps the attack surface (new entry points, new egress, security
boundaries crossed against `.codearbiter/security-controls.md`, the data handled), then walks each
of the six STRIDE categories — spoofing, tampering, repudiation, information disclosure, denial of
service, elevation of privilege — marking each threat's mitigation `PRESENT`, `PLANNED`, or `GAP`.
It reads no code changes to review after the fact; for code already written, `/ca:review` or
`/ca:checkpoint` cover that ground instead.

The report distinguishes `PROCEED`, `PROCEED-WITH-CONSTRAINTS`, and `STOP`.
A critical, currently exploitable, unmitigated threat stops the pass. Missing required
security controls is a separate prerequisite failure. The pass and any optional
reviewers are read-only; they do not create an ADR or change project files.

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

## Verdict
PROCEED-WITH-CONSTRAINTS: implement signature verification before exposing the endpoint.
```
