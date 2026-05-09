# Failure Handling

## User-Facing Failure Classes (engineer prompts)

| Class | Trigger | Options |
|---|---|---|
| Critical-path | T1 adapter or `critical_path` node fails | Full teardown / leave for inspection |
| Non-critical | T2/T3 adapter fails, core healthy | Retry / skip & continue / full teardown |
| Infra | OpenTofu fails before anything provisioned | Retry / abort |

## Security-Relevant Failure Classes (system behavior, NOT user-prompted)

| Class | Trigger | Required Behavior |
|---|---|---|
| AuthN failure | Token invalid/expired | Audit `outcome=failure`, return 401, MUST NOT retry |
| AuthZ denial | RBAC deny | Audit `outcome=denied`, return 403, MUST NOT retry |
| Secret fetch failure | Secrets Manager error | Audit, fail closed, alert (PagerDuty [S3+]) |
| Signature verify failure | cosign / SBOM / receipt | Audit, fail closed, halt deployment, alert |
| Audit emit failure | Z-AUDIT unreachable | Fail request closed [S3+]; degrade to local queue with bounded TTL [S2] |

## Teardown

Every node MUST declare `teardown_procedure`.

- For OpenTofu: `tofu destroy -auto-approve=false` with operator confirmation [S3+].
- For Ansible state-in-instance: node author owns the teardown play.

Verification: `make validate-definitions` rejects nodes without `teardown_procedure`.
