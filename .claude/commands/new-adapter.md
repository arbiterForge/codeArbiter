---
description: Scaffold a new FUSION adapter with the typed source--target contract
argument-hint: "<source-node-type> <target-node-type>"
---

Scaffold a new adapter from `${1:?source type required}` to
`${2:?target type required}`.

Before scaffolding:

1. Read `docs/domain.md`.
2. Read `schemas/adapter.schema.json`.
3. Verify both `fusion-nodes/${1}/` and `fusion-nodes/${2}/` exist. If
   either is missing, STOP.
4. Verify the directory `fusion-adapters/${1}--${2}/` does not exist.

Scaffold:

- `fusion-adapters/${1}--${2}/definition.yaml` with: source_type=${1},
  target_type=${2}, version=0.1.0, priority_tier (ASK USER — 1, 2, or 3),
  variables_schema (empty `{}` OK), criticality (ASK USER)
- `fusion-adapters/${1}--${2}/connect.yml` — Ansible play stub
- `fusion-adapters/${1}--${2}/README.md`

NEVER use the term "connector" in any file or commit message. The agent MUST
say "adapter" exclusively.

After scaffolding:

1. Update `fusion-nodes/${1}/definition.yaml` to add `${2}` to
   `valid_connections` (if not already present).
2. Run `make validate-definitions`.
3. Invoke `schema-validator` subagent.
