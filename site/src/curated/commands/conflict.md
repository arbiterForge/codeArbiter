---
entity: commands/conflict
related: [override, reconcile]
use_when: "Two rules, documents or pieces of code contradict each other and you need work to stop until you decide. codeArbiter usually raises this on its own."
avoid_when: "A gate you have decided to bypass rather than a contradiction to resolve, which is `/ca:override`."
asks: "How to resolve it: update one source, update the other, or supersede one with an ADR. Work stays halted until you decide."
produces: "A halt report quoting both passages, the nature of the conflict and its level in the conflict hierarchy. The only change afterward is a document update you authorized."
gates:
  - gate: halt on detection
    when: the persona, a .codearbiter/ document, and code contradict each other — or two docs contradict each other
    effect: all other work stops, both sides are quoted side by side and classified against the conflict-resolution hierarchy, and work resumes only after you resolve it explicitly
---

## What it does

The protocol for a rule conflict — not a skill route, an orchestrator-level halt. When two sources
disagree (the persona vs. a `.codearbiter/` document, a doc vs. code, or two docs against each
other), everything in progress stops, both passages are quoted exactly, and the tension is
classified against the conflict-resolution hierarchy so you can see which level it sits at. The
orchestrator never picks a side, and recency alone never decides it — a more-recently-updated
source is noted as informational, not determinative. It also fires automatically whenever the
orchestrator detects this class of contradiction on its own, not just when invoked directly.

## Usage

```
/ca:conflict
```

Takes no arguments — it presents whatever conflict triggered it (or the most recent one it detected).

## Example

```text
> /ca:conflict

## Conflict detected — work halted

### Source A
File: plugins/ca/arbiter.md · Last updated: 2026-06-10
> Direct commit to a protected branch is prohibited.

### Source B
File: .codearbiter/decisions/0004-fast-forward-hotfix-branch.md · Last updated: 2026-07-01
> Hotfix commits may land directly on main under the fast-forward exception.

### Nature of conflict
ADR-0004 appears to carve an exception into a hard rule the persona states as absolute.

### Conflict-hierarchy level
Level 1 — a hard rule vs. an accepted ADR.

### To resolve
Update ADR-0004 to route through commit-gate, or supersede the hard rule via a new ADR.

---
Work is halted. Resolve before the orchestrator proceeds.
```
