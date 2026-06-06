<!--
Copyright (c) 2026 suadtl
Author: suadtl
Created: 2026-05-10
File: checkpoint.md
-->

# /checkpoint

## Purpose

Run a full cross-cutting review of the codebase: architecture drift, test coverage, security posture, coding standards, scaffold completeness, and decision health. Produces a dated checkpoint document that must be signed off by a named approver before any stage promotion. All 7 reviewer agents run — no skipping.

## Usage

```
/checkpoint
```

No arguments. Checkpoint reviews the entire codebase against all projectContext documents.

## Routes To

All 7 checkpoint agents run in parallel (no ordering dependency between them):

1. `architecture-drift-reviewer` — reads `${PROJECT_ROOT}/.agents/projectContext/decisions/` and scans for code that contradicts accepted ADRs
2. `coverage-auditor` — reads `${PROJECT_ROOT}/.agents/projectContext/audit-spec.md` and `${PROJECT_ROOT}/.agents/projectContext/tech-stack.md`; audits test coverage and audit event emission
3. `security-reviewer` — reads `${PROJECT_ROOT}/.agents/projectContext/security-controls.md` and `${PROJECT_ROOT}/.agents/projectContext/trust-zones.md`; reviews security posture
4. `standards-compliance-reviewer` — reads `${PROJECT_ROOT}/.agents/projectContext/coding-standards.md`; checks naming, banned patterns, type safety
5. `scaffold-completeness-reviewer` — reads `${PROJECT_ROOT}/.agents/projectContext/open-tasks.md`; identifies planned artifacts that don't yet exist
6. `decision-challenger` — reads `${PROJECT_ROOT}/.agents/projectContext/decisions/`; adversarially challenges every accepted ADR

Then sequentially:

7. `finding-triage` — reads all 6 reviewer reports; assigns stage promotion impact to each finding (`BLOCKS_S2`, `DEFERRED_S3`, `NON_BLOCKING`)
8. `checkpoint-aggregator` — reads triage report and `${PROJECT_ROOT}/.agents/projectContext/stage`; writes dated checkpoint to `${PROJECT_ROOT}/.agents/projectContext/checkpoints/YYYY-MM-DD.md`

## What Happens Step by Step

1. All 6 reviewer agents dispatched in parallel
2. Each agent returns a structured findings report
3. `finding-triage` reads all 6 reports, classifies each finding by stage promotion impact
4. `checkpoint-aggregator` writes `${PROJECT_ROOT}/.agents/projectContext/checkpoints/YYYY-MM-DD.md` containing:
   - All findings by severity
   - Triage classification for each finding
   - Current stage status
   - Sign-off block (date, reviewer names, sign-off status — to be completed manually)
5. Report URL / path presented to user

## Output Document Structure

```
# Checkpoint — YYYY-MM-DD

## Current stage
Stage N — <name>

## Summary of findings

| Reviewer | CRITICAL | HIGH | MEDIUM | LOW |
|----------|----------|------|--------|-----|
| ...      | N        | N    | N      | N   |

## All findings

### [Reviewer name]
- <Severity>: <finding> — <file:line> — <triage classification>

## Stage promotion impact

### BLOCKS_S2 (must resolve before Stage 2 promotion)
- ...

### DEFERRED_S3 (must resolve before Stage 3 promotion)
- ...

### NON_BLOCKING (informational)
- ...

## Sign-off block

| Field | Value |
|-------|-------|
| Date | YYYY-MM-DD |
| Reviewed by | [name] |
| Sign-off status | PENDING |

Sign-off must be completed by a named approver before stage promotion proceeds.
```

## Hard Gates

- All 7 agents MUST complete — no skipping
- MUST NOT promote stage without a signed-off checkpoint document
- If `security-reviewer` raises CRITICAL: all work halts until user resolves before sign-off can occur
- `[CONFIRM-NN]` placeholders found during the review MUST NOT be resolved by guessing — surface and stop
- Read-only (except writing the checkpoint document) — no code is modified

## When NOT to Use

- For a targeted review of a specific file: use `/review`
- For a pre-implementation threat model: use `/threat-model`
- For ADR health only: use `/adr-status`
- For stage promotion: use `/stage N` after the checkpoint is signed off
