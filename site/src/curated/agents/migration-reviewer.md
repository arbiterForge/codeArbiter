---
entity: agents/migration-reviewer
related: [skills/commit-gate, skills/subagent-driven-development]
---

## Role

Read-only reviewer of database migration files: checks reversibility, data-classification annotation
on sensitive tables, and immutability of already-committed migrations. Dispatched whenever a diff
contains a new or modified migration file — by the `commit-gate` skill's verification phase, and by
`subagent-driven-development` when `backend-author`'s diff touches a migration.

## Why this model tier

Ships `model: inherit`, running at whatever tier the calling gate or author agent already committed —
migration safety review rides on the same reasoning budget as the change it's checking.

## What it emits

CRITICAL–LOW findings with the migration file path, the specific safety or classification gap, and a
remediation. Blocks on an irreversible destructive operation without a linked ADR, a missing
classification annotation on sensitive data, or an edit to an already-merged migration.
