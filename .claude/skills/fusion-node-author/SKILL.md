# Fusion Node Author Skill

## Identity
Claude IS a FUSION node construction authority who treats definition correctness and audit wiring as non-negotiable prerequisites for any node scaffold.

## Trigger
- Creating a new FUSION node (a self-contained deployable unit).
- Modifying an existing node's `definition.yaml`.
- Reviewing a node scaffold for completeness.
- When `/new-node` command is invoked.

## Phases

### Phase 1 — Pre-Flight
Read `docs/domain.md`. Verify the proposed node name does not conflict with existing nodes in `fusion-nodes/` or reserved vocabulary in `docs/domain.md`. Verify the target location is `fusion-nodes/<name>/` — MUST NOT scaffold inside `fusion-core/`. If location or name is wrong, BLOCK before any files are written.

**Gate:** Name is valid. Location is `fusion-nodes/`. `docs/domain.md` read in current session.

### Phase 2 — Definition Authoring
Construct `definition.yaml`. Required fields (MUST all be present):
- `name`: slug, lowercase, hyphenated
- `version`: semver
- `criticality`: MUST ask the user — never guess. Valid values: `low`, `medium`, `high`, `critical`.
- `teardown_procedure`: MUST be non-empty. Describe the teardown steps explicitly.
- Any credential fields MUST have `sensitive: true` and use the `_ref` suffix (e.g., `api_key_ref`).

MUST ask the user for `criticality` before writing the file. Do not proceed if criticality is unknown.

**Gate:** All required fields present. `criticality` confirmed by user. `teardown_procedure` non-empty. All credential fields have `sensitive: true` and `_ref` suffix.

### Phase 3 — Schema Validation Gate
Run `make validate-definitions`. Invoke the `schema-validator` agent to independently validate the `definition.yaml`. BLOCK on any schema error. Do not proceed until both the make target and the agent return clean.

**Gate:** `make validate-definitions` exits 0. schema-validator agent returns no errors.

### Phase 4 — TDD Integration
If the node has a backend integration point (API endpoint, database interaction, service call), invoke fusion-tdd skill for that integration. The node is not complete until the TDD skill Phase 1 obligation checklist is produced. If no backend integration point exists, document why and proceed.

**Gate:** fusion-tdd skill invoked (if applicable). Obligation checklist produced or absence documented.

### Phase 5 — Audit Wiring
Verify that `deploy.solution` and `teardown.solution` lifecycle events will emit audit events. These are auditable actions and MUST have emit() calls with correct fields. Route to fusion-audit-emit skill Phase 5 for test obligation verification.

**Gate:** Audit emits planned for deploy and teardown. fusion-audit-emit skill Phase 5 complete.

### Phase 6 — CODEOWNER Gate
New node types require a CODEOWNER approval comment before merge. Add a comment in the PR: `CODEOWNER-REQUIRED: new node type — [node-name]`.

**Gate:** CODEOWNER approval comment present.

## Decision Gates

| Gate | Condition | Action |
|---|---|---|
| Wrong location | Node scaffolded in fusion-core/ or wrong dir | BLOCK |
| Missing required field | Any of name/version/criticality/teardown absent | BLOCK |
| Criticality guessed | criticality not confirmed by user | BLOCK |
| Schema invalid | make validate-definitions fails | BLOCK |
| No audit wiring | deploy/teardown missing audit emits | BLOCK |
| No CODEOWNER comment | New node type, no approval comment | FLAG — require before merge |

## Hard Rules
- MUST NOT scaffold a node inside `fusion-core/`.
- MUST NOT guess `criticality` — always ask the user.
- MUST NOT write `definition.yaml` with an empty `teardown_procedure`.
- MUST NOT use the word "connector" — see `docs/domain.md`.
- MUST NOT mark complete without schema validation passing.

## Reference: Directory Layout

```
fusion-nodes/<node-name>/
├── definition.yaml       # REQUIRED
├── main.tf               # if IaC
├── playbook.yml          # if Ansible config
├── values.yaml           # if Helm
└── README.md             # REQUIRED
```

Naming: kebab-case, descriptive of what is deployed. Examples: `ec2-windows-dc`, `ec2-ubuntu`, `k3s-cluster`, `helm-opencti`.

## Reference: Mandatory definition.yaml Fields

```yaml
name: ec2-windows-dc
type: ec2-windows-dc                    # MUST match directory name
version: 0.1.0                          # SemVer
execution_worker: ansible               # ansible (S1-S2) | argo (S3+)

variables_schema:                        # JSON Schema fragment
  type: object
  required: [domain_name, admin_password_ref]
  properties:
    domain_name:
      type: string
      pattern: "^[a-z0-9.-]+$"
    admin_password_ref:                  # SECRET — uses _ref suffix
      type: string
      pattern: "^arn:aws:secretsmanager:"
      sensitive: true                    # MUST be set on any credential

valid_connections:                       # node TYPES this can adapt to
  - ec2-ubuntu
  - ec2-windows-endpoint

criticality: critical_path               # critical_path | non_critical

teardown_procedure:                      # REQUIRED — never empty
  type: tofu
  command: tofu destroy -auto-approve=false
```

## Reference: Teardown Procedures by Type

- **OpenTofu nodes:** `tofu destroy -auto-approve=false`. Operator confirmation required at S3+. Idempotent.
- **Ansible-configured state inside an instance:** the node author owns a `teardown.yml` playbook that undoes whatever `playbook.yml` did. Cleanup MUST be idempotent (running twice MUST NOT error).
- **Helm releases:** `helm uninstall <release>` plus deletion of any external resources (PVCs that don't have `helm.sh/resource-policy: keep`).
- **K3s installs:** `/usr/local/bin/k3s-uninstall.sh` (or `k3s-agent-uninstall.sh` for workers).

## Reference: Variables vs. Targets

- **Variables** are inputs from the engineer at deploy time (filled via the canvas pre-flight prompt). Defined in `variables_schema`.
- **Targets** are passed in by an adapter at runtime — IP addresses, hostnames, credentials of the connected node. The node MUST NOT hardcode target details. Read them from environment variables `FUSION_TARGET_<TYPE>_<FIELD>` injected by the orchestrator.

## Reference: Validation Commands

```bash
# Validates this one node:
make validate-definitions FILE=fusion-nodes/<name>/definition.yaml

# Validates everything:
make validate-definitions
```

After validation passes, invoke the `schema-validator` subagent — it catches the rules JSON Schema cannot express.

## See Also

- `docs/domain.md` — load-bearing definitions
- `schemas/node.schema.json` — the formal contract
- `docs/failure-handling.md` — how `criticality` drives behavior
- `.claude/commands/new-node.md` — `/new-node <name>` to scaffold
