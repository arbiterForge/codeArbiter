---
description: Pre-implementation security architecture review for a proposed zone crossing, feature, or attack surface change.
argument-hint: "<scope: path, feature name, or zone crossing e.g. 'Z-UI → Z-API'>"
---

Run a pre-implementation security architecture review. This command reviews
**architectural intent before code is written**. For reviewing code that already
exists, use `security-reviewer` agent instead.

Arguments:
- `${1:?scope required}` — path, feature name, or zone crossing description
  (e.g., `Z-UI → Z-API`, `backend/src/auth/`, `new secrets rotation endpoint`)

## Pre-flight

1. Read `docs/architecture/trust-zones.md` in full — required before any action.
2. Read `CLAUDE.md` §8 (trust zone diagram) to orient the scope.
3. Read `.fusion/stage` — threat model findings are stage-aware.

## Invoke fusion-security-architecture Skill

Invoke the `fusion-security-architecture` skill with the following context:

```
Scope: ${1}
Current stage: [read from .fusion/stage]
```

The skill will execute all 6 phases:

1. **Phase 1 — Scope Definition**: Map every zone boundary the proposed change crosses. No crossing may be classified as "out of scope."
2. **Phase 2 — Threat Model**: STRIDE analysis for every zone crossing. Identify GAP and CONSTRAINT findings.
3. **Phase 3 — Zero Trust Validation**: Verify `deploy/egress-allowlist.yaml` contains every NEW crossing with CODEOWNER approval.
4. **Phase 4 — Control Family Mapping**: Map every threat to NIST SP 800-53 Rev. 5 control families.
5. **Phase 5 — ADR Trigger Assessment**: Determine whether the change requires a new ADR or modifies an existing one.
6. **Phase 6 — Report**: Structured findings with verdict: PROCEED / PROCEED-WITH-CONSTRAINTS / STOP-NEEDS-ADR.

## Hard Stops

MUST NOT proceed past Phase 3 if undeclared egress is present.
If Phase 5 identifies a required ADR: MUST NOT produce a PROCEED verdict until
the ADR is drafted. Route to `fusion-decision-lifecycle` to register it.
If verdict is STOP-NEEDS-ADR: implementation MUST NOT begin until the ADR is
written and the threat-model is re-run.

## Completion Report

After Phase 6 completes, output:
- Verdict: PROCEED / PROCEED-WITH-CONSTRAINTS / STOP-NEEDS-ADR
- Count of zone crossings reviewed (NEW vs. EXISTING)
- Count of STRIDE GAP findings by severity
- Count of control family gaps (AC / IA / SC — these are hard blocks)
- Any required ADR actions from Phase 5
- List of CONSTRAINT findings with resolution owners (if PROCEED-WITH-CONSTRAINTS)

A PROCEED or PROCEED-WITH-CONSTRAINTS verdict is required before implementation
begins. Do not begin writing code until this command completes without a
STOP-NEEDS-ADR verdict.
