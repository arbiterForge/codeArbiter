# Open Confirmations

The agent MUST NOT guess answers to these. When a task touches one, surface
the `[CONFIRM-NN]` ID and stop.

| ID | Question | Blocks |
|---|---|---|
| CONFIRM-01 | OIDC provider for Stage 1–2: GDIT SSO, self-hosted Keycloak, AWS Cognito, or other? | `docs/stack.md`, `docs/security-controls.md` |
| CONFIRM-02 | FIPS 199 categorization — confirm Moderate/Moderate/Moderate for FUSION control plane. | `docs/data-classification.md` |
| CONFIRM-03 | Specific CUI categories in scope (e.g., `CUI//SP-PRVCY`, `CUI//SP-CTI`). | `docs/data-classification.md` markings |
| CONFIRM-04 | Owner for R-01 (Ansible GPLv3 risk). | `docs/risks.md` |
| CONFIRM-05 | Audit sink technology (CloudWatch Logs + KMS + S3 object-lock? Splunk? Elastic with WORM?). | `docs/audit-spec.md` retention/integrity |
| CONFIRM-06 | Authorization boundary — does Cove.GDIT count as a single boundary, or are sub-VPCs separate? | `docs/architecture/trust-zones.md`, `docs/data-classification.md` egress |
| CONFIRM-07 | Private container registry choice for Stage 3+ mirroring (ECR? Harbor on K3s?). | `docs/dependency-policy.md` |
| CONFIRM-08 | Does NIST AI RMF apply? (Is the AI in the deploy path, or strictly the dev-time coding agent?) | Whether to add `docs/ai-governance.md` |
| CONFIRM-09 | Stage promotion authority — who signs off Stage 1→2, 2→3, 3→4. | CLAUDE.md §1 |
| CONFIRM-10 | Production deployment topology — Stage 3 and Stage 4 HA targets. | `docs/architecture/trust-zones.md` |
