# FUSION — Task Backlog

**Document 3 of 3** | Companion to: Architecture Breakdown, Phased Build Plan
**Decomposition source:** Desktop Claude architectural session, May 2026
**Status:** Authoritative task backlog source of truth — to be reconciled against existing scaffold and CLI work-in-progress
**Revision:** Final (Phase 3) — incorporates standardized LOCKED/OPEN/DEFERRED vocabulary, decision-ID tagging, TBD owner disambiguation

---

## How to Use This Document

This document enumerates concrete engineering tasks grouped by phase. Tasks are written at small-grain (1-3 hour units where possible) so they can be assigned directly to agents or human engineers without further decomposition.

**Task ID format:** `<PHASE>.<AREA>.<NUMBER>` — e.g., `MVP1.AUTH.001`, `V1.LIB.014`

**Status vocabulary (consistent across all three artifacts):**
- **LOCKED** — decision is made; scaffold should reflect it
- **OPEN** — decision is awaiting input
- **DEFERRED** — decision is intentionally postponed

**Decision IDs:** Where a task implements a specific architectural decision, the relevant decision ID from Architecture Breakdown §5–§6 appears in square brackets. The `fusion-arbiter` skill uses these to determine task readiness.

**Each task has:**
- A short imperative title
- A specific deliverable (the test for "done")
- A role assignment using disambiguated TBD values:
  - `TBD-DARREN-REVIEW` — assignment happens at the architectural review meeting
  - `TBD-AVAILABLE` — any available team member; not yet specifically chosen
  - `TBD-SPIKE-OUTCOME` — assignment depends on a spike outcome
- Dependencies on other tasks
- Flag if it requires a spike before it can start
- Estimated effort range
- Decision IDs implemented (where applicable)

**Reconciliation protocol when consuming this document:**

1. For each task, check if work has already been started in the existing scaffold.
2. If a task is already complete in scaffold, mark it complete and verify the deliverable matches. If the deliverable was implemented differently, surface the variance.
3. If a task is in progress, validate that the scaffold approach matches the task description.
4. If a task hasn't been started, treat as a candidate for next sprint.
5. Tasks may be consolidated if scaffold patterns make them inseparable. Document consolidations.

**Task status legend:**
- ⬜ Not started (default)
- 🔄 In progress
- ✅ Complete
- 🚫 Blocked (with reason)
- ❓ Needs scaffold reconciliation

All tasks below are ⬜ unless your scaffold context indicates otherwise.

---

## Areas (used in task IDs)

- **AUTH** — Keycloak, OIDC, OPA, sessions
- **API** — Fastify routes, validation, WebSocket
- **DB** — Drizzle schema, migrations, queries
- **LIB** — Gitea, library sync, repo structure
- **CANVAS** — React Flow, frontend canvas
- **UI** — Other frontend (panes, wizard, property grid)
- **EXEC** — Worker abstraction, Z-WORKER, IaC execution
- **AUDIT** — OCSF events, audit transport
- **DEPLOY** — Helm chart for FUSION itself, deployment infrastructure
- **CI** — Enforcement scaffold, pipeline gates
- **DOCS** — ADRs, runbooks, contribution guides
- **DEMO** — MVP1 demo solution and supporting nodes/adapters
- **SPIKE** — Time-boxed validation efforts

---

## PHASE 1 — MVP1 BACKLOG

### MVP1.CI — Enforcement Scaffold (Week 1 priority)

This area is foundation work. Complete it BEFORE feature acceleration begins. Without this, agent-driven contributions degrade the codebase faster than they advance it.

**MVP1.CI.001** — Configure Husky for pre-commit hooks
- Deliverable: `.husky/pre-commit` runs lint-staged on every commit
- Dependencies: none
- Effort: 1-2 hours
- Owner: Brennon

**MVP1.CI.002** — Configure lint-staged for TypeScript files
- Deliverable: `.lintstagedrc` runs `eslint --fix` and `prettier --write` on staged TS files
- Dependencies: MVP1.CI.001
- Effort: 1 hour

**MVP1.CI.003** — Configure Vitest as test runner
- Deliverable: `vitest.config.ts` configured, `npm test` runs all unit tests, coverage reporting enabled
- Dependencies: none
- Effort: 2-3 hours

**MVP1.CI.004** — Add Drizzle migration generation and check
- Deliverable: `drizzle-kit generate` produces migrations from schema; CI fails if generated migrations differ from committed migrations
- Dependencies: backend scaffold exists
- Effort: 2-3 hours

**MVP1.CI.005** — Add Zod-route-coverage check (closes F-019)
- Deliverable: Lint rule or test that fails CI if any Fastify route handler is registered without `schema: { body: ..., response: ... }`
- Dependencies: MVP1.CI.003
- Effort: 3-4 hours
- Spike note: This may require a custom AST visitor or convention-based test. Validate approach early.

**MVP1.CI.006** — Add OCSF audit schema validation hook
- Deliverable: All `audit.emit()` call sites have their event payload validated against `schemas/audit-event.schema.json` at test time
- Dependencies: ADR-0003 schema file exists; MVP1.CI.003
- Effort: 2-3 hours

**MVP1.CI.007** — Add Semgrep rule for `audit.emit()` enforcement
- Deliverable: Semgrep rule fails CI if a route handler that mutates state does not call `audit.emit()`
- Dependencies: MVP1.CI.003
- Effort: 3-4 hours

**MVP1.CI.008** — Add license header check
- Deliverable: Pre-commit hook fails if any new TS file lacks the standard GDIT proprietary header
- Dependencies: MVP1.CI.001
- Effort: 1-2 hours

**MVP1.CI.009** — Add dependency license check
- Deliverable: CI fails if any new dependency added to `package.json` has a license outside the approved list (MIT, Apache 2.0, BSD, MPL 2.0, ISC)
- Dependencies: none
- Effort: 2-3 hours

**MVP1.CI.010** — Set up Gitea Actions or external CI pipeline for FUSION repo
- Deliverable: PRs trigger full CI run; merges to main trigger build and image push
- Dependencies: Gitea instance available
- Effort: 4-6 hours

---

### MVP1.AUTH — Authentication and Authorization

**MVP1.AUTH.001** — Bundle Keycloak in FUSION Helm chart
- Deliverable: `helm install fusion` deploys Keycloak as a sidecar service; admin console accessible
- Dependencies: Helm chart skeleton exists
- Effort: 4-6 hours

**MVP1.AUTH.002** — Configure Keycloak realm for FUSION
- Deliverable: Realm created with FUSION client registered, redirect URIs configured, basic role definitions (Solutions Engineer, Admin)
- Dependencies: MVP1.AUTH.001
- Effort: 2-3 hours

**MVP1.AUTH.003** — Configure Keycloak federation to Cove.GDIT AD
- Deliverable: Cove.GDIT AD users can authenticate to Keycloak via LDAP federation
- Dependencies: MVP1.AUTH.002, AD credentials available
- Effort: 4-6 hours

**MVP1.AUTH.004** — Implement OIDC client in Z-FRONTEND
- Deliverable: User redirected to Keycloak for login, returns to FUSION with valid token, token stored and refreshed
- Dependencies: MVP1.AUTH.002
- Effort: 4-6 hours

**MVP1.AUTH.005** — Implement OIDC token validation middleware in Z-API
- Deliverable: Fastify middleware validates JWT signature, expiry, and issuer; rejects invalid tokens with 401
- Dependencies: MVP1.AUTH.002
- Effort: 3-4 hours

**MVP1.AUTH.006** — Bundle OPA in FUSION Helm chart
- Deliverable: OPA running as sidecar; HTTP API accessible from Z-API
- Dependencies: MVP1.AUTH.001
- Effort: 3-4 hours

**MVP1.AUTH.007** — Define initial OPA policy bundle structure
- Deliverable: `fusion-policies` repo created in Gitea; basic role-based policies in Rego; `opa test` passes
- Dependencies: Gitea available
- Effort: 4-6 hours
- Spike note: Spike 4 validates the bundle structure. MVP1 uses a simplified version; full structure follows post-spike.

**MVP1.AUTH.008** — Implement OPA client in Z-API
- Deliverable: `authz.can(user, action, resource)` helper calls OPA, returns boolean, logs decision
- Dependencies: MVP1.AUTH.006, MVP1.AUTH.007
- Effort: 3-4 hours

**MVP1.AUTH.009** — Wire OPA decision logging to audit emit
- Deliverable: Every OPA decision emits an OCSF audit event
- Dependencies: MVP1.AUTH.008, MVP1.AUDIT.003
- Effort: 2-3 hours

---

### MVP1.DB — Database Schema and Migrations

**MVP1.DB.001** — Bundle PostgreSQL in FUSION Helm chart
- Deliverable: PostgreSQL deploys as part of Helm install with persistent volume claim
- Dependencies: Helm chart skeleton
- Effort: 3-4 hours

**MVP1.DB.002** — Define Drizzle schema for solutions table
- Deliverable: `solutions` table with `id`, `tenant_id`, `name`, `created_by`, `owner`, `customer_program`, `original_purpose`, `problem_statement`, `outcome_statement`, `created_at`, `updated_at`, `git_sha`
- Dependencies: backend scaffold exists, Drizzle configured
- Effort: 2-3 hours

**MVP1.DB.003** — Define Drizzle schema for nodes table (registry cache)
- Deliverable: `nodes` table with `id`, `name`, `type`, `version`, `git_sha`, `variables_schema` (JSONB), `valid_connections` (JSONB), `teardown_capability`, `criticality`
- Dependencies: MVP1.DB.001
- Effort: 2-3 hours

**MVP1.DB.004** — Define Drizzle schema for adapters table (registry cache)
- Deliverable: `adapters` table with `id`, `name`, `source_node_type`, `target_node_type`, `adapter_kind`, `tier`, `criticality`, `teardown_capability`, `version`, `git_sha`, `variables_schema`
- Dependencies: MVP1.DB.001
- Effort: 2-3 hours

**MVP1.DB.005** — Define Drizzle schema for solution_nodes (composition)
- Deliverable: Junction table linking solutions to nodes with `node_git_sha`, `position_x`, `position_y`, `variables` (JSONB)
- Dependencies: MVP1.DB.002, MVP1.DB.003
- Effort: 2 hours

**MVP1.DB.006** — Define Drizzle schema for solution_edges (composition)
- Deliverable: Edges table with `solution_id`, `source_node_id`, `target_node_id`, `adapter_id`, `adapter_git_sha`, `selected_adapters` (JSONB array for multi-select)
- Dependencies: MVP1.DB.005
- Effort: 2 hours

**MVP1.DB.007** — Define Drizzle schema for environments table
- Deliverable: `environments` table with `id`, `tenant_id`, `name`, `target_type` (enum: aws, vmware, baremetal, hybrid), `variables_schema` (JSONB), `trusted_for_active_checks` (boolean)
- Dependencies: MVP1.DB.001
- Effort: 2 hours

**MVP1.DB.008** — Define Drizzle schema for env_variables (with secret references)
- Deliverable: `env_variables` table with `env_id`, `key`, `value` (text, for non-secrets), `secret_ref` (text, for references to secrets manager). Constraint: exactly one of `value` or `secret_ref` is non-null.
- Dependencies: MVP1.DB.007
- Effort: 2 hours

**MVP1.DB.009** — Define Drizzle schema for deployment_receipts table
- Deliverable: `deployment_receipts` table with `id`, `solution_id`, `environment_id`, `started_at`, `completed_at`, `status`, `pinned_artifacts` (JSONB), `solution_last_tested`, `solution_age_status`, `pin_health_status`, `final_logs_ref`
- Dependencies: MVP1.DB.002, MVP1.DB.007
- Effort: 2-3 hours

**MVP1.DB.010** — Define Drizzle schema for users and user_attributes
- Deliverable: `users` table with `id`, `keycloak_subject_id`, `email`, `display_name`, `active`. `user_attributes` table with DA group memberships and other OPA-relevant attributes
- Dependencies: MVP1.DB.001
- Effort: 3-4 hours

**MVP1.DB.011** — Define Drizzle schema for audit_events table
- Deliverable: `audit_events` table conforming to OCSF schema per ADR-0003. Append-only enforced by Postgres trigger or app-level convention.
- Dependencies: MVP1.DB.001, ADR-0003 schema
- Effort: 3-4 hours

**MVP1.DB.012** — Configure Graphile Worker
- Deliverable: Graphile Worker tables created via its migration; worker process bootstraps in Z-WORKER service
- Dependencies: MVP1.DB.001
- Effort: 3-4 hours

**MVP1.DB.013** — Generate initial migration set and commit
- Deliverable: All MVP1 schema migrations generated by `drizzle-kit`, committed, and applied successfully
- Dependencies: All MVP1.DB.* schema tasks
- Effort: 1-2 hours

---

### MVP1.LIB — Library and Gitea Integration

**MVP1.LIB.001** — Bundle Gitea in FUSION Helm chart
- Deliverable: Gitea deploys as part of Helm install with persistent storage
- Dependencies: Helm chart skeleton
- Effort: 4-6 hours

**MVP1.LIB.002** — Configure Gitea organization and initial repos
- Deliverable: `FUSION_ORG` org created with `fusion-core`, `fusion-nodes`, `fusion-adapters`, `fusion-policies`, `fusion-schemas` repos
- Dependencies: MVP1.LIB.001
- Effort: 2 hours

**MVP1.LIB.003** — Configure Gitea branch protection rules
- Deliverable: `main` branch on every repo cannot be force-pushed; PRs required for merge
- Dependencies: MVP1.LIB.002
- Effort: 1-2 hours

**MVP1.LIB.004** — Define node definition YAML schema
- Deliverable: JSON Schema document defining the structure of a node `definition.yaml` (metadata, variables_schema, valid_connections, teardown_capability, criticality)
- Dependencies: none
- Effort: 3-4 hours

**MVP1.LIB.005** — Define adapter definition YAML schema
- Deliverable: JSON Schema document defining the structure of an adapter `definition.yaml` (source_type, target_type, adapter_kind, tier, criticality, teardown_capability, variables_schema)
- Dependencies: none
- Effort: 3-4 hours

**MVP1.LIB.006** — Implement Gitea webhook receiver in Z-API
- Deliverable: Z-API endpoint accepts Gitea webhook POSTs with signature validation; logs received events
- Dependencies: Z-API scaffold, Gitea available
- Effort: 3-4 hours

**MVP1.LIB.007** — Implement basic Gitea→DB sync handler
- Deliverable: On push-to-main webhook, Z-API fetches changed files via Gitea API, parses YAML definitions, upserts into DB with new `git_sha`
- Dependencies: MVP1.LIB.006, MVP1.DB.003, MVP1.DB.004
- Effort: 6-8 hours
- Note: This is the "basic" sync, not the full mechanics covered by Spike 1. Edge cases are simplified for MVP1.

**MVP1.LIB.008** — Define solution repo template
- Deliverable: A template repo structure for `solution-*` repos (manifest, references to nodes/adapters with git_sha pinning)
- Dependencies: MVP1.LIB.004, MVP1.LIB.005
- Effort: 3-4 hours

---

### MVP1.API — Fastify API Routes

**MVP1.API.001** — Implement health check endpoint
- Deliverable: `GET /api/health` returns 200 with version, db status, gitea status, keycloak status
- Dependencies: backend scaffold
- Effort: 2 hours

**MVP1.API.002** — Implement user info endpoint
- Deliverable: `GET /api/me` returns current user from JWT, with Zod schemas registered for response
- Dependencies: MVP1.AUTH.005
- Effort: 2 hours

**MVP1.API.003** — Implement solutions list endpoint
- Deliverable: `GET /api/solutions` returns list of solutions visible to user (OPA-checked), with Zod schemas
- Dependencies: MVP1.DB.002, MVP1.AUTH.008
- Effort: 3 hours

**MVP1.API.004** — Implement solution get endpoint
- Deliverable: `GET /api/solutions/:id` returns solution with composition (nodes, edges, environment binding) and pinned definitions
- Dependencies: MVP1.API.003, MVP1.DB.005, MVP1.DB.006
- Effort: 4 hours

**MVP1.API.005** — Implement solution create endpoint
- Deliverable: `POST /api/solutions` creates a new solution with required project metadata
- Dependencies: MVP1.API.003
- Effort: 3 hours

**MVP1.API.006** — Implement solution update endpoint
- Deliverable: `PUT /api/solutions/:id` updates solution composition (nodes, edges, variable bindings); preserves git_sha pinning
- Dependencies: MVP1.API.004
- Effort: 4 hours

**MVP1.API.007** — Implement environment profile endpoints
- Deliverable: `GET /api/environments`, `POST /api/environments`, `PUT /api/environments/:id`
- Dependencies: MVP1.DB.007, MVP1.DB.008
- Effort: 4-5 hours

**MVP1.API.008** — Implement nodes registry endpoint
- Deliverable: `GET /api/nodes` returns synced node registry with git_sha
- Dependencies: MVP1.LIB.007
- Effort: 2-3 hours

**MVP1.API.009** — Implement adapters registry endpoint with type-pair filter
- Deliverable: `GET /api/adapters?source_type=X&target_type=Y` returns valid adapters for that pair
- Dependencies: MVP1.LIB.007
- Effort: 3 hours

**MVP1.API.010** — Implement pre-flight validation endpoint
- Deliverable: `POST /api/solutions/:id/preflight` returns validation result for solution + environment combination
- Dependencies: MVP1.API.004, MVP1.API.007
- Effort: 6-8 hours

**MVP1.API.011** — Implement deployment dispatch endpoint
- Deliverable: `POST /api/solutions/:id/deploy` creates deployment record, dispatches Graphile Worker job, returns job ID and WebSocket URL
- Dependencies: MVP1.API.010, MVP1.DB.009, MVP1.DB.012
- Effort: 6-8 hours

**MVP1.API.012** — Implement deployment status endpoint
- Deliverable: `GET /api/deployments/:id` returns deployment state with full receipt
- Dependencies: MVP1.API.011
- Effort: 3 hours

**MVP1.API.013** — Implement WebSocket endpoint for live deployment output
- Deliverable: `WS /api/deployments/:id/stream` streams stdout/stderr from Z-WORKER to frontend
- Dependencies: MVP1.API.011
- Effort: 6-8 hours

**MVP1.API.014** — Add OPA authorization check to all mutation routes
- Deliverable: Every POST/PUT/DELETE endpoint calls `authz.can()` before proceeding
- Dependencies: MVP1.AUTH.008
- Effort: 4-6 hours

**MVP1.API.015** — Add audit emit to all security-relevant routes
- Deliverable: Every security-relevant action calls `audit.emit()` with conformant OCSF event
- Dependencies: MVP1.AUDIT.003
- Effort: 4-6 hours

**MVP1.API.016** — Register Zod schemas on every Fastify route (close F-019)
- Deliverable: Every route definition includes `schema: { body, response }` with Zod-derived JSON Schema
- Dependencies: All MVP1.API.* route tasks
- Effort: 4-6 hours
- Note: This is a sweep across all routes, not a single task. Could be done route-by-route as routes are written.

---

### MVP1.EXEC — Worker Abstraction and Execution

**MVP1.EXEC.001** — Define worker abstraction interface in shared types
- Deliverable: TypeScript interface for execution worker contract (action, node-type, target, vars, dry-run input; status, logs, state output)
- Dependencies: shared types package
- Effort: 3-4 hours

**MVP1.EXEC.002** — Implement Z-WORKER service skeleton
- Deliverable: Node.js service that polls Graphile Worker queue, dispatches jobs to worker abstraction, reports status
- Dependencies: MVP1.DB.012, MVP1.EXEC.001
- Effort: 6-8 hours

**MVP1.EXEC.003** — Implement subprocess execution adapter
- Deliverable: Worker abstraction implementation that spawns subprocess with restricted env and working directory; captures stdout/stderr
- Dependencies: MVP1.EXEC.001
- Effort: 6-8 hours

**MVP1.EXEC.004** — Implement OpenTofu execution worker
- Deliverable: Worker that wraps OpenTofu CLI with `tofu init`, `tofu plan`, `tofu apply`, `tofu destroy` operations behind the abstraction
- Dependencies: MVP1.EXEC.003
- Effort: 6-8 hours

**MVP1.EXEC.005** — Implement Ansible execution worker
- Deliverable: Worker that wraps `ansible-playbook` with inventory generation and var passing behind the abstraction
- Dependencies: MVP1.EXEC.003
- Effort: 6-8 hours
- Note: Tag all Ansible-specific code with comment markers for future port-effort scoping per Ansible licensing decision.

**MVP1.EXEC.006** — Implement Helm execution worker
- Deliverable: Worker that wraps `helm install`, `helm upgrade`, `helm rollback` behind the abstraction
- Dependencies: MVP1.EXEC.003
- Effort: 4-6 hours

**MVP1.EXEC.007** — Implement output streaming from worker to API
- Deliverable: Worker streams stdout/stderr lines to a Postgres-backed pub/sub or Redis stream that Z-API forwards to WebSocket
- Dependencies: MVP1.EXEC.002, MVP1.API.013
- Effort: 6-8 hours

**MVP1.EXEC.008** — Implement tier-based execution ordering
- Deliverable: Worker dispatcher executes adapters in tier order (Tier 1 → Tier 2 → Tier 3), failing tier blocks subsequent tiers
- Dependencies: MVP1.EXEC.002
- Effort: 6-8 hours

**MVP1.EXEC.009** — Implement basic teardown on failure
- Deliverable: When critical-path failure occurs, worker can execute teardown procedure for everything provisioned so far
- Dependencies: MVP1.EXEC.004, MVP1.EXEC.005, MVP1.EXEC.006
- Effort: 8-12 hours
- Note: Full failure classification UI is V1; MVP1 just needs basic teardown working.

**MVP1.EXEC.010** — Implement deployment receipt finalization
- Deliverable: On deployment completion, worker writes pinned_artifacts (AMI IDs, image digests, chart versions used) to deployment receipt
- Dependencies: MVP1.DB.009, MVP1.EXEC.008
- Effort: 4-6 hours

---

### MVP1.AUDIT — Audit Trail (per ADR-0003)

**MVP1.AUDIT.001** — Commit OCSF audit event JSON Schema to `fusion-schemas` repo
- Deliverable: `audit-event.schema.json` per ADR-0003 with all required fields
- Dependencies: MVP1.LIB.002
- Effort: 3-4 hours

**MVP1.AUDIT.002** — Generate TypeScript types from JSON Schema
- Deliverable: Build step generates TS types from `audit-event.schema.json`; types live in shared package
- Dependencies: MVP1.AUDIT.001
- Effort: 2-3 hours

**MVP1.AUDIT.003** — Implement `audit.emit()` interface
- Deliverable: Function that validates event against schema, then dispatches to current transport implementation
- Dependencies: MVP1.AUDIT.002
- Effort: 4-6 hours

**MVP1.AUDIT.004** — Implement audit transport at chosen stage
- Deliverable: Either S1 (Postgres direct write) OR S2 (NATS JetStream) per CLI consolidation decision
- Dependencies: MVP1.AUDIT.003; CLI consolidation decision on stage
- Effort: 6-8 hours (S1) or 12-16 hours (S2)
- 🚫 **BLOCKED on stage decision** — to be resolved at CLI consolidation

**MVP1.AUDIT.005** — Add audit emit to authentication events
- Deliverable: Login, logout, token refresh, failed auth all emit OCSF events
- Dependencies: MVP1.AUDIT.003, MVP1.AUTH.004, MVP1.AUTH.005
- Effort: 3-4 hours

---

### MVP1.CANVAS — React Flow Canvas

**MVP1.CANVAS.001** — Set up React Flow with TypeScript
- Deliverable: Empty canvas page renders, React Flow installed and configured
- Dependencies: frontend scaffold
- Effort: 2-3 hours

**MVP1.CANVAS.002** — Implement custom node component
- Deliverable: Custom node renderer that displays node name, type icon, status indicator
- Dependencies: MVP1.CANVAS.001
- Effort: 4-6 hours

**MVP1.CANVAS.003** — Implement node drag-from-palette
- Deliverable: Engineer can drag nodes from left pane onto canvas; node persists in canvas state
- Dependencies: MVP1.CANVAS.002
- Effort: 4-6 hours

**MVP1.CANVAS.004** — Implement custom edge component with adapter rendering
- Deliverable: When connection drawn between two nodes, adapter icon renders in middle of edge
- Dependencies: MVP1.CANVAS.002
- Effort: 6-8 hours

**MVP1.CANVAS.005** — Implement adapter resolution on connect
- Deliverable: When user draws connection, frontend queries `/api/adapters?source_type=X&target_type=Y`; if multiple results, presents selection modal
- Dependencies: MVP1.CANVAS.004, MVP1.API.009
- Effort: 4-6 hours

**MVP1.CANVAS.006** — Implement adapter status (green/red)
- Deliverable: Adapter icon shows green border when all required vars are filled, red when missing or invalid
- Dependencies: MVP1.CANVAS.004
- Effort: 3-4 hours

**MVP1.CANVAS.007** — Implement property grid (right-click reveals)
- Deliverable: Right-click on node opens docked property grid showing schema-driven properties; values are editable; auto-saves on change
- Dependencies: MVP1.CANVAS.002
- Effort: 8-12 hours

**MVP1.CANVAS.008** — Implement canvas save to backend
- Deliverable: Canvas state (nodes, edges, properties) persists to backend via `PUT /api/solutions/:id` on debounced changes
- Dependencies: MVP1.CANVAS.007, MVP1.API.006
- Effort: 4-6 hours

**MVP1.CANVAS.009** — Implement canvas load from backend
- Deliverable: Existing solution loads into canvas with all nodes, edges, adapters, and pinned definitions
- Dependencies: MVP1.CANVAS.008, MVP1.API.004
- Effort: 4-6 hours

---

### MVP1.UI — Other Frontend (Wizard, Panes, Project Page)

**MVP1.UI.001** — Implement 4-pane GUI layout
- Deliverable: CSS grid layout with Left, Center, Right, Bottom panes; panes cannot be minimized; sizes are fixed
- Dependencies: frontend scaffold
- Effort: 4-6 hours

**MVP1.UI.002** — Implement Left pane node palette
- Deliverable: Two collapsible groups ("Infrastructure and Networking", "Vendor Connectors"); items are draggable to canvas
- Dependencies: MVP1.UI.001, MVP1.API.008
- Effort: 6-8 hours

**MVP1.UI.003** — Implement Right pane control palette (basic)
- Deliverable: Two collapsible groups ("Controls", "Actions"); MVP1 includes only items needed for demo solution
- Dependencies: MVP1.UI.001
- Effort: 4-6 hours

**MVP1.UI.004** — Implement Bottom pane action bar
- Deliverable: Buttons for Open, Save, Save Workflow Image (deferred to V1), Submit Change/Feature Request (deferred to V1)
- Dependencies: MVP1.UI.001
- Effort: 3-4 hours

**MVP1.UI.005** — Implement project property page
- Deliverable: Form with all required fields per spec (Project Name, Created By auto, Owner, Customer/Program, Original Purpose dropdown with Other text field, Problem Statement, Outcome Statement, Date auto)
- Dependencies: MVP1.API.005
- Effort: 6-8 hours

**MVP1.UI.006** — Implement environment profile selector
- Deliverable: Dropdown to select existing environment profile or create new; profile binding persists with solution
- Dependencies: MVP1.API.007
- Effort: 4-6 hours

**MVP1.UI.007** — Implement pre-flight wizard step 1 (environment selection)
- Deliverable: Wizard step that confirms environment profile, lists what will be provisioned
- Dependencies: MVP1.UI.006
- Effort: 4-6 hours

**MVP1.UI.008** — Implement pre-flight wizard step 2 (FUSION-provisioned resources)
- Deliverable: Wizard step that displays resources FUSION will create, with editable variables
- Dependencies: MVP1.UI.007, MVP1.API.010
- Effort: 6-8 hours

**MVP1.UI.009** — Implement pre-flight wizard step 3 (external dependencies)
- Deliverable: Wizard step that prompts for external dependencies declared in solution manifest
- Dependencies: MVP1.UI.008
- Effort: 6-8 hours

**MVP1.UI.010** — Implement pre-flight wizard step 4 (active validation)
- Deliverable: Wizard step that runs validation checks (where allowed by environment profile trust flag); displays results
- Dependencies: MVP1.UI.009, MVP1.API.010
- Effort: 6-8 hours

**MVP1.UI.011** — Implement pre-flight wizard step 5 (summary and play)
- Deliverable: Final wizard step shows summary; Play button triggers deployment dispatch
- Dependencies: MVP1.UI.010, MVP1.API.011
- Effort: 4-6 hours

**MVP1.UI.012** — Implement deployment status panel
- Deliverable: Panel shows live output from WebSocket; displays status per node and per adapter; shows tier progression
- Dependencies: MVP1.API.013
- Effort: 8-12 hours

**MVP1.UI.013** — Implement deployment receipt view
- Deliverable: After deployment completes, view shows receipt with all pinned artifacts, status, timing, logs reference
- Dependencies: MVP1.API.012
- Effort: 4-6 hours

---

### MVP1.DEMO — Demo Solution (Nodes, Adapters, Solution Definition)

**MVP1.DEMO.001** — Author EC2 Windows Server 2022 STIG node
- Deliverable: Node definition in `fusion-nodes/ec2-windows-dc/` with definition.yaml, main.tf (OpenTofu for EC2), playbook.yml (Ansible for DC promotion), teardown.yml
- Dependencies: MVP1.LIB.004, MVP1.EXEC.004, MVP1.EXEC.005
- Effort: 12-16 hours

**MVP1.DEMO.002** — Author EC2 Ubuntu node
- Deliverable: Node definition in `fusion-nodes/ec2-ubuntu/` with definition.yaml, main.tf, playbook.yml, teardown.yml
- Dependencies: MVP1.LIB.004, MVP1.EXEC.004, MVP1.EXEC.005
- Effort: 8-12 hours

**MVP1.DEMO.003** — Author EC2 Windows endpoint node
- Deliverable: Node definition in `fusion-nodes/ec2-windows-endpoint/` similar to DC but without DC promotion
- Dependencies: MVP1.LIB.004
- Effort: 8-12 hours

**MVP1.DEMO.004** — Author K3s install node
- Deliverable: Node definition that runs on Ubuntu, installs K3s, retrieves kubeconfig
- Dependencies: MVP1.DEMO.002
- Effort: 8-12 hours

**MVP1.DEMO.005** — Author OpenCTI node
- Deliverable: Node definition that deploys OpenCTI Helm chart onto K3s
- Dependencies: MVP1.DEMO.004, MVP1.EXEC.006
- Effort: 8-12 hours

**MVP1.DEMO.006** — Author domain-join adapter (Windows DC → Ubuntu)
- Deliverable: Adapter definition in `fusion-adapters/ec2-windows-dc--ec2-ubuntu/` that joins Ubuntu to AD domain
- Dependencies: MVP1.LIB.005, MVP1.DEMO.001, MVP1.DEMO.002
- Effort: 8-12 hours

**MVP1.DEMO.007** — Author domain-join adapter (Windows DC → Windows endpoint)
- Deliverable: Similar to MVP1.DEMO.006 but for Windows endpoint
- Dependencies: MVP1.LIB.005, MVP1.DEMO.001, MVP1.DEMO.003
- Effort: 6-8 hours

**MVP1.DEMO.008** — Author K3s-on-Ubuntu connect adapter
- Deliverable: Adapter that wires K3s install to a target Ubuntu node
- Dependencies: MVP1.DEMO.002, MVP1.DEMO.004
- Effort: 4-6 hours

**MVP1.DEMO.009** — Author OpenCTI-on-K3s connect adapter
- Deliverable: Adapter that wires OpenCTI deployment to a target K3s node
- Dependencies: MVP1.DEMO.004, MVP1.DEMO.005
- Effort: 4-6 hours

**MVP1.DEMO.010** — Compose demo solution
- Deliverable: Solution definition in `solution-dc-lab/` that references all demo nodes and adapters with proper pinning
- Dependencies: All MVP1.DEMO.* node and adapter tasks
- Effort: 4-6 hours

**MVP1.DEMO.011** — Test full demo solution deployment end-to-end
- Deliverable: Solution deploys cleanly to Cove.GDIT, all components functional, deployment receipt captured
- Dependencies: MVP1.DEMO.010, all MVP1.EXEC.* tasks, all MVP1.API.* tasks
- Effort: 12-20 hours (significant debugging time expected)

---

### MVP1.DEPLOY — FUSION's Own Deployment

**MVP1.DEPLOY.001** — Define FUSION Helm chart skeleton
- Deliverable: `helm/fusion/` directory with `Chart.yaml`, `values.yaml`, basic templates
- Dependencies: none
- Effort: 4-6 hours

**MVP1.DEPLOY.002** — Add PostgreSQL subchart
- Deliverable: PostgreSQL deploys as part of FUSION install
- Dependencies: MVP1.DEPLOY.001, MVP1.DB.001
- Effort: 3-4 hours

**MVP1.DEPLOY.003** — Add Gitea subchart or in-chart deployment
- Deliverable: Gitea deploys as part of FUSION install
- Dependencies: MVP1.DEPLOY.001, MVP1.LIB.001
- Effort: 4-6 hours

**MVP1.DEPLOY.004** — Add Keycloak subchart
- Deliverable: Keycloak deploys as part of FUSION install
- Dependencies: MVP1.DEPLOY.001, MVP1.AUTH.001
- Effort: 4-6 hours

**MVP1.DEPLOY.005** — Add OPA in-chart deployment
- Deliverable: OPA deploys as sidecar with policy bundle volume
- Dependencies: MVP1.DEPLOY.001, MVP1.AUTH.006
- Effort: 3-4 hours

**MVP1.DEPLOY.006** — Add Z-API and Z-FRONTEND deployments
- Deliverable: Both services deploy via Helm with proper labels, services, and ingress
- Dependencies: MVP1.DEPLOY.001
- Effort: 6-8 hours

**MVP1.DEPLOY.007** — Add Z-WORKER deployment
- Deliverable: Z-WORKER deploys as separate pod with subprocess execution capability
- Dependencies: MVP1.DEPLOY.001, MVP1.EXEC.002
- Effort: 4-6 hours

**MVP1.DEPLOY.008** — Configure ingress with TLS
- Deliverable: NGINX ingress routes external traffic to Z-FRONTEND and Z-API; TLS certificates configured
- Dependencies: MVP1.DEPLOY.006
- Effort: 4-6 hours

**MVP1.DEPLOY.009** — Set up EC2 host with K3s for FUSION in Cove.GDIT
- Deliverable: EC2 instance running K3s, accessible from authorized GDIT users, Helm chart installable
- Dependencies: AWS access in Cove.GDIT
- Effort: 6-8 hours

**MVP1.DEPLOY.010** — Deploy FUSION to Cove.GDIT and validate end-to-end
- Deliverable: FUSION running in Cove.GDIT, accessible via URL, all services healthy
- Dependencies: MVP1.DEPLOY.009, all bundled service tasks
- Effort: 8-12 hours (debugging expected)

---

### MVP1.DOCS — Documentation

**MVP1.DOCS.001** — Author ADR template
- Deliverable: `docs/adr/template.md` with standard sections
- Dependencies: none
- Effort: 1 hour

**MVP1.DOCS.002** — Author ADRs for major MVP1 decisions
- Deliverable: ADRs for: Drizzle over Prisma, Fastify over alternatives, Graphile Worker over alternatives, Worker abstraction interface, Multi-tenant retrofit insurance, Reversal capability tiers, Pin-with-monitoring fidelity model, Architecture change trigger policy
- Dependencies: MVP1.DOCS.001
- Effort: 8-12 hours total

**MVP1.DOCS.003** — Author node authoring guide (initial)
- Deliverable: `docs/contribution/node-authoring.md` with schema, examples, publication gate criteria, teardown requirements
- Dependencies: MVP1.LIB.004, MVP1.DEMO.001
- Effort: 4-6 hours

**MVP1.DOCS.004** — Author adapter authoring guide (initial)
- Deliverable: `docs/contribution/adapter-authoring.md` with schema, examples, tier guidance, teardown requirements
- Dependencies: MVP1.LIB.005, MVP1.DEMO.006
- Effort: 4-6 hours

**MVP1.DOCS.005** — Author FUSION deployment runbook
- Deliverable: `docs/runbooks/fusion-deployment.md` covering Helm install, configuration, troubleshooting
- Dependencies: MVP1.DEPLOY.010
- Effort: 4-6 hours

**MVP1.DOCS.006** — Author MVP1 demo script for OCTO funding gate
- Deliverable: `docs/demo/octo-q1-demo.md` with step-by-step demo flow, talking points, fallback plans
- Dependencies: MVP1.DEMO.011
- Effort: 4-6 hours

---

### MVP1.OPS — Operational Setup

**MVP1.OPS.001** — Initiate Red Hat exception license conversation
- Deliverable: Email or ticket to GDIT partnerships team requesting Red Hat distribution exception evaluation
- Dependencies: none
- Effort: 1-2 hours
- ⚠️ **PRIORITY: Week 1 of MVP1.** Do not defer.

**MVP1.OPS.002** — Establish Brennon-on-FUSION time commitment in writing
- Deliverable: Email confirmation from Darren that Brennon is X% on FUSION through MVP1
- Dependencies: none
- Effort: 1 hour
- ⚠️ **PRIORITY: Week 1 of MVP1.**

**MVP1.OPS.003** — Schedule architectural review with Darren post-PTO
- Deliverable: Calendar meeting with Darren and Matt to walk through this decomposition output and capability classification
- Dependencies: Darren's return from PTO
- Effort: 1 hour to schedule

**MVP1.OPS.004** — Reconcile this decomposition output with CLI scaffold context
- Deliverable: Variance report identifying differences between this document set and current scaffold; decisions captured for each variance
- Dependencies: All three decomposition documents complete
- Effort: 4-6 hours

---

## PHASE 2 — V1 BACKLOG

### V1.SPIKE — Required Spikes Before V1 Implementation

**V1.SPIKE.001** — Spike: DB↔Gitea Sync Mechanics
- Deliverable: ADR documenting webhook flow, conflict resolution, drift recovery, branch lifecycle, stale canvas detection. Test harness exercising failure modes. Identification of any architectural changes required for V1 sync.
- Dependencies: MVP1 functional with basic sync
- Effort: 1-2 weeks (40-80 hours)
- 🔬 **SPIKE — must complete before V1 sync expansion**

**V1.SPIKE.002** — Spike: Worker Abstraction Interface Validation
- Deliverable: Pyinfra implementation of one MVP1 node behind the worker abstraction; report on interface adequacy or required refinements; estimate of port effort if Ansible must be replaced
- Dependencies: MVP1.EXEC.* complete
- Effort: 3-5 days (24-40 hours)
- 🔬 **SPIKE — insurance against Ansible licensing decision**

**V1.SPIKE.003** — Spike: K8s Job-Based Subprocess Sandboxing
- Deliverable: Working prototype of one node deploying via K8s Job; ADR documenting credential/state/streaming model; identification of constraints
- Dependencies: MVP1.EXEC.* complete; K3s environment available
- Effort: 1-2 weeks (40-80 hours)
- 🔬 **SPIKE — must complete before V1 deployment engine work**

**V1.SPIKE.004** — Spike: OPA Policy Bundle Structure
- Deliverable: Policy bundle template with file organization, package naming, test patterns, integration approach with Fastify; ADR documenting policy update flow and audit integration
- Dependencies: MVP1.AUTH.007 in place
- Effort: 1-2 weeks (40-80 hours)
- 🔬 **SPIKE — must complete before policy surface expansion**

**V1.SPIKE.005** — Spike: Pin-with-Monitoring CI/CD Integration
- Deliverable: Working pin check pipeline for at least one pin type (AMI, container, Helm chart); notification flow validated; ADR documenting credential and notification routing
- Dependencies: MVP1 pinning model in place; CI pipeline exists
- Effort: 1-2 weeks (40-80 hours)
- 🔬 **SPIKE — required for V1 fidelity model operationalization**

---

### V1.AUTH — Authorization Maturity

**V1.AUTH.001** — Implement DA group management UI (admin)
- Deliverable: Admin UI to create DA groups, assign users to groups, grant cross-DA access
- Dependencies: V1.SPIKE.004
- Effort: 16-24 hours

**V1.AUTH.002** — Expand OPA policies for DA-aligned access
- Deliverable: Rego policies that gate node/adapter/solution access by DA membership
- Dependencies: V1.SPIKE.004
- Effort: 12-16 hours

**V1.AUTH.003** — Implement environment-scoped OPA policies
- Deliverable: Rego policies that gate environment access (e.g., only certain users can deploy to production environment profiles)
- Dependencies: V1.SPIKE.004
- Effort: 8-12 hours

**V1.AUTH.004** — Implement OKTA federation in Keycloak
- Deliverable: Production deployment can federate to OKTA in addition to AD
- Dependencies: MVP1 Keycloak in place; OKTA tenant available
- Effort: 8-12 hours

---

### V1.LIB — Library Maturity (Post-Spike 1)

**V1.LIB.001** — Implement webhook retry and recovery
- Deliverable: Failed webhooks are retried; sync handler is idempotent; recovery on duplicate events
- Dependencies: V1.SPIKE.001
- Effort: 8-12 hours

**V1.LIB.002** — Implement stale canvas WebSocket push
- Deliverable: When a node/adapter definition is updated in DB, open canvases referencing it receive WebSocket message; UI shows "updates available" indicator
- Dependencies: V1.SPIKE.001
- Effort: 8-12 hours

**V1.LIB.003** — Implement diff preview for definition updates
- Deliverable: When user clicks "updates available", UI shows diff of what would change; user can accept or stay pinned
- Dependencies: V1.LIB.002
- Effort: 12-16 hours

**V1.LIB.004** — Expand node library — Networking nodes
- Deliverable: Nodes for VPC, Subnet, Security Group, NAT Gateway, Internet Gateway, Route Table
- Dependencies: V1.SPIKE.002
- Effort: 30-40 hours

**V1.LIB.005** — Expand node library — Storage nodes
- Deliverable: Nodes for S3 bucket, EBS volume, EFS share
- Dependencies: V1.SPIKE.002
- Effort: 16-24 hours

**V1.LIB.006** — Expand node library — Compute nodes (additional)
- Deliverable: Nodes for additional EC2 instance types, Lambda function, ECS service
- Dependencies: V1.SPIKE.002
- Effort: 24-40 hours

**V1.LIB.007** — Expand adapter library to cover expanded node combinations
- Deliverable: Adapters for new node combinations introduced in V1.LIB.004-006
- Dependencies: V1.LIB.004, V1.LIB.005, V1.LIB.006
- Effort: 40-60 hours

---

### V1.EXEC — Execution Engine Maturity (Post-Spikes 2 and 3)

**V1.EXEC.001** — Replace subprocess execution with K8s Job execution
- Deliverable: Z-WORKER spawns Kubernetes Jobs instead of local subprocesses; output streams via K8s API or Job-side WebSocket
- Dependencies: V1.SPIKE.003
- Effort: 24-40 hours

**V1.EXEC.002** — Introduce Argo Workflows for orchestration
- Deliverable: Tier-based execution is implemented as Argo workflow templates; Z-WORKER dispatches to Argo
- Dependencies: V1.EXEC.001
- Effort: 30-40 hours

**V1.EXEC.003** — Implement full failure classification engine
- Deliverable: When deployment fails, system classifies failure (critical / non-critical / infrastructure) and prompts user with appropriate options
- Dependencies: V1.EXEC.002
- Effort: 16-24 hours

**V1.EXEC.004** — Implement partial deployment cancellation
- Deliverable: User can cancel mid-deployment; system tears down everything provisioned so far cleanly
- Dependencies: V1.EXEC.003
- Effort: 12-16 hours

**V1.EXEC.005** — Implement adapter retry with state preservation
- Deliverable: When non-critical adapter fails, user can retry that adapter without losing prior progress
- Dependencies: V1.EXEC.003
- Effort: 12-16 hours

---

### V1.SECRETS — OpenBao Integration

**V1.SECRETS.001** — Bundle OpenBao in FUSION Helm chart
- Deliverable: OpenBao deploys as part of Helm install with persistent storage; auto-unseal configured
- Dependencies: none
- Effort: 8-12 hours

**V1.SECRETS.002** — Implement OpenBao client in Z-API
- Deliverable: `secrets.get(ref)` and `secrets.set(ref, value)` helpers using OpenBao API; reads access logged
- Dependencies: V1.SECRETS.001
- Effort: 8-12 hours

**V1.SECRETS.003** — Migrate environment profile secrets to OpenBao
- Deliverable: All `env_variables.secret_ref` values now point to OpenBao paths; .env file no longer in use
- Dependencies: V1.SECRETS.002
- Effort: 8-12 hours

**V1.SECRETS.004** — Implement IAM role-based AWS credentials
- Deliverable: FUSION uses EC2 instance role for AWS API calls instead of static credentials in OpenBao
- Dependencies: V1.SECRETS.003
- Effort: 6-8 hours

**V1.SECRETS.005** — Define secret rotation policies
- Deliverable: OpenBao policies for periodic rotation of credentials; rotation events emit audit events
- Dependencies: V1.SECRETS.002
- Effort: 6-8 hours

---

### V1.OBSERVE — Observability Stack

**V1.OBSERVE.001** — Bundle Loki in FUSION Helm chart
- Deliverable: Loki deploys with persistent storage; configured to receive logs from all FUSION services
- Dependencies: none
- Effort: 6-8 hours

**V1.OBSERVE.002** — Bundle Grafana in FUSION Helm chart
- Deliverable: Grafana deploys with Loki and Prometheus data sources pre-configured
- Dependencies: V1.OBSERVE.001, V1.OBSERVE.003
- Effort: 6-8 hours

**V1.OBSERVE.003** — Bundle Prometheus in FUSION Helm chart
- Deliverable: Prometheus deploys with scrape configs for all FUSION services
- Dependencies: none
- Effort: 6-8 hours

**V1.OBSERVE.004** — Configure Pino to emit JSON logs to Loki
- Deliverable: All FUSION services emit JSON logs that are picked up by Loki
- Dependencies: V1.OBSERVE.001
- Effort: 4-6 hours

**V1.OBSERVE.005** — Build standard Grafana dashboards
- Deliverable: Dashboards for FUSION health, deployment success rates, library usage, audit event volumes
- Dependencies: V1.OBSERVE.002
- Effort: 12-16 hours

**V1.OBSERVE.006** — Graduate audit transport to S2 (NATS) if not already
- Deliverable: NATS JetStream operational, audit events flowing through NATS, transport implementation switched
- Dependencies: per ADR-0003 staging
- Effort: 12-16 hours

---

### V1.UI — UI Maturity

**V1.UI.001** — Introduce Zustand for canvas coordination state
- Deliverable: Canvas-coordination state moves from prop drilling/context to Zustand store
- Dependencies: MVP1 canvas functional
- Effort: 12-16 hours

**V1.UI.002** — Implement Debug Window with validation engine
- Deliverable: Debug window component shows validation issues with click-to-navigate; validation engine evaluates canvas continuously
- Dependencies: V1.UI.001
- Effort: 24-40 hours

**V1.UI.003** — Implement dynamic property grid (connection-aware)
- Deliverable: Property grid surfaces additional properties when nodes are connected, based on connected node types
- Dependencies: V1.UI.001
- Effort: 16-24 hours

**V1.UI.004** — Implement platform notifications via WebSocket push
- Deliverable: Backend can push notifications to all connected users; UI shows notification bell and update prompt
- Dependencies: V1.UI.001
- Effort: 12-16 hours

**V1.UI.005** — Implement update notification flow
- Deliverable: Non-mandatory updates show update button; mandatory updates show modal
- Dependencies: V1.UI.004
- Effort: 8-12 hours

**V1.UI.006** — Implement revision history UI
- Deliverable: Per-solution revision history view with revision messages, dates, authors
- Dependencies: data captured in MVP1
- Effort: 8-12 hours

---

### V1.SUBSOLUTION — Sub-Solution Composition

**V1.SUBSOLUTION.001** — Implement sub-graph selection on canvas
- Deliverable: User can select a subset of nodes/edges; selection is a coherent sub-graph
- Dependencies: MVP1 canvas functional
- Effort: 16-24 hours

**V1.SUBSOLUTION.002** — Implement sub-solution export
- Deliverable: Selected sub-graph can be exported as a sub-solution definition with all node/adapter pinning preserved
- Dependencies: V1.SUBSOLUTION.001
- Effort: 12-16 hours

**V1.SUBSOLUTION.003** — Implement sub-solution import via copy-on-import
- Deliverable: Engineer can import a sub-solution into an existing canvas; imported nodes/adapters are copied with their pinning
- Dependencies: V1.SUBSOLUTION.002
- Effort: 16-24 hours

**V1.SUBSOLUTION.004** — Implement variable namespace handling at import
- Deliverable: Variable names that collide with existing canvas variables are namespace-prefixed; user can review and adjust
- Dependencies: V1.SUBSOLUTION.003
- Effort: 12-16 hours

---

### V1.AI — AI Features (V1 Subset)

**V1.AI.001** — Define abstract `ai.complete()` interface
- Deliverable: TypeScript interface for AI completion calls with prompt, context, and result types
- Dependencies: shared types package
- Effort: 4-6 hours

**V1.AI.002** — Implement first AI backend (cloud)
- Deliverable: Implementation of `ai.complete()` that calls Anthropic Claude API or AWS Bedrock
- Dependencies: V1.AI.001, decision on initial provider
- Effort: 12-16 hours

**V1.AI.003** — Implement LLM-assisted adapter property suggestions
- Deliverable: When adapter is added to canvas, AI suggests likely property values based on connected nodes; suggestions are clearly marked as AI-generated
- Dependencies: V1.AI.002
- Effort: 16-24 hours

**V1.AI.004** — Implement one-way AI notification panel in Debug Window
- Deliverable: Background AI workers can post insights to a non-interactive notification panel; non-blocking
- Dependencies: V1.UI.002, V1.AI.002
- Effort: 12-16 hours

---

### V1.PIN — Pin-with-Monitoring Operationalization (Post-Spike 5)

**V1.PIN.001** — Implement AMI availability check pipeline
- Deliverable: Scheduled job checks AMI IDs against AWS API; updates `pin_health_status`
- Dependencies: V1.SPIKE.005
- Effort: 8-12 hours

**V1.PIN.002** — Implement container image availability check pipeline
- Deliverable: Scheduled job checks image SHAs against container registry; updates pin status
- Dependencies: V1.SPIKE.005
- Effort: 8-12 hours

**V1.PIN.003** — Implement Helm chart availability check pipeline
- Deliverable: Scheduled job checks chart versions against chart repo; updates pin status
- Dependencies: V1.SPIKE.005
- Effort: 6-8 hours

**V1.PIN.004** — Implement pre-deploy pin verification
- Deliverable: When user presses Play, pin checks run synchronously before deployment dispatches; failures block deployment
- Dependencies: V1.PIN.001, V1.PIN.002, V1.PIN.003
- Effort: 8-12 hours

**V1.PIN.005** — Implement age-tiered deployment gates
- Deliverable: Solutions older than 6 months show warning; older than 12 months blocked without override
- Dependencies: deployment dispatch in MVP1
- Effort: 8-12 hours

**V1.PIN.006** — Implement broken-pin notification routing
- Deliverable: Broken pins notify solution owner via configured channel; in-app indicator updated
- Dependencies: V1.PIN.001-003
- Effort: 8-12 hours

---

### V1.REGISTRY — Container Registry Standup

**V1.REGISTRY.001** — Stand up Gitea container registry in Cove.GDIT
- Deliverable: Gitea instance configured for container storage; FUSION images can be pushed
- Dependencies: existing Gitea
- Effort: 6-8 hours

**V1.REGISTRY.002** — Migrate FUSION image references to Gitea registry
- Deliverable: Helm chart values reference Gitea registry by default; override available
- Dependencies: V1.REGISTRY.001
- Effort: 4-6 hours

**V1.REGISTRY.003** — Configure CI to push images to Gitea registry on merge
- Deliverable: PR merges trigger image build and push to Gitea registry
- Dependencies: V1.REGISTRY.001, MVP1.CI.010
- Effort: 6-8 hours

**V1.REGISTRY.004** — Evaluate Harbor migration criteria
- Deliverable: Decision document: do we migrate to Harbor for V1, or stay on Gitea registry? Criteria: vulnerability scanning needed? Image signing mandatory? Replication needed?
- Dependencies: V1.REGISTRY.001
- Effort: 4-6 hours (decision); 24-40 hours if migration is approved

---

### V1.DODAF — DoDAF Diagram Export

**V1.DODAF.001** — Implement SV-1 styled diagram export
- Deliverable: Export current canvas as SV-1-styled SVG/PNG
- Dependencies: canvas functional
- Effort: 16-24 hours

**V1.DODAF.002** — Implement SV-2 styled diagram export
- Deliverable: Export current canvas as SV-2-styled SVG/PNG
- Dependencies: canvas functional
- Effort: 16-24 hours

---

### V1.ZT — Zero Trust Integration (V1 Subset)

**V1.ZT.001** — Add ZT compliance metadata fields to node/adapter schema
- Deliverable: Schema includes `zt_pillars` (array) and `zt_activities` (array) fields
- Dependencies: MVP1 schemas
- Effort: 4-6 hours

**V1.ZT.002** — Implement ZT coverage summary view
- Deliverable: Per-solution view shows which ZT pillars/activities are covered by the composition
- Dependencies: V1.ZT.001
- Effort: 12-16 hours

**V1.ZT.003** — Engage EVEREST on ZT activity mapping (if engaged)
- Deliverable: ZT activity reference data populated via EVEREST collaboration
- Dependencies: EVEREST engagement decision
- Effort: variable

---

## PHASE 3 — V2 BACKLOG (Outline)

V2 tasks are intentionally outlined at coarser grain. The dedicated product team that owns V2 will refine these to small-grain tasks during their planning phase. This outline preserves intent and dependency without prescribing implementation details that the product team will determine.

### V2.EAGER — Eager Execution Mode (Post-Spike 5 work)
- Per-canvas eager execution toggle
- Continuous node-readiness evaluation engine
- Cost/resource preview for eager mode
- Confirmation prompts and visual states for partially-deployed resources
- Cancellation flow for in-flight eager deployments

### V2.COLLAB — Real-Time Collaborative Canvas
- CRDT or operational transform implementation for canvas state
- Presence tracking with user initials bubbles
- Concurrent edit conflict resolution
- Replaces V1's branch-based collaboration for power-user scenarios

### V2.LIVING — Real-Time Living Artifact Generation
- Continuous compilation of canvas changes to underlying IaC files
- Partial/invalid canvas state handling
- Conflict resolution between concurrent canvas-to-artifact compilations

### V2.AI — Advanced AI Capabilities
- AI-generated Zero Trust documentation
- AI-generated Zero Trust playbooks and configuration
- Synthetic test deployment definition (research spike required)
- Real-time feasibility checking
- Category-based universal adapters (LUNA collaboration)

### V2.AIRGAP — Customer Air-Gap Distribution
- Tarball-based image bundle generation
- Manifest signing for supply chain integrity
- Customer-side import scripts
- Documentation for varied transit methods

### V2.DODAF — Formally Compliant DoDAF Artifacts
- DoDAF schema mapping
- Compliant SV-1 / SV-2 generation
- Suitability for actual architecture review submission

### V2.SAAS — Multi-Tenant SaaS Capability
- Per-tenant data isolation enforcement
- Tenant onboarding flows
- License-tier policy enforcement (OPA-based)
- Billing integration (if SaaS model selected)

### V2.PARTNER — Vendor Partnership Surface
- External contribution workflow
- Trust and verification model for non-GDIT contributions
- Adapter and node submission process

### V2.SUBSOLUTION — Sub-Solution Maturity
- Variable conflict resolution UI on import
- Versioned sub-solution catalog

---

## Backlog Summary

### MVP1 Task Count by Area
- CI: 10 tasks
- AUTH: 9 tasks
- DB: 13 tasks
- LIB: 8 tasks
- API: 16 tasks
- EXEC: 10 tasks
- AUDIT: 5 tasks
- CANVAS: 9 tasks
- UI: 13 tasks
- DEMO: 11 tasks
- DEPLOY: 10 tasks
- DOCS: 6 tasks
- OPS: 4 tasks

**Total MVP1 tasks: 124**
**Estimated MVP1 effort range: 800-1200 hours**

This fits within the ~1,600-1,800 hour MVP1 capacity envelope (after subtracting Claude Code tokens, AWS costs, and contingency from $300K), with margin for debugging, integration friction, and the inevitable scope discovery that occurs during build.

### V1 Task Count by Area
- SPIKE: 5 tasks (each 1-2 weeks)
- AUTH: 4 tasks
- LIB: 7 tasks
- EXEC: 5 tasks
- SECRETS: 5 tasks
- OBSERVE: 6 tasks
- UI: 6 tasks
- SUBSOLUTION: 4 tasks
- AI: 4 tasks
- PIN: 6 tasks
- REGISTRY: 4 tasks
- DODAF: 2 tasks
- ZT: 3 tasks

**Total V1 tasks: 61 (with 5 prerequisite spikes)**
**Estimated V1 effort range: 800-1400 hours**

### V2 Outline (Refined by Product Team)
- 8 areas outlined; small-grain tasks deferred to product team planning

---

**End of Document 3.** Companion documents:

- **Document 1:** Architecture Breakdown
- **Document 2:** Phased Build Plan

---

## Reconciliation Checklist for CLI Consolidation

When merging this backlog with the existing CLI scaffold context, work through this checklist:

1. ⬜ Identify which MVP1 tasks have already been completed by scaffold work. Mark them ✅. Verify deliverables match.
2. ⬜ Identify which MVP1 tasks are in progress. Mark them 🔄. Verify approach matches task description.
3. ⬜ Identify scaffold work that isn't in this backlog. Add as new tasks OR justify why they don't belong.
4. ⬜ Identify backlog tasks that conflict with scaffold approach. Resolve via ADR.
5. ⬜ Resolve audit transport stage decision (S1 vs S2) for MVP1.AUDIT.004.
6. ⬜ Confirm Ansible licensing decision is on track or update fallback plan accordingly.
7. ⬜ Schedule Spike 1 (DB↔Gitea) timing relative to MVP1 completion.
8. ⬜ Confirm spike ownership assignments with Darren and Matt.
9. ⬜ Validate effort estimates against team velocity from MVP1 actuals (once available).
10. ⬜ Surface any task this backlog missed that scaffold work has revealed as necessary.
