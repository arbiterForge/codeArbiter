# FUSION — Architecture Breakdown

**Document 1 of 3** | Companion to: Phased Build Plan, Task Backlog
**Decomposition source:** Desktop Claude architectural session, May 2026
**Status:** Authoritative architectural source of truth — to be reconciled against existing scaffold
**Revision:** Final (Phase 3) — incorporates stable decision IDs, anchor-based cross-references, standardized LOCKED/OPEN/DEFERRED vocabulary

---

## How to Use This Document

This document is the canonical architectural source of truth for FUSION as of the close of the decomposition session. It is intended to be injected into the Claude CLI project context to arbitrate variance with any pre-existing scaffold or ADR work.

**Decision ID convention:** Every architectural decision in this document is tagged with a stable identifier in the form `<AREA>.<SUBAREA>.<NAME>` (e.g., `STACK.BACKEND.FRAMEWORK`). These IDs are referenced by the `fusion-arbiter` skill. The canonical list lives in the skill's `references/decision-categories.md`.

**Status vocabulary (used consistently throughout all three artifacts):**

- **LOCKED** — decision is made; scaffold should reflect it; divergence is a variance requiring arbitration
- **OPEN** — decision is awaiting input; not a variance until closed
- **DEFERRED** — decision is intentionally postponed to a later phase; scaffold should not pre-implement

**Reconciliation protocol when consuming this document:**

1. For each architectural decision below, compare against current codebase and ADRs.
2. If they agree, no action needed.
3. If they disagree, surface the disagreement explicitly. Either:
   - Update this document with the rationale for the divergence (existing scaffold has context this document lacks), or
   - Update the scaffold/ADR to align with this document (this document has cross-cutting context the local decision lacked).
4. Do not silently choose one or the other. Capture the decision either way.

**Known existing scaffold elements with potential variance:**

- Backend uses Fastify 5 + Drizzle + Zod (this doc concurs)
- Frontend currently uses Context + Router loaders + URL params + local state (this doc concurs for MVP1, prescribes Zustand inflection point at V1)
- ADR-0003 establishes OCSF audit schema with abstract emit interface and four-stage transport progression — this doc concurs and flags only the MVP1 stage selection (S1 vs S2) as open
- F-019 (route-level Zod schema registration) is identified as an open gap; this doc prescribes closing it before MVP1 ships
- NATS JetStream chosen for audit at S2 — this doc accepts ADR-0003 architecture, flags only sequencing question

---

## 1. System Overview

FUSION is an internal-first platform for GDIT solutions engineers to design, save, and redeploy modular MOSA-based solutions via a React Flow canvas. It is backed by a Git-authoritative library, executes deployments via IaC tooling, and is architected to evolve from internal tool → exportable IaC playbook generator → multi-tenant SaaS without re-architecture.

**Primary user:** GDIT solutions engineers and CTO capability team members.
**Primary problem:** PoC rot — solutions decay between demos because they require constant patching rather than redeploy-on-demand.
**Operating definition of "working":** Engineer loads a solution, binds it to an environment profile, satisfies pre-flight requirements, presses play, and has a fully integrated solution in under two hours.
**Out of scope:** Operations and maintenance of deployed solutions, drift detection, ongoing health monitoring.

**Architectural posture:** Internal-first with multi-tenant retrofit awareness (`tenant_id` columns from MVP1). Self-contained packaging mandate (single Helm chart deployable into K3s/K8s with no external runtime SaaS dependencies, with Ansible exception pending legal review).

**Positioning:** "Make strict adherence to mandates as friendly as possible."

---

## 2. Component Diagram

```
┌────────────────────────────────────────────────────────────────────────────┐
│                          USER (Solutions Engineer)                         │
└──────────────────────────────────┬─────────────────────────────────────────┘
                                   │ HTTPS / WebSocket
                                   │
┌──────────────────────────────────┴─────────────────────────────────────────┐
│                            FUSION HELM CHART                               │
│                  (deploys into K3s/K8s — self-contained)                   │
│                                                                            │
│  ┌──────────────────────────────────────────────────────────────────────┐  │
│  │                    Z-FRONTEND  (React + React Flow + TS)             │  │
│  │  - 4-pane GUI: Left (nodes), Center (canvas), Right (controls),      │  │
│  │    Bottom (actions)                                                  │  │
│  │  - Property grid (docked, context-aware)                             │  │
│  │  - Adapter auto-rendering on connection edges                        │  │
│  │  - Pre-flight wizard, environment selector, deployment status panel  │  │
│  │  - Debug window (validation issues, click-to-navigate)               │  │
│  │  - State: Context (auth) + Router loaders (server data) + URL params │  │
│  │    (wizard) + local (UI). Zustand introduced at V1 canvas inflection │  │
│  └────────────────────┬─────────────────────────────────────────────────┘  │
│                       │ HTTPS API + WebSocket                              │
│  ┌────────────────────┴─────────────────────────────────────────────────┐  │
│  │                    Z-API  (Fastify 5 + TypeScript)                   │  │
│  │  - Solution CRUD, environment profile CRUD                           │  │
│  │  - Pre-flight validation orchestration                               │  │
│  │  - Deployment dispatch (creates job, returns job ID)                 │  │
│  │  - WebSocket relay for live deployment output                        │  │
│  │  - OPA policy evaluation on every authorized action                  │  │
│  │  - Audit emit on every security-relevant action (per ADR-0003)       │  │
│  │  - Zod validation on every route (input AND response — closes F-019) │  │
│  └─────┬────────────────┬────────────────┬────────────────┬─────────────┘  │
│        │                │                │                │                │
│  ┌─────┴──────┐  ┌──────┴──────┐  ┌──────┴──────┐  ┌──────┴──────────┐    │
│  │  Z-DB      │  │  Z-AUTHZ    │  │  Z-AUTHN    │  │  Z-WORKER       │    │
│  │ Postgres   │  │   OPA       │  │  Keycloak   │  │ (Node.js exec)  │    │
│  │            │  │             │  │             │  │                 │    │
│  │ - solutions│  │ - policies  │  │ - OIDC      │  │ - Pulls jobs    │    │
│  │ - nodes    │  │   from Gitea│  │ - Federates │  │   from queue    │    │
│  │ - adapters │  │ - decision  │  │   to AD,    │  │ - Spawns        │    │
│  │ - environ. │  │   logging   │  │   OKTA, or  │  │   subprocess    │    │
│  │   profiles │  │             │  │   customer  │  │   (MVP) or K8s  │    │
│  │ - deploy.  │  │             │  │   IdP       │  │   Job (V1+)     │    │
│  │   receipts │  │             │  │             │  │ - Streams       │    │
│  │ - audit    │  │             │  │             │  │   output to API │    │
│  │   events   │  │             │  │             │  │ - Calls worker  │    │
│  │ - jobs     │  │             │  │             │  │   abstraction:  │    │
│  │   (Graphile│  │             │  │             │  │   OpenTofu →    │    │
│  │    Worker) │  │             │  │             │  │   Ansible →     │    │
│  │ - tenant_id│  │             │  │             │  │   Helm          │    │
│  └─────┬──────┘  └─────────────┘  └─────────────┘  └────┬────────────┘    │
│        │                                                 │                  │
│        │                                                 │ Spawns           │
│        │                                                 ▼                  │
│        │                                         ┌─────────────────┐       │
│        │                                         │  EXECUTION      │       │
│        │                                         │  WORKERS        │       │
│        │                                         │                 │       │
│        │                                         │  - OpenTofu     │       │
│        │                                         │    (MPL 2.0)    │       │
│        │                                         │  - Ansible      │       │
│        │                                         │    (GPL — TBD)  │       │
│        │                                         │  - Helm         │       │
│        │                                         │    (Apache 2.0) │       │
│        │                                         │                 │       │
│        │                                         │  Behind a       │       │
│        │                                         │  worker         │       │
│        │                                         │  abstraction    │       │
│        │                                         │  interface;     │       │
│        │                                         │  swappable.     │       │
│        │                                         └────┬────────────┘       │
│        │                                              │                    │
│  ┌─────┴────────────────────────────────────────┐    │                    │
│  │                Z-LIBRARY                     │    │                    │
│  │              Gitea (bundled)                 │    │                    │
│  │                                              │    │                    │
│  │  Repos:                                      │    │                    │
│  │  - fusion-core (FUSION app source)           │    │                    │
│  │  - fusion-nodes (node defs + IaC code)       │    │                    │
│  │  - fusion-adapters (typed A→B integrations)  │    │                    │
│  │  - solution-* (per-solution repos)           │    │                    │
│  │  - fusion-policies (OPA Rego)                │    │                    │
│  │  - fusion-schemas (OCSF, JSON Schema)        │    │                    │
│  │                                              │    │                    │
│  │  Webhooks → Z-API → DB sync                  │    │                    │
│  │  No force-push to main; PR-only              │    │                    │
│  └──────────────────────────────────────────────┘    │                    │
│                                                       │                    │
│  ┌──────────────────────────────────────────────┐    │                    │
│  │                Z-AUDIT                       │    │                    │
│  │   Per ADR-0003 (OCSF schema, abstract emit)  │    │                    │
│  │                                              │    │                    │
│  │   MVP1: S1 or S2 (sequencing decision        │    │                    │
│  │   pending CLI consolidation review)          │    │                    │
│  │   V1+: NATS JetStream                        │    │                    │
│  │   V3+: Kafka if env-native                   │    │                    │
│  │   V4+: WORM-locked + hash-chain              │    │                    │
│  └──────────────────────────────────────────────┘    │                    │
└───────────────────────────────────────────────────────┼────────────────────┘
                                                        │
                                                        │ Provisions
                                                        ▼
                              ┌───────────────────────────────────────────┐
                              │           DEPLOYMENT TARGETS              │
                              │                                           │
                              │  MVP1 development environment:            │
                              │  AWS / Cove.GDIT (dev choice, not limit)  │
                              │   - EC2 instances (DC, Ubuntu, endpoint)  │
                              │   - VPC, security groups                  │
                              │   - K3s cluster on Ubuntu EC2             │
                              │   - OpenCTI on K3s                        │
                              │                                           │
                              │  Architectural scope (provider-agnostic   │
                              │  via OpenTofu providers):                 │
                              │   - Cloud: AWS, Azure, GCP, etc.          │
                              │   - On-premise infrastructure:            │
                              │     vSphere, Nutanix, OpenStack,          │
                              │     bare metal                            │
                              │   - Air-gapped customer environments      │
                              │                                           │
                              │  Solutions declare external dependencies  │
                              │  via brownfield manifest:                 │
                              │   - Required existing tools (e.g. Splunk) │
                              │   - Required service accounts             │
                              │   - Required network access               │
                              │   - Required pre-conditions               │
                              └───────────────────────────────────────────┘
```

---

## 3. Component Responsibilities

### 3.1 Z-FRONTEND (React + React Flow + TypeScript)

**Owns:**
- All user interaction surface
- Canvas state during a session (via React Flow's internal store)
- Pre-flight wizard flow
- Property grid rendering and editing
- Debug window display
- WebSocket consumption for live deployment output
- Adapter resolution UI when connections are drawn

**Does not own:**
- Persistent state (DB is owned by Z-API)
- Authorization decisions (OPA via Z-API)
- Identity (Keycloak via Z-API)
- Execution (Z-WORKER)

**State management policy (binding):**
- Server data fetched on route load → Router loaders
- Server data with live updates (V1+) → Zustand subscription + WebSocket
- Auth/identity → React Context
- Canvas coordination across components (V1+) → Zustand
- Component-internal state → useState/useReducer
- Wizard navigation → URL params (bookmarkable, refresh-safe)

**MVP1 boundary:** No third-party state library. Existing scaffold pattern (Context + Router loaders + URL params + local state) is sufficient and should not be replaced. Zustand enters at V1 when canvas interactivity expands beyond drag/drop/save.

**TanStack Query is not adopted.** Router loaders cover the read pattern; mutation-driven invalidation can be handled with router actions + revalidate. Do not introduce TanStack Query unless background refetching or optimistic updates become genuine requirements.

---

### 3.2 Z-API (Fastify 5 + TypeScript)

**Owns:**
- All HTTP and WebSocket endpoints
- Request validation via Zod
- Response serialization via registered Fastify route schemas (closes F-019)
- Solution, node, adapter, environment profile, and deployment receipt CRUD
- Pre-flight validation orchestration
- Job dispatch to Z-WORKER via Graphile Worker
- WebSocket relay between Z-WORKER output and Z-FRONTEND
- OPA policy evaluation calls on every authorized action
- Audit emission per ADR-0003 OCSF schema on every security-relevant action
- Gitea webhook reception and DB sync orchestration

**Does not own:**
- Identity verification (delegated to Keycloak)
- Authorization logic (delegated to OPA)
- Subprocess execution (delegated to Z-WORKER)

**Critical implementation gates:**
- Every route must register Zod schemas for both request body AND response (F-019). Without this, Fastify's `fast-json-stringify` does not strip unknown fields, which is a defense-in-depth security gap.
- Every route handler that mutates state must call `audit.emit()` per ADR-0003.
- Every route handler that requires authorization must call OPA before performing the action.

---

### 3.3 Z-WORKER (Node.js execution dispatch)

**Owns:**
- Pulling deployment jobs from the Graphile Worker queue
- Spawning execution processes (subprocess in MVP1, K8s Job in V1+)
- Streaming subprocess output to Z-API via WebSocket or pubsub
- Reporting job status updates back to the database
- Calling the worker abstraction interface — does NOT call OpenTofu, Ansible, or Helm directly

**Worker abstraction contract:**

Every execution worker must accept:
- `action` — install, configure, connect, teardown
- `node-type` — what is being operated on
- `target` — where to operate
- `vars` — solution variables resolved at deploy time
- `dry-run` flag — validate without executing

Every worker must return:
- `status` — success, failed, partial
- `logs` — streamed output
- `state` — what was actually deployed (for idempotency tracking)

**This abstraction exists specifically so that the Ansible licensing decision can be resolved without re-architecture.** If Ansible must be replaced, only worker implementations change. Z-WORKER orchestration, solution manifests, and node definitions remain unchanged.

**Subprocess sandboxing path:**
- MVP1: subprocess with restricted env vars and working directory. Acceptable because FUSION is internal-only and node definitions come from PR-reviewed Gitea repo. Documented as a known limitation.
- V1: K8s Job-based execution. Each deployment runs in its own pod with scoped service account and limited RBAC. Spike 3 validates this before V1 commits.

---

### 3.4 Z-DB (PostgreSQL — bundled)

**Owns the source of truth for:**
- Active deployment state
- Solution drafts (pre-Gitea promotion)
- Environment profiles
- Deployment receipts (point-in-time snapshots)
- User/role data
- Job queue (via Graphile Worker)
- Audit events (regardless of audit transport stage)
- Synced cache of authoritative library content from Gitea

**Owns the read cache for:**
- Node, adapter, and policy definitions synced from Gitea
- Every cached entity has a `git_sha` column pinning it to a specific authoritative version

**Schema additions locked in MVP1:**
- `tenant_id` column on every solution-related table (multi-tenant retrofit insurance)
- `git_sha` columns on `solution_nodes`, `solution_edges`, etc.
- `adapter_kind` discriminator on adapter definitions
- `teardown_capability` field on nodes and adapters
- `pinned_artifacts`, `solution_last_tested`, `solution_age_status`, `pin_health_status` on solutions
- Audit table conforming to ADR-0003 OCSF schema

**ORM:** Drizzle. No code generation. Schema lives in plain TypeScript at `backend/src/db/schema.ts`. This was a deliberate choice over Prisma because Prisma's separate binary and shadow database requirements are awkward in air-gapped/classified environments.

---

### 3.5 Z-AUTHN (Keycloak — bundled)

**Owns:**
- Identity verification only (no authorization logic)
- OIDC token issuance
- Federation to upstream identity providers per environment:
  - Cove.GDIT lab → AD (LDAP/Kerberos)
  - Production → OKTA
  - Customer air-gapped → customer's AD or IdP
  - Customer cloud-IdP → customer's OIDC/SAML provider

**Does not own:**
- DA group permissions (those are OPA policy)
- Resource-level access (OPA)
- Action authorization (OPA)

**Why this separation matters:** AuthZ logic stays portable across IdPs. Changing IdPs (Cove.GDIT AD → OKTA → customer) is a Keycloak configuration change, not a code change. License-tier gates (future SaaS) become OPA policy additions, not refactor work.

---

### 3.6 Z-AUTHZ (OPA — bundled)

**Owns:**
- All authorization decisions in FUSION
- Policy bundle loaded from `fusion-policies` Gitea repo
- Decision logging (every OPA decision emits an OCSF audit event per ADR-0003)

**Inputs to a decision:**
- Identity claims from Keycloak token
- User attributes from Z-DB (DA group memberships, roles, environment access)
- Resource being accessed
- Action being attempted

**Output:** allow/deny with optional rationale.

**Spike 4 validates the policy bundle structure before V1 commits to expanding the policy surface.**

---

### 3.7 Z-LIBRARY (Gitea — bundled)

**Repository structure:**

```
fusion-core/                    FUSION application source
fusion-nodes/                   Node definitions + IaC code
  ├── ec2-windows-dc/
  │   ├── definition.yaml       (metadata, variable schema, valid connections)
  │   ├── main.tf               (OpenTofu code)
  │   ├── playbook.yml          (Ansible code)
  │   ├── values.yaml           (Helm values, if applicable)
  │   ├── teardown.yml          (reversal procedure — REQUIRED for publication)
  │   └── README.md
  └── ...
fusion-adapters/                Typed A→B integration contracts
  ├── ec2-windows-dc--ec2-ubuntu/
  │   ├── definition.yaml       (source/target types, kind, tier, capability)
  │   ├── connect.yml           (wiring code)
  │   └── README.md
  └── ...
solution-opencti/               Per-solution repos
solution-splunk-itsi/
solution-dc-lab/
fusion-policies/                OPA Rego policies
fusion-schemas/                 OCSF, JSON Schema definitions
```

**Branch protection:** No force-push to main. PR-only merges. Branch protection enforced at Gitea API level.

**Sync model:** Gitea is authoritative. Z-DB is the read cache. UI never reads from Git directly. Webhooks on merge trigger DB sync. Every cached entity carries `git_sha`.

**Spike 1 (DB↔Gitea sync mechanics) is the highest-priority spike before V1 commits to the full multi-user library workflow.**

---

### 3.8 Z-AUDIT (per ADR-0003)

**Architecture (locked):**
- OCSF-aligned schema with ECS field naming where they overlap
- Required `metadata.schema_version` (1.0.0 at launch)
- Abstract `audit.emit()` interface — transport is swappable
- Schema is the single source of truth for backend, frontend, and tests
- TypeScript types derived from JSON Schema, not the reverse

**Transport stages (per ADR-0003):**
- S1 (Prototype): Direct HTTP POST to sink (Postgres table or CloudWatch)
- S2 (Internal MVP): NATS JetStream persistent stream — preferred per ADR
- S3 (Hardened): Kafka if environment is Kafka-native
- S4 (ATO-Ready): WORM-locked sink with hash-chain

**Open decision:** Whether MVP1 ships at S1 or S2. Architecture supports either; transition is mechanical via the abstract interface. To be resolved at CLI consolidation review.

---

## 4. Data Flow Examples

### 4.1 Loading and Deploying a Solution

```
1. Engineer authenticates via Z-AUTHN (Keycloak)
   → Keycloak federates to AD/OKTA/customer IdP
   → Returns OIDC token with identity claims

2. Engineer navigates to "Load a Canvas" in Z-FRONTEND
   → Router loader fetches solution list from Z-API
   → Z-API checks OPA: can(user, "list", "solutions")? → allow
   → Z-API queries Z-DB, returns solution list
   → Audit event emitted: solution_list_accessed

3. Engineer selects a solution, canvas opens
   → Router loader fetches solution + pinned node/adapter definitions
   → Z-API checks OPA: can(user, "read", solution_id)? → allow
   → Z-API queries Z-DB for solution and all referenced git_sha versions
   → Returns full solution composition with pinned definitions
   → Audit event emitted: solution_opened

4. Engineer selects an environment profile
   → Pre-flight wizard activates
   → Wizard step 1: profile selection (or create new)
   → Wizard step 2: confirm FUSION-provisioned resource targets
   → Wizard step 3: external dependency satisfaction
   → Wizard step 4: pre-condition validation (active checks where allowed)
   → Wizard step 5: pre-flight summary

5. Engineer presses Play
   → Z-FRONTEND POSTs deployment request to Z-API
   → Z-API checks OPA: can(user, "deploy", solution_id)? → allow
   → Z-API creates deployment record, dispatches job via Graphile Worker
   → Z-API opens WebSocket for output streaming
   → Z-API returns job ID + WebSocket URL
   → Audit event emitted: deployment_initiated

6. Z-WORKER pulls the job
   → Resolves variables from environment profile and solution config
   → Calls worker abstraction in tier order:
     Tier 1 adapters (infrastructure standup) →
     Tier 2 adapters (service dependencies) →
     Tier 3 adapters (post-integration)
   → Each step streams stdout/stderr through Z-API WebSocket relay to UI
   → Each step emits audit events with class_uid for that action

7. Deployment completes
   → Z-WORKER updates deployment record with final status
   → If success: deployment receipt finalized with pinned_artifacts captured
   → If failure: failure classification engine evaluates failure type
     → Critical path: prompt user (full teardown / leave for inspection)
     → Non-critical: prompt user (retry adapter / skip / teardown)
     → Infrastructure: prompt user (retry full / abort)
   → Audit event emitted: deployment_completed (with outcome)
```

### 4.2 Library Update Propagation

```
1. Developer pushes branch to fusion-nodes repo
2. Developer opens PR
3. CI pipeline runs (linting, schema validation, teardown procedure check)
4. PR merged to main (no force-push, branch protection enforced)
5. Gitea webhook fires to Z-API
6. Z-API sync handler:
   - Fetches changed files from Gitea API
   - Updates Z-DB with new git_sha
   - Marks any open canvases referencing affected definitions with
     "updates available" indicator (via WebSocket push)
7. Audit event emitted: library_definition_updated
8. Pin-monitoring CI runs against the new definition's pinned artifacts
   - If any pin is stale or unreachable: solution flagged with
     missing_required_pin status
```

---

## 5. Stack Locked <a id="stack-locked"></a>

| Decision ID | Layer | Tool | Status | License | Rationale |
|---|---|---|---|---|---|
| `STACK.FRONTEND.FRAMEWORK` | Frontend framework | React + React Flow | LOCKED | MIT | Vision-locked from day one |
| `STACK.FRONTEND.LANGUAGE` | Frontend language | TypeScript | LOCKED | Apache 2.0 | Strict typing essential for agent-coded development |
| `STACK.BACKEND.FRAMEWORK` | Backend framework | Fastify 5 | LOCKED | MIT | Schema-friendly, low overhead, no decorator ceremony |
| `STACK.BACKEND.LANGUAGE` | Backend language | Node.js + TypeScript | LOCKED | MIT | Single-language stack, shared types between frontend and backend |
| `STACK.BACKEND.ORM` | ORM | Drizzle | LOCKED | Apache 2.0 | Query-builder-first, no codegen binary, air-gap friendly |
| `STACK.BACKEND.VALIDATION` | Validation | Zod | LOCKED | MIT | TypeScript-first, route schema integration |
| `STACK.DB.ENGINE` | Database | PostgreSQL | LOCKED | PostgreSQL License | FIPS-compatible builds, STIG'd images, bundleable |
| `STACK.JOB-QUEUE` | Job queue | Graphile Worker | LOCKED | MIT | Postgres-backed, no extra infrastructure |
| `STACK.LIBRARY.GIT` | Library | Gitea | LOCKED | MIT | Self-hostable, MIT, container storage available |
| `STACK.IAC.INFRASTRUCTURE` | IaC infrastructure | OpenTofu | LOCKED | MPL 2.0 | Open Terraform fork, clean for commercial bundling |
| `STACK.IAC.CONFIG-MGMT` | Configuration management | Ansible (community) | OPEN | GPL v3 | Decision pending Red Hat exception — see [§8.1](#ansible-licensing) |
| `STACK.IAC.K8S-DEPLOY` | Application deployment | Helm | LOCKED | Apache 2.0 | Kubernetes-native, industry standard |
| (V1+) | Job orchestration | Argo Workflows | LOCKED | Apache 2.0 | DAG-based, K8s-native, fits canvas model |
| `STACK.AUTH.IDENTITY` | Identity broker | Keycloak | LOCKED | Apache 2.0 | OIDC, federates to AD/OKTA/customer, FIPS builds |
| `STACK.AUTH.AUTHORIZATION` | Authorization | OPA | LOCKED | Apache 2.0 | Policy-as-code, ZT-aligned |
| `STACK.SECRETS.V1` | Secrets (V1+) | OpenBao | LOCKED for V1 | MPL 2.0 | Vault community fork, Linux Foundation |
| `STACK.LOGGING` | Logging | Pino | LOCKED | MIT | Native to Fastify, structured JSON |
| `STACK.OBSERVABILITY.METRICS` | Metrics | OpenTelemetry SDK | LOCKED | Apache 2.0 | Vendor-neutral instrumentation |
| (V1+) | Log aggregation | Loki + Grafana | LOCKED for V1 | Apache 2.0 | Self-contained, queryable |
| (V1+) | Metrics scraping | Prometheus + Grafana | LOCKED for V1 | Apache 2.0 | Industry standard, self-contained |
| `STACK.HOSTING` | Hosting | K3s on EC2 | LOCKED | Apache 2.0 | Lightweight K8s, FIPS-compatible |

**Stack disqualified or rejected:**
- Terraform (BSL since 2023, prohibits commercial competition)
- HashiCorp Vault (BSL since 2023)
- Prisma (separate binary and shadow DB requirements awkward in air-gap)
- NestJS (decorator drift in agent-generated code)
- BullMQ (Redis dependency violates self-contained mandate)
- Puppet, Chef (agent-based, designed for fleet O&M, not on-demand deployment)

---

## 6. Architectural Patterns Locked <a id="patterns-locked"></a>

### 6.1 Worker Abstraction `[PATTERN.WORKER-ABSTRACTION]` LOCKED
Z-WORKER calls an abstract execution worker interface. Today the implementation is Ansible-based; tomorrow it could be Pyinfra, Salt, or custom containerized workers. Solution manifests, node definitions, and Z-WORKER orchestration code are unaffected by which implementation is current.

### 6.2 Multi-Tenant Retrofit Insurance `[PATTERN.MULTI-TENANT-RETROFIT]` LOCKED
Every solution-related table includes a `tenant_id` column from MVP1, defaulting to a single 'gdit' tenant. Zero functional change in MVP1. Eliminates the multi-tenant migration when SaaS ships.

### 6.3 Sub-Solution Composition (Copy-on-Import) `[PATTERN.SUB-SOLUTION-COMPOSITION]` LOCKED
Importing a sub-solution into a parent solution copies its nodes, adapters, and configurations as a snapshot. Updates to the source sub-solution do not propagate. This is a feature, not a bug — projects that imported the old version aren't surprise-broken.

### 6.4 Reversal Capability Tiers `[PATTERN.REVERSAL-TIERS]` LOCKED
Every node and adapter declares its teardown capability:
- `clean` — full automated reversal
- `partial` — automated teardown with documented manual residue
- `manual` — checklist only, no automated teardown

Publication gate: nodes cannot merge to main without a teardown procedure. Brownfield deployments with `manual` reversal require elevated permission and explicit acknowledgment.

### 6.5 Pin-with-Monitoring Deployment Fidelity `[PATTERN.PIN-WITH-MONITORING]` `[PATTERN.AGE-TIERED-DEPLOYMENT-GATES]` LOCKED
Two redeployment modes:
- **Logical reproduction (default):** Adapt to current artifacts (latest STIG'd AMI, current Helm chart version). Solution may behave slightly differently across deployments. Suitable for normal use.
- **Pinned reproduction:** Solution explicitly bound to specific artifact versions. Pin health monitored via CI/CD on configurable schedule. If a pin breaks, solution is flagged. Solutions older than thresholds are gated:
  - 0–6 months: green
  - 6–12 months: yellow (warning + acknowledgment)
  - 12+ months: red (blocked + elevated override required)

No artifact archive infrastructure. Container registry retains internal images while any pin references them; aging-out is the secondary forcing function for solution revalidation.

### 6.6 Eager Execution `[PATTERN.EAGER-EXECUTION]` DEFERRED to V2
MVP1 has no eager execution. V1 builds the foundation (per-node staging declarations, dependency resolver, partial teardown infrastructure). V2 introduces eager execution as a per-canvas toggle, default off. Cost preview always visible when enabled. Justified by defense exercise kit deployments where time-to-deployment is operationally critical.

### 6.7 Brownfield Dependency Declaration `[PATTERN.BROWNFIELD-DEPENDENCY]` LOCKED
Solutions declare external dependencies (existing tools, service accounts, network access, pre-conditions) in their manifest. Pre-flight wizard guides the engineer through satisfying every declared dependency before deployment. Each dependency declares its check tier: `required`, `recommended`, or `skip-in-airgap`.

### 6.8 Architecture Change Trigger Policy `[PATTERN.CHANGE-TRIGGER-POLICY]` LOCKED
Any of the following constitutes a legitimate trigger for stop-and-review:
- External: license/policy denials, dependency relicensing, customer pull, ATO/FedRAMP/IL mandates
- Internal: spike findings, well-supported core team member claims, technical impossibility surfacing

Concerns raised early are inexpensive; concerns raised late are expensive. Team members are expected to surface concerns when meaningfully formed, not when fully proven.

---

## 7. Integrations Catalog

### 7.1 Internal (Bundled in Helm Chart)

| Integration | Purpose | License Status |
|---|---|---|
| PostgreSQL | Application database | Clean |
| Gitea | Library backing | Clean |
| Keycloak | Identity broker | Clean |
| OPA | Authorization | Clean |
| OpenBao (V1+) | Secrets management | Clean |
| Loki + Grafana (V1+) | Log aggregation | Clean |
| Prometheus + Grafana (V1+) | Metrics | Clean |

### 7.2 External (Called at Runtime)

| Integration | Purpose | Air-gap Behavior |
|---|---|---|
| Cloud provider APIs (via OpenTofu) — AWS, Azure, GCP, OCI, etc. | Provisioning compute, network, storage, and managed services for cloud-targeted solutions | Required when target is cloud; not invoked when target is air-gapped on-premise |
| On-premise infrastructure APIs (via OpenTofu) — vSphere, Nutanix Prism, OpenStack, MAAS, etc. | Provisioning VMs, networks, and storage in customer datacenter environments | Available in air-gap when customer's management plane is reachable from FUSION's deployment context |
| Customer IdP | Identity federation (AD/OKTA/etc.) | Required for production deployment in customer environment |
| External tool APIs (Splunk, ServiceNow, etc.) | Brownfield integration per solution manifest | Solution-declared, FUSION never assumes |

**Note on MVP1:** Development targets AWS via Cove.GDIT. This is a development environment choice; the architecture is provider-agnostic by design through OpenTofu's provider model. Adding support for an additional provider (Azure, vSphere, Nutanix, etc.) is a node/adapter authoring task, not a platform re-architecture.

### 7.3 Deployment-Time Only

| Integration | Purpose | Notes |
|---|---|---|
| Container registries (Docker Hub, ghcr.io for MVP1, Gitea registry/Harbor for V1+) | Image source for FUSION's bundled images | MVP1 uses public; V1 stands up GDIT-internal |

---

## 8. Open Architectural Decisions <a id="open-decisions"></a>

These decisions remain OPEN and must be resolved at the indicated milestone. Each is captured with the context required to resolve it. The `fusion-arbiter` skill applies the standardized handling table from `references/known-open-decisions.md` to scaffold state for each.

### 8.1 Ansible Licensing `[STACK.IAC.CONFIG-MGMT]` OPEN — Resolution: Before V1 Planning <a id="ansible-licensing"></a>

**Decision required:** Continue with Ansible after Red Hat exception, or swap to alternative.

**Decision tree:**
- Red Hat grants distribution exception → Continue with Ansible. Self-contained packaging mandate intact.
- Red Hat denies → Two paths:
  - Drop self-contained packaging mandate (Ansible installed separately at runtime)
  - Swap to Pyinfra (MIT) or Salt (Apache 2.0). Self-contained mandate preserved. Lose Jeff's specialization.

**Action:** Brennon initiates Red Hat exception conversation in week 1 of MVP1. Do not wait until end of MVP1.

**Risk mitigation in MVP1:** Limit playbook investment to minimum required for MVP1 demo. Tag Ansible-specific constructs in code for future port-effort scoping.

### 8.2 Audit Transport Stage at MVP1 `[STATE.AUDIT-TRANSPORT]` OPEN — Resolution: CLI Consolidation Review <a id="audit-transport-stage"></a>

**Decision required:** MVP1 ships at S1 (Postgres direct write) or S2 (NATS JetStream as scaffolded).

**Architecture is LOCKED either way per ADR-0003.** Only sequencing differs.

**Context for resolution:**
- ADR-0003 designates S2 as preferred for Internal MVP
- Desktop architectural review surfaced the question of whether S2 infrastructure cost is premature for $300k MVP1 budget and 5 internal users
- Abstract emit interface makes S1→S2 transition mechanical

**Action:** Resolved at consolidation when full codebase context is available — this is exactly what the `fusion-arbiter` skill is designed to facilitate.

### 8.3 AI Integration Architecture OPEN — Resolution: V1 Planning, with LUNA Engagement <a id="ai-integration"></a>

**Decision required:** AI service integration pattern for V1+ features (LLM-assisted adapter property suggestions, debug window AI assistant).

**Pattern recommendation:** Abstract `ai.complete()` interface (similar to audit emit) with swappable backend implementations:
- Cloud (Anthropic Claude API, AWS Bedrock GovCloud) for non-classified deployments
- Self-hosted open weights (Llama via vLLM) for classified/air-gap deployments

**Action:** Not LOCKED at MVP1. LUNA likely engages on this post-MVP1. Feature interface pattern is LOCKED; provider selection is OPEN.

### 8.4 Customer Air-Gap Distribution DEFERRED to V2 <a id="customer-airgap"></a>

**Decision required:** Specific tooling for air-gap packaging (tarball generation, manifest signing, customer-side import scripts).

**Reason for deferral:** Defense customer transit methods vary widely (SIPR transfer, removable media, customer mirror, sneakernet). Designing for one specific pattern would constrain unnecessarily.

**Action:** Address at V2 planning when customer-deployment scenarios are concrete.

### 8.5 Container Registry Migration Trigger OPEN — Resolution: V1 <a id="container-registry"></a>

**Decision required:** Whether Gitea container storage suffices for V1, or whether Harbor migration is required before V1 ships.

**Decision criteria:** Migrate to Harbor when any of:
- Vulnerability scanning becomes a compliance requirement
- Image signing (cosign) becomes mandatory for ATO
- Replication to multiple sites becomes valuable
- Multi-tenant registry isolation becomes needed

**Default:** Start with Gitea container storage at V1 transition. Migrate if criteria are met.

---

## 9. Required Spikes Before V1 Commitment

Six spikes captured. Each is 1-2 weeks of focused work for one engineer. Most can run in parallel after MVP1 is substantially complete. Detailed context is preserved in the Phased Build Plan and Task Backlog.

| # | Spike | Pre-V1? | Owner |
|---|---|---|---|
| 1 | DB↔Gitea Sync Mechanics | Yes (highest priority) | TBD-DARREN-REVIEW — likely Brennon + Matt |
| 2 | Worker Abstraction Interface Validation | Yes | TBD-DARREN-REVIEW — likely Jeff |
| 3 | K8s Job-Based Subprocess Sandboxing | Yes | TBD-DARREN-REVIEW — likely Dan |
| 4 | OPA Policy Bundle Structure | Yes | TBD-DARREN-REVIEW — likely Heather + Brennon |
| 5 | Eager Execution Prep Work Validation | Late V1 | TBD-AVAILABLE |
| 6 | Pin-with-Monitoring CI/CD Integration | V1 | TBD-AVAILABLE |

**Spike list to be reviewed with Darren and Matt the week after Darren returns from PTO.**

---

## 10. Long-Term Vision (Captured but Not Roadmapped)

These are direction-setting items, not commitments:

- **Category-based universal adapters.** Today: Splunk-to-Dynatrace adapter. Future: SIEM-to-APM adapter, generic across specific tool implementations. Likely a LUNA collaboration when AI capabilities mature. Transforms the quadratic adapter problem into a linear one.
- **Living SBOM as architectural byproduct.** The pin-with-monitoring data is a continuously-validated SBOM. Defense customers receiving FUSION outputs get a living SBOM, not a snapshot. Material differentiator at the commercial-product stage.
- **Vendor partnership integration.** If FUSION succeeds, vendors like Splunk may want to participate directly. Architecture supports this — adapter and node definitions are external contributions through the same Gitea PR process FUSION engineers use.
- **Policy-driven licensing.** Future SaaS license tier gates become OPA policy additions, not code changes. Already supported by the Keycloak+OPA architecture.

---

## 11. What This Document Does Not Cover

- Specific UI mockups, color palettes, component library choices (defer to design phase)
- Specific page-by-page navigation flows (covered in scaffold and to evolve)
- Specific Helm chart structure and values schema (covered in deployment scaffold)
- Specific Drizzle schema field types (covered in `backend/src/db/schema.ts`)
- Specific Zod schema definitions (covered in shared types package)
- Specific OPA policy contents (covered post-Spike 4)
- Specific test coverage thresholds and CI configuration (covered in enforcement scaffold task)

These belong in implementation; this document covers architectural decisions only.

---

**End of Document 1.** Companion documents:

- **Document 2:** Phased Build Plan (MVP1 / V1 / V2)
- **Document 3:** Task Backlog (small-grain, prioritized, dependency-flagged)
