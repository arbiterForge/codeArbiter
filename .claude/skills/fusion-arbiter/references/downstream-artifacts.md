# Downstream Artifacts Catalog

This file catalogs the architectural artifacts that the FUSION arbiter can recommend producing once enough information is available. For each artifact, the catalog defines:

- **Purpose** — what the artifact is for
- **Readiness criteria** — explicit decision-ID lists that determine `ready` vs `partial` vs `blocked`
- **Production guidance** — how to produce the artifact (handed to the user; arbiter does not auto-produce)

## How the Arbiter Uses This File

During Stage 5, the arbiter walks this catalog and assesses readiness for each artifact using the explicit criteria below. Output goes to `docs/fusion-arbiter-readiness.md` as a menu the user can select from.

The arbiter does NOT produce these artifacts unless the user explicitly selects them.

## Readiness Evaluation Algorithm

For each downstream artifact:

1. Read the artifact's `ready_criteria` list. If ALL criteria are met, mark `ready`.
2. Otherwise, read the `blocked_criteria` list. If ANY criterion is met, mark `blocked` and report which criterion triggered.
3. Otherwise, mark `partial` and list the unmet `ready_criteria` items as "what's missing."

A criterion is "met" when:
- For `<DECISION-ID> = locked`: the decision exists in the artifacts as a clear position OR exists as an `accepted` entry in the decision log
- For `<DECISION-ID> = locked-and-implemented`: the decision exists AND scaffold evidence demonstrates implementation
- For `<spike-ID> = complete`: the spike's deliverable ADR exists in `docs/adr/`
- For `<file-or-pattern>`: the file or pattern exists in the project

---

## Artifact: Component Interface Contracts

**Purpose:** Define the precise input/output contract for each Z-* component (Z-API, Z-WORKER, Z-DB, etc.) so agent-driven development has stable boundaries.

**ready_criteria:**
- `STACK.BACKEND.FRAMEWORK = locked-and-implemented`
- `STACK.BACKEND.VALIDATION = locked-and-implemented`
- `SCHEMA.SOLUTION-MANIFEST = locked`
- `API.AUTHZ.OPA-CALL = locked`
- `API.AUDIT.EMIT = locked`
- At least one route in scaffold demonstrating the full pattern (auth + validation + OPA + audit)

**blocked_criteria:**
- `STACK.BACKEND.FRAMEWORK` is divergent and unresolved
- `STACK.BACKEND.VALIDATION` is divergent and unresolved

**Production guidance:**
Generate one contract file per component. Use TypeScript interface definitions (most components are TS), JSON Schema for cross-component contracts (e.g., audit events). Group by component, then by endpoint or function. Each contract: input shape, output shape, error cases, side effects.

---

## Artifact: Drizzle Schema (Concrete Field-Level)

**Purpose:** The actual `backend/src/db/schema.ts` file defining every table, column, type, constraint, and index.

**ready_criteria:**
- `STACK.BACKEND.ORM = locked-and-implemented` as Drizzle
- `SCHEMA.SOLUTION-MANIFEST = locked`
- `SCHEMA.NODE-DEFINITION = locked`
- `SCHEMA.ADAPTER-DEFINITION = locked`
- `SCHEMA.AUDIT-EVENT = locked`
- `SCHEMA.ENVIRONMENT-PROFILE = locked`
- `SCHEMA.DEPLOYMENT-RECEIPT = locked`
- `PATTERN.MULTI-TENANT-RETROFIT = locked`
- `STATE.GITSHA-PINNING = locked`

**blocked_criteria:**
- `STACK.BACKEND.ORM` is not Drizzle (different ORM in scaffold means schema syntax differs)
- Any `SCHEMA.*` decision is divergent and unresolved

**Production guidance:**
A single `schema.ts` file with full table definitions. Include `tenant_id` on solution-related tables. Include `git_sha` columns where required. Include the "exactly one of value or secret_ref" constraint pattern. Skip indexes initially — add after query analysis.

---

## Artifact: OPA Policy Bundle Skeleton

**Purpose:** Initial Rego policy structure with package layout, decision flow, and starter policies for MVP1.

**ready_criteria:**
- `STACK.AUTH.AUTHORIZATION = locked` as OPA
- `API.AUTHZ.OPA-CALL = locked`
- Spike 4 (OPA Policy Bundle Structure) = complete OR user has accepted producing a pre-spike skeleton

**blocked_criteria:**
- `STACK.AUTH.AUTHORIZATION` is divergent and unresolved

**Production guidance:**
Generate `fusion-policies/` repo skeleton: `policies/` directory with package layout (e.g., `policies/solutions.rego`, `policies/environments.rego`), `tests/` directory with corresponding `*_test.rego` files, `bundle.tar.gz` build script, README with policy authoring guide.

---

## Artifact: Helm Chart Skeleton

**Purpose:** Bundled Helm chart that deploys FUSION as a single atomic unit.

**ready_criteria:**
- `DEPLOY.HELM-CHART = locked`
- `DEPLOY.SELF-CONTAINED = locked`
- `STACK.HOSTING = locked`
- `STACK.DB.ENGINE = locked`
- `STACK.LIBRARY.GIT = locked`
- `STACK.AUTH.IDENTITY = locked`
- `STACK.AUTH.AUTHORIZATION = locked`

**blocked_criteria:**
- `DEPLOY.HELM-CHART` is divergent and unresolved
- `DEPLOY.SELF-CONTAINED` is divergent and unresolved

**Production guidance:**
Generate `helm/fusion/` directory with `Chart.yaml`, `values.yaml`, templates per service. Use subcharts where they exist. Include `values.schema.json`. Default values target Cove.GDIT for MVP1 with overrides documented.

---

## Artifact: Solution Manifest JSON Schema

**Purpose:** Formal JSON Schema for solution manifests, used for Gitea CI validation and FUSION load-time validation.

**ready_criteria:**
- `SCHEMA.SOLUTION-MANIFEST = locked`
- `SCHEMA.NODE-DEFINITION = locked`
- `SCHEMA.ADAPTER-DEFINITION = locked`
- `STATE.GITSHA-PINNING = locked`
- `PATTERN.SUB-SOLUTION-COMPOSITION = locked`

**blocked_criteria:**
- Any of the above is divergent and unresolved

**Production guidance:**
Single JSON Schema file documenting the manifest format: nodes (with pinned `node_git_sha`), edges (with adapter selection and pinned `adapter_git_sha`), environment binding, project metadata, sub-solution composition references. Generate TypeScript types from the schema.

---

## Artifact: Node Authoring Guide (Detailed)

**Purpose:** Full contribution guide for node authors — schema requirements, IaC code organization, teardown procedure standards, publication gate criteria.

**ready_criteria:**
- `SCHEMA.NODE-DEFINITION = locked`
- `PATTERN.REVERSAL-TIERS = locked`
- At least one MVP1 node implemented as a reference example
- `CI.PIPELINE = locked-and-implemented` (publication gate runs in CI)

**blocked_criteria:**
- `SCHEMA.NODE-DEFINITION` is divergent and unresolved

**Production guidance:**
Markdown guide with sections: directory structure, definition.yaml schema, OpenTofu code conventions, configuration code conventions, teardown procedure requirements, publication gate, PR review expectations. Include a complete worked example from one MVP1 demo node.

---

## Artifact: Adapter Authoring Guide (Detailed)

**Purpose:** Same as node authoring guide but for adapters.

**ready_criteria:**
- `SCHEMA.ADAPTER-DEFINITION = locked`
- `PATTERN.REVERSAL-TIERS = locked`
- At least one MVP1 adapter implemented as reference
- `CI.PIPELINE = locked-and-implemented`

**blocked_criteria:**
- `SCHEMA.ADAPTER-DEFINITION` is divergent and unresolved

**Production guidance:**
Same structure as node authoring guide but covering adapter-specific concerns: source/target type declarations, tier classification, multi-select compatibility, integration code conventions.

---

## Artifact: Audit Event Reference

**Purpose:** Complete enumeration of every audit event FUSION emits, with class_uid, schema, trigger condition, and example payload.

**ready_criteria:**
- `SCHEMA.AUDIT-EVENT = locked` per ADR-0003
- `API.AUDIT.EMIT = locked-and-implemented`
- ADR-0003 exists in `docs/adr/`

**blocked_criteria:**
- `SCHEMA.AUDIT-EVENT` is divergent and unresolved
- ADR-0003 cannot be located

**Production guidance:**
Markdown reference enumerating every audit event by class_uid. Each entry: name, trigger description, required fields, example payload. Group by category (auth, deployment, library, secrets). Cross-reference with NIST 800-53 controls per ADR-0003. Independent of audit-transport-stage decision.

---

## Artifact: Spike Plan Document (Per Spike)

**Purpose:** Detailed plan documents for each of the six spikes, ready for the assigned engineer.

**ready_criteria (per individual spike):**
- The spike's scope is clearly described in the Task Backlog
- The spike's owner is assigned (not `TBD-DARREN-REVIEW`, not `TBD-AVAILABLE`, not `TBD-SPIKE-OUTCOME`)

**blocked_criteria:**
- Spike scope is in active dispute (variance unresolved)

**Production guidance:**
Per-spike document with: context (full reasoning from artifacts), questions to answer, success criteria, suggested approach, expected output, time-box, risks. One document per spike under `docs/spikes/`.

---

## Artifact: ADR Set for MVP1 Decisions

**Purpose:** Formal ADRs for every architectural decision made during MVP1, in the project's ADR format, ready to commit.

**ready_criteria:**
- `DOCS.ADR-CONVENTION = locked` (template exists or this artifact will produce it first)
- At least 5 decisions exist in `docs/fusion-arbiter-decisions.md`
- An existing ADR pattern is identifiable (e.g., ADR-0003 exists and shows the format)

**blocked_criteria:**
- No clear ADR convention exists in the project

**Production guidance:**
One ADR per major decision in the arbiter log. Use the project's existing ADR format. Cross-reference each ADR to the originating arbiter decision entry by DECISION-NNNN.

---

## Artifact: V1 Scope Refinement Document

**Purpose:** Document refining V1 scope based on what was actually delivered in MVP1, ready for the OCTO Q2 funding gate.

**ready_criteria:**
- All MVP1 tasks marked `complete` in the task backlog OR explicit user statement that MVP1 is substantively complete
- Spikes 1, 2, 3, 4 = complete
- Updates to V1 task list captured based on MVP1 actuals

**blocked_criteria:**
- MVP1 not complete

**Production guidance:**
Defer until MVP1 is substantively complete. Partial production is not useful for this artifact.

---

## Artifact: Funding Gate Demo Script

**Purpose:** Step-by-step demo script for OCTO Q1 funding gate with talking points, fallback plans, and architectural-integrity highlights.

**ready_criteria:**
- MVP1.DEMO.011 (full demo deployment test) marked `complete`
- All architectural commitments demonstrably visible in the demo

**blocked_criteria:**
- MVP1.DEMO.011 not complete

**Production guidance:**
Tight markdown script. Lead with architectural integrity framing ("this demo shows what we built; pay attention to how it was built"). Include explicit moments where architectural commitments surface — pre-flight wizard, deployment receipt, audit trail, pinned `git_sha`s, Keycloak+OPA separation. Include fallback plans for failure modes.

---

## Artifact: Cross-Context Variance Report (One-Time)

**Purpose:** Specific report bridging Desktop session context with CLI/scaffold context — the consolidation deliverable for the import-and-arbitrate activity.

**ready_criteria:**
- All three architectural artifacts present (per Rule 2)
- Scaffold codebase accessible
- The arbiter has completed Stage 1 through Stage 4 at least once

**blocked_criteria:**
- Three artifacts not located

**Production guidance:**
This is essentially the variance report Stage 3 produces, framed as the bridging deliverable. After this report is processed, the arbiter operates on a unified context.

---

## How to Recommend

For each artifact in this catalog, the arbiter's Stage 5 output uses this exact format:

```markdown
## Downstream Artifact Readiness

### <Artifact Name>
- **Readiness:** ready | partial | blocked
- **Why:** [one sentence with specific decision-ID references]
- **What's missing (if partial):** [bulleted list of unmet ready_criteria items]
- **What's blocking (if blocked):** [the specific blocked_criteria item that triggered]
- **Recommendation:** produce now | produce after specific variances resolved | do not produce yet
```

The user then chooses which artifacts to commission.
