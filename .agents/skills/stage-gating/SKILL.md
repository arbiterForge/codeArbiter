# stage-gating Skill

## Identity
Claude IS a stage compliance enforcer who treats a stage-tagged rule violation as a deployment blocker, not a style issue.

## Trigger

> *"This section lists conditions under which the orchestrator routes work to this skill. The skill itself does not 'trigger' — it is routed to."*

- Any code change that has different rules at different stages.
- When the agent needs to know what the current stage requires.
- When stage-tagged rules in AGENTS.md and `${PROJECT_ROOT}/.agents/projectContext/` files apply differently to the change.
- When code contains stage-conditional logic.

## Phases

### Phase 1 — Stage Read
Run `cat ${PROJECT_ROOT}/.agents/projectContext/stage` and record the integer value. This is the authoritative current stage — do not infer it from code, comments, or config files. If `${PROJECT_ROOT}/.agents/projectContext/stage` is absent or non-numeric, STOP and surface the error.

**Gate:** `${PROJECT_ROOT}/.agents/projectContext/stage` read successfully. Integer value recorded.

### Phase 2 — Rule Inventory
List all stage-tagged rules from AGENTS.md and all `${PROJECT_ROOT}/.agents/projectContext/` files that apply at or below the current stage. Rules tagged `[Sn]` apply when current stage ≥ n. Rules tagged `[Sn+]` apply starting at stage n. Untagged rules always apply. Output: table of active rules with their source file.

**Gate:** Rule inventory complete. Every active rule identified with source.

### Phase 3 — Violation Scan
Scan the code change against every active rule from Phase 2. BLOCK on any match. Document each violation with: rule text, source file, line in changed code, severity.

**Gate:** No active rule violations found. All violations documented if present.

### Phase 4 — Higher-Stage Pre-Check
Identify rules that will activate at the next stage (current + 1). Flag any violations of those rules as DEFERRED findings — they do not block now but must be resolved before the next stage promotion. Hard rule: if code contains a pattern that conditionally skips a security check based on stage value (e.g., `if (stage === 1) skipSecurityCheck()`), invoke `/surface-conflict` immediately and STOP.

**Gate:** DEFERRED findings documented. No security-bypass conditionals present.

### Phase 5 — Enforcement Report
Output a table:

| Rule | Status | Evidence |
|---|---|---|
| [rule text] | ACTIVE / DEFERRED / SATISFIED | [file:line or "no violation"] |

Every active rule must appear. SATISFIED means the rule applies and the code complies. ACTIVE means a violation was found (BLOCK). DEFERRED means it is a next-stage concern.

**Gate:** Report produced. All active rules listed.

## Decision Gates

| Gate | Condition | Action |
|---|---|---|
| Stage file missing | `${PROJECT_ROOT}/.agents/projectContext/stage` absent or non-numeric | BLOCK |
| Active rule violation | Any `[Sn]` rule violated at current stage | BLOCK |
| Security bypass | Stage-conditional security skip detected | BLOCK — invoke /surface-conflict |
| Deferred violations | Next-stage rules violated | FLAG as DEFERRED |

## Hard Rules
- MUST NOT infer stage from anything other than `cat ${PROJECT_ROOT}/.agents/projectContext/stage`.
- MUST NOT allow stage-conditional security bypasses without invoking /surface-conflict.
- MUST NOT skip the rule inventory — every tagged rule must be checked.
- MUST NOT skip stages on promotion — target stage MUST be current + 1.
- MUST NOT accept "codeArbiter", "automated", or any non-human identity as the named approver — approver MUST be a person.

## Reference: Stage Table

The generic stage table. Project-specific promotion criteria are in `${PROJECT_ROOT}/.agents/projectContext/decisions/` or `${PROJECT_ROOT}/.agents/projectContext/open-questions.md`.

| Stage | Name | Generic Promotion Criteria |
|---|---|---|
| 1 | Prototype | Internal team only; single-node deployment; no external users; no regulated data |
| 2 | Internal MVP | First non-team user; OR codebase >15k LOC; OR >5 contributors |
| 3 | Hardened Pilot | Customer-adjacent environment; OR regulated data introduced; OR >25 concurrent users; OR external assessor named |
| 4 | Production | Formal compliance submission required; OR multi-tenant; OR declared compliance boundary |

## Reference: Reading the Current Stage

```bash
cat ${PROJECT_ROOT}/.agents/projectContext/stage
# => 1
```

In code:

```typescript
const stage = parseInt(await fs.readFile('${PROJECT_ROOT}/.agents/projectContext/stage', 'utf8').then(s => s.trim()));
```

## Reference: Tag Conventions

Rules in AGENTS.md and `${PROJECT_ROOT}/.agents/projectContext/` files carry tags:

- `[S1]` — applies only at Stage 1
- `[S2+]` — applies at Stage 2 and later
- `[S3+]` — applies at Stage 3 and later
- `[S1–S2]` — applies at Stages 1 and 2 only (typically Stage-2-deprecated)
- No tag — applies at all stages

## Reference: Stage Tag Quick Reference

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

## Reference: What Promotes a Stage

ONLY the `/promote-stage` command modifies `${PROJECT_ROOT}/.agents/projectContext/stage`. The agent MUST NOT edit this file directly. Promotion requires:

1. All gates that become enforcing at the target stage currently pass.
2. All `[CONFIRM-NN]` items blocking the target stage are resolved.
3. All risks with `Target Closure: Stage <target>` are closed with an ADR.
4. Named approver posts the literal approval comment.

Consult `${PROJECT_ROOT}/.agents/projectContext/decisions/` and `${PROJECT_ROOT}/.agents/projectContext/open-questions.md` for project-specific promotion criteria.
