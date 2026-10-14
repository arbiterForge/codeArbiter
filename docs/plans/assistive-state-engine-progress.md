# Assistive state-engine overhaul: implementation progress

**PR:** #983, `overhaul/assistive-state-engine` -> `main`.
**State:** DRAFT; fifth implementation slice under verification, not the completed overhaul or a released package.
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
| T05 | Main execution instruction path converted | Native writer/drafting plus canonical feature, sprint, brainstorming, TDD, batch coordination, subagent implementation, and commit/PR handoff now describe assistive execution instead of artifact approval ceremonies; generated into Claude, Codex, and Pi. Obsolete host hook/adapter pending-request cleanup and installed behavior still need work. |
| T06 | Compact task packet implemented in native source | Read-only `task-context` delivers one task, directly cited criteria, dependencies and scoped prerequisites without source snapshots/receipt chains, with stale-model and size-limit refusal. Complete installed-host/token-cost qualification remains. |
| T07 | One interrupted-prompt recovery path implemented | Unanswered legacy reconciliation prompts can be superseded without a code after route binding and no-attempt checks; actual in-flight mutations still require exact replay. Pending approval/prerequisite conversion, mixed-client upgrade, rollback and installed-host qualification remain. |
| T08 | Main execution and adapter surfaces regenerated | Schema 0.3.2, candidate metadata, bridge/builder and farm bundle remain synchronized. The historical atlas now binds sixteen exact fifth-slice owner blobs; final public claims/Academy/mixed-host qualification remain. |
| T09 | Focused evidence collected | Native tests and source checks below are not final installed-candidate or publication qualification. |

Continue in this same PR. Do not create a second overhaul branch or mark this slice ready to merge.

## Sixth slice: routed-agent mutation test and unanswered prompt recovery

**Starting development commit:** `541540957b0d78a86d9fdd2218667cb644803ea2`;
this is not a released package. The existing Mac hook job failed on an old
mutation fixture that inserted a generic agent link into the now-retired
compulsory `subagent-driven-development` route. Its replacement targets the
real optional `dispatching-parallel-agents` route and still demonstrates
that unsupported `<role>` agent names are rejected. All 23 routing/index
parity tests pass locally; no missing-route check was disabled.

The reconciliation host helper gains `--supersede --reason` for an
unanswered previously armed user-reconciliation prompt. The existing locked
pending reader, registered prompt binding and durable attempt lookup are
used; no new authority or persistence service is introduced. It refuses
different identities, invalid/overlong reason strings, missing or wrong
route bindings, dual legacy/admin markers and in-flight operation attempts.
It removes only the unanswered prompt and reports a superseded
**non-authority** disposition. It does not manufacture verified acceptance,
touch the actual task's BLOCKED state or delete receipts. If an attempt
already exists, its exact operation ID and receipt must be recovered using
the existing replay path. The old exact-prompt cancellation remains for
historical inspection/compatibility; normal receipt-free task progress
needs neither operation.

Canonical protocol and artifact documentation will describe this bounded
recovery. Only the three generated adapter copies of the owning Python
sources will be updated, with no new slash command or changed released
version. Full T04 subject-scoped command-result applicability, other
legacy pending marker categories and T07 mixed-client rollback remain
material work; they are not silently inferred from this narrow repair.

### Sixth-slice verification

| Check | Local observation and limitation |
|---|---|
| Routing/index parity | **23 passed**, including the moved negative-control fixture against the actual optional Codex generic agent route. The prior Mac CI failure had targeted a route intentionally removed by the assistive overhaul. |
| Legacy reconciliation adapter | **52 passed** on Windows after the seven new unanswered-prompt supersession and CLI tests. Cases cover ordinary cancellation, exact replay after a lost response, in-flight refusal, current/legacy ambiguity, invalid route binding, cross-session behavior, and lock ordering. Tests use isolated Git fixtures and the real native candidate where the preexisting suite requires it; they are not a model-backed installed-host session. |
| Generated surfaces and references | **147 generated-surface tests** with one existing skip; **53 routing/cleanup tests**, **18 consumer-closure tests**, and **22 host-descriptor tests** passed. The canonical Python bridge matches its three generated adapter copies and the canonical Markdown surfaces match their three projections. |
| Package/ADR consistency | Root Pi metadata parity and host-package generator `--check` passed. ADR identity and lifecycle checks passed; no historical acceptance was upgraded to verified evidence. |
| Hosted CI status | At the starting head `541540957b0d78a86d9fdd2218667cb644803ea2`, documentation deployment passed and the Mac hook contract failed on the obsolete agent-link mutation anchor. Other structured-artifact jobs were still running at inspection. A subsequent head must be checked independently; no green CI claim is inferred from local tests. |

No prompt was auto-approved, no old receipt or source was deleted, and no
consumer project was migrated. This is a specific in-flight-safe retirement
operation, not a sweeping approval/prerequisite cleanup or an engine rewrite.

## Fifth slice: CI contract correction and compact context

**Starting PR head:** `049cc775128eb4bb00950e88481d242c196e8495`.
**Development-only status:** changes in this slice must not be represented as
released or installed-host verified until the exact candidate has been built,
CI has passed, and a supported installed host has been exercised.

The previous hosted checks failed because current execution instructions had
removed duplicate artifact approvals but historical test assertions still
required the removed phrases and a compulsory reviewer sequence. The corrected
prose tests keep **real** recorded-intent protections: explicit user decisions
outweigh older records, ADR contradictions need a visible consequential choice,
and actually deferred outcomes are not silently resurrected. Missing optional
plan/decision indices remain fail-soft and do not become user permission gates.

The static conformance suite retains an explicit, exact test-name inventory;
its renamed authoring/workflow cases and new positive tests are reflected in that
inventory. Golden native-rendered spec/plan hashes were independently rederived
from the installed development binary with schema 0.3.2; the old schema 0.3.1
historical capture was **not** relabeled. The strict identity and renderer-drift
assertions remain. No check is made to return success for all inputs.

The C02/C04 site comparison data retains its older reviewed source quotes as
historical evidence, with separate current source references and explicit
historical qualification. Active HTML guides display that difference rather
than implying the old receipt-approval protocol is still the new default.
Windows `core.autocrlf` previously rewrote the old captured HTML example's
checked-out LF bytes to CRLF and made an exact SHA-256 check fail. Narrow
`.gitattributes` entries now preserve that example's original HTML bytes on
Windows, without modifying its historical digests or relaxing the byte check.

**Next T06 implementation:** native read-only `task-context` returns a compact
source-bound task packet with its directly referenced criteria, relevant
actual dependency states, scoped prerequisite observations, and explicitly
unscoped legacy prerequisites. It returns `assessment: advisory` and
`evidence_assessed: false`, not approval or a current passing-test claim.
The model digest is checked against the current plan. A changed source binding
is visible. A packet too large for the declared budget fails without returning
partial data. It does not snapshot source files, launch a reviewer, execute a
command, mint an authority ticket, or create a second state store.

The canonical implementation skill recommends this packet for normal HTML work,
with bounded exact/batch symbol reads on older installed packages. The operation
is an internal native API addition, **not** a new public slash command. It uses
the existing packaged Go/Python bridge, and generated host surfaces stay derived
from their canonical owner. This is development-source behavior until the final
coherent package/host checks close.

### Local focused evidence for this slice

- The pre-existing missing-permission conformance fixtures were kept strict;
  current suite membership was checked against Python test ASTs for all five
  exact candidate scripts. Renamed positive behaviors now have named tests;
  old assertion-only permission refusals were not silently counted as passes.
- `test_recorded_intent_surface.py`: **18 passed**. The actual deferral,
  supersession, contradiction, index-fail-soft, and intent-parser rules are
  retained, while irrelevant approval phrases are no longer required.
- `test_command_catalog.py`: **5 passed**, preserving exact catalog routing
  and recovery wording without demanding artifact approval for ordinary work.
- Five targeted documentation suites (`model`, `workflows`, `concepts-decisions`,
  `human-experience`, and `workflow-propagation`): **62 passed** on Windows.
  Those assertions distinguish historical source quotes from current defaults.
- Seven new native `TestTaskContext*` scenarios pass on Windows, alongside the
  existing assistive and closed-schema tests. They cover referenced criteria,
  scoped/unscoped prerequisites, real stops, dependency states, stale identities,
  bounded-output rejection, and avoiding full-source snapshots/authority files.
- The checked-in saved-search example's two native HTML blobs now match their
  unchanged historical SHA-256 records exactly on Windows. Narrow LF checkout
  rules repair the byte instability instead of falsifying the old provenance.
- `tools/build-surface.py --check` and `tools/sync-core.py --check` pass:
  canonical instructions and the Python bridge match their generated copies
  across Claude, Codex, and Pi. These do not establish live host qualification.

### Fifth-slice verification boundaries

| Check | Result and limitation |
|---|---|
| Native Windows Go module | The full 15 tested packages passed on the initial fifth-slice native implementation, with other packages having no tests; after adding the three missing task definition fields to the packet, the focused task-context/assistive/schema-closure suite passed again. This is not a new full-module run against the exact final PR head. |
| Rebuilt native development candidate | Windows/amd64 `ca-artifact` built with Go 1.27.1, local SHA-256 `5bcff62b25b6959ed3e36b375f11808b58795c454a1e8f257f996230f0c85ee5`. The builder reports `module_tests_passed: true` and `upstream_host_qualified: false`. This is a local fixture, not distributed bytes or a live host. |
| CLI bridge | Seventeen tests passed against that development candidate; adding task-context did not change the bridge's historical authority restrictions for explicit proof consumers. |
| Authoring contract correction | The first full authoring run had two failures from tests expecting every caller to duplicate the same Markdown/HTML boilerplate. The owner include and feature entry retain strict fallback checks; sprint and brainstorming are tested for correct delegation. The corrected five-test contract class now passes. Full authoring rerun is tracked by conformance and must not be assumed green. |
| Recorded intent and catalog | Eighteen and five tests respectively passed, with consequential decisions and deferral provenance checked rather than artifact approval codes. |
| Current-versus-historical documentation | Five targeted site suites: 62 passed. The documented saved-searches HTML capture retains its original digest and has platform-stable LF checkouts. |
| Atlas/source fidelity | Sixteen current owner blobs at exact commit `b8db5f4e5301e02feeb9c5aee06daa86cbdd595b`, with the previous geometry marked historical. Complete site generation, TypeScript typecheck and diagram audit passed; 65 atlas/source tests passed. The two source-derived feature/sprint SVG descriptions now identify the retained geometry as historical; all other diagram content is unchanged. Generated SVG LF checkout is stable across platforms. No new live website deployed. |
| Python adversarial conformance | First local run found missing `jsonschema`/`referencing` only in the temporary Windows test environment, plus the now-corrected redundant authoring assertion. The original reference suite correctly failed to run without its pinned requirements. An isolated virtual environment is being used for the full rerun; do not count the first failure as a native-engine regression or the second attempt as passed until its result is captured. |

The source correction stays **one draft PR**. The full T04 impact-aware applicability,
T07 pending-prompt/mixed-client recovery, complete low-token workflow measurement,
and actual installed host/upgrade qualification remain open. A local synthetic
fixture cannot establish the prompt/model behavior of the distributed package.

Results belong to the specific execution and candidate; local fixture success
is not independent model-backed host evidence. The final Windows Go module run,
rebuilt development payload, Python bridge/conformance suites, and hosted CI are
tracked here or in the PR when completed. Do not silently replace earlier
historical verification with this attempt.

## Fourth slice: ordinary execution callers (source candidate)

**Source status:** Implemented in the draft PR, **not** live-host qualified or released. Exact commit and hosted CI state are recorded in the PR after publishing the branch.

The canonical `/feature`, `/sprint`, `brainstorming`, `executing-plans`, `subagent-driven-development`, TDD entry boundary, and the ordinary commit/PR handoff now use the implemented assistive model rather than requiring a second artifact approval conversation. A plan remains useful and mandatory for its full-lane workflow, but the spec can be a working draft. Existing in-scope implementation changes do not require digest-bound replies, a per-task author/reviewer fleet, or a reviewer replay just because test receipts changed.

Task selection uses `eligible` as advice, actual task dependencies, and scoped factual observations. `task-review` without receipts reports implementation readiness; `accept-scope` without receipts records `DONE`, not proof of testing. Unknown/failing tests remain visible; review follows real risk. Interruption handling inspects current work and respects CAS/replay, active workers, `BLOCKED` states and actual user denials. No tool permission, security, irreversible-operation, secrets, commit, merge or publication authorization is granted by these changes.

The canonical route/skill indexes and the complete generated Claude, Codex and Pi surfaces have been regenerated. Old contracts requiring artifact authority were replaced in their targeted regression suites with positive checks that real host controls and safe progress distinctions remain. The first CI failure on the prior commit was an obsolete prerequisite surface assertion; the source now checks that ordinary task-scoped observations require no legacy prompt adapter, while the historical attestation adapter's own negative tests are retained. The docs assertion likewise distinguishes Pi's native writer/ordinary progress from unqualified historical verification/review authority.

**Local verification performed during this slice:**

- `test_routing_and_cleanup_surface.py`: 53 passing tests after updating policy-bound assertions.
- `test_build_surface.py`: 147 tests, one existing skip, passing after preserving the exact changed Codex charter route count and replacing the obsolete fixed PR preflight assertion with checks of real authorization/hosted-CI boundaries.
- `test_artifact_workflow.py ArtifactWorkflowResolverTest`: 12 passing tests for canonical format, resumed tasks, advisory state, separate explicit evidence, and commit/PR rules.
- `test_artifact_consumers.py`: 18 passing tests for resource closure.
- `tools/build-surface.py --check`: passed after regenerating all three host projections.
- Full native-builder-dependent Python workflow/authoring/prerequisite suites were attempted concurrently but did not complete in the bounded local exercise; do **not** count them as passes. Run them on the current exact head in CI and investigate any failures. A local Windows docs test also hit the existing captured-product-example digest mismatch; do not alter that historic capture to force green.

**Unresolved:** actual installed-host /feature and /sprint canaries, old armed prompt retirement and recovery, ordinary command/result recording with scoped freshness, complete cross-surface site/public explanation, upgrade and rollback. The route atlas remains historical. A fourth-slice follow-up now binds fifteen affected canonical owner blobs to exact source commit `24845e8ff72b96236436221f0cea22f6f4ea3e27`, keeps the October 7 geometry and historical source links, and visibly distinguishes the new assistive execution paths from the old approval arrows. Local `npm run gen:atlas`, site TypeScript typecheck and 64 targeted atlas/revalidation tests pass. The full site/docs deployment, live rendered origin and completed workflow remain unverified. Do not merge this partial version.

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

### Third-slice documentation follow-up

Hosted docs generation on native commit
`6fe7f45a18daa547525b8c1b5f0585750916b1ea` stopped because the atlas correctly
detected changed artifacts-owner bytes. The release-applicability generator had
completed; the failing child was `gen:atlas`, not release classification.

The follow-up does not claim that old permission diagrams now describe the
finished overhaul. Original geometry, source links, and historical review records
remain intact. A visible partial-implementation notice identifies the retained
October 7 routes as historical and describes the actual authoring/progress and
bounded review-rerun changes. Affected node details, the reading guide, standalone
HTML/SVG labels, and source-ledger export carry that distinction. Four current
owner blobs are checked against their actual committed bytes; later source drift
still fails rather than silently substituting main or relabeling old evidence.

Verification: the complete `npm run gen` pipeline, including release-applicability,
atlas, 17 standard diagrams, and diagram audit, passes. TypeScript typecheck passes.
All 53 targeted atlas/source-revalidation/model tests pass on Windows with one
worker. Initial parallel/serial attempts hit the existing five-second limit in
redundant whole-fixture source reads; the shared positive fixture check is retained
once and every exact drift-rejection assertion remains. No timeout or assertion
was waived. New tests cover the visible historical/current distinction, exact
source identities, preserved geometry, export parity, invalid references, and
escaping. Full Astro/browser execution and the next hosted docs result are not
claimed by these checks.

The existing pinned Academy submodule was initialized only in the temporary
checkout to run the site's normal generator. Its pin and remote repository were
not changed. Standard generated diagrams had no substantive tracked changes and
are not republished as newly reviewed routes. Remaining execution/hook conversion
and the final coherent route update stay in this same PR's T05/T08 work.

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

1. Finish T05/T07 pending host adapters: inspect/retire old armed approval, prerequisite and reconciliation prompts without losing historical receipts or interrupting active operations; verify actual host hook behavior. The main canonical sprint/feature/task execution path is now converted.
2. Complete T04 ordinary command/result and subject-scoped applicability plus T07 interrupted-operation, mixed-client upgrade, old markers and rollback after later edits. Neither instruction tests nor a native schema reader proves the installed workflow.
3. Finish T06-T09 in this PR: compact task packets/HTML, obsolete-prompt and interrupted-work upgrade, generated instructions, package compatibility, and an actual installed-candidate exercise. The full requirements and twelve acceptance scenarios are in the handoff.

## Merge and release boundary

Do not merge or publish this partial conversion. The main host instruction path is updated, but obsolete hook/pending-request protocols, some advanced/farm callers, and mixed old/new installed clients are not fully qualified. Preserve actual host permissions, explicit user stops/denials, normal repository CI, and publication controls. No package was released and no existing user's project state was migrated.

**Claim-registry delta for subsequent Project maintenance:** product-specific assistive-engine direction is accepted; native progress, scoped prerequisite observations, and batch completion are source-only on this PR; full orchestration, migration, and released behavior remain unverified. Record that distinction without relabeling October 7 evidence or claiming the Project files were replaced.
