# Debug correctness: implementation plan input

Status: Source-only plan; T01-T04 SOURCE_COMPLETE, T05-T06 BLOCKED, T07-T40 PENDING. D1 remains incomplete until native adoption and actual approval. See [D1.md](D1.md). No runtime implementation, product verification or release qualification is asserted.  
Specification: [SPEC.md](SPEC.md), CA-DEBUG-CORRECTNESS-01 D1 review revision 3  
Contract: [CONTRACT.md](CONTRACT.md)  
Scenario oracles: [SCENARIOS.md](SCENARIOS.md)  
Completeness review: [REVIEW.md](REVIEW.md)

## 1. Execution and integration boundary

This is the requested WIP preparation, not a shadow authoritative `.codearbiter` plan. D1 source preparation has settled exact adoption inputs in D1-PROFILE.md and D1-CASES.json. Native adoption/approval is still blocked as recorded in D1.md. A qualified installed session must create the engine-owned native specification and bound plan, validate readiness and obtain actual required approval before implementation. Map these external AC/task identities to engine-issued records; do not fabricate IDs, receipts, or approved status. Sequential planning retains approved-source binding; initial sprint planning uses only its explicit draft-pair preparation and real combined approval. No farm is requested.

After adoption, record actual native pair pointers and label these proposal inputs historical, not a second active execution ledger. PENDING here is descriptive, not a native resume state. The user's WIP request authorizes publication of this proposal, not implementation, merge, release or provider expenditure.

Base: `arbiterForge/codeArbiter@4187f1e22dc7da3cf755a2654bbf7ec268236126`. PR #854 was rechecked open/draft at `578065076e2e11a4e63f33256cb386a5cba1d7d2`; the debug owner and declaration match the prior candidate byte-for-byte. Re-read both refs before execution; recorded identities are evidence, not permission to overwrite later changes.

**P-854:** Before overlapping owner edits, require #854's accepted consolidation to be integrated, or explicit approval for a narrowly identified prerequisite extraction. Do not merge/cherry-pick its whole farm branch or treat its synthetic merge ref as a merge. Preserve `{{SKILL_ENTRY:debug}}`, the single owning skill, Claude owner versus generated-command visibility, Codex/Pi entry discovery, actual output-relative resource resolution and retirement of `new-skill`/`skill-author`. Replace the moved active-fix prohibition with a finite internal diagnostic return, not recursive public routing. If the prerequisite changes or is rejected, record a revised integration decision. Do not resurrect retired procedures.

**P-AUTH:** Before D2/D3, exact installed native capability, current ready/approved spec-and-plan binding and actual workflow authority. Missing capability stops native authoring/execution; no hand-authored HTML, Markdown shadow or source-built authority substitute.

**P-QUAL:** Before live qualification, exact intended host/package/runtime cells, permitted tools/network/targets and applicable model/provider/spend authority. Unknown inputs block that cell and readiness claim, not unrelated deterministic work. No OS, installed version or provider is inferred from profile or memory.

## 2. Delivery slices

| Slice | Task range | Outcome and exit |
|---|---|---|
| D1 | T01-T06 | Freeze ownership, contract, oracles and native adoption; actual approval before implementation. |
| D2 | T07-T24 | Coupled finite validator, truthful debug producer, actual fix consumer and bug-origin TDD. P-854 gates overlapping owner edits. |
| D3 | T25-T30 | Installed-root, interpreter, literal-argument and effect portability. Parallel with D2 under separate file ownership after D1. |
| D4 | T31-T40 | Generated/documentation closure, actual package/host/model qualification and release handoff. Follow dependencies, not numeric order. |

The minimal coherent implementation includes T07-T34, T36 and operative documentation after D1. Source/fixture completion is not exercise qualification: applicable T35/T37-T40 evidence and normal gates remain required. Do not ship a newly required producer without its validator, consumer and helper. No persistent case kind, global memory, new public entry or mandatory agent fleet is part of any slice.

## 3. Exact path ownership

Keys in task rows expand to these repository-relative paths. New locations are proposed, not claims that they already exist. Equivalent existing owners may be selected only with documented correspondence and updated verification, never duplicate contracts.

| Key | Exact paths and boundary |
|---|---|
| P | `docs/proposals/debug-correctness/` containing SPEC.md, CONTRACT.md, SCENARIOS.md, PLAN.md and REVIEW.md; source-only proposal. |
| L | `core/pysrc/_debughandofflib.py`; new finite definitions, decoder and semantic validator; no import effects. |
| E | `core/pysrc/debug-handoff.py`; new private stdin/stdout entry, not a registered hook or public command. |
| R | `core/surface/skills/debug/references/handoff.md` and `core/surface/skills/debug/references/debug-handoff.schema.json`; on-demand projections plus bounded interpretation, no skill frontmatter. |
| G | `tools/build-debug-handoff.py`; proposed source-only projection/check tool only if existing generation cannot own it. |
| W | `core/surface/skills/debug/SKILL.md`; sole debug procedure. |
| B | `core/surface/commands/debug.md`; retain the whole-file SKILL_ENTRY declaration after P-854. |
| F | `core/surface/commands/fix.md`; existing caller and actual handoff consumer. |
| T | `core/surface/skills/tdd/SKILL.md` and `core/surface/includes/author-tdd-workflow.md`; bug-origin/author integration. |
| A | `core/surface/agents/backend-author.md`, `frontend-author.md` and `infra-author.md` in that same agents directory; inspect, edit only demonstrated contradictions. |
| I | `core/surface/includes/routing-table.md` and `core/surface/skills/INDEX.md`; existing routing/discovery, no new registrations. |
| H | `core/surface/commands/task.md`, `core/surface/includes/codex-host-notes.md`, `core/surface/includes/pi-host-notes.md`; proposed private `core/surface/includes/helper-invocation.md` only when no existing owner avoids duplication. |
| D | `.github/scripts/test_debug_handoff.py`; proposed production decoder/SEM/conformance unittest entry. |
| J | `.github/scripts/test_debug_workflow.py`; proposed source/actual-consumer fixtures, not model execution proof. |
| K | `.github/scripts/test_debug_helper_invocation.py`; proposed real subprocess/layout/argv/effect tests. |
| Q | `.github/scripts/test_debug_package.py`; proposed exact candidate and cold-layout tests. |
| X | `.github/scripts/test_debug_qualification.py`; proposed evidence-record/oracle boundary checks, not a provider runner. |
| Z | `.github/fixtures/debug/` with cases.json, handoff-examples.json and qualification-cells.json; finite synthetic inputs and explicit pending records. |
| CI | `.github/scripts/test_ci_impact.py` and `.github/workflows/ci.yml`; integrate focused checks through current planner/jobs; preserve unrelated #854 work. |
| DOC | `site/src/curated/commands/debug.md`, `site/src/curated/skills/debug.md`, `site/src/curated/commands/fix.md`, `docs/architecture.md`, `docs/parity.md`; trace live generator ownership before changing diagrams or narrower source inputs. |

Canonical sources generate host copies. The descriptor owns all output paths, including Claude commands/skills, Codex/Pi public ca-debug skills/private debug routines and existing hooks directories for shared Python. Verify copying of non-Markdown schema references rather than assume it. Never edit a derivative directly or alter historical acceptance records.

## 4. Verification contract

Each row's AC cell is its external `maps-to` reference to the actual TDD obligation(s) derived after native adoption. It is not a second obligation ID scheme. A verification advances its criterion but does not replace red, review, coverage, lint, commit or merge requirements.

Existing source commands: C1 `python tools/build-surface.py --check`; C2 `python .github/scripts/test_build_surface.py`; C3 `python .github/scripts/test_host_descriptors.py`; C4 `python .github/scripts/test_command_route_compatibility.py`; C5 `python .github/scripts/check_routing_index_parity.py`; C6 `python .github/scripts/test_board_sync.py`; C7 `python .github/scripts/test_codex_skill_resources.py`; C8 `python .github/scripts/test_ci_impact.py`; C9 `python .github/scripts/test_artifact_surface.py`. Contributor Python syntax checks use `python -m py_compile` on exact changed paths; they are not the validator's no-write journey.

D/J/K/Q/X are introduced by T07/T14/T25/T34/T36, respectively. Once implemented, their ordinary command is `python <exact script path>` with standard unittest. Document and test supported selectors; zero selected assertions must fail. Until introduced these are planned commands, not existing or executed checks. G's checked mode is tested before use. Read current actual core-sync/package commands; do not invent flags.

For each behavior, observe a meaningful failed obligation at its actual layer before minimum implementation and green. Missing imports, nonexistent test selectors, disconnected toy consumers and schema-shaped answers are not target red. Do not commit a failing required contributor check because the branch is WIP. Tests and their minimal implementation may be committed together after the actual red-to-green cycle when necessary.

S/D/H/M mean source-generated, real deterministic mechanics, exact installed-host journeys and actual model workflows as defined in SCENARIOS.md. Source tests cannot prove execution or causation. The pure validator cannot prove current authority, causal truth, freshness or arbitrary diagnostic side effects. Qualification cells use actual production paths and independently reviewed hidden oracles.

## 5. Task ledger

Follow explicit dependencies. T36 can prepare evidence records after D1. T34 introduces Q after generated integration; T32 waits for both T34 and T36 so CI never references an uncreated runner. Numbering is stable identity, not a requirement to run tasks sequentially.

### D1

SOURCE_COMPLETE means the source-only preparation deliverable exists, not native acceptance. T01 records the integration policy; P-854 is NOT satisfied while its accepted consolidation is unintegrated. T02/T04 retain actual independent review as an outstanding T06/T36 requirement. T05 is blocked by the inspected installed-workflow mismatch; T06 additionally lacks a current native pair and host-observed approval. These labels are not engine task states.

| ID | Exact path keys and work | Verification / completion evidence | AC / maps-to | Depends on | Status |
|---|---|---|---|---|---|
| T01 | P, W, B, I: Revalidate main/#854 and record the exact accepted owner-consolidation prerequisite, without importing unrelated changes. | V36: exact refs/patches, sole owner, discovery differences and retirement retained. | AC-25,AC-26 | None | SOURCE_COMPLETE |
| T02 | P: Cross-check scope, original review, all criteria and scenario oracles; resolve missing intent before task execution. | All G1-G8/R01-R15 and original V01-V35 retained; answer what remains broken if static checks pass. | AC-01,AC-10,AC-16,AC-27 | T01 | SOURCE_COMPLETE |
| T03 | P/CONTRACT.md: Finalize the finite date-time, numeric, Unicode, fingerprint and validator-result profiles before native readiness. | V39/V40: explicit valid/invalid format cases and schema/runtime agreement; 0.0 control is not a defect. | AC-07,AC-14,AC-15 | T02 | SOURCE_COMPLETE |
| T04 | P/SCENARIOS.md: Freeze closed-field/SEM negative cases and hidden ground truth; retain original example identities. | Every SEM-01 through SEM-19 has negative coverage; solvable versus blocked outcomes fixed before trials. | AC-10,AC-15,AC-27,AC-28 | T03 | SOURCE_COMPLETE |
| T05 | P; engine-selected native spec/plan paths: Adopt this proposal through the qualified installed native authoring workflow and record the actual pair pointers. | Engine-issued IDs, ready validation, exact source binding, external-ID correspondence; no fake receipt or Markdown shadow. | AC-26,AC-27 | T04 | BLOCKED |
| T06 | Native pair; P/REVIEW.md: Complete adversarial/completeness review, native task expansion and actual required approval. | Current approved pair and real host-observed authority; complete AC coverage and acyclic task graph. P-AUTH satisfied. | AC-26,AC-27 | T05 | BLOCKED |

### D2

| ID | Exact path keys and work | Verification / completion evidence | AC / maps-to | Depends on | Status |
|---|---|---|---|---|---|
| T07 | D, Z/handoff-examples.json: Introduce the fixture harness with original valid, shape-invalid and semantic-invalid examples. | V19/V20: named test selection, proper shape/SEM distinction, and zero-selected tests fail. | AC-14,AC-15 | T06 | PENDING |
| T08 | L, D: Implement finite model definitions and primitive validation with no import-time effects. | V20/V39: full-match IDs, bounds, nulls, enums, Unicode/date/integer profile; booleans and trailing controls reject. | AC-14,AC-15 | T07 | PENDING |
| T09 | L, D: Implement bounded byte decoding before semantic validation. | V20/V39: exact/over 65,536 UTF-8 bytes, depth 16/17, duplicate keys, malformed/non-finite JSON and lone surrogates. | AC-14,AC-15 | T08 | PENDING |
| T10 | L, D: Implement reference, evidence and check-state semantics. | V19/V20: duplicate/dangling references, planned-check reproduction and conflicting evidence reject; genuine executed observations remain valid. | AC-07,AC-15 | T09 | PENDING |
| T11 | L, D: Implement five-outcome, actionable-handoff, regression-reuse and fingerprint-pair semantics. | V13/V37-V39: positive outcome controls and explicit negative cross-field cases; no validation-as-causality claim. | AC-10,AC-13,AC-15,AC-18 | T10 | PENDING |
| T12 | E, D: Add the private bounded stdin/result wrapper with bytecode suppression before local imports. | V40: actual exit 0/2/3, bounded diagnostics, no raw echo, files/cache, subprocesses, network or authority events. | AC-14,AC-15 | T11 | PENDING |
| T13 | L, R, G, D: Generate checked schema/reference projections from the finite runtime definitions. | Deterministic projection and stale-output rejection; shape conformance distinct from SEM proof; no runtime schema interpreter. | AC-14,AC-15,AC-25 | T12 | PENDING |
| T14 | J, Z/cases.json: Introduce actual producer/consumer transport and finite call-return fixtures. | V21-V23/V36: exercise real payload/helper paths and caller context, not a disconnected mock consumer. | AC-16,AC-17,AC-24 | T13 | PENDING |
| T15 | W, B, J: Revise sole-owner entry/capture and optional-map use while retaining the SKILL_ENTRY declaration. | V01-V03/V36 and source checks: no invented repro, onboarding, padded wrapper, or lost host discovery. | AC-01,AC-02,AC-03,AC-25 | T14,P-854 | PENDING |
| T16 | W, J: Revise hypothesis/evidence phases for real discriminators, capture limits and current source/runtime binding. | V07-V10/V39: no fixed-count padding, recency-as-proof, partial-log refutation or unchanged read loop. | AC-06,AC-07 | T15 | PENDING |
| T17 | W, R, J: Define bounded diagnostic actions and sanitized untrusted-input handling, without a new executor. | V04-V06/V12: no unsafe replay, log instructions, unauthorized instrumentation or confirmation by proposed experiment. | AC-04,AC-05,AC-09 | T16 | PENDING |
| T18 | W, J: Replace the three-exit model with five truthful outcomes and valid early unresolved return. | V11-V18/V37: no forced ADR, no-action from failed replay, or loss of supported multi-cause/authority blockers. | AC-08,AC-10,AC-11,AC-12,AC-13 | T17 | PENDING |
| T19 | W, R, J: Wire validated bounded summary/packet transfer, legacy normalization, capacity handling and honest resume. | V19-V22/V30: preserve actual evidence, disclose drift/loss/limits, no new store or automatic full-JSON output. | AC-14,AC-16,AC-23,AC-28 | T18,T13 | PENDING |
| T20 | F, J: Consume packet through real validation, caller authority and freshness checks; implement one internal diagnostic prerequisite return. | V21-V23/V31/V36: no public recursion, repeated answered questions, diagnosis-only repair or intent-field authority. | AC-16,AC-17,AC-24 | T19 | PENDING |
| T21 | T, A, J: Add explicit bug-origin obligations and inspect author charters; edit only demonstrated contradictions. | V23/V33: actual author receives scoped regression/expectation without fabricated feature artifacts; feature/refactor authority retained. | AC-17,AC-26 | T20 | PENDING |
| T22 | T, J: Implement adequate existing target-red reuse and separate unrelated/setup baseline failures. | V24/V25/V38: named test reuse, no duplicate-by-age, concealed baseline, false target red or commit-gate waiver. | AC-18,AC-19 | T21 | PENDING |
| T23 | T, A, J: Close minimum-repair and fresh verification behavior, including intermittent oracles and changed fixtures. | V26/V27: correct red before repair, unchanged assertions, renewed red after material setup changes and honest stochastic limits. | AC-20,AC-26 | T22 | PENDING |
| T24 | W, F, I, J: Reconcile terminal task/ADR behavior and route/discovery summaries after the real follow-up helper is tested. | V15/V17/V31/V33, C5/C6: no default queued close; authorized real follow-ups only; history and owners intact. | AC-11,AC-12,AC-24,AC-25,AC-26 | T23,T30 | PENDING |

### D3

| ID | Exact path keys and work | Verification / completion evidence | AC / maps-to | Depends on | Status |
|---|---|---|---|---|---|
| T25 | K, Z: Introduce isolated subprocess/layout fixtures that capture actual helper attempts and literal argv. | V28/V29: no repaired-command or source-path rescue; owned scratch and observed effects. | AC-21,AC-22 | T06 | PENDING |
| T26 | H, K: Define resource-derived installed-root resolution for affected validator and task invocations. | V28: unset tokens, nested/arbitrary cwd, spaces/non-ASCII paths, missing helper; no /hooks or cache/source search. | AC-21 | T25 | PENDING |
| T27 | H, K: Validate interpreter selection before invoking the helper, preserving original nonzero failure. | V29: real/alternate/missing/stub/incompatible Python; exactly one writer attempt, no second-interpreter replay. | AC-22 | T26 | PENDING |
| T28 | H, K: Preserve literal arguments, options-before-separator and bounded stdin on supported host shells. | V29: quotes, leading hyphens, metacharacters and non-ASCII remain data; no shell interpolation. | AC-05,AC-22 | T27 | PENDING |
| T29 | E, H, K: Exercise actual validator invocation from read-only installed layout without root tokens. | V40: no pycache/temp/project writes, socket/process effects or payload echo; correct limits/status and no fallback retry. | AC-14,AC-21,AC-22 | T28,T12 | PENDING |
| T30 | H, K: Exercise the actual existing writer through the genuinely authorized follow-up invocation. | V28/V29/V31: correct worktree board, literal input, lock/refusal/atomic behavior and single attempt preserved. | AC-21,AC-22,AC-24,AC-26 | T29 | PENDING |

### D4

| ID | Exact path keys and work | Verification / completion evidence | AC / maps-to | Depends on | Status |
|---|---|---|---|---|---|
| T31 | Canonical owners; generated hosts: Regenerate shared Python, all affected host entries/routines, references and catalogs from their owners. | C1-C5/C7/C9 and checked contract projection; actual public/private closure; no hand-edited derivatives or retired registrations. | AC-25,AC-26 | T24,T30,T13 | PENDING |
| T32 | CI: Register focused D/J/K/Q/X checks in the existing CI planner only after every referenced runner exists. | C8: correct impact selection, docs-only behavior, missing/zero tests cannot be green; preserve #854 CI/conformance changes. | AC-25,AC-27 | T31,T34,T36 | PENDING |
| T33 | DOC: Update operative docs and generator-owned diagrams after tracing the current source of each claim. | Current site pipeline and C1-C9 as applicable; five outcomes, authority, helper/discovery limits agree; history remains historical. | AC-25,AC-26 | T31 | PENDING |
| T34 | Q, Z: Introduce and run exact-candidate inventory/cold-layout package checks with current packaging ownership. | V28/V32/V34/V36/V40: exact commit/tree/digest, inaccessible source checkout, real installed helper/resources and partial-install rejection. | AC-21,AC-22,AC-25,AC-27 | T31,T36 | PENDING |
| T35 | Q, J, Z; actual declared Claude cell: Run harmless real installed Claude debug-to-fix and authorized task journeys. | Applicable V01/V03-V06/V15/V17/V21-V29/V31/V33/V36/V38/V40 with actual tool/caller/TDD/effect trace, not schema proof. | AC-01,AC-03,AC-04,AC-05,AC-11,AC-12,AC-16,AC-17,AC-18,AC-19,AC-20,AC-21,AC-22,AC-24,AC-26,AC-27 | T34,T32,T33,P-QUAL | PENDING |
| T36 | X, Z/qualification-cells.json: Introduce qualification-record checks and freeze trial setup/hidden oracles without a provider executor. | V34/V35/V41: exact cells/settings/permissions, false-green rejection, unknown metering explicit; no trial spend yet. | AC-27,AC-28 | T04,T06 | PENDING |
| T37 | X, Z; authorized declared model/host cells: Run the required paired comparison and candidate safety/disclosure/staleness trials. | Fourteen paired cases, three fresh repetitions for each arm per configuration; candidate V05/V06/V22 x3; retain all failures and other required proof layers. | AC-01,AC-02,AC-03,AC-04,AC-05,AC-06,AC-07,AC-08,AC-09,AC-10,AC-11,AC-12,AC-13,AC-16,AC-17,AC-18,AC-19,AC-20,AC-23,AC-24,AC-27,AC-28 | T35,T36,P-QUAL | PENDING |
| T38 | Q, K, X, Z; declared Codex/Pi cells: Independently exercise Codex installed journeys and applicable Pi generated/contract regression checks. | No Claude-result inheritance, token/source rescue or implied Pi HTML-authority support; exact pending/degraded cells disclosed. | AC-14,AC-16,AC-17,AC-20,AC-21,AC-22,AC-25,AC-26,AC-27 | T34,T32,T36,P-QUAL | PENDING |
| T39 | Native pair; exact evidence records: Reconcile all criterion evidence, rerun affected failed cases after fixes, and obtain fresh independent review. | All 28 criteria mapped to actual distinct proof layers; current required CI complete; pending external cells prevent readiness claims. | AC-25,AC-26,AC-27,AC-28 | T33,T35,T37,T38 | PENDING |
| T40 | Native pair; existing release owner: Prepare release/rollback handoff and actual exercise-environment smoke prerequisite; do not publish. | Coupled rollback and exact artifact/cell evidence; no state migration or inferred version/merge/release authority. | AC-23,AC-25,AC-26,AC-27,AC-28 | T39 | PENDING |

T35/T37/T38 are qualification work packages. During native planning expand them into scenario/cell child tasks with exact commands or observable tool journeys, bindings and permissions. Preserve all parent criteria and repetition counts. Split any implementation row that cannot remain a bounded red-to-green unit. Do not invent fixed durations, convert all hosts into one checkbox or mark a parent complete from one child.

## 6. Criterion-to-task traceability

This table is derived from the task AC cells. It checks consistency, not completeness of user intent or execution success. T02 and the adversarial review separately address intent. Every task has at least one criterion; every original AC has one or more tasks.

| Criterion | Tasks |
|---|---|
| AC-01 | T02,T15,T35,T37 |
| AC-02 | T15,T37 |
| AC-03 | T15,T35,T37 |
| AC-04 | T17,T35,T37 |
| AC-05 | T17,T28,T35,T37 |
| AC-06 | T16,T37 |
| AC-07 | T03,T10,T16,T37 |
| AC-08 | T18,T37 |
| AC-09 | T17,T37 |
| AC-10 | T02,T04,T11,T18,T37 |
| AC-11 | T18,T24,T35,T37 |
| AC-12 | T18,T24,T35,T37 |
| AC-13 | T11,T18,T37 |
| AC-14 | T03,T07,T08,T09,T12,T13,T19,T29,T38 |
| AC-15 | T03,T04,T07,T08,T09,T10,T11,T12,T13 |
| AC-16 | T02,T14,T19,T20,T35,T37,T38 |
| AC-17 | T14,T20,T21,T35,T37,T38 |
| AC-18 | T11,T22,T35,T37 |
| AC-19 | T22,T35,T37 |
| AC-20 | T23,T35,T37,T38 |
| AC-21 | T25,T26,T29,T30,T34,T35,T38 |
| AC-22 | T25,T27,T28,T29,T30,T34,T35,T38 |
| AC-23 | T19,T37,T40 |
| AC-24 | T14,T20,T24,T30,T35,T37 |
| AC-25 | T01,T13,T15,T24,T31,T32,T33,T34,T38,T39,T40 |
| AC-26 | T01,T05,T06,T21,T23,T24,T30,T31,T33,T35,T38,T39,T40 |
| AC-27 | T02,T04,T05,T06,T32,T34,T35,T36,T37,T38,T39,T40 |
| AC-28 | T04,T19,T36,T37,T39,T40 |

## 7. Parallelism, integration and acceptance

After T06, L/E/R/G/D and H/K can have separate owners. The workflow owner handles W/F/T/I/A after P-854. Do not run parallel writers against those shared files or CI/generator inventories. Fixtures may be prepared independently; ground truth must remain outside the solving model's accessible synthetic checkout and be reviewed independently of its answer.

T25-T28 need not wait for E; T29 must use the actual entry, not a stand-in. T24 waits for the tested real follow-up path T30. T36 may prepare metadata without live provider use. T31 regenerates once after canonical conflict resolution; T34 then creates Q, and only afterward T32 registers every extant runner. Documentation may be drafted in parallel but is reconciled against final behavior. Main/#854 drift requires source-level reconciliation followed by regeneration, not selecting one generated side wholesale.

Brownfield remains independent. Consume the existing optional coarse map and absent-map behavior; do not depend on that session's unapproved AGENTS placement/schema or take ownership of context generation. #854's farm, refactor and independent retirement work are not this implementation.

Retain the fourteen paired cases and three fresh repetitions for each baseline/candidate arm per declared host/model configuration from SCENARIOS.md. Candidate V05/V06/V22 additionally run three times. Other scenarios retain their declared proof layers. Keep individual failed trials and rerun affected cases after corrections; unknown metering is not zero, unlike configurations are not pooled, and best-run selection is not qualification. Solvable cases cannot pass as unresolved; genuinely blocked cases must identify a discriminator and resume condition. No automatic provider spend or unsupported host claim.

D1 review challenges packet truth versus validation and actual approval. D2 review exercises real caller/consumer and target-red treatment. D3 runs the literal installed invocation without source/path rescue. D4 binds exact package bytes, current-source CI, host observations and model outcomes separately. Missing, cancelled, stale, zero-selected or wrong-cell evidence does not count. Pending external cells may be disclosed in a source PR but prevent their readiness claim. No current-source or source-fixture result is relabeled a released/installed guarantee.

## 8. Failure, migration and rollback

No new durable case store or consumer-state migration is introduced. Preserve historical notes/tasks, accepted ADRs and authority records. Legacy summaries are evidence input, not silently approved packets. Lost context is admitted; retained packets need actual current applicability checks. Required red commit/merge gates remain stops even when unrelated failures predate the fix.

An unavailable capability, owner, authority or safe bounded action is reported precisely. Do not change modes, trust, thresholds, registrations or security rules to proceed. A host gap blocks/narrows that cell; safe inspection can still yield an honest unresolved result. A material change invalidates affected proof and triggers fresh checks. No review or verification result is invented to populate a required field.

Rollback producer, validator, consumer, generated resources and operative docs coherently, without restoring #854's retired authoring surface or reversing independent consolidation. Do not leave old consumers silently accepting new packets, or new producers depending on removed helpers. Retain failed and prior qualification evidence. Partial installation fails explicitly, not by source-clone rescue.

The WIP proposal can be reviewed now. Implementation starts only after T01-T06 and relevant prerequisite gates. Native approval, source completion, merge eligibility, named-host readiness and published-artifact qualification remain distinct. Before the exercise, a selected exact qualified artifact needs a harmless smoke in the actual environment. Merge, tag and publication still require separate authorization.
