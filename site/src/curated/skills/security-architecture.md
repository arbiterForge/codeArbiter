---
entity: skills/security-architecture
related: [commands/threat-model]
gates:
  - gate: critical unmitigated threat
    when: during the structured threat pass
    effect: the only condition that stops the pass outright — an exploitable, high-impact gap with no mitigation; lesser gaps are reported as constraints instead
---

## Phases

1. Map the attack surface — new entry points, new outbound calls, security boundaries crossed,
   and the sensitivity of the data involved.
2. Walk that surface through six threat categories, marking each relevant one's mitigation as
   present, planned, or a gap, and optionally dispatching a specialist reviewer for auth, crypto,
   or broader boundary concerns.
3. Report the surface, the threats found — gaps first — and a verdict: proceed, proceed with
   named constraints, or stop.

## Exits

The report hands any decision-worthy gap to you or to a decision record; this skill never
authors one itself. Everything short of a critical threat is surfaced as a constraint to carry
forward.
