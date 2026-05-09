# Data Model — Local Postgres

Read-cache + draft state. UI MUST NOT read from Git directly. Promoting a draft
= open PR via Gitea API.

## Tables

```
nodes(id, name, type, version, git_sha, variables_schema,
      execution_worker, valid_connections, criticality,
      teardown_procedure, classification)

adapters(id, name, source_node_type, target_node_type, version,
         git_sha, variables_schema, priority_tier, criticality, classification)

solutions(id, name, version, git_sha, deployment_target, status, classification)

solution_nodes(solution_id, node_id, node_git_sha, position_x, position_y,
               variables_ref)              -- ref to variables, never inline secrets

solution_edges(solution_id, source_node_id, target_node_id, adapter_id,
               adapter_git_sha)

environments(id, name, target_type, variables_schema)

env_variables(env_id, key, value_ref, classification)
                                           -- value_ref points to Secrets Manager
                                           -- raw values PROHIBITED

deployment_receipts(id, solution_id, solution_git_sha, started_at,
                    completed_at, status, snapshot_sha256, snapshot_signature,
                    snapshot_blob_ref, classification)
                                           -- immutable; signed

audit_events(...)                          -- separate DB or sink in Z-AUDIT
```

## Hard Rules

- `env_variables.value_ref` MUST be a Secrets Manager ARN. Raw secrets MUST NOT be inserted; CHECK constraint enforces format. (IA-5, SC-28)
- `deployment_receipts` MUST be immutable. Enforced by Postgres trigger denying UPDATE/DELETE + IAM-restricted role. (AU-9, SI-7)
- `snapshot_blob_ref` points to S3 with object-lock (Compliance mode) [S3+]; SHA-256 stored in row; signature via cosign. (AU-9)
- All migrations via Drizzle (`backend/drizzle/migrations/`); migration files MUST be reviewed by a CODEOWNER. (CM-3)
- Every column carrying CUI or Secret-Ref MUST be tagged in `backend/src/db/schema.ts`. (MP-3, AC-16) [S2+]
