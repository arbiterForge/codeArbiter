# Tech Stack — Pinned

All MAJOR versions pinned. Minor/patch via Renovate; auto-merge only for patch + passing CI.

Decision: ADR-0004 (`docs/decisions/0004-adopt-nodejs-typescript-backend.md`) — Node.js/TypeScript
is used for both frontend and backend. Python is no longer in the application stack.

| Layer | Choice | Pinned Major | License | FIPS Posture |
|---|---|---|---|---|
| OS (containers) | Red Hat UBI9 FIPS | 9.x | Proprietary (free redistribution) | FIPS 140-3 validated OpenSSL provider |
| Node runtime | Node.js 22 LTS | 22 | MIT | Uses system OpenSSL FIPS provider (UBI9 FIPS build) |
| Frontend | React + React Flow | React 18, @xyflow/react 12 | MIT | n/a (TLS only in browser) |
| Backend API | Fastify | 5.x | MIT | Per-route Zod validation for all I/O |
| API Validation | Zod | 3.x | MIT | Shared with frontend; schema → TS type in one step |
| ORM | Drizzle ORM | 0.x | Apache 2.0 | SQL-first, TypeScript-native migrations |
| Auth token verify | jose | 5.x | MIT | JOSE/JWK; FIPS-compatible via system OpenSSL |
| Job execution | child_process.spawn (shell:false) + ansible-playbook [S1–S2]; Argo [S3+] | ansible-core 2.17; argo 3.5 | Apache 2.0 / GPLv3 (R-01) | — |
| IaC | OpenTofu | 1.8 | MPL 2.0 | — |
| Config Mgmt | Ansible-core | 2.17 | GPLv3 (RISK R-01) | — |
| K8s app deploy | Helm | 3.15 | Apache 2.0 | — |
| VM first-boot | cloud-init | 24.x | Apache 2.0 / GPLv3 dual | — |
| K8s | K3s | v1.30 | Apache 2.0 | — |
| Source control | Gitea (self-hosted on K3s) | 1.22 | MIT | — |
| Database | PostgreSQL | 16 | PostgreSQL License | EBS encryption with KMS CMK |
| Crypto provider | OpenSSL via UBI9 FIPS provider | 3.0 FIPS | Apache 2.0 | **FIPS 140-3 Cert #4985** |
| Secrets | AWS Secrets Manager (FIPS endpoint) | — | — | FIPS 140-3 |
| AuthN | OIDC (provider per [CONFIRM-01]) | — | — | — |

## Hard Stack Rules

- MUST NOT introduce HashiCorp Terraform anywhere. Rationale: BSL. Verification: `make license-scan` denies `hashicorp/terraform`. (SR-3)
- MUST NOT use any cryptographic primitive outside the system FIPS provider. Rationale: SC-13. Verification: `make fips-check`.
- MUST NOT introduce a paid third-party license. Rationale: budget + redistribution risk.
- MUST pin all dependencies (lockfiles committed: `package-lock.json` for all packages). Rationale: CM-2, SR-4. Verification: `make lockfile-check`.
- MUST NOT call `child_process.exec()` or `spawn()` with `shell: true`. Rationale: SI-10 (command injection). Verification: Semgrep rule `javascript.lang.security.audit.dangerous-spawn-shell`.

## Cryptographic Algorithm Allow-List (FIPS 140-3)

Approved: AES-256-GCM, AES-256-CBC + HMAC-SHA-384, RSA-3072+, ECDSA P-256/P-384, SHA-256/384/512, HKDF-SHA-384.

Prohibited: MD5, SHA-1, RC4, 3DES, any non-FIPS curve.

## FIPS Node.js Configuration Note

The Node.js 22 container image MUST be sourced from Red Hat UBI9 or built from
source with `--openssl-fips` to ensure the FIPS 140-3 validated OpenSSL provider
is active. Verify at runtime: `node -e "require('crypto').getFips()"` MUST return `1`.
