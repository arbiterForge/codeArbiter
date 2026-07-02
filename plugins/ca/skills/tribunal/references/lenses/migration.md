# migration — lens mandate

Executed by `tribunal-migration-reviewer`. Evidence-or-drop on every check.

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
