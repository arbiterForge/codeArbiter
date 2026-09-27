# SMARTS deep-dive review

**Date:** 2026-09-26
**Repository:** `arbiterForge/codeArbiter`
**Development baseline inspected:** `8e88bce938ebf7dc8cfd934307b8d6859092d86e`
**Purpose:** Preserve the source review that motivated `.codearbiter/specs/smarts-design-quality-integration.md`.

## Executive finding

SMARTS itself is not fundamentally broken. The six-lens acronym and most of the comparison mechanics are strong. The material defect is **integration placement**.

Current codeArbiter treats SMARTS primarily as an arbitration/reconciliation mechanism and, secondarily, as an autonomous sprint decision mechanism. That is narrower than the intended product principle: SMARTS should routinely inform material solution design before an approach is frozen.

This explains the observed operator experience that a SMARTS read often has to be explicitly requested even though SMARTS is supposed to be a foundational design principle.

The proposed correction is not a new command. It is deeper, proportional integration through existing workflow owners.

## Evidence boundary

These findings describe current development source at:

`arbiterForge/codeArbiter@8e88bce938ebf7dc8cfd934307b8d6859092d86e:/`

They are not claims that every currently distributed Claude, Codex or Pi package has identical behavior. Release claims require exact distributed-artifact evidence separately.

No excluded downstream or employer-specific source was used.

## Current SMARTS topology

SMARTS is distributed across more surfaces than one skill:

| Surface | Current role | Review |
|---|---|---|
| `core/surface/includes/smarts/core.md` | six lenses, cell grammar, recommendation strength, ADR-0025 Step 0 | strong rubric, overly defined around architectural variance |
| `decision-variance` | full variance discovery, SMARTS comparison and user-attributed arbitration | strong integration |
| `grader` | independent SMARTS comparison for one variance | strong integration |
| `decision-challenger` | adversarial ADR challenge with SMARTS context | appropriate |
| `SPRINT.md` | SMARTS on non-hard-gate autonomous decisions | deep integration |
| `brainstorming` | recorded-intent reads, alternatives, trade-offs, isolation and YAGNI | material SMARTS trigger gap |
| `feature` full lane | delegates solution shaping to brainstorming | inherits trigger gap |
| `feature` small lane | mini-spec to TDD | no general SMARTS integration, which is often appropriate |
| `writing-plans` | criterion/task decomposition and verification mapping | correctly should not rescore an approved design |
| `fix` | regression-first minimal correction | no conditional SMARTS remediation-choice contract |
| `debug` | evidence-led root-cause analysis | correctly should not use SMARTS to rank hypotheses |
| `refactor` | parity-bound behavior-preserving restructure | no conditional SMARTS method-choice contract |
| typed `smarts-apply` | delegated, scope-preserving plan-method mutation | strong and intentionally narrow |
| docs | broad conceptual explanation | route model still centers reconciliation and sprint |

## Primary integration defect

The strongest source evidence is the mismatch between the SMARTS/recorded-intent contract and `brainstorming`.

`core/surface/includes/smarts/core.md` says its scoring path serves decision-variance, grader, decision-challenger and sprint, and its ADR-0025 Step 0 explicitly applies to sprint plus brainstorming before scoring.

`core/surface/skills/brainstorming/SKILL.md` Phase 2 does good design work:

- proposes genuine approaches;
- forbids manufactured alternatives;
- checks accepted ADRs;
- applies an isolation lens;
- applies YAGNI;
- records the selected approach and trade-off.

It does **not** unambiguously require the six SMARTS lenses before selecting a material solution.

The regression tests mirror the same architecture. `.github/scripts/test_recorded_intent_surface.py` rigorously pins brainstorming's recorded-intent preflight, deferral handling, ADR checks and Phase 5 review. It does not establish that a material brainstorming approach choice actually receives a six-lens SMARTS evaluation.

Therefore "SMARTS is present in the repository" and "SMARTS automatically informed this design choice" are not equivalent.

## Historical trace

The repository history helps explain how this happened.

### 2026-05-10: initial generic SMARTS framework

Commit:

`c365852ac68db060fb50a9c3e3b9b2360309ce7d`

Source:

`.agents/skills/arbiter/references/smarts-framework.md`

The acronym was already the current six lenses:

- Scalable
- Maintainable
- Available
- Reliable
- Testable
- Securable

The historical file also contained richer per-lens considerations and pitfalls. Examples included scale dimensions, onboarding and handoff cost, partial availability, recovery, idempotency, state consistency, contract tests, trust boundaries and supply-chain integrity.

### 2026-06-04: v2 migration compressed SMARTS into decision-variance

Commit:

`f5a22ddff87b2120d23c916f7a5baac72b4b3565`

The migration explicitly retained the six-lens SMARTS engine inside `decision-variance`, compressed a much larger reference corpus, and retained the append-only user-attributed decision log.

This was a reasonable simplification, but it reinforced the association:

`SMARTS -> variance -> arbitration`

### 2026-06-04: sprint reused SMARTS for autonomous decisions

Commit:

`c408315d6496fcab07e0ca5fb22003f841ca94c7`

Sprint then reused SMARTS for non-hard-gate autonomous choices while deliberately not inheriting decision-variance's user-choice rule.

The framework therefore became deeply integrated in arbitration and autonomy without becoming equally explicit in ordinary attended solution shaping.

### Later ADR-0025 work

Current:

`.codearbiter/decisions/0025-recorded-intent-precedes-autonomous-scoring-and-spec-shaping.md`

ADR-0025 correctly recognized that SMARTS quality scoring alone does not prove conformance to recorded project intent. It added a recorded-intent Step 0 for sprint and brainstorming and explicitly avoided duplicating that step in arbitration.

That improved governance but did not close the separate six-lens invocation gap in brainstorming.

## Framework strengths to preserve

### Six-lens selection

The acronym is good. In particular:

- **Available** and **Reliable** are correctly separate.
- **Testable** is a first-order design property rather than an implementation afterthought.
- **Securable** evaluates whether security can be satisfied without retrofit rather than pretending a design review is a completed security assessment.
- **Maintainable** explicitly considers future engineers and agents.
- **Scalable** includes an anti-overengineering trap, which is important.

No lens should be renamed or replaced.

### Qualitative rather than numeric

Current SMARTS correctly avoids fake precision. Strong/Adequate/Weak/Indifferent cells plus strong/moderate/tied recommendation strength are more defensible than assigning arbitrary points.

That must remain true after deeper integration. Counting Strong cells is not SMARTS.

### Evidence-specific cells

The hard rule rejecting "best practice", "industry standard" and similar vague claims is valuable. A verdict should cite an option property, project constraint or concrete failure mode.

### No fake alternatives

Brainstorming already has the right rule: when one sane approach exists, say so. A deeper SMARTS integration must preserve that and support single-option fitness analysis instead of manufacturing a straw competitor.

### Explicit non-SMARTS factors

Cost, delivery speed, team skill, vendor lock-in and stakeholder constraints should remain visible but outside the acronym. SMARTS is a design-quality rubric, not a claim that six technical dimensions are the whole decision.

### Authority separation

The existing system correctly distinguishes a recommendation from authority.

Interactive arbitration records only explicit user choices. Sprint has bounded delegated autonomy. Typed `smarts-apply` requires explicit paired delegation and preserves protected plan scope.

Do not weaken those boundaries while making SMARTS easier to invoke.

## Semantic defect: Indifferent vs missing evidence

Current `core.md` defines `Indifferent` as a lens that does not differentiate options at the current scale/context.

The hard rules also direct genuine uncertainty to `Indifferent`.

Those are not the same state.

Example:

- Both options have equivalent, measured failover behavior -> Availability is **Indifferent**.
- The repository has no evidence for one option's failover behavior -> Availability is **Unknown**.

Collapsing the second into the first silently turns missing evidence into evidence of equivalence.

This is important enough to change the machine-readable vocabulary, not just documentation.

Current structured-artifact validation lives in:

`core/artifacts/internal/observation/sprint.go`

It machine-validates the six lens names, verdict vocabulary, justification budget, anti-hedging rules, distinct option labels and selected-option dominance. The implementation comments correctly say that it validates the comparison contract, not the truth of the model's assessment.

That is a good boundary. Add Unknown without pretending the validator can prove the model's factual judgment.

## Semantic defect: implicit evaluation context

A verdict such as "Scalable: Adequate" is not meaningful without the scenario.

Relevant context can include:

- expected users/jobs/data;
- planning horizon;
- single-region versus multi-region;
- outage tolerance;
- retry/idempotency requirements;
- trust boundary;
- delivery/team constraints.

The historical SMARTS file contained more of these prompts. Compression reduced context cost but made generic scoring easier.

The correction should be a small context envelope, not a large requirements template. Only facts that can differentiate the current choice are required.

## Priority and precedent

Current decision-variance uses a `Precedent:` line to surface similar prior decisions and observed lens patterns.

That is useful, but history should not silently become a weight system.

Preferred order:

1. explicit current user/spec priority;
2. explicit applicable project priority;
3. relevant precedent;
4. no assumed preference.

No numeric weights are needed.

## Integration design

### Three depths

The recommended model is:

1. **Scan** - concise six-lens fitness read for ordinary solution shaping.
2. **Comparison** - full matrix when real alternatives exist or the user asks for the detailed SMARTS read.
3. **Delegated decision** - current authority-bearing sprint path.

The important product change is that a user asking for "full SMARTS" changes presentation depth, not whether SMARTS happens at all.

### Full-lane feature planning

This is the primary missing integration.

Brainstorming Phase 2 should:

- identify real approaches;
- establish bounded decision context;
- apply SMARTS before selection;
- surface non-SMARTS constraints;
- retain Weak/Unknown cells and assumptions;
- seed a concise rationale into the spec.

The existing spec approval remains the user gate. SMARTS does not add a second approval.

### Small lane

Do not force a six-row table onto trivial two-file work.

Use a scan only when a materially different solution strategy exists. If that strategy reveals architectural scope, route to the full lane under the existing classifier.

### Fix and debug

Do not run SMARTS over debug hypotheses. Root cause is an evidence problem.

Once the cause is known, use SMARTS only when remediation choices materially differ. A forced minimal correction should remain cheap.

### Refactor

Likewise, a straightforward rename/extract does not need ceremony. A choice between materially different restructuring strategies can use SMARTS after the surface/parity contract is established and before implementation.

### Writing-plans

Do not rescore.

ADR-0025 explicitly rejected extending the recorded-intent check into writing-plans because the intended flow is record -> spec -> plan -> code. Reopening the design during plan decomposition would create unnecessary ceremony and contradictory second opinions.

Planning needs only a drift guard: if it discovers an undecided material design choice, return it to the design owner.

### Implementation review

The earlier interactive review suggested using the "design-quality reviewer" to detect SMARTS drift. Source inspection corrected that recommendation.

`core/surface/agents/design-quality-reviewer.md` is specifically an anti-slop reviewer for generated user-facing UI/reports/slides/charts/CLI/diagrams. It explicitly does not review codeArbiter's internal framework documents. Overloading it with engineering design-quality semantics would violate its current product contract.

`architecture-drift-reviewer` is also not a general solution-quality reviewer. It checks implementation against accepted ADRs.

The correct owner is the existing Phase 3 **spec-compliance review** in `subagent-driven-development`. If the approved spec persists SMARTS rationale and assumptions, that review can detect implementation that materially contradicts them without re-running the entire design decision or adding a new reviewer role.

## Typed SMARTS authority is a strength

The `smarts-apply` path is stronger than a prompt-only mechanism and should be preserved.

Current source requires:

- an approved plan;
- the matching approved spec;
- explicit paired `delegate-methods` user authority;
- an existing task;
- all six lens records;
- a selected option;
- a valid strength/rationale;
- no protected-scope change;
- no active affected writer;
- fresh downstream proof after a method revision.

It also rejects a selected option that is dominated by another option according to the submitted comparison.

That mechanism should remain narrow. It is not the general SMARTS interface. Attended planning needs reasoning, not an authority-producing engine call.

## Testing gap

Current tests are strong at proving:

- source/projection parity;
- recorded-intent prose;
- sprint authority;
- SMARTS typed scope preservation;
- cell vocabulary and anti-hedging;
- documentation claims.

The missing class is **trigger-behavior proof**.

Required future scenarios should include:

1. two real feature approaches trigger SMARTS before selection;
2. one sane approach gets a one-option scan, not fake alternatives;
3. missing evidence is Unknown, not Indifferent;
4. a trivial local choice avoids a full table;
5. a material fix strategy gets SMARTS after root cause;
6. debug hypothesis ranking stays evidence-only;
7. a material refactor strategy gets SMARTS before implementation;
8. writing-plans cannot silently invent a new material design choice;
9. approved spec retains the SMARTS rationale;
10. implementation drift against that rationale is caught by spec-compliance review;
11. explicit "full SMARTS read" expands detail without changing authority;
12. sprint delegation and existing hard gates remain intact.

A grep for the word SMARTS is not sufficient proof.

## Resource-waste and overengineering review

Deeper integration can fail by making the framework too present.

Avoid:

- loading detailed lens guidance every turn;
- dispatching graders for routine brainstorming;
- rescoring at spec, plan, TDD, every task and review;
- forcing option tables for obvious changes;
- creating a new SMARTS service, database, command or agent;
- duplicating recorded-intent reads across every consumer;
- persisting a new project-wide SMARTS file when current context/spec evidence is enough.

The cheapest durable design is one canonical semantic core, optional lazy lens detail, existing workflow owners and behavior-oriented trigger tests.

## Recommended implementation order

1. Correct the canonical SMARTS role and add Unknown semantics.
2. Add the small evaluation-context contract and optional explicit priority evidence.
3. Wire SMARTS into brainstorming Phase 2.
4. Persist concise rationale/assumptions in full-lane specs, including typed HTML.
5. Add proportional small-feature/fix/refactor triggers while keeping debug diagnosis separate.
6. Add the writing-plans drift guard.
7. Extend existing spec-compliance review for rationale invalidation.
8. Update docs to teach scan/comparison/delegated depths.
9. Add trigger-behavior fixtures and regenerate host surfaces.
10. Re-run existing SMARTS, recorded-intent, sprint-authority and artifact-authority suites to prove no authority regression.

## Confirmed findings

- Current main reviewed: `8e88bce938ebf7dc8cfd934307b8d6859092d86e`.
- SMARTS is a shared core contract, not one isolated skill.
- Decision-variance, grader and sprint use SMARTS explicitly.
- Brainstorming receives recorded-intent logic but lacks an equally explicit mandatory six-lens solution-selection step.
- The earliest traced SMARTS source already used the same six acronym lenses and contained richer lens guidance.
- Current `Indifferent` semantics conflate equivalence with uncertainty.
- Current typed `smarts-apply` has meaningful machine-enforced authority/scope protections.
- `design-quality-reviewer` is not the correct owner for general SMARTS implementation drift.

## Material contradictions

1. SMARTS/ADR-0025 documentation treats brainstorming as a scoring consumer, while the brainstorming body does not unambiguously require six-lens scoring before a material approach is selected.
2. `Indifferent` is defined as non-differentiation but is also used for genuine uncertainty.
3. Documentation explains SMARTS broadly while the practical route model emphasizes reconciliation and sprint more than normal attended feature design.

## Canon or claim-registry delta

No organization-wide ArbiterForge canon change is required.

The product-level codeArbiter semantic change proposed by the paired specification is:

> SMARTS is codeArbiter's cross-cutting six-lens design-quality rubric for material solution choices; the owning workflow supplies authority, persistence and presentation depth.

## Affected surfaces

- `core/surface/includes/smarts/**`
- `brainstorming`
- feature/small-lane routing
- fix/debug/refactor boundaries
- writing-plans drift routing
- subagent spec-compliance review
- sprint SMARTS vocabulary
- decision-variance/grader compatibility
- structured-artifact SMARTS schema/validator
- SMARTS documentation
- generated Claude/Codex/Pi surfaces
- SMARTS/recorded-intent/artifact workflow tests

## Decisions requiring user approval

Resolved by the maintainer for this specification:

- no public SMARTS command;
- adopt deeper automatic integration;
- preserve the six acronym lenses;
- add Unknown semantics;
- add bounded evaluation context;
- persist concise SMARTS rationale in full-lane specs;
- permit optional explicit project/spec priority evidence without numeric weights;
- use proportional triggers for small feature/fix/refactor;
- keep debug diagnosis evidence-led;
- do not rescore in writing-plans;
- preserve existing sprint/arbitration/typed authority boundaries.

## Verification still required

This review did not execute implementation tests or inspect exact distributed host artifacts for release behavior. Implementation must prove trigger behavior on source/generated surfaces and later qualify affected exact candidate artifacts according to the normal release path.

## Recommended next action

Implement `.codearbiter/specs/smarts-design-quality-integration.md` as one bounded cross-cutting campaign. The first implementation review should attack two failure modes specifically:

1. SMARTS became so ubiquitous that trivial work pays a recurring context/ceremony tax.
2. SMARTS still exists mostly as prose and tests cannot prove that material attended design choices actually pass through it.
