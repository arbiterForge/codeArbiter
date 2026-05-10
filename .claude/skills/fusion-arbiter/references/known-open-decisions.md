# Known Open Decisions

The architectural artifacts deliberately leave certain decisions open. The arbiter MUST NOT treat these as variances during arbitration — they are open by design.

This file enumerates each open decision and divides them into two scopes:

- **Arbiter-scope open decisions** — closeable through the arbitration process; standardized handling rules apply
- **Out-of-scope open decisions** — not arbitrated by this skill; surfaced for awareness only

## Standardized Handling Table (Arbiter-Scope Open Decisions)

For every arbiter-scope open decision, the arbiter applies this exact rule table:

| Scaffold state | Action |
|---|---|
| Implements artifact direction (the artifact's stated default or recommended path) | Note as consistent with deferral; no variance |
| Implements an artifact-listed alternative | Surface as `open-decision-closure` in the variance report; check whether closure was authorized in the decision log |
| Silent — no implementation yet | Note as consistent with deferral; no variance |
| Implements something not listed in the artifact's options | Surface as scope creep; verify with user before treating as a closure |

If the user decides to close the open decision during the arbitration session, the closure is recorded in `docs/fusion-arbiter-decisions.md` with `Status type: open-decision-closure` per the format in `references/decision-log-format.md`.

---

## Arbiter-Scope Open Decisions

### Open Decision: Ansible Licensing

**Where the artifacts say it is open:**
- Architecture Breakdown §8.1
- Phased Build Plan MVP1 risks
- Task Backlog MVP1.OPS.001

**What is open:**
Whether GDIT will use Ansible (community, GPL v3) bundled inside FUSION, or replace it with Pyinfra/Salt, or drop the self-contained packaging mandate.

**Artifact-listed options:**
1. Continue with Ansible after Red Hat exception
2. Swap to Pyinfra (MIT)
3. Swap to Salt (Apache 2.0)
4. Drop self-contained packaging mandate

**What would close it:**
- Red Hat grants distribution exception → option 1
- Red Hat denies → choose among options 2, 3, or 4

**Action item explicitly tracked:** MVP1.OPS.001 — Brennon initiates Red Hat exception conversation in week 1 of MVP1.

**Decision deadline:** End of MVP1 / start of V1 planning.

**Apply standardized handling table to this decision.**

---

### Open Decision: Audit Transport Stage at MVP1

**Where the artifacts say it is open:**
- Architecture Breakdown §8.2
- Task Backlog MVP1.AUDIT.004 (marked 🚫 BLOCKED)

**What is open:**
Whether MVP1 ships at ADR-0003 Stage 1 (direct Postgres write) or Stage 2 (NATS JetStream as scaffolded).

**Artifact-listed options:**
1. S1 — Postgres direct write (Desktop session recommendation)
2. S2 — NATS JetStream (ADR-0003 preference)

**What would close it:**
The CLI consolidation review — comparing Desktop architectural reasoning with CLI scaffold reasoning side-by-side. **This is exactly what the arbiter is for.**

**Note:** Architecture is locked either way per ADR-0003. Only sequencing differs.

**Apply standardized handling table to this decision.**

---

### Open Decision: AI Integration Architecture for V1

**Where the artifacts say it is open:**
- Architecture Breakdown §8.3
- Task Backlog V1.AI.002

**What is open:**
Specific AI service integration for V1 features (LLM-assisted adapter property suggestions, debug window AI assistant). Pattern is locked (abstract `ai.complete()` interface). Provider is open.

**Artifact-listed options:**
1. Anthropic Claude API (cloud)
2. AWS Bedrock GovCloud (cloud)
3. Llama via vLLM (self-hosted, classified/air-gap-suitable)
4. Defer until LUNA engagement

**What would close it:**
- LUNA (AI/ML DA) engagement
- V1 planning conversation
- Concrete deployment requirements surfacing

**Apply standardized handling table to this decision.**

---

### Open Decision: Container Registry Migration Trigger

**Where the artifacts say it is open:**
- Architecture Breakdown §8.5
- Task Backlog V1.REGISTRY.004

**What is open:**
Whether V1 stays on Gitea container storage or migrates to Harbor.

**Artifact-listed options:**
1. Stay on Gitea container storage for V1
2. Migrate to Harbor before V1 ships

**What would close it:**
Compliance requirements surfacing (vulnerability scanning, image signing, replication, multi-tenant isolation).

**Apply standardized handling table to this decision.**

---

## Out-of-Scope Open Decisions (Not Arbitrated by This Skill)

The arbiter explicitly does NOT arbitrate the following decisions. They are operational, political, or strategic — not architectural. If the user asks about them, the arbiter redirects to the appropriate resolution mechanism.

### Out-of-Scope: Customer Air-Gap Distribution

**Where mentioned:** Architecture Breakdown §8.4; Phased Build Plan V2 V2.AIRGAP.

**Why out-of-scope:** Deferred to V2 by design when customer-deployment scenarios are concrete. No MVP1 or V1 arbitration applies. If scaffold work has begun on air-gap distribution prematurely, that is scope creep — surface to user without arbitration.

**Resolution mechanism:** V2 product team planning.

---

### Out-of-Scope: Spike Ownership Assignments

**Where mentioned:** Task Backlog V1.SPIKE.* tasks.

**Why out-of-scope:** Operational personnel decision, not architectural. Cannot be arbitrated by SMARTS analysis.

**Resolution mechanism:** MVP1.OPS.003 — architectural review with Darren and Matt the week after Darren's PTO.

---

### Out-of-Scope: Cross-DA Engagement Timing

**Where mentioned:** Architecture Breakdown §10; Phased Build Plan V1 risks.

**Why out-of-scope:** Strategic relationship decision, not architectural. When to engage EVEREST, CORAL, LUNA on FUSION is a Brennon+Darren call.

**Resolution mechanism:** Brennon and Darren strategic conversation, gated by MVP1 success and OCTO funding direction.

---

### Out-of-Scope: Ansible License Negotiation Internal Process

**Where mentioned:** Architecture Breakdown §8.1; Task Backlog MVP1.OPS.001.

**Why out-of-scope:** The *outcome* of the Red Hat exception conversation drives the architectural decision (Ansible Licensing — see arbiter-scope above). The *process* of conducting that negotiation is operational and not arbitrated here.

**Resolution mechanism:** GDIT partnerships team and Brennon. Surface to user only when outcome is determined.

---

## Anti-Pattern: Treating Open Decisions as Variances

If the arbiter is generating a variance entry for any of the above, that is a bug in the arbiter's logic. Open decisions go in the readiness assessment file, not the variance report.

The distinction:
- **Variance** = artifacts and scaffold disagree on something the artifacts have a position on
- **Arbiter-scope open decision** = artifacts deliberately have no position; awaiting input; can be closed during arbitration via standardized handling
- **Out-of-scope open decision** = not architectural; not arbitrated by this skill at all

The arbiter must articulate the difference for any item it surfaces.

## Closing an Open Decision Mid-Arbitration

For arbiter-scope open decisions, if the user wants to close one during the arbitration session:

1. Confirm with the user that they want to close an artifact-deferred decision
2. Apply the SMARTS framework to the artifact-listed options
3. Record the decision in `docs/fusion-arbiter-decisions.md` with `Status type: open-decision-closure` and a note that this closes an artifact-deferred decision
4. Update the readiness assessment to reflect the now-closed decision

For out-of-scope open decisions, the arbiter declines: "This is operational/strategic, not architectural — outside this skill's scope. The resolution mechanism is <X>."
