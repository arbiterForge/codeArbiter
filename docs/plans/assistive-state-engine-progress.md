# Assistive state-engine overhaul: implementation progress

**PR:** #983, `overhaul/assistive-state-engine` -> `main`.
**State:** DRAFT; initial implementation slice, not the completed overhaul or a released package.
**Baseline:** `arbiterForge/codeArbiter@045c0812888f20f4c843677cfb37b802e2084770:/`.
**Contract:** [the complete nine-task handoff](assistive-state-engine-overhaul.md).
**Decision:** [ADR-0043](../../.codearbiter/decisions/0043-assistive-state-engine.md), accepted product direction, separately bound to its actual source commit. No independent review or release proof is fabricated by that acceptance.

## Task status

| Task | Status | Actual delivery / remaining work |
|---|---|---|
| T01 | Complete for this starting slice | Owner decision, caller disposition below, retained full scope, native before/after failure fixture. A model-backed workflow benchmark was not run. |
| T02 | In progress | Native advisory scheduling; receipt-free start, implementation-completion report, and progress reconciliation; ordinary draft source binding; explicit evidence query separated from scheduling. Scope completion and full caller conversion remain. |
| T03 | Groundwork only | Legacy prerequisites remain visible with recorded status and unknown task scope. No typed factual-observation writer or task-scoped prerequisite schema has been implemented. |
| T04 | Not started | Subject-scoped evidence applicability and elimination of completion-review rerun coupling remain. |
| T05 | Not started | Active host prompts, approval/prerequisite/reconciliation adapters, context delivery, and orchestration still need conversion. |
| T06 | Not started | Existing bounded symbol reads and HTML are retained; compact task-packet and retrieval-cost work remains. |
| T07 | Not started | Existing state can be read by this slice, but complete upgrade, obsolete-prompt recovery, and mixed-client compatibility are not qualified. |
| T08 | Partial propagation only | The changed Python bridge is regenerated to three host copies; full active-instruction, metadata, and documentation reconciliation remains. |
| T09 | Focused evidence collected | Native tests and source checks below are not final installed-candidate or publication qualification. |

Continue in this same PR. Do not create a second overhaul branch or mark this slice ready to merge.

## What the native code now does

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
| Host package manifests, compatibility/release tooling | Publish a compatible engine/bridge/caller set with honest host-specific status and upgrade behavior. | No release/version/maturity changes in this slice. |

The handoff intentionally supersedes the October 7 Project recommendation to preserve identical artifact-origin refusals. Its old measurements remain historical. No private Project Source file is automatically replaced by this PR.

## Verification performed

Tests execute in isolated temporary roots, not an existing user repository. No host model session or publication was performed.

| Check | Actual result / boundary |
|---|---|
| Six new native assistive scenarios against the unchanged base | All six failed as expected: three hit `DRAFT_BINDING`, three hit the mandatory context-ticket request field. This reproduces the native admission problem; it is not a full host transcript. |
| `go test ./internal/operations -run '^TestAssistive' -count=1 -v` on final native changes | Six pass on Windows/amd64, Go 1.27.1. Covers draft work, no routine snapshot, independent task selection, preserved stops/duplicate-start rejection, CAS/replay/plan maintenance, and rejection of partial evidence claims. |
| `go test ./... -count=1` on Windows/amd64 | All 15 tested packages passed on the initial implementation slice; four packages have no tests. Operations took 360.945 seconds. Later request-schema/test adjustments were rerun in the focused Windows suite and the full Linux operations suite. This is not a final all-platform release matrix. |
| Final Linux operations test binary | Cross-compiled with Go 1.27.1, then actually executed under Ubuntu/WSL on an isolated Linux filesystem copy. 114 top-level tests passed, zero failed; one Windows-specific case was skipped by its existing platform condition. Compilation alone is not counted as execution. |
| Existing receipt-integrity regression | Moved the invented-ticket assertion to the delivery-receipt validator itself. Delivery proof remains checked; task start no longer depends on it. No failing assertion was simply deleted. |
| `python tools/sync-core.py --check` | Passed: 90 canonical Python files across three projections remain byte-identical. |
| Python syntax checks for changed bridge/test files | Passed. Full behavioral Python workflow and installed-host coverage are not claimed by syntax checks. |
| `python .github/scripts/check_adr_identity.py` | Passed with the exact ADR stem; partial supersession scope remains explained in the ADR body. |
| `python .github/scripts/check_adr_lifecycle.py --base-ref 045c0812888f20f4c843677cfb37b802e2084770` | Passed. Old ledger/log history remains the exact canonical Git prefix; the new acceptance binds actual committed ADR bytes, not invented reviewer events. |
| `git diff --check` | Passed before the implementation commit. |

The fixture verifies that ordinary work produces no approval, observation, or review-receipt files. It does not claim a measured reduction in provider token spend, human permission prompts, or model reviewer launches. A complete installed workflow and final CI remain T09 evidence.

## Next implementation steps

1. Finish T02/T03 against the actual model and request schema: separately represent progress and evidence status, add task-scoped factual prerequisites, preserve real user decisions, and finish normal scope completion without legacy authority dependencies. Include additive/old-state compatibility rather than creating a parallel state store.
2. Complete T04/T05 together: remove review-to-receipt identity coupling and convert the real host/caller paths. Do not fix integration failures by restoring mandatory approval/ticket checks or by making proof validators always succeed.
3. Finish T06-T09 in this PR: compact task packets/HTML, obsolete-prompt and interrupted-work upgrade, generated instructions, package compatibility, and an actual installed-candidate exercise. The full requirements and twelve acceptance scenarios are in the handoff.

## Merge and release boundary

Do not merge or publish this partial conversion. The active host instructions still contain the unwanted workflow, and mixed old/new installed clients have not been qualified. Preserve actual host permissions, explicit user stops/denials, normal repository CI, and publication controls. No package was released and no existing user's project state was migrated.

**Claim-registry delta for subsequent Project maintenance:** product-specific assistive-engine direction is accepted; initial native progress implementation is source-only on this PR; full orchestration, migration, and released behavior remain unverified. Record that distinction without relabeling October 7 evidence or claiming the Project files were replaced.
