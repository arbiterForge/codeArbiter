# /adr "title"

## Purpose

Create a new Architecture Decision Record. Invokes the `decision-lifecycle` skill to author the ADR, register it, and queue it for challenge. ADRs document significant architectural decisions with context, alternatives considered, and the rationale for the chosen path.

## Usage

```
/adr "title of the decision"
```

The title should name the decision clearly: what was decided, not what was considered. Example: `"Use PostgreSQL as the primary database"` not `"Database selection"`.

## Routes To

`decision-lifecycle` skill (`.agents/skills/decision-lifecycle/SKILL.md`).

## What Happens Step by Step

1. `decision-lifecycle` skill opens — collects context from the user:
   - What decision needs to be made or was just made?
   - What context forced this decision?
   - What alternatives were considered?
   - What are the consequences?
2. ADR file created at `projectContext/decisions/000N-<slugified-title>.md` with frontmatter:
   ```yaml
   status: proposed
   date: YYYY-MM-DD
   title: <title>
   ```
3. ADR body authored with sections: Context, Decision, Alternatives considered, Consequences, Risks
4. ADR registered in `projectContext/decisions/README.md` — index entry added
5. ADR queued for challenge — `decision-challenger` agent is notified at next `/checkpoint`
6. Any `[CONFIRM-NN]` placeholders left open are registered in `projectContext/open-questions.md`

## ADR File Structure

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

## Hard Gates

- MUST NOT resolve any `[CONFIRM-NN]` placeholder by guessing — surface the question and stop
- ADR numbering MUST be sequential — check `projectContext/decisions/README.md` for the next number
- If an ADR contradicts an existing accepted ADR: invoke `/surface-conflict` before proceeding
- ADR status starts at `proposed` — only the user can advance it to `accepted` or `superseded`

## ADR Status Lifecycle

```
proposed → accepted → (optionally) superseded
         → rejected
```

Status transitions require user confirmation. codeArbiter does not advance ADR status without explicit user instruction.

## When NOT to Use

- To check the health of existing ADRs: use `/adr-status`
- To challenge an existing ADR: use `/checkpoint` (which invokes `decision-challenger`)
- To ask about an architectural decision without recording it: use `/btw`
