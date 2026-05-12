# /onboard [topic]

## Purpose

Interactive onboarding tour of the project for new contributors or new AI sessions. Two modes: full tour (no argument) or targeted deep-dive (with a topic). Stays conversational until the user exits or switches topics. Read-only — never writes or modifies any file.

## Usage

```
/onboard                    # full tour — covers all major areas
/onboard architecture       # trust zones, ADRs, key design decisions
/onboard security           # security controls, threat model, secrets policy
/onboard workflow           # commands, TDD workflow, commit/PR flow
/onboard stack              # tech stack, dependencies, test runner
/onboard decisions          # ADR index, accepted decisions, open questions
```

## Routes To

`onboard` skill (`${FRAMEWORK_ROOT}/.agents/skills/onboard/SKILL.md`).

The topic argument scopes which `${PROJECT_ROOT}/.agents/projectContext/` documents the skill reads. Without an argument, the skill walks the full set with a pause-and-confirm rhythm between topics.

## When NOT to Use

- To start implementing: use `/feature`
- To get a quick project status: use `/status`
- To ask a specific question: use `/btw` (lighter weight than onboarding)
