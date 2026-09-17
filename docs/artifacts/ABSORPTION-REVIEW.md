# Independent absorption review

Date: 2026-09-16

Reviewed base: `a3d7785f`

Package SHA-256: `4b518d4cf73089ce0adbaca173f96c06380efebc2580f44bae3b471388224372`

## Verdict

The package is suitable to retain as a disabled foundation, not as a complete
feature rollout. The engine and its Linux and Windows persistence paths have substantial
behavioral coverage, the canonical/generated ownership model is now respected,
and required native-host CI is wired. The default remains the legacy Markdown
workflow. HTML farm use remains explicitly blocked.

Full merge readiness is **not asserted**. The blocking work is real host
authority integration, complete producer/consumer closure, HTML farm qualification,
macOS native execution evidence, host-package payload shipping, a selected live
pilot, and observed exact-head hosted CI. Tests,
package progress notes and regenerated examples were used as leads only; each
disposition below was checked against implementation and repository wiring.

## Corrections made during review

- Replaced spec/plan hard-coding in shared engine seams with the compile-time,
  kind-neutral registry in `core/artifacts/internal/kind/contracts.go`. New kinds
  still require closed reviewed contracts; this adds no runtime plugin surface.
- Corrected capability reporting so each supported host reports its actual
  backend; unknown platforms fail closed instead of claiming Linux semantics.
- Corrected the package's claim that safe-integer/string canonical JSON deviated
  from the design. The original design itself rejects floats and unsafe integers.
- Added the missing feature/sprint pilot and resume boundary while keeping the
  normal path on legacy Markdown.
- Removed guidance that falsely implied current host packages contain the native
  binary. The bridge contract is retained, but the pilot is unavailable until a
  verified payload is actually packaged.
- Added a path-scoped, pinned Go 1.27.1 CI matrix for Ubuntu, Windows and macOS,
  including both required merge-gate registrations and an impact-map edge.
- Preserved the architectural decision as an extensible structured-artifact
  engine; no change to ADR-0004 was made or needed.

## Acceptance-criterion disposition

`Local pass` means the inspected implementation satisfies the bounded engine
contract exercised here. It is not whole-feature acceptance when a host,
packaging, release or rollout condition remains open.

| Criterion | Disposition | Independent basis / remaining gap |
|---|---|---|
| AC-001 | Local pass | Captured pre-engine registration sets, byte-bound startup fixtures and negative controls show no public command, agent, persistent tool, top-level skill or eager schema addition. |
| AC-002 | Local pass; semantic approval open | Closed draft/readiness schemas and explicit authority diagnostics exist; schema validity still cannot approve prose truth. |
| AC-003 | Partial | Pair binding, coverage and DAG validation exist; all real plan producers/consumers are not end-to-end qualified. |
| AC-004 | Local pass | Stable allocation, retirement, tombstone and no-reuse behavior are implemented and exercised. |
| AC-005 | Local pass | Canonical HTML reads verify embedded model, generated view, renderer and digests before returning data. |
| AC-006 | Partial qualification | Offline branded rendering passed fresh Chromium desktop/mobile/print/text-growth checks; native multi-browser/accessibility qualification is absent. |
| AC-007 | Local pass; host closure open | Bounded whole-record paging, progress and receipt-bound cursors exist; real host context budgets remain unqualified. |
| AC-008 | Local pass; permission integration open | Typed closed operations keep artifact content inert; every host's actual governed execution boundary is not wired. |
| AC-009 | Linux/Windows pass; macOS pending | CAS, replay, native locking and recovery pass on Linux and Windows. macOS exact-host and network/power-loss guarantees remain absent. |
| AC-010 | Linux/Windows pass; distribution open | Rooted paths and manifest-verified installed-payload selection pass on Linux and Windows; host packages do not yet ship the payload and macOS awaits exact-host CI. |
| AC-011 | Partial | Receipt and transition checks exist, but synthetic capture does not prove actual user/SMARTS/reviewer authority integration. |
| AC-012 | Engine pass; workflow partial | Stale normative bindings are rejected; every resume/dispatch caller has not been converted and exercised. |
| AC-013 | Partial | Named-test and evidence-input checks exist; real runner adapters and complete environment/input closure remain. |
| AC-014 | Engine pass; orchestrator partial | Scope state, reconciliation, stale evidence, interrupted REVIEW resume and atomic acceptance pass against the native candidate; real callers are not qualified. |
| AC-015 | Partial | Canonical feature and sprint entries carry the disabled pilot boundary, and synthetic native-candidate authoring/execution fixtures pass; no complete real-host workflow has run. |
| AC-016 | Partial | Typed scope links avoid Markdown proof for new artifacts; external issue-checkbox coverage remains heuristic. |
| AC-017 | Partial | Advisory discovery and receipt-aware cache invalidation exist; full live hook/cache/dedup qualification is absent. |
| AC-018 | Locally implemented; qualification pending | The minimal current-slice projection, immutable authorization/base binding, actual pre-canary and pre-dispatch guards, provider-only enrichment and exact-byte seal are implemented. Current authority adapters, installed payloads, generated-host/exact-head CI and a fresh model-era matrix remain open, so use stays disabled. |
| AC-019 | Local pass; production conversion open | Loss-aware line mappings and non-transfer of approvals are implemented. An exact-candidate native-Windows pair preview/apply preserved draft and unverified-authority state; no production repository pair has been converted. |
| AC-020 | Local native proof; remaining hosts pending | Linux semantic cutover/rollback and Linux/Windows native storage recovery pass. The exact-candidate Windows pilot restored both legacy files byte-for-byte and removed both HTML authorities. The full Windows semantic suite, macOS exact-host and production-host execution remain open. |
| AC-021 | Partial | Inventory-led search now accounts for live canonical/generated consumers and explicit exclusions, and the no-growth gate passes. Entries marked pending still identify incomplete runtime, host and release integration. |
| AC-022 | Partial | Native builders and verified bridges pass on Linux and Windows. The release-only boundary rejects linked/replaced roots, fake architectures and unsupported identities, requires exact commit/workflow-run/platform/digest/test receipts, and required CI aggregates all three host candidates into package-owned overlays. Linux and Windows cold execution pass from each staged root without Go, PATH or network fallback. The ordinary installer remains fail-closed; actual release-channel application, hosted macOS and published provenance are open. |
| AC-023 | Partial | Named native locking/replacement/process-death suites pass on Linux and Windows, and macOS compiles/vets; macOS exact-host plus physical/network fault evidence remain open. |
| AC-024 | Local engine pass | Strict parser, resource bounds, inert content and renderer checks pass; unqualified host seams prevent whole-feature acceptance. |
| AC-025 | Local pass | Normative/model identities are separated and safe-integer/string canonicalization matches the original contract. |
| AC-026 | Partial | Diagnostics and published guidance are explicit, and the recorded rollout decision keeps legacy behavior as the default. All-host cold-install and production resume behavior remain unproved. |

## Implementation-task disposition

| Task | Disposition | Independent basis / remaining gap |
|---|---|---|
| T-001 | Implemented locally | Owned inventory, independent search, public-surface/startup negative controls, generated-path accounting and required CI wiring pass. This records, rather than conceals, downstream integration gaps. |
| T-002 | Local pass | Spec and plan model/schema versions, compatibility reads and generated parity exist. |
| T-003 | Local pass | Strict decoding and separate hashes reject duplicates, invalid Unicode, floats and unsafe integers. |
| T-004 | Local pass | Structural/readiness and typed intent validation exist; natural-language correctness remains review authority. |
| T-005 | Local pass | Binding, paths, coverage, dependency order and verification definitions are validated. |
| T-006 | Local pass | Durable allocation, update, retirement and marker correspondence are implemented. |
| T-007 | Local pass | Deterministic static rendering and strict parse/view verification are implemented. |
| T-008 | Partial qualification | Safe local branding and Chromium checks pass; broader browser/accessibility qualification remains. |
| T-009 | Local pass | Exact/outline/context reads, cursor binding and forward progress are implemented. |
| T-010 | Linux/Windows pass; macOS pending | Descriptor/root-handle containment, no-follow rejection and locked CAS pass on Linux and Windows; macOS exact-host evidence is pending. |
| T-011 | Linux/Windows pass; macOS pending | Native replace/journal/process-death recovery passes on Linux and Windows; macOS is compile/vet-only locally. |
| T-012 | Local pass | Closed bounded CLI protocol and inert mutation operations exist without a public registration. |
| T-013 | Partial | Approval/rebind checks exist; real host authority capture mappings are incomplete. |
| T-014 | Partial | Task/evidence/resume state exists; real host checkpoint orchestration is incomplete. |
| T-015 | Locally implemented; host qualification pending | Canonical producer guidance and bridge calls create/read real HTML pairs, preserve incomplete drafts and fail closed without the payload; full generated-host execution is unproved. |
| T-016 | Partial | Native-candidate fixtures cover dispatch, stale blocking, interrupted REVIEW resume and atomic scope acceptance; real feature/sprint entry traces remain incomplete. |
| T-017 | Partial | Candidate discovery/cache/capability integration exists; live host suites remain. |
| T-018 | Locally implemented; qualification pending | Projection, binding, durable downgrade marker, authorized enrichment, exact-byte/provider seal and shared runtime guards have fresh local fixtures. Real authority, packaged-host, hosted-CI and current mixed-model evidence are still required. |
| T-019 | Local pass | Review-only loss-aware import is implemented; a selected production conversion remains. |
| T-020 | Linux/Windows pass; macOS pending | Recoverable pair cutover and guarded rollback pass on Linux and Windows; macOS exact-host execution is pending. |
| T-021 | Locally implemented; release qualification pending | Linux and Windows native build/bridge checks pass. The reviewed release-only copier pins its roots, rejects fake architecture and unsupported identity, and accepts candidates only with independently supplied exact-host qualification receipts bound to the protected CI identity. Linux and Windows cold execution pass from all three staged host roots without a child build or runtime fetch. The ordinary installer intentionally fails closed. Actual release-channel application and published provenance proof remain absent. |
| T-022 | Partial | Required three-host CI runs named native, bridge, package and cold-install checks, emits qualification receipts only after cell success, and feeds a separately required aggregation/cold-execution job; hosted exact-head results remain absent. |
| T-023 | Locally implemented; hosted qualification pending | The reviewed draft pair is byte-pinned and reproduced through the current protocol. Go checks cover pair bindings, coverage/DAG/checkpoints, marker/DOM integrity, identity-domain behavior and hostile inputs. A separate Python stdlib serializer verifies pinned current-schema normative/model/render identities, while a real task-start transition verifies revision/model advancement without normative drift. The orchestrator requires exact reviewed test membership and applicable non-skipped results from the 41 reference cases and all bridge, authoring, workflow, farm and package cases, revalidating the same candidate manifest/binary identity before and after each suite. Windows orchestration and Windows/Linux Go test, vet and Linux race execution are fresh and green; required three-host CI runs this gate before qualification. Hosted Linux/macOS exact-head results remain open; this is not farm-promotion evidence. |
| T-024 | Locally implemented; rollout and host qualification pending | The two required guides and directory/tech-stack integration describe implemented behavior, offline review, capability diagnostics, migration/recovery and unsupported cells. A clean-commit native-Windows candidate is bound to manifest/binary digests and embeds canonical receipt/event bytes plus transaction identities for pair conversion/rollback and synthetic-authority new-feature execution through process recreation, reconciliation to PENDING, redispatch, REVIEW and atomic acceptance. The explicit evidence-backed decision remains no default cutover and no mass migration; typed HTML and HTML farm use remain disabled. |

## Fresh evidence

- Go 1.27.1 Windows/amd64 official archive, SHA-256
  `a3911b5e0e1b1053f25ed0675f4c1c6aad1e2bfcf253df2b9be4caabd2edd95d`:
  `go test -buildvcs=false ./...`, `go vet -buildvcs=false ./...`, all eight
  named native storage/recovery tests and the native bridge cases passed. The
  package suite confirms that the Windows developer installer fails closed and
  that the release-only builder rejects linked/replaced roots, candidate-only
  qualification claims, fake native headers and unsupported versions before it
  cold-executes the package-owned binary from all three staged host roots without
  invoking Go or any child build process. A production dependency/source guard
  rejects network-capable Go packages, unreviewed third-party packages and direct
  network syscalls before that no-network-fallback claim is accepted.
- Go 1.27.1 Linux/amd64 official archive, SHA-256
  `63d339f0da5ab53635a56f2490a7984dfe12dfcff22ad749f63edaf590168445`:
  all 17 package checks passed, including cold execution from all three staged
  roots and the deterministic linked-ancestor swap race. The temporary WSL
  toolchain was removed after the run.
- Fresh Windows native-candidate authoring/workflow fixtures: 3/3 producer cases
  and 5/5 execution/resume cases passed. They use synthetic cooperative events
  and therefore do not claim production authority integration.
- Fresh Windows farm fixtures: the three exact named Go contracts plus the
  ordered two-task pending-dependency case and authorization/refresh/seal adversarial cases passed; 7/7 native-candidate integration
  cases passed for base binding, canary preflight, provider-only enrichment,
  full-byte/provider sealing, stale-source rejection, durable downgrade blocking,
  parsed-byte digest matching, linked-install rejection and the real built dispatcher
  blocking an unbound HTML plan before `.farm`, worktree or network side effects.
  These synthetic cases do not qualify any model or promote the backend.
- Go 1.27.1 Linux/amd64 official archive, SHA-256
  `63d339f0da5ab53635a56f2490a7984dfe12dfcff22ad749f63edaf590168445`:
  test, vet and `go test -buildvcs=false -race ./...` passed.
- Real Linux installed-payload bridge: 8/8 tests passed, including tamper,
  binary symlink, linked-directory, inert-content and empty child-environment cases.
- Mandatory auth/crypto review passed with no findings after replacing the
  repository-local HMAC key with content-addressed cooperative delivery receipts;
  forged-but-unstored receipt digests fail closed and the same-user trust boundary
  is explicit.
- Mandatory native storage/package security re-review passed with zero findings
  after descriptor-relative Unix installation, pinned release staging on Unix and
  Windows, exact-host qualification binding, architecture validation, Windows
  developer-install fail-closed behavior, and linked/replacement regressions.
- Original design reference: validator reports 26 criteria, 24 tasks and six
  checkpoints; 41/41 fresh reference regressions passed. It correctly remains
  draft, execution-ineligible and authority-unverified.
- Fresh Windows cross-kind conformance: 6/6 orchestration checks passed. The
  named Go conformance test imported the reviewed normative pair through schema
  0.3.1 and verified bindings, bidirectional coverage, DAG/checkpoint membership,
  markers/anchors, renderer round-trip and digest-domain behavior. A separate
  Python stdlib serializer matched the pinned current-schema normative, model and
  rendered-byte identities, and a real task-start transition preserved normative
  identity while advancing revision/model identity. The same candidate manifest
  and binary identity was revalidated around every subordinate suite, whose exact
  reviewed test membership and applicable non-skipped outcomes were enforced.
  The old reference
  harness now writes explicit UTF-8/LF fixtures on Windows; reviewed artifact
  bytes and the production format were not changed.
- Fresh exact-candidate native-Windows T-024 pilot: clean commit `2ea35d02` reproduced the
  release manifest `88310faf63984ad1a092002414be17ce1d50cf70c2a07ef4209e89a3558462f9`
  and executable `daf464c0d9bdea9ce363268b262f00ef8fba0abf9ebebb5a0c8969c483625fbe`.
  A selected legacy pair produced a digest-bound preview, applied with a
  fixture-supplied mapping-review attestation bound to that preview digest,
  remained draft and authority-unverified, transferred no approval, and rolled
  back to the exact original bytes while removing both HTML authorities. A
  separate new-feature fixture rejected draft dispatch, used synthetic workflow
  receipts, observed persisted `IN_PROGRESS` after process recreation, reconciled
  to `PENDING`, redispatched with fresh context and completed review plus atomic
  scope acceptance. This is fixture evidence, not a production-host
  authority or comparative model-performance result. Exact observed fields and
  limitations, canonical receipt/event objects and transaction identities are
  retained in `docs/artifacts/T024-PILOT-EVIDENCE.json`. This is exact local
  fixture evidence, not an independently signed CI receipt or production
  authority trace.
- Browser review with Chrome 152.0.7977.82 passed the spec and plan at 1440 px
  and 390 px, with JavaScript disabled, local-only requests, doubled text,
  mobile table of contents and print disclosure.
- Pi tooling: typecheck passed; 863 tests passed with one intentional skip;
  build, 45 package tests, 26 parity tests and 13 public-doc tests passed.
- Canonical/generated parity: `sync-core --check`, `build-surface --check`,
  `build-host-packages.py --check`, artifact type generation, 18 descriptor
  tests, 65 surface tests, 145 Codex resource tests (one skip), 195 read-inject
  tests, 18 pre-read checks, 18 recorded-intent tests, four command-catalog
  tests, plugin reference closure and 77 CI-impact tests passed.

## Remaining blockers before full merge readiness

1. Qualify the locally implemented AC-018/T-018 path through real authority events,
   installed host payloads, generated-host/exact-head CI and a fresh frontier/low-tier
   model matrix. The promotion bar starts at zero and gives the June 2026 run no credit.
2. Complete real authority-event adapters and full producer, consumer, resume,
   context, status and doctor closure on every generated host.
3. Obtain exact-host macOS storage, recovery, bridge and cold-install results;
   preserve the declared lack of physical-power-loss/network-filesystem proof.
4. Package provenance-bound, checksummed native binaries into each release target and run
   cold-install and restore drills; no normal installation can use the pilot yet.
5. Run a selected production-repository conversion and full real-host interrupted
   workflow trace; the disposable T-024 fixture does not establish those claims.
6. Obtain exact-head hosted CI results for the new three-host matrix and all
   existing required jobs, then satisfy normal version/changelog/release policy.

Until those items are closed, legacy Markdown remains the default, HTML use is
explicit opt-in only after a payload exists, and HTML farm use remains disabled.
