# /stage [N]

## Purpose

Report the current project stage, or run the promotion checklist to advance to a target stage. Stage promotions require a signed-off checkpoint and a named approver — codeArbiter cannot promote a stage on its own authority.

## Usage

```
/stage          # report current stage from projectContext/stage
/stage 2        # run promotion checklist: current → Stage 2
/stage 3        # run promotion checklist: current → Stage 3
```

## Routes To

`stage-gating` skill (`.agents/skills/stage-gating/SKILL.md`).

- **No argument:** status-report mode. Reads `projectContext/stage` and most recent `projectContext/checkpoints/*` doc; reports stage, last checkpoint date, unresolved `BLOCKS_S[N+1]` findings.
- **With target N:** promotion mode. Skill verifies sign-off, resolves blocks, then requires user confirmation before updating `projectContext/stage`.

## Command-owned reference

Generic stage progression (project-specific criteria in `projectContext/stage-definitions.md`):

| Stage | Typical Promotion Trigger |
|-------|--------------------------|
| 1 | Initial project start |
| 2 | First non-team user; OR codebase threshold reached; OR contributor count threshold |
| 3 | Customer-adjacent environment; OR sensitive data introduced; OR external assessor named |
| 4 | Production deployment; OR multi-tenant; OR formal security boundary declared |

## When NOT to Use

- To run a checkpoint: use `/checkpoint` first, then come back to `/stage N`
- To ask what stage criteria mean: use `/btw`
