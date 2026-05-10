---
description: Scaffold a new FUSION node with full definition.yaml contract
argument-hint: "<node-name> e.g. ec2-windows-dc"
---

Scaffold a new node `${1:?node name required}` in `fusion-nodes/${1}/`.

Before scaffolding:

1. Read `docs/domain.md` in full.
2. Read `schemas/node.schema.json` in full.
3. Confirm `${1}` does not already exist in `fusion-nodes/`. If it does, STOP.

Scaffold these files (placeholders OK, but `definition.yaml` MUST validate):

- `fusion-nodes/${1}/definition.yaml` — populated with: name, type, version=0.1.0, criticality (ASK USER, do not guess), variables_schema (empty `{}` is OK to start), valid_connections (empty `[]` is OK to start), teardown_procedure (REQUIRED — for IaC nodes use `tofu destroy`), execution_worker (`ansible` for current stage)
- `fusion-nodes/${1}/main.tf` — empty stub with comment
- `fusion-nodes/${1}/playbook.yml` — empty stub with comment
- `fusion-nodes/${1}/README.md` — name, purpose, variables, valid_connections

After scaffolding:

1. Run `make validate-definitions` against the new file. If it fails, FIX the
   `definition.yaml` and re-run. Do not commit a failing definition.
2. Invoke the `schema-validator` subagent to review the new node.
3. Report the diff and the next step (CODEOWNER review).

MUST NOT scaffold the node inside `fusion-core/`. Nodes live in
`fusion-nodes/`. If running this command from inside `fusion-core/`, refuse
and tell the user to switch repos.
