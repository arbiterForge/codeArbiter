---
description: Report ADR health — aged decisions, unchallenged ADRs, unresolved CONFIRM-NN placeholders, and supersession candidates.
argument-hint: "[--adr <number>]"
---

Report the current health of all architectural decisions. Invokes the
`fusion-decision-lifecycle` skill.

Arguments:
- `${1:-}` — optional `--adr <number>` to scope the report to a single ADR;
  omit for a full health report across all ADRs.

## Invoke fusion-decision-lifecycle Skill

Invoke the `fusion-decision-lifecycle` skill with the following context:

```
Scope: ${1:---all}
Current date: [today's date in YYYY-MM-DD]
Current stage: [read from .fusion/stage]
```

The skill will execute all 5 phases:

1. **Phase 1 — Index Scan**: Build ADR table with status and age. Flag any ADR not reviewed in 12 weeks as AGED.
2. **Phase 2 — CONFIRM-NN Audit**: Classify every CONFIRM-NN placeholder as RESOLVED-WITH-EVIDENCE, PARTIALLY-EVIDENCED, or OPEN. Surface each non-RESOLVED entry to the user.
3. **Phase 3 — Supersession Check**: Identify ADRs that contradict newer ADRs but are not marked superseded.
4. **Phase 4 — Challenge Routing**: Spawn `decision-challenger` agent for every AGED and UNCHALLENGED ADR.
5. **Phase 5 — Lifecycle Report**: Produce the full structured report.

## Scoped Run (--adr <number>)

If `${1}` is `--adr <N>`: run Phases 1–5 scoped to ADR-N only. Phase 4 will
challenge only that ADR. The lifecycle report will cover only that ADR.

## Hard Stops

MUST NOT resolve any CONFIRM-NN without explicit user decision and attribution.
MUST NOT mark an ADR superseded without surfacing the candidate pair to the user.
If any ADR returns confidence ≤ 2 from the decision-challenger: surface immediately
before completing Phase 5 output.

## Completion Report

After Phase 5 completes, output the lifecycle report directly. Also state:
- Total ADRs reviewed
- Count AGED, count UNCHALLENGED
- Count OPEN CONFIRM-NN, count PARTIALLY-EVIDENCED
- Count confidence ≤ 2 (REQUIRES-IMMEDIATE-REVIEW)
- Count supersession candidates requiring human decision

If any REQUIRES-IMMEDIATE-REVIEW findings exist: these MUST be resolved before
the next `/promote-stage` run.
