# Debug correctness: implementation plan input

Status: Proposed, source-only plan. All tasks PENDING. No native approval, implementation, product verification, or release qualification is asserted.  
Specification: [SPEC.md](SPEC.md), CA-DEBUG-CORRECTNESS-01 review revision 2  
Contract: [CONTRACT.md](CONTRACT.md)  
Scenario oracles: [SCENARIOS.md](SCENARIOS.md)  
Completeness review: [REVIEW.md](REVIEW.md)

## 1. Execution boundary

This plan is the requested WIP preparation, not a shadow authoritative `.codearbiter` plan. D1 prepares the exact adoption input. A qualified installed authoring session must create the native specification and bound plan, validate readiness, and obtain the actual required approval before D2/D3 implementation. Preserve source external IDs as correspondence to engine-issued criterion and task IDs; do not fabricate those native IDs or receipts. Ordinary sequential planning requires approved-source binding; an initial sprint uses only its explicitly supported draft-pair preparation and combined approval. No farm is requested.

Native task status is owned by that workflow. The PENDING labels here are descriptive, not an executable resume store or evidence that a native task exists. After adoption, link the native pair and label these proposal inputs historical rather than maintaining a second active plan.

The PR is based on `arbiterForge/codeArbiter@4187f1e22dc7da3cf755a2654bbf7ec268236126`. PR #854 was open/draft at `35a3cd18a327fe5aa306ba452cc21ae096a24b02`. Its procedural-owner consolidation is an integration prerequisite for overlapping workflow changes, not evidence that all its changes are merged or permission to merge them. Re-read both refs before execution and after any dependency update.

## 2. Delivery slices and prerequisite gates

| Slice | Outcome | Dependencies and exit |
|---|---|---|
| D1, T01-T06 | Freeze ownership, reviewed contract, oracles, and native adoption. | Can prepare now. No dependency on brownfield. Exit requires exact native spec/plan readiness and actual approval; unresolved method details are settled before that gate. |
| D2, T07-T24 | Coupled validator, evidence/outcome producer, real fix consumer, and bug-origin TDD. | D1 approval; T01 integration decision must be satisfied before T15-T23 edit shared workflow owners. Unit/fixture work may proceed without importing #854's unrelated work. |
| D3, T25-T30 | Installed-root, interpreter, literal-argument, and actual helper-effect portability. | D1 approval. Can proceed alongside D2 with explicit file ownership. Integrates the actual validator after its entry is available. |
| D4, T31-T40 | Generated closure, documentation, exact-package and model qualification, release handoff. | D2 and D3 integrated. No host/model readiness claim before its exact required cells pass. |

**Minimal coherent implementation slice:** T07-T33 after D1. It includes producer, validator, consumer, affected helper path, generated surfaces, and operative documentation together. It is not a released or exercise-qualified slice until the applicable T34-T40 evidence and ordinary gates pass. Do not ship a newly required producer without its consumer/helper or call a prose-only rewrite complete.

**P-854:** Before overlapping canonical owner edits, either #854's accepted consolidation is integrated into the chosen base, or the maintainer explicitly authorizes a narrowly identified prerequisite extraction. Do not merge/cherry-pick the whole farm branch, assume its synthetic merge ref is a merge, or restore its retired authoring operation. A rejected/changed #854 requires an explicit revised integration decision and contract review, not unilateral resurrection of wrappers.

**P-AUTH:** Installed native artifact capability, ready/current pair, actual approval, and relevant workflow permissions. Missing capability is reported; no manually authored HTML, source-built authority substitute, or fake receipt.

**P-QUAL:** Exact intended host/package/runtime cells, permitted tools/network/targets, and any evaluation provider/model/spend authorization must be known before live qualification. Missing inputs block that cell and its readiness claim, not unrelated deterministic work. No OS or provider is guessed from the maintainer's profile.

## 3. File ownership and notation

Paths below are repository-relative and exact. New paths are proposed implementation locations, not claims that they already exist. Parent approval may select an equivalent existing owner only after recording the correspondence and updating verification, never by creating parallel contracts.

| Key | Exact path(s) | Ownership |
|---|---|---|
| P | `docs/proposals/debug-correctness/SPEC.md`, `CONTRACT.md`, `SCENARIOS.md`, `PLAN.md`, `REVIEW.md` within this same directory | Source-only proposal; no installed discovery. |
| L | `core/pysrc/_debughandofflib.py` | New finite definitions, strict decoder, shape/semantic validation; sole runtime model owner. |
| E | `core/pysrc/debug-handoff.py` | New thin private stdin/stdout entry; not a registered hook. |
| R | `core/surface/skills/debug/references/handoff.md`, `core/surface/skills/debug/references/debug-handoff.schema.json` | On-demand projections from L plus bounded human interpretation; no skill frontmatter or public index registration. |
| G | `tools/build-debug-handoff.py` | Proposed source-only deterministic projection/check tool, only if existing generation has no suitable owner. No runtime registration. |
| W | `core/surface/skills/debug/SKILL.md` | Sole debug procedure after P-854. |
| B | `core/surface/commands/debug.md` | Whole-file `{{SKILL_ENTRY:debug}}`, retained declarative entry, not a second procedure. |
| F | `core/surface/commands/fix.md` | Existing fix caller and genuine handoff consumer. |
| T | `core/surface/skills/tdd/SKILL.md`, `core/surface/includes/author-tdd-workflow.md` | Bug-origin obligation and author execution integration. |
| A | `core/surface/agents/backend-author.md`, `core/surface/agents/frontend-author.md`, `core/surface/agents/infra-author.md` | Inspect affected caller obligations; edit only a demonstrated contradiction with scoped bug behavior. |
| I | `core/surface/includes/routing-table.md`, `core/surface/skills/INDEX.md` | Existing routing/discovery descriptions; not new public registrations. |
| H | `core/surface/includes/helper-invocation.md`, `core/surface/commands/task.md`, `core/surface/includes/codex-host-notes.md`, `core/surface/includes/pi-host-notes.md` | Shared affected helper convention; add the private include only when no existing owner can carry it without duplication. Retain native host differences. |
| D | `.github/scripts/test_debug_handoff.py` | Proposed unittest decoder/shape/semantic/conformance tests. |
| J | `.github/scripts/test_debug_workflow.py` | Proposed structural/actual workflow-consumption fixture tests; cannot stand in for model execution. |
| K | `.github/scripts/test_debug_helper_invocation.py` | Proposed real subprocess/helper argv/effect tests with owned scratch. |
| Q | `.github/scripts/test_debug_package.py` | Proposed exact candidate resource/installed-layout tests. |
| X | `.github/scripts/test_debug_qualification.py` | Proposed qualification-record/oracle boundary checks, not a provider executor. |
| Z | `.github/fixtures/debug/cases.json`, `.github/fixtures/debug/handoff-examples.json`, `.github/fixtures/debug/qualification-cells.json` | Proposed finite fixtures, hidden-oracle metadata, and explicit pending cells. No real secrets or claims of completed runs. |
| CI | `.github/scripts/test_ci_impact.py`, `.github/workflows/ci.yml` | Integrate only required focused checks through existing planner/jobs; preserve unrelated #854 CI and conformance work. |
| DOC | `site/src/curated/commands/debug.md`, `site/src/curated/skills/debug.md`, `site/src/curated/commands/fix.md`, `docs/architecture.md`, `docs/parity.md` | Operative source docs; check the live inventory before selecting a narrower exact edit. No historical record rewrite. |

Generated host copies are not independently authored. The host descriptor owns their paths. Current debug output families are Claude `plugins/ca/commands/debug.md` and `plugins/ca/skills/debug/`, Codex `plugins/ca-codex/skills/ca-debug/` and `plugins/ca-codex/routines/debug/`, and Pi equivalents under `plugins/ca-pi/`. Shared Python is vendored into each host's existing `hooks/` directory by the normal source sync. Preserve current file modes and resource allowlists; verify rather than assume how non-Markdown reference files are copied.

## 4. Verification notation

Each task's `AC` cell is also its external `maps-to` reference: the TDD obligation(s) derived from those exact source criteria after native adoption. It is not a new obligation ID scheme. A test/observable advances a criterion but never replaces TDD's red, review, coverage, commit, or merge requirements.

Existing source commands confirmed in the repository's conventions or command catalog:

- C1: `python tools/build-surface.py --check`
- C2: `python .github/scripts/test_build_surface.py`
- C3: `python .github/scripts/test_host_descriptors.py`
- C4: `python .github/scripts/test_command_route_compatibility.py`
- C5: `python .github/scripts/check_routing_index_parity.py`
- C6: `python .github/scripts/test_board_sync.py`
- C7: `python .github/scripts/test_codex_skill_resources.py`
- C8: `python .github/scripts/test_ci_impact.py`
- C9: `python .github/scripts/test_artifact_surface.py`
- C10: `python -m py_compile <exact changed Python paths>`; contributor syntax verification, not the validator's no-write journey.

D/J/K/Q/X denote the proposed test scripts in the path table. T07/T25/T34/T36 introduce their real test entrypoints and document exact supported selectors. Until introduced, the command is a planned test, not an existing or executed check. The ordinary invocation is `python <exact script path>` using standard unittest; focused execution may use its verified supported selector. A typo/zero-selected suite must fail. Source projections use G with a tested `--check` mode only once implemented. Use the current actual core-sync and packaging commands after reading their help; this plan does not invent unsupported flags.

For each behavior change, first demonstrate the failed obligation at the appropriate actual layer, then implement and record green. A missing import, nonexistent test name, or intentionally disconnected toy model is not red for the claimed defect. Source tests prove operative content/ownership, helper tests prove their actual mechanics, and H/M observations prove host/model behavior. Never commit a red required contributor check merely because the branch is WIP. Tests and their minimal implementation may be committed together after the observed red-to-green cycle.

## 5. Ordered tasks

### D1: freeze contract and tests

| ID | Work and exact path key | Verification / completion evidence | AC / maps-to | Depends on | Status |
|---|---|---|---|---|---|
| T01 | Re-read main/#854, compare W/B/I and source authoring README; record narrow P-854 integration disposition in P/REVIEW.md. | Exact refs/patches, owner declaration, discovery differences, retirement preservation, and explicit implementation prerequisite; no unrelated branch imported. V36. | AC-25,AC-26 | None | PENDING |
| T02 | Cross-check P/SPEC.md scope and all AC against original review and SCENARIOS.md; record missing/contradictory behavior before planning. | All G1-G8 and R01-R15 map to AC; answer what could remain broken even if static tests pass; no dropped original V01-V35. | AC-01,AC-10,AC-16,AC-27 | T01 | PENDING |
| T03 | Finalize finite timestamp/numeric/Unicode/fingerprint and private validation error profile in P/CONTRACT.md. | Explicit supported date-time format cases and parser/schema equivalence; M04/M05 controls retained; trailing controls, orphan fingerprint and invalid Unicode reject. Resolve method details before ready review, not during silent execution. V39,V40. | AC-07,AC-14,AC-15 | T02 | PENDING |
| T04 | Freeze field/outcome/SEM coverage and hidden-ground-truth expectations in P/SCENARIOS.md; retain v1 example identities. | Every SEM-01 through SEM-19 has a named negative case; solved versus blocked oracles fixed before model trials; all AC have required proof layers. | AC-10,AC-15,AC-27,AC-28 | T03 | PENDING |
| T05 | Adopt P through the qualified installed native authoring workflow; create actual same-slug HTML spec and plan only at engine-selected `.codearbiter` paths. | Engine-issued identities, complete contextual reads, ready validation, spec/task external-ID correspondence, no fabricated receipt or Markdown shadow. Actual paths/IDs recorded in a bounded pointer in P/REVIEW.md. | AC-26,AC-27 | T04 | PENDING |
| T06 | Perform native completeness/adversarial review and actual required spec/plan approval; finalize exact task ordering/ownership. | Real host-observed approval and current binding at approved gate; all 28 criteria covered, every task in scope, no cycle; P-AUTH satisfied. No implementation on generic approval text. | AC-26,AC-27 | T05 | PENDING |

### D2: implement the coupled workflow

| ID | Work and exact path key | Verification / completion evidence | AC / maps-to | Depends on | Status |
|---|---|---|---|---|---|
| T07 | Introduce D and Z/handoff-examples.json fixture harness with original valid/schema-invalid/semantic-invalid cases and named test discovery. | Harness selects intended cases, controls distinguish shape from semantics, zero-match selection fails; fixture-only success is not product success. V19,V20. | AC-14,AC-15 | T06 | PENDING |
| T08 | Add finite model definitions and primitive validation in L, tested by D; no side effects at import. | Full-match IDs, bounded nonblank text, nullability, enums, arrays, scalar/date/Unicode/integer profile; invalid booleans and trailing controls reject. V20,V39. | AC-14,AC-15 | T07 | PENDING |
| T09 | Add bounded byte decoder in L and D. | Exact/over 65,536 UTF-8 bytes, depth 16/17, duplicate keys, escaped surrogates, malformed and non-finite JSON; bounded failure without payload echo. V20,V39. | AC-14,AC-15 | T08 | PENDING |
| T10 | Implement unique-ID/reference/check-state SEM rules in L and D. | Duplicate/dangling IDs, planned-check-as-reproduction, conflicting evidence and fabricated completed result reject; valid executed non-process observation remains supported. V19,V20. | AC-07,AC-15 | T09 | PENDING |
| T11 | Implement outcome/regression/next-step SEM rules in L and D. | All five positive controls, null repair action/completion, missing existing owner, missing named reuse test, wrong regression disposition, and orphan fingerprint controls. V13,V37,V38,V39. | AC-10,AC-13,AC-15,AC-18 | T10 | PENDING |
| T12 | Add E thin bounded stdin/result entry and bytecode suppression. | Actual process emits valid exit 0, invalid 2, internal 3; at most 16 diagnostics/8,192 bytes; no traceback/raw payload, project/cache writes, sockets, or child process. V40 through real entry. | AC-14,AC-15 | T11 | PENDING |
| T13 | Generate R schema/reference from L using G or the justified existing generator; add checked projection mode. | Repeated projection is deterministic; stale hand-edited projection fails check; no separate runtime schema loader. D differentially checks shape/profile and separately reports SEM checks. | AC-14,AC-15,AC-25 | T12 | PENDING |
| T14 | Define actual W/F packet transport and diagnostic-return fixtures in J and Z/cases.json. | Exercise actual public/private payload and entry invocation, preserving packet fields and original caller; no disconnected alternate consumer or returned-JSON-equals-success shortcut. V21,V22,V23,V36. | AC-16,AC-17,AC-24 | T13 | PENDING |
| T15 | Revise W description/entry boundaries/capture with optional current map; preserve B declaration. | J and source checks reject old repro-before-investigation, padded aliases, automatic scaffolding, and duplicated wrapper; V01-V03 real-model oracles retained for qualification. | AC-01,AC-02,AC-03,AC-25 | T14,P-854 | PENDING |
| T16 | Revise W hypothesis and evidence phases with bounded search/discriminator/capture limitations. | J rejects fixed-count closure, absent-log refutation, recency-as-proof, and repeated unchanged checks; V07-V10/V39 fixtures map to later H/M proof. | AC-06,AC-07 | T15 | PENDING |
| T17 | Add W diagnostic action and disclosure rules with on-demand R context as needed. | V04-V06/V12 tests and inspectable actions preserve permissions/effects and reject unsafe replay, instrumentation-as-confirmation and log instructions; no new executor or rule bypass. | AC-04,AC-05,AC-09 | T16 | PENDING |
| T18 | Replace W three-exit decision with all five outcomes and valid early unresolved return. | J positive/negative outcomes V11-V18/V37; supported multi-cause and continuation blockers preserved; no forced ADR or no-action from failed replay. | AC-08,AC-10,AC-11,AC-12,AC-13 | T17 | PENDING |
| T19 | Implement W validated summary/packet transfer, capacity behavior, legacy normalization and honest resume. | J uses actual validator; V19-V22/V30 show field-preserving output, stale/lost context handling, explicit oversize behavior, no case store or compulsory full JSON. | AC-14,AC-16,AC-23,AC-28 | T18,T13 | PENDING |
| T20 | Update F to consume packet with real caller authority/freshness checks and finite internal debug prerequisite return. | V21-V23/V31/V36 prove same invocation, no public recursion, no repeated answered questions, no diagnosis-only repair or packet-label authority. | AC-16,AC-17,AC-24 | T19 | PENDING |
| T21 | Add explicit bug-origin obligation source in T; audit A and edit only demonstrated conflicting author requirements. | V23/V33 retain feature/refactor gates and no fabricated feature artifacts for bugs; actual author receives regression/expectation/current scope. | AC-17,AC-26 | T20 | PENDING |
| T22 | Revise T target-red baseline classification and existing-test reuse. | V24/V25/V38: named adequate existing red reused; unrelated/import/setup failures remain visible and never count as target red or waive required commit gates. | AC-18,AC-19 | T21 | PENDING |
| T23 | Close regression/repair verification in T and actual author workflow. | V26/V27 show failure for right reason before minimum repair, unchanged assertions, renewed red after material setup changes, fresh bounded proof and stochastic limits. | AC-20,AC-26 | T22 | PENDING |
| T24 | Reconcile terminal task/ADR behavior and I routing/discovery summaries with W/F. | V15/V17/V31/V33: no default queued close, explicitly authorized real follow-ups only, immutable history retained, no widened owner/authority. C5,C6 plus J. | AC-11,AC-12,AC-24,AC-25,AC-26 | T23,T30 | PENDING |

### D3: portable invocation, parallel with bounded D2 ownership

| ID | Work and exact path key | Verification / completion evidence | AC / maps-to | Depends on | Status |
|---|---|---|---|---|---|
| T25 | Introduce K controlled subprocess/layout harness and interpreter/argv fixtures in Z. | Harness isolates package/cwd/worktree, counts actual helper attempts and captures argv literally; tests cannot repair the command being tested or read source as rescue. V28,V29. | AC-21,AC-22 | T06 | PENDING |
| T26 | Establish H resource-derived installed-root guidance for affected validator/task callers. | K exercises unset tokens, arbitrary/nested cwd, spaces/non-ASCII installed path and missing helper. No /hooks or recursive source/cache discovery. V28. | AC-21 | T25 | PENDING |
| T27 | Fix H affected interpreter-selection guidance without helper retry. | K real, absent, alternate, stub and incompatible interpreters; refusal preserves original status and invokes mutating helper exactly once. V29. | AC-22 | T26 | PENDING |
| T28 | Fix H affected literal user-text/options/stdin delivery for supported host shells. | K captures exact quotes/metacharacters/leading hyphens/non-ASCII and options-before-separator; invalid input cannot become executable syntax. V29. | AC-05,AC-22 | T27 | PENDING |
| T29 | Test E plus affected H invocation in actual read-only installed layout. | K/V40 observes no pycache/temp/project writes, network or processes; stdin/output bounds and error codes preserved. No source helper fallback or second interpreter invocation. | AC-14,AC-21,AC-22 | T28,T12 | PENDING |
| T30 | Exercise actual existing task writer through affected H authorized follow-up recipe. | K/V28/V29/V31: correct worktree board, actual lock/refusal/atomic behavior, literal text, one attempt; removing default no-action write does not hide this retained route. | AC-21,AC-22,AC-24,AC-26 | T29 | PENDING |

### D4: propagation and qualification

| ID | Work and exact path key | Verification / completion evidence | AC / maps-to | Depends on | Status |
|---|---|---|---|---|---|
| T31 | Regenerate affected core Python and all host Markdown/reference/catalog payloads from canonical owners. | C1-C5,C7,C9 plus checked schema projection; expected B full-owner expansion, actual public/private resource closure and no retired registration revival. No manual generated repairs. | AC-25,AC-26 | T24,T30,T13 | PENDING |
| T32 | Integrate focused D/J/K/Q/X routing through CI and existing test inventory, preserving #854 changes. | C8 tests select new checks for their changed owners and docs-only selection remains appropriate; zero tests and missing exact-head results cannot produce aggregate green. | AC-25,AC-27 | T31 | PENDING |
| T33 | Update DOC and relevant operative route diagrams/reference inputs only after tracing current generator ownership. | C1-C9 as applicable and actual documented site pipeline; all five outcomes, read-only/application-code distinction, handoff, portability limits and discovery agree. No historical proof relabeling. | AC-25,AC-26 | T31 | PENDING |
| T34 | Introduce/run Q exact candidate inventory and cold-layout tests using current qualified package workflow. | Candidate commit/tree/digest and no source access; actual installed validator/resources plus authorized task route resolve from public and private entries. Partial install fails explicitly. V28,V32,V34,V36,V40. | AC-21,AC-22,AC-25,AC-27 | T31,T32 | PENDING |
| T35 | Run harmless real installed Claude debug-to-fix and retained task journeys on declared available cells. | V01,V03-V06,V15,V17,V21-V29,V31,V33,V36,V38,V40 as applicable: real dispatch/tool/effect and caller/TDD trace, not schema-only proof. P-QUAL required. | AC-01,AC-03,AC-04,AC-05,AC-11,AC-12,AC-16,AC-17,AC-18,AC-19,AC-20,AC-21,AC-22,AC-24,AC-26,AC-27 | T34,T33,P-QUAL | PENDING |
| T36 | Introduce X/qualification-cells record validation and freeze M trial setup/hidden oracles, without implementing a provider runner. | V34/V35/V41 reject wrong artifact/cell, missing/zero/cancelled proof and best-run-only records. Exact host/model/tools/settings/authorization/metering fields or explicit unknowns. | AC-27,AC-28 | T04,T06 | PENDING |
| T37 | Run declared comparative model trials and candidate safety/disclosure/staleness trials. | SCENARIOS minimum 14 paired cases x 3 fresh baseline/candidate repetitions per declared configuration; V05,V06,V22 candidate x3; all other required rows in declared layers. Retain individual failures; solvable fixtures cannot escape unresolved. | AC-01,AC-02,AC-03,AC-04,AC-05,AC-06,AC-07,AC-08,AC-09,AC-10,AC-11,AC-12,AC-13,AC-16,AC-17,AC-18,AC-19,AC-20,AC-23,AC-24,AC-27,AC-28 | T35,T36,P-QUAL | PENDING |
| T38 | Independently run Codex installed journeys and applicable Pi generated/contract regression checks on declared cells. | Same exact qualified obligations per claimed host, tokenless root and actual generated public/private calls. Explicit pending/degraded cells; no Claude-result inheritance or implied Pi HTML-authority support. | AC-14,AC-16,AC-17,AC-20,AC-21,AC-22,AC-25,AC-26,AC-27 | T34,T36,P-QUAL | PENDING |
| T39 | Reconcile complete acceptance evidence, repeat affected failed cases after corrections, and request fresh independent review. | All 28 native criteria mapped to actual proof; scenario and task DAG checks; source/host/model proof distinct; normal exact-head required CI complete; pending external cells prevent their readiness claim. No stale run reused after edits. | AC-25,AC-26,AC-27,AC-28 | T33,T35,T37,T38 | PENDING |
| T40 | Prepare authorized release/rollout and rollback handoff using current package owner; record exact exercise smoke prerequisite. | Coherent producer/validator/consumer/generated/docs rollback, no state migration/history deletion, real package version only when owner assigns it, installed smoke in actual exercise environment. No merge/tag/publish without separate authorization. | AC-23,AC-25,AC-26,AC-27,AC-28 | T39 | PENDING |

T35/T37/T38 are qualification work packages, not single agent implementation tasks. Before native execution, expand them into per-scenario/per-cell child tasks with exact commands or observed tool journeys, bindings and required permissions; preserve every listed criterion and original repetition count. Likewise split any implementation row that cannot remain a bounded red-to-green unit. Do not invent a fixed duration, collapse all host runs into one checkbox, or waive the parent gate. This expansion is method planning, not new product scope.

## 6. Criterion coverage, both directions

This checks consistency, not completeness or successful execution. T02 and the adversarial review separately address whether the criteria cover the intent.

| AC | Principal implementation/proof tasks |
|---|---|
| AC-01 | T15,T35,T37 |
| AC-02 | T15,T37 |
| AC-03 | T15,T35,T37 |
| AC-04 | T17,T35,T37 |
| AC-05 | T17,T28,T35,T37 |
| AC-06 | T16,T37 |
| AC-07 | T03,T10,T16,T37 |
| AC-08 | T18,T37 |
| AC-09 | T17,T37 |
| AC-10 | T04,T11,T18,T37 |
| AC-11 | T18,T24,T35,T37 |
| AC-12 | T18,T24,T35,T37 |
| AC-13 | T11,T18,T37 |
| AC-14 | T08,T09,T12,T13,T19,T29,T38 |
| AC-15 | T07-T13 |
| AC-16 | T14,T19,T20,T35,T37,T38 |
| AC-17 | T14,T20,T21,T35,T37,T38 |
| AC-18 | T11,T22,T35,T37 |
| AC-19 | T22,T35,T37 |
| AC-20 | T23,T35,T37,T38 |
| AC-21 | T25,T26,T29,T30,T34,T35,T38 |
| AC-22 | T25,T27-T30,T34,T35,T38 |
| AC-23 | T19,T37,T40 |
| AC-24 | T14,T20,T24,T30,T35,T37 |
| AC-25 | T01,T13,T15,T24,T31-T34,T38-T40 |
| AC-26 | T01,T05,T06,T21,T23,T24,T30,T31,T33,T35,T38-T40 |
| AC-27 | T02,T04-T06,T32,T34-T40 |
| AC-28 | T04,T19,T36,T37,T39,T40 |

Every task table row names at least one AC; no task is authorized merely because it appears in this table. D1 checks and native adoption do not count as implemented behavior. Each principal-task entry must also appear in that task's AC cell; review mismatches before adoption.

## 7. Parallel work and merge order

After T06, separate owners may work on D/L/E/R/G and on K/H. The workflow owner handles W/F/T/I/A in order after P-854. Avoid parallel writers on W, F, T, H, or the generator/CI inventories. A fixture author may prepare Z/J, but hidden oracles must be reviewed independently of the model solving the cases.

D3 can advance T25-T28 before E exists; T29 waits for the actual entry, not a stand-in. T24 waits for T30 because the real follow-up route is part of terminal behavior. T36 may prepare qualification records independently after D1, but no paid/live trial runs before P-QUAL. Documentation may be drafted independently, then reconciled after T31. D4 combines source projections once; regenerate after resolving canonical conflicts rather than choosing one generated side.

Brownfield may improve its context/map contract independently. Debug's optional-map consumption must remain compatible with its current coarse map and absent-map case. Do not turn the other session's proposed schema or AGENTS placement into an unapproved debug dependency.

## 8. Review checkpoints and failure handling

At D1, challenge the transfer model: a valid packet can still be false, stale, or unauthorized. At D2, review the actual consumer and target-red classifications, not only producer prose. At D3, run the literal emitted invocation from the installed layout, not a corrected hand-written equivalent. At D4, compare the exact payload and individual model/host observations; a green source checker cannot close absent runtime proof.

An unmet approval or safety gate remains a stop. A resource/authority/cell gap is reported precisely; do not change modes, trust, thresholds, registries, or rules to pass. Host errors narrow/block that cell; useful safe inspection may still return unresolved. Model failure keeps its trial evidence, receives a scoped correction, and requires fresh affected trials. A source change invalidates proof whose inputs it changes.

The case-appropriate unresolved outcome is a product success only for a genuinely blocked fixture, never a blanket pass for hard solvable tasks. Detect expensive ceremony by measuring actual aggregate tokens/time/interventions against the same inputs and current declared model settings. Unknown usage is not free. No numeric savings or universal diagnosis guarantee is specified.

## 9. Migration, rollback, and acceptance

There is no consumer-state migration or new durable case directory. Never clear historical debug notes/tasks, accepted ADRs, or approvals. Rollback changes the coupled feature resources and claims, retaining prior evidence and #854's independent owner consolidation/retirement. Do not leave new packets silently accepted by old consumers or new producers requiring removed helpers.

The WIP PR may contain this reviewed proposal now. It must not be represented as native approved work, runtime implementation, or exercise qualification. Promotion to implementation starts with T01-T06. Completion of runtime code alone does not close installed/model criteria. Merge and release retain their actual required checks and separate authorizations. A target host remains unqualified where its external cells are pending.
