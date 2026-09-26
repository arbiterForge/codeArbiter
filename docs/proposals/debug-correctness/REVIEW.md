# Debug correctness: completeness and integration review

Date: 2026-09-25  
Scope: Review the supplied specification, prepare the implementation plan, and open a planning-only WIP PR in arbiterForge/codeArbiter.  
Result: The original scope is retained. Four concrete contract edge cases and several integration/qualification details are made explicit in this reviewed proposal. Native adoption, approval, implementation, and product qualification remain pending.

## 1. Inputs and evidence boundary

The original conversation package is `codearbiter-debug-specification-v1.zip`:

- Archive SHA-256: `78329cd6a9abf2810eb4853b8068f0385837db9ec9d1cb2611662a04c9cf15b3`.
- Original `SPEC.md` SHA-256: `f1c7da4e8376e00ab5e93a6d39d98c4caf6762e9362172782f3ff56212d4eab3`.
- Original handoff schema SHA-256: `0eb6b02035b77cb64b53e7e69777d88a0f558cc095ccd01282d4345f1754c173`.
- The supplied package contains a prose specification, 28 criterion records, 35 scenario records, a proposed JSON Schema, six valid and eight invalid examples, original source references, a prior review, a shell probe, and its original preparation report. Those are inputs, not product implementation or current installed-host evidence.

The original package was inspected locally. Its complete requirements, semantic rules, acceptance/scenario mappings, delivery and rollback boundaries were read. Its prior green preparation report was not reused as proof of this review's amendments.

Live source inspection:

| Surface | Inspected identity | What it establishes |
|---|---|---|
| Main branch | `4187f1e22dc7da3cf755a2654bbf7ec268236126`, tree `ffbbae240f113d0936c0f52a2151597d935ab14c` | Current development base, not released behavior. |
| Original review baseline | `d171126e71e48b78d242c3d95b218236fdd8f61d` | The reviewed debug implementation and related workflow contracts. |
| Main comparison | Original baseline to current main | Three commits ahead; only `.claude-plugin/marketplace.json` changed. The affected debug source was not silently assumed unchanged. |
| PR #854 | `35a3cd18a327fe5aa306ba452cc21ae096a24b02`, tree `5183bd46aaa719b1065f9d12fcdb77f9428d0101` | Open, draft candidate at inspection; 107 changed files. Not merged or released. |
| Planning branch | `docs/debug-correctness-plan`, created from the inspected main | Separate source-only proposal, not a stack importing #854's farm/runtime work. |

Exact source references for the owning procedures and governing contracts are listed in SPEC.md. In particular, the plan contract was inspected at `arbiterForge/codeArbiter@4187f1e22dc7da3cf755a2654bbf7ec268236126:core/surface/skills/writing-plans/SKILL.md`. It requires native authoring, exact binding, criterion coverage and actual approval; this proposal does not claim to have performed those operations.

## 2. PR #854: actual overlap, not a title-based assumption

The PR metadata, all changed filenames, relevant patches and current discussion were read through the connected GitHub tools. Relevant candidate files were read at the exact head. Broader historical farm comments are not relabeled as debug qualification.

The actual canonical command patch replaces the old independently authored debug wrapper with the single declaration `{{SKILL_ENTRY:debug}}`. Its owner skill gains the description, argument hint, plain-language entry boundary, existing no-action board-note disclosure, and the prohibition on re-entering from an active fix/ADR. The five investigation phases are otherwise unchanged in that patch.

The source-only README explains the compiler behavior: one command-backed owner supplies the full procedure; the generated Claude command is hidden from model invocation while the owner remains discoverable, and Codex/Pi public entries remain discoverable because private routines are outside their discovery roots. Resource links must render relative to the actual generated entry location. Source counts or fewer loads are not measured model effectiveness.

The same candidate retires `new-skill`, `skill-author`, and its bundled template without a callable replacement. Its farm, refactor, release-coordinate, cleanup-test and CI changes are separate work. This effort must not restore retired authoring surfaces or count those changes as debug implementation.

Bindings:

- `arbiterForge/codeArbiter@35a3cd18a327fe5aa306ba452cc21ae096a24b02:core/surface/commands/debug.md`
- `arbiterForge/codeArbiter@35a3cd18a327fe5aa306ba452cc21ae096a24b02:core/surface/skills/debug/SKILL.md`
- `arbiterForge/codeArbiter@35a3cd18a327fe5aa306ba452cc21ae096a24b02:core/surface/README.md`
- PR: https://github.com/arbiterForge/codeArbiter/pull/854

**Integration decision for the proposal:** preserve the consolidated owner and retirement; revise debug behavior in the owner. Replace the blanket active-fix re-entry ban with the bounded internal prerequisite return required by this specification, not recursive public routing. Keep this WIP on main. Before overlapping skill changes, revalidate and integrate the accepted prerequisite, or obtain explicit authority for a narrowly scoped extraction. Do not automatically merge/cherry-pick #854 or its synthetic merge ref.

## 3. Completeness findings and amendments

These are specification findings or clarifications, not claims of newly reproduced production vulnerabilities.

| ID | Finding and significance | Revision and verification |
|---|---|---|
| CR-01 | High integration risk: the old plan could edit a procedural debug wrapper that #854 eliminates, duplicate the owner, or retain its active-fix prohibition while promising a diagnostic prerequisite. | Preserve SKILL_ENTRY, single owner, host discovery differences and retirement; explicit P-854 gate. AC-17/24/25/26, V36, T01/T15/T20/T31. |
| CR-02 | Medium contract gap: a code-defect packet can be shape-valid while its fix next step has null action/completion evidence. Existing-owner output also needs an actual owner or explicit absence treatment. | SEM-17 and outcome matrix require actionable non-none targets and a real named existing owner. Missing owner uses an explicit evidence action. AC-10/13/16, V37. |
| CR-03 | Medium contract gap: `reuse_existing: true` can be shape-valid with a null test identity. That is not an executable reused-regression handoff. | SEM-16 requires named existing test and cited adequate target-red evidence; actual freshness/red remains a consumer obligation. AC-15/18, V38. |
| CR-04 | Medium contract ambiguity: a fingerprint without its recipe is accepted by the proposed shape, and the original regex allows an otherwise valid case ID ending in a newline. | SEM-18 pairs fingerprint/recipe and documents its limited meaning; SEM-19 requires full-string IDs. Preserve nullable unknowns and current-state revalidation. AC-07/15, V39. |
| CR-05 | Medium execution-contract detail: a nominally pure validator still needs bounded stdin, deterministic exit/output semantics, and protection from import-created bytecode/cache writes. | Specify a thin private entry, Python -B plus import suppression, byte/output/depth caps, result codes, no effects and no raw error echo. This is a proposed helper, not a new hook/tool or general executor. AC-14/15, V40. |
| CR-06 | Clarification, not a discovered defect: actual date-time checking must be enabled, and JSON Schema permits integral numeric values such as 0.0. A Python implementation could accidentally disagree or admit booleans. | Keep the invalid timestamp control and mathematically integral finite-number semantics. T03 fixes the exact supported date-time/Unicode profile before native readiness. No claim that 0.0 acceptance itself is wrong. AC-15, V39. |
| CR-07 | Qualification refinement: shape acceptance and a source-only fake consumer cannot establish causal truth, actual caller authority, host effects, or successful fix continuation. An unresolved escape could mask every difficult case. | Preserve all original proof layers and V01-V35; add explicit real-consumer/public-private-path assertions and candidate V05/V06/V22 repetitions. Solvable cases have fixed required outcomes; blocked cells stay pending. AC-16/17/24/27/28, V36/V41. |
| CR-08 | Delivery clarification: a plan that begins from an external Markdown package cannot honestly claim native approval, and a partial producer-only rollout would recreate a broken handoff. | Keep source-only proposal status; T01-T06 native adoption/approval gate; D2/D3 coherent integration, no new state migration; coupled rollback preserves independent #854 work. AC-23/25/26/27. |

No observed edge case is described as a running validator bug: the original packet was a proposed schema plus semantic obligations, not an implemented validator. Some schema-valid inputs were intentionally reserved for semantic rejection. The review closes ambiguities and demands actual rejection tests rather than claiming the schema can prove causation.

## 4. Checks actually executed

Local standard Python tooling loaded the original JSON Schema with `jsonschema.Draft202012Validator` and an enabled `FormatChecker`. These tests did not execute repository product code, native authoring, a host model, or the proposed production validator.

| Check | Observed result | Boundary |
|---|---|---|
| Original SHA256SUMS entries | All 24 file digests matched. | Integrity of supplied inputs only. |
| Original schema meta-validation | Passed. | Schema shape is valid; no proof of complete business semantics. |
| Original example shape classification | All 14 matched the manifest's declared shape expectations. | Six valid and four semantic-invalid examples pass shape; four schema-invalid examples reject. This is not fourteen product-semantic passes. |
| M01, reuse_existing true with null candidate_test_id | Accepted by original shape. | Motivates explicit SEM-16/negative fixture. |
| M02, code-defect fix target with null action/completion | Accepted by original shape. | Motivates explicit actionable transfer rule. |
| M03, supplied fingerprint with null recipe | Accepted by original shape. | Motivates paired identity/recipe rule. |
| M04, invalid observed_at date-time | Rejected when format checking is enabled. | Positive control retained; no claim of missing schema date-time validation. |
| M05, exit_code 0.0 | Accepted. | Consistent with JSON Schema integer semantics; not a defect. |
| M06, trailing newline in case_id | Accepted by original regex shape. | Full-string identifier boundary needs explicit validation. |

The synthetic probe mutations contain no real credentials or production data. The earlier Codex root probe remains historical shell-level evidence from the original audit; it is not a live Codex test in this review. Deleting the no-action writer instruction does not independently qualify the retained authorized follow-up invocation.

The review's local source acquisition through Git failed on DNS resolution; live connector reads and Git object writes were available. Accordingly no repository-wide or focused repository test suite is claimed run here. Required future commands and evidence are assigned in PLAN.md, not labeled passing.

## 5. Scope and plan checks

The reviewed proposal retains eight scope goals, fifteen requirement groups, all 28 original acceptance IDs, all 35 original scenario IDs, and all fifteen original semantic-rule IDs. Four semantic clarifications and six review scenarios are added. No criterion is silently removed or renumbered; new native IDs must be allocated by the engine and mapped to these external references at adoption.

The plan has forty proposed task/work-package IDs in D1-D4. Each names exact paths through a resolved ownership table, dependencies, verification/observable, criterion mapping and PENDING status. Larger installed-host/model packages must be expanded into cell/scenario child tasks in native planning; they are not single completed checks. The original fourteen-case paired set and three repetitions for both arms remain mandatory for each declared configuration. Candidate safety/disclosure/staleness repetitions supplement that set, not replace it.

**Negative-intent review:** If all static and schema checks pass, real host loading, tool effects, diagnostic causality, stale-packet detection, repair authority, and actual TDD continuation can still be wrong. Therefore the native plan must preserve real installed and model criteria. A no-write validator also cannot prove no side effects from an arbitrary diagnostic; actions retain their own safety/permission assessment.

**Overbuild review:** No persistent case family, standalone note writer, generic schema interpreter, global memory, mandatory agent fleet, new public skill, provider runner, or farm enablement is needed. Finite contract logic and source-only schema projection are the chosen boundary. Future persistence requires separate scope and ADR-0037 adoption, not a hidden D2 addition.

**Integration review:** The new task/helper guidance is limited to actual debug validation and authorized follow-ups. No unrelated task-board or cross-host sweep. Shared safety, accepted ADRs, unrelated feature/refactor authority, release and commit gates remain intact. Brownfield context production and #854 farm work are not imported into this effort.

## 6. Publication and acceptance state

This PR publishes five source-only proposal files: SPEC.md, CONTRACT.md, SCENARIOS.md, PLAN.md, and this review. It changes no installed resource, workflow, helper, generator, package manifest, version, authority record, or consumer state. No GitHub merge or release is authorized or performed by this planning request.

The proposal is complete enough to enter native planning preparation. It is deliberately not declared native-ready or approved: T03 must settle its finite date-time/profile method, T01 must revalidate the integration disposition, and T05/T06 must use the actual installed artifact/approval workflow. Intended host/model/platform/budget inputs remain qualification prerequisites instead of invented facts. The provided implementation design does not depend on a particular OS or provider.

## 7. Required disposition

| Record | Result |
|---|---|
| Confirmed findings | Original scope retained; schema edge cases and #854 owner overlap inspected; input integrity/example shape checks rerun. |
| Material contradictions | Old independent wrapper versus consolidated owner; active-fix prohibition versus finite diagnostic return; nominal handoff versus missing actionable/test identity; proposed shape versus unstated cross-field invariants. |
| Canon/claim-registry delta | No organization canon or cross-product registry changed. Project bootstrap snapshots remain historical. No new product or host guarantee. |
| Affected surfaces | This PR: source-only proposal directory. Future work: debug/fix/TDD, bounded private validation and invocation, generated hosts, tests and operative docs. |
| Decisions requiring approval | Native specification/plan adoption and actual approval; #854 prerequisite integration/extraction if still pending; specific external qualification access/spend. No repeated approval of already known user intent is requested here. |
| Verification still required | All proposed product scenarios, source suites, installed Claude/Codex journeys, applicable Pi parity, model trials, native readiness/approval and exact released-payload evidence. WIP CI is not those product results. |
| Recommended next action | Resume T01-T06 in a qualified installed authoring session, preserve #854 single-owner/retirement semantics, then implement D2/D3 and qualify D4 without broadening scope. |


## D1 continuation, 2026-09-25

See [D1.md](D1.md) for T01-T04 source completion and T05/T06 blockers. [D1-PROFILE.md](D1-PROFILE.md) freezes the previously deferred profile; [D1-CASES.json](D1-CASES.json) retains all SEM and scenario identities with explicit proof layers. Native capabilities succeeded on the inspected installed ca 2.21.12 binary, but its bridge lacks the workflow_preflight admission required by current source. No native artifact, approval or product result is inferred from that probe. Earlier review findings remain commit-bound history.

## D1 native adoption continuation, 2026-09-25

The earlier probe above remains historical. Pinned installed ca-codex 0.13.18 now supplies the required workflow preflight. One engine-authored [specification](../../../.codearbiter/specs/debug-correctness.html) and [plan](../../../.codearbiter/plans/debug-correctness.html) pass ready validation, preserve the 28 criteria, 41 scenarios and 40 parent task IDs, and retain draft_preview binding and draft governance. The plan adds 83 scenario/family qualification children; exact package/runtime/model/permission/budget cells remain pending. The original untracked native specification in the previous worktree was inspected through the engine and left untouched.

This authoring continuation is not an independent review receipt. T06 must resolve a real representation limitation: schema 0.3.1 native prerequisites apply plan-wide, whereas P-854 and P-QUAL are scoped in the source. The conservative draft leaves them unsatisfied and blocks every execution scope until reviewed resolution. Actual host-observed approval, oracle review, product scenarios and qualification remain unperformed. [D1.md](D1.md), D1-ENVIRONMENT.json and D1-CHECKS.json record the current evidence and limits.

The subsequent independent MEDIUM finding identified 150 unsupported verification declarations despite structural readiness. The author correction uses the installed collector contract: existing standard-unittest invocations are backed by actual emitted names; future declarations retain explicit planned identities and behavioral assertions; only actual non-test CLI checks use exit-only. T24 transparently adds the future standard-unittest exposure of all 11 existing board-sync checks without changing their assertions or CLI contract, and T33 depends on it. [D1-COLLECTORS.json](D1-COLLECTORS.json) records the reproduced rejection, all 150 corrected admissions, actual source observations and missing/duplicate negative controls. This correction is author evidence pending focused independent recheck, not a review verdict or approval.
