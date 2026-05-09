# Decision Log Index

Append-only. One file per decision. Supersede by adding a new file referencing
the prior one — never edit prior entries.

Format: `NNNN-short-slug.md`. Numbering is monotonic.

## Decisions

- [0001 — Adopt CLAUDE.md contract for `fusion-core`](0001-adopt-claude-md-contract.md)
- [0002 — Adopt `@xyflow/react@12` in place of `reactflow@11`](0002-adopt-xyflow-react-v12.md)
- [0003 — Adopt OCSF-aligned audit event schema with abstract emit interface](0003-adopt-ocsf-audit-schema.md)
- [0004 — Adopt Node.js/TypeScript for the backend (Z-API + Z-WORKER)](0004-adopt-nodejs-typescript-backend.md)

## Review Cadence

This index + every linked ADR MUST be reviewed at every Stage promotion AND
every 12 weeks at minimum. (CM-3, PM-9)
