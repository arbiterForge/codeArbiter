# Architectural Decision Records

<!-- ADRs live in this directory. Each file is named NNN-short-title.md where NNN is zero-padded. -->
<!-- Created by the `decision-lifecycle` skill via the /adr command. -->
<!-- Never delete an ADR — superseded ADRs are updated with status: superseded and a pointer to the superseding ADR. -->

## Read-on-invocation guarantee

This README is the surface scan. ADR bodies are read ONLY when an ADR is explicitly referenced by ID (e.g. "ADR-007") or accessed via `/adr-status --adr N`. Routine flows MUST NOT bulk-read this directory.

## Index

| ADR | Title | Status | Date | Last Challenged | Body |
|---|---|---|---|---|---|
| ADR-001 | Ticketing design — in-repo scope-overflow inbox + optional Plane on-prem | proposed | 2026-05-12 | — | [body](001-ticketing-design.md) |

## Status Values

- `proposed` — drafted, not yet accepted
- `accepted` — formally accepted
- `superseded` — replaced by a newer ADR (link provided)
- `rejected` — formally rejected with documented reason
- `deprecated` — no longer applies but kept for historical record
