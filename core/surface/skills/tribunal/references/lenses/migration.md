# migration — lens mandate

Executed by `tribunal-lens-reviewer` under the `migration` assignment. Write contract + evidence discipline: `finding-record.md`.

## Scope emphasis
Migration files in the assigned slice, cross-referenced against schema and query code.

## Required reading
- `{{PROJECT_DIR}}/.codearbiter/security-controls.md` — data-classification categories; `{{PROJECT_DIR}}/.codearbiter/tech-stack.md` — ORM/schema conventions.

## Checklist
- Reversibility: rollback/down path present; destructive ops (DROP, TRUNCATE) guarded; NOT NULL added without DEFAULT/backfill; single-step rename that breaks queries mid-deploy.
- Data-classification annotation present for tables holding sensitive data (PII, credentials, payment, audit).
- Immutability: edits to an already-committed migration (schema divergence across environments).
- Index concurrency on large tables; locks that block production traffic.
- Schema-to-code drift, backfill correctness, operation ordering, unguarded destructive operations.

## Exposure
Count of migration files reviewed.

## Out of scope
Application-level data handling (appsec/secrets).
