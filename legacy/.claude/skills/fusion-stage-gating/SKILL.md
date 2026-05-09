---
name: fusion-stage-gating
description: Use whenever a code change has different rules at different FUSION stages, when the agent needs to know what the current stage requires, or when stage-tagged rules in CLAUDE.md and docs/ apply differently. Tells the agent how to read .fusion/stage, how stage tags work, and how to handle stage-conditional behavior in code.
---

# FUSION Stage Gating

FUSION uses a 4-stage trajectory. Many rules tighten as the system promotes
through stages. The agent MUST check the current stage before applying any
stage-tagged rule.

## The Four Stages

| Stage | Name | Promotion trigger (any one) |
|---|---|---|
| 1 | Prototype | Internal team only; single-node K3s; no external users; no CUI |
| 2 | Internal MVP | First non-team GDIT user; OR codebase >15k LOC; OR >5 contributors |
| 3 | Hardened Pilot | Customer-adjacent env; OR CUI introduced; OR >25 concurrent users; OR external assessor named |
| 4 | ATO-Ready Production | ATO submission required; OR multi-tenant; OR FedRAMP boundary declared |

## Reading the Current Stage

```bash
cat .fusion/stage
# => 1
```

In code:

```python
from backend.common.stage import current_stage  # reads .fusion/stage at startup, validates
```

## Tag Conventions in Documentation

Rules in CLAUDE.md and `docs/` carry tags:

- `[S1]` — applies only at Stage 1
- `[S2+]` — applies at Stage 2 and later
- `[S3+]` — applies at Stage 3 and later
- `[S1–S2]` — applies at Stages 1 and 2 only (typically Stage-2-deprecated)
- No tag — applies at all stages

When the current stage is `n`, every rule tagged `[Sn]` or `[Sm+]` where `m ≤ n` is enforcing. CI fails if a rule tagged `[Sn]` is violated when `current_stage ≥ n`.

## Stage-Conditional Code Patterns

When code legitimately needs to behave differently per stage:

```python
from backend.common.stage import current_stage, Stage

if current_stage() >= Stage.HARDENED_PILOT:        # >= 3
    require_mfa(claim_type="phishing-resistant")
else:
    require_mfa(claim_type="any")  # MFA required from S2 onward, but any factor at S2
```

Rules:

- The conditional MUST cite the doc rule it implements in a comment.
- Stage comparisons MUST use the `Stage` enum, never raw integers.
- The "lower stage" branch MUST NOT be a no-op for security-relevant behavior. If the rule requires MFA at S2+, MUST NOT skip MFA at S1 — the rule says "from S2 onward", and S1 is silent. Read the rule.

## What Promotes a Stage

ONLY the `/promote-stage` command (in `.claude/commands/promote-stage.md`)
modifies `.fusion/stage`. The agent MUST NOT edit this file directly.
Promotion requires:

1. All gates that become enforcing at the target stage currently pass.
2. All `[CONFIRM-NN]` items blocking the target stage are resolved.
3. All risks with `Target Closure: Stage <target>` are closed with ADR.
4. Named approver per `[CONFIRM-09]` posts the literal approval comment.

## What This Means for the Agent's Daily Work

- Before writing code that interacts with auth, audit, secrets, network, or supply chain — `cat .fusion/stage` and check the relevant doc for tags at that stage and below.
- When in doubt, code to the *higher* requirement. It's easier to relax than to harden.
- If you're tempted to write `if stage == 1: skip_security_check()` — STOP. Surface a conflict via `/surface-conflict`. Rules don't usually relax going up; they only tighten.
- When promoting a stage, do not bulk-disable Stage-N-only rules. Many remain enforcing forever; they were tagged `[Sn]` to indicate when they began applying, not when they end.

## Stage Tag Quick Reference

| Tag | Means |
|---|---|
| `[S1]` | At Stage 1 only |
| `[S2]` | At Stage 2 only |
| `[S3]` | At Stage 3 only |
| `[S4]` | At Stage 4 only |
| `[S2+]` | Stage 2 and all later stages |
| `[S3+]` | Stage 3 and all later stages |
| `[S1–S2]` | Stages 1 and 2 only |
| (no tag) | All stages |

## Verification

```bash
make stage-rules-check
# Lists every stage-tagged rule and whether it's currently enforcing.
```
