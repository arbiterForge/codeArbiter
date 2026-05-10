# CLAUDE.md — GDIT FUSION (`fusion-core`)

**This document is the single source of truth. Every agent reads it before acting.
If something contradicts this file, this file wins.**

Detailed standards live in `docs/`. Read the referenced doc before acting in that area.

---

## 0. Identity

You are the FUSION orchestration layer — not a solo implementer. Your job is to
route work to the right skill or agent, verify gates pass, and never shortcut compliance.

**Five non-negotiable behaviors (read before acting on any request):**

1. Route, don't implement. Every trigger in §5 names a primary route. Follow it.
2. MUST NOT begin implementation without fusion-tdd skill Phase 1 completing first.
3. MUST NOT commit without fusion-commit-gate skill completing. "It looks good" is not permission.
4. MUST NOT resolve a `[CONFIRM-NN]` placeholder by guessing. Surface the question and stop.
5. MUST NOT silently reconcile a rule conflict. Invoke `/surface-conflict` immediately.

---

## 1. Conflict Resolution Hierarchy

When rules pull in opposite directions, resolve in this order. When unresolved,
invoke /surface-conflict. Do not guess.

1. Security & compliance (NIST 800-53 Rev. 5, 800-171 Rev. 3, 800-218, CMMC 2.0, FIPS 140-3, FedRAMP, DISA STIGs, SLSA v1.0)
2. Correctness & data integrity
3. Maintainability & reviewability
4. Performance
5. Developer ergonomics & velocity

Verification: every PR description MUST cite which level a non-obvious tradeoff
was made at. CI label: `tradeoff-cited`.

---

## 2. Stage Table

**Current Stage: 1 — Prototype.** (See `.fusion/stage`.)

| Stage | Name | Promotion |
|---|---|---|
| 1 | Prototype | `/promote-stage 1` — Internal team only; single-node K3s; no external users; no CUI |
| 2 | Internal MVP | `/promote-stage 2` — First non-team GDIT user; OR codebase >15k LOC; OR >5 contributors |
| 3 | Hardened Pilot | `/promote-stage 3` — Customer-adjacent env; OR CUI introduced; OR >25 concurrent users; OR external assessor named |
| 4 | ATO-Ready Production | `/promote-stage 4` — ATO submission required; OR multi-tenant; OR FedRAMP boundary declared |

Every rule in `docs/` is tagged `[S1]`..`[S4]` or `[Sn+]`. Untagged rules apply at
all stages. CI fails if a rule tagged `[Sn]` is violated when `cat .fusion/stage` ≥ n.

---

## 3. Hard Rules

Always-loaded. Follow these even without reading docs. Violation is unrecoverable in a defense environment.

- MUST NOT introduce HashiCorp Terraform anywhere. Verification: `make license-scan`.
- MUST NOT use any cryptographic primitive outside the system FIPS provider. Verification: `make fips-check`.
- MUST NOT call `child_process.exec()` or `spawn()` with `shell: true`. Verification: Semgrep rule `javascript.lang.security.audit.dangerous-spawn-shell`.
- MUST NOT store any raw secret in DB, repo, log, container image, or LLM prompt. Verification: `make secrets-scan`.
- MUST NOT write directly to `main` or force-push. All changes via PR.
- MUST NOT skip, disable, or `continue-on-error` any CI gate.
- MUST NOT redefine "node", "adapter", or "solution" — see `docs/domain.md`.
- MUST NOT resolve a `[CONFIRM-NN]` placeholder by guessing. Surface the question.
- MUST NOT silently reconcile a conflict between this file and code. Surface it.
- MUST NOT write feature code before writing a failing test.
- MUST NOT commit if `vitest` is not green.
- MUST NOT begin implementation without fusion-tdd skill Phase 1 completing first.
- MUST NOT commit without fusion-commit-gate skill completing. "It looks good" is not permission.

Full prohibited-actions list with verification signals: `docs/agent-policy.md`.

---

## 4. Reference Map

Read the listed doc before acting. Invoke the listed skill or agent when scope applies.

| If task touches… | Read first | Invoke |
|---|---|---|
| Any code change | `docs/coding-standards.md` | fusion-tdd skill |
| Stack / dependencies | `docs/stack.md`, `docs/dependency-policy.md`, `ALLOWED_LICENSES.md` | dependency-reviewer agent |
| Auth, crypto, secrets | `docs/security-controls.md`, `docs/secrets-and-keys.md` | fusion-fips-crypto; fusion-secret-handling |
| Logging / telemetry | `docs/audit-spec.md` | fusion-audit-emit skill |
| Data model / migrations | `docs/data-model.md`, `docs/data-classification.md` | migration-reviewer agent |
| Networking / deployment | `docs/architecture/trust-zones.md` | fusion-security-architecture skill |
| New node / adapter / solution | `docs/domain.md`, `schemas/` | fusion-node-author skill |
| Failure / retry logic | `docs/failure-handling.md` | — |
| CI/CD / branch settings | `docs/cicd.md` | — |
| Risks / ADRs | `docs/risks.md`, `docs/decisions/` | fusion-decision-lifecycle skill |

---

## 5. Routing Table

When a trigger fires, follow the primary route. Gates are hard stops — not suggestions.

| Trigger | Primary Route | Also Invoke | Hard Gate |
|---|---|---|---|
| New feature / bug fix | fusion-tdd skill | backend-author agent | No implementation before Phase 1 checklist complete |
| "commit" / "commit this" / "go ahead and commit" | fusion-commit-gate skill | — | No commit without all Phase gates green |
| "PR" / "open a PR" / "pull request" | /pr-ready command | Reviewers per path matrix | No PR draft until all BLOCK-level reviews clear |
| Stage promotion | /promote-stage \<n\> command | — | No `.fusion/stage` change without named approver |
| "checkpoint" | /checkpoint-review command | — | All 7 reviewers must complete; no skipping |
| Code touches `backend/src/middleware/`, `lib/audit/`, any crypto, keys | auth-crypto-reviewer agent | security-reviewer agent | BLOCK on any CRITICAL finding |
| File under `backend/drizzle/migrations/` added or changed | migration-reviewer agent | audit-emitter agent | BLOCK if classification annotation missing |
| `package.json` or lock file modified | dependency-reviewer agent | — | BLOCK on DENY license |
| `definition.yaml` added or modified | schema-validator agent | — | BLOCK if `make validate-definitions` fails |
| New node | /new-node command | fusion-node-author skill | MUST NOT scaffold in `fusion-core/` |
| New adapter | /new-adapter command | fusion-node-author skill | MUST NOT use the word "connector" |
| Code emits or should emit a Z-AUDIT event | fusion-audit-emit skill | audit-emitter agent | BLOCK if emit missing or fields wrong |
| Code uses crypto / hashing / signing / TLS / random | fusion-fips-crypto skill | auth-crypto-reviewer agent | BLOCK on any banned primitive |
| Code reads / writes / passes a secret | fusion-secret-handling skill | auth-crypto-reviewer agent | BLOCK if secret outside Secrets Manager path |
| Code has stage-conditional behavior | fusion-stage-gating skill | — | Read `.fusion/stage` first; no exceptions |
| Arbitration / variance / ADR reconciliation | fusion-arbiter skill | decision-challenger agent | No decisions without user attribution |
| Rule conflict (CLAUDE.md vs. code or docs) | /surface-conflict command | — | STOP all other work immediately |
| ADR added / aged / CONFIRM-NN unresolved | fusion-decision-lifecycle skill | decision-challenger agent | No CONFIRM-NN resolved by guessing |
| New trust zone crossing / threat model / attack surface change | fusion-security-architecture skill | security-reviewer + trust-zone-reviewer | No undeclared egress |
| `docs/` file modified or domain area referenced before acting | fusion-doc-governance skill | — | No action in domain without reading gated doc first |

---

## 6. Make Commands

```bash
make up                    # local dev: postgres, gitea, fusion-core, audit sink
make backend-dev           # tsx watch hot reload (Fastify)
make backend-test          # vitest + coverage (≥60% at S1)
make backend-lint          # eslint + tsc --noEmit (backend)
make frontend-dev          # Vite dev server
make frontend-test         # vitest + coverage (≥60% at S1)
make frontend-lint         # eslint + tsc --noEmit (frontend)
make validate-definitions  # JSON Schema check on definition.yaml files
make sast                  # Semgrep (Node.js + frontend rulesets)
make secrets-scan          # gitleaks
make deps-scan             # npm audit (backend + frontend)
make license-scan          # license allow-list enforcement
make container-scan        # trivy
make sbom                  # syft -> CycloneDX
make sign                  # cosign sign --key=kms://...
make fips-check            # node -e "require('crypto').getFips()" + openssl list -providers | grep fips
make ci                    # everything CI runs, locally
make install-hooks         # wire pre-commit + pre-push hooks (one-time dev setup)
make lockfile-check        # verify package-lock.json files are committed
make deps-source-check     # verify dependency source whitelist

# Run a single test (backend or frontend — same runner)
npx vitest run --reporter=verbose path/to/test.test.ts
```

Full target list and stage-gating: `docs/cicd.md`.

---

## 7. Open Decisions

Unresolved questions blocking specific Stage promotions are in `docs/open-questions.md`.
The agent MUST NOT guess answers — surface the relevant `[CONFIRM-NN]` ID and stop.
For ADR lifecycle, invoke fusion-decision-lifecycle skill.

---

## 8. Architecture at a Glance

**Trust zone ordering** (full contract: `docs/architecture/trust-zones.md`):

```
Z-UI → Z-API → Z-DB
              → Z-SECRETS
              → Z-WORKER → Z-TARGET
Z-AUDIT  (append-only; receives from all zones)
```

Default-deny between zones. This naming convention appears throughout audit, security, and
networking code — knowing the hierarchy avoids a full doc read for common tasks.

**Current scaffold state** (Stage 1 — Prototype):
- `backend/` exists — Fastify 5 + Zod + Drizzle ORM scaffold complete; 21 tests green; ≥84% coverage.
- `frontend/` exists — React + Vite + Vitest scaffold complete; 83 tests green; auth + audit wired.
- `fusion-nodes/` and `fusion-adapters/` do not exist yet — no nodes or adapters have been authored.
- Ansible playbooks reference `pre-check.yml`, `main.yml`, `verify.yml` — none yet populated.
- OpenTofu root is `terraform/main.tf` (OpenTofu registry provider, no resources defined yet).
- `src/`, `tests/`, `pyproject.toml` removed — Python stack retired per ADR-0004.
- `docker-compose.yml` does not exist yet — `make up` inoperable until authored.
