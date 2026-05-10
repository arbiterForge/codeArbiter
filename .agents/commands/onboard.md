# /onboard [topic]

## Purpose

Interactive onboarding tour of the project for new contributors or new AI sessions. Invokes the `onboard` skill. Two modes: full tour (no argument) or targeted deep-dive (with a topic argument). Stays conversational until the user exits or asks to switch topics.

## Usage

```
/onboard                    # full tour — covers all major areas
/onboard architecture       # targeted: trust zones, ADRs, key design decisions
/onboard security           # targeted: security controls, threat model, secrets policy
/onboard workflow           # targeted: commands, TDD workflow, commit/PR flow
/onboard stack              # targeted: tech stack, dependencies, test runner
/onboard decisions          # targeted: ADR index, accepted decisions, open questions
```

## Routes To

`onboard` skill (`.agents/skills/onboard/SKILL.md`).

## Full Tour Mode

When invoked without an argument, the skill covers:

1. **Project identity** — what this project does, its current stage, primary contributors
2. **Tech stack** — language, framework, test runner, key dependencies (from `projectContext/tech-stack.md`)
3. **Architecture** — trust zones, zone boundaries, key patterns (from `projectContext/trust-zones.md`)
4. **Security posture** — compliance level, key controls, what is and isn't allowed (from `projectContext/security-controls.md`)
5. **Workflow** — how features get built (TDD), how commits happen, how PRs open (from `AGENTS.md` command table)
6. **Open decisions** — ADRs that are proposed but not yet accepted, open `[CONFIRM-NN]` questions
7. **Open tasks** — what is in-flight vs. backlog (from `projectContext/open-tasks.md`)

The skill pauses after each topic and asks: "Ready to continue, or do you want to explore this topic further?"

## Targeted Mode

When invoked with a topic argument:

1. Skill reads the relevant `projectContext/` documents for that topic
2. Delivers a focused explanation of that area
3. Offers to answer follow-up questions in the same session
4. Remains in conversational mode until the user types "done" or invokes another command

## Key Behaviors

- **Read-only** — onboard never writes or modifies any file
- **Conversational** — responses are human-readable paragraphs, not machine-formatted reports
- **Honest about gaps** — if `projectContext/` is missing a document that should exist, the skill names the gap
- **Does not start implementation** — if the user asks "how do I build X?" during onboarding, the skill explains the process and suggests using `/feature` rather than starting implementation inline
- **No gates** — this command is always safe to invoke; no routing table entries fire

## When NOT to Use

- To start implementing: use `/feature`
- To get a quick project status: use `/status`
- To ask a specific question: use `/btw` (lighter weight than onboarding)
