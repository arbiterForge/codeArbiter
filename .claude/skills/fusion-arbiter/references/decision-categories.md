# Decision Categories — Canonical Scan List

This is the canonical list of decision categories the FUSION arbiter scans for during Stage 2 evidence indexing. The list is organized by area and prioritized within each area.

**This list is closed.** The arbiter MUST NOT invent new categories.

If the arbiter encounters a decision that does not fit any category here:

1. Note the decision in the evidence index with `category: UNKNOWN`
2. Describe what makes it not fit any existing category
3. Ask the user to either map it to an existing category or explicitly add a new category to this file
4. Wait for the user's choice

The user adding a new category is itself a decision logged in `docs/fusion-arbiter-decisions.md` with `Decision category: META.CATEGORY-CREATION`. This makes category list growth an explicit, auditable event rather than ad-hoc accumulation.

## Stack Decisions

These are foundational technology choices. Every variance here propagates broadly.

- `STACK.FRONTEND.FRAMEWORK` — React + React Flow expected
- `STACK.FRONTEND.LANGUAGE` — TypeScript expected
- `STACK.FRONTEND.STATE-MGMT` — Context + Router loaders + URL params + local (MVP1); Zustand at V1 inflection
- `STACK.BACKEND.FRAMEWORK` — Fastify 5 expected
- `STACK.BACKEND.LANGUAGE` — Node.js + TypeScript expected
- `STACK.BACKEND.ORM` — Drizzle expected
- `STACK.BACKEND.VALIDATION` — Zod with route-level schema registration expected
- `STACK.DB.ENGINE` — PostgreSQL bundled
- `STACK.JOB-QUEUE` — Graphile Worker expected
- `STACK.LIBRARY.GIT` — Gitea bundled
- `STACK.IAC.INFRASTRUCTURE` — OpenTofu expected
- `STACK.IAC.CONFIG-MGMT` — Ansible (license decision deferred — known open decision)
- `STACK.IAC.K8S-DEPLOY` — Helm expected
- `STACK.AUTH.IDENTITY` — Keycloak bundled, OIDC
- `STACK.AUTH.AUTHORIZATION` — OPA bundled
- `STACK.SECRETS.V1` — OpenBao expected for V1
- `STACK.LOGGING` — Pino expected
- `STACK.OBSERVABILITY.METRICS` — OpenTelemetry SDK expected
- `STACK.HOSTING` — K3s on EC2 expected (Cove.GDIT for MVP1)

## Architectural Patterns

- `PATTERN.WORKER-ABSTRACTION` — execution workers behind an abstract interface
- `PATTERN.MULTI-TENANT-RETROFIT` — `tenant_id` columns on solution-related tables
- `PATTERN.SUB-SOLUTION-COMPOSITION` — copy-on-import semantics
- `PATTERN.REVERSAL-TIERS` — clean / partial / manual capability declarations
- `PATTERN.PIN-WITH-MONITORING` — fidelity model
- `PATTERN.AGE-TIERED-DEPLOYMENT-GATES` — green / yellow / red
- `PATTERN.EAGER-EXECUTION` — V2 toggleable; V1 prep work
- `PATTERN.BROWNFIELD-DEPENDENCY` — solution-declared external dependencies via wizard
- `PATTERN.CHANGE-TRIGGER-POLICY` — defined triggers for stop-and-review

## State Ownership

- `STATE.DB-GIT-SYNC` — local DB ↔ Gitea sync model with `git_sha` pinning
- `STATE.GITSHA-PINNING` — solutions pin `git_sha` for every referenced node and adapter
- `STATE.DEPLOYMENT-RECEIPT` — point-in-time snapshot, never expires
- `STATE.ENVIRONMENT-PROFILE` — non-secret globals + secret references + trust flag
- `STATE.AUDIT-TRANSPORT` — per ADR-0003, four-stage progression; MVP1 stage open

## Schema and Data Model

- `SCHEMA.SOLUTION-MANIFEST` — solution composition format
- `SCHEMA.NODE-DEFINITION` — node YAML schema with metadata, variables, valid_connections, teardown_capability, criticality
- `SCHEMA.ADAPTER-DEFINITION` — adapter YAML schema with source_type, target_type, adapter_kind, tier, criticality, teardown_capability
- `SCHEMA.AUDIT-EVENT` — OCSF-aligned per ADR-0003
- `SCHEMA.ENVIRONMENT-PROFILE` — environment variable schema
- `SCHEMA.DEPLOYMENT-RECEIPT` — pinned artifacts, age status, pin health status

## API Surface

- `API.AUTH.MIDDLEWARE` — OIDC token validation middleware
- `API.AUTHZ.OPA-CALL` — OPA called on every authorized action
- `API.AUDIT.EMIT` — audit emit on every security-relevant action
- `API.VALIDATION.ZOD-ROUTES` — Zod schemas registered on every route (closes F-019)
- `API.WEBSOCKET.OUTPUT-STREAM` — WebSocket relay for deployment output

## Repo Structure

- `REPO.GITEA.ORG` — `FUSION_ORG` organization in Gitea
- `REPO.GITEA.NODES` — `fusion-nodes` repo for node definitions
- `REPO.GITEA.ADAPTERS` — `fusion-adapters` repo for adapter definitions
- `REPO.GITEA.POLICIES` — `fusion-policies` repo for OPA Rego
- `REPO.GITEA.SCHEMAS` — `fusion-schemas` repo for OCSF and JSON Schema
- `REPO.GITEA.SOLUTIONS` — per-solution repos under `solution-*` naming
- `REPO.BRANCH-PROTECTION` — no force push to main, PR-only merges

## Deployment

- `DEPLOY.HELM-CHART` — single Helm chart bundles entire FUSION
- `DEPLOY.SELF-CONTAINED` — no external SaaS runtime dependencies (Ansible exception pending)
- `DEPLOY.K3S-HOSTING` — K3s on EC2 in Cove.GDIT for MVP1
- `DEPLOY.AWS-TARGET` — OpenTofu AWS provider for MVP1 deployment target
- `DEPLOY.SUBPROCESS-SANDBOX` — restricted env (MVP1) → K8s Job (V1)

## CI/CD and Enforcement

- `CI.HUSKY-PRECOMMIT` — pre-commit hooks via Husky
- `CI.LINT-STAGED` — staged-file linting
- `CI.VITEST` — test framework
- `CI.DRIZZLE-MIGRATIONS` — migration check
- `CI.ZOD-ROUTE-COVERAGE` — F-019 enforcement
- `CI.OCSF-AUDIT-VALIDATION` — schema validation hook
- `CI.SEMGREP-AUDIT-EMIT` — `audit.emit()` enforcement rule
- `CI.LICENSE-CHECK` — dependency license allowlist
- `CI.PIPELINE` — Gitea Actions or external CI

## Compliance Posture

- `COMPLIANCE.FIPS-CAPABLE` — FIPS-compatible builds where applicable
- `COMPLIANCE.STIG-IMAGES` — STIG'd base images for nodes
- `COMPLIANCE.NIST-800-53` — control mapping per ADR-0003
- `COMPLIANCE.ZERO-TRUST` — Keycloak + OPA pattern, audit trail, ZT metadata fields

## Documentation Posture

- `DOCS.ADR-CONVENTION` — ADRs follow defined template
- `DOCS.NODE-AUTHORING-GUIDE` — contribution guide for nodes
- `DOCS.ADAPTER-AUTHORING-GUIDE` — contribution guide for adapters
- `DOCS.RUNBOOKS` — operational runbooks for FUSION deployment

## Meta-Categories

These categories cover decisions about the arbitration process itself:

- `META.CATEGORY-CREATION` — adding a new entry to this canonical list
- `META.STALE-ARTIFACT-RESOLUTION` — re-evaluation, keep-as-is, or supersession of a prior decision

## Scan Order Priority

When time-constrained or when scope is large, prioritize scanning categories in this order:

1. STACK (everything propagates from these)
2. PATTERN (architectural commitments)
3. SCHEMA (data contracts)
4. STATE (consistency model)
5. API (interface contracts)
6. DEPLOY (operational reality)
7. REPO (organizational structure)
8. CI (enforcement infrastructure)
9. COMPLIANCE (regulatory alignment)
10. DOCS (knowledge preservation)
