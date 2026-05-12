# /feature "description"

## Purpose

Start a new feature. This is the **only permitted path** to begin implementation work. Invokes the full TDD workflow and routes to the appropriate implementation agent. No code may be written before `tdd` skill Phase 1 completes.

## Usage

```
/feature "clear description of the feature"
```

The description must be specific enough to determine scope (backend, frontend, infra, or multi-area). Vague descriptions like "improve things" will be rejected — codeArbiter will ask for clarification.

## Routes To

`tdd` skill (`.agents/skills/tdd/SKILL.md`) — all phases. After Phase 1, codeArbiter routes to one of:

- `backend-author` — backend / API / service code
- `frontend-author` — UI / frontend code
- `infra-author` — IaC, containers, CI/CD manifests

If scope spans multiple agents, they run sequentially. Full test suite must pass between transitions.

## When NOT to Use

- **Bug fixes:** use `/fix` — Phase 1 is framed differently (regression test first)
- **Questions / discussion:** use `/btw`
- **Committing existing work:** use `/commit`
- **Dependencies:** use `/add-dep`
