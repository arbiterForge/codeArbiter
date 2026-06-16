# Canonical ADR template

The single source of truth for the shape of an Architecture Decision Record under
`${CLAUDE_PROJECT_DIR}/.codearbiter/decisions/`. Both `decision-lifecycle` (via `/adr`) and
`decompose` (Layer 4 DRAFT ADRs) author to this exact format, so `/adr-status` and the
`governs:` post-write hook parse every ADR the same way regardless of who wrote it.

## Filename

`NNNN-<slug>.md` — a zero-padded 4-digit sequential number with no gaps (`0001-…`, `0002-…`),
numbered across the existing `decisions/` directory.

## File format

```markdown
---
status: proposed
date: YYYY-MM-DD
title: <title>
decided-by: <user identifier>
supersedes: NNNN | none
governs: <optional, comma-separated path globs this decision constrains — e.g. src/auth/*, config/tls/*>
---

# ADR-NNNN — <title>

## Status
<Proposed | Accepted | Superseded | Rejected | Draft>

## Context
<What situation, constraint, or requirement prompted this decision?>

## Decision
<What was decided. One clear statement.>

## Alternatives considered
- **<Option A>** — <why not chosen>
- **<Option B>** — <why not chosen>

## Consequences
<What becomes easier or harder as a result.>

## Risks
<What could go wrong; what would prove this decision wrong.>
```

## Field & status semantics

- **`status:` (frontmatter) is authoritative** — `/adr-status` reads it. The `## Status` body line
  mirrors it for human readers. Keep the two in agreement.
- **Status lifecycle:** `proposed → accepted → superseded | rejected`. `decompose` authors Layer 4
  ADRs as **`status: draft`** during the interview and promotes each to `status: accepted` at its
  Phase 5 (a frontmatter `status:` edit only — never a body rewrite). Status transitions otherwise
  require explicit user instruction; never advance status on the skill's own judgment.
- **`decided-by:`** names the user who made the decision — real attribution, never inferred.
- **`supersedes:`** names the prior ADR's number (or `none`). Supersession is a forward-only chain:
  set it on the new ADR; never edit the prior ADR to add a back-reference.
- **`governs:`** (optional) lists fnmatch-style, repo-relative forward-slash path globs. When present,
  the post-write hook surfaces a "governed by ADR-NNNN" notice on any Write/Edit touching a matching
  file. Omit it for decisions without a file footprint.
