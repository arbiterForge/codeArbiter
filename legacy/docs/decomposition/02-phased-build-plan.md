# FUSION — Phased Build Plan

**Document 2 of 3** | Companion to: Architecture Breakdown, Task Backlog
**Decomposition source:** Desktop Claude architectural session, May 2026
**Status:** Authoritative phasing source of truth — to be reconciled against existing scaffold and ADRs
**Revision:** Final (Phase 3) — incorporates phase entry criteria, decision-ID tagging on phase items, standardized LOCKED/OPEN/DEFERRED vocabulary

---

## How to Use This Document

This document defines the phasing of FUSION's build across three named milestones: **MVP1**, **V1**, and **V2**. Each phase has a single-sentence goal, defined scope, explicit deferrals with rationale, identified risks, definition of done, and entry criteria.

**Status vocabulary (consistent across all three artifacts):**
- **LOCKED** — decision is made; scaffold should reflect it
- **OPEN** — decision is awaiting input; not a variance until closed
- **DEFERRED** — decision is intentionally postponed to a later phase

**Decision ID convention:** Phase items reference the decision IDs from Architecture Breakdown §5–§6 in square brackets. The `fusion-arbiter` skill uses these to determine which decisions must be LOCKED before a phase item can ship.

**Reconciliation protocol when consuming this document:**

1. For each item placed in a phase, compare against current scaffold/ADR understanding.
2. If a scaffold item exists that this document classifies in a later phase, surface the variance — either the scaffold work is actually V1 prep that landed early (acceptable) or it represents scope creep into MVP1 (review).
3. If this document classifies an item earlier than current scaffold understanding, surface as a potential acceleration request.
4. Do not silently accept variance. Capture decisions either way.

---

## Phase Overview

| Phase | Window | Funding | Team | Primary Outcome |
|---|---|---|---|---|
| MVP1 | 6 weeks | $300K (IR&D, OCTO Q1) | 1.5 FTE (Brennon + variable Darren pull-in) | Demonstrate architectural integrity with one end-to-end working solution |
| V1 | Post-MVP1, IR&D continuation | TBD (gated by OCTO MVP1 buy-in) | Expanded as funded | Production-ready internal platform with multi-user, full library, complete deployment lifecycle |
| V2 | Post-handoff to product team | Product team budget | Dedicated product team | Customer-deliverable platform with eager execution, advanced AI features, customer air-gap support |

---

## PHASE 1 — MVP1

### Goal

**Demonstrate that FUSION's architectural commitments are buildable and coherent, by delivering one end-to-end deployable solution from canvas to running infrastructure, with the architectural integrity required to convince OCTO this is a foundation worth funding rather than a prototype that needs replacement.**

### Window

6 weeks from kickoff to OCTO Q1 funding gate demo.

### Budget

$300K total including labor, AWS costs, API tokens, licenses, and partnership-sourced NFR licenses.

### Team

- **Brennon** — Technical lead, lead architect, sole coder (with agent assistance). Full-time on FUSION.
- **Darren** — Vision owner, design authority, variable pull-in.
- **Matt** — Programming background. Pull in as needed for code review and specific subsystems.
- **Jeff** — Ansible specialist. Pull in for Ansible-specific playbook authoring.
- **Heather** — Cyber SME. Pull in for ZT alignment review.
- **Dan** — Senior systems engineer. Pull in for K3s/infrastructure questions.

### What's Included

#### 1. Core Platform Scaffold (in progress per existing scaffold)
- React + React Flow + TypeScript frontend
- Fastify 5 + Drizzle + Zod backend
- PostgreSQL bundled
- Helm chart structure for self-contained deployment
- K3s on EC2 in Cove.GDIT for FUSION hosting

#### 2. Authentication and Authorization
- Keycloak bundled in Helm chart
- Federation to Cove.GDIT AD (lab environment)
- OIDC token issuance and validation
- OPA bundled in Helm chart
- Initial OPA policies covering basic role-based access (Solutions Engineer, Admin)
- AuthZ decision logging into audit trail

#### 3. Library and Persistence
- Gitea bundled in Helm chart
- Initial repo structure (fusion-core, fusion-nodes, fusion-adapters, solution-* repos)
- Drizzle schema with all MVP1 tables including `tenant_id`, `git_sha` columns, `adapter_kind` discriminator, `teardown_capability`, pin-related fields
- Local DB ↔ Gitea basic sync (single-instance, single-user simplification acceptable for MVP1)

#### 4. Canvas and UI
- 4-pane GUI layout (Left: nodes, Center: canvas, Right: controls/actions, Bottom: actions)
- React Flow canvas with drag-and-drop node placement
- Connection drawing between nodes
- Adapter auto-rendering on connection edges
- Adapter selection modal when multiple adapters are valid for a connection pair
- Static property grid per node type (right-click reveals docked grid)
- Property auto-save on edit
- Limited node library: exactly the nodes needed for the MVP1 demo solution

#### 5. Pre-flight Wizard
- Environment profile creation and selection
- Variable resolution from environment profile + solution config
- Pre-flight check for missing required variables
- Active validation for `required` tier dependencies (graceful degradation acceptable)
- Pre-flight summary screen before deploy

#### 6. Execution Engine
- Worker abstraction interface defined
- Ansible-based worker implementation (first backend behind the abstraction)
- OpenTofu integration via worker abstraction
- Helm integration for K3s deployments via worker abstraction
- Subprocess execution with restricted env and working directory
- Output streaming via WebSocket from worker → API → frontend
- Deployment record creation with all pinned `git_sha`s captured

#### 7. The MVP1 Demo Solution
A solution that deploys to AWS Cove.GDIT consisting of:
- Windows Server 2022 STIG'd Domain Controller (EC2)
- Ubuntu Server EC2 joined to that domain
- K3s installed on the Ubuntu server
- OpenCTI deployed via Helm onto K3s
- Domain join adapter
- K3s install adapter
- OpenCTI configuration adapter

This is the demonstration vehicle. Every architectural commitment must be visible in deploying this solution.

#### 8. Audit Trail (per ADR-0003)
- OCSF-aligned schema deployed
- `audit.emit()` interface implemented
- Audit transport stage at MVP1: **TBD pending CLI consolidation review** — either S1 (Postgres direct) or S2 (NATS JetStream as scaffolded)
- Audit events emitted on every security-relevant action

#### 9. Project Property Page
- Required fields: Project/Solution Name, Created By (auto), Owner, Customer or Program Name, Original Purpose (with sub-options), Problem Statement, Outcome Statement, Date (auto)
- Persisted with solution

#### 10. Enforcement Scaffold
- Husky + lint-staged pre-commit hooks
- Vitest test framework configured
- Drizzle migration check
- Zod-route-coverage check (closes F-019)
- OCSF audit schema validation hook
- License header check
- Semgrep rule for `audit.emit()` enforcement on auditable actions
- CI pipeline (Gitea Actions or external) running all gates on PR

#### 11. Documentation
- Architecture decision records (ADRs) for major decisions made during MVP1
- Node and adapter authoring guide (initial draft — to be refined as the library grows)
- Contribution workflow documentation
- README with deployment instructions for FUSION itself

### What's Explicitly Deferred

#### Deferred to V1
- Multi-user collaboration (MVP1 is single-user; V1 introduces branch-based via Gitea)
- Full node and adapter library expansion (MVP1 has only what's needed for the demo solution)
- Real-time DB↔Gitea sync with full edge case handling (MVP1 has basic sync; full sync mechanics need Spike 1)
- Loki / Prometheus / Grafana bundling (MVP1 logs to stdout, exposes OTel metrics endpoint without scraper)
- OpenBao for secrets (MVP1 uses .env file in Cove.GDIT private lab — acceptable risk)
- IAM role-based AWS credentials (MVP1 uses static credentials in .env)
- DA group management UI and cross-DA access (MVP1 has single team; data model supports it but no UI)
- Revision history UI (data captured; UI deferred)
- Debug window with validation engine (foundation in place via Zod; full debug window UI is V1)
- Platform notifications and update push (V1)
- Dynamic property grid (connection-aware schema) (V1)
- LLM-assisted adapter property suggestions (V1)
- DoDAF-styled diagram export (V1)
- Modular sub-solution export and import (V1)
- Pin health monitoring CI integration (V1)
- K8s Job-based subprocess sandboxing (V1)
- Argo Workflows orchestration (V1)
- Container registry standup in Cove.GDIT (V1)

**Rationale for V1 deferrals:** Each of these requires either infrastructure that is not yet justified by user load (notifications, DA management UI), validation work that hasn't completed (subprocess sandboxing, sync mechanics), or feature surface beyond the demo's core architectural commitments (LLM features, DoDAF, sub-solution composition).

#### Deferred to V2
- Eager execution mode
- Real-time collaborative editing (Figma-style)
- Real-time living artifact generation
- AI-generated Zero Trust documentation and playbooks
- Synthetic test deployments
- Real-time feasibility checking
- Customer air-gap distribution tooling
- Formally compliant DoDAF artifact generation
- Variable conflict resolution on sub-graph import

**Rationale for V2 deferrals:** Each of these requires either substantial standalone engineering investment (eager execution, real-time collab, living artifacts), AI capability sequencing that depends on LUNA engagement (AI-generated ZT, feasibility checking), or customer-facing concerns that emerge only after FUSION is a product, not an internal tool (air-gap distribution).

#### Deferred Indefinitely (Post-Handoff Product Team)
- Multi-tenant SaaS billing
- License-tier policy enforcement
- Customer self-onboarding
- Public marketplace for third-party adapter contributions
- Vendor partnership integrations (Splunk, ServiceNow, etc. as direct contributors)

### Phase Risks

| Risk | Severity | Mitigation |
|---|---|---|
| Service-delivery cadence collapsing onto product engineering | HIGH | Frame MVP1 demo as "architectural integrity demonstration"; walk into funding gate with phased plan in hand |
| Untrained AI code degrading codebase | HIGH | Enforcement scaffold completed in week 1, before feature acceleration |
| Brennon pulled to delivery services | MEDIUM | Darren explicit time commitment in writing; deliberate redundancy via Matt or Dan early |
| Ansible licensing decision slipping | MEDIUM | Initiate Red Hat conversation in week 1 of MVP1, parallel to development |
| Demo solution too ambitious for 6 weeks | MEDIUM | Keep solution narrow: 1 DC, 1 Ubuntu, 1 endpoint, K3s, OpenCTI. No additional scope creep. |
| Audit transport stage decision blocking forward progress | LOW | Architecture supports both S1 and S2; can defer to consolidation without blocking other work |

### Definition of Done

MVP1 is complete when:

1. A solutions engineer can authenticate to FUSION via Keycloak, see a list of available solutions, select the demo solution, satisfy the pre-flight wizard, press Play, and watch real-time output as FUSION provisions the full demo solution into AWS Cove.GDIT.
2. The provisioned solution is functional — Domain Controller is up and STIG'd, Ubuntu is domain-joined, K3s is running, OpenCTI is reachable.
3. The deployment receipt records all pinned `git_sha`s and external artifact references.
4. The same solution can be re-deployed by pressing Play again with the same environment profile, producing equivalent infrastructure.
5. Every security-relevant action during the deployment has emitted an OCSF-conformant audit event.
6. Every Z-API route has registered Zod schemas for both request and response (F-019 closed).
7. The CI pipeline gates all merges; PRs cannot bypass enforcement scaffold checks.
8. Architecture decisions made during MVP1 are documented as ADRs.
9. The funding gate demo is rehearsed and ready for OCTO presentation.

---

## PHASE 2 — V1

### Goal

**Mature FUSION from a demonstration of architectural integrity into a production-capable internal platform that GDIT solutions engineers across multiple capability teams and digital accelerators can use as their primary solution authoring and deployment tool.**

### Window

Post-MVP1, contingent on OCTO Q2 funding gate. Likely 4-6 months of work.

### Phase Entry Criteria

V1 cannot begin until ALL of the following are met:

1. MVP1 Definition of Done is met (all 9 criteria from §MVP1 DoD below)
2. OCTO Q2 funding gate has approved continued IR&D
3. Ansible licensing decision `[STACK.IAC.CONFIG-MGMT]` has been resolved (one of: Red Hat exception granted, Pyinfra/Salt swap planned, self-contained packaging dropped)
4. Spike 1 (DB↔Gitea Sync Mechanics) has completed and produced its ADR
5. Spikes 2, 3, 4 have completed (Worker Abstraction, K8s Job Sandboxing, OPA Bundle Structure)
6. Architectural review with Darren and Matt has occurred (per MVP1.OPS.003)
7. Audit transport stage decision `[STATE.AUDIT-TRANSPORT]` is resolved if not already at S2

### Team

Expanded as funded. Likely additions:
- Dedicated TypeScript/React engineer (or CORAL temp-assignment)
- Dedicated systems/IaC engineer
- Continued Brennon as architect
- Possible LUNA engagement on AI features
- Possible EVEREST engagement on Zero Trust integration

### What's Included

#### 1. Multi-User Foundation
- Branch-based collaboration via Gitea (each user works on their own branch, merges via PR)
- User session management at scale (token refresh, session timeout, concurrent session policy)
- DA group management UI (admin can create groups, assign users, grant cross-DA access)
- Full OPA policy framework with DA-aligned policies, environment access policies, ownership-based policies

#### 2. DB↔Gitea Sync Maturity (Post-Spike 1)
- Webhook-driven sync with retry and recovery
- Stale canvas detection via WebSocket push
- Updates-available indicator with diff preview
- Branch protection rules enforced at Gitea API level
- Recovery flow when local DB and Gitea drift

#### 3. Library Expansion
- Significantly expanded node library (10-20+ node types beyond MVP1's demo set)
- Significantly expanded adapter library
- Node and adapter authoring workflow documented and operationalized
- Contribution standards published (publication gate, teardown procedure requirement, schema discipline)

#### 4. Deployment Lifecycle Maturity
- K8s Job-based subprocess sandboxing (Post-Spike 3) — replaces MVP1 plain subprocess
- Argo Workflows introduced as orchestration layer for tier-based execution
- Failure classification engine with all failure types handled (critical / non-critical / infrastructure)
- Per-tier teardown execution
- Partial deployment cancellation
- Pin-with-monitoring CI/CD integration (Post-Spike 6)
- Solution age tracking with green/yellow/red gates

#### 5. Secrets Management (V1)
- OpenBao bundled in Helm chart
- Environment profiles store secret references, never raw values
- Secret rotation policies defined
- IAM role-based AWS credentials replace .env files
- Audit events for all secret access

#### 6. Observability (V1)
- Loki + Grafana bundled for log aggregation
- Prometheus + Grafana bundled for metrics
- Audit transport graduates to S2 (NATS JetStream) per ADR-0003 if not already
- Standard dashboards for FUSION health, deployment success rates, library usage

#### 7. Container Registry
- Gitea container storage activated (or Harbor migration if criteria met)
- All FUSION bundled images sourced from GDIT-internal registry
- Helm chart values default to GDIT registry, override available

#### 8. UI Maturity
- Debug window with validation engine (issues list, click-to-navigate, on/off toggle)
- Dynamic property grid (connection-aware schema)
- Platform notifications via WebSocket push
- Update notification flow with optional acceptance
- Revision history UI
- Project metadata expanded views

#### 9. Modular Sub-Solution Composition
- Sub-graph selection on canvas
- Sub-solution export
- Sub-solution import via copy-on-import semantics
- Variable namespace handling at import time

#### 10. AI Features (V1 subset)
- LLM-assisted adapter property suggestions (abstract `ai.complete()` interface)
- Background validation enrichment (web research for tool configurations — optional)
- One-way AI notification panel in Debug Window

#### 11. Zero Trust Integration (V1 subset)
- ZT compliance metadata on nodes (does this node contribute to ZT?)
- ZT coverage summary based on solution graph (rules-based, not AI-generated)
- EVEREST engagement on ZT activity mapping if they engage

#### 12. DoDAF Output (V1 subset)
- DoDAF-styled SV-1 / SV-2 diagram export (SVG/PNG)
- Not formally compliant DoDAF artifacts (V2)

### What's Explicitly Deferred

#### To V2
- All items previously listed as V2 in MVP1 deferrals
- Real-time collaborative editing (V1 uses branch-based)
- Eager execution mode
- AI-generated ZT documentation and playbooks
- Formally compliant DoDAF artifacts

#### Indefinitely
- All items previously listed as indefinite deferrals in MVP1

### Phase Risks

| Risk | Severity | Mitigation |
|---|---|---|
| Other DAs forcing committee architecture | MEDIUM | Contribution standards published before V1 ramp; COVE retains maintainer authority |
| Darren's brain dump items resurface as scope demands | MEDIUM | Architectural review with Darren completed before V1 ramp; explicit phasing rationale documented |
| Spike findings invalidate V1 architectural commitments | MEDIUM | Spikes 1-4 complete BEFORE V1 implementation begins; Spike 5-6 complete during V1 |
| Ansible licensing decision still unresolved | HIGH | Decision deadline is end of MVP1 / start of V1; if unresolved, V1 starts with explicit fallback path activated |
| Self-contained packaging promise breaks under V1 load | MEDIUM | Continuously validate "self-contained" claim against actual implementation state |

### Definition of Done

V1 is complete when:

1. Multiple GDIT solutions engineers from different DAs can use FUSION concurrently (via branch-based collaboration) to author and deploy solutions.
2. The library includes a meaningful set of nodes and adapters covering the most common GDIT solution patterns.
3. Deployments run via Argo Workflows in K8s Jobs with full failure classification and teardown.
4. Secrets are managed via OpenBao; .env is no longer in use.
5. Pin-with-monitoring is operational; aging solutions are flagged; broken pins are detected.
6. Container images are sourced from GDIT-internal registry.
7. Audit trail is operational at S2 (NATS) per ADR-0003.
8. Debug window, dynamic property grid, sub-solution composition, and DoDAF export are operational.
9. AI-assisted adapter property suggestions are operational behind an abstract interface.
10. FUSION is ready for handoff to a dedicated product team, with documented architecture, runbooks, contribution guides, and ADRs sufficient for the product team to inherit cleanly.

---

## PHASE 3 — V2

### Goal

**Transform FUSION from a production-capable internal platform into a customer-deliverable product capable of being licensed, sold as a service, or deployed into customer environments — including air-gapped defense customer environments — with the advanced capabilities (eager execution, real-time collaboration, AI-driven Zero Trust) that justify it as a commercial offering.**

### Window

Post-handoff to dedicated product team. Timeline determined by product team and Growth division.

### Phase Entry Criteria

V2 cannot begin until ALL of the following are met:

1. V1 Definition of Done is met
2. Handoff to dedicated FUSION product team has occurred
3. Spikes 5 (Eager Execution Prep) and 6 (Pin-with-Monitoring CI) have completed
4. Customer deployment scenarios are concrete enough to drive air-gap distribution decisions `[customer-airgap]`
5. Growth division has commercial positioning defined
6. AI integration architecture decision is closed `[ai-integration]` (LUNA engagement or alternative)

### Team

Dedicated FUSION product team (size TBD). COVE may continue to participate as power users and architectural advisors but no longer owns the codebase.

### What's Included

#### 1. Eager Execution Mode (Post-Spike 5)
- Per-canvas toggle (default off)
- Continuous node-readiness evaluation
- Cost/resource preview always visible when enabled
- Confirmation prompts at first eager execution per session
- Visual states for partially-deployed resources
- Justified by defense exercise kit scenarios where deployment time is operationally critical

#### 2. Real-Time Collaborative Canvas
- Figma-style multi-user editing
- Presence tracking (initials bubbles tracking user position)
- CRDT or operational transform for conflict-free concurrent edits
- Replaces V1's branch-based collaboration model for power-user scenarios

#### 3. Real-Time Living Artifact Generation
- Canvas changes immediately propagate to underlying IaC artifact files
- Continuous compilation rather than save-time generation
- Significant state machine investment

#### 4. Advanced AI Capabilities
- AI-generated Zero Trust documentation and configuration playbooks
- Synthetic test deployments (definition required — research spike)
- Real-time feasibility checking on solutions in progress
- Category-based universal adapters (LUNA collaboration if engaged)

#### 5. Customer Air-Gap Distribution
- Tarball-based image bundle generation
- Manifest signing for supply chain integrity
- Customer-side import scripts
- Documented patterns for varied transit methods

#### 6. Formally Compliant DoDAF Artifacts
- SV-1 and SV-2 generation conformant to DoDAF specifications
- Suitable for submission in actual architecture reviews

#### 7. Multi-Tenant SaaS Capability
- Per-tenant data isolation enforced (data model already supports via `tenant_id`)
- Tenant onboarding flows
- License-tier policy enforcement (OPA-based)
- Billing integration if SaaS model selected

#### 8. Vendor Partnership Surface
- External contribution workflow for vendors (Splunk, ServiceNow, etc.)
- Adapter and node submission process for non-GDIT contributors
- Trust and verification model for external library content

#### 9. Variable Conflict Resolution on Sub-Graph Import
- When a sub-solution's variables collide with parent solution's variables, structured resolution flow
- Namespace prefixing or explicit override declaration

### What's Explicitly Deferred or Out of Scope

V2 does not include:
- Specific SaaS pricing model selection (Growth division's decision)
- Specific go-to-market sequencing (sector-by-sector commercial expansion)
- Specific partner program structures (if vendor partnerships materialize)

### Phase Risks

| Risk | Severity | Mitigation |
|---|---|---|
| Eager execution complexity exceeds estimates | HIGH | Spike 5 validates feasibility before commitment |
| Real-time collaboration is a multi-month engineering investment | HIGH | Product team scope; not a COVE problem |
| Marketing language outpaces self-contained reality | MEDIUM | Continuous claim/reality tracking |
| Customer air-gap patterns vary too widely to standardize | MEDIUM | Document multiple supported patterns rather than forcing one |
| LUNA engagement does not materialize | MEDIUM | Universal adapters become aspirational rather than committed |

### Definition of Done

V2 is complete when:

1. FUSION is a sellable product offering with a defined commercial model.
2. Eager execution is operational and demonstrated as a flagship capability.
3. Customer air-gap distribution patterns are documented and supported.
4. Real-time collaborative editing is functional for multi-user power scenarios.
5. AI-driven Zero Trust documentation and playbook generation is operational.
6. DoDAF compliance is achievable for customers requiring it.
7. Multi-tenant SaaS capability is demonstrable, even if not yet activated commercially.
8. The product team has full ownership and Growth division has product-market positioning.

---

## Cross-Phase Concerns

### Architecture Change Triggers

Per the Architecture Change Trigger Policy (Architecture Breakdown §6.8), any of the following triggers stop-and-review at any phase:

- Red Hat denies Ansible exception
- Spike findings invalidate the approach the spike was meant to validate
- ATO/FedRAMP/IL mandates surface specific tooling requirements
- OCTO redirects primary use case
- Core upstream dependency relicensing or deprecation
- Well-supported claim from a core team member

### Cross-Phase Risk: Vision Document Scope Creep

Darren's original brain dump (captured in Functional Scope work, classified across phases in this document) includes items that span all three phases. The risk: items get reclassified upward into earlier phases as enthusiasm builds.

**Mitigation:** This phasing document is the authoritative classification. Reclassification requires explicit architectural review and ADR documentation, not informal agreement.

### Cross-Phase Risk: Funding Gate Pressure

Each phase has a funding gate. Each gate creates pressure to claim more capability than is actually delivered.

**Mitigation:** Definition of Done for each phase is the gate criterion. If Definition of Done is not met, the phase is not complete regardless of funding pressure.

---

**End of Document 2.** Companion documents:

- **Document 1:** Architecture Breakdown
- **Document 3:** Task Backlog (small-grain, prioritized, dependency-flagged)
