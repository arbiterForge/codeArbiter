# Canonical ADR template

The single source of truth for the shape of an Architecture Decision Record under
`<project-root>/.codearbiter/decisions/`. Both `decision-lifecycle` (via `/adr`) and
`decompose` (Layer 4 DRAFT ADRs) author to this exact format, so `/adr-status` and the
`governs:` post-write hook parse every ADR the same way regardless of who wrote it.

## Filename

`NNNN-<slug>.md` — a zero-padded 4-digit sequential number with no gaps (`0001-…`, `0002-…`),
numbered across the existing `decisions/` directory.

**The filename stem is the ADR's identifier** — `0014-githook-shim-dropin-fail-closed`, not
`0014`. The number alone is a sort key, not a name: this repository already holds two ADRs
numbered 0014, so `supersedes: 0014` named two documents at once until it was disambiguated.
Reference an ADR by its full stem everywhere a machine reads it.

## File format

```markdown
---
status: proposed
date: YYYY-MM-DD
title: <title>
decided-by: <user identifier>
supersedes: NNNN-<slug> | none
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
- **`accepted` means Accepted/Planned.** It records an approved governance decision and does not imply
  implementation. Implemented and Verified are derived delivery states from the separate append-only
  `adr-lifecycle.jsonl`; they are never written into ADR frontmatter. After acceptance, the decision
  record is immutable except for the recognized, agreeing status value in the strictly parsed
  frontmatter `status:` field and `## Status` section. Approval attribution and all other Status prose
  remain bound with title, date, `decided-by`, supersession, governed paths, H1, and every other
  section. A later explicit status transition changes only those recognized status values.
- **`decided-by:`** names the user who made the decision — real attribution, never inferred.
- **`supersedes:`** names the prior ADR's full filename stem — `supersedes:
  0014-githook-shim-dropin-fail-closed`, not `supersedes: 0014` — or `none`. A bare number is
  still accepted for the legacy records that carry one, but ONLY while it names exactly one
  ADR; once a number is shared it is an error, not a guess, and
  this repository's own CI fails the build (the identity check is CI-only and is
  not shipped, so a consumer enforces this rule by review rather than by script). Supersession is a forward-only
  chain: set it on the new ADR; never edit the prior ADR to add a back-reference.
- **`supersedes:` cannot say WHICH CLAUSE it supersedes.** A partial supersession — the new ADR
  replaces some clauses of the prior one and leaves the rest in force — must say so in prose, and
  a chain may legitimately fork when two ADRs supersede different clauses of one predecessor.
  The frontmatter records only *which document*; the body records *how much of it*.
- **`governs:`** (optional) lists fnmatch-style, repo-relative forward-slash path globs. When present,
  the post-write hook surfaces a "governed by ADR-NNNN" notice on any Write/Edit touching a matching
  file. Omit it for decisions without a file footprint.
