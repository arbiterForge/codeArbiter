# SMARTS design-quality integration

**Slug:** `smarts-design-quality-integration`
**Date:** 2026-09-26
**Source baseline:** `arbiterForge/codeArbiter@8e88bce938ebf7dc8cfd934307b8d6859092d86e:/`
**Intent:** Make SMARTS an automatic design-quality discipline for material solution choices without adding a public SMARTS command or turning every workflow step into a six-row ceremony.

## Problem

SMARTS is codeArbiter's established six-lens engineering framework:

- **Scalable**
- **Maintainable**
- **Available**
- **Reliable**
- **Testable**
- **Securable**

Current source implements the rubric well once SMARTS is invoked. It has a shared qualitative vocabulary, evidence-specific cells, recommendation strength, recorded-intent handling, arbitration ownership, sprint logging, decision-log persistence, and a typed delegated-method producer.

The integration point is narrower than the framework's intended role.

Today SMARTS is modeled primarily as:

1. the scoring mechanism for `decision-variance` and its grader;
2. the autonomous choice mechanism for `/sprint`;
3. a recorded-intent dependency of `brainstorming`.

That is not enough to make SMARTS the normal design-quality discipline for attended solution planning. In particular, `brainstorming` Phase 2 selects an approach using trade-offs, ADR checks, isolation and YAGNI, but does not unambiguously require a six-lens SMARTS evaluation before a material approach is selected. The structural tests strongly pin recorded-intent behavior on brainstorming, but do not prove that the six SMARTS lenses actually run at the solution-selection point.

The result is a real usability defect: an operator can need to ask for a "SMARTS read" to obtain analysis that should already have informed a material design choice.

There are also two semantic weaknesses in the current rubric:

1. **Indifferent conflates equivalence and missing evidence.** Current prose permits `Indifferent` both when a lens genuinely does not differentiate options and when the model is uncertain. Those are different states. Missing evidence must not masquerade as equivalence.
2. **Evaluation context is implicit.** A verdict such as "Scalable: Adequate" is only meaningful relative to a scale horizon, operating boundary and failure/security expectations. The historical SMARTS source contained richer lens prompts than the compressed current core.

Done means a normal attended design flow applies SMARTS automatically at the right decision points, keeps the reasoning proportionate to the choice, preserves workflow authority boundaries, and no longer depends on the user remembering to request the framework.

## Approach

Treat SMARTS as a **cross-cutting design-quality kernel** used by existing workflow owners, not as another public workflow.

The implementation has three evaluation depths:

1. **SMARTS scan** - lightweight six-lens fitness pass for ordinary solution shaping. It identifies material strengths, weaknesses, unknowns and decisive lenses without requiring a full comparison table in user-visible output.
2. **SMARTS comparison** - full option-by-option comparison when two or more materially plausible approaches exist, when the user explicitly asks for a full SMARTS read, or when reconciliation/arbitration already requires it.
3. **SMARTS delegated decision** - the existing authority-bearing autonomous path used by an approved sprint for in-scope method decisions, including the current typed `smarts-apply` boundary where applicable.

All three depths use one canonical SMARTS semantic definition. They differ in presentation, persistence and decision authority, not in what the acronym means.

The primary automatic application point is `brainstorming` Phase 2, before an attended full-lane feature or initial sprint approach is frozen. Other lanes invoke SMARTS only when they encounter a material solution choice. `writing-plans` does not rescore an already approved design.

No `/smarts` command is added. No new top-level skill, agent, persistent service, eager schema, background process or startup-loaded framework surface is added.

## Scope

### In scope

- Reframe canonical SMARTS semantics from "evaluation for architectural variances" to codeArbiter's design-quality rubric for material engineering solution choices.
- Preserve the six acronym lenses exactly: Scalable, Maintainable, Available, Reliable, Testable, Securable.
- Add an explicit `Unknown` / insufficient-evidence assessment state distinct from `Indifferent`.
- Add a bounded evaluation-context envelope so verdicts state the relevant operating assumptions.
- Add optional explicit lens-priority evidence without numerical weights.
- Make full-lane `brainstorming` run SMARTS before selecting a material approach.
- Support single-option SMARTS fitness scans when only one sane approach exists; do not manufacture alternatives.
- Add proportional SMARTS triggers for the small feature lane, bug remediation and refactor method selection when a material choice actually exists.
- Keep root-cause diagnosis itself evidence-led and outside SMARTS.
- Persist concise SMARTS design rationale and load-bearing assumptions in an approved full-lane specification.
- Make implementation/spec-compliance review detect invalidation of that recorded rationale without inventing a new review agent.
- Preserve `decision-variance`, grader, decision-challenger, sprint authority, append-only decision logging and typed `smarts-apply` boundaries.
- Restore richer per-lens prompts and traps from the historical SMARTS source as lazy reference material rather than bloating the hot path.
- Add behavior-oriented tests that prove when SMARTS runs and when it deliberately does not.

### Out of scope

- A public `/smarts` command.
- A new top-level skill or reviewer agent solely for SMARTS.
- Replacing `decision-variance` or changing its user-attributed arbitration authority.
- Numerical SMARTS scores, weighted sums, percentages or winner arithmetic.
- Treating SMARTS as user approval, artifact approval, prerequisite satisfaction, security authority, publication authority or acceptance evidence.
- Rerunning the full SMARTS design analysis in `writing-plans`, TDD or every implementation task.
- Forcing multiple alternatives when one credible approach exists.
- Making every reversible local coding choice user-visible.
- Broadening `design-quality-reviewer`; that agent is specifically the anti-slop reviewer for generated user-facing visual/formatted output.
- Converting SMARTS into a compliance framework or replacing security-specific review and hard gates.

## Decided parameters

### 1. Canonical role

The canonical description becomes materially equivalent to:

> SMARTS is codeArbiter's six-lens design-quality rubric for material engineering solution choices. Workflow owners decide when a choice needs a scan, a full comparison, or delegated autonomous handling; SMARTS itself does not grant authority.

"Architectural variance" remains one important consumer, not the definition of the framework.

### 2. Lenses remain unchanged

The acronym is stable and no lens is added, removed or renamed:

- Scalable
- Maintainable
- Available
- Reliable
- Testable
- Securable

Business or delivery factors such as cost, time-to-market, team skill, vendor lock-in and stakeholder constraints remain **non-SMARTS considerations**. They are surfaced alongside SMARTS when material and never silently converted into a seventh lens.

### 3. Assessment vocabulary

Every evaluated lens uses exactly one state:

- **Strong** - performs well for the stated context.
- **Adequate** - acceptable for the stated context.
- **Weak** - materially poor for the stated context.
- **Indifferent** - available evidence shows the lens does not materially differentiate the options at the stated context/horizon.
- **Unknown** - evidence required to judge the lens is missing, contradictory or not yet established.

`Unknown` is not neutral and must not be treated as `Indifferent`, Adequate or a pass. A recommendation may still be made with Unknown cells only when the missing evidence is not decision-critical; the output names the missing observation and why it does not currently control the decision. A decision-critical Unknown prevents a strong recommendation and must be surfaced before an irreversible or authority-bearing choice.

The machine-readable SMARTS decision schema, validators and tests must adopt the same vocabulary. No compatibility shim may silently map Unknown to Indifferent.

### 4. Evaluation context envelope

Before scoring a material choice, the caller establishes only the context needed to make the lenses meaningful:

- **decision** - the actual choice being made;
- **scope/horizon** - the bounded system and relevant planning horizon;
- **scale expectation** - only when scale could differentiate approaches;
- **failure/availability expectation** - only when failure behavior could differentiate approaches;
- **security/trust boundary** - only when relevant to Securable;
- **non-SMARTS constraints** - cost, schedule, team skill, vendor or stakeholder constraints that materially affect the recommendation.

The envelope is scope-sized and fail-soft. It does not require every field for every choice and does not create a new persistent project file. Existing project context, the active spec, explicit user steering and relevant recorded decisions provide the evidence when available.

### 5. Priority and dominance

SMARTS remains qualitative. The implementation must not count Strong cells or invent weights.

When lenses conflict, preference evidence is applied in this order:

1. explicit current user or approved-spec priority;
2. explicit applicable project priority already recorded in project context or an accepted decision;
3. relevant prior decision precedent, clearly labelled as precedent rather than authority;
4. no assumed priority.

Absent explicit priority evidence, a tied comparison remains tied.

### 6. Recorded intent stays governance, not acronym semantics

ADR-0025's recorded-intent requirement remains in force for the consumers it governs. The implementation may split pure SMARTS lens semantics from recorded-intent helper prose to reduce consumer confusion, but it must preserve the accepted behavior:

- brainstorming and sprint consult relevant recorded intent before choosing;
- arbitration retains its own authority-order handling and named exemption from duplicate Step 0 behavior;
- missing decomposition records fail soft;
- no bulk read of `plans/` or `decisions/` is introduced.

Moving text between files does not change ADR-0025's behavioral obligations.

### 7. Canonical source structure

Prefer a small hot-path core plus lazy detail:

- `includes/smarts/core.md` - canonical role, lens names, assessment vocabulary, comparison/strength rules and context contract;
- a lazy SMARTS lens reference under the same include family - richer considerations, traps and examples for each lens, derived from and modernizing the original SMARTS source;
- `includes/smarts/decision-log-format.md` - existing append-only persistence contract;
- recorded-intent instructions remain owned by the callers/governance contract that need them or by a narrowly shared include if that reduces duplication without widening scope.

Exact file splitting is an implementation choice only if it preserves these ownership boundaries and generated-host parity.

### 8. Brainstorming is the primary automatic integration point

In full-lane `brainstorming` Phase 2:

1. identify genuine approaches;
2. do not manufacture alternatives;
3. establish the bounded SMARTS context;
4. run a SMARTS scan or comparison;
5. surface relevant non-SMARTS constraints;
6. select or recommend the approach under the caller's existing authority;
7. record the design rationale, assumptions, Weak/Unknown cells and decisive lenses in the running notes that seed the spec.

When there are two or more materially plausible approaches, use a comparison. When only one sane approach exists, run a single-option fitness scan and explain why no alternative was credible.

SMARTS does not create another approval gate. The existing spec approval remains the user decision boundary for attended feature planning.

### 9. Small feature lane is conditional

Do not turn the small lane into a full architecture exercise.

The small lane runs a SMARTS scan only when its otherwise-small change still contains a material solution choice, such as two meaningfully different implementation strategies with distinct failure, testability, security or maintenance consequences.

A trivial or obvious local change can state `SMARTS: no material solution choice` and proceed through the existing confirmation/TDD path. This statement is diagnostic, not a new persisted artifact.

If the choice reveals scope that violates the existing small-lane classification criteria, route to the full lane rather than using SMARTS to justify keeping an architectural change "small."

### 10. Bug and debug boundary

`debug` remains evidence-led. SMARTS must not rank root-cause hypotheses or replace confirmation/refutation evidence.

After root cause is established:

- if remediation is effectively forced, `/fix` proceeds without a full comparison;
- if two or more materially different remediation strategies exist, the fix owner runs a SMARTS scan/comparison before implementation;
- if the evidence reveals a behavior/design ambiguity, the existing ADR path remains the owner.

This keeps diagnosis and solution selection distinct.

### 11. Refactor boundary

A routine behavior-preserving rename/extract/move with one credible method does not need a full SMARTS table.

When a refactor has materially different restructuring strategies, perform the SMARTS scan/comparison after the exact surface and parity requirements are known and before implementation chooses the method. SMARTS cannot weaken the behavior-preservation contract, coverage gate or surface boundary.

### 12. Writing-plans does not rescore

Preserve ADR-0025's record -> spec -> plan -> code chain.

`writing-plans` must not repeat a full SMARTS evaluation of an approved design. It may only enforce a **design-drift guard**: if planning discovers a material solution choice that is not already decided by the approved spec and is not a reversible implementation method within existing authority, return the choice to the owning design workflow rather than silently inventing architecture in the plan.

This guard is a routing check, not a second design review.

### 13. Sprint behavior remains authority-correct

`/sprint` remains the autonomous owner for non-hard-gate choices inside its approved scope.

- Existing SMARTS logging and hard-gate behavior remain.
- Material delegated plan-method changes continue to use the existing typed `smarts-apply` authority when supported and explicitly delegated.
- A concise scan may be used as presentation for ordinary low-impact in-scope choices, but the underlying six-lens evidence must remain available wherever current logging or typed authority requires it.
- `Unknown` cannot be used to evade a hard gate or invent missing user authority.
- A SMARTS result is still not an approval receipt or task acceptance.

### 14. Spec persistence

Approved full-lane specs gain a concise SMARTS design-rationale record containing, at minimum:

- chosen approach;
- alternatives considered, or an explicit single-option statement;
- decisive lens/lenses;
- material Weak and Unknown observations;
- load-bearing assumptions;
- relevant non-SMARTS considerations;
- explicit priority evidence when one influenced the recommendation.

For typed HTML artifacts this must be represented through the artifact model/engine, not by scraping or hand-editing rendered HTML. For legacy Markdown, use a stable documented section.

The rationale is design evidence, not a new source of execution authority.

### 15. Implementation drift check reuses existing spec-compliance ownership

Do not repurpose `design-quality-reviewer`; its source contract is specifically visual/formatted-output anti-slop review.

Instead, extend the existing spec-compliance review in `subagent-driven-development` so that, when the approved spec carries SMARTS rationale, it checks only for **material invalidation**:

- implementation contradicts a load-bearing assumption;
- implementation introduces a Weak or Unknown condition that the approved design explicitly avoided;
- implementation uses a materially different approach than the one approved.

A mismatch returns the task/scope to the owning planning/reconciliation path. The implementation reviewer does not rerun the entire SMARTS decision or choose a replacement design.

### 16. Documentation

The SMARTS concepts documentation must teach the three depths and the authority distinction:

- scan - routine solution fitness;
- comparison - material alternatives and explicit full read;
- delegated decision - approved autonomous choice.

Docs must make clear that ordinary attended feature shaping is now a primary consumer. Reconciliation and sprint are no longer presented as the only meaningful routes where SMARTS happens.

### 17. Resource and complexity budget

Deeper integration must not make normal interactions materially slower or more context-heavy.

- No new eager startup read.
- No bulk ADR/plan read.
- Detailed per-lens guidance is lazy.
- Do not dispatch a grader for ordinary brainstorming; inline analysis is the default.
- Do not create a full table when a concise scan communicates the decision.
- Do not rerun SMARTS at plan, TDD and every task boundary.
- Generated-host copies remain projections of canonical shared source.

The goal is better decision quality with less operator prompting, not more ceremony.

## Acceptance criteria

1. **Canonical definition.** The canonical SMARTS source defines it as codeArbiter's six-lens design-quality rubric for material engineering solution choices, while retaining architectural variance as a consumer rather than the framework's definition.
2. **No new public surface.** The generated command/skill/agent catalogs show no new public SMARTS command, top-level SMARTS skill or SMARTS-only reviewer agent.
3. **Six-lens stability.** Canonical source and all generated host projections retain exactly Scalable, Maintainable, Available, Reliable, Testable and Securable as the acronym lenses.
4. **Unknown semantics.** Canonical prose, machine-readable SMARTS schema/validator and tests distinguish `Unknown` from `Indifferent`; seeded missing-evidence fixtures cannot pass as Indifferent and a decision-critical Unknown cannot produce a strong recommendation.
5. **Context envelope.** SMARTS analysis fixtures prove verdicts are bound to a stated decision and only the context dimensions relevant to that choice; the workflow does not require irrelevant fields or create a new global configuration file.
6. **No numeric scoring.** Tests reject or otherwise prevent any generated winner logic based on cell counts, numeric weights or arithmetic scores.
7. **Full-lane feature trigger.** A feature fixture with two materially plausible approaches produces a six-lens SMARTS comparison before approach selection and persists the rationale into the spec.
8. **Single-option trigger.** A feature fixture with one credible approach runs a one-option SMARTS fitness scan, records why alternatives were not credible and does not invent a straw option.
9. **Explicit full-read request.** An attended user request for a full SMARTS read expands the presentation to the comparison detail without changing decision authority or adding a command route.
10. **Small-lane proportionality.** A trivial small-lane change proves SMARTS does not manufacture a comparison or expand scope; a small-looking change with a material design fork either receives a bounded scan or is routed to the full lane when existing small-lane criteria are violated.
11. **Debug/fix separation.** Debug fixtures prove SMARTS is absent from hypothesis ranking/root-cause confirmation. Fix fixtures prove materially distinct remediation strategies are evaluated before implementation while a forced minimal correction avoids unnecessary ceremony.
12. **Refactor proportionality.** A straightforward behavior-preserving refactor proceeds through current parity gates without a forced full table; a fixture with materially distinct restructuring strategies applies SMARTS before implementation and cannot weaken parity requirements.
13. **Planning boundary.** `writing-plans` does not rescore the approved design. A fixture where planning discovers a new material design choice returns to the owning design path instead of silently embedding the choice in plan tasks.
14. **Sprint preservation.** Existing sprint tests for recorded intent, logging, hard gates, delegation and `smarts-apply` remain green after the semantic changes; Unknown cannot manufacture authority or bypass a hard stop.
15. **Typed validator closure.** The structured-artifact SMARTS validator accepts the updated qualitative vocabulary, still rejects missing lenses, hedging, dominated selected options, malformed choices and protected-scope expansion, and keeps acceptance_granted false for method-only SMARTS authority.
16. **Spec rationale persistence.** New full-lane HTML specs can store and retrieve the SMARTS design rationale through typed engine operations; legacy Markdown has one documented stable section. Rendered HTML is never parsed as authority.
17. **Implementation drift.** Spec-compliance fixtures detect a task that materially contradicts the approved SMARTS approach or load-bearing assumption and route it back without creating a new reviewer agent or autonomously choosing a replacement.
18. **Historical lens detail retained lazily.** The richer considerations/traps from the original SMARTS framework are available through lazy source/reference material, and no ordinary SMARTS scan requires bulk-loading that detail when the concise core is sufficient.
19. **Behavioral trigger tests.** Tests cover at least: multi-option feature, single-option feature, missing evidence, trivial local choice, materially different fix strategies, materially different refactor strategies, planning-time design drift, explicit full-read request and sprint delegated decision.
20. **Host parity.** Canonical changes regenerate cleanly across Claude, Codex and Pi; relevant surface/parity checks prove no host silently loses the trigger or assessment semantics.
21. **Recorded-intent preservation.** ADR-0025 behavior remains intact: correct consumers, authority-order semantics, index-first reads, fail-soft missing decomposition state, contradiction handling and no duplicate recorded-intent rescore in writing-plans.
22. **Resource bound.** An ordinary full-lane approach-selection fixture does not dispatch grader/scout, does not bulk-read decisions/plans, and loads detailed lens guidance only when needed. A trivial small-lane fixture adds no full SMARTS table or extra workflow artifact.
23. **Documentation.** The SMARTS concept page explains scan/comparison/delegated depths, Unknown vs Indifferent, evaluation context, non-SMARTS considerations, attended feature shaping, sprint authority and reconciliation authority without implying SMARTS grants approval.
24. **Regression closure.** Existing SMARTS, recorded-intent, decision-variance, sprint authority, artifact authority, feature, refactor, debug/fix, generated-surface and docs tests remain green or are intentionally updated with equivalent or stronger assertions.

## Verification strategy

Implementation must prove both **semantic correctness** and **trigger correctness**.

Required proof should include:

- unit/schema tests for verdict vocabulary, Unknown behavior, dominance and no-numeric-scoring rules;
- structural tests over canonical and generated SMARTS/brainstorming surfaces;
- workflow fixtures for the trigger cases in AC-19;
- existing recorded-intent surface tests;
- existing artifact sprint-authority and approval-adapter tests;
- generated-surface parity checks;
- documentation content tests;
- exact candidate host-package reference/resource closure as required by the affected release path.

A grep proving that the word `SMARTS` appears in brainstorming is insufficient. At least one behavioral fixture must demonstrate that a material approach choice cannot be selected without the SMARTS pass, and at least one negative fixture must demonstrate that a trivial choice does not receive unnecessary ceremony.

## Risks and failure modes

- **Ceremony inflation:** SMARTS can become a table tax on every choice. The depth model, single-option scan and negative trigger fixtures are required to prevent this.
- **Unknown inflation:** A weak model could label hard judgments Unknown to avoid commitment. Unknown therefore requires a named missing observation and does not replace evidence-specific reasoning.
- **Pseudo-math:** Adding a fifth state can tempt ranking arithmetic. Numeric scoring remains prohibited.
- **Authority confusion:** A good SMARTS recommendation can be mistaken for approval. Existing workflow owners and typed authority receipts remain the only authority sources.
- **Recorded-intent duplication:** Moving SMARTS source text can accidentally rerun ADR-0025 logic everywhere. The accepted consumer scope remains pinned.
- **Context cost:** Restoring historical lens detail can bloat normal prompts. Rich detail stays lazy and canonical core stays concise.
- **Plan churn:** Re-running the analysis in writing-plans would create contradictory second opinions after approval. The plan lane gets only a drift/routing guard.
- **Review-agent overlap:** `design-quality-reviewer` has a different product role and must not be repurposed. Implementation drift belongs to existing spec-compliance ownership.
- **Host drift:** Canonical source must regenerate every host projection and tests must pin the trigger contract, not only prose parity.
- **Historical compatibility:** Existing decision logs and sprint logs remain valid historical records. No migration rewrites prior entries solely because the verdict vocabulary expands.

## Non-goals

- SMARTS is not a requirements framework.
- SMARTS is not a substitute for TDD, security review, dependency review, migration review or architecture reconciliation.
- SMARTS does not make an ADR implemented or verified.
- SMARTS does not decide business strategy by itself.
- SMARTS does not require user-visible tables for every use.
- SMARTS does not create authority from model confidence.

## Open questions

None. The maintainer approved the direction captured here, including no public command, automatic integration at material design points, Unknown semantics, a bounded context envelope, concise spec persistence, optional explicit priority evidence, proportional triggers and preservation of the existing planning/authority boundaries.

**Governs:** core/surface/includes/smarts/**, core/surface/skills/brainstorming/SKILL.md, core/surface/commands/feature.md, core/surface/commands/fix.md, core/surface/skills/debug/SKILL.md, core/surface/skills/refactor/SKILL.md, core/surface/skills/writing-plans/SKILL.md, core/surface/skills/subagent-driven-development/SKILL.md, core/surface/SPRINT.md, core/surface/skills/decision-variance/**, core/surface/agents/grader.md, core/artifacts/internal/observation/sprint.go, core/artifacts/internal/operations/sprint.go, site/src/content/docs/concepts/smarts.mdx, .github/scripts/test_recorded_intent_surface.py
