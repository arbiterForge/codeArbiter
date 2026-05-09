# Domain Concepts

These three terms have load-bearing meaning. The agent MUST NOT redefine them.

## Node

Self-contained deployable unit. Knows everything about how to deploy itself
except (a) variables provided at deploy time and (b) the target handed to it
by an adapter.

Directory contract:

```
fusion-nodes/<node-name>/
├── definition.yaml       # required
├── main.tf               # if IaC
├── playbook.yml          # if Ansible
├── values.yaml           # if Helm
└── README.md
```

`definition.yaml` MUST declare:
- `variables_schema` — required inputs
- `valid_connections` — node types this can be adapted to
- `criticality` — `critical_path` | `non_critical`
- `teardown_procedure` — how to destroy what was provisioned

## Adapter

Typed A→B integration between two specific node types. NEVER called a
"connector". Carries only what is needed to establish the initial integration
handshake (domain join params, API registration, service account creation, etc.).

Directory:

```
fusion-adapters/<src>--<tgt>/
├── definition.yaml
├── connect.yml
└── README.md
```

`definition.yaml` MUST declare:
- `source_type`
- `target_type`
- `variables_schema`
- `priority_tier` — 1 (infra), 2 (service), 3 (post-integration)

Adapter rules:
- Adapters are typed — `ec2-windows-dc → ec2-ubuntu` is a specific artifact, NOT a generic channel.
- Canvas enforces compatibility at `onConnect` — incompatible node types cannot wire together.
- An edge can have multiple adapters multi-selected.
- 3-tier priority is global across the whole solution deployment (Risk R-02).

## Solution

Canvas of nodes wired by adapters. Tagged `on-prem` | `cloud` | `hybrid`.
MUST pin `git_sha` for every node and adapter at save time.

## Verification

`make validate-definitions` validates every `definition.yaml` against
`schemas/{node,adapter,solution}.schema.json`.
