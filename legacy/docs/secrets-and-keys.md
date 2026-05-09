# Secrets, Identity & Key Management

- MUST source all secrets from AWS Secrets Manager (FIPS endpoint) via IAM instance role / IRSA. Rationale: IA-5, SC-12, SC-28. [S1+]
- MUST NOT write secrets to disk except via tmpfs mount with mode 0400 and process-scoped lifetime. (SC-28)
- MUST NOT log secret values; logger MUST redact via `backend/common/log_redact.py` allow-list of safe fields. (AU-9, AU-11)
- MUST NOT store secrets in env vars of long-lived processes; use short-lived per-request fetch with cache TTL ≤ 5 min. [S2+]
- MUST rotate worker job credentials per deployment (one-time STS token scoped to that deployment's resources). (IA-5(1)) [S2+]
- MUST NOT include secrets in any prompt sent to an LLM (including the agent's own context). Treat the LLM provider as out-of-boundary. (SC-7, AC-21)
- MUST use KMS CMKs (not AWS-managed keys) for all data encryption. (SC-12, SC-28(1)) [S2+]

## `.env` Policy

PERMITTED only for non-sensitive local-dev configuration (ports, log levels). Any
`.env*` file MUST be in `.gitignore` AND scanned by gitleaks. Use of `.env` for
AWS credentials or any secret is PROHIBITED at all stages, including Stage 1.

## Verification

- `make secrets-scan` (gitleaks) on every PR + nightly historical scan
- Pre-commit hook installed by `make install-hooks`
