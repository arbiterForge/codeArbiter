---
entity: commands/adr
related: [adr-status, reconcile, skills/decision-lifecycle]
gates:
  - gate: user attribution
    when: authoring the ADR content
    effect: context, decision, alternatives, and consequences are confirmed with you directly — an unknown becomes an inline `[CONFIRM-NN]`, never a guess
  - gate: numbering + marker
    when: writing the file
    effect: the next ADR number is fixed with no gap, and a short-lived authoring marker is armed so the write hooks allow the file — `/adr` is the only path that can arm it
---

## What it does

Records an architectural decision as a numbered, dated ADR under `.codearbiter/decisions/`. This is
the only sanctioned way an ADR gets written: the underlying skill drops a 30-minute authoring marker
immediately before the write, and the repo's pre-write/pre-edit hooks refuse to touch a
`.codearbiter/decisions/NNNN-*.md` file without one. Status transitions
(`proposed → accepted → superseded | rejected`) always require your explicit instruction — the
decision never advances on its own.

## Usage

```
/ca:adr "<decision title>"
```

Title the decision as what was decided, not what was considered — `"Use PostgreSQL as the primary
database"`, not `"Database selection"`.

## Example

```text
> /ca:adr "Use PostgreSQL as the primary database"

Indexed 6 existing ADRs under .codearbiter/decisions/ — next number is 0007.

Confirm before I write:
  Context: <you supply/confirm>
  Decision: Use PostgreSQL as the primary database
  Alternatives considered: <you supply/confirm>
  Consequences: <you supply/confirm>

Written: .codearbiter/decisions/0007-use-postgresql-as-the-primary-database.md (status: proposed)
Decision log entry appended — Decided by: dev@example.com
```

## When to reach for it

Recording a decision you've already made. If the question is which option to pick, that's
`/ca:reconcile`; if you just want to know an ADR's health, that's `/ca:adr-status`.
