---
name: fusion-node-author
description: Use whenever creating, modifying, or reviewing a FUSION node — the self-contained deployable unit defined by definition.yaml, main.tf, playbook.yml, and values.yaml. Covers the directory contract, the four mandatory definition fields, teardown procedures, and validation.
---

# Authoring a FUSION Node

A node is self-contained. It knows everything about how to deploy itself
except (a) variables provided at deploy time and (b) the target handed to it
by an adapter. Get this contract wrong and the canvas can't compose your node.

## Directory Layout (exact)

```
fusion-nodes/<node-name>/
├── definition.yaml       # REQUIRED
├── main.tf               # if IaC
├── playbook.yml          # if Ansible config
├── values.yaml           # if Helm
└── README.md             # REQUIRED
```

Naming: kebab-case, descriptive of what is deployed. Examples:
`ec2-windows-dc`, `ec2-ubuntu`, `k3s-cluster`, `helm-opencti`.

## Mandatory `definition.yaml` Fields

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
  # OR for Ansible-only:
  # type: ansible
  # playbook: teardown.yml
```

## The Four Hard Rules

1. `criticality` is exactly `critical_path` or `non_critical`. No other values. Drives failure-handling behavior — getting it wrong corrupts the engineer's prompts.
2. `teardown_procedure` is REQUIRED. The MVP allows leak-on-failure, the production stages do not. Always declare it now.
3. Every variable holding a credential MUST have `sensitive: true` AND a name ending in `_ref` AND a pattern matching the Secrets Manager ARN format. The agent MUST NOT accept raw secret values as inputs.
4. `valid_connections` MUST list types that exist in `fusion-nodes/`. Floating refs are caught at validation time.

## Teardown Procedures by Type

- **OpenTofu nodes:** `tofu destroy -auto-approve=false`. Operator confirmation required at S3+. Idempotent.
- **Ansible-configured state inside an instance:** the node author owns a `teardown.yml` playbook that undoes whatever `playbook.yml` did. Cleanup MUST be idempotent (running twice MUST NOT error).
- **Helm releases:** `helm uninstall <release>` plus deletion of any external resources (PVCs that don't have `helm.sh/resource-policy: keep`).
- **K3s installs:** `/usr/local/bin/k3s-uninstall.sh` (or `k3s-agent-uninstall.sh` for workers).

## Variables vs. Targets

- **Variables** are inputs from the engineer at deploy time (filled via the canvas pre-flight prompt). Defined in `variables_schema`.
- **Targets** are passed in by an adapter at runtime — IP addresses, hostnames, credentials of the *connected* node. Your node MUST NOT hardcode target details. Read them from environment variables `FUSION_TARGET_<TYPE>_<FIELD>` injected by the orchestrator.

## What NOT to Do

- Do NOT call this thing a "connector" — that's an adapter. Different concept.
- Do NOT bake variable defaults that look like real secrets into the schema.
- Do NOT skip `teardown_procedure` because "we'll add it later."
- Do NOT inline a node `definition.yaml` into `fusion-core/`. Nodes live in `fusion-nodes/`.
- Do NOT add a node type that overlaps with an existing one. Search first.
- Do NOT write a node with execution_worker `argo` while `.fusion/stage` is 1 or 2.

## Validation

```bash
# Validates this one node:
make validate-definitions FILE=fusion-nodes/<name>/definition.yaml

# Validates everything:
make validate-definitions
```

After validation passes, invoke the `schema-validator` subagent — it catches
the rules JSON Schema can't express.

## See Also

- `docs/domain.md` — load-bearing definitions
- `schemas/node.schema.json` — the formal contract
- `docs/failure-handling.md` — how `criticality` drives behavior
- `.claude/commands/new-node.md` — `/new-node <name>` to scaffold
