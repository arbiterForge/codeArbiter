---
description: Author a new codeArbiter skill the only sanctioned way — prove the gap is real, get the spec approved, then write it.
argument-hint: "<verb-noun skill name>"
---

# /ca:new-skill — author a skill

The permitted entry to creating a skill. Nothing is written until the gap is proven uncovered — skills
are not created speculatively. Name the skill in verb-noun form (`"dependency-review"`), not as a
description of what it does (`"the thing that checks packages"`).

## Flow

Routes to the `skill-author` skill — five phases:

1. **Gap confirmation** — prove no existing skill or agent already covers the need, and that this is a
   reusable multi-phase workflow rather than a one-off command. If the gap isn't real, work stops and
   the covering skill is named.
2. **Specification** — draft the `SKILL.md` outline: trigger, purpose, phase list with inputs/outputs/
   gates per phase, which agents it dispatches, which `${CLAUDE_PROJECT_DIR}/.codearbiter/` docs it reads.
3. **User review** — present the spec; do not proceed until the user approves. Changes revise Phase 2.
4. **Authoring** — write `${CLAUDE_PLUGIN_ROOT}/skills/<name>/SKILL.md` and any reference files it needs.
5. **Verification** — read the authored skill back; confirm every referenced gate has a check and
   every `.codearbiter/` doc it reads exists (or is noted as a gap to create).

## Routes to

`skill-author` (`${CLAUDE_PLUGIN_ROOT}/skills/skill-author/SKILL.md`) — all five phases.

## When NOT to use

- A one-time action → `/ca:feature` or a command definition.
- An existing skill nearly covers it → extend that skill via `/ca:feature`.
- "Do we even need a skill here?" → `/ca:btw`.

## Hard gate

MUST prove the gap is real in Phase 1 before writing any skill content. MUST get user approval on the
spec before authoring. MUST NOT create a skill that duplicates an existing skill's purpose — surface
the overlap instead. Skill files live only under `${CLAUDE_PLUGIN_ROOT}/skills/<name>/`.
