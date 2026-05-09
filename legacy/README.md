# FUSION — Redeployable Platform for GDIT Digital Accelerator Solutions

FUSION is a standardized, redeployable deployment platform that solves PoC rot for GDIT
Digital Accelerator solutions. It provides a production-aligned scaffold — Fastify API,
React frontend, OIDC auth, OCSF audit logging, Drizzle ORM, and Gitea-based CI/CD — that
DA teams drop solutions into rather than rebuilding from scratch each engagement.

**Category:** Platform
**Maturity:** Prototype (Stage 1)
**FUSION Stage:** 1 of 4 — internal team only, single-node K3s, no external users, no CUI

## Prerequisites

| Requirement | Version | Notes |
|---|---|---|
| Node.js | 22 LTS | `node --version` |
| npm | >= 10 | bundled with Node.js 22 |
| make | any | `make --version` |
| pre-commit | >= 3.6 | `pipx install pre-commit` |
| Ansible | >= 2.15 | control node only |
| OpenTofu | >= 1.8 | `tofu --version` |
| Docker / Podman | any | local dev stack only |

## Quick Start

~~~bash
# 1. Clone the repo
git clone https://gitea.cove.gdit/cove/cove-apps-fusion.git
cd cove-apps-fusion

# 2. Install Node.js dependencies (frontend + backend workspaces)
npm install

# 3. Install pre-commit hooks
make install-hooks

# 4. Copy and populate environment variables
cp .env.example .env
# Edit .env with real values — see docs/build-guide.md

# 5. Bring up the local dev stack (requires docker-compose.yml — see CLAUDE.md §8)
make up

# 6. Start backend (hot reload)
make backend-dev

# 7. Start frontend (hot reload)
make frontend-dev
~~~

## Key Environment Variables

| Variable | Description | Required |
|---|---|---|
| `DATABASE_URL` | PostgreSQL connection string | Yes |
| `OIDC_JWKS_URI` | OIDC provider JWKS endpoint | Yes |
| `OIDC_ISSUER` | Expected JWT issuer | Yes |
| `AUDIT_SINK_URL` | HTTP endpoint for audit event POSTs | Yes |
| `AUTH_BYPASS` | `true` only in test/local dev — never in production | Dev only |
| `VITE_OIDC_ISSUER` | Frontend OIDC issuer (build-time) | Yes |
| `VITE_OIDC_CLIENT_ID` | OIDC client ID (build-time) | Yes |
| `VITE_API_BASE_URL` | Backend API base URL (build-time) | Yes |
| `VITE_AUDIT_SINK_URL` | Audit sink URL visible to browser (build-time) | Yes |

## Architecture Overview

```
Z-UI (React) → Z-API (Fastify) → Z-DB (PostgreSQL)
                               → Z-SECRETS (AWS Secrets Manager)
                               → Z-WORKER (Node.js job runner) → Z-TARGET
Z-AUDIT (append-only OCSF sink — receives from all zones)
```

See `docs/architecture/trust-zones.md` for the full zone contract.

## Running Tests

~~~bash
make backend-test     # Vitest + coverage ≥60%
make frontend-test    # Vitest + coverage ≥60%
make ci               # Full CI suite (lint + typecheck + tests + security scans)
~~~

## Documentation

| Doc | Purpose |
|---|---|
| `docs/build-guide.md` | Dev environment setup and build instructions |
| `docs/deploy-guide.md` | Deployment to a target environment |
| `docs/hardening-guide.md` | Post-deployment security hardening |
| `docs/runbook.md` | Day-2 operations — health checks, restart, log inspection |
| `docs/architecture/trust-zones.md` | Zone model and network policy contract |
| `docs/audit-spec.md` | Audit event schema and required fields |
| `docs/coding-standards.md` | TypeScript, Zod, Drizzle, Fastify conventions |
| `docs/decisions/` | Architecture Decision Records (ADR-0001 through ADR-0004) |

## Limitations

- `make up` is currently inoperable — `docker-compose.yml` not yet authored (CLAUDE.md §8)
- `fusion-nodes/` and `fusion-adapters/` directories do not yet exist — no nodes or adapters defined
- Ansible playbooks exist as stubs only — `pre-check.yml` and `main.yml` not yet populated
- Auth requires an OIDC provider — see `[CONFIRM-01]` in `docs/open-questions.md`

## Changelog

See [CHANGELOG.md](CHANGELOG.md).

## License

Proprietary — internal GDIT/COVE use only. See [LICENSE](LICENSE).
