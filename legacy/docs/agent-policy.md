# Agent Policy — Actions Requiring Explicit Human Approval

Approval = comment from a human listed in CODEOWNERS, in the PR thread, with
the literal text `Approved by <name> for <action>`.

The agent MUST NOT, without approval:

1. Modify locked stack choices (`docs/stack.md`) or trust zones (`docs/architecture/trust-zones.md`). (CM-3)
2. Add a new third-party dependency. (SR-3)
3. Add HashiCorp Terraform anywhere. (License — BSL prohibited)
4. Open a new network egress (any new outbound destination, port, or protocol). (SC-7, AC-4)
5. Write directly to `main` or force-push any branch. (CM-3)
6. Store any raw secret in DB, repo, log, or container image. (IA-5, SC-28)
7. Redefine "node", "adapter", or "solution". (`docs/domain.md`)
8. Modify Drizzle migrations under `backend/drizzle/migrations/` after they have been applied to any environment. (CM-3, SI-7)
9. Issue any production write (DB, K8s, AWS API) — operator-only. (AC-6, CM-3)
10. Modify CI/CD workflows, branch protection, or CODEOWNERS. (CM-3)
11. Modify IAM policies, KMS key policies, or security groups. (AC-6)
12. Modify any file under `backend/audit/` or anything that emits audit events. (AU-9)
13. Modify the schema of `deployment_receipts` or any audit table. (AU-9, SI-7)
14. Generate, modify, or remove cryptographic code (key generation, signing, encryption, KDF, RNG). (SC-12, SC-13)
15. Bypass the conflict-resolution hierarchy in CLAUDE.md §0; surface the conflict instead.
16. Fetch or include data classified CUI or above in any prompt or LLM context. (SC-7, MP-3)
17. Resolve a `[CONFIRM-NN]` placeholder by guessing — surface the question.

## Verification

PR check `agent-policy-check` (Semgrep + custom linter in `tools/agent_policy/`)
plus CODEOWNERS path-based review. CODEOWNERS file at `.github/CODEOWNERS` maps
the protected paths above to required reviewers.
