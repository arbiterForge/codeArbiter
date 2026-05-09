# Documentation Maintenance Index

This file tracks every doc in the project, its review trigger, and the last time it was
verified accurate. Update the `Last Verified` column whenever a doc is meaningfully reviewed
or edited. The goal is to catch stale docs before they mislead contributors or auditors.

## Review Triggers

| Trigger | When |
|---|---|
| `stage-promotion` | Before promoting to the next FUSION stage |
| `on-change` | Whenever the thing the doc describes changes |
| `quarterly` | Every 12 weeks minimum (CM-3, PM-9) |
| `on-incident` | After any production incident or security event |

## Index

### Architecture & Design

| File | What It Covers | Review Trigger | Last Verified | Status |
|---|---|---|---|---|
| `CLAUDE.md` | Conflict resolution, stage rules, hard rules, TDD contract, commit policy, architecture summary | `stage-promotion` + `on-change` | 2026-05-05 | Current |
| `docs/architecture/trust-zones.md` | Zone model, allowed inbound/outbound, mTLS roadmap | `stage-promotion` + `on-change` | 2026-05-05 | Current — F-005 open question documented |
| `docs/domain.md` | FUSION vocabulary: node, adapter, solution | `on-change` (schema change) | Review pending | |
| `docs/stack.md` | Pinned versions, FIPS allow-list, hard stack rules | `on-change` (dep update) | 2026-05-05 | Current |
| `docs/data-model.md` | DB schema description, classification tagging rules | `on-change` (migration) | Review pending | |
| `docs/decisions/README.md` | ADR index | `on-change` (new ADR) | 2026-05-05 | Current (ADR-0001–0004) |
| `docs/decisions/0001-*.md` | CLAUDE.md contract ADR | `stage-promotion` | 2026-05-05 | Current |
| `docs/decisions/0002-*.md` | @xyflow/react ADR | `on-change` (license/version) | 2026-05-05 | Current |
| `docs/decisions/0003-*.md` | OCSF audit schema ADR | `stage-promotion` | 2026-05-05 | Stale Python paths in body — tracked |
| `docs/decisions/0004-*.md` | Node.js/TypeScript backend ADR | `stage-promotion` | 2026-05-05 | Current |

### Operations

| File | What It Covers | Review Trigger | Last Verified | Status |
|---|---|---|---|---|
| `docs/build-guide.md` | Dev environment setup, `npm install`, running tests | `on-change` (tooling change) | 2026-05-05 | Current |
| `docs/deploy-guide.md` | Deployment prerequisites, Ansible/Helm commands, validation | `on-change` (deploy change) | 2026-05-05 | Current — placeholder sections marked |
| `docs/runbook.md` | Day-2 ops: health checks, restart, common failures | `on-change` + `quarterly` | 2026-05-05 | Current |
| `docs/hardening-guide.md` | Post-deploy security hardening, FIPS, STIG alignment | `stage-promotion` + `on-change` | 2026-05-05 | Current — known gaps documented |
| `docs/failure-handling.md` | User-facing vs security-event failure behavior | `on-change` (error handling) | Review pending | |

### Security & Compliance

| File | What It Covers | Review Trigger | Last Verified | Status |
|---|---|---|---|---|
| `docs/security-controls.md` | NIST 800-53 control family mappings, FIPS rules | `stage-promotion` | Review pending | |
| `docs/audit-spec.md` | Required audit event fields, sinks, retention | `on-change` (audit change) | 2026-05-05 | Stale Python path on line 105 — tracked |
| `docs/secrets-and-keys.md` | Secret sourcing, rotation, secret_ref pattern | `on-change` (secrets change) | Review pending | |
| `docs/data-classification.md` | CUI/None/Secret-Ref column tagging rules | `on-change` (schema change) | Review pending | |
| `SECURITY.md` | Vulnerability reporting, scanning tools, incident procedure | `quarterly` | 2026-05-05 | Current |
| `ALLOWED_LICENSES.md` | License allow-list for dependencies | `on-change` (new dep) | Review pending | |

### Process & Governance

| File | What It Covers | Review Trigger | Last Verified | Status |
|---|---|---|---|---|
| `docs/risks.md` | Risk register R-01 through R-08 | `quarterly` + `stage-promotion` | 2026-05-05 | Current (R-06, R-07, R-08 added) |
| `docs/open-questions.md` | CONFIRM-NN placeholders blocking stage promotion | `on-change` | 2026-05-05 | Current |
| `docs/cicd.md` | CI gate definitions, stage-gating rules, branch protection | `on-change` (CI change) | 2026-05-05 | Current |
| `docs/agent-policy.md` | Agent prohibited actions | `on-change` | 2026-05-05 | Current |
| `docs/dependency-policy.md` | Dependency review process, SBOM, signing | `on-change` (new dep) | Review pending | |
| `docs/glossary.md` | Domain + federal terminology | `on-change` (new term) | Review pending | |
| `docs/coding-standards.md` | TypeScript, Zod, Drizzle, Fastify conventions | `on-change` | 2026-05-05 | Current |
| `CONTRIBUTING.md` | Branch naming, PR process, how to consume cove-shared | `on-change` | 2026-05-05 | Current |
| `CODEOWNERS` | Path-level ownership | `on-change` (team change) | 2026-05-05 | Current |

### Changelogs & Scaffolding

| File | What It Covers | Review Trigger | Last Verified | Status |
|---|---|---|---|---|
| `README.md` | Project overview, quick start, env vars, limitations | `stage-promotion` + `on-change` | 2026-05-05 | Current |
| `CHANGELOG.md` | Version history (Keep a Changelog format) | `on-change` (every PR) | 2026-05-05 | Current |
| `solution.yaml` | Catalog metadata (language, maturity, tags) | `stage-promotion` | Review pending — Python refs need update |
| `.gitea/pull_request_template.md` | PR checklist | `on-change` | 2026-05-05 | Current |

### Checkpoints

| File | What It Covers | Review Trigger | Last Verified | Status |
|---|---|---|---|---|
| `docs/checkpoints/2026-05-04.md` | First checkpoint — pre-TypeScript-scaffold | Historical | 2026-05-04 | Historical — not maintained |
| `docs/checkpoints/2026-05-05.md` | Second checkpoint — Stage 1 full review | Sign-off pending | 2026-05-05 | Awaiting sign-off |

---

## Stale Doc Backlog

Items known to be stale at the time of last checkpoint. These must be resolved before
Stage 2 promotion or they will appear as findings in the next checkpoint.

| Item | Location | Issue | Priority |
|---|---|---|---|
| Python paths in ADR body | `docs/decisions/0003-adopt-ocsf-audit-schema.md:111-112` | References `backend/audit/events.py` and `tests/test_audit_schema.py` (Python, retired) | Before S2 |
| Python test path | `docs/audit-spec.md:105` | References `tests/security/test_audit_fail_closed.py` (Python) | Before S2 |
| `solution.yaml` language field | `solution.yaml` | `primary_language: python` — should be `typescript` | This sprint |
| `fusion-c4.puml` | `docs/architecture/trust-zones.md` | Diagram file referenced but not yet authored | Stage 2 |
| `deploy/egress-allowlist.yaml` | `docs/architecture/trust-zones.md` | Referenced but not yet authored | Stage 2 |
| `docs/decisions/0003` ADR body | Python paths in Consequences section | Author TypeScript payback note | Before S2 |

---

## How to Use This File

1. When you change a piece of infrastructure (e.g., add a new route, update a dependency, change a CI job), find the row in the index whose "What It Covers" matches and update `Last Verified` to today.
2. At every stage promotion, run through the `stage-promotion` rows and verify each one is accurate before the checkpoint.
3. At the quarterly review cadence (CM-3, PM-9), sweep the entire index and update Status for anything marked "Review pending."
4. When a doc becomes stale in a way you don't have time to fix immediately, add it to the Stale Doc Backlog table rather than leaving it silently wrong.
