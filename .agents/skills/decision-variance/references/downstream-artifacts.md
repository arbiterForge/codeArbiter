# Downstream Artifacts Catalog

This file catalogs the architectural artifacts that this skill can recommend producing once enough information is available. For each artifact, the catalog defines:

- **Purpose** — what the artifact is for
- **Readiness criteria** — explicit decision-ID lists that determine `ready` vs `partial` vs `blocked`
- **Production guidance** — how to produce the artifact (handed to the user; this skill does not auto-produce)

## How This Skill Uses This File

During Stage 5, this skill walks this catalog and assesses readiness for each artifact using the explicit criteria below. Output goes to `projectContext/arbiter-readiness.md` as a menu the user can select from.

This skill does NOT produce these artifacts unless the user explicitly selects them.

## Readiness Evaluation Algorithm

For each downstream artifact:

1. Read the artifact's `ready_criteria` list. If ALL criteria are met, mark `ready`.
2. Otherwise, read the `blocked_criteria` list. If ANY criterion is met, mark `blocked` and report which criterion triggered.
3. Otherwise, mark `partial` and list the unmet `ready_criteria` items as "what's missing."

A criterion is "met" when:
- For `<DECISION-ID> = locked`: the decision exists in the artifacts as a clear position OR exists as an `accepted` entry in the decision log
- For `<DECISION-ID> = locked-and-implemented`: the decision exists AND scaffold evidence demonstrates implementation
- For `<spike-ID> = complete`: the spike's deliverable ADR exists in `projectContext/decisions/`
- For `<file-or-pattern>`: the file or pattern exists in the project

---

## Artifact: Component Interface Contracts

**Purpose:** Define the precise input/output contract for each major component so agent-driven development has stable boundaries.

**ready_criteria:**
- `STACK.BACKEND.FRAMEWORK = locked-and-implemented`
- `STACK.BACKEND.VALIDATION = locked-and-implemented`
- `SCHEMA.SOLUTION-MANIFEST = locked`
- `API.AUTHZ.CALL = locked`
- `API.AUDIT.EMIT = locked`
- At least one route in scaffold demonstrating the full pattern (auth + validation + authorization + audit)

**blocked_criteria:**
- `STACK.BACKEND.FRAMEWORK` is divergent and unresolved
- `STACK.BACKEND.VALIDATION` is divergent and unresolved

**Production guidance:**
Generate one contract file per component. Use the project's primary language's interface or type definitions for same-language contracts; JSON Schema for cross-component contracts (e.g., audit events). Group by component, then by endpoint or function. Each contract: input shape, output shape, error cases, side effects.

---

## Artifact: Data Schema (Concrete Field-Level)

**Purpose:** The actual schema definition file(s) defining every table, collection, column/field, type, constraint, and index.

**ready_criteria:**
- `STACK.BACKEND.ORM = locked-and-implemented`
- `SCHEMA.SOLUTION-MANIFEST = locked`
- `SCHEMA.NODE-DEFINITION = locked`
- `SCHEMA.ADAPTER-DEFINITION = locked`
- `SCHEMA.AUDIT-EVENT = locked`
- `SCHEMA.ENVIRONMENT-PROFILE = locked`
- `SCHEMA.DEPLOYMENT-RECEIPT = locked`
- `PATTERN.MULTI-TENANT-RETROFIT = locked`
- `STATE.GITSHA-PINNING = locked`

**blocked_criteria:**
- `STACK.BACKEND.ORM` is not resolved (schema syntax depends on ORM)
- Any `SCHEMA.*` decision is divergent and unresolved

**Production guidance:**
A schema definition file using the project's data access layer. Include tenant isolation columns on solution-related tables. Include artifact SHA columns where required. Include constraints verifying reference formats for stored references. Skip indexes initially — add after query analysis.

---

## Artifact: Authorization Policy Bundle Skeleton

**Purpose:** Initial policy structure with package layout, decision flow, and starter policies for the first milestone.

**ready_criteria:**
- `STACK.AUTH.AUTHORIZATION = locked`
- `API.AUTHZ.CALL = locked`
- Authorization policy bundle structure spike = complete OR user has accepted producing a pre-spike skeleton

**blocked_criteria:**
- `STACK.AUTH.AUTHORIZATION` is divergent and unresolved

**Production guidance:**
Generate a policy repository skeleton with: `policies/` directory with package layout, `tests/` directory with corresponding test files, bundle build script, README with policy authoring guide. Tailor to the authorization engine selected in `STACK.AUTH.AUTHORIZATION`.

---

## Artifact: Deployment Package Skeleton

**Purpose:** Bundled deployment package that deploys the system as a single atomic unit.

**ready_criteria:**
- `DEPLOY.PACKAGING = locked`
- `DEPLOY.SELF-CONTAINED = locked`
- `STACK.HOSTING = locked`
- `STACK.DB.ENGINE = locked`
- `STACK.LIBRARY.GIT = locked`
- `STACK.AUTH.IDENTITY = locked`
- `STACK.AUTH.AUTHORIZATION = locked`

**blocked_criteria:**
- `DEPLOY.PACKAGING` is divergent and unresolved
- `DEPLOY.SELF-CONTAINED` is divergent and unresolved

**Production guidance:**
Generate a deployment package directory (Helm chart, Compose file, or equivalent per `DEPLOY.PACKAGING`) with charts/services per component. Include a schema or defaults file. Default values target the milestone environment with overrides documented.

---

## Artifact: Solution Manifest JSON Schema

**Purpose:** Formal JSON Schema for solution manifests, used for VCS CI validation and load-time validation.

**ready_criteria:**
- `SCHEMA.SOLUTION-MANIFEST = locked`
- `SCHEMA.NODE-DEFINITION = locked`
- `SCHEMA.ADAPTER-DEFINITION = locked`
- `STATE.GITSHA-PINNING = locked`
- `PATTERN.SUB-SOLUTION-COMPOSITION = locked`

**blocked_criteria:**
- Any of the above is divergent and unresolved

**Production guidance:**
Single JSON Schema file documenting the manifest format: nodes (with pinned SHA), edges (with adapter selection and pinned SHA), environment binding, project metadata, sub-solution composition references. Generate language-native types from the schema.

---

## Artifact: Node Authoring Guide (Detailed)

**Purpose:** Full contribution guide for node authors — schema requirements, code organization, teardown procedure standards, publication gate criteria.

**ready_criteria:**
- `SCHEMA.NODE-DEFINITION = locked`
- `PATTERN.REVERSAL-TIERS = locked`
- At least one node implemented as a reference example
- `CI.PIPELINE = locked-and-implemented` (publication gate runs in CI)

**blocked_criteria:**
- `SCHEMA.NODE-DEFINITION` is divergent and unresolved

**Production guidance:**
Markdown guide with sections: directory structure, definition schema, IaC code conventions, configuration code conventions, teardown procedure requirements, publication gate, PR review expectations. Include a complete worked example from one reference node.

---

## Artifact: Adapter Authoring Guide (Detailed)

**Purpose:** Same as node authoring guide but for adapters.

**ready_criteria:**
- `SCHEMA.ADAPTER-DEFINITION = locked`
- `PATTERN.REVERSAL-TIERS = locked`
- At least one adapter implemented as reference
- `CI.PIPELINE = locked-and-implemented`

**blocked_criteria:**
- `SCHEMA.ADAPTER-DEFINITION` is divergent and unresolved

**Production guidance:**
Same structure as node authoring guide but covering adapter-specific concerns: source/target type declarations, tier classification, multi-select compatibility, integration code conventions.

---

## Artifact: Audit Event Reference

**Purpose:** Complete enumeration of every audit event the system emits, with class identifier, schema, trigger condition, and example payload.

**ready_criteria:**
- `SCHEMA.AUDIT-EVENT = locked`
- `API.AUDIT.EMIT = locked-and-implemented`
- An ADR capturing the audit event schema decision exists in `projectContext/decisions/`

**blocked_criteria:**
- `SCHEMA.AUDIT-EVENT` is divergent and unresolved
- No ADR capturing the audit schema decision can be located

**Production guidance:**
Markdown reference enumerating every audit event by identifier. Each entry: name, trigger description, required fields, example payload. Group by category (auth, deployment, secrets, etc.). Cross-reference with the compliance control framework from `projectContext/security-controls.md`.

---

## Artifact: Spike Plan Document (Per Spike)

**Purpose:** Detailed plan documents for each open spike, ready for the assigned engineer.

**ready_criteria (per individual spike):**
- The spike's scope is clearly described in the Task Backlog
- The spike's owner is assigned (not a TBD placeholder)

**blocked_criteria:**
- Spike scope is in active dispute (variance unresolved)

**Production guidance:**
Per-spike document with: context (full reasoning from artifacts), questions to answer, success criteria, suggested approach, expected output, time-box, risks. One document per spike under `docs/spikes/`.

---

## Artifact: ADR Set for Milestone Decisions

**Purpose:** Formal ADRs for every architectural decision made during the current milestone, in the project's ADR format, ready to commit.

**ready_criteria:**
- `DOCS.ADR-CONVENTION = locked` (template exists or this artifact will produce it first)
- At least 5 decisions exist in `projectContext/arbiter-decisions.md`
- An existing ADR pattern is identifiable in `projectContext/decisions/`

**blocked_criteria:**
- No clear ADR convention exists in the project

**Production guidance:**
One ADR per major decision in the decision log. Use the project's existing ADR format. Cross-reference each ADR to the originating decision-log entry by DECISION-NNNN.

---

## Artifact: Cross-Context Variance Report (One-Time)

**Purpose:** Specific report bridging separate session contexts — the consolidation deliverable for the import-and-arbitrate activity.

**ready_criteria:**
- All three architectural artifacts present (per Rule 2)
- Scaffold codebase accessible
- This skill has completed Stage 1 through Stage 4 at least once

**blocked_criteria:**
- Three artifacts not located

**Production guidance:**
This is the variance report Stage 3 produces, framed as the bridging deliverable. After this report is processed, this skill operates on a unified context.

---

## How to Recommend

For each artifact in this catalog, this skill's Stage 5 output uses this exact format:

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
