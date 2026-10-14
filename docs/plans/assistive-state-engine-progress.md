# Assistive state-engine overhaul: implementation progress

**PR:** #983, `overhaul/assistive-state-engine` -> `main`.
**State:** DRAFT; three implementation slices, not the completed overhaul or a released package.
**Baseline:** `arbiterForge/codeArbiter@045c0812888f20f4c843677cfb37b802e2084770:/`.
**Contract:** [the complete nine-task handoff](assistive-state-engine-overhaul.md).
**Decision:** [ADR-0043](../../.codearbiter/decisions/0043-assistive-state-engine.md), accepted product direction, separately bound to its actual source commit. No independent review or release proof is fabricated by that acceptance.

## Task status

| Task | Status | Actual delivery / remaining work |
|---|---|---|
| T01 | Complete for this starting slice | Owner decision, caller disposition below, retained full scope, native before/after failure fixture. A model-backed workflow benchmark was not run. |
| T02 | Native lifecycle expanded | Advisory scheduling, receipt-free work progress/reconciliation, draft binding, and receipt-free implementation batch completion are implemented. Full caller conversion and subject-scoped evidence assessment remain. |
| T03 | Native path implemented | Typed fact/decision definitions, explicit task scope, reported observations, failure/unknown visibility, definition-specific applicability, bounded symbol readback, and escaped HTML are implemented. Normal host callers still need T05 conversion. |
| T04 | Bounded rerun correction implemented | A new explicit batch review can select a fresh passing rerun without another task review of unchanged source/support. General task/source-scoped applicability and ordinary result recording remain. |
| T05 | Native authoring and drafting converted | Writer admission and plan preflight no longer require artifact approvals or future reviewers. The canonical drafting skill and artifact guidance are regenerated. Remaining sprint/execution entrypoints, hooks, context delivery, and obsolete adapters still need conversion. |
| T06 | Partial readback | Exact/batch prerequisite reads now include their bounded assessment and new-schema HTML displays it. Full compact task packets and retrieval-cost work remain. |
| T07 | Not started | Existing state can be read by this slice, but complete upgrade, obsolete-prompt recovery, and mixed-client compatibility are not qualified. |
| T08 | Candidate metadata and schema propagation | Schema 0.3.2 is synchronized through the bridge, builders, installed candidate checks, and rebuilt farm bundle. Breaking candidate versions advance independently; full active-instruction/documentation conversion remains. |
| T09 | Focused evidence collected | Native tests and source checks below are not final installed-candidate or publication qualification. |

Continue in this same PR. Do not create a second overhaul branch or mark this slice ready to merge.

## Third slice: authoring admission and review reuse

Starting head: `b6a775f3a9f30a450940d75ec7447b69b6c75808` on the same PR branch.

The native bridge now asks whether the actual writer can operate, not whether
all future authority producers are installed. Spec/plan route selection no
longer calls the historical host authority inventory. Plan preflight checks the
selected source's identity and structural validity without requiring ready or
approved status. Existing wrong-root, forged-client, namespace-conflict, pinned
payload, and CAS checks remain. Incomplete drafts remain incomplete rather than
acquiring fabricated approval. The paired-draft argument is a typed compatibility
keyword, not a separate permission mode.

The canonical writing-plans skill now reflects that behavior: coherent task
sizes, actual criteria/dependencies, useful diagnostics, no drafting approval
codes, and no future-runner preflight simply to maintain the plan. The artifact
include describes ordinary progress separately from explicit historical receipt
operations. These edits are generated into all three adapters. They do not by
themselves convert every sprint/execution entrypoint or retire old hooks.

The native completion path also separates a new verification run from a task
review of unchanged work. A new explicit batch review may select a separately
validated passing rerun while retaining the original task review and its original
run. The prior reviewed subject must still be current, the rerun must match its
own recorded workspace, normalized reviewed workspaces must agree, and selected
support must be retained. Different source or corrupt recorded closure fails;
a new receipt ID alone no longer forces another task reviewer. No old review is
relabeled as seeing a new run. This is a bounded T04 correction, not general
impact analysis or removal of the explicit path's initial review requirement.

CI on the starting head exposed stale runtime `adapter_version` literals and a
second Codex package manifest after the preceding candidate bumps. Runtime
identities and both Codex manifests are now aligned with the existing unreleased
candidates (3.0.0 / 0.18.0 / 0.19.0). No root-validation check is weakened, and no
new release/version series is invented. The earlier payload-version passes did
not establish this runtime consistency; the descriptor and cold-install checks
cover that separate boundary.

### Third-slice verification

| Check | Actual result |
|---|---|
| Final native Windows build | All 15 tested native packages pass. Built with Go 1.27.1; the builder explicitly records no upstream-host qualification. |
| Final Linux operations suite | 124 top-level tests pass, zero fail; one existing Windows-only case skips. The binary was cross-compiled and actually executed under Ubuntu/WSL on an isolated Linux filesystem copy. |
| Final pinned writer/bridge fixtures | 50 authoring tests, 17 bridge tests, 43 workflow tests, and 79 legacy approval-compatibility tests pass against the final rebuilt native payload. |
| Rerun reuse regressions | Fresh distinct runs can reach a separately reviewed batch acceptance while original task review/run references remain unchanged. Changed source and a corrupt run-owned closure are rejected. No model or real verification command runs inside the explicitly synthetic producer fixture. |
| Runtime identity and interpreter checks | 22 descriptor tests pass; the ca/Codex cold-install matrix passes 468 assertions; 87 Codex adapter tests pass. These are isolated interpreter/hook fixtures, not model-backed feature qualification. |
| Generated surfaces and references | Surface generator: 147 tests run, one skip. Routing/cleanup: 53 pass. Three-adapter reference graph, canonical Python projection, and generated surface/package checks pass. |
| Integrity checks | Changed Python files compile; whitespace and ADR identity/lifecycle checks pass. No accepted ADR body or historical evidence was rewritten. |

The final Windows fixture executable SHA-256 is
`3ec20d84e8250a405bbc7f23d0fe3efc0ff5fd6730ee1da19aa58f83d8d17e06`.
It is a local test payload, not a released artifact or a marketplace installation.

Self-review caught a reuse-path omission before commit: the newly selected run
must match its own recorded workspace as well as the old reviewed subject.
That original run-integrity check is retained and has a negative regression.
An obsolete namespace-test mock was updated to include the real capability call;
its conflicting-namespace assertions were preserved and extended to that call.
No check was waived to obtain these results.

The latest commit and hosted-CI observation belong to the PR, not a claim of
continuous monitoring. Actual model-backed installed execution, full ordinary
result/applicability handling, remaining entrypoint/hook conversion, and complete
upgrade/rollback qualification remain outstanding. No release was performed.

## Second slice: scoped prerequisites and completed implementation batches

The existing prerequisite operation now records bounded caller-reported facts or
conversation decisions without arming an approval request. Definitions identify
`fact` versus `decision` and the actual `task_refs`. Missing legacy scope stays
unknown. Only affected tasks get waiting-prerequisite advice; starting/progress
operations are not another permission boundary.

Latest failures and unknown results supersede earlier successes in the advisory
view. Definition-specific identity covers the requirement, kind, source refs,
and task scope; titles and unrelated task-method edits do not invalidate it.
The engine records time and provenance without claiming authenticated host or
user evidence. User declines remain visible; a tool result or agent opinion
cannot be labeled a resolved user decision. Sources are inert text, safely escaped
in HTML. Existing journals retain history, and CAS/replay checks protect writes.

`accept-scope` now also has a receipt-free progress form with a reason. It records
`DONE`, meaning implementation complete with checks not assessed, instead of
manufacturing `ACCEPTED`. Pending work and recorded stops are not silently cleared.
The explicit proof form and its real evidence validators remain separate.

Old artifact reads preserve their bytes. New fields and DONE use schema 0.3.2;
old-version labels cannot conceal the new semantics. Exact/batch symbol reads
include the prerequisite assessment without HTML parsing or new receipt chains.
This is native compatibility/readback, not completed installed-host migration.

The candidate manifests advance for the approved breaking overhaul: Claude
3.0.0, Codex 0.18.0, Pi 0.19.0. These are **unreleased source candidates**, derived
from each independent series, not published-version or maturity claims. The root
Pi manifest is regenerated rather than edited separately. No tags, registries,
release objects, marketplace refs, or historical evidence are changed.

The previous head's platform CI failed on an obsolete CLI assertion requiring
approval for ordinary draft binding. The assertion is replaced with actual
successful-binding, no-authority, and replay coverage. Version gates previously
failed because the changed payload reused the base versions; candidate metadata
now advances rather than disabling those checks.

## What the first native slice delivered

`eligible` is an advisory query over recorded tasks and their explicit task dependencies. It returns `assessment: advisory`, `evidence_assessed: false`, recorded reasons, waiting task IDs, binding currency, and visible prerequisite requirements. It does not call `guards`, take a source snapshot, or validate approval/review receipt chains. It does not return an accepted/current-evidence claim. Earlier checkpoint numbering is not a blanket dependency gate.

`task-start` records pending work as in progress without an approval or context ticket. Starting the same active/stopped task under a new operation ID is still refused; identical operation IDs replay safely. Recording progress is not permission to perform a host operation.

`task-review` without receipts records implementation reported ready for review. Its reason explicitly says verification and review were not assessed. It does not create receipts or turn a self-report into verification. An explicit evidence claim uses the same operation with both real verification and review receipts; the closed request schema rejects partial receipt claims and completion hashes without their receipts.

`task-reconcile` supports a reasoned progress update without a receipt. It does not automatically clear stops or redispatch work; the caller must inspect actual work and honor the user's instructions. Explicitly supplied legacy receipts remain validated.

Ordinary `plan-bind` can select a structurally valid draft source without a new approval. The binding stays `draft_preview` unless the selected source really has current approval provenance. It does not reset unrelated progress or manufacture an approval. The explicit initial paired-draft compatibility path still has its older restrictions pending the remaining overhaul.

`verification-status` now owns the old accepted/current-evidence query, with genuine validation preserved. Existing acceptance-proof consumers use it rather than treating advisory scheduling as proof. This is an explicit claim-assessment operation, not a strict/relaxed execution mode. Its remaining legacy permission and freshness dependencies must not be wired back into normal task selection. T04/T05 finish that separation.

Ordinary starts no longer create a scope snapshot baseline. The first explicit receipted review initializes that legacy evidence baseline; it is not claimed to be a pre-work diff baseline. Full scope-evidence redesign remains in T04.

## T01 caller disposition and continuation map

All paths below are inside `arbiterForge/codeArbiter`. The base facts were read at the commit above; implementation changes belong only to this draft branch.

| Owning source | Disposition | Slice status |
|---|---|---|
| `core/artifacts/internal/operations/engine.go` | Keep pending-transaction barrier, CAS, request replay, and safe dispatch. Separate observational work from authority-producing operations. | Existing safeguards retained; advisory/evidence queries use the shared-observation classification. |
| `core/artifacts/internal/operations/lifecycle.go` and `assistive.go` | Convert task selection and ordinary progress from authorization to assistance. | Initial native separation implemented. Legacy scope/farm proof remains separate and unchanged in meaning. |
| `core/artifacts/internal/operations/protocol.go` | Keep closed, bounded requests; remove mandatory ceremony fields from ordinary progress. | Start ticket optional compatibility input; review has two closed claim/progress shapes; reconciliation receipt optional. |
| `core/artifacts/internal/operations/mutations.go` | Keep typed changes and stable IDs; preserve unrelated execution state. | Existing implementation reused; regression fixture checks preservation. |
| `core/artifacts/internal/validate/` and `internal/store/` | Keep structural references, path checks, transactional writes, before-images, conflict detection, and recovery. | No blanket validator/store weakening. |
| `core/artifacts/internal/evidence/` and completion-review operations | Convert whole-workflow freshness/reviewer dependencies to claim-specific applicability; keep historical results. | Not implemented; real legacy evidence checks remain, rather than returning fake success. |
| `core/pysrc/_artifactlib.py` | Separate explicit acceptance proof from ordinary scheduling. Keep pinned native payload and bounded decoding. | Proof queries use `verification-status`; generated host copies synchronized. Full admission simplification remains. |
| `_approvallib.py`, `_prerequisitelib.py`, `_reconciliationlib.py`, `artifact-reconcile.py` | Remove active duplicate permission ceremonies; retain historical readers/recovery only where required. | Not yet converted. Do not implement another Pi authority producer to satisfy the retired design. |
| `core/surface/includes/artifacts.md`, `sprint-authority.md`, `SPRINT.md`, planning/execution/TDD/resume skills | Remove instructions that recreate native approval, review, prerequisite, or reconciliation admission. | Active instructions still describe the old workflow; this is a known integration gap, not shipped parity. |
| `_artifactpromptlib.py`, `_contextselectlib.py`, actor-delivery callers | Keep useful task/constraint context, remove receipt/ticket-driven permission to continue ordinary work. | Caller conversion remains. |
| `core/artifacts/internal/read/` and renderer | Keep compact symbol reads, complete paging, stable anchors, and safe HTML. Do not use delivery receipts as task-start authorization. | Existing implementation retained; receipt integrity tested independently of task start. |
| Host package manifests, compatibility/release tooling | Publish a compatible engine/bridge/caller set with honest host-specific status and upgrade behavior. | Unreleased breaking candidate versions are set; no tag, publication, marketplace promotion, or maturity change was made. |

The handoff intentionally supersedes the October 7 Project recommendation to preserve identical artifact-origin refusals. Its old measurements remain historical. No private Project Source file is automatically replaced by this PR.

## Second-slice verification

All mutation fixtures use isolated test repositories. No model-backed host session,
user project migration, release, or marketplace promotion was performed.

| Check | Actual result |
|---|---|
| Focused Windows native regressions | 14 assistive scenarios pass, plus the existing all-operation schema-closure test. Coverage includes scoped facts, later failures/unknowns, source classification, inert Unicode/HTML, history, CAS/replay, stopped work, DONE versus accepted proof, and old-schema read preservation. |
| Final Linux native operations suite | 122 top-level tests pass, zero fail; one existing Windows-only case skips. Cross-compiled with Go 1.27.1, then actually executed under Ubuntu/WSL on an isolated Linux filesystem copy. |
| CLI integration and statement profile | 17 tests pass. The prior draft-binding CI failure is corrected; ordinary binding has explicit successful/no-approval/replay coverage. |
| Existing full Python workflow suite | 43 tests pass. This closes the previous local suite gap, but does not establish the new prerequisite path in an actual model-backed host. |
| Installed-candidate metadata bridge | Seven selected installed-input tests pass; these validate inert package fixtures, not a real installed host. |
| Doctor tests | 40 pass, one existing skip. Current capability fixtures use schema 0.3.2. |
| Native schema/type and Python projections | Generated/embedded schemas and Go views match; 90 canonical Python files match their three host copies; root Pi metadata and the badge/catalog check pass. |
| Farm bundle | Rebuilt from locked dependencies with the existing build script; the tracked bundle changes only its schema identity. No farm/model execution was performed. |
| Python syntax, ADR identity/lifecycle, whitespace | Passed. Existing accepted ADR/history is not rewritten. |

The initial complete Linux run identified an outer schema-closure omission in
the new union request descriptors. Both alternatives were already closed, but
the published operation root now also declares the closed union. The unchanged
schema-closure test and the full Linux suite pass after that correction; it was
not waived. All three payload-version guards passed against committed candidate
`2219957a3cb0e0fb64d9c83cb47a6cf031f237b4`: Claude 2.26.4 to 3.0.0,
Codex 0.17.4 to 0.18.0, and Pi 0.18.4 to 0.19.0 with regenerated root
metadata and its changelog. Final hosted CI state is recorded in the PR.

The source and generated callers still do not constitute a finished installed
workflow. Keep this PR draft until T04/T05/T07 and the remaining T06/T08/T09
work are completed together. Historical first-slice evidence follows separately.

## First-slice verification (historical; not proof of the second slice)

Tests execute in isolated temporary roots, not an existing user repository. No host model session or publication was performed.

| Check | Actual result / boundary |
|---|---|
| Six new native assistive scenarios against the unchanged base | All six failed as expected: three hit `DRAFT_BINDING`, three hit the mandatory context-ticket request field. This reproduces the native admission problem; it is not a full host transcript. |
| `go test ./internal/operations -run '^TestAssistive' -count=1 -v` on final native changes | Seven pass on Windows/amd64, Go 1.27.1, including the added stale-binding visibility regression. Covers draft work, no routine snapshot, independent task selection, preserved stops/duplicate-start rejection, CAS/replay/plan maintenance, and rejection of partial evidence claims. |
| `go test ./... -count=1` on Windows/amd64 | All 15 tested packages passed on the initial implementation slice; four packages have no tests. Operations took 360.945 seconds. Later request-schema/test adjustments were rerun in the focused Windows suite and the full Linux operations suite. This is not a final all-platform release matrix. |
| Final Linux operations test binary | Cross-compiled with Go 1.27.1, then actually executed under Ubuntu/WSL on an isolated Linux filesystem copy. 115 top-level tests passed, zero failed; one Windows-specific case was skipped by its existing platform condition. Compilation alone is not counted as execution. |
| Existing receipt-integrity regression | Moved the invented-ticket assertion to the delivery-receipt validator itself. Delivery proof remains checked; task start no longer depends on it. No failing assertion was simply deleted. |
| `python tools/sync-core.py --check` | Passed: 90 canonical Python files across three projections remain byte-identical. |
| Python syntax checks for changed bridge/test files | Passed. This is not installed-host qualification. |
| Full Python workflow attempt | Ran 43 tests: 42 passed and one obsolete stale-context admission assertion failed. Replaced that assertion with visible stale binding plus allowed progress and continued refusal of an unsupported verification claim. The matching new native regression passes; the complete Python suite was not rerun after this test-only correction. CI still owns that outstanding check. |
| `python .github/scripts/check_adr_identity.py` | Passed with the exact ADR stem; partial supersession scope remains explained in the ADR body. |
| `python .github/scripts/check_adr_lifecycle.py --base-ref 045c0812888f20f4c843677cfb37b802e2084770` | Passed. Old ledger/log history remains the exact canonical Git prefix; the new acceptance binds actual committed ADR bytes, not invented reviewer events. |
| `git diff --check` | Passed before the implementation commit. |

The fixture verifies that ordinary work produces no approval, observation, or review-receipt files. It does not claim a measured reduction in provider token spend, human permission prompts, or model reviewer launches. A complete installed workflow and final CI remain T09 evidence.

## Next implementation steps

1. Finish the normal T05 execution path: connect the implemented prerequisite/progress operations to sprint/execution entrypoints and remove duplicate artifact permission dependencies in hooks/context delivery. Drafting and the bounded batch-rerun correction are already implemented; do not rebuild them or add another authority adapter.
2. Complete T04 result/applicability handling and T07 compatibility alongside that conversion: accurate ordinary results, affected-source refresh, old prompt markers, interrupted operations, mixed installed clients, and rollback after later edits. Neither a passing rerun reuse fixture nor a native schema reader test establishes the complete workflow.
3. Finish T06-T09 in this PR: compact task packets/HTML, obsolete-prompt and interrupted-work upgrade, generated instructions, package compatibility, and an actual installed-candidate exercise. The full requirements and twelve acceptance scenarios are in the handoff.

## Merge and release boundary

Do not merge or publish this partial conversion. The active host instructions still contain the unwanted workflow, and mixed old/new installed clients have not been qualified. Preserve actual host permissions, explicit user stops/denials, normal repository CI, and publication controls. No package was released and no existing user's project state was migrated.

**Claim-registry delta for subsequent Project maintenance:** product-specific assistive-engine direction is accepted; native progress, scoped prerequisite observations, and batch completion are source-only on this PR; full orchestration, migration, and released behavior remain unverified. Record that distinction without relabeling October 7 evidence or claiming the Project files were replaced.
