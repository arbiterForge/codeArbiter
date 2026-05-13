<!--
Copyright (c) 2026 suadtl
Author: suadtl
Created: 2026-05-12
File: create-context.md
-->

# /create-context

## Purpose

Bootstrap the projectContext for an existing codebase. Dispatches six parallel scout
subagents to read the repository, synthesizes their findings into the full
`${PROJECT_ROOT}/.agents/projectContext/` file set, fills gaps via a targeted interview, and
locks the project as initialized.

This is the **only permitted path** to initialize projectContext when meaningful source
code already exists. For a green-field project with no source code, use `/decompose`
instead.

## Usage

```
/create-context
```

No arguments. The skill reads the repository and asks only what it cannot determine
automatically.

## Routes To

`context-creation` skill (`${FRAMEWORK_ROOT}/.agents/skills/context-creation/SKILL.md`) —
all six phases:

| Phase | What happens |
|---|---|
| 1 — Pre-Flight Confirmation | Confirms brownfield state; identifies primary source directories |
| 2 — Scout Dispatch | Six `general-purpose` subagents read the codebase in parallel |
| 3 — Synthesis | Scout reports → draft projectContext files; low-confidence inferences flagged as `[CONFIRM-NN]` |
| 4 — Gap Interview | Targeted questions to resolve `CONFIRM-NN` items scouts could not answer |
| 5 — projectContext Write | All files written to `${PROJECT_ROOT}/.agents/projectContext/` |
| 6 — Initialization Lock | `<!--INITIALIZED-->` sentinel written; full file tree displayed |

## Hard Gates

- BLOCK if `<!--INITIALIZED-->` already present in `${PROJECT_ROOT}/.agents/projectContext/CONTEXT.md` — context exists; route to normal operation instead
- BLOCK if no meaningful source code found — route to `/decompose` instead
- BLOCK if any of the six Phase 2 scouts fails to return a report before Phase 3 begins
- BLOCK if any `[CONFIRM-NN]` item exits Phase 4 without being resolved or explicitly deferred
- BLOCK if `<!--INITIALIZED-->` sentinel is not written before Phase 6 closes

## When NOT to Use

- **Context already initialized:** check `/status` or look for `<!--INITIALIZED-->` in `CONTEXT.md`
- **Green-field project (no source code):** use `/decompose`
- **Broken / partially initialized state:** use `/init` (repair only — restores sentinel without re-running scouts)
- **Update a specific projectContext file:** edit `${PROJECT_ROOT}/.agents/projectContext/` directly or use `/feature`
