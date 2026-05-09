# Risk Register

| ID | Risk | Severity | Status | Owner | Target Closure | Mitigation |
|---|---|---|---|---|---|---|
| R-01 | Ansible GPLv3 redistribution risk | High | Open | [CONFIRM-04] | Stage 3 | Worker abstraction + swap to Salt/pyinfra/custom OR legal exception |
| R-02 | 3-tier adapter priority is a simplification | Medium | Open | Arch lead | Stage 3 | Replace with Argo native DAG |
| R-03 | Single team is builder + first user | Low | Accepted | Team | n/a | Frustration is QA |
| R-04 | Internal-vs-multi-tenant retrofit cost | Medium | Open | Arch lead | Stage 4 | Data model designed with `tenant_id`-ready isolation |
| R-05 | Worker subprocess sandboxing weak | High | Open | Sec lead | Stage 3 | gVisor or Firecracker isolation; rootless by Stage 2 |
| R-06 | `@xyflow/react` MIT license not contractually guaranteed | Medium | Open | Arch lead | Stage 2 | Document drop-in alternative (plain SVG/D3 canvas); add license-change tripwire to `make license-scan` that hard-fails if `@xyflow/react` license deviates from MIT. Precedent: HashiCorp BSL, Elasticsearch SSPL. |
| R-07 | `audit.emit()` transport semantic mismatch at S2 promotion | High | Open | Arch lead | Stage 2 | S1 HTTP POST is synchronous; NATS JetStream (S2) is at-least-once async — calling code assumes sync semantics today. Define failure-semantics contract as a test assertion before transport swap. [CONFIRM-05] unresolved. |
| R-08 | npm mirror availability in classified/air-gapped target environments | Medium | Open | Arch lead | Stage 3 | Validate against at least one named target customer environment before Stage 3 promotion. Document npm mirror stand-up procedure as a FUSION deployment prerequisite if needed. |

## Review Cadence

Every 4 weeks at architecture sync. Closure recorded in `docs/decisions/`.
