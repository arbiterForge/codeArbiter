# Pi parent delegation and surface implementation handoff

## Status, authority, and acceptance decision

This is an implementation design for `arbiterForge/codeArbiter`, based on development source at **`fd7eb34b2da439551443d09526ab48fd1d1bb9bf`**. It is not an implemented feature, a released-behavior claim, or a qualification receipt. The accompanying `surfaces-tasks.json` maps every original finding **SF01–SF16 and SW-F01–SW-F09** to executable work slices, prerequisites, rejection cases, completion evidence, and rollback.

The work belongs on the program's separate integration branch. Keep it away from `main` until the entire program, including migration, recovery, regenerated surfaces, host qualification, and publication recovery, meets its acceptance gates. The final major release is a program-level action; this document does not select a new version or authorize an intermediate partial release.

The user selected **functional scoped parent delegation for Pi authors**. A child that completes its handshake and reads files but cannot write, edit, or execute admitted author commands does not satisfy SF01. Read-only operation is an honest temporary degraded capability and remains useful for reviewers; it is not closure for the author feature. Existing final-argument checks, bridge hard blocks, project-trust checks, plan-mode restrictions, source ownership, credential isolation, and process-tree cleanup remain in force.

The recommended minimum is **parent-mediated exact tool-operation admission under the existing trusted-host model**. A parent approves the concrete frozen operation and executes it through an owned executor. This does not require Docker. The grant describes which tool request, command, working directory, role, and live run the parent admitted. It does not promise that arbitrary project test code is confined to those paths or prevented from using the host network. If a future profile advertises transitive filesystem or network confinement, that profile requires a separately qualified isolation backend and cannot fall back silently to the trusted-host profile.

Ordinary progress remains nonblocking. Delegated mutations retain the existing requirement to establish permission and record the admitted operation before execution. Interruption records do not become a new attestation requirement for unrelated editing, discussion, or workflow progress. A conflict or unknown outcome stops only operations that depend on the affected resources, except for genuine host-wide authority loss such as project trust being withdrawn.

## 1. What the current source and tests establish

References in this document use the pinned source above. The source ledger at the end provides complete `owner/repo@commit:path` references. Source paths with a proposed filename are explicitly labeled as proposals.

| Existing boundary | Source-confirmed behavior | Consequence for implementation |
|---|---|---|
| Parent dispatch admission | `extension.ts:installPiDispatch` checks enabled repository state, affirmative live project trust, and a current lifecycle lease. `dispatch.ts:createDispatchTool` accepts only `mode`, `roles`, `task`, `depth`, and `limits`; it currently ignores its host tool-call ID. | Add a separate internal authority port carrying parent mode, final frozen request, host-call correlation, lifecycle, and permission context. Task text and model-provided scope proposals are not authority. |
| Child launch | `runner.ts:validateChildLaunch` binds active Node, Pi runtime identity, package-owned extension/charter/skills, and an exact role catalog tool list. `buildChildArgv` selects RPC, disables project extensions/context/session material, and uses the existing offline inference arrangement. | Preserve these restrictions and at-most-one-author-per-dispatch. A delegation grant must not enable project extension loading, recursive dispatch, or arbitrary child executables. |
| Child bootstrap | `child-extension.ts` reads exactly 32 bytes of private nonce from fd3. The one-shot handshake binds nonce, challenge, cwd, provider/model, tool list, untrusted-project mode, and RPC context. | Any richer bootstrap is a new versioned internal protocol, not an existing supported Pi API. Do not append unrecognized bytes to the current nonce format. |
| Handshake confirmation | The child requests one exact `ui.confirm` attestation; the runner verifies its digest and automatically responds to that one request. The runner rejects other UI requests in later phases. | This proves the expected child configuration. It is **not human approval to mutate files**. Do not reinterpret it as consent, or turn all child RPC confirmation requests into automatic approvals. |
| Current child mutator path | `installChild` installs the standard wrappers with `projectTrust: "not-required"`, but supplies neither parent delegation, a permission-audit callback, nor a TUI confirmation context. Execute-mode write/edit/bash mutation actions require `ask`; `confirmationUi` accepts TUI only. | The existing isolated source probe completes handshake/read and then rejects every mutator. Implement a new guarded delegated branch; do not merely mark the child ready, change its mode to TUI, grant project trust, or make execute policy default-allow. |
| Parent tool permission | `tool-guard.ts` snapshots canonical final arguments, calls the Python bridge, evaluates descriptor-owned policy, confirms through parent TUI, durably audits approval, and rechecks lifecycle, mode, source ownership, native execute identity, arguments, signal, and live trust after awaits. | Extract/reuse this decision sequence as a parent-owned operation gate. Do not maintain a looser parallel policy for children. Bridge `warn` remains advisory; bridge `block` remains a hard block. |
| Policy exceptions | `policy.ts` allows read/inspection and the separately owned `ca-plan` planning-write path in plan mode, while denying source/config/shell mutations. | Preserve the existing bounded planning exception. It is not a reason to allow arbitrary child authorship in plan mode. |
| Registry ownership | The bootstrap/final guard admits `codearbiter_dispatch` only from the owning parent extension. Existing tests verify competing source rejection. | Keep the registry ownership guard. Ownership alone is not task permission. New effect execution must still cross the parent operation gate. |
| Audit sink | `audit-sink.ts` bounds rows, rejects linked state/log targets, compares identities before and after append, and syncs the handle. A false return may occur after bytes were written. | This is a hardened append sink, not an operation deduplication or recovery journal. A false return is not proof that no row exists. Do not replay a mutation based on that boolean. |
| Process ownership | The runner uses managed process trees and verified cleanup. The Windows supervisor already uses fd3 for the capability stream and fd4–fd7 for launch/control/status/leash duties. | Reuse the managed tree boundary. Do not casually allocate another FD or change raw forwarding without Windows tests. Keep cleanup and observation alive after new work is revoked. |
| Inference credentials | The separate loopback inference broker retains actual upstream credentials in the parent; children receive a revocable narrow broker token and private environment. | Delegation needs a distinct purpose-bound channel/token. Never reuse the inference token as mutation authority or pass parent credentials into a delegated command's environment. |
| Path helper | `path-boundary.ts:canonicalPath` falls back to lexical resolution if `realpath` fails. | This helper is not sufficient authority for a newly promised strict filesystem boundary. Use strict observation for admitted targets; reserve stronger confinement claims for a qualified executor. |
| Current tests | `runner-isolation.test.ts` exercises handshake, replay, missing UI, source identity, protocol bounds, and forbidden recursive registration. `tool-guard.test.ts` exercises confirmation, audit refusal, final-argument drift, mode/trust loss, and lifecycle races. `dispatch.test.ts` uses fake child results for successful dispatch. | Extend these tests; their existing successes do not establish child authorship. The old source probe is a regression fixture, not released or installed-host proof. |
| Installed-host fixture | `final-arguments-live.test.ts` uses the installed Pi extension loader, registry, and tool wrapper, while substituting bridge and tool factories. | Retain this real host-ordering evidence and label its substitutions. Add an exact packaged author flow with real file and command effects for the new claim. |

The local `pi-api.d.ts` is a structural subset consumed by the adapter, not an upstream parent-delegation facility. It declares extension event handlers, tool/command registration, tool registry inspection, and selected context access. There is no existing `delegate`, `grant`, `runAsParent`, or upstream filesystem-confinement API to call. The proposed protocol below is owned and implemented by codeArbiter.

## 2. Alternatives and recommended scope

| Alternative | Functional author support | Authority and isolation promise | Decision |
|---|---|---|---|
| Keep current child read-only and correct labels | No | Preserves the current refusal behavior | Temporary degradation only; fails the selected completion criterion. |
| Convert child RPC confirmation to automatic success | Superficially | Would equate a child request with parent approval and bypass the current permission boundary | Reject. It removes a guard without establishing authority. |
| Parent admits each exact operation and owns execution | Yes | Honest capability/action scope under the current host trust model; direct request paths and command bytes are checked | **Recommended minimal implementation.** No new universal sandbox dependency and no invented upstream API. |
| Parent preapproves a finite operation batch | Yes | Same scope as the previous row, with explicit bounded batch ownership, expiry, argument digests, and revocation | A later UX optimization after single-operation semantics are proven. A wildcard command or arbitrary future argument set is not an exact batch. |
| Parent grants path/network-confined arbitrary shell execution | Yes, if implemented | Transitive operating-system/container guarantees, including project code and its subprocesses | Separate execution profile requiring an actually qualified backend. Do not advertise until verified; do not make it a hidden prerequisite for ordinary delegation. |

Start with per-operation parent confirmation for the same mutation classes the parent currently asks about. This preserves familiar consent semantics and gives the parent a concrete operation to approve. A dispatch-level grant admits a role, repository, worktree, action ceiling, deadline, and operation channel; it does not preapprove all future writes. Exact operation approval consumes that run grant and records its specific frozen arguments. A subsequent operation with changed bytes, command, path, mode, repository identity, or executable/settings profile requires new admission.

Scope proposals may be included in a **versioned addition** to the public dispatch schema, but are requests only. The parent validates and narrows them against the user's instruction and current host authority. Do not derive authority from a role's prose charter or free-form task string. Preserve existing callers that omit the proposal: reviewer calls retain current behavior; author calls enter concrete per-operation admission rather than acquiring an unbounded implicit scope.

## 3. Proposed internal contracts

The following names and fields are proposals. They are not claims about existing APIs or schemas. Implement them as bounded closed data with versioned decoders. The receiving CLI agent must review exact platform/runtime interfaces before choosing implementation details.

### 3.1 Run admission owned by the parent

An in-memory parent registry holds the live capability. Its durable record is useful for reconciliation, not sufficient to recreate the capability after restart.

| Binding | Proposed content | Rule |
|---|---|---|
| Caller | Parent host tool-call correlation derived from the actual host-supplied tool-call ID; parent session identity; opaque lifecycle generation | Never accept a model-supplied caller ID as authority. Hash/normalize values for public logs without losing internal binding. |
| Repository/worktree | Strictly observed canonical worktree root, repository/common-Git identity where relevant, and the task's owned working directory | A changed path identity invalidates admission. Do not equate another worktree with the same repository or accept lexical fallback after observation failure. |
| Run and child | Parent-generated unpredictable run/grant/child IDs; selected catalog role; package/runtime identity; managed process ownership | PID alone is not sufficient because it can be reused. A child cannot choose a sibling ID or upgrade its classification. |
| Authority generation | Current parent lifecycle/mode generation and a monotonic per-grant revision | Switching session or mode, trust withdrawal, cancellation, or explicit revocation retires the generation. A later valid session does not revive it. |
| Ceiling | Allowed tool names/action classes; direct requested targets if supplied; exact-command-only execution profile; maximum operation count, size, timeout and output | An action ceiling is not human approval for every matching operation. Unknown fields, overflow, duplicate IDs, and unsupported classes are refused. |
| Deadline | Parent-monotonic lifetime bounded by the existing dispatch timeout and an explicit expiry | Wall-clock adjustment cannot lengthen live authority. After restart, old grants remain revoked regardless of timestamps. |
| Consent | Parent-observed per-operation confirmation or an explicitly admitted finite batch identifier | Handshake attestation, project trust, child self-report, and artifact attestation are not substitutes. |
| Evidence identity | Exact package digest, Pi runtime identity, policy/descriptor version and executor profile | Receipts state which admission implementation ran; they do not turn a runtime version string into qualification. |

For the minimum trusted-host profile, call path fields **admitted request targets**, not “sandboxed paths.” Reject traversal, ambiguous platform spelling, noncanonical/mismatched roots, unsupported target kinds, and static symlink/junction/hardlink escapes before invoking a direct file operation. Existing-file and new-file parents need distinct validation. The exact path bytes and observed target identity join the operation digest.

If the executor uses native Pi file tools, do not claim those tools provide an atomic expected-hash update or race-free containment: `ToolDefinitionPort.execute` exposes neither a CAS transaction nor a rooted descriptor. Serialize Arbiter-owned writes, refuse known stale preconditions, check before/after observations, and never replay or restore blindly over observed intervening edits. These observations are not atomic protection against every concurrent external edit or path swap; report their limits and any uncertainty honestly. If product language promises that even a concurrently swapped path cannot redirect writes, implement and qualify a safe file-effect primitive first. Native task **NT-10** is the integration seam; it must not silently widen the current artifact store into an arbitrary source executor.

### 3.2 Operation request and response

A child proxy sends a bounded envelope containing protocol version, parent-issued child/run binding, a monotonically increasing operation sequence, an opaque request ID, exact tool name, canonical JSON tool parameters, and a digest over those parameters and the admitted execution profile. Authentication is transport-owned. The parent resolves the binding from its registry; it does not trust fields that purport to grant authority.

The parent response distinguishes these facts:

- **Admission:** denied, cancelled, expired, revoked, admitted, or unavailable.
- **Execution:** not started, executing, completed, failed, or outcome unknown.
- **Containment:** not applicable, running, verified stopped, or unverified.
- **Observation:** exact effect/result observation, observed target state only, unavailable, or stale.
- **Recovery:** none, read-only reconciliation available, explicit new operation required, or dependent resource held.

Do not flatten all five into `accepted` or `degraded`. The child judgment remains a model result. Parent-observed operation and cleanup facts are separate. A model returning `{"state":"accepted"}` cannot override a refused required mutation or unresolved effect. A legitimate no-change author task can still complete, with an honest no-change effect summary; qualification must separately demonstrate real write, edit, and command execution.

### 3.3 Transport

Recommended transport: a distinct parent-owned loopback endpoint or equivalent private local IPC, with a short-lived per-child random capability delivered through a **new bounded fd3 envelope version**. Keep the existing strict RPC stream for Pi messages and the one attestation request. Do not insert ad hoc JSON records into stdout that the current parser cannot distinguish from Pi protocol.

A proposed v2 bootstrap envelope contains the existing nonce plus only the internal endpoint and purpose-bound token material required by that managed child. The runner and child bundle negotiate/require the same supported version before task submission. The Windows supervisor's existing raw fd3 forwarding must be tested with the new bound; do not repurpose fd4–fd7. A malformed, truncated, oversized, replayed, or unsupported envelope keeps mutation blocked. Mixed old/new installed bundles fail with a bounded diagnostic, not weaker fallback authority.

Keep the operation token out of prompts, returned tool content, ordinary audit rows, repository files, child subprocess environments, and inference configuration. Revoke it as soon as the child exits or its parent authority retires; close listeners and active requests through owned cleanup. Bind the endpoint to loopback or use a verified local transport. Reject nonlocal peers, wrong method/path/content type, wrong purpose token, unknown bindings, oversize frames, excessive concurrency and sequence reuse. Avoid broad CORS or an unrelated service endpoint. Same-user host compromise is outside the trusted-host guarantee; do not advertise the bearer channel as OS isolation.

## 4. Enforcement and execution order

1. **Parent dispatch admission:** validate exact dispatch data; verify package role classification, actual host caller correlation, enabled repository, strict worktree identity, live affirmative trust, parent mode and current generation. Acquire the bounded run grant. Record its identity and scope without raw secrets. Do not start an author process if the required authority/executor cannot be established.
2. **Managed child startup:** retain exact executable/resource validation, private environment, inference broker, process-tree readiness, one-shot nonce and configuration attestation. Only after the parent accepts that child identity may its run grant become active.
3. **Child final tool boundary:** keep source ownership/bootstrap/final-argument guards. Register write/edit/bash as proxies for delegated effects; do not invoke their local mutation executors after a boolean approval. Read and pure inspection retain their separate capability. The delegated route is explicit and cannot be selected by ordinary tool parameters.
4. **Parent final gate:** authenticate the operation; freeze its actual arguments; resolve current binding; validate direct targets/command profile and resource prerequisites; call the existing Python bridge and descriptor policy; preserve hard-block and warning behavior. A denied policy cannot be overridden by a run grant or UI approval.
5. **Concrete consent:** if policy says `ask`, use the **parent's** real TUI context to show the action, target/cwd, bounded safe command summary, authority profile and consequence. The full frozen bytes are bound internally even if secrets must be redacted from display. Cancellation, missing UI, timeout, thrown UI access, or stale approval produces no execution. Headless authors require a separately supported explicit host authority mechanism; do not silently self-approve.
6. **Revalidation and durable claim:** after every await that can change authority, recheck mode, lifecycle, trust, registry/source ownership, executable/settings identity, arguments, target observations and expiry. Write an exclusive operation claim and ensure its durable result is known before mutation. A journal-write unknown state does not authorize execution.
7. **Owned execution:** execute through a parent-owned effect executor with signal, deadline, output bounds and managed process-tree cleanup. Do not hand back “approved” and then allow an uncontrolled child-local mutation. Keep file effects and shell effects separate because their recovery guarantees differ.
8. **Observation and response:** persist effect outcome and containment observations before acknowledging completed mutation to the child. If the result record or response is lost after the effect, return/recover `unknown` from durable identity rather than repeat it. Tool-result bridge notifications should have one owning route with the same parent operation correlation; avoid both parent and child duplicating a post-write side effect.
9. **Retirement:** after task completion, cancellation, mode/trust/session change, timeout, crash or shutdown, revoke new admission immediately. Finish owned cleanup and read-only reconciliation, retain resource references if cleanup is uncertain, and surface only the affected unresolved work.

### Shell execution and credentials

The currently declared `createBashToolDefinition(cwd, options)` accepts a generic local options record; that declaration does not establish an upstream environment override API. Do not invent one. The existing `background-jobs.ts:piShellLaunch` plus `process-tree.ts` provides a source-visible internal pattern for bounded absolute shell identity, operator command prefix, explicit environment, deadlines and managed cleanup. An internal delegated executor can reuse/extract that behavior, or run the native tool in a separately owned helper with a verified safe environment. It must qualify whichever concrete route it implements.

Preserve the child's credential-blind environment guarantee. Parent-mediated commands must not inherit `process.env` wholesale or gain upstream provider credentials merely because the process now belongs to the parent. Use a bounded operator-config projection/private home as appropriate and strip both inference and operation bearer tokens from command environments. Record environment/profile **identity**, not secret values. Preserve supported shell prefix and platform behavior; do not quietly substitute a different shell or ignore an operator setting.

An approved command can execute project code. A matching command string such as `npm test` is not evidence that its scripts cannot write elsewhere or contact the network. The trusted-host profile states this plainly. Direct push/publish/dependency/network commands remain subject to their existing action-class policies and concrete consent. A stronger offline or path-confined profile must use an actually enforced backend, prove its subprocess behavior, and fail if that backend is unavailable.

## 5. Durable outcomes and interruption recovery

Use a small bounded journal with **one agreed host bookkeeping owner**. Choose its exact path/schema in PI-D01/PI-D04 with NT-10 and the shared recovery contract. Git-common or other host-owned bookkeeping may remain outside the artifact evidence store. Register and validate the closed output namespace with NT-02 **only if the implementation uses the artifact reserved root**; do not require an artifact-store journal or impose a global pending-journal guard on every host effect. If a shared store is selected, preserve its real integrity prerequisites until that store is reconciled, while semantic task/delegation conflicts remain resource-scoped. Do not assume existing native artifact APIs already support arbitrary source effects. Records belong to the observed repository/worktree and an owner/version. Defeat linked-path adoption, bound individual and total data, and preserve unknown old-version records for read-only inspection rather than deleting them.

Suggested record fields include run/grant/child/operation IDs, parent tool-call correlation, generation, role, policy/executor profile, repository/worktree identity, exact request digest, target/precondition observations, admitted consent source, transition sequence, timestamps used for explanation, effect references, containment observations, and recovery disposition. Raw credentials, prompts, full secret-bearing command text and file contents do not belong in ordinary logs. If an encrypted or private recovery payload is required to reconstruct a file intent, specify its owner, bounds and retention deliberately; hashes alone cannot reconstruct missing contents.

| State | Event and guard | Next state and side effects | Retry/recovery rule |
|---|---|---|---|
| Proposed | Parent denies policy, UI declines, identity is invalid, or scope is unavailable | Refused/cancelled; no executor call | A changed legitimate request can be submitted as a new operation after correction. Do not permanently blacklist a task for a correctable request. |
| Proposed | Parent confirms exact operation; all live checks still match | Admitted | Admission expires with its generation and deadline. |
| Admitted | Exclusive durable claim is confirmed | Claimed | Only this claim may execute the exact digest. A concurrent duplicate joins/observes it. |
| Admitted | Claim write fails or is uncertain | Admission unavailable/claim unknown; no new effect | Inspect the journal identity read-only. Do not infer absence from a failed append. |
| Claimed | Revalidation succeeds immediately before owned execution | Executing | One live executor owns the claim. |
| Claimed | Authority or expected target changed before execution | Refused/stale; record no execution if observed | New corrected request requires new admission. |
| Executing | Executor finishes and outcome/containment are durably observed | Observed completed or observed failed | Return the stored response to an identical retry. A failed command is not automatically idempotent. |
| Executing | Parent/child disconnects, process times out, output overflows or response is lost | Settling/unknown with owned process/resource references | Stop new conflicting work; run bounded cleanup independently of the cancelled request signal; re-observe. |
| Executing | Source file equals desired hash after a crash, but the operation's durable completion is absent | Observed desired state, causal outcome uncertain | Do not claim “this operation executed once.” Preserve the weaker observation; do not automatically repeat or roll back. |
| Any recorded operation | Same operation ID and same digest is retried | Return current/stored state; never a second executor | Live requests can wait on the same result within bounds. |
| Any recorded operation | Same ID with a different digest or binding | Protocol rejection | No effect, no overwrite of old evidence. |
| Unknown/settling | Read-only observation proves owned process stopped and resource state is known | Reconciled observation or explicit unresolved conflict | A human/agent can choose an explicit new operation after reviewing facts. Recovery is not new author dispatch. |
| Retired grant | Restart or new parent session encounters old record | Revoked authority plus recoverable observation | Never reconstruct a live mutation token from disk or accept old approvals. |

For source writes, never restore a before-image blindly over an intervening user edit. For shell commands and external effects, generic automatic replay is unsafe. Preserve exact references and require effect-specific observation. For Git farm receipts, preserve commit/tree/run identities and rebuild reporting from those observations; do not force-reset task branches or redispatch authors merely because a report file is missing.

The shared recovery UX should issue one bounded startup/reentry notice with affected resources and an inspection action. It must not become a mandatory “acknowledge all historical records” gate. Disjoint work continues. If an unknown shell effect has genuinely unbounded affected resources, state that limitation and require scoped reconciliation before claiming those resources are safe; do not pretend a lexical command classifier identifies every dependency.

## 6. Revocation, concurrency, and ownership

| Event | New admission | Existing work | Recovery visibility |
|---|---|---|---|
| Explicit child/task cancel or its deadline | Retire that grant and queued operations | Cancel owned execution, verify containment, preserve uncertain result | Show that task's state; unrelated tasks continue. |
| Parent mode changes to plan | Deny/retire child mutation grants | Cancel pending approvals; settle effects already started; preserve existing bounded native planning exception | Reads/planning remain available under their own guards. |
| Project trust becomes missing/false/throws | Retire all governed mutation authority for that project lifecycle | Stop owned work and cleanup | This is an authority failure, not merely a dependent-work conflict. |
| Session switch/fork/reload/shutdown | Retire old generation; new session has no inherited grants | Owned cleanup continues without admitting new mutation | New lifecycle can inspect old records, not spend old tokens. |
| Wrapper owner or native executable/settings identity changes | Refuse the affected operation/grant | Do not execute a replacement definition based on old consent | Fixed bounded diagnostic; require fresh valid admission. |
| Two identical operation requests race | One claim/executor only | Second awaits or reads the same durable result | One operation identity, no duplicate side effect. |
| Different operations overlap the same admitted resource | Serialize or reject stale preconditions | Keep exact owner/expected state | Conflict is scoped to the dependent resource. |
| Disjoint author grants in different dispatches | Preserve explicit global/per-repository concurrency ceiling | First implementation may serialize repository mutations while allowing disjoint reads | Do not claim parallel writers are supported until tested. Retain current at-most-one-author per dispatch. |
| Reviewer uses bash | Permit only actions admitted for its actual role and parent policy | A role label does not magically make `bash` read-only | Never equate all reviewer bash with pure inspection; inherited tool lists remain ceilings, not unrestricted permission. |
| Child retries after correction | Revalidate as a new operation with a new ID and current authority | Old refused evidence remains immutable | Corrected debug/reviewer resubmission is allowed. No blanket permanent stale ban. |

Do not let a renderer, status callback, best-effort audit display, or activity identity determine authority. Likewise, generation checks that suppress stale UI must not suppress cleanup that is necessary to release an owned process or resource. The sidebar/footer fix is a rendering lifecycle task; the delegation executor needs a separate settling owner.

## 7. Required tests and evidence ladder

The tests below are acceptance obligations, not claims that they have run. Keep every existing hard-boundary regression. The new tests must fail against the pinned implementation where the specific bug exists; they must not merely mirror a new enum declaration.

### Protocol and permission rejection cases

- Missing/incorrect/replayed nonce or token; wrong purpose; sibling/run/generation mismatch; unknown protocol version; truncated/oversized envelope; unexpected field; duplicate operation ID with changed bytes; after-expiry and after-revocation messages: zero executor calls.
- Project trust absent/false/throwing; plan mode; wrapper source drift; descriptor or executable identity change; no parent TUI; cancellation or UI timeout; bridge hard block; audit/journal admission failure: zero mutation. Bridge warnings remain advisory only when the ordinary policy path allows them.
- Freeze final parameters before approval and revalidate after bridge, UI, journal and any other await. Mutate nested arrays, getters/proxies, cwd, owner, current mode and raw request during each await. Reject without leaking secret-shaped details.
- Path traversal, Windows drive/UNC/case variants, new-parent absence, symlink/junction/hardlink outside root, linked journal directory, replaced target, and observation failure: test the advertised admission guarantee. If a strong confinement profile exists, add adversarial concurrent path-swap and subprocess escape tests against the real backend; passing ordinary admission tests does not establish confinement.
- A child never self-grants by adding parameters, setting the ambient child marker, selecting an author role, requesting an RPC UI confirmation, replaying an old grant, or registering a recursive dispatcher. A denied reviewer mutation cannot be relabeled as inspection by its own string.

### Functional author acceptance

Against the exact packaged extension and admitted Pi runtime in a disposable trusted repository, run an author that performs an admitted write, an edit of the resulting file, and an admitted command that creates/verifies a fixture result. The parent must observe the exact arguments and resulting bytes/process outcome, show the parent permission UI, persist operation identity before each mutation, and return the corresponding tool result. Check a reviewer can inspect those results and a chain preserves bounded/redacted prior output.

A handshake-only test, synthetic `accepted` child response, fake tool factory counter, source-module import, or a test that only verifies mutations remain blocked does **not** satisfy this gate. Keep them as lower-level evidence. Use a deterministic local provider fixture to drive the real child loop if appropriate; label that provider substitution. Add a genuine user-visible parent TUI confirmation observation, because an injected `confirm: async () => true` proves neither rendering nor human consent routing. Paid remote provider use is not required to prove local effect authority, and credentials must never appear in the test receipt.

### Interruption and concurrency

Inject failure before durable claim; after claim/before execution; during execution; after effect/before outcome persistence; after outcome/before response; during token revocation; during cleanup; and after a parent restart. Verify that identical retries do not duplicate effects, different-input reuse is rejected, uncertain operations remain uncertain, and disjoint ordinary work continues. For commands, prove process descendants are stopped or report containment unverified; killing the observation client is insufficient.

Race two operations on one file, two identical calls, a revoked old generation against a valid new one, and a user edit during reconciliation. Verify no stale approval executes, no blind rollback overwrites the user, no token survives retirement, no late listener resurrects authority, and cleanup completes after admission is revoked. Existing POSIX and Windows supervision tests remain required. Windows tests must cover the actual fd3 envelope forwarding and helper protocol, not a POSIX-only pipe double.

### Packaging and host matrix

The source currently admits Pi **1.1.0**, Node **at least 22.19.0**, and Python **3**. This is an admission statement, not proof that every Node/platform combination is qualified. Derive the release candidate's matrix from the program's actual supported-host policy and qualify exact selected artifacts on each claimed platform. Record package SHA-256, loaded parent/child/helper bundle digests, Pi artifact identity, Node/Python versions, OS/architecture, policy version, executor profile, test route and substitutions.

Keep optional artifact-approval support separate: the private approval entry is currently gated to Pi 1.0.2 while ordinary compatibility admits 1.1.0; the cold-package path's synthetic policy event is not a parent-observed ordinary tool approval. PI-C01 must resolve that optional capability honestly. It must not turn routine progress or child authorship into a new artifact-attestation ceremony.

After staging packages, install from the exact candidate tarball in a disposable home, execute the functional author and rejection/recovery cells, then test update/disable/uninstall and mixed-bundle refusal. The final public publication receipt must refer to the identical qualified bytes. Any rebuild after qualification needs a new digest and relevant rerun. An older package rollback must preserve the new journal for read-only diagnosis and refuse unsupported record versions without deleting user work.

## 8. Task sequence and bounded rollout

The complete task details are in `surfaces-tasks.json`. The Pi critical path is:

1. **PI-D01:** freeze the versioned grant/effect/transport contract, explicit trust and evidence boundaries, and one host bookkeeping owner; agree the NT-10 seam and conditional artifact namespace registration.
2. **PI-D02:** extract or reuse the parent final operation gate, plumb parent mode and caller/lifecycle authority through dispatch, and add concrete per-operation consent.
3. **PI-D03:** implement authenticated child proxies, owned parent execution, safe environment and managed transport, without removing current child guards.
4. **PI-D04:** implement exclusive claims, durable outcomes, duplicate handling and read-only reconciliation; integrate the shared interruption notification without restoring authority.
5. **PI-D05:** complete revocation, expiry, dependent-resource conflict handling, bounded concurrency and settlement ownership.
6. **PI-D06:** project truthful capability/diagnostic/help output and distinguish author execution, reviewer availability, artifact approval and evidence mode.
7. **PI-D07:** qualify functional authorship and all negative/recovery cells against the exact candidate package on the supported matrix.

PI-L01/PI-L02 independently correct persona readiness and sidebar resurrection. DIST-M01 closes the release manifest incompatibility. FARM-R01–R03 correct receipt recovery, containment loss and unknown Git observations. SBX-C01–C03 correct cache identity, output-overflow containment and resource observation. SITE-U01/U02 correct search rejection and reconnect behavior. BUILD-G01/G02 address generation and compatibility authorization. DIST-M02 preserves marketplace-specific promotion semantics while making uncertain outcomes explicit. PI-C01 and SBX-D01–D04/HOST-D01 correct capability/documentation contradictions without broadening permissions or deleting legitimate host differences.

During integration, keep any incomplete author implementation disabled or clearly degraded. This is a safe intermediate state, not a release acceptance exemption. Re-enabling functional authorship requires PI-D07 evidence. Do not merge a half-completed author feature to main and schedule its safety/functional completion for after the major release.

## 9. ADR and claim-registry changes to propose

These are proposed decisions; assign actual ADR numbers only after checking the current registry.

| Proposed decision record | Required content | Existing decision treatment |
|---|---|---|
| Scoped Pi parent delegation | Parent owns permission/effect authority; exact operations; child bootstrap is configuration attestation; no self-grant; explicit trusted-host versus confined profiles; functional author acceptance | Amend/supersede only conflicting passages of current Pi child/isolation/permission ADRs. Preserve credential isolation, final arguments, source ownership and platform containment requirements. |
| Durable effect observation and recovery | Separate permission, effect, observation and containment; exclusive operation identity; no blind replay; dependent-work-only conflict scope; settled cleanup after revocation | Share only true invariants across native, Python and TS. Do not require one universal workflow enum or expand an artifact journal into arbitrary effects by naming it a kernel. |
| Capability and evidence vocabulary | Implemented/admitted/qualified/released; source/fake-host/real-host/candidate-artifact/published-artifact evidence; optional artifact approval kept distinct from ordinary permission | Correct old broad Pi support/refusal claims. An accepted ADR is not qualification evidence. |
| Resource lifetime and build cache | Sandbox shell detach versus explicit destroy; frozen cleanup targets; unknown resource discovery; stable builder/platform-aware cache identity; effective offline policy | Preserve persistent-box behavior, explicit broad prune, keep-volume exceptions, supported Node/Python fallback, and the separate Claude-inside entrypoint. |
| Generated surface ownership and compatibility removal | One canonical capability/compatibility contract; complete staged outputs; history-backed removal authorization and approved floor exceptions | Replace slogan-only enforcement claims. Preserve host-specific handwritten adapters and approved compatibility differences. |

The registry should record parent delegation as **planned** until implemented, then **implemented** against the integration commit, **qualified** only for the exact tested artifact/runtime/profile, and **released** only after publication metadata and bytes agree. Do not fill a single boolean `Pi supported` cell with these different facts. Retain the historical audit and probes as commit-bound evidence; replace current claims only after their owning source and propagation are inspected.

## 10. Rollback and remaining decisions

Rollback revokes new grants first, stops/observes owned processes, preserves journals and user source changes, and restores the last qualified adapter/package through the program's existing distribution mechanism. It does not reset a worktree merely to recreate a clean test state, delete unresolved records, or reinterpret an unknown operation as not executed. Do not attempt generic compensation for arbitrary shell commands. A pre-release integration rollback can retain the old read-only degraded author behavior temporarily; the program remains incomplete until functional support is restored and qualified.

The central implementation direction is already chosen by the user. The receiving agent may make routine internal schema and implementation choices consistent with it. Routine persistence, retention bounds and internal storage choices that implement the approved durable recovery design do not require repeat approval. Bring B a concrete proposal only for a material new public guarantee, destructive data loss or retention reduction, expanded network/authority scope, or a changed supported-host commitment. SMARTS progress/evidence semantics remain a separate B-plus-receiving-agent discussion and must not be silently decided by this Pi design.

### Confirmed findings

The current child has no usable mutator permission route; current parent dispatch lacks the mode/permission port needed to supply one; final-argument and ownership guards are substantive and must be retained; the existing audit sink and process supervisor provide useful boundaries but not a complete effect journal. The linked task ledger covers all 25 owned audit findings.

### Material contradictions

Author tool advertisement versus actual RPC permission path; readiness versus missing persona; optional Pi approval/runtime mismatch; qualified manifest versus farm parser; “retry author” versus already completed farm effects; sandbox lifetime/storage/network/fallback claims versus the actual driver; compatibility slogan versus history authorization.

### Canon or claim-registry delta

Add capability-specific admission/evidence/release status, exact operation versus confinement language, durable observation/recovery terms, and the explicit host/surface exceptions described above. Do not claim main-source behavior is released.

### Affected surfaces

Pi parent/child/runner/guard/policy/session/status/package and qualification surfaces; farm execution/reports; native manifest consumers and build producers; sandbox driver/commands/skills/README; site search/drawer/build generators; marketplace promotion; compatibility metadata and derived docs; Claude dormant/write-scope claims. The JSON ledger provides exact owning paths and propagation tasks.

### Decisions requiring user approval

No repeat approval is required for the selected functional delegation direction. Any broader OS confinement promise, newly enabled sandbox network mode, or new release/support scope requires a concrete separately reviewable decision. SMARTS progress/evidence remains deferred as requested.

### Verification still required

All new implementation, behavioral tests, exact candidate packages and supported-host cells remain to be produced. The earlier probes are source-level diagnosis, not host qualification. No repository source or external release was changed while preparing this handoff.

### Recommended next action

On the isolated integration branch, implement PI-D01 and the shared durable-observation contracts first, then complete the parent-gated functional author path and its interruption tests. Work independent surface corrections in parallel, integrate all program slices, qualify exact artifacts, and perform the final major release only after the full program is complete.

## Source ledger and review boundary

The prior audit fully read the owned runtime files and records their coverage in `audit-work/surfaces-read-files.txt`. This handoff re-read the key authority and test sections below. Targeted test reads are not claimed as a full test-suite execution. No test was run in this handoff turn, and no upstream Pi source was fetched anew; the design explicitly requires exact runtime verification during implementation.

- `arbiterForge/codeArbiter@fd7eb34b2da439551443d09526ab48fd1d1bb9bf:plugins/ca-pi/tools/src/contracts.ts` — existing tool/context/lifecycle ports.
- `arbiterForge/codeArbiter@fd7eb34b2da439551443d09526ab48fd1d1bb9bf:plugins/ca-pi/tools/src/pi-api.d.ts` — local structural host declarations, fully re-read.
- `arbiterForge/codeArbiter@fd7eb34b2da439551443d09526ab48fd1d1bb9bf:plugins/ca-pi/tools/src/child-extension.ts` — bootstrap, wrapper installation, nonce and child runtime construction, fully re-read.
- `arbiterForge/codeArbiter@fd7eb34b2da439551443d09526ab48fd1d1bb9bf:plugins/ca-pi/tools/src/extension.ts` — parent dispatch admission, session lifecycle and final enforcement wiring; targeted re-read.
- `arbiterForge/codeArbiter@fd7eb34b2da439551443d09526ab48fd1d1bb9bf:plugins/ca-pi/tools/src/dispatch.ts` — exact request schema, role/concurrency bounds, child result and registration path; targeted re-read.
- `arbiterForge/codeArbiter@fd7eb34b2da439551443d09526ab48fd1d1bb9bf:plugins/ca-pi/tools/src/runner.ts` — exact launch identity, RPC argv, parser/attestation and managed execution/cleanup; targeted re-read.
- `arbiterForge/codeArbiter@fd7eb34b2da439551443d09526ab48fd1d1bb9bf:plugins/ca-pi/tools/src/tool-guard.ts` — final canonical arguments, permission/audit/revalidation, wrapper ownership and lifecycle; targeted re-read.
- `arbiterForge/codeArbiter@fd7eb34b2da439551443d09526ab48fd1d1bb9bf:plugins/ca-pi/tools/src/policy.ts` — descriptor/action policy and existing planning exception; targeted re-read.
- `arbiterForge/codeArbiter@fd7eb34b2da439551443d09526ab48fd1d1bb9bf:plugins/ca-pi/tools/src/audit-sink.ts` — actual append identity/sync behavior and false-return ambiguity, fully re-read.
- `arbiterForge/codeArbiter@fd7eb34b2da439551443d09526ab48fd1d1bb9bf:plugins/ca-pi/tools/src/path-boundary.ts` — lexical versus canonical fallback semantics, fully re-read.
- `arbiterForge/codeArbiter@fd7eb34b2da439551443d09526ab48fd1d1bb9bf:plugins/ca-pi/tools/src/background-jobs.ts` — bounded environment, `piShellLaunch`, managed process pattern; targeted re-read.
- `arbiterForge/codeArbiter@fd7eb34b2da439551443d09526ab48fd1d1bb9bf:plugins/ca-pi/tools/src/process-tree.ts` and `plugins/ca-pi/tools/src/windows-supervisor.ts` — full prior audit; fd layout and reuse sites checked again.
- `arbiterForge/codeArbiter@fd7eb34b2da439551443d09526ab48fd1d1bb9bf:plugins/ca-pi/tools/src/child-env.ts` and `plugins/ca-pi/tools/src/inference-broker.ts` — full prior audit; credential/isolation boundary retained rather than broadened.
- `arbiterForge/codeArbiter@fd7eb34b2da439551443d09526ab48fd1d1bb9bf:plugins/ca-pi/tools/src/compatibility.ts` — admitted Pi/Node/Python values, fully re-read.
- `arbiterForge/codeArbiter@fd7eb34b2da439551443d09526ab48fd1d1bb9bf:plugins/ca-pi/tools/test/runner-isolation.test.ts` — child adapter cases 1480–1634 re-read; other protocol cases inventoried and linked to source behavior.
- `arbiterForge/codeArbiter@fd7eb34b2da439551443d09526ab48fd1d1bb9bf:plugins/ca-pi/tools/test/tool-guard.test.ts` — permission cases 350–625, descriptor/ownership cases 1630–1705 re-read; relevant drift/trust cases inventoried.
- `arbiterForge/codeArbiter@fd7eb34b2da439551443d09526ab48fd1d1bb9bf:plugins/ca-pi/tools/test/dispatch.test.ts` — request/fake-child contract and production admission/lifecycle cases re-read.
- `arbiterForge/codeArbiter@fd7eb34b2da439551443d09526ab48fd1d1bb9bf:plugins/ca-pi/tools/test/final-arguments-live.test.ts` — installed-host loader/registry versus substituted factories/bridge boundary, fully re-read.

Additional exact finding references, targeted test locations, original confidence levels and probes are retained in `surfaces-tasks.json`; they are not silently upgraded to released behavior.
