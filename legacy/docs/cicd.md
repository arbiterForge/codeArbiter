# CI/CD Gates

## Non-Bypass Gates (the agent MUST NOT skip, disable, or `continue-on-error`)

`sast`, `secrets-scan`, `deps-scan`, `license-scan`, `container-scan`, `sbom`,
`validate-definitions`, `fips-check`. (CM-3, CM-5)

## Process Rules

- MUST NOT modify branch protection rules, CODEOWNERS, or `.gitea/workflows/*` without a PR labeled `ci-change` and CODEOWNER review. (CM-3, AC-3)
- MUST NOT merge own PRs. (AC-5, separation of duties)
- MUST NOT push to `main`. All changes via PR. (CM-3)
- MUST NOT deploy to staging without passing CI. MUST NOT deploy to prod without CODEOWNER approval AND a signed release tag [S3+]. (CM-3, AC-6)

## Stage-Gated Test Thresholds

| Gate | Stage 1 | Stage 2 | Stage 3 | Stage 4 |
|---|---|---|---|---|
| Unit coverage | advisory | ≥70% | ≥85% | ≥90% |
| Integration tests | smoke only | per bounded context | full happy + sad paths | + chaos (network partition, secret rotation) |
| SAST | advisory | enforce, no High | enforce, no Medium+ | enforce, no Medium+; weekly full ruleset |
| Secrets scan | enforce | enforce | enforce + history scan | enforce + history scan |
| Dependency scan | advisory | enforce, no High/Critical | enforce, no Medium+; SLA 14d | enforce, no Medium+; SLA 7d |
| Container scan | advisory | enforce, no High/Critical | + STIG hardened base image | + DISA STIG check (OpenSCAP) |
| SBOM | generated | generated + attached to release | + signed | + uploaded to customer |
| DAST (ZAP) | — | baseline weekly | baseline per release | full active scan per release |
| Pen test | — | — | annual | annual + post-major-change |

## Make Targets (full reference)

```bash
make up
make down
make seed
make backend-dev
make backend-test
make backend-lint
make frontend-dev
make frontend-test
make frontend-lint
make validate-definitions
make layout-check
make registry-check
make netpol-check
make sast
make secrets-scan
make deps-scan
make license-scan
make container-scan
make sbom
make sign
make slsa-provenance
make fips-check
make dast
make stig-check
make deploy-stage
make deploy-prod
make teardown SOLUTION=<name>
make ci                  # everything CI runs
make install-hooks       # pre-commit + pre-push hooks
make lockfile-check
make deps-source-check
```

Pre-push hook (installed by `make install-hooks`) refuses to push if local
`make ci` has not passed since the last commit.
