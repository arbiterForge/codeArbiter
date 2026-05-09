# Data Handling & Classification

System categorization (FIPS 199): **Moderate** for confidentiality, integrity,
availability — pending [CONFIRM-02] in `docs/open-questions.md`.

## Data Classes

| Class | Marking | Encryption at Rest | Encryption in Transit | Allowed Egress |
|---|---|---|---|---|
| Public | none | optional | TLS 1.3 | any |
| Internal | INTERNAL | KMS CMK | TLS 1.3 mTLS [S3+] | within Cove.GDIT |
| CUI | `CUI//SP-PRIV` etc. per [CONFIRM-03] | KMS CMK FIPS | TLS 1.3 mTLS, FIPS suites only | within authorization boundary only |
| Secret reference | SECRET-REF | KMS CMK FIPS | TLS 1.3 mTLS | Z-SECRETS only |

## Rules

- MUST tag every Postgres column carrying CUI or Secret-Ref in `backend/db/classification.py`. Rationale: MP-3, AC-16. Verification: test `test_all_columns_classified`. [S2+]
- MUST NOT send CUI to any external service not on the egress allow-list (`deploy/egress-allowlist.yaml`). (SC-7, AC-4)
- MUST NOT include CUI in agent prompts, telemetry, error messages, or stack traces. (SC-7, MP-3)
- MUST mark CUI per CUI Registry (32 CFR 2002) when displayed in UI. [S3+]
- MUST encrypt all backups with KMS CMK and test restore quarterly [S3+]. (CP-9, CP-10)
