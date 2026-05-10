# /stage [N]

## Purpose

Report the current project stage, or run the promotion checklist to advance to a target stage. Invokes the `stage-gating` skill. Stage promotions require a signed-off checkpoint document and a named approver — codeArbiter cannot promote a stage on its own authority.

## Usage

```
/stage          # reports current stage from projectContext/stage
/stage 2        # runs full promotion checklist from current stage to Stage 2
/stage 3        # runs full promotion checklist from current stage to Stage 3
```

## Routes To

`stage-gating` skill (`.agents/skills/stage-gating/SKILL.md`).

## Without Target (Status Report Mode)

When invoked without an argument:

1. Reads `projectContext/stage` — current stage number and name
2. Reads `projectContext/checkpoints/` — most recent checkpoint document
3. Reports:
   - Current stage
   - Date of most recent signed-off checkpoint
   - Any `BLOCKS_S[N+1]` findings from the most recent checkpoint that are unresolved

## With Target (Promotion Mode)

When invoked with a target stage number:

1. `stage-gating` skill reads `projectContext/stage` — confirms promotion is to the next stage only (no skipping)
2. Reads the most recent checkpoint document from `projectContext/checkpoints/`
3. Verifies the checkpoint sign-off block is complete (named approver, signed off)
4. Verifies all `BLOCKS_S[target]` findings from the checkpoint are resolved
5. Verifies any stage-specific criteria from `projectContext/open-questions.md` are resolved
6. If all gates pass: presents the proposed stage change to the user for confirmation
7. User confirms → `projectContext/stage` updated to target stage number

## Stage Table

Stage table lives in `projectContext/stage-definitions.md` (or equivalent). The generic progression:

| Stage | Typical Promotion Trigger |
|-------|--------------------------|
| 1 | Initial project start |
| 2 | First non-team user; OR codebase threshold reached; OR contributor count threshold |
| 3 | Customer-adjacent environment; OR sensitive data introduced; OR external assessor named |
| 4 | Production deployment; OR multi-tenant; OR formal security boundary declared |

Read `projectContext/stage-definitions.md` for the exact criteria defined for this project.

## Hard Gates

- MUST NOT skip stages — promotion is always to the immediately next stage
- MUST NOT update `projectContext/stage` without a signed-off checkpoint
- MUST NOT update `projectContext/stage` while `BLOCKS_S[target]` findings are unresolved
- MUST NOT update `projectContext/stage` without naming an approver
- Named approver MUST be a person, not "codeArbiter" or "automated"

## When NOT to Use

- To run a checkpoint: use `/checkpoint` first, then come back to `/stage N`
- To ask what stage criteria mean: use `/btw`
