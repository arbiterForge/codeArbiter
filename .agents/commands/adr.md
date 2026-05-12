# /adr "title"

## Purpose

Create a new Architecture Decision Record. Invokes the `decision-lifecycle` skill to author the ADR, register it, and queue it for challenge.

## Usage

```
/adr "title of the decision"
```

Title should name the decision clearly: what was decided, not what was considered. Example: `"Use PostgreSQL as the primary database"` not `"Database selection"`.

## Routes To

`decision-lifecycle` skill (`${FRAMEWORK_ROOT}/.agents/skills/decision-lifecycle/SKILL.md`).

## Command-owned mechanics

**Authoring marker (H-11).** Before invoking the skill, run:

```
mkdir -p ${FRAMEWORK_ROOT}/.agents/.markers && touch ${FRAMEWORK_ROOT}/.agents/.markers/adr-authoring-active
```

The H-11 PreToolUse hook (`${FRAMEWORK_ROOT}/.agents/hooks/pre-write.sh`, `${FRAMEWORK_ROOT}/.agents/hooks/pre-edit.sh`) blocks Writes and Edits to `${PROJECT_ROOT}/.agents/projectContext/decisions/*.md` unless this marker is present and fresh (modified within the last 30 minutes).

After the skill completes Step 7 (or if `/adr` aborts), remove the marker:

```
rm -f ${FRAMEWORK_ROOT}/.agents/.markers/adr-authoring-active
```

If the command aborts midway, the marker may persist until cleaned up or ages out.

**ADR file path.** Created at `${PROJECT_ROOT}/.agents/projectContext/decisions/000N-<slugified-title>.md` with sequential numbering — check `${PROJECT_ROOT}/.agents/projectContext/decisions/README.md` for the next number.

**ADR file template.**

```markdown
---
status: proposed
date: YYYY-MM-DD
title: <title>
---

# ADR-NNNN — <title>

## Status

Proposed

## Context

<What situation, constraint, or requirement prompted this decision?>

## Decision

<What was decided? One clear statement.>

## Alternatives considered

- **<Option A>** — <why it was not chosen>
- **<Option B>** — <why it was not chosen>

## Consequences

<What becomes easier or harder as a result of this decision?>

## Risks

<What could go wrong? What would prove this decision wrong?>

## [CONFIRM-NN] placeholders

<List any open questions that need resolution before this ADR can move to "accepted">
```

**Status lifecycle.** `proposed → accepted → (optionally) superseded` or `→ rejected`. Status transitions require explicit user instruction — codeArbiter does not advance ADR status on its own.

## When NOT to Use

- Check health of existing ADRs: `/adr-status`
- Challenge an existing ADR: `/checkpoint` (invokes `decision-challenger`)
- Ask about a decision without recording it: `/btw`
