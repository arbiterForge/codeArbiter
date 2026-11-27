# Cross-owner design review: hooks, Pi delegation, and native state

## Review result and boundary

I fully read the final `pi-delegation-design.md` (279 lines) and `native-smarts.md` (261 lines) against the hook/workflow recovery design and its task ledger. This review inspects proposed contracts, not a new implementation. No repository source was changed, no new broad source research was performed, and no runtime tests were run. All three designs remain anchored to development source `arbiterForge/codeArbiter@fd7eb34b2da439551443d09526ab48fd1d1bb9bf`; they are not release qualification evidence.

Two wording conflicts in the reviewed drafts require normalization. Root has already supplied their resolution: keep Pi's explicit trusted-host, exact-action admission minimum, and require a durable exclusive claim before any externally visible effect. The precise replacements below implement that direction without adding another user decision. After these replacements and the dependency normalization below, I found no other material contradiction across the reviewed designs in ordinary-work continuity, request finality, authority, or storage ownership.

## 1. Required normalization: the direct-file executor's promised guarantee

### Conflicting draft text

In `native-smarts.md`, **“Durable recovery and Pi interface (NT-10)”** says that source writes must either use a narrow platform-safe primitive with containment/link-race/CAS tests or a separate confined executor. Read as an unconditional acceptance floor, this requires guarantees beyond the minimum Pi profile.

In `pi-delegation-design.md`, **§3.1 “Run admission owned by the parent”**, the minimum profile can use existing native Pi file tools with serialized Arbiter-owned writes, static admission and before/after observations. It explicitly says those tools expose neither an expected-hash transaction nor a rooted descriptor, and stronger guarantees need another qualified primitive. That is an honest action-admission model, but its phrase “preserve external edits” can itself sound stronger than the proposed non-atomic execution can guarantee.

Root selected the following interpretation: **NT-10 may supply bounded durable claims/outcomes while the parent executor preserves existing trusted-host semantics. A race-free containment or CAS promise is conditional on implementing and qualifying a primitive that actually enforces it.** Known stale preconditions must be refused, and observed changes must never be blindly replayed or overwritten during recovery. Before/after observations do not protect every concurrent external edit.

### Recommended replacement in native-smarts.md

Replace the paragraph starting “For source writes, either extract…” with:

> The initial Pi profile is trusted-host exact-action admission. NT-10 may provide the bounded durable claim/outcome seam while a parent-owned executor preserves the existing host tool semantics, strict static request/target admission, and observed before/after checks. Refuse preconditions already known to be stale, and never blindly replay an uncertain effect or restore a before-image over an observed intervening edit. These observations are not an atomic expected-hash update, race-free containment, or a guarantee that every concurrent external edit is protected. If a new profile advertises those stronger guarantees, implement and qualify a narrow platform-safe primitive or an actual confinement backend before enabling that profile. Keep the existing native artifact store's anchored paths, CAS, closed target scope, and unsupported-platform behavior intact; do not expose arbitrary source paths through an artifact operation or claim the weaker host profile has the native store's guarantees.

This preserves the native store's existing integrity contract while avoiding an unintended hard prerequisite for the separately scoped Pi host executor. It does not claim that any particular existing Pi tool already satisfies a stronger guarantee.

### Recommended replacement in pi-delegation-design.md

Replace the paragraph in §3.1 starting “If the executor uses native Pi file tools…” with:

> If the executor uses native Pi file tools, do not claim those tools provide an atomic expected-hash update or race-free containment: `ToolDefinitionPort.execute` exposes neither a CAS transaction nor a rooted descriptor. Serialize Arbiter-owned writes, perform strict static target admission and before/after observations, refuse preconditions already known to be stale, and report uncertain outcomes honestly. Preserve observed intervening edits by refusing blind replay or restoration; these checks do not guarantee protection from every concurrent external edit. If product language promises atomic CAS or protection even when a path is concurrently swapped, implement and qualify a safe file-effect primitive or confinement backend first. Native task NT-10 is the integration seam for the agreed claim/outcome contract and any explicitly selected stronger primitive; it must not silently widen the artifact store into an arbitrary source executor.

No Docker or stronger confinement backend becomes a universal dependency of ordinary child authorship. Equally, the trusted-host profile must not inherit confinement terminology from a stronger optional profile.

## 2. Required normalization: claim ordering versus private staging

The same NT-10 paragraph uses the phrase **“write-before-claim ordering.”** Without naming which write it means, that conflicts with the Pi execution order and hook recovery design's requirement to persist an exclusive effect claim before mutation. It could describe harmless private staging in the existing file transaction, but the receiving agent must not read it as permission to mutate source before the claim.

Use this explicit shared ordering statement wherever the ambiguous phrase appears:

> Private bounded staging, such as preparing a payload or before-image, may occur before publication of the claim under the owner's existing safe transaction protocol. The durable exclusive operation claim must be confirmed before any externally visible source-file, command, or publication effect begins. If claim durability is unknown, no new effect may start. A response or outcome-record failure after an effect must retain uncertainty and reconcile the existing operation; it does not prove that the effect did not happen.

For native canonical transactions, keep their existing journal/staging semantics. For Pi operations, keep the parent-owned admission → durable claim → execution → observed outcome order. For harvest, keep registration → claim → selected-owner effect → exact-target reconciliation/settlement. Sharing this ordering invariant does not require a universal enum or one generic executor.

## 3. Precise compatibility statements

| Topic | Compatible statements in the reviewed designs | Implementation condition to retain |
|---|---|---|
| Ordinary authorized work | All three distinguish ordinary progress/bookkeeping from evidence claims and effect admission. A missing recovery notice or historical acknowledgement must not hold unrelated work. | Recovery availability is not a new universal gate. Existing policy-required permission and store integrity checks still apply to the operation that actually depends on them. |
| Dependency-only conflict scope | Pi scopes conflicts/uncertain effects to affected resources; native scopes semantic task conflicts to dependents; hooks updates the prose owners to the selected dependent-only rule. | Independent work can include authorized mutations, not just read-only tasks. Do not broaden a local semantic conflict into a project-wide approval state. |
| Actual broad authority loss | Pi project-trust withdrawal retires the governed authority for that lifecycle; all designs preserve actual user/host denial and explicit stops. | This is not a contradiction with dependent-only semantic conflicts. Do not restore trust or clear a stop because a new session, corrected packet, or recovery record exists. |
| Prepared native transaction | Native's existing pending multi-file transaction is an integrity dependency for its canonical store. Hooks puts ordinary recovery metadata outside that store. | Keep native `Pending()` protection. Do not attach every host tool effect to that store merely to reuse a journal, and do not delete the guard to claim independent progress. Safe work outside that dependent store continues. |
| Storage namespace | Pi and native now make artifact output registration conditional on actually using the reserved artifact root. Hooks proposes a Git-common runtime spool, excluded from evidence. | No unconditional NT-02 dependency for Git-common records. If a later implementation puts a projection/output in the artifact namespace, closed reader/producer registration becomes a real prerequisite for that projection only. |
| Ownership | Each design requires an agreed owner/version for durable records and rejects arbitrary executable handlers. | Share storage primitives or a summary projection where useful; do not make two code paths authoritative writers for the same record. Pi operation history and terminal-harvest obligations retain their distinct kind/owner semantics even if they share a physical parent directory. |
| Startup/reentry | Hooks automatic scans are read-only and bounded; Pi asks for one bounded inspection notice; native supports truthful recovery projections. | The shared scan may report that a journal needs repair, but must not mutate it or execute work. Separately owned Pi process settlement can continue under its existing execution lifecycle; it is not a side effect granted by the notification helper. |
| Corrected reviewer submission | Native and hooks use fresh linked requests when the old request is final, with actual current launch/target/contract binding. Pi permits legitimate corrected operations under current authority. | Preserve old rejection/denial/history. Never relabel a second stop as a first stop, add retry keys to a closed old schema, or treat corrected JSON as removal of a genuine denial. |
| Exact acknowledgement retry | Native replays the same operation ID/request hash; Pi returns stored/current state; harvest reconciles exact operation/origin before retry. | Different content is a new linked logical attempt only after the old outcome is known. A lost acknowledgement alone is never a reason to choose a new ID. |
| Effect-specific replay | Harvest's registered local adapters may retry a proven-absent/idempotent local creation under the actual target contract. Pi shell/arbitrary source effects have no generic replay guarantee. | A shared UI must not transfer harvest retry permission to a Pi unknown shell operation. Reconciliation dispatches to the owning kind; common labels do not imply common effect semantics. |
| Weak versus causal observation | Pi correctly distinguishes “desired bytes now exist” from proof that the operation executed once; native distinguishes progress and evidence; harvest settles only a valid target effect/disposition. | For harvest, exact-origin reuse can satisfy the declared ensure-origin obligation without claiming causal authorship. Do not label a hash coincidence as a native proof or an exactly-once Pi effect receipt. |
| Retention | All retain unresolved records/history, preserve unknown versions, and avoid silent destructive repair. | A total-capacity bound must refuse/mark new registration unavailable rather than evict unresolved history. Bound scans independently of history size. Root may choose routine capacity values without reopening the already authorized recovery direction. |
| Cancellation and cleanup | Pi retires future admission while settling owned processes; hooks forbids false cleanup and automatic branch/worktree deletion; native never treats terminal commit as general undo. | Process containment for an already owned execution is distinct from deleting user worktrees/branches. ADR0036's deletion authority is not superseded by a recovery record. |
| Rollback | All preserve newer user changes, unresolved intents and compatible inspection; none treats source rollback as undo of an observed external effect. | Keep the exact reader/version matrix and complete-store backups for native migration. Do not drop unknown records to make an old client appear compatible. |
| Qualification | Pi distinguishes fixtures, host loading, functional effects, exact package evidence and release evidence; native and hooks do likewise. | Full author acceptance still needs real admitted write/edit/command effects. Read-only fallback is temporary degradation, not closure of SF01. The disposable-home and dummy-credential boundary remains mandatory for the relevant tests. |

### One projection, several owners

The shared startup summary can carry a record's owner/kind, opaque identity, semantic version, observed status, reason, uncertainty and supported inspection/resume route. It must not turn Pi operation statuses into the harvest reducer's writable state, nor turn a native recovery conflict into a prompt requiring all historical work to be acknowledged. Final field names remain implementation choices within the agreed closed contracts.

The Python recovery scanner can be implemented and tested against an adapter fixture before Pi-D04 exists. The real Pi integration consumes parent-observed outcomes after the Pi owner is ready. It cannot infer grants or outcomes from a child model result. This avoids a dependency cycle while retaining a real integration acceptance requirement.

### Open policy choices stay open

`native-smarts.md` correctly labels progress/evidence representation as a provisional B discussion; its recommendation B is not an accepted decision. That does not block independent hook recovery, output-schema corrections, manifest correction, or reviewer retry work. The hook design's maintenance-only HIGH disposition question also remains separate: nothing in the Pi or native retry contract chooses a gate exception.

## 4. External dependency classification for DAG normalization

The `external_dependencies` objects in `hooks-workflow-tasks.json` identify coordination and acceptance relationships. They must not all be converted into hard “cannot begin work” edges. The table below is the authoritative classification for this review. A prerequisite for a particular final integration test is not a prerequisite for authoring independent source or fixtures.

| HW task and external reference | Link type | Actual prerequisite | Work that may proceed independently |
|---|---|---|---|
| **HW-04 → NT-04** | Contract coordination plus completion/conformance dependency | Shared admitted roles/bounds and native consumer behavior must agree before cross-language acceptance is closed. | Python regression fixture, boundary documentation, producer readback and test construction can proceed before NT-04 implementation finishes. |
| **HW-06 → PI-D05** | Coordination and final cross-host scope test; **not a hard source prerequisite** | The integrated Pi child cancellation/dependency behavior must match the dependent-only policy. | Canonical conflict/SPRINT/context-check text, generated surfaces and independent policy tests can be completed first. No ordinary workflow change waits for the Pi revocation implementation. |
| **HW-08 → NT-11** | Request/profile contract coordination plus final reviewer-flow acceptance | Fresh real launch/current target/contract observations must be accepted through the supported native format. Any genuinely new profile must exist before the adapter emits that profile. | Corrected-submission prose, bounded host attempt linkage and existing-format fixtures can proceed. NT-11 can inspect/qualify existing formats without waiting for the entire HW-08 implementation. |
| **HW-14 → PI-D04** | Downstream Pi adapter integration and completion dependency; **not a prerequisite for the shared scanner** | Real Pi outcome projection must implement the agreed owner/identity/status shape before Pi wiring and installed-host tests are complete. | HW-11/12 shared store/read/reconciliation work, Claude/Codex notices, status/standup flow and Pi adapter tests against an explicit fixture can proceed. PI-D04 does not depend on HW-14 completion. |
| **HW-14 → PI-D05** | Final authority/revocation conformance requirement | The real Pi resume/notice integration must prove that current lifecycle scope applies and no retired grant is restored. | Read-only summary projection and all host-independent functionality proceed before revocation implementation finishes. Only the final Pi-specific acceptance cell waits. |
| **HW-25 → DIST-M01** | Shared-schema coordination plus consumer conformance dependency | The supported optional-field schema must be selected before final Python/farm accept/reject parity can be closed. | Read existing behavior, prepare five/six-field and malformed fixtures, and preserve Python's current checks in parallel. Do not create two independent schema redesigns. |
| **HW-26 ↔ PI-D07** | Shared qualification boundary and evidence link; **not HW-26 waiting on PI-D07 completion** | Pi-D07's real functional tests must consume the proven disposable-home/credential/identity boundaries. The final program gate collects their exact-artifact evidence. | Isolation setup and benchmark/runtime-discovery boundary tests in HW-26 precede or run alongside PI-D07. A hard reverse dependency would create the wrong order and can form a cycle. |
| **HW-27 → ROOT-INTEGRATION-AND-RELEASE** | Ownership/routing pointer, **not a dependency edge back to the root gate** | Root integration/release gate collects HW-27 evidence. Publication follows whole-program acceptance. | HW-27 conformance work runs before the root gate closes. Normalize the direction as root gate depends on HW-27, not both directions. |
| **HW-27 → NATIVE-SMARTS-PROGRESS-EVIDENCE** | Whole-program completion dependency for the selected semantic scope | B's actual choice and the dependent native consumers must be implemented/qualified before claiming the whole requested program finished. | All unrelated HW tasks remain actionable. Do not make the pending representation choice a prerequisite for terminal-harvest bookkeeping, documentation fixes, or corrected-request handling. |
| General references to **PI-D01–PI-D07** in the cross-workstream map | Informational ownership and contract-coordination links | Specific Pi public/internal shapes and lifecycle behavior are consumed only where named above. | Do not expand this range into seven hard prerequisites for every hook task. |

HW-14's own shared storage contract must exist before its production scanner can read real records; that is the meaningful internal dependency on HW-11. HW-12's target adapter completion is necessary for a truthful functional resume route, but not for a read-only notice fixture. The same distinction applies throughout: develop contracts, fixtures and independent code in parallel; hold activation and final acceptance at the real consuming boundary.

Root may represent these links as `contract_coordination`, `integration_completion`, `qualification_input`, or equivalent fields. The labels are not a required new product schema. Preserve the semantics and avoid a synthetic all-to-all implementation barrier.

## 5. Actions for the root handoff

1. Apply the executor-guarantee and claim-ordering replacements consistently to the two design documents and any task text that repeats the stronger unconditional rule. Keep the Pi minimum trusted-host profile explicit.
2. Tighten any unqualified “preserve external edits” claim to known-stale refusal, honest uncertainty, and no blind replay/restoration; do not claim atomic protection that the selected executor does not provide.
3. Normalize external task relationships using the table above. In particular, remove hard source-order edges HW-06 → PI-D05 and HW-14 → PI-D04/05; retain their actual final integration tests.
4. Keep storage registration conditional on artifact namespace use, and keep one authoritative owner per record. No new global native-journal dependency is warranted for Git-common bookkeeping.
5. Preserve the two genuinely open policy discussions and the exact-artifact evidence ladder. Nothing in this cross-review resolves a policy by changing a validation label.

No additional material cross-owner conflict was found in the fully read drafts. This is a design consistency conclusion with the two specified normalizations, not a claim that the future implementation is safe, complete, or tested.
