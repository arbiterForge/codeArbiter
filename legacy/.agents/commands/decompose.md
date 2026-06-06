<!--
Copyright (c) 2026 suadtl
Author: suadtl
Created: 2026-05-14
File: decompose.md
-->

# /decompose

## Purpose

Bootstrap the projectContext for a green-field project — one with no meaningful
source code yet. Routes to the `decompose` skill, which conducts a layered
interview to elicit purpose, scope, primary users, domain vocabulary, and
architectural constraints, then writes the full
`${PROJECT_ROOT}/.agents/projectContext/` file set and locks the project as
initialized.

This is the **only permitted path** to initialize projectContext when no
meaningful source code exists. For an existing codebase, use `/create-context`
instead.

## Usage

```
/decompose
```

No arguments. The skill interviews the user; it does not need a starting
artifact, though one (e.g., a project handoff summary) may be supplied freely
during the interview phases.

## Routes To

`decompose` skill (`${FRAMEWORK_ROOT}/.agents/skills/decompose/SKILL.md`) —
all six phases:

| Phase | What happens |
|---|---|
| 1 — Pre-Flight Confirmation | Confirms green-field state; verifies no source code and no existing initialization sentinel |
| 2 — Persona Adoption | codeArbiter adopts the decomposer persona for the interview |
| 3 — Layered Interview (Layers 1–6) | Structured elicitation across the six decomposition layers |
| 4 — Synthesis | Interview responses → draft projectContext files; low-confidence inferences flagged as `[CONFIRM-NN]` |
| 5 — projectContext Population | All files written to `${PROJECT_ROOT}/.agents/projectContext/` |
| 6 — Initialization Lock | `<!--INITIALIZED-->` sentinel written; full file tree displayed |

## Hard Gates

- BLOCK if `<!--INITIALIZED-->` already present in `${PROJECT_ROOT}/.agents/projectContext/CONTEXT.md` — context exists; route to normal operation instead
- BLOCK if meaningful source code is detected — route to `/create-context` instead
- BLOCK if any `[CONFIRM-NN]` item exits Phase 4 without being resolved or explicitly deferred
- BLOCK if `<!--INITIALIZED-->` sentinel is not written before Phase 6 closes

## When NOT to Use

- **Context already initialized:** check `/status` or look for `<!--INITIALIZED-->` in `CONTEXT.md`
- **Existing codebase (source code present):** use `/create-context`
- **Broken / partially initialized state:** use `/init` (repair only — restores sentinel without re-running the interview)
- **Update a specific projectContext file:** edit `${PROJECT_ROOT}/.agents/projectContext/` directly or use `/feature`
