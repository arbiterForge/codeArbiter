# Correctness review and implementation-plan handoff

**Date:** 2026-09-25
**Disposition:** amended draft pair prepared for review; no implementation or execution approval.
**Review boundary:** source-grounded correctness review by the authoring assistant, not an independent policy-owned review receipt.

## Reviewed artifacts and current source

The starting specification is `SPEC-EXERCISE-BROWNFIELD`, revision 4, at `arbiterForge/codeArbiter@91b0966883acb43fda4b9a3d435c13447e1da666:.codearbiter/specs/exercise-ready-brownfield.html`. Its model digest is `4c9023356fddede46a5feced03fe29d337965adf4f4f38e4cbf519e1b275e355`. The current main inspection returned `4187f1e22dc7da3cf755a2654bbf7ec268236126`; main is development evidence, not a release assertion.

The amended specification is revision 7, with 41 criteria and 101 scenarios. Its normative digest is `addf0bf9bea697f1edd485e56d41b29810ced5d374d59ccf6d60197f9bda0d7a`. The single draft plan is `PLAN-EXERCISE-BROWNFIELD`, revision 2, at `.codearbiter/plans/exercise-ready-brownfield.html`, bound by native `draft_preview` to that exact digest.

Overlapping work was re-read: #854 `680cb03d39f91fd3e4a8ad968f0536a84dde9f0d` and #871 `2b6e5a5bcfdb5d4713ba6d8f655d9cc99bfd4827`, both open/open. No branch was imported. Their owner changes must be revalidated before overlapping implementation.

## Main conclusion

The largest implementation risk was an ownership hole: the spec required bounded legacy context mutations while assuming that those writers already existed. The current context-creation procedure still directly writes several of those documents. The revised spec and plan explicitly provide the missing engine-owned, finite Markdown content contract instead of asking an implementer to invent a generic rewrite helper.

Two other likely failures were an incremental refresh that accidentally redispatched all six domains and a readiness milestone treated as permission to commit an incomplete HTML plan. Both are now explicit contracts. The optional guidance experiment is not the first implementation dependency.

There are thirteen findings below: twelve specification/integration findings and one reproduced installed-helper failure. Hypothetical consequences are not represented as executed product failures. The first premortem and older evidence files remain unchanged.

## SR-01. Ambiguity and refresh scope have contradictory admission rules

**Affected criteria:** `AC-008`, `AC-009`, `AC-011`

**What would fail:** SEC-03 rejects ambiguous findings while AC-008 permits them. Every refresh can be read as requiring six new full-repository reports.

**Addressed in the specification/plan:** Require six domains only for initial or explicitly full onboarding. Scoped refresh validates only affected assignments and retains the extent of previously known coverage. Complete report transport does not mean every finding is certain.

**Rejecting evidence required:** An ambiguous returned finding reaches gap handling; a missing report cannot. A one-command refresh launches only its affected evidence assignment, not six new scouts.

Source: `arbiterForge/codeArbiter@4187f1e22dc7da3cf755a2654bbf7ec268236126:core/surface/skills/context-creation/SKILL.md:151-168`.

Source: `arbiterForge/codeArbiter@4187f1e22dc7da3cf755a2654bbf7ec268236126:core/surface/skills/context-check/SKILL.md:58-85`.

## SR-02. Read-only discovery accidentally forbids its own model transport

**Affected criteria:** `AC-002`, `AC-038`

**What would fail:** The absolute no publishing source/data rule also forbids sending approved source to the selected model provider; activation can run before the intended boundary exists.

**Addressed in the specification/plan:** Separate approved inference transport from repository-controlled egress, credential-file discovery and activation side effects. Pre-activation inspection must run outside active repository hooks when no qualified pre-start boundary exists.

**Rejecting evidence required:** A local/no-network fixture performs no egress; an explicitly authorized remote-provider fixture uses only that inference channel. Repository text cannot authorize another destination.

## SR-03. Legacy content has no existing bounded writer to reuse

**Affected criteria:** `AC-041`, `AC-022`

**What would fail:** The scaffold, board, override and provenance helpers exist, but no schema-owned bounded writer currently owns tech-stack/coding-standards/security-controls/code-map synthesis. A plan that just calls the existing writer is not executable.

**Addressed in the specification/plan:** Enroll one closed internal repository-context kind in the existing engine for the five existing content documents, with canonical Markdown and finite per-document typed codecs. Keep existing task, question, audit, release and ADR owners. No new JSON canonical shadow or generic text replacement API.

**Rejecting evidence required:** Exact-byte unowned-region preservation, duplicate/unknown owned-field rejection, actual approval-bound adoption, native package capability and source/generated consumer tests precede enabling the new write route.

Source: `arbiterForge/codeArbiter@4187f1e22dc7da3cf755a2654bbf7ec268236126:core/surface/skills/context-creation/SKILL.md:112-145`.

Source: `arbiterForge/codeArbiter@4187f1e22dc7da3cf755a2654bbf7ec268236126:core/pysrc/init-codearbiter.py:90-107`.

Source: `arbiterForge/codeArbiter@4187f1e22dc7da3cf755a2654bbf7ec268236126:core/artifacts/internal/kind/contracts.go:6-15`.

Source: `arbiterForge/codeArbiter@4187f1e22dc7da3cf755a2654bbf7ec268236126:.codearbiter/decisions/0037-extensible-structured-artifact-engine.md:23-33`.

## SR-04. New provenance could look clean to an old reader

**Affected criteria:** `AC-014`, `AC-015`, `AC-031`

**What would fail:** Versioned compatibility was requested without a mixed-reader policy. Current v1 readers skip unknown records, which can turn a new schema into silence rather than an explicit unknown.

**Addressed in the specification/plan:** Gate new writes on qualified paired producer/consumers; read v1 conservatively, never silently rewrite all records, and refuse verified-context claims on old hosts. Use named raw-byte digest and membership methods in new records.

**Rejecting evidence required:** Mixed v1/v2 and old/new reader fixtures, missing records, stale doc bytes and added instructions never become false freshness.

Source: `arbiterForge/codeArbiter@4187f1e22dc7da3cf755a2654bbf7ec268236126:core/pysrc/_provenancelib.py:251-297`.

Source: `arbiterForge/codeArbiter@4187f1e22dc7da3cf755a2654bbf7ec268236126:core/pysrc/_provenancelib.py:779-881`.

## SR-05. Freshness can invalidate itself or leak between actors

**Affected criteria:** `AC-018`, `AC-019`, `AC-033`

**What would fail:** The spec binds everything to current state but does not separate evidence inputs from files the workflow itself writes, nor semantic dedup from coincidentally equal text.

**Addressed in the specification/plan:** Separate source dependencies, approved output preimages and allowed transient state; scope delivery by recipient, scope and epoch. Planned task edits are reconciled by existing review/verification, not mistaken for unrelated concurrent edits.

**Rejecting evidence required:** Own marker/journal updates do not launch new scouts; a changed cited source still invalidates its claim; equal command text under different cwd is never deduplicated.

## SR-06. Existing repository rules can be demoted while new policy is over-approved

**Affected criteria:** `AC-035`, `AC-012`, `AC-026`

**What would fail:** Treating all existing instructions as evidence can discard valid effective repository conventions or demand renewed approval for every inherited rule.

**Addressed in the specification/plan:** Preserve effective host/user/repository instruction precedence. Distinguish carrying an existing applicable constraint unchanged from inventing/adopting a new normative rule or claiming a new Arbiter approval.

**Rejecting evidence required:** An unchanged effective root convention is referenced without a repeat interview; an upstream/local conflict still requires resolution and cannot be settled by a copied accepted label.

## SR-07. argv-only guidance cannot represent real commands honestly

**Affected criteria:** `AC-017`, `AC-022`, `AC-023`

**What would fail:** CI scripts may contain shell expansion, pipelines or platform-specific launchers. Converting every declaration to argv fabricates equivalent behavior; unsafe path rejection also omits the legitimate root cwd dot.

**Addressed in the specification/plan:** Use actionable literal argv with resolved executable/profile only when evidenced. Otherwise retain a declaration reference, not a pretend executable argv. Root dot is valid for scope/cwd only; target files must remain strict descendants.

**Rejecting evidence required:** Pipeline declaration remains unverified/reference-only; arguments containing spaces remain distinct; root cwd works while traversal/file target dot fails.

## SR-08. The benchmark gate is not reproducible enough

**Affected criteria:** `AC-028`, `AC-037`, `AC-031`

**What would fail:** Three sequences and medians lack pairing/aggregation rules, provider cache accounting and correctness-oracle independence; cherry-picking reruns could pass.

**Addressed in the specification/plan:** Freeze fixture task IDs, pairing/order, exact model/profile and independent oracle hashes before any paid run. Include every attempt and failure; distinguish unknown from zero. Keep the original proposed thresholds but define paired per-fixture aggregation and failure dispositions.

**Rejecting evidence required:** A zero baseline, missing usage, mixed model/cache conditions, selected best rerun or oracle copied from candidate guidance yields no-go/inconclusive, not a saving.

## SR-09. Slice readiness is confused with the existing all-plan commit gate

**Affected criteria:** `AC-039`, `AC-029`, `AC-030`

**What would fail:** Current _preflight_current_acceptance requires every live plan task accepted/current, and mandatory criteria cannot be disposed by a table label. The draft promises independent slices without distinguishing readiness reporting from permission to commit an unfinished plan.

**Addressed in the specification/plan:** Keep the all-plan gate unchanged. E0-E2 readiness is a scoped qualification result, not an exemption. Conditional tasks must have explicit approved branch outcomes, with genuine no-go evidence not a fabricated acceptance of implementation. Any future partial delivery needs an approved amendment of the same plan before committing; no new public gate or receipt shortcut.

**Rejecting evidence required:** Exercise acceptance can be reported while P1 remains unselected, but commit preflight still rejects any pending live task. No assumed applicability skip or fake PASS.

Source: `arbiterForge/codeArbiter@4187f1e22dc7da3cf755a2654bbf7ec268236126:core/pysrc/_artifactlib.py:556-680`.

Source: `arbiterForge/codeArbiter@4187f1e22dc7da3cf755a2654bbf7ec268236126:core/artifacts/internal/validate/validate.go:520-537`.

## SR-10. Native reader and engine global failure domains can contaminate unrelated work

**Affected criteria:** `AC-034`, `AC-022`, `AC-041`

**What would fail:** Current engine scans all registered artifacts and globally blocks on pending transactions. Adding guidance to that catalog can make malformed optional guidance break unrelated spec/plan work; read-only inspections themselves can create local lock/cache state.

**Addressed in the specification/plan:** Require kind-owned parsing and explicit failure locality with regression evidence, without weakening existing pending-transaction recovery. Unselected/unsupported optional guidance must not be loaded as an active spec/plan. Preserve the documented global pending-transaction gate; prevent optional operations from leaving it pending by qualified recovery.

**Rejecting evidence required:** An invalid optional guidance fixture cannot silently become approved context or poison unrelated legacy reads; a real pending transaction still requires recovery and cannot be hidden.

Source: `arbiterForge/codeArbiter@4187f1e22dc7da3cf755a2654bbf7ec268236126:core/artifacts/internal/operations/engine.go:61-108`.

Source: `arbiterForge/codeArbiter@4187f1e22dc7da3cf755a2654bbf7ec268236126:core/artifacts/internal/repository/catalog.go:27-75`.

## SR-11. A plan could turn conditional trials into global prerequisites

**Affected criteria:** `AC-001`, `AC-020`, `AC-027`, `AC-039`

**What would fail:** Plan prerequisites are global in the current schema; adding unpaid/unselected P1 or every platform there would block core preparation.

**Addressed in the specification/plan:** Keep global prerequisites to actual spec/plan approval and source integrity. Scope host/trial authorization to the tasks that consume it, and explicitly bound greenfield reuse to the shared first-input mechanism.

**Rejecting evidence required:** Core planning and deterministic fixtures do not request paid credentials, create native consumer files or wait for an unselected pilot; real host claims still require their own exact evidence.

## SR-12. The authoring request is stale inside the normative document

**Affected criteria:** `AC-032`

**What would fail:** SEC-01 says no plan was requested and the campaign guide says approval must precede any planning, even after the maintainer explicitly requests the plan.

**Addressed in the specification/plan:** Update the active request and handoff: prepare one unapproved draft pair for combined review using the existing draft-preview machinery. This is not spec approval, runtime implementation, paid trial authorization or an autonomous sprint grant. Preserve historical review records.

**Rejecting evidence required:** Both artifacts validate structurally/readiness and remain draft/unapproved; no plan binding to fabricated approved authority.

## SR-13. Installed intent checking crashes on successful native validation

**Affected criteria:** `AC-001`, `AC-032`

**What would fail:** Reproduced with the exact ca 2.21.16 installed _intentlib.py: a ready spec returns diagnostics null and the helper exits 2 with NoneType is not iterable. This can block ordinary plan preparation before campaign work starts.

**Addressed in the specification/plan:** Add a bounded prerequisite fix to normalize documented empty diagnostics from a valid native response; preserve invalid/false/error handling. Today use native ready validation and explicit typed criterion/scope traversal as separately reported evidence, not a claimed successful helper run.

**Rejecting evidence required:** Positive null and empty-list success; invalid diagnostics, valid false, transport errors and unapproved input stay distinguishable. No source implementation change is made in this planning session.

Source: `arbiterForge/codeArbiter@4187f1e22dc7da3cf755a2654bbf7ec268236126:core/pysrc/_intentlib.py:main`.

Source: `arbiterForge/codeArbiter@4187f1e22dc7da3cf755a2654bbf7ec268236126:core/surface/skills/writing-plans/SKILL.md:52-73`.

## Additional plan correctness checks

The plan has 60 pending tasks and 11 checkpoints. All 41 criteria are covered, every task maps to at least one criterion, dependencies resolve without cycles, and checkpoint dependencies point to earlier checkpoints. Shared-source task paths include their generated host derivatives; test creation precedes CI registration. Each test name is a proposed implementation obligation, not an executed test result.

The original create attempt used broad BF-CORE/BF-PILOT execution-scope labels. The installed engine correctly rejected it with INVALID_SCOPE because the current protocol requires execution_scope to equal checkpoint. The task records were corrected to the actual contract and then created successfully. No native contract or validator was relaxed.

The final task depends on the selected pilot qualification task. A pilot no-go is not a synthetic acceptance of those implementation tasks. A disposable native draft fixture retired only the nine unstarted pilot tasks and two pilot checkpoints, removed their graph edges, and still passed native readiness with 51 live tasks and all required criterion relationships. This tests draft structure and coverage only. A real no-go needs actual decision authority, an approved same-plan amendment, and normal reconciliation of stale acceptance; that authority transition was not fabricated or tested as completed.

Evaluator-side answers and scoring oracles are explicitly outside the solving model workspace and input in T-002, T-045 and T-057. A frozen oracle that the solver can read is not independent evidence. Leakage invalidates the trial.

## Verification actually run

The exact published ca 2.21.16 archive matched SHA-256 `32588a10eb5070b408443e5a0ef23453128725d33574c49a93f5edf5edf22fb8`. Its native Windows AMD64 engine and installed-resource bridge performed all canonical artifact reads/writes. Resource preflight explicitly retained live_host_verified false. No global installation or settings were modified.

Both final artifacts pass native structural and ready validation and fail approval validation as unapproved drafts. Native outline/readback matched the task records and the exact spec binding; replay and standalone draft validation were checked. Planning negative controls reject a cycle, missing criterion coverage, unknown dependency and incorrect execution scope. None of those checks proves campaign implementation.

The installed HTML intent helper was executed and failed with exit 2: diagnostics was null on a successful native response and its consumer attempted to iterate it. Direct native ready validation and explicit typed scope/criterion traversal are recorded separately; they are not described as a successful run of the broken helper. T-004 contains the bounded fix and positive/negative controls. No runtime helper was edited in this planning change.

The machine-readable `plan-authoring-evidence.json` records final identities and the local publication checks. No new real model onboarding, paid evaluation, consumer instruction publication, full native product conformance, independent policy review or execution approval was performed.

## Approval and remaining risks

The finite repository-context kind is a material proposed architecture/enrollment detail, not an already accepted or shipped capability. Approve the exact revised spec and draft plan before implementation. The new aggregate scout limits and the predeclared evaluation thresholds are proposed parameters, not measured savings.

The real exercise profile, actual read-only scout containment, actor delivery through compaction, provider usage accounting, lossless legacy adoption and exact installed native writes remain qualification obligations. Existing host documentation describes loading, not an automatic enforceable trust boundary. The plan requires positive useful contributions as well as negative safety controls; an all-BLOCK implementation cannot pass.

Organization canon and cross-product claim registries are unchanged. The September bootstrap remains historical. Runtime, packages, CI configuration, generated plugin payloads, existing user/project state and consumer instructions are not changed by this planning PR.

## Next action

Review and approve the current native pair, then begin CP-00. Revalidate moving ownership at T-001 and fix the installed intent-consumer prerequisite at T-004 before claiming the ordinary planning journey works. Retain the separate approval/data/resource boundary for real trials and the existing all-live-task commit gate.
