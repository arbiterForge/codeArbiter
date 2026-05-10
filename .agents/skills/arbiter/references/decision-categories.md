# Decision Categories — Canonical Scan List

This is the canonical list of decision categories the arbiter scans for during Stage 2 evidence indexing. The list is organized by area and prioritized within each area.

**This list is closed.** The arbiter MUST NOT invent new categories.

If the arbiter encounters a decision that does not fit any category here:

1. Note the decision in the evidence index with `category: UNKNOWN`
2. Describe what makes it not fit any existing category
3. Ask the user to either map it to an existing category or explicitly add a new category to this file
4. Wait for the user's choice

The user adding a new category is itself a decision logged in `projectContext/arbiter-decisions.md` with `Decision category: META.CATEGORY-CREATION`. This makes category list growth an explicit, auditable event rather than ad-hoc accumulation.

## Stack Decisions

These are foundational technology choices. Every variance here propagates broadly.

- `STACK.FRONTEND.FRAMEWORK` — frontend UI framework
- `STACK.FRONTEND.LANGUAGE` — frontend language
- `STACK.FRONTEND.STATE-MGMT` — frontend state management approach
- `STACK.BACKEND.FRAMEWORK` — backend application framework
- `STACK.BACKEND.LANGUAGE` — backend language and runtime
- `STACK.BACKEND.ORM` — data access / ORM layer
- `STACK.BACKEND.VALIDATION` — input validation approach
- `STACK.DB.ENGINE` — primary database engine
- `STACK.JOB-QUEUE` — async job / worker queue
- `STACK.LIBRARY.GIT` — version control service (self-hosted or SaaS)
- `STACK.IAC.INFRASTRUCTURE` — infrastructure-as-code tool
- `STACK.IAC.CONFIG-MGMT` — configuration management tool
- `STACK.IAC.K8S-DEPLOY` — Kubernetes deployment tool
- `STACK.AUTH.IDENTITY` — identity provider
- `STACK.AUTH.AUTHORIZATION` — authorization engine
- `STACK.SECRETS.PRIMARY` — primary secrets store
- `STACK.LOGGING` — structured logging library
- `STACK.OBSERVABILITY.METRICS` — metrics / tracing SDK
- `STACK.HOSTING` — hosting platform and topology

## Architectural Patterns

- `PATTERN.WORKER-ABSTRACTION` — execution workers behind an abstract interface
- `PATTERN.MULTI-TENANT-RETROFIT` — tenant isolation approach on data models
- `PATTERN.SUB-SOLUTION-COMPOSITION` — composition and import semantics
- `PATTERN.REVERSAL-TIERS` — reversibility / teardown capability declarations
- `PATTERN.PIN-WITH-MONITORING` — artifact pinning and fidelity model
- `PATTERN.AGE-TIERED-DEPLOYMENT-GATES` — deployment health gate tiers
- `PATTERN.EAGER-EXECUTION` — eager vs deferred execution model
- `PATTERN.BROWNFIELD-DEPENDENCY` — external dependency declaration approach
- `PATTERN.CHANGE-TRIGGER-POLICY` — triggers for stop-and-review workflows

## State Ownership

- `STATE.DB-GIT-SYNC` — local DB and version control sync model
- `STATE.GITSHA-PINNING` — artifact SHA pinning strategy
- `STATE.DEPLOYMENT-RECEIPT` — deployment receipt and snapshot semantics
- `STATE.ENVIRONMENT-PROFILE` — environment variable and secret reference model
- `STATE.AUDIT-TRANSPORT` — audit event transport and delivery progression

## Schema and Data Model

- `SCHEMA.SOLUTION-MANIFEST` — solution composition format
- `SCHEMA.NODE-DEFINITION` — node definition schema
- `SCHEMA.ADAPTER-DEFINITION` — adapter definition schema
- `SCHEMA.AUDIT-EVENT` — audit event schema
- `SCHEMA.ENVIRONMENT-PROFILE` — environment variable schema
- `SCHEMA.DEPLOYMENT-RECEIPT` — deployment receipt schema

## API Surface

- `API.AUTH.MIDDLEWARE` — authentication middleware approach
- `API.AUTHZ.CALL` — authorization check integration pattern
- `API.AUDIT.EMIT` — audit emit integration on security-relevant actions
- `API.VALIDATION.ROUTES` — input validation on routes
- `API.WEBSOCKET.OUTPUT-STREAM` — streaming output delivery

## Repo Structure

- `REPO.VCS.ORG` — VCS organization structure
- `REPO.VCS.NODES` — node definitions repository
- `REPO.VCS.ADAPTERS` — adapter definitions repository
- `REPO.VCS.POLICIES` — authorization policy repository
- `REPO.VCS.SCHEMAS` — schema repository
- `REPO.VCS.SOLUTIONS` — solution repositories naming and layout
- `REPO.BRANCH-PROTECTION` — branch protection and merge policy

## Deployment

- `DEPLOY.PACKAGING` — deployment packaging approach (Helm chart, container, etc.)
- `DEPLOY.SELF-CONTAINED` — self-contained vs external-dependency packaging
- `DEPLOY.HOSTING-TOPOLOGY` — hosting platform and topology
- `DEPLOY.CLOUD-TARGET` — cloud provider or on-premises target
- `DEPLOY.SUBPROCESS-SANDBOX` — subprocess / job execution isolation

## CI/CD and Enforcement

- `CI.PRE-COMMIT` — pre-commit hook framework
- `CI.LINT-STAGED` — staged-file linting approach
- `CI.TEST-RUNNER` — test framework and runner
- `CI.SCHEMA-MIGRATIONS` — schema migration enforcement approach
- `CI.ROUTE-COVERAGE` — route validation coverage enforcement
- `CI.AUDIT-VALIDATION` — audit schema validation enforcement
- `CI.AUDIT-EMIT-ENFORCEMENT` — audit emit call enforcement rule
- `CI.LICENSE-CHECK` — dependency license allowlist enforcement
- `CI.PIPELINE` — CI pipeline platform

## Compliance Posture

- `COMPLIANCE.CRYPTO-POLICY` — cryptographic algorithm policy
- `COMPLIANCE.BASE-IMAGES` — base image hardening approach
- `COMPLIANCE.CONTROL-FRAMEWORK` — primary compliance control framework
- `COMPLIANCE.ZERO-TRUST` — zero trust architecture pattern

## Documentation Posture

- `DOCS.ADR-CONVENTION` — ADR template and convention
- `DOCS.NODE-AUTHORING-GUIDE` — contribution guide for nodes
- `DOCS.ADAPTER-AUTHORING-GUIDE` — contribution guide for adapters
- `DOCS.RUNBOOKS` — operational runbooks

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
