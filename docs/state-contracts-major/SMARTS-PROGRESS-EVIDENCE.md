# Native-engine implementation handoff and SMARTS discussion packet

## Status, authority and scope

This is a proposed implementation corpus for the receiving CLI agent. It is not a record of implementation, a completed test run, an accepted architectural choice, or a released behavior claim. The development source inspected is **arbiterForge/codeArbiter@fd7eb34b2da439551443d09526ab48fd1d1bb9bf**. Rebase the evidence against the integration branch's actual starting commit before coding; retain a delta if that commit differs.

The user has decided that unresolved conflicts hold only dependent work, corrected debug/reviewer submissions can be resubmitted, Pi child authors need supported scoped parent delegation, and interrupted workflows need durable recovery while ordinary work remains nonblocking. Those decisions are implementation inputs. The representation and migration of progress versus evidence remains **open for B and the CLI agent**. No decision-log entry, selected SMARTS option, approval, receipt, or accepted ADR for that open choice is created by this packet.

All implementation, generated derivatives and tests stay on the separate integration branch until the whole authorized change is implemented and tested; the eventual delivery is a new major release. This packet does not choose the branch name, release number, tag, or publication time. Root handoff owns those integration and release obligations.

Native scope includes findings **N-F01 through N-F10**, the native side of corrected reviewer attempts, and the storage interface supporting Pi interruption recovery. The original audit's **39 native machine families and 173 native transition rows** remain the behavioral baseline; the final whole-repository inventory contains 287 families and 1,748 rows. The native task ledger accompanies this packet in native-tasks.json. Prior audit evidence is in audit-work/native.json; the launch-binding producer probe is audit-work/probe_launch_binding_results.json.

## What current code actually does

| Surface | Inspected behavior | Implementation consequence |
|---|---|---|
| Ordinary progress | recordWork changes progress with CAS/replay and preserves evidence references; receipt-free task-review records REVIEW as implementation reported ready. | Retain autonomous ordinary progress. REVIEW alone is not a verification or review event. |
| Strict review | progress routes receipt-bearing requests through guards, snapshot, prerequisites, exact verification/review binding, then also writes REVIEW. | Preserve the explicit evidence-consuming path and historical receipts; expose its basis distinctly. |
| Scope completion | Receipt-free finishScope records DONE; strict acceptance records ACCEPTED. | A completion label must identify what was actually claimed. |
| Dependency invalidation | task-block writes BLOCKED and traverses dependents, changing non-PENDING/non-BLOCKED states to STALE. Receipt-free reconcile leaves dependent progress unchanged; its advice still follows transitive dependencies. | Do not call this one uniform state machine. The proposed change to propagation is intentional semantics, pending the representation discussion. |
| Check history | Reported checks are bounded in the live model, retain source/outcome, and keep older states through journal before-images. Applicable later failures remain visible. | Never translate progress, a reported pass, or a stale receipt into independently verified success. |
| File recovery | Run and Commit reject ordinary canonical operations while a prepared multi-file journal remains. Recover preflights targets, stages and backups; replay returns the original durable result. | Reuse this integrity mechanism. Do not remove its global pending guard to implement scoped semantic conflicts. |
| Corrected reviews | Authority-bearing native review results admit pass only; the producer review contract includes changes_requested. Profile/launch/context/target/contract/coverage are bound. | A corrected attempt is a fresh observed submission, not mutation of a rejected observation into pass. |
| Compatibility | Current schema 0.3.2 accepts old compatible records; old 0.3.1 clients refuse upgraded models. The existing mixed-schema test preserves complete-store backups and later writes. | Backward read is not universal downgrade. Preserve the distinction and extend the exact-client matrix. |

Evidence owners: SRC-PROGRESS, SRC-DEPENDENCY, SRC-CHECKS, SRC-RECOVERY, SRC-REVIEW and SRC-COMPAT below. This table describes source, not a native runtime result: Go was unavailable in the audit environment.

## SMARTS decision to discuss with B

### Context envelope and recorded intent

**Decision:** What should own recorded work progress, assessment of evidence, and dependency readiness in the native plan model, and how should existing overloaded records migrate?

**Scope and horizon:** The next integrated major release of this file-backed engine and its existing Claude, Codex and Pi consumers. No database, service, general policy language, new permission broker or replacement public command is proposed.

**Current scale:** The code bounds artifact symbols at 8,192, recent task checks at 16 per task, and individual contextual responses. No measured future history volume, read/write rate or acceptable latency was supplied. That missing workload is disclosed below; it is not an excuse to add a speculative distributed architecture.

**Failure expectation:** Preserve stable IDs, reasons, real user stops, actual negative results, CAS, journal before-images and exact replay. An unavailable evidence input must produce an honest unassessed/unknown result while unrelated authorized work continues. A known pending multi-file transaction remains an integrity dependency for its canonical store until reconciled.

**Trust boundary:** security-controls.md defines cooperative same-user integrity, host-owned permissions, preserved user denials, inert stored content, bounded paths, and no fabricated attestations. A digest is not a grant. Neither a progress field nor an assessment field grants permission.

**Intent result: constrains.** The user's current explicit decisions control. ADR-0043 already requires progress/evidence separation and dependency-scoped waiting, while preserving typed state and recovery. ADR-0037 supports closed per-kind contracts in a small shared file kernel. Neither selects the concrete representation below. ADR-0004's no-database principle remains compatible; its literal “no schema layer” and “no transactional guarantees beyond append-only files” no longer describe the inspected implementation. Its historical wording must not veto safe typed migration.

### Three plausible options

**A — Compatibility overlay.** Keep the existing persisted task labels and mutation branches. Add a single explicit read projection identifying reported progress, dependency advice, evidence basis and uncertainty. Legacy STALE stays legacy STALE; do not fabricate its lost prior progress. This minimizes format changes and retains old-client behavior, but the storage still combines different meanings. It is a credible low-migration option, with a lasting explanation cost.

**B — Independent recorded progress; evidence applicability derived from its real inputs.** Version the task representation so implementation progress and explicit stop information are not overwritten by evidence/dependency invalidation. Keep observations and receipts immutable. Derive each assessment from the selected observation, its origin and subject, relevant current inputs, and known conflicting results. Read projections expose dependency readiness separately. Any performance cache is a disposable projection keyed to all assessed inputs, never another authority. The exact field names and enum labels must be settled in the approved design; no invented wire format in this packet is preapproved.

**C — Independent progress plus persisted assessment state.** Version the representation with independent progress and explicit stored assessment records. Each assessment includes the exact observed basis, as-of identity/time and evidence references. Relevant mutations update or invalidate these assessment records through explicit events. Readers can display the last known assessment when inputs are unavailable, but must label it as historical rather than current. This gives consumers an easy stable snapshot and clear assessment history, at the cost of more writes, invalidation paths and opportunities for a stored assessment to outlive its basis.

All three must obey the user's already-decided dependency scope, resubmission and interruption requirements. A is an alternative for representation, not permission to impose a whole-project semantic stop. B and C are alternatives for facts and projections, not authority expansions.

### Full six-lens comparison

The cells below judge the proposed designs under the stated constraints. They are not measurements or claims that any proposal is already implemented.

| SMARTS lens | A — Compatibility overlay | B — Independent progress, derived assessment | C — Independent progress, persisted assessment |
|---|---|---|---|
| Scalable | Unknown. missing_observation: target history volume and read frequency; decision_critical: false. | Unknown. missing_observation: target history volume and read frequency; decision_critical: false. | Unknown. missing_observation: target history volume and read frequency; decision_critical: false. |
| Maintainable | Adequate. One read projection clarifies consumers; overloaded writes and legacy explanations remain. | Strong. One persisted progress fact and immutable evidence prevent competing mutable truths. | Adequate. Explicit assessment records simplify readers but add invalidation owners across every relevant mutation. |
| Available | Strong. No task-format cutover; existing readers retain their current access. | Adequate. Progress survives missing evidence; new readers must handle legacy and unassessed inputs during migration. | Adequate. Historical assessments remain readable offline; current claims still require their basis and compatible readers. |
| Reliable | Weak. STALE still overwrites progress; the projection cannot reconstruct an unknown prior state without evidence. | Strong. Relevant-input assessment preserves progress and history without persisting another freshness truth. | Adequate. CAS protects assessment writes; stale stored conclusions require explicit invalidation and current-basis checks. |
| Testable | Adequate. Existing fixtures remain useful; every legacy branch still needs interpretation tests. | Strong. Progress transitions and pure assessment cases compose with existing CAS, failure-history and recovery fixtures. | Adequate. Explicit events are deterministic, but every mutator and interruption boundary must preserve assessment invalidation. |
| Securable | Indifferent. All options retain host permissions, immutable observations, scoped denials and closed decoding; progress never grants authority. | Indifferent. All options retain host permissions, immutable observations, scoped denials and closed decoding; progress never grants authority. | Indifferent. All options retain host permissions, immutable observations, scoped denials and closed decoding; progress never grants authority. |

**Precedent:** DECISION-0064 / ADR-0037 favors shared mutation/recovery mechanics with closed kind contracts (Maintainable, Reliable, Securable, Testable). DECISION-0076 / ADR-0043 is an explicit owner correction separating progress from evidence, not a scored precedent selecting B or C. No prior decision among A/B/C is asserted.

**Provisional recommendation: B. Strength: moderate. Status: pending B discussion.** Maintainable and Reliable favor one progress fact plus immutable evidence and derived applicability. A has a concrete availability/compatibility advantage during rollout. B's migration must preserve ambiguous legacy state rather than pretend that it can recover erased progress. C remains plausible if the receiving implementation demonstrates that a persisted assessment record materially improves offline orientation or bounded read cost without becoming a second freshness authority. No Strong-cell counting or invented numeric weighting is used.

The scale Unknown is non-critical at present because no workload or SLA has been established that selects one representation; all options remain bounded, local, file-backed designs. Measure representative large histories during implementation and reopen the comparison if the result defeats bounded reads or migration cost. Do not relabel an unmeasured workload as a pass.

### Lens-by-lens argument and counterargument

**Scalable.** A adds little storage but requires downstream explanation and potentially history lookup when a legacy STALE record has no current progress meaning. B can reuse the existing bounded task check/input-scope machinery, and must avoid a full repository snapshot merely to report progress. C moves work toward mutation-time invalidation and can make last-assessed views cheap, but increases write fan-out as dependencies grow. None has measured workload evidence. The useful experiment is the same fixed plans, dependency graph and retained-history populations for all candidates; measure files opened, bytes read, allocations, latency and journal amplification. A fast single happy-path request does not prove scalability.

**Maintainable.** B lets the code, UI and agent packet answer three separate questions directly: what work was reported, what dependencies currently constrain it, and what the available evidence supports. A costs less change now but leaves each new consumer vulnerable to inferring proof from REVIEW or ACCEPTED. C makes the assessment explicit in the file but obliges every mutator to identify stale conclusions. Counterargument to B: a “derived” design can still become opaque if different consumers reimplement its rules. Require one domain-owned assessment implementation and generated/checked contract descriptions, not three versions in Go, Python and TypeScript.

**Available.** A avoids a model cutover and therefore has the strongest backward-client availability during transition. B can preserve progress when source files, a verifier or an old receipt are unavailable, but cannot truthfully claim current verification. C can show its stored as-of assessment under that failure; that is a UX benefit only when the historical qualifier is unmistakable. All retain actual file-integrity failures. A prepared journal does not authorize reads of a partially replaced canonical pair. “Independent work continues” means unrelated safe operations continue, not that uncertain bytes become trustworthy.

**Reliable.** B prevents an upstream block or stale receipt from erasing the dependent's reported implementation work. Relevant changes update assessment, not history. A cannot recover a pre-STALE label just by renaming it. C's event trail offers explicit assessment history, but a missed invalidation can leave an attractive stale success beside fresh progress. Counterargument to B: computing against live files can race. Preserve existing anchored reads, identity/hash checks, repeated-scan requirements where the evidence contract uses them, and operation-scoped memo boundaries; never cache a prior failure/absence into success.

**Testable.** Existing tests already demonstrate ordinary reconcile preserving dependent progress, transitive dependency advice, stops surviving upstream resolution, latest negative reported checks, and immutable replay. B can extend those sequences with one changed axis at a time and then cross-component scenarios. C can be tested deterministically too, but every event that changes the basis needs a negative test. A is not test-free: it needs truthful projection fixtures for both receipt-free and receipted REVIEW. A test that merely serializes the new field is insufficient; prove that a later failed check does not disappear when a task is marked done.

**Securable.** The material trust boundary is the same for all options. Honest evidence typing is essential, but it is not a new authentication mechanism. Keep actual host permission, caller-reported versus host-observed provenance, immutable content-addressed chains, safe rendering, bounded decoding, and no command execution from stored fields. Counterargument: more explicit state can look authoritative to agents. Therefore responses and generated guidance must label basis, currentness and allowed operation scope, while never using “ready” or “done” as a permission grant.

### Questions B and the CLI agent should settle

1. Is a compatibility overlay acceptable as the final representation, or only as an intermediate reader bridge?
2. Does B want current evidence applicability derived on demand (recommended), or an explicit persisted as-of assessment with its extra invalidation contract?
3. How should an old STALE record with no trustworthy prior-state evidence be displayed? The safe baseline is “legacy state; prior implementation progress unresolved,” retaining the exact raw value and reason.
4. Which existing response fields must remain stable for old consumers, and what new version/capability indicates the new projection? Do not change closed response/request schemas by adding unknown fields to old versions.
5. What concrete large-history workload, if any, is important enough to alter the recommendation?

Only work whose implementation depends on these answers waits. NT-02, NT-03, NT-04, the schema-only/documentation corrections, and the independent reviewer/recovery work can proceed.

## Proposed transition invariants for the discussion

These are semantic requirements and test scenarios, not approved new wire enums.

| State dimensions before | Event | Required state/evidence result | Side effects and retry |
|---|---|---|---|
| Pending work; no proof | Ordinary task-start | Record in-progress; proof remains unassessed. | CAS/journal only; no authority capture, source snapshot or reviewer dispatch. Same operation replays. |
| In-progress; verification missing | Receipt-free task-review | Record implementation reported ready. | Preserve prior checks/receipts as history; never fabricate a review event. |
| Reported complete; later applicable check fails | Record actual failed check | Keep reported progress; expose failed outcome and affected claim conflict. | Retain earlier pass and later failure; dependent verification claim waits, independent work continues. |
| Task A blocked; B depends on A; X independent | Record obstacle or unresolved decision | A's stop/reason survives; B waits on A; X remains selectable. | No blanket task reset. B's own explicit stop cannot be replaced by A's reason. |
| Upstream condition resolves; dependent has its own user stop | Reconcile upstream | Recompute dependency advice; dependent's user stop remains. | Do not implicitly redispatch or clear denial. |
| Existing proof; only presentation changes | Update presentation | Preserve proof applicability when its actual bound inputs are unchanged. | No automatic reviewer restart or fabricated receipt refresh. |
| Existing proof; relevant requirements/source change | Change actual bound inputs | Expose stale/inapplicable assessment only for affected subject. | Preserve progress/history and stable references; require new evidence only for a new explicit evidence claim. |
| No accessible verification input | Read context / record progress | State unavailable or unknown honestly; ordinary authorized progress remains possible. | Bounded error/omission detail; no manufactured pass. |
| Rejected review submission | Correct submission | New linked attempt with exact current target/contract/launch; prior rejection remains final. | New logical attempt identity; no overwrite or second-stop-as-first-stop relabeling. |
| Commit completed, stdout lost | Retry exact mutation | Original durable result; no duplicate edit or new revision. | Reuse operation ID and request hash; never generate a new ID merely because acknowledgement was lost. |
| Prepared multi-file journal | Resume | Complete/rollback only after existing recovery preflight, or retain conflict. | No silent reset, no overwriting third-party edits; ordinary work outside the dependent unsafe store continues. |
| Legacy STALE; earlier progress unknown | Read / preview migration | Retain ambiguity and exact legacy provenance. | No automatic conversion to pending, in-progress, done or verified. |

## Native correction map

### N-F01 — Register and validate context-preview output at every consumer (NT-02)

Producer contextOrdinaryPreview stores a content-addressed codearbiter.context-preview/0.1.0 object under context-previews through PutDerived. Snapshot's reserved-directory switch omits that directory, and completion normalization uses the same output recognizer. A valid ordinary preview therefore becomes an invalid reserved output for later strict consumers.

Add a closed output-kind contract shared by producer admission and consumer recognition. The context preview validator must check the actual format, required fields, request shape/mode, digest-shaped binding, bounded base64 before-images, safe document/target mapping and existing context mutation semantics as appropriate. Snapshot recognition must validate historical preview bytes without demanding that the preview's target still match today's bytes; that freshness check belongs to apply. A preview that is stale for application is still a valid retained output. Do not make the entire .artifacts directory an ignored area.

Avoid an import cycle by putting the preview-format contract in an existing low-level context contract owner or a minimal dependency-free internal contract unit; operations cannot become an import dependency of evidence/store. Keep format, filenames, hashes, response omission limits and ordinary no-permission behavior unchanged. A “successful” test must run preview → snapshot → normalized completion. Negative tests cover wrong digest/name, unknown key/format, malformed or oversized before-image, nested directory, link/reparse path and wrong document target. No proof is minted.

### N-F02 — Close operation discovery and traits (NT-03)

repair-apply is dispatched, has a closed request schema and is journaled, but Names omits it. Add it and make omission mechanically detectable. A repository-owned descriptor set should own operation names and finite traits: request contract identity, ordinary versus explicit-evidence behavior, journal requirement, read/metadata/file/external effects, and lock mode where the mode actually differs. Handwritten domain guards remain domain code; no generic expression language is justified.

The existing TestAllOperationSchemasClosed iterates Names, so an omitted operation evades it. Add a reverse coverage witness comparing dispatch-supported operations to the descriptor set. Test repair-preview → repair-apply → exact retry and capability discovery. Do not equate JournaledMutation=false with no writes: immutable capture and context delivery tokens are counterexamples. Preserve public names and the current protocol until an explicitly versioned change requires otherwise.

### N-F09 — Align launch-file role limits (NT-04)

commandBindingSchema permits 37 launch files, validateQualifiedBinding permits 32 workspace-manifest roles, while completionWorkspacesOnce rejects more than 32 total files. The actual Python producer created 33 files for 31 workspaces and 34 for 32 workspaces on POSIX; Windows source permits 37 with its wrapper/runtime/CLI/prefix inputs. Native rejection has not been runtime reproduced here.

Make schema, role validation and completion use the same finite contract, with 32 workspace manifests and the bounded total required by the admitted roles. The observation package is already used by evidence, so a simple exported contract constant/helper there is plausible; do not introduce a package cycle. Share cross-language fixture data or a checked generated contract with the producer instead of trusting matching comments. Preserve unique paths, singleton non-workspace roles, absolute/canonical paths, manifest containment, executable hash, filesystem identity and two-pass change detection.

Test actual producer fixtures at 30/31/32 workspace manifests; admit valid total counts 32/33/34 and native Windows 37; reject 33 workspace roles, total 38, duplicate paths/roles, misplaced manifests, changed executable/launch bytes and profile relabeling. Verification commands are not executed merely to inspect or bind them.

### N-F10 — Retire records without orphaning their history (NT-05)

Changes emits tombstones with id/revision/reason/replacement only. symbol.Build assigns the collection kind retired_symbols. planStructure requires historical task checks to resolve to a retired record whose Kind is tasks, a condition the producer cannot emit. syncExecution also preserves scope baselines whose checkpoint can have been retired, and structural validation rejects those baselines.

Introduce an explicit, versioned representation of original record kind and retained retired execution ownership. The precise field name is proposed work, not an already-supported API. New tombstones obtain their original kind from the pre-mutation symbol index, including nested records. Archive or explicitly type retired task/checkpoint execution data so it cannot drive current scheduling, while retaining checks, scope baselines, receipt references and reasons. Do not delete history to make validation pass.

Old tombstones have no kind. A stable-ID prefix is not evidence of kind. Use hash-verified preimages or a trusted exact historical model when available; otherwise preserve unresolved legacy kind and show it as historical/unclassified. Only actions requiring that unresolved ownership wait. Migration must remain valid under closed versioned schemas and must not promote unknown history to current evidence.

Test check → task retirement → read/render/history, scope baseline → checkpoint retirement, nested retirement, ID reuse rejection, repeated retire rejection, incompatible old reader refusal, migration replay and interrupted retirement. Keep tombstones immutable and stable IDs permanently reserved.

### N-F03/N-F04 — Progress/evidence semantics and truthful projections (NT-09; decision pending)

First publish a precise current-behavior compatibility projection: ordinary reported REVIEW, strict receipted REVIEW, ordinary DONE and strict ACCEPTED are distinct bases even when labels overlap. Do not infer a strict current proof just because an evidence reference exists. The evidence chain still needs its actual subject/currentness checks.

After B chooses representation, implement only the selected design across the state mutators, dependency advice, task-context, eligibility, exact/batch reads, renderers, schema/version dispatch and host consumers. Explicitly rewrite tests whose old requirement was STALE overwriting dependent progress. Preserve ordinary progress, active-work duplicate protection, exact CAS, explicit stops and strict evidence consumers. Never silently treat a missing receipt as permission to manufacture one.

The new projection must identify reported outcome, evidence origin, whether assessment ran, assessment basis, relevant changed inputs and omissions. Missing or truncated history remains unknown where it matters. An advisory scheduler must not use a derived “ready” label as verified completion.

### N-F05/N-F07 — Accurate operation effects and scoped source reads (NT-06)

Exact read has different effects from contextual read: the latter can write content-addressed delivery tokens. Darwin shared locking can create metadata; Windows observation locking requires existing metadata; Linux uses its directory locking backend. taskContext invokes assessTaskChecks and scopedInputDigest, reading bounded declared task/shared inputs and known build manifests despite a comment claiming it never inspects source.

Correct comments and contract/diagnostic descriptions, and expose operation/mode/platform effect traits through the same descriptor owner as NT-03 where useful. Do not remove locking to make a comment true, silently widen source scanning, change exact read into a live verification claim, or classify metadata writes as user permission. Test missing-metadata and read-only layouts on each supported native platform, contextual versus exact reads, and declared versus unrelated source changes.

### N-F06 — Separate schema vocabulary from reachable work events (NT-07)

work.check_status accepts unknown/passed/failed, but native create/adoption initialize unknown and implemented lifecycle changes do not set passed or failed. Label those latter values as accepted stored vocabulary without an implemented public native transition. Preserve old reads and renders. No automatic “mark done → passed,” inferred test run, new check-status mutator or fabricated receipt is authorized by this correction.

### N-F08 — Correct unsupported-platform diagnostics (NT-08)

fs_other applies only outside Linux/Darwin/Windows but says Windows/macOS promotion is pending. Replace this with the actual unsupported GOOS/backend and bounded remedy. NativeWrites/backend capability declarations already exist. Source backend availability must not become an assertion of release qualification. Test supported capability fixtures and unsupported compilation/message coverage; do not add a platform or fetch a binary.

## Durable recovery and Pi interface (NT-10)

PI-D01 owns the scoped parent delegation contract. NT-10 depends on that interface; PI-D04 consumes NT-10's agreed persistence seam. Avoid a dependency cycle.

Current store.Commit can persist bounded file edits and before-images, but the host does not presently have an approved arbitrary-source-file executor or a durable Pi effect journal just because these primitives exist. The new owner must validate exact repository identity, relative root, target/action scope, before identity/hash, actual host permission, cancellation and effect identity before performing a mutation. A captured delegation is not a filesystem sandbox.

Prefer a host-specific bounded record contract for a Pi attempt/claim/outcome. Register its internal-output namespace only if it is actually stored in the artifact reserved root; a Git-common local bookkeeping spool has a different owner and should not be invented as review evidence. Every record needs a version, operation/attempt identity, scope/request digest, phase, bounded result or uncertainty, and recovery rule. Do not put secrets in records.

For the minimum trusted-host delegation profile, the persistence seam may own bounded durable claims/outcomes while parent-owned Pi tools retain their existing file-operation semantics. Strictly admit the actual request targets, refuse known stale preconditions, serialize Arbiter-owned effects, and observe before/after state. These checks are not atomic CAS or a guarantee against every concurrent external edit or path swap. Never blindly replay an uncertain effect or restore over observed intervening work. If the advertised profile promises race-free containment or expected-hash mutation, first implement and qualify a narrow platform-safe primitive or an appropriate confined executor. Do not expose arbitrary paths through an existing artifact operation. Preserve the existing native anchored-path, create-only publication, CAS, conflict and unsupported-platform guarantees wherever native storage is reused. Private payload staging may precede an operation claim, but a confirmed durable exclusive claim must precede every visible source mutation or command effect; durable outcome observation precedes acknowledgement.

Resume distinguishes: not admitted; admitted but effect not started; effect uncertain; outcome recorded; acknowledged; revoked/expired. Exact replay returns the recorded result. Uncertain outcome is observed before any retry; no blind duplicate edit, command or external call. Cancellation revokes future admissions, terminates/settles owned processes as supported, and records whether an in-flight effect completed; it cannot claim undo of a completed effect.

A semantic conflict in one task or delegation does not freeze unrelated work. A pending canonical multi-file transaction currently makes that store a dependent integrity domain. Keep this boundary truthful. Disjoint canonical reads/writes during pending recovery would require a separately designed read/write-set isolation mechanism; deleting Pending() is not an implementation of the user requirement.

## Corrected reviewer submissions (NT-11)

There is no native global prohibition on all future reviews. The inspected charter prohibits retry under the **same request**. The native authority consumer validates a fresh observed passing result with exact host profile, launch, target, contract and coverage. changes_requested and malformed replies do not become successful receipts.

The host workflow should retain the rejected attempt and create a linked new request for the corrected submission. Re-freeze the subject if it changed. For unchanged subjects, preserve exact identity and a new real attempt/launch; do not relabel a later stop from the original child as the first stop. An explicitly recorded host/user denial remains a separate stop and cannot be cleared by correcting JSON.

Use the existing observation format when a fresh valid attempt fits it. If linkage must cross the native content-addressed boundary, introduce a closed version/profile and backward inspection path; do not add extra keys to an old closed schema. Native successful capture is content-addressed/idempotent; journaled mutations consuming a receipt retain their operation-ID replay rules. “Resubmit corrected content” and “retry an unknown acknowledgement” are different events.

## Compatibility, migration and rollback contract

1. **Reader first.** Candidate readers inspect historical bytes without rewriting them. Preserve current legacy format/profile distinctions and raw unknown legacy state. Return explicit unsupported-version diagnostics where interpretation is unsafe.
2. **No silent format upgrade on read.** A schema-changing write is a deliberate versioned transaction with exact expected revision/model hash. Preserve artifact IDs, record IDs, references, explicit stops, evidence and prior model hashes in the real journal.
3. **Complete-store recovery.** Before migration, retain the affected canonical files plus indexes/provenance/history/transactions and their exact digests. A single HTML before-image is not a store backup.
4. **Migration preview and actual cutover.** Specify mappings, unresolved cases, touched paths, old/new readers and whether any old client loses access. Apply with exact CAS. A changed source invalidates that preview.
5. **Retry.** Same intent uses its existing operation ID and request hash. Different content needs a new operation ID only after the earlier outcome is known. OPERATION_ID_REUSE, RECOVERY_REQUIRED, OPERATION_ROLLED_BACK and COMMIT_OUTCOME_UNKNOWN remain distinct.
6. **Rollback before later work.** Complete/rollback a prepared operation using the existing preflight. A terminal committed transaction is not general undo.
7. **Rollback after later work.** Preserve the newer store and export/forward-recover. Restore a complete compatible snapshot into a separate target; never copy an old before-image over later committed work.
8. **Old client after cutover.** The old client either reads its supported exact representation safely or explicitly refuses. It must never drop unknown fields, rewrite new state, clear stops or accept new evidence under an old profile.
9. **Ambiguous STALE and untyped tombstones.** Retain the raw value and historical evidence. Do not derive truth from name prefixes, UI labels or comments. Unresolved mappings constrain only operations that need them.
10. **Major release is not migration proof.** The package version signals compatibility policy; exact old/new binaries, on-host tests and actual distributed artifact readback establish the tested behavior.

## Meaningful validation plan and commands

The following are real command shapes supported by the inspected repository. New sequence cases must be added to the named existing owners; a listed command does not mean the proposed case already exists or has passed. Run focused tests during each slice, then the repository's integration gates once for the actual integrated candidate.

| Concern | Existing owner and planned sequence | Command |
|---|---|---|
| Ordinary progress and independent work | operations/assistive_test.go and dependency_advice_test.go: draft → start → reported-ready → upstream block/reconcile → dependent waits, independent proceeds, explicit stop survives. Update old STALE assertion only after B's decision. | From core/artifacts: go test ./internal/operations -run 'TestAssistive\|TestDependency\|TestTaskContext' |
| Evidence truth | operations/task_check_test.go and check_conflicts_test.go: pass → fail → unknown/skip → later applicable pass; preserve history, scope, unassessed/trimming and no authority files. | From core/artifacts: go test ./internal/operations -run 'TestTaskCheck\|TestCheckConflict\|TestCheckReportBoundary' |
| Output closure | operations/context_assistive_test.go, evidence/snapshot_test.go and completion_workspace_test.go: preview → snapshot → normalized completion; malformed historical preview remains rejected. | From core/artifacts: go test ./internal/operations ./internal/evidence |
| Operation and platform traits | operations/protocol_test.go, capabilities_test.go, read tests and platform lock tests: forward/reverse registry coverage, repair replay, exact/contextual effects. | From core/artifacts: go test ./internal/operations ./internal/read ./internal/store |
| Launch binding | observation/runner_contract_test.go and evidence/completion_workspace_test.go: actual producer role/count fixtures, valid boundaries and identity mutation. | From core/artifacts: go test ./internal/observation ./internal/evidence |
| Retirement | operations/migration_test.go, validate/validate_test.go, symbol/index_test.go and render tests: checked task and checkpoint retire without history loss; ID reuse remains rejected. | From core/artifacts: go test ./internal/operations ./internal/validate ./internal/symbol ./internal/render |
| Process death and acknowledgement | store/crash_test.go has real child-process death at staging/journal/replacement points; extend consuming CLI/host loss-of-ack sequences. | From core/artifacts: go test ./internal/store -run 'TestProcessDeathRecovery\|TestJournalPublicationCrash\|TestTransactionalCAS\|TestRecoveryConflictPreservesExternalEdit' |
| Corrected review | observation/contract_test.go, native_v1_test.go, native_v2_test.go and operations/completion_rerun_test.go: rejected attempt → fresh corrected attempt → exact capture/replay; old mutated chain and stale target fail. | From core/artifacts: go test ./internal/observation ./internal/authority ./internal/operations |
| Schema compatibility | tools/test-artifact-mixed-schema.py: old read before cutover; candidate upgrade, two subsequent writes, old refusal, exact replay and separate complete-store restore. Keep existing 0.3.1→0.3.2 fixture; add current baseline→new schema fixture. | From repo: python tools/test-artifact-mixed-schema.py --old /absolute/old/ca-artifact --candidate /absolute/candidate/ca-artifact |
| Work compatibility | tools/test-artifact-work-old-client.py: new field plus later edit survives old reader/writer refusal. | From repo: python tools/test-artifact-work-old-client.py --old /absolute/old/ca-artifact --candidate /absolute/candidate/ca-artifact |
| Integrated Linux race gate | Existing CI invokes the repository's population-aware parallel runner. Preserve full test population and fail on empty/incomplete runs. | From repo: python tools/go_test_parallel.py --module core/artifacts --build-flag=-race |
| Derived types and public surface | Existing CI check; extend for selected model/projection contract. | From repo: python tools/generate-artifact-types.py --check ; python .github/scripts/test_artifact_surface.py |

The last row denotes two separate commands, not permission to skip generation/readback. CI pins Go **1.27.1**, matching core/artifacts/go.mod. Run supported native tests on actual Linux, Darwin and Windows targets; cross-compilation alone does not verify locks, junctions or Windows npm launch identity. Keep publication and installed-candidate qualification under the release owner. Test commands needing exact binaries use actual built paths and recorded digests, never a fabricated or PATH-discovered replacement.

## ADR and documentation amendments to propose

| Record | Suggested forward amendment | What stays intact |
|---|---|---|
| ADR-0043 | Record B's eventual representation decision, precise progress/evidence/dependency semantics, dependent-only conflicts, corrected attempt handling, and recovery projection. Clarify ordinary progress versus strict optional evidence paths. | No duplicate artifact permission layer; user stops, host permissions, typed records, CAS/journals and historical evidence. |
| ADR-0037 | Explain finite operation/output contracts and capability traits as internal compile-time interfaces, plus explicit native/host recovery ownership. State that no generic FSM interpreter or runtime plugin system is introduced. | Small file-backed kernel, closed kinds, one canonical authority, inert stored commands and per-kind compatibility. |
| ADR-0004 | Add a forward record clarifying that “no schema layer/no transactional guarantees” was historical context superseded by typed schemas and file transactions. | No database/daemon; stock standard-library Python integration. |
| ADR-0025 | Clarify current user decisions outrank conflicting older records and a consequential unresolved choice holds dependent work only. Preserve a truthful pending discussion instead of logging an unmade choice. | Index-first lookup, fail-soft missing history, explicit arbitration exemptions and no invented authority. |
| ADR-0033 / lifecycle records | Lifecycle owner records actual acceptance, implementation and verification separately for the approved changes; retain old sealed packets. | No rewriting historical accepted bodies or backfilling proof from this handoff. |
| Protocol/artifact docs and generated consumers | Describe exact effects, admitted operations, schema-only work values, distinct progress/evidence basis, safe retry and supported backend diagnostics. | Existing command names and preserved compatibility boundaries unless deliberately versioned. |

Do not renumber an ADR in this packet or edit accepted content as a routine documentation fix. The receiving agent should prepare concrete proposed amendments/forward decisions and use the repository's actual lifecycle owner. The user's implementation decisions are already inputs; the pending progress/evidence decision and acceptance of newly authored ADR text remain separate.

## Source reference index

Every path below is relative to the pinned **arbiterForge/codeArbiter@fd7eb34b2da439551443d09526ab48fd1d1bb9bf** source. The native JSON task ledger carries fully qualified owner/repository@commit:path references for each N-F finding.

- **SRC-SMARTS:** core/surface/includes/smarts/core.md; lenses.md; decision-log-format.md; core/surface/skills/brainstorming/SKILL.md; core/surface/skills/decision-variance/SKILL.md and references/analysis.md; core/surface/agents/grader.md and decision-challenger.md; core/surface/includes/sprint-authority.md. These canonical workflow files were fully read.
- **SRC-INTENT:** .codearbiter/decisions/0025-recorded-intent-precedes-autonomous-scoring-and-spec-shaping.md; 0037-extensible-structured-artifact-engine.md; 0043-assistive-state-engine.md; 0004-database-free-stdlib-only-architecture.md. Their bodies were fully read. decision-log.md was consulted index-first, then relevant DECISION-0063/0064/0076 sections; no full-log read is claimed for this handoff.
- **SRC-SECURITY:** .codearbiter/security-controls.md, fully read, especially Native artifacts and recovery and Pi trust boundary.
- **SRC-PROGRESS:** core/artifacts/internal/operations/assistive.go:recordWork (152); lifecycle.go:progress (278), invalidateDependents (252); prerequisite_observation.go:finishScope (66); schema/common.schema.json:task_state (950), retired (996); schema/plan.schema.json:execution (154).
- **SRC-DEPENDENCY:** core/artifacts/internal/operations/assistive.go:dependencyAdvice (14), eligible (53); dependency_advice_test.go (11–112); task_context.go:taskContext (13).
- **SRC-CHECKS:** core/artifacts/internal/operations/task_check.go:assessTaskChecks (151); input_scope.go:scopedInputDigest (39); task_check_test.go:TestTaskCheckLatestFailureOverridesPriorPassAndSkipsUnknown (145), TestTaskCheckBoundedRecentViewKeepsHistoryInJournal (274).
- **SRC-RECOVERY:** core/artifacts/internal/store/transaction.go:Lookup (183), Commit (258), Recover (414); operations/engine.go:Run (76); cmd/ca-artifact/main.go:run (17); store/crash_test.go:TestProcessDeathRecovery (17), TestJournalPublicationCrash (100).
- **SRC-REVIEW:** core/artifacts/internal/observation/contract.go:reviewDecisionSchema (165), ValidateLink (381), reviewContractHash (603), validateReview (611); authority/receipt.go:ReceiptSchema/EventSchema/Inspect; core/surface/agents/authority-reviewer.md (41–50).
- **SRC-COMPAT:** tools/test-artifact-mixed-schema.py; tools/test-artifact-work-old-client.py; .github/workflows/ci.yml (738–770 and 960–990); core/artifacts/go.mod.
- **SRC-FINDINGS:** exact producer/consumer paths, symbols and start-line evidence for every N-F record are copied verbatim into native-tasks.json from audit-work/native.json. They were read during the original native audit; handoff changes are proposals.

## Completion evidence expected from the CLI agent

For each task, return its commit, affected contracts and consumers, exact tests run with platform/toolchain, observed failures and resolutions, backward-reader results, and actual rollback/recovery exercise. Mark any remaining blocked task with its real dependency, not a generic project-wide approval status. Preserve the old audit row IDs as traceability rather than replacing the audit with a smaller summary.

The final integrated candidate must demonstrate the full dependent-work and interruption sequences across hosts, then satisfy the separate release pipeline and exact-artifact readback. No universal “always improves everything” or “cannot break anything” guarantee follows from a design or test suite; the corpus supplies bounded invariants, meaningful regressions and a controlled release boundary.

