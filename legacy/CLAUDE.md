# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

**This document is the single source of truth. Every agent reads it before acting.
If something contradicts this file, this file wins.**

---

# CLAUDE.md — GDIT FUSION (`fusion-core`)

Detailed standards live in `docs/`. The agent MUST read the referenced doc BEFORE acting in that area.

---

## 0. Conflict Resolution Hierarchy

When rules pull in opposite directions, resolve in this order. If unresolved at
this hierarchy, STOP and ask a human.

1. Security & compliance (NIST 800-53 Rev. 5, 800-171 Rev. 3, 800-218, CMMC 2.0, FIPS 140-3, FedRAMP, DISA STIGs, SLSA v1.0)
2. Correctness & data integrity
3. Maintainability & reviewability
4. Performance
5. Developer ergonomics & velocity

Verification: every PR description MUST cite which level a non-obvious tradeoff
was made at. CI label: `tradeoff-cited`.

---

## 1. Project Purpose & Current Stage

FUSION is a redeployable platform for GDIT Digital Accelerator solutions. It
solves PoC rot (primary), siloed DA development, and late-bound Zero Trust.
FUSION is BOTH a deployment platform AND a schema/contract that solutions MUST
conform to.

**FUSION is NOT** an O&M tool, drift detector, monitoring system, or multi-tenant
SaaS. Operational contract ends at deployment-validation.

**Current Stage: 1 — Prototype.** (See `.fusion/stage`.)

| Stage | Name | Promotion Trigger (any one) |
|---|---|---|
| 1 | Prototype | Internal team only; single-node K3s; no external users; no CUI |
| 2 | Internal MVP | First non-team GDIT user; OR codebase >15k LOC; OR >5 contributors |
| 3 | Hardened Pilot | Customer-adjacent env; OR CUI introduced; OR >25 concurrent users; OR external assessor named |
| 4 | ATO-Ready Production | ATO submission required; OR multi-tenant; OR FedRAMP boundary declared |

Every rule in `docs/` is tagged `[S1]`..`[S4]` or `[Sn+]`. Untagged rules apply at
all stages. CI fails if a rule tagged `[Sn]` is violated when `cat .fusion/stage` ≥ n.

Stage promotion authority: see `[CONFIRM-09]` in `docs/open-questions.md`.

---

## 2. Where to Look (the agent MUST read these before acting in scope)

| If the task touches... | MUST read first | Why |
|---|---|---|
| Any code change | `docs/coding-standards.md` | Lint, type, input-validation rules |
| Stack / dependencies | `docs/stack.md`, `docs/dependency-policy.md`, `ALLOWED_LICENSES.md` | Pinned versions, license allow-list, SBOM/sign rules |
| Auth, crypto, secrets | `docs/security-controls.md`, `docs/secrets-and-keys.md` | Control-family mappings, FIPS rules, secrets sourcing |
| Logging or telemetry | `docs/audit-spec.md` | Required fields, sinks, retention, redaction |
| Data model / migrations | `docs/data-model.md`, `docs/data-classification.md` | Schema, classification tags, immutability |
| Networking / deployment | `docs/architecture/trust-zones.md` | Zone allow-lists, NetworkPolicy contract |
| New node / adapter / solution | `docs/domain.md`, `schemas/` | Load-bearing vocabulary, JSON schemas |
| Failure or retry logic | `docs/failure-handling.md` | User-facing vs security-event handling |
| CI/CD / branch settings | `docs/cicd.md` | Non-bypass gates, CODEOWNERS rules |
| Risks or tradeoffs | `docs/risks.md`, `docs/decisions/` | Open risks, ADR index |
| Glossary / acronyms | `docs/glossary.md` | Domain + federal terminology |

---

## 3. Always-Loaded Hard Rules (the agent MUST follow these even without reading docs)

These exist here, in always-loaded context, because violating them is
unrecoverable in a defense environment.

- MUST NOT introduce HashiCorp Terraform anywhere. Rationale: BSL prohibited. Verification: `make license-scan`.
- MUST NOT use any cryptographic primitive outside the system FIPS provider. Rationale: SC-13. Verification: `make fips-check`.
- MUST NOT call `child_process.exec()` or `spawn()` with `shell: true`. Rationale: SI-10 (command injection). Verification: Semgrep rule `javascript.lang.security.audit.dangerous-spawn-shell`.
- MUST NOT store any raw secret in DB, repo, log, container image, or LLM prompt. Rationale: IA-5, SC-28, AC-21. Verification: `make secrets-scan`.
- MUST NOT write directly to `main` or force-push. All changes via PR. Rationale: CM-3.
- MUST NOT skip, disable, or `continue-on-error` any CI gate. Rationale: CM-3, CM-5.
- MUST NOT redefine "node", "adapter", or "solution" — see `docs/domain.md`.
- MUST NOT resolve a `[CONFIRM-NN]` placeholder by guessing. Surface the question.
- MUST NOT silently reconcile a conflict between this file and code. Surface it.
- MUST NOT write feature code before writing a failing test. See §9 TDD Contract.
- MUST NOT commit if `vitest` is not green. See §9 TDD Contract.

Full prohibited-actions list with verification signals: `docs/agent-policy.md`.

---

## 4. Copy-Pasteable Commands

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

## 5. Specialized Subagents

For bounded tasks, the agent SHOULD delegate to a specialized subagent (own
context window, focused system prompt). Available agents in `.claude/agents/`:

- `backend-author` — write Node.js/TypeScript backend features; owns TDD workflow, Zod, Fastify, Drizzle, audit emit
- `security-reviewer` — review changes touching auth, audit, crypto, deploy; also checks TDD compliance
- `schema-validator` — validate `definition.yaml` files in nodes/adapters/solutions
- `dependency-reviewer` — review any dep additions for license, provenance, risk
- `audit-emitter` — verify audit events are emitted correctly per `docs/audit-spec.md`
- `migration-reviewer` — review Drizzle migrations for safety + classification tags

Invoke via Claude Code's subagent mechanism. The parent session MUST cite which
subagent reviewed which change in the PR description.

---

## 6. Decision Log

Append-only. Per-decision files in `docs/decisions/` (ADR format).
Index: `docs/decisions/README.md`. Most recent: `docs/decisions/0004-adopt-nodejs-typescript-backend.md`.

Review cadence: this file + all `docs/` MUST be reviewed at every Stage promotion
AND every 12 weeks at minimum. (CM-3, PM-9)

---

## 7. Open Confirmations

Unresolved questions blocking specific Stage promotions:
`docs/open-questions.md`. The agent MUST NOT guess answers — surface the
relevant `[CONFIRM-NN]` ID and stop.

---

## 9. TDD Contract

**Tests are written before feature code. This is not optional.**

### Workflow (every agent MUST follow for any new feature or bug fix)

1. Write a failing test in `src/__tests__/<feature>.test.ts` that describes the expected behavior
2. Run `npx vitest run src/__tests__/<feature>.test.ts` — confirm it fails **for the right reason**
3. Write the minimum code to make the test pass
4. Run `npx vitest run` — confirm full suite is green
5. Refactor if needed; keep tests green
6. Run `npm run lint` — zero errors before committing

### Required Test Coverage (every feature)

Every test file MUST include cases for:

- **Happy path** — expected input produces expected output
- **Invalid input** — malformed data, missing fields, wrong types (Zod 400/422)
- **Boundary conditions** — empty collections, max lengths, zero values
- **Audit event emission** — any action that writes to Z-AUDIT MUST have a test
  asserting the event was emitted with the correct `action` and `outcome` fields

For features touching auth or Z-API boundaries, also add:
- **Unauthenticated request** — must return 401/403, never a data response

### Pre-Commit Gate

All of the following MUST pass before staging a commit:

1. `npx vitest run` — full suite green (≥60% coverage enforced at Stage 1)
2. `npm run lint` — zero ESLint errors (`@typescript-eslint/strict`, `no-console`, `no-explicit-any`)
3. `npm run typecheck` — `tsc --noEmit` clean in the changed package

If any gate fails: **do not commit**. Surface the failure; never use `--no-verify`.
See §10 for the full commit procedure — which gates run and when is governed there.

### Coverage Threshold by Stage

| Stage | Threshold |
|---|---|
| 1 (Prototype) | ≥60% — enforced |
| 2 (Internal MVP) | ≥70% — enforced |
| 3 (Hardened Pilot) | ≥85% — enforced |
| 4 (ATO-Ready) | ≥90% — enforced |

### FUSION-Specific Test Obligations

Beyond standard TDD, FUSION code MUST also test:

- **Z-AUDIT events**: every auditable action (authn, authz denial, secret read,
  deployment, teardown, schema migration) MUST have a test asserting
  `audit.emit(...)` was called with all required fields (see `docs/audit-spec.md`)
- **definition.yaml validity**: every new node/adapter/solution definition MUST
  have a corresponding `make validate-definitions` call in CI or a schema assertion
  in `backend/src/__tests__/definitions.test.ts`
- **Trust zone enforcement**: network calls crossing zone boundaries MUST have
  tests asserting the shared HTTP client in `backend/src/common/http.ts` is used
  (not bare `fetch()` or `undici` outside that module)

---

## 10. Commit Policy

**This policy governs every commit the agent makes. It applies to all subagents.
Non-compliance is a CM-3 violation. The only valid override is an explicit user
instruction that names which step is being waived and why — and that waiver MUST
be recorded in the commit message body.**

### When a Commit Is Permitted

The agent MUST NOT commit unless one of these two conditions is met:

1. **Explicit user instruction** — the user says "commit", "commit this", "go ahead
   and commit", or equivalent direct language.
2. **Scoped permission** — the user says "do X and commit it". The commit happens
   only after X is fully complete and all gates pass — not during, not between steps.

The agent MUST NOT commit:
- Mid-task or between file edits when work is not yet complete.
- Speculatively ("I'll go ahead and commit this since it looks good").
- After doc updates, cleanup, or config changes unless the user explicitly asked for a commit.
- When any required gate below is failing — surface the failure instead.

### What Belongs in One Commit

One commit = one logical unit. Never mix types without explicit user instruction.

| Type | Scope examples | What belongs together |
|---|---|---|
| `feat` | `backend`, `frontend` | New behavior + its tests + direct inline doc update + **CHANGELOG entry** |
| `fix` | `backend`, `frontend` | Bug fix + regression test for that bug + **CHANGELOG entry** |
| `test` | `backend`, `frontend` | Test additions or corrections only — no feature change |
| `refactor` | `backend`, `frontend` | Code restructure, no behavior change, full suite green |
| `docs` | `docs`, `agents` | Documentation changes only — no source code |
| `chore` | `ci`, `gitignore`, `infra`, `ansible`, `schemas` | Non-functional: config, tooling, deletions, dependency bumps |
| `ci` | `ci` | CI/CD workflow changes only |

If staged files span more than one type, the agent MUST split them into separate
commits — unless the user explicitly says to combine them.

**CHANGELOG rule:** commits of type `feat` or `fix` MUST include an update to the
`[Unreleased]` section of `CHANGELOG.md` in the same commit. Write the entry at
commit time — not mid-coding — when the full scope is known. `test`, `refactor`,
`docs`, `chore`, and `ci` commits do not require a CHANGELOG entry.

### Pre-Commit Procedure

The agent MUST execute these steps in order. No step may be skipped.

**Step 1 — Confirm branch**
Run `git branch --show-current`. STOP and surface an error if the current branch is `main`.
The agent MUST NOT commit to `main` under any circumstances.

**Step 2 — Classify the change**
Determine whether staged (or to-be-staged) files include source code (`backend/`, `frontend/`)
or are docs/config/tooling only. This determines which gates run in Step 4.

**Step 3 — Review the staged diff**
Run `git diff --staged` and read the full output before staging anything.
The agent MUST NOT commit blind. If the diff contains unexpected files or content, stop and
surface the discrepancy to the user.

**Step 4 — Run the appropriate verification gates**

| Change classification | Required gates |
|---|---|
| Backend source changed | `make backend-test` → `make backend-lint` — both MUST pass |
| Frontend source changed | `make frontend-test` → `make frontend-lint` — both MUST pass |
| Both backend and frontend changed | All four gates above — all MUST pass |
| Docs / config / tooling only (no `.ts`, `.tsx`) | `make secrets-scan` — MUST pass |

`make secrets-scan` (gitleaks) runs on ALL commits regardless of classification.
If any gate fails: STOP. Report the failure. Do not commit. Do not use `--no-verify`.

**Step 5 — Stage specific files by name**
MUST NOT use `git add -A`, `git add .`, or any wildcard that captures unreviewed files.
Stage each file or directory by explicit path. If a file is unrelated to the current
logical unit, do not stage it — leave it for a separate commit.

**Step 6 — Write the commit message**

Format: Conventional Commits

```
type(scope): short imperative description — 72 chars max on this line

Body: explain WHY, not what. The diff shows what.
Reference BLOCKS_S2 findings as F-NNN if applicable.
If any procedure step was waived by user instruction, state it here:
  OVERRIDE: user waived Step 4 gate (make backend-test) — reason: <reason>

Co-Authored-By: Claude Sonnet 4.6 <noreply@anthropic.com>
```

Valid types: `feat` `fix` `test` `refactor` `docs` `chore` `ci` `infra`
Valid scopes: `backend` `frontend` `ansible` `docs` `ci` `infra` `schemas` `agents`

**Step 7 — Commit**
Run the commit. If a pre-commit hook fails: fix the underlying issue, re-run the
affected gates, then create a NEW commit. MUST NOT amend to bypass the failure.
MUST NOT use `--no-verify`, `--no-gpg-sign`, or any hook-bypass flag.

**Step 8 — Report to the user**
State the commit SHA and a one-sentence description of what was committed.
Nothing else.

### Hard Nevers (no override possible)

These apply even if the user instructs otherwise. If instructed to violate them,
surface the rule and stop.

- MUST NOT `git add -A` or `git add .`
- MUST NOT `git commit --no-verify` or any variant that skips hooks
- MUST NOT `git push --force` or `--force-with-lease` to `main`
- MUST NOT commit directly to `main`
- MUST NOT commit when `vitest` is red in any package that was changed
- MUST NOT commit when `make secrets-scan` reports findings
- MUST NOT amend a commit that has already been pushed to a remote

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
