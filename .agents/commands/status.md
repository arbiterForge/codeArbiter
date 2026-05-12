# /status

## Purpose

Display a formatted summary of the project's current state: open tasks, open questions, current stage, and most recent checkpoint status. Read-only. No side effects. No skill invoked.

## Usage

```
/status
```

No arguments.

## What Happens

1. Reads `${PROJECT_ROOT}/.agents/projectContext/stage` — current stage number and name
2. Reads `${PROJECT_ROOT}/.agents/projectContext/open-tasks.md` — all tasks, grouped by status (IN-FLIGHT, BACKLOG, DONE)
3. Reads `${PROJECT_ROOT}/.agents/projectContext/open-questions.md` — all unresolved `[CONFIRM-NN]` placeholders and open questions
4. Reads `${PROJECT_ROOT}/.agents/projectContext/checkpoints/` — most recent checkpoint file (if any), sign-off status, unresolved findings
5. Reads `${PROJECT_ROOT}/.agents/projectContext/decisions/README.md` — count of proposed vs. accepted ADRs
6. Outputs a formatted status report

## Output Structure

```
## Project Status — YYYY-MM-DD

### Stage
Stage N — <name>

### Open tasks
IN-FLIGHT (N):
- <task title> — <brief description>

BACKLOG (N):
- <task title>

### Open questions
- [CONFIRM-NN] <question text> — from ADR-NNNN

### ADR health
- Accepted: N
- Proposed (awaiting challenge): N
- Aged (>12 weeks): N

### Most recent checkpoint
- Date: YYYY-MM-DD
- Sign-off: COMPLETE / PENDING
- Unresolved BLOCKS_S[N+1] findings: N
```

## Hard Gates

- Read-only — no file is modified
- If `[CONFIRM-NN]` placeholders are found in open-questions.md: surface them in the output but do NOT resolve them
- No skill is invoked by this command

## When NOT to Use

- For a deep review of ADR health: use `/adr-status`
- For a full checkpoint: use `/checkpoint`
- For a specific question: use `/btw`
