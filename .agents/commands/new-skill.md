# /new-skill "skill name"

## Purpose

Author a new codeArbiter skill through a structured 5-phase process. Invokes the `skill-author` skill. A gap must be confirmed real before any writing begins — skills are not created speculatively.

## Usage

```
/new-skill "skill name"
```

The skill name should describe what the skill does in verb-noun form. Examples: `"dependency-review"`, `"stage-gating"`, `"audit-emit"`. Not: `"the thing that checks packages"`.

## Routes To

`skill-author` skill (`${FRAMEWORK_ROOT}/.agents/skills/skill-author/SKILL.md`) — all 5 phases.

## The 5 Phases

**Phase 1 — Gap Confirmation**
Confirms the skill gap is real:
- Does any existing skill or agent already cover this need?
- Is this a one-time task (better as a command) or a reusable multi-phase workflow (better as a skill)?
- What specific trigger would invoke this skill?
- What would Phase 1 of the new skill produce, and who consumes it?

If the gap is NOT confirmed real: work stops. codeArbiter explains which existing skill covers the need.

**Phase 2 — Skill Specification**
Produces a SKILL.md outline:
- Skill name, trigger, purpose
- Phase list with inputs, outputs, and gates for each phase
- Which agents the skill invokes
- What `${PROJECT_ROOT}/.agents/projectContext/` documents it reads

**Phase 3 — User Review**
Presents the specification to the user. Work does not proceed until the user approves the specification. If the user requests changes, Phase 2 is revised.

**Phase 4 — Authoring**
Writes the skill files:
- `${FRAMEWORK_ROOT}/.agents/skills/<name>/SKILL.md` — full skill definition
- Updates `${FRAMEWORK_ROOT}/.agents/skills/` index if one exists
- Creates any reference files the skill needs (e.g., templates, decision category lists)

**Phase 5 — Verification**
- Reads the authored skill file back to verify it is internally consistent
- Checks that every gate referenced in the skill has a corresponding check described
- Checks that every `${PROJECT_ROOT}/.agents/projectContext/` document the skill reads actually exists (or notes it as a gap to create)

## Hard Gates

- MUST confirm the gap is real in Phase 1 before writing any skill content
- MUST get user approval on the specification (Phase 3) before authoring (Phase 4)
- MUST NOT create a skill that duplicates an existing skill's purpose — surface the overlap instead
- Skill files live in `${FRAMEWORK_ROOT}/.agents/skills/<name>/` — MUST NOT be placed elsewhere

## When NOT to Use

- If the need is a one-time action: use `/feature` or a command definition instead
- If an existing skill covers it: use that skill; suggest extending it via `/feature` if it's missing a phase
- To ask whether a skill is needed: use `/btw`
