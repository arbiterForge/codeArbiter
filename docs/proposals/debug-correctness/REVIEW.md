# Debug correctness: completeness and integration review

Reading boundary added 2026-09-28: each entry records observations and status
at its stated date. Earlier draft, unapproved, pending and blocked labels remain
historical evidence. Current native authority and task state come from the
qualified installed workflow. The T-006 author assessment is appended below.

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

## T-001 source revalidation, 2026-09-26

This dated append records author-side source inspection for native task `T-001`
and its AC-025/AC-026 preparation obligations. It does not accept the task,
satisfy `T-GATE-OWNER`, or authorize extraction, overlapping implementation,
provider use, installation, merge, or release. The earlier review and D1 records
remain evidence of their stated dates.

The selected qualified installed ca-codex 0.13.11 `ArtifactClient` confirmed
specification revision 3 and plan revision 9 as approved, with verified authority
and `approved_source` binding. The specification normative identity remains
`f77cb9e52c3ee118fa69871a4dd6f15a124a47732e3e28b820870dcaabdd65cd`; the plan
normative identity is
`be0d60739863f88d808a6da359e9fbd96abda60f2d06031ed665a1bfa99b1a8b`, with model
identity `907cf19524cf03ab2d6f895bcc7945cdc7e80e2b16e98534db3a6f6190f69d2f`.
Ten fresh contextual pages delivered all 102 T-001 context records and ended
with `context_complete: true` and ticket
`85b71213249dee0739c911c9774ee10e851fab43e08302e642f2346c4e9f1387`.
These are observations of the existing workflow state, not author-created
approval, verification, or review receipts.

### Exact refs and source comparison

Live `git ls-remote origin refs/heads/main refs/pull/854/head` and
`gh pr view 854` agreed on the following identities. The observation was made on
2026-09-26; the inspection clock read 12:03:15 UTC. Git objects were already
available locally and were inspected without changing the checkout or index.

| Surface | Commit | Tree | Observed status |
|---|---|---|---|
| Task checkout | `0759ca2bf3d6740141fa3b0e0bf219232633fbb5` | `72ac2b8254841c569ad80d0b200d52c1be8d92f9` | Existing dirty native artifacts, artifact journal, and resume note preserved. |
| Live main | `a5a3d79cb5633cae3982552d6a7cf724de83aa49` | `f315d9cc196702899373b1f15d279af6c34e53aa` | Reference branch for this comparison. |
| PR #854 | `721e59929e93939108e758db6900fb8862499757` | `61ff4f764d81cb3d52282be76f05efea1f95c24e` | Open, **non-draft**, base main; `mergedAt` and `mergeCommit` null. |

`git ls-tree`, exact-ref `git show`, and bounded
`git diff --no-ext-diff --no-textconv` established these blob identities. Each
of the four paths is identical between the task checkout and live main.

| Canonical path | Main and task-checkout blob | PR #854 blob |
|---|---|---|
| `core/surface/commands/debug.md` | `6070b055e175a574d43de96203e484c997a49106` | `b206f9c45616068bf7ce74f4e3be762f702b739a` |
| `core/surface/includes/routing-table.md` | `758f17280708f7c4fc2eaec2a7ab63095416a5db` | `04a30ba5f3b5892de89b959796013953bdd7ef98` |
| `core/surface/skills/INDEX.md` | `5a0547c1e5251a8424f18b78bcfde54357c99c2a` | `05642727daa8f77c2bdfd103b87cd85ff814e2a3` |
| `core/surface/skills/debug/SKILL.md` | `0e0995202a00c7e11751b3e7c159de0205a90391` | `9ccacb1c8499690645661e1f8599091aacea80e4` |

All four PR blobs also match the frozen adoption candidate
`30279f9df7650af5b2680d493aba7d34caeea004`; their bounded diff is empty. The two
debug-owner blobs recorded in historical D1-OWNERSHIP.json also still match.
That byte identity does not update the historical PR status or confer acceptance.

The current candidate replaces the 41-line command wrapper with the sole line
`{{SKILL_ENTRY:debug}}`. `core/surface/skills/debug/SKILL.md` owns the description,
argument hint, plain-language entry boundary and full procedure. Its five
investigation phases remain unchanged by that patch. The routing table points
diagnosis intent and explicit debug invocation to this same owner; the index
names it as a command-backed owner. Other routing/index changes in #854 remain
outside this task.

### Discovery, retirement and integration boundary

Inspection of the exact candidate README and generated payload headers confirms
the distinction that future integration must retain:

| Candidate surface | Observed discovery contract |
|---|---|
| `plugins/ca/commands/debug.md` | Generated full procedure, `disable-model-invocation: true`; explicit command retained. |
| `plugins/ca/skills/debug/SKILL.md` | Discoverable owning skill; no model-invocation disable flag. |
| `plugins/ca-codex/skills/ca-debug/SKILL.md` | Discoverable `ca-debug` entry; owner copy is under private `routines/debug/`. |
| `plugins/ca-pi/skills/ca-debug/SKILL.md` | Discoverable `ca-debug` entry; owner copy is under private `routines/debug/`. |

The candidate's resource contract renders links from the actual generated output
location. This inspection did not run the generator, install a package, or prove
host loading, model effectiveness, token savings, or Pi artifact authority.

The candidate deletes `core/surface/commands/new-skill.md`,
`core/surface/skills/skill-author/SKILL.md`, and its
`references/skill-template.md`; the corresponding generated command/entry and
private routine paths are absent on all three hosts. The routing and skill
indexes remove that route. Preserve the retirement and do not add a replacement
public authoring surface.

The consolidation is **not integrated in the inspected main or task checkout**:
their debug command still contains the old wrapper, and the exact PR head is
not an ancestor of live main (`git merge-base --is-ancestor` returned 1).
PR #854 being open and its relevant bytes remaining stable does not resolve
`T-GATE-OWNER`. That gate still requires actual accepted integration or a genuine
narrow ref/path coordination or extraction decision before overlapping edits.
No such decision is created here, and no source owner or unrelated farm change
was imported.

The candidate still retains the active-fix/ADR re-entry ban and the no-action
board write. They are inspected baseline behavior, not debug-correctness
implementation. The already-approved later tasks must implement the finite
internal diagnostic return and truthful no-action behavior after their gates;
this source-only task changes neither rule.

### Verification and retained history

From `docs/proposals/debug-correctness`, the exact declared command
`python -m unittest -v check-d1` exited 0. All seven named outcomes passed, with
no skipped tests: `test_adjacent_links`, `test_native_adoption_not_fabricated`,
`test_original_examples_retained`, `test_plan_coverage_and_graph`,
`test_profile_vectors`, `test_scenario_inventory_and_oracles`, and
`test_semantic_matrix`. These check source preparation and retained historical
records; they do not prove production behavior, installed-host acceptance,
independent review, owner integration, or native task acceptance. In particular,
`test_native_adoption_not_fabricated` checks the historical draft-adoption record,
not the currently approved pair.

No product implementation or new test was authored, so no RED result was
manufactured. This prose append touches no Python hook or TypeScript tree to
which the declared lint/typecheck or coverage commands apply. The later
implementation tasks retain their full TDD obligations. Fresh native verification
and independent spec review remain the orchestrator's next steps.

D1-OWNERSHIP.json, D1-CHECKS.json, D1-ENVIRONMENT.json, D1-COLLECTORS.json,
D1-CASES.json, PLAN.md and D1.md remain unchanged. Their earlier refs, draft-pair
statements, source completion labels and prerequisite observations are dated
evidence, not rewritten into current task completion or product proof.

## T-001 current merged-owner evidence, 2026-09-27

This bounded AC-025/AC-026 source correction continues the original T-001
dispatch. All ten delivered revision-11 context pages were read: 102 records,
complete ticket
`6ba2dadfd7e46c75cdb263fd7343b3758eaa205e2e440d2ed31f52be38b53a54`.
The supplied context records the approved specification binding and amended-plan
receipt `c808e0640a5ccfd814ac3dcc8365753522eef18970a6a92320afa2983e957e9d`;
this pass performs no native authority validation or transition. Earlier review,
resume and D1 records retain their dated observations.

At 2026-09-27T19:06:09Z, `gh pr view 854 --repo arbiterForge/codeArbiter`
and `git ls-remote origin refs/heads/main refs/pull/854/head` confirmed
[PR #854](https://github.com/arbiterForge/codeArbiter/pull/854) is **MERGED**,
non-draft, into `main`, at 2026-09-26T23:02:31Z.

| Inspected surface | Commit | Tree |
|---|---|---|
| Task checkout | `0759ca2bf3d6740141fa3b0e0bf219232633fbb5` | `72ac2b8254841c569ad80d0b200d52c1be8d92f9` |
| PR #854 final head | `00f2598e60446f015506530a3396c87728d2eada` | `8ec980e1868f86f18479c1ddb2a13233d1820fec` |
| PR #854 merge | `6320eb51ec4cccee27ac1da1be326824d7e51a57` | `8ec980e1868f86f18479c1ddb2a13233d1820fec` |
| Live main | `8e88bce938ebf7dc8cfd934307b8d6859092d86e` | `2616f9c25371686f021b4fb6e4e32636396b5ff5` |

Exact-ref `git ls-tree`, `git show` and bounded
`git diff --no-ext-diff --no-textconv` confirm these four blobs are identical
in the final PR head, live main and frozen candidate
`30279f9df7650af5b2680d493aba7d34caeea004` (both scoped comparisons exit 0).

| Canonical path | Accepted blob |
|---|---|
| `core/surface/commands/debug.md` | `b206f9c45616068bf7ce74f4e3be762f702b739a` |
| `core/surface/skills/debug/SKILL.md` | `9ccacb1c8499690645661e1f8599091aacea80e4` |
| `core/surface/includes/routing-table.md` | `04a30ba5f3b5892de89b959796013953bdd7ef98` |
| `core/surface/skills/INDEX.md` | `05642727daa8f77c2bdfd103b87cd85ff814e2a3` |

The sole canonical debug procedure remains
`core/surface/skills/debug/SKILL.md`; the command is only
`{{SKILL_ENTRY:debug}}`. Routing and the index select that owner for diagnosis
intent and explicit debug invocation. The accepted entry-boundary patch leaves
the five investigation phases unchanged. Its active-fix/ADR re-entry ban and
no-action board write remain baseline behavior for later approved tasks.

Current generated headers and `core/surface/README.md` retain Claude's
discoverable `skills/debug/SKILL.md` owner and explicit-only
`commands/debug.md` (`disable-model-invocation: true`). Codex and Pi retain
discoverable `skills/ca-debug/SKILL.md` entries, with owner copies in private
`routines/debug/SKILL.md`. All six generated debug files match the final PR
head. The source contract still requires resource links relative to the actual
generated output location; no generator run or installed-host claim is made here.

The canonical `commands/new-skill.md`, `skills/skill-author/SKILL.md` and
bundled `references/skill-template.md`, plus their nine generated host files,
are absent in both the final PR head and live main. The canonical command
directory, routing table and skill index contain no `new-skill` or
`skill-author` reference (`git grep` exits 1: no matches). Preserve that
retirement without a replacement public authoring surface.

**Main contains the accepted consolidation; this task checkout does not.**
`git merge-base --is-ancestor` returns 0 for both the PR head and merge commit
against live main, but 1 for the merge commit or live main against task HEAD.
`git rev-list --left-right --count HEAD...8e88bce938ebf7dc8cfd934307b8d6859092d86e`
reports `4 105`. The checkout's four old canonical blobs remain as recorded on
2026-09-26, and all twelve retired source/generated files are still present.
Integration or an actual narrow ref/path coordination decision remains necessary
before overlapping edits under `T-GATE-OWNER`; this inspection neither accepts
that gate nor changes T-001 state. No merge, rebase, extraction, product edit,
native-artifact edit or historical-input replacement was performed.


The declared command `python -m unittest -v check-d1`, run from
`docs/proposals/debug-correctness`, exited 0 with seven passing named outcomes
and no skips: `test_adjacent_links`, `test_native_adoption_not_fabricated`,
`test_original_examples_retained`, `test_plan_coverage_and_graph`,
`test_profile_vectors`, `test_scenario_inventory_and_oracles`, and
`test_semantic_matrix`. These are source-preparation checks, including preservation
of historical draft/adoption and unmerged-PR records; they are not current native
verification, independent review, full AC-025/AC-026 product proof, or task
acceptance. This factual documentation append requires no invented RED test.
Native verification and review remain with the original dispatch.


## T-006 authority-boundary correction, 2026-09-28

This author assessment retains the native review's changes_requested verdict
from reviewer `01a0e884-7f90-7a21-a697-166f1f774d6d`, request
`bd1653fde721ae27ed38d7967093dceea179c1f7dfd813d18ad20f406f42d08b`, first stop
at 15:02:29 UTC. All six supplied revision-23 contextual pages, containing 115
records, were read. This entry supplies a correction for fresh review; it is not
a review receipt or task acceptance.

**AUTHORITY_SCOPE_CONTRADICTION (HIGH): disputed as an authority defect.**
T-006 retains create/modify ownership for the original native adoption paths,
but its explicit resume rule forbids recreating or overwriting the approved
spec/plan and requires verification of historical preparation plus remaining
review. PLAN-GATES-001 separately requires current verified approvals,
approved-source binding, complete context and native eligibility. T-006's
done_when also requires those guards and the actual review obligations. The
path inventory does not override these narrower conditions. PLAN.md now states
that boundary explicitly. No native path action, method, acceptance criterion
or authority requirement is changed by this clarification.

**STALE_AUTHORITY_STATUS (MEDIUM): confirmed wording ambiguity.**
The supplied typed context contains verified approval records alongside
preparation-time prose in the specification summary, SEC-001, PROFILE-004 and
plan PLAN-BOUNDARY-001. D1.md and PLAN.md also retained draft/unapproved wording
without a sufficiently clear reading boundary. Their new dated notes make the
historical scope explicit. Drafting-time statements about adoption or all tasks
being pending are not reliable current-state queries; use native identity,
approved-gate validation and eligible results. Product evidence and independent
review obligations still require their own actual results.

This correction leaves the frozen canonical statements unchanged. It does not
amend the approved definitions, replace engine status with prose, or turn the
historical D1 records into current proof. If native review requires wording
changes inside the approved artifacts, those changes must return to their
supported revision and approval owner. Source checks cannot resolve that gate.
The original review remains changes_requested; fresh governed verification and
independent review must evaluate this correction before any native acceptance.

## T-004 source-design correction proposed, 2026-09-28

The 16:46:32.779Z first-stop review of source identity
`2901285ca87548dd3d6660fae345f7f90a8eed3ffed89b593556b7b25b0933eb`
remains `changes_requested`. This append is an author disposition, not a replacement
review receipt, native task transition, or proof of product behavior.

**SEM_COVERAGE_UNBOUND (MEDIUM): confirmed.** The former SEM-01..19 rows were
prose and `check-d1.py` checked only nonempty strings. The proposed
`D1-CASES.json` adds five complete synthetic base packets and nineteen named
negative/positive control pairs. Each pair fixes an exact field mutation, V-scenario,
proof layer and expected result; the existing `test_semantic_matrix` materializes
and checks their structure without adding a collector name. The source checker
does not execute or prove the future validator, host effects, or model judgment.
Some compound SEM ledgers require more than one production test in D2; this D1
control set fixes at least one concrete negative per SEM without reducing those
later obligations.
The five positive synthetic bases now disclose absent fingerprints, and evidence
with missing source or capture-time identity carries a limitation. SEM-11 clears
that limitation in its negative packet and retains unknown runtime identity with
an explicit limitation in its positive packet. SEM-08/09's malformed packets are bound
to V13's D-layer unresolved/no-action variants and expect rejection; their V11/V15
model-outcome obligations remain separate and pending.

**SOLVABILITY_ORACLE_UNFROZEN (MEDIUM): confirmed at the source-design boundary.**
The proposed `pretrial_classification` fixes all fourteen V35 paired IDs,
including every V25 and V31 variant, as solvable or blocked with an expected
disposition and ground-truth basis. The existing scenario test forbids a
solvable-to-unresolved collapse. This design freeze is not the independently
reviewed executable hidden oracle or readiness evidence. T-036 owns that later
binding and its qualification validator; live model trials remain pending.
`independent_oracle_review` and every product scenario remain `PENDING`.

The seven declared `python -m unittest -v check-d1` test names are preserved.
The original fourteen example IDs, scenario IDs, variant inventories, three
repetitions per arm/configuration, and dated historical records are retained.
Fresh governed verification and review must assess this proposed source correction
before any native acceptance.

## T-GATE-OWNER source observation, 2026-09-29

This dated entry updates the earlier T-001 checkout observation without changing
its historical record. The 2026-09-29 live read of
`gh api repos/arbiterForge/codeArbiter/pulls/854` returned `state: closed`,
`merged: true`, `merged_at: 2026-09-26T23:02:31Z`, final head
`00f2598e60446f015506530a3396c87728d2eada`, and merge commit
`6320eb51ec4cccee27ac1da1be326824d7e51a57`. The merge commit's
parents are `1501cc4e` and that final PR head. This is the accepted integration
on main; the earlier open-PR observations are not a current-state claim.

The actual PR #871 completion checkout and the separate source staging clone
both have `HEAD` `0759ca2bf3d6740141fa3b0e0bf219232633fbb5` and a pending
`MERGE_HEAD` `158daa0016eb7f7127221fac6deefb59991804ad` from an actual
`git merge --no-commit --no-ff`. In the source staging clone,
`git merge-base --is-ancestor 6320eb51ec4cccee27ac1da1be326824d7e51a57
158daa0016eb7f7127221fac6deefb59991804ad` exits 0. A scoped working-tree
comparison of the four canonical debug/discovery paths and six generated debug
paths against the #854 merge commit exits 0. The pending merge has not been
committed or turned into a native task-acceptance receipt.

The integrated canonical `core/surface/commands/debug.md` is exactly
`{{SKILL_ENTRY:debug}}`; `core/surface/skills/debug/SKILL.md` remains the sole
procedure owner. Routing and the skill index select that owner. The generated
Claude command contains the full procedure but is explicit-only; its skill
remains discoverable. Codex and Pi retain discoverable `ca-debug` entries with
private owner copies. The generated entries retain the no-action board helper.
The builder's output-relative resource contract remains under its existing
`test_codex_links_are_rendered_from_entry_location` check. The canonical
`new-skill` command and `skill-author` owner/template remain deleted, with no
generated host entry or catalog route restored.

The finite `test_debug_workflow.py` source candidate checks the current
canonical declaration, canonical and generated discovery indexes, real
generator outputs against checked-in Claude, Codex and Pi entries/resources,
advanced/change catalog metadata, and retirement. Its
negative control renders an independent debug wrapper against the unchanged
owner and rejects that incomplete public entry. A third test resolves a
synthetic owner resource from the generated Codex entry location. A fourth
test removes the canonical discovery row and changes rendered debug visibility
to show both regressions are detected. All four candidate tests passed
against the source staging clone on this date. They
corroborate the source boundary only: they do not transform historical
`D1-OWNERSHIP.json` bytes,
an open PR, a matching blob, or this review into integration authority. That
historical file remains byte-exact at SHA-256
`80b9c318b8da57dc843139d89c226fffa89abaa97a90ff2f8565089bed1e39ef`.
Native verification, independent spec and quality review, the T-014/T-020
consumer work, and task acceptance remain separate pending steps.

## T-002 review-addition coverage, 2026-10-02

T-002's completeness review includes the original V01-V35 scenarios and all
six review additions below. These mappings are already required by the approved
specification; this entry makes their place in T-002's completion evidence
explicit. The original fourteen example IDs remain required and unchanged.

| Review addition | Source criterion IDs | Native criterion IDs |
|---|---|---|
| V36 | AC-17, AC-24, AC-25 | AC-017, AC-024, AC-025 |
| V37 | AC-10, AC-13, AC-16 | AC-010, AC-013, AC-016 |
| V38 | AC-15, AC-18 | AC-015, AC-018 |
| V39 | AC-07, AC-15 | AC-007, AC-015 |
| V40 | AC-14 | AC-014 |
| V41 | AC-27, AC-28 | AC-027, AC-028 |

`check-d1.py` now checks each exact criterion mapping in `D1-CASES.json`,
including rejection of missing, unrelated, or duplicate links. The regression
first exposed 25 accepted invalid mappings with the previous checker; the
corrected checker rejects all 25 and retains the seven existing checks. Valid
criterion reordering remains accepted.

This is source-only completeness evidence. It does not execute the scenarios
or establish product behavior in the D, H, M, or S proof layers. All scenario
product statuses remain PENDING. Native verification, independent review,
task acceptance, and downstream product qualification require their own current
evidence; this entry grants none of them. Earlier dated observations remain
historical records.
