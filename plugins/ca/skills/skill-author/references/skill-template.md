---
name: <skill-name>
description: <One terse sentence: what routes to this skill, the phase count, and the hard gate. No doc refs, no trigger disclaimer. Example: "The only path to X. Routed to when the user invokes /foo. Three gated phases — A, B, C. Nothing ships until every gate clears.">
---

# <skill-name>

<One-line intro naming what routes to it: `/<command>` (user-invoked) or the parent skill (internal).>

## Pre-flight

Read these, or STOP and surface the gap — never guess a command:

- `${CLAUDE_PROJECT_DIR}/.codearbiter/<doc>.md` — <what it provides>. Stop if missing; do not guess.
- `${CLAUDE_PLUGIN_ROOT}/skills/<other-skill>/SKILL.md` — <only if a sibling skill must clear first>.
- `${CLAUDE_PLUGIN_ROOT}/agents/<agent>.md` — <only if this skill dispatches an agent>.

## Phase 1 — <title> · gate: BLOCK

<Imperative description of what this phase does. Terse, no hedging.>

Gate: <a concrete, checkable exit condition>. A partial result does not pass.

## Phase 2 — <title> · gate: BLOCK

<...>

Gate: <...>.

## Phase N — <title> · gate: BLOCK

<Final phase. If the skill ends by persisting, hand off to `commit-gate` — never `git commit` directly.>

Gate: <...>.

## Hard rules

- MUST NOT <invariant, stated once — not duplicated from a phase>.
- MUST NOT <invariant>.
- MUST NOT guess a command — read the cited `.codearbiter/` doc or STOP.

<!--
House-style reminders (delete before shipping):
- Frontmatter is `name:` + `description:` only.
- H1 matches `name`. One-line intro names what routes to it.
- Each non-declarative phase ends in a one-line `Gate:`.
- Paths: project state -> `${CLAUDE_PROJECT_DIR}/.codearbiter/<doc>`;
  skills -> `${CLAUDE_PLUGIN_ROOT}/skills/<name>`;
  agents -> `${CLAUDE_PLUGIN_ROOT}/agents/<name>.md`.
- Surviving project docs only: CONTEXT.md, tech-stack.md, coding-standards.md,
  specs/, plans/, security-controls.md, decisions/, overrides.log.
- Terminology lock: a skill is *routed to*; an agent is *dispatched*.
  Never "trigger", "fires", "runs". No `## Trigger` block.
- Out-of-scope finding -> one line with inline `[NEEDS-TRIAGE]`.
- Terse, imperative. No "should", no "if it looks wrong".
-->
