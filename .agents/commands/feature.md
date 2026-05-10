# /feature "description"

## Purpose

Start a new feature. This is the **only permitted path** to begin implementation work. Invoking `/feature` triggers the full TDD workflow and routes to the appropriate implementation agent. No code may be written before Phase 1 of the `tdd` skill completes.

## Usage

```
/feature "clear description of the feature"
```

The description must be specific enough to determine scope (backend, frontend, infra, or multi-area). Vague descriptions like "improve things" will be rejected — codeArbiter will ask for clarification before proceeding.

## Routes To

`tdd` skill (`.agents/skills/tdd/SKILL.md`) — all 6 phases.

## Implementation Agent

After Phase 1 (obligation checklist) is complete, codeArbiter routes to one of:

- `backend-author` — for backend/API/service code
- `frontend-author` — for UI/frontend code
- `infra-author` — for IaC, containers, CI/CD manifests

Agent selection is based on the feature scope described. If scope spans multiple agents, they are coordinated **sequentially** — each agent must complete its TDD workflow before the next begins. The full test suite must pass between agent transitions.

## What Happens Step by Step

1. Phase 1 (obligation checklist) runs — identifies all test obligations before any code is written
2. codeArbiter selects the implementation agent(s) based on scope
3. Selected agent reads `projectContext/tech-stack.md` and `projectContext/coding-standards.md`
4. Agent writes failing tests for every Phase 1 obligation
5. Agent confirms each test fails for the right reason
6. Agent writes minimum implementation to make tests pass
7. Full test suite runs — must be green before proceeding
8. Lint and type-check run — must pass before proceeding
9. Phase 6 (commit readiness check) — hands off to `/commit` if all gates pass

## Hard Gates

- MUST NOT begin implementation before Phase 1 (obligation checklist) is complete
- Implementation agent MUST read `projectContext/tech-stack.md` before writing any code
- Test MUST be written and confirmed **failing** before any implementation code is written
- Full test suite MUST be green before staging any file
- Lint and type-check MUST pass before staging any file
- If a security-sensitive path is touched (auth, crypto, secrets, middleware, audit), `security-reviewer` agent is invoked before the commit gate

## When NOT to Use

- **Bug fixes:** use `/fix` — Phase 1 is framed differently (regression test first)
- **Questions / discussion:** use `/btw` — no routing table fires
- **Committing existing work:** use `/commit`
- **Dependencies:** use `/add-dep`
- **IaC-only infrastructure work with no application code:** `/feature` still applies — `infra-author` is the routed agent
