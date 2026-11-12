# Hook and workflow implementation design

## Status, authority, and delivery boundary

This is an implementation handoff, not a claim that the implementation has changed. Its source baseline is `arbiterForge/codeArbiter@fd7eb34b2da439551443d09526ab48fd1d1bb9bf`. Findings and transition evidence remain in `audit-work/hooks.json`, `workflows.json`, `generator-extra.json`, and `pi-qualification-extra.json`. The receiving CLI agent must compare its checkout with that commit and reconcile changed owners before applying a task. Source at this commit is development behavior; it is not evidence that an exact released package has these changes.

The user has selected these outcomes: conflicts pause only dependent work; corrected debug and reviewer submissions may be submitted again; ordinary work gains durable interruption recovery that does not create a universal gate; ADR changes belong in the handoff. The parent workstream owns the integration branch and eventual major release. All tasks here land on that held integration branch, with no intermediate merge or publication presented as completion of the whole effort. The numeric release version, target set, tags, release evidence, and publication sequence belong to the root release plan.

Two decisions remain separate. The dependency reviewer's maintenance-only HIGH exception conflicts with the common HIGH-to-BLOCK rule (`W-F03`); permission to resubmit does not resolve that policy. The progress/evidence distinction is being reviewed by B and the receiving agent through SMARTS in the native workstream. Neither decision blocks independent corrections in this document. A major-release instruction also does not authorize removal of an unnamed compatibility route.

The implementation strategy is a small set of explicit transition contracts at existing owners. It does not replace the product with one global state engine, introduce a daemon or database, or turn bookkeeping into authorization. Shared Python remains the owner of hook semantics; host adapters translate observed host events; native evidence retains its independent validity rules; generated surfaces derive facts from the relevant owner.

## What changes and what stays authoritative

| Finding or boundary | Selected treatment | Authoritative owner and evidence |
|---|---|---|
| `HOOK-F01` | Deliver the selected persona on every real mode transition, including A → B → A, while deduplicating repeated delivery of the same transition. | `core/pysrc/prompt-submit.py:_dedup_key/_already_injected/_inject_claude`; `_modelib.py:flip`; `audit-work/probe_mode_results.json`. |
| `HOOK-F02` | Return and render truthful partial outcomes after mode marker commit and audit failure; retain owed-audit recovery. | `_modelib.py:flip/ledger_backs`; `prompt-submit.py:_effective_mode/_flip_stderr_line`; same probe. |
| `HOOK-F03` | Make doctor recognize the actual scoped Pi package through the shared host/package identity contract. | `core/pysrc/doctor.py:check_payload`; `plugins/ca-pi/hooks/_host.py`; `plugins/ca-pi/package.json`; diagnostic probe. |
| `HOOK-F04` | Reconcile the Python producer and native completion consumer's bounded launch-file contract. | `_artifactauthoritylib.py:_bind_commands/_native_launch/_npm_workspace_runner`; native task `NT-04`; launch-binding probe. |
| `HOOK-F05` | Restore spinner settings only if their current value still matches the value owned by the installer. | `core/pysrc/wire-statusline.py:cmd_uninstall/_uninstall_spinner_verbs`; diagnostic probe. |
| `HOOK-B01`, `W-F02` | Permit corrected debug inputs, with error categories and attempt linkage; retain causal, freshness, and authorization requirements. | `_debughandofflib.py`; `debug-handoff.py`; debug skill and preparation reference. |
| `HOOK-B02`, `W-F05` | Describe prompt-submit as the persona-delivery owner and startup as setup/briefing; disclose actual startup/global/Git-common side effects. | `prompt-submit.py`, `session-start.py`, `_githooks.py`, `_taskexcludelib.py`; init and README surfaces. |
| `HOOK-B03`, `W-F06` | Correct the help text to the existing whole staged candidate binding. | `security-pass.py`, `_sensitivelib.py:staged_candidate_binding`, `_bashguardlib.py`, `git-enforce.py`; override and security-record includes. |
| `HOOK-B04`, `W-F04` | Implement the durable recovery contract below; terminal promotion remains an explicit workflow action. | `includes/harvest.md`, `session-start.py`, `_standuplib.py`, `knowledge.py`, standup owner. |
| `HOOK-B05` | Integrate with host task `DIST-M01` for optional manifest qualification; preserve platform/digest/native-tested checks. | `_artifactlib.py:ArtifactClient._open_binary`; farm manifest consumer. |
| `W-F01` | Scope conflict pauses to the actual dependency set and preserve independent authorized work. | Conflict command, SPRINT, context-check, ADR0043. |
| `W-F03` | Isolate the HIGH disposition decision and record the selected rule before implementing it. | Dependency reviewer and common reviewer contract. |
| `W-F07` | Describe one detached `gh` watch process accurately; it still refreshes checks. | Watch command; receiving agent verifies supported `gh pr checks --help` and official current command documentation. |
| `W-F08` | Derive command signatures, Tribunal count, and reviewer summaries from explicit owner metadata. | COMMANDS, command/skill owners, agents index and bodies. |
| `W-F09` | Align registry and validator with the public compatibility rule; retain aliases until separately approved named removal. | Command route registry, build-surface, compatibility include, release-state observer. |
| `GEN-F01` | Correct the nudge threshold description to estimated avoidable context freed, without changing its runtime predicate. | `configuration-reference.ts`; `_prunelib.py:nudge_decision`. |
| `GEN-F02` | Report bounded static extraction honestly; improve lexical masking and expose dynamic/omitted parts. | `extract-hook-gates.ts`, `render-hooks-reference.ts`; actual dynamic recovery suffixes in `_bashguardlib.py`. |
| `GEN-B01` | Globally reserve emitted slugs and protect published routes. | `assign-slugs.ts`; this is a source-proven helper edge case, not an observed broken production URL. |
| Pi qualification supplement | Preserve disposable-home, real-runtime discovery, and benchmark evidence boundaries in the new qualification matrix. | Three test-only helpers listed below; these are not installed runtime state. |

## Durable interruption recovery: precise product behavior

### The obligation being recovered

The first registered kind is `terminal-harvest`. A workflow discovers a bounded, eligible follow-up and records the obligation before depending on conversation retention. The record contains enough sanitized information to re-present or reconcile that exact candidate. Registration is ordinary local bookkeeping for already authorized work. It is not a decision to create a task, change an open question, publish an issue, accept an ADR, finish work, approve review, or delete anything.

The existing terminal step remains where the workflow applies its harvest policy. The change is that an interrupted workflow has a durable local continuation. Registration at terminal time alone would reproduce the defect. Conversely, the implementation must not claim to recover a finding that was never successfully registered. A failed registration reports `durable: false` with a bounded reason and allows independent work to continue.

Known producer sites are the TDD Phase 6 findings, brainstorming and planning triage findings, commit-gate set-asides, checkpoint DEFERRABLE findings, and low-confidence sprint decisions identified in `core/surface/includes/harvest.md`. The same registered-kind architecture can later support a specific ordinary continuation, but this release does not grant a generic instruction-replay facility. An unregistered kind is unavailable and cannot supply executable code, arbitrary target paths, or shell text to the runner.

### Storage and ownership

Add a shared Python owner, proposed as `core/pysrc/_workflowrecoverylib.py`, and a bounded CLI, proposed as `core/pysrc/workflow-recovery.py`. Put the closed schema and kind declarations in proposed `core/workflow-recovery-contract.json`, following the repository's existing root `core/*-contract.json` pattern. These are proposed new paths, not claims about existing files.

Store records under the repository's resolved Git-common directory in an owned `codearbiter/workflow-recovery/v1/` subtree. Use the existing safe Git-common/worktree resolution patterns from `_artifactauthoritylib.py` and `_reconciliationlib.py`; do not accept a caller-provided arbitrary storage root in installed operation. Bind each record to the repository instance, its selected native project identity when present, the originating worktree, and an exact workflow run. A Git-common store survives interruption and branch switching locally. It is not portable work evidence, a cloud backup, or a claim of durability after deletion of that repository's Git directory.

Git-common placement avoids inventing a new `.codearbiter` document kind. Register the new runtime path and owner explicitly in the product's storage/inventory/cleanup/doctor documentation and relevant packaging checks. Native snapshot/evidence policies already exclude Git metadata (`core/artifacts/internal/validate/input_policy.go`); preserve that exclusion. No plan may cite recovery bookkeeping as reviewed input or completion evidence. If a later implementation adds a native consumer or a `.codearbiter` projection, that is an explicit additional registry/schema task and must be admitted by every relevant reader before it ships.

The local owner must validate exact path containment, directory/file type, and the same symlink/ownership requirements used by comparable protected spools. Reads must not follow a caller-supplied path out of the owned subtree. Registration and transition writes use an OS-held lock, revision compare-and-swap, atomic replace, and a durable commit result that distinguishes written, observed, and durability-uncertain outcomes. Do not claim no effect merely because an error occurred after the commit point; `_planfilelib.py` is an existing example of that distinction.

Use canonical records keyed by obligation ID with a bounded paged index. Index maintenance is part of a recoverable write transaction, not an independent best-effort write that can permanently hide an acknowledged record. A small durable write intent under the writer lock can recover the record/index pair; prove each interruption point. Automatic read-only scans inspect the bounded transaction header before an index page and report partial/unavailable when repair is needed; the explicit recovery/write path performs the repair under its lock. Readers never translate an unreadable or incomplete index into “nothing pending.” This is a file protocol, not a new database service.

### Minimal closed record

| Field group | Required meaning |
|---|---|
| Version and kind | Exact schema version and an installed registered kind, initially `terminal-harvest`. Unknown versions are preserved and reported unavailable. |
| Identity | Repository-local ID; native `project_id` if already available; worktree identity; `workflow_run_id`; stable `obligation_id`; exact source origin including its item suffix. |
| Work binding | Native work ID, exact legacy origin/row identity, or explicit `none` for authorized ordinary work without an enrolled task. Do not require task creation merely to register recovery. |
| Source binding | Workflow/phase, source locator, source fingerprint, and source branch/base observations where relevant. Branch names are observations, not sufficient identity. |
| Candidate | Bounded sanitized title/description, work/decision kind, blocking classification, and provenance. Store no full transcript, raw debug packet, secret, credential, raw rejected payload, or arbitrary command. |
| Lifecycle | State, monotonically increasing record revision, created/updated timestamps, reason code, previous attempt linkage, and explicit last transition. Time is diagnostic, not permission. |
| Claim | Attempt ID, host/session and process-instance identity, claim nonce, expected record revision, and intended effect operation ID. The claim is not an authorization grant. |
| Effect binding | Selected owner, target kind, exact origin, immutable candidate revision, operation ID, and expected target revision/hash when the target supports them. |
| Outcome | Observed target identity and receipt/digest; disposition such as promoted, reused, explicitly declined, superseded, or explicitly cancelled; evidence for that disposition. |

Do not persist “authorized: true” as a reusable permission ticket. Record the relevant authority source or scoped parent delegation reference only as context and revalidate the actual current host/user boundary at effect time. Registering or reading a local obligation must not require a new user approval ceremony. Existing interactive harvest confirmation remains specific to promotion; an already authorized sprint may use its existing in-scope promotion authority. Revocation, actual denial, an explicit stop, or a changed scope continues to constrain the affected effect.

### Three identities, with different jobs

1. **Obligation ID** is stable across discovery replay, process restart, and session reentry. Derive it from canonical repository/workflow/kind/exact-origin identity, or persist an opaque ID with an exact unique origin index. Do not derive it from a timestamp or the current session alone.
2. **Candidate revision** changes when an authorized correction changes the proposed content. Compare-and-swap protects a concurrent edit; the old candidate remains in transition history. A new revision does not overwrite an effect of unknown outcome.
3. **Effect operation ID** binds obligation ID, candidate revision, target owner, and requested action. The exact retry uses the same ID and immutable payload. A corrected attempt gets a new linked identity only after the earlier effect is known absent or settled. Target origin deduplication remains a second defense across different workflow runs.

The target operation's real idempotency contract governs retries. Native work creation can use its stable operation identity and exact origin. Legacy work origin deduplication is also valuable, but `_worklib.LegacyClient` does not become a durable operation ledger just because a caller passes an operation ID. After an ambiguous result, look up the exact origin through the selected owner before retrying. Never select a same-title item or choose a different writer as fallback.

### State × event × side effect contract

`unavailable` is a durable unresolved state, not a synonym for discarded or denied. Its reason distinguishes temporary I/O, unsupported version, changed binding, actual authorization denial, corrupt evidence, and an uncertain previous effect. The diagnostic must give the next legitimate action without implying that every reason can be solved by resubmission.

| State | Event and guard | Next state | Required side effects and failure behavior |
|---|---|---|---|
| Absent | Eligible candidate discovered; closed kind/schema and bounded bindings valid | `pending` | Durably register before claiming success. Same identity and same candidate return existing state. No task/issue/decision write. |
| Absent | Invalid, oversize, unknown-kind input or storage unavailable | Absent; unavailable result | Return bounded sanitized diagnostics and `durable: false`. Ordinary unrelated work continues. Do not invent a persisted record. |
| `pending` | Same registration arrives again | `pending` | Return existing ID/revision; no duplicate or rewritten candidate. Different payload is a conflict/correction request, not idempotent success. |
| `pending` | Authorized correction, expected revision matches, no unknown effect | `pending` at new revision | Record corrected candidate and prior linkage. No authority or source truth is invented to make validation pass. |
| `pending` | Startup, prompt reentry, status, or standup scan | `pending` | Read a bounded summary; expose pending count/partial scan and a resume route. Never execute promotion, cleanup, publication, or review automatically. |
| `pending` | Workflow terminal step or explicit resume; current binding and actual effect authority hold; per-obligation lock acquired | `claimed` | Persist claim and immutable effect intent before calling the target adapter. A duplicate claimant returns busy/current state. |
| `pending` | Target ownership ambiguous, source stale, unsupported kind/version, actual scope denied, or required material unavailable | `unavailable` | Retain candidate and precise reason. Pause only this dependent effect. Do not fall back to a second owner or request universal approval. |
| `pending` | Interactive preview declined | `settled: declined` only after its local audit event is durable | Write one idempotent decline event and terminal receipt; no board/question write. If audit commit is uncertain, retain a recoverable attempt. |
| `claimed` | Effect not yet attempted; process remains live | `claimed` | The OS-held per-obligation lock prevents another executor. A timestamp is not proof the owner died. |
| `claimed` | Target reports success and exact target readback proves effect or exact-origin reuse | `settled: promoted/reused` | Persist target ID and outcome receipt. Do not infer parent work completion, review pass, merge, or cleanup. |
| `claimed` | Target response lost or process dies after effect may have committed | `claimed`, then reconciliation | A later executor acquires the released OS lock and queries exact operation/origin. It never blindly replays an unknown effect. |
| `claimed` | Reconciliation proves exact intended effect exists | `settled: promoted/reused` | Record recovered receipt; no duplicate write. Existing independently edited content is not overwritten. |
| `claimed` | Reconciliation proves effect did not commit and current binding/authority still hold | `pending` or a new `claimed` attempt | Preserve the immutable effect identity for exact retry; record the failed attempt. No new permission is fabricated. |
| `claimed` | Outcome cannot be determined, target unavailable, or source/authority changed | `unavailable` | Retain unresolved effect intent and reason. New revisions and effects wait for reconciliation of this obligation only. |
| `claimed` | Another session presents a live/busy claim | `claimed` | Report busy with bounded metadata; no TTL-based theft or global session wait. |
| `unavailable` | Read-only status/reentry | `unavailable` | Show reason and the legitimate recovery route. Suppress repeated identical notices within the session without discarding state. |
| `unavailable` | Relevant condition changes; current bindings and real authority revalidated; previous effect reconciled | `pending` | Record reason-specific recovery. A formatting correction alone cannot clear an authorization denial or explicit stop. |
| `unavailable` | Unknown schema or malformed on-disk record | `unavailable` | Preserve bytes under owned access; no automatic overwrite, deletion, downgrade, or empty-state interpretation. Report only bounded safe metadata. |
| `pending` / `unavailable` | Explicit authorized cancellation or supersession, with no unreconciled effect | `settled: cancelled/superseded` | Retain disposition and link to replacement if any. An absent source or elapsed time alone is insufficient. |
| `settled` | Exact registration, retry, or notification replay | `settled` | Return the terminal receipt/tombstone and target link; no repeated effect or prompt. |
| `settled` | New authorized follow-up after changed facts | New linked obligation/attempt | Keep old history immutable. Do not reopen the old receipt or pretend the previous outcome never happened. |
| Any persisted state | Record/index write fails after a possible commit point | Observed state or explicit uncertain result | Re-read/reconcile; report requested, observed, committed/durable facts separately. Never silently revert a later writer. |

There is no age-triggered `pending → settled` transition, no `error → complete` transition, and no `validation-pass → authorization-granted` transition.

### Claims and interruption recovery

Hold a per-obligation OS lock for the entire local adapter execution and reconciliation window. Keep the global index/writer lock short. An adapter cannot release the only liveness lock and continue mutating while another process is allowed to recover it. If cross-process execution requires a different lock protocol, its owner-instance binding and cancellation semantics must be proved in the same change; a stale timestamp alone is insufficient.

On restart, a persisted claim plus an available OS lock means the previous critical section is no longer held. It does not prove that the target effect failed. The handler first reads the exact selected target and operation/origin identity. Only observed target state decides whether to settle, retry, or report unavailable. An unavailable target never permits a speculative second write.

For a batch, each candidate has its own obligation and outcome. One failed candidate does not erase successfully settled candidates or hold unrelated work hostage. The batch summary names completed, retained, and unavailable IDs. It must not say the entire harvest succeeded merely because one helper returned zero.

### Target adapters and original workflow rules

| Target | Allowed effect | Idempotency and authorization |
|---|---|---|
| Native work | Create/reuse the exact origin using `work.py`, or report a current refusal. | Preserve the native operation ID, current owner/project identity, and exact-origin lookup across active/archive. Never downgrade to a legacy writer. |
| Legacy work | Use the sanctioned `taskwrite.py`/work owner route and existing exact-origin behavior. | Re-read origin across open/archive after uncertainty; keep locking and archive-first semantics. An operation ID echo is not proof of durable execution. |
| Nonblocking decision | Append a deferred decision through a narrowly scoped, idempotent writer. | If no existing writer can supply a stable origin/event ID and CAS/readback, implement that adapter before enabling automatic retry. Do not append duplicate prose on every resume. |
| Blocking decision | Present the existing escalation/resolution route. | Registration is allowed; automatic confirmation and automatic promotion are not. Pause only work actually depending on that unresolved decision. |
| Declined promotion | Append one bounded local decline event with stable identity. | An explicit decline settles this candidate only after its audit outcome is durable; it is not a broad refusal of independent work. |
| GitHub issue or any external publication | No recovery-time automatic effect. | Existing explicit publication authority and workflow apply. Pending local recovery does not authorize sending information or creating remote records. |

Preserve the current harvest rule that candidates are contingent on the work unless the workflow explicitly establishes otherwise. A pending record may survive an interrupted or abandoned branch locally, but that survival does not make a follow-up authoritative on another branch. Reentry must revalidate the source/work binding. A candidate that should survive abandonment can be routed to the existing issue workflow under its actual publication authority; the scanner must not create the issue itself.

Commit-gate's harvest still occurs before explicit staging so promoted work can travel with its originating work commit, as ADR0008 requires. Startup does not stage any path. Nothing in the recovery ledger marks a work item done or changes the commit candidate. Ordinary discovery bookkeeping can be durable locally without becoming a committed project artifact.

### Startup, reentry, and user experience

Use one shared summary projection across `session-start.py`, relevant prompt/reentry paths, the status/standup flows, and the host adapters. Read an existing ledger only for an already active project. A dormant project must not be activated and must not gain a new recovery directory just because a hook ran. Explicit status/recovery can show missing/legacy state honestly.

Proposed hard data bounds are 32 record summaries and 256 KiB per automatic scan, with at most 64 KiB per candidate registration and 32 candidates in one producer batch. These are implementation acceptance limits, not claims about current performance. Payloads that exceed them require explicit bounded batching or a visible unavailable outcome; never silently truncate a candidate into a different obligation. The scan returns `complete`, `partial`, or `unavailable` plus an opaque continuation cursor and observed counts. An unknown total is reported as unknown. A count from a partial scan is a lower bound, not a complete backlog count.

Use a versioned paged index so scanning one page does not enumerate and sort the entire history. A cursor binds index generation and page identity; stale cursors restart a bounded read or report a changed inventory. Before shipping, measure the scan within the actual host startup budget and add timeout handling at existing host boundaries. Do not promise a hard wall-clock limit for arbitrary filesystem I/O merely because the loop checks a deadline.

Display a concise actionable notice, for example: “2 follow-ups from the interrupted fix await harvest; 1 is unavailable because its source changed. Resume these items or keep working.” The recovery status is a projection of the durable ledger, not the truth owner. Suppress the same notice after delivery for the same session/ledger revision, but a mode switch, compaction, or dedup bug must never delete the underlying record. A failed notification does not mean the obligation was settled.

New-session recovery is supported without pretending that a new session owns the old session's grants. The new session can inspect the local pending record and reconcile already attempted effects. It can apply a new effect only within its current real authority. Pi child registration must be bounded to the parent delegation's work/run/origin scope through `PI-D01`–`PI-D05`; its durable observation can feed the shared notice, but recovery never restores a revoked grant. Claude/Codex/Pi should present the same semantic result through their own supported event seams.

### Retention, upgrades, and rollback

Unresolved obligations never disappear because they are old, a budget was exceeded, a branch was deleted, or an agent said “done.” Retain pending/claimed/unavailable state until an observed target effect or an explicit authorized terminal disposition settles it. At capacity, registration reports that it was not durable; it does not evict an older unresolved item. This design bounds individual records and work per read; it does not falsely promise a fixed lifetime disk footprint for an indefinitely retained history.

Settled records may be compacted to small immutable tombstones containing operation/origin identity, terminal disposition, target reference, and receipt digest. Preserve exact ID lookup and deduplication after compaction. Compaction writes and verifies the replacement/index before removing redundant owned bytes. Do not delete a live target, worktree, branch, unrelated transcript, or pending record as part of ledger maintenance. Retention/archival is local runtime housekeeping, not an exception to destructive cleanup authorization. If an implementation wants to relax ADR0036's cleanup confirmation clause, that belongs to the separate independently reviewed cleanup backend and a successor ADR; this design supplies no such relaxation.

Absence of a ledger means “no registered obligations,” not “all historical workflows completed.” Do not bulk-mine old conversations, full logs, or arbitrary plans at startup. Any optional legacy residue import must be an explicit bounded operation using source checksums and exact origins, with current owner deduplication and visible uncertainty. Old versions must ignore the new owned runtime directory without deleting it. Unknown schema versions remain readable only as bounded unavailable metadata; do not overwrite them with a lower version. Rollback disables new writers/notifications while preserving the ledger and target records. Retain an explicit version-compatible export/recovery path; reverting source is not a transaction rollback of effects already observed.

### Failure-injection acceptance matrix

| Interruption or conflict | Required observation after restart |
|---|---|
| Before any durable registration | No claimed recovery guarantee; the producer reports `durable: false` when it observed failure. |
| Record written, index transaction incomplete | The bounded recovery header repairs or reports unavailable; an acknowledged registration is never silently absent. |
| Registration response lost | Exact ID/origin replay returns the existing record, with no duplicate. |
| Claim written, target not called | Reconciliation proves absence, then permits the exact authorized retry. |
| Target committed, response lost | Exact-origin/operation readback settles once; no duplicate task or question. |
| Target committed, settlement write fails | The record remains recoverable and the next read records the existing target. |
| Two sessions race to claim/correct/settle | One expected revision wins; the loser observes conflict/busy and preserves the winner. |
| Source changed while pending | Only this candidate becomes unavailable until current context resolves it. |
| Active target owner changes or dual ownership appears | No fallback writer; affected promotion is unavailable. |
| Claiming process dies / live process is slow | Dead critical section can reconcile; live lock cannot be stolen based on time. |
| Explicit denial or revoked Pi parent delegation | The pending record persists; no new effect; unrelated authorized work continues. |
| Malformed/unknown-version record or stale cursor | Bounded diagnostic and partial/unavailable inventory; no “clean” summary and no destructive repair. |
| Partial batch and full scan budget | Exact completed/remaining IDs and continuation; no global completion or inferred empty queue. |
| Compaction/rollback/host reinstall | Tombstone deduplication and unresolved records survive; no replay of external effects. |

## Corrected debug and reviewer submissions

### Debug

The current `_debughandofflib.py` is a stateless validator. `debug-handoff.py` accepts bounded input and reports exit 2 for input/shape/reference/internal-semantic failures, exit 3 for operational failures, and exit 0 for a valid packet. None of these facts independently proves a causal claim, the current runtime, or permission to repair. Keep the bounded schema, field paths, sanitized diagnostics, and full causal/regression obligations.

Replace the blanket no-resubmission sentences in `core/surface/skills/debug/SKILL.md` and `references/preparation.md`. A correction may address a reported input defect, stale binding after new observation, or operational recovery. It must name what changed, preserve the known case history, and distinguish observed facts from proposed repairs. Do not treat every exit 2 as “format only”; semantic failures may require new evidence or a different disposition. An unchanged retry without a changed condition is not progress. Do not switch interpreters or alternate validators to bypass the installed owner.

The normal successful debug handoff remains a bounded packet and summary. Do not introduce a persistent debug packet store merely to implement resubmission. The terminal-harvest ledger may retain a sanitized follow-up obligation, not the complete diagnosis or rejected payload. If the validator is unavailable, the transfer remains unvalidated; correcting presentation does not authorize a code fix or manufacture a failing regression.

### Reviewer

`core/surface/agents/authority-reviewer.md` prohibits retry **under the same request**. It does not prove that all future review requests are prohibited. Preserve immutable request finality. A corrected submission uses a new linked request/attempt where the current adapter consumes or rejects the old one; it captures the current frozen target, contract, context, host child launch, coverage, and actual first terminal event. An exact transport replay of an unchanged immutable successful operation uses its original operation ID.

Native task `NT-11` verifies compatibility. The native authority-bearing review schema admits a valid observed pass; `changes_requested` is not a success receipt. The existing native validator binds host profile, captured launch, target/context, contract, coverage, and assessment. Prefer the existing observation formats with a fresh truthful launch when sufficient; do not add ad hoc retry fields to closed old schemas. A later stop from the same child cannot be relabeled `first_stop`. Keep rejected, denied, failed, and changes-requested history; never mutate an old refusal into approval.

A correction can repair the report or respond to actual findings. It cannot remove an actual user denial, relax tool scope, claim independence after steering, pass missing evidence, or convert a HIGH finding into a nonblocking result without the separately selected policy. Apply the distinction to common review output and diagnostics, not only to the debug route.

## ADR and policy changes

Accepted ADR bodies are part of the repository's append-only decision history. Do not silently rewrite an accepted body to make history agree with the new implementation. Use the installed ADR workflow and current acceptance/implementation ledger: allocate successor numbers at implementation time, record exact scoped supersession, attribute the user-selected decisions, and attach implementation and verification evidence only after it exists.

| Current owner | Required decision update | Explicit boundary |
|---|---|---|
| ADR0030, orchestration mode plane | Scoped successor clarifies selected/raw/backed effective mode, transition identity, persona delivery, compaction generation, and truthful partial audit outcome. Correct the contradictory gates-on/off language. | Deterministic guards remain mode-independent. Delivery does not prove the model consumed or forgot earlier persona text. |
| ADR0043, assistive state engine | Add a scoped implementation clarification/successor for dependent-only conflict pauses and durable nonblocking bookkeeping/reentry. | Do not decide the separate progress/evidence SMARTS question here; no new universal approval gate or database. |
| ADR0008, board-sync chokepoint | Clarify that local pending capture can precede terminal harvest and survive interruption while promotion/staging still respects branch contingency and the work commit. | No automatic cross-branch promotion, issue publication, board completion, or staging. |
| ADR0036, cleanup direction | Record that recovery-ledger retention does not supersede per-item/group cleanup authority. Link the host cleanup successor only if that workstream actually implements and independently reviews its backend. | The user-approved recovery feature is not permission to delete worktrees/branches or weaken deletion proof. |
| Debug/review policy owners | Record corrected-submission permission, error categories, and immutable attempt linkage in a focused decision if required by current accepted policy. | Actual denial, evidence freshness, reviewer independence, and scope controls remain separate. |
| Common reviewer/dependency policy (`W-F03`) | B and receiving agent choose maintenance-only HIGH disposition; then update both owners and generated summaries in one change. | Not settled by corrected resubmission. Until chosen, preserve/reveal the conflict for the affected review. |
| Compatibility policy (`W-F09`) | Make the existing major/1.0 floor plus separately approved named removal and fresh release evidence the one machine-readable rule. | No alias removal is included in this plan. If B chooses a different rule, make that explicit before implementation. |

The operating corpus should record these as accepted user directions, proposed implementation choices, or unresolved choices accurately. Do not label a drafted ADR accepted, an implemented reducer verified, or a tested source release-qualified before the respective evidence exists.

## Mode and installer corrections

For persona delivery, model a transition epoch or equivalent current delivered-state identity, not the historical set of every mode ever delivered during a session. The epoch must advance only for a real selected/effective transition, remain stable for duplicate host events, and cooperate with the compaction generation. Include arbiter → dangerous → arbiter, ops → arbiter → ops, repeated same-mode tokens, duplicate prompts, new sessions, and compaction during transitions. Retain exact whole-prompt token recognition and owed audit behavior.

For mode outcomes, keep requested, raw persisted, ledger-backed effective, and delivered state distinct. An audit append failure after a raw marker commit must report that partial result and its recovery, not “session remains unchanged.” The existing owed-audit mechanism must converge on replay without duplicate rows or bypassing backing checks. Status text must never claim that dangerous/ops mode disabled deterministic gates.

For spinner uninstall, store the exact installed owned value separately from the prior backup. Restore the backup only if the current setting equals that owned value; otherwise preserve the user's later value and report that ownership ended. Handle missing settings, partial backups, repeated uninstall, upgrade from older backup shapes, and unchanged statusLine ownership independently. Never replace a whole settings object to fix one key.

The Pi doctor correction must use the real scoped package identity and host/package source while retaining all independent checks for version, extension, skills, and package discovery. Do not change the package's public name to fit a broken diagnostic. The launch binding correction must land with `NT-04`: the actual POSIX probe produced 32/33/34 launch files for 30/31/32 workspaces; the source-supported Windows maximum is 37. Preserve the 32 workspace-manifest role bound and real launch fingerprints; do not make all collections unbounded to admit a legitimate producer result.

## Generated surfaces and compatibility

Correct factual descriptions at their source and generate derivatives. `GEN-F01` changes the nudge explanation to the runtime's freed-context predicate. It does not change when the runtime nudges. For `GEN-F02`, label extracted text as static templates, retain source links, expose dynamic fragments and skipped calls, and remove the guarantee that extraction proves every runtime message. The literal-tag pass must honor lexical code masking as other passes do. A typed registry can be introduced for canonical gate IDs/events/recovery templates when that reduces duplication, but shipping a registry must not turn extracted text into an authorization owner.

For command/index drift, owner metadata should supply supported argument spelling, version-target grammar, Tribunal lenses, and reviewer disposition summaries. Generate installed catalogs and site views from that metadata. Do not change `--dryrun` to match stale `--dry-run` wording, invent a new alias without testing its grammar, or make MEDIUM untested-source findings blocking simply to match an index sentence. Resolve `W-F03` before generating a definitive dependency HIGH disposition summary.

For slugs, reserve every emitted output globally and produce deterministic results in stable input order. The `foo`, `foo`, `foo-2` sequence must not emit duplicates. Compare old and new catalogs before regenerating routes; preserve redirects for any already published URLs. The audit did not establish an existing production collision, so describe this as a bounded helper correction until candidate comparison demonstrates an affected route.

For compatibility, update `core/surface/command-routes.json`, `tools/build-surface.py`, `core/surface/includes/command-compatibility.md`, and the release observer together. Use structured rule fields or a single unambiguous supported value representing the actual floor, separately approved named decision, and fresh exact-release evidence. The clock remains tied to the confirmed non-draft GitHub release described by the owner. A matching version string, source tag, or major bump alone is insufficient. Preserve all presently supported aliases unless a separate named removal is supplied.

## Pi qualification boundary preservation

The following are test/qualification helpers, not installed product lifecycle owners:

- `plugins/ca-pi/tools/test/benchmark-boundary.ts` uses production wrapper code with fixture tool factories and an allowing fake bridge. It emits ready/complete phases, requires 100 measured samples, and performs 5 warmups. This is evidence about the exercised adapter boundary and measurement protocol, not real-host security permission or end-to-end runtime latency by itself.
- `plugins/ca-pi/tools/test/live-pi-host.ts` finds an installed Pi package from PATH and resolves its declared bin. The helper itself does not establish a release digest, supported version, trusted publisher, or complete launch containment. Callers must bind those qualification facts where claimed.
- `plugins/ca-pi/tools/test/setup-disposable-home.ts` seeds dummy credentials and redirects the test process's home/auth variables. Its exit cleanup is best effort and abrupt termination can leave temporary residue. Source presence does not prove every test process preloaded it; the test entrypoints must prove that boundary. It must never be interpreted as production authentication behavior or as permission to inspect the operator's real credential store.

The new recovery and Pi delegation tests must inherit disposable homes before importing runtime code, use dummy credentials, identify the exact installed candidate and host version, and keep test-only fixture results distinct from installed-host observations and release evidence. Test cleanup can remove only its exact newly created temporary root. A leaked fixture directory must not be described as a live user-resource cleanup result.

## Verification and completion evidence

The companion JSON specifies existing test paths and proposed new test paths separately. File names are locations for implementation, not claims that their tests already prove the new behavior. The receiver must read the relevant test owner before changing it. Start each confirmed defect with a meaningful failing regression using the actual boundary; reuse the audit probes as reproduction evidence, not as a substitute for integration tests.

Recovery needs fault injection at each commit boundary, multiprocess contention, exact-origin replay, partial-batch failure, worktree/branch/source changes, unknown schema, budget exhaustion, and rollback retention. Measure actual file effects and observed targets; do not merely assert that a helper returns zero. Resubmission tests require a malformed-then-corrected valid path, a semantic-evidence failure that remains a failure until real evidence changes, a denied action that stays denied, and fresh reviewer attempt linkage with immutable old history.

Run source-generation parity and package checks after canonical changes; do not patch only `plugins/ca`, `ca-codex`, or `ca-pi` copies. The baseline audit proved all shared Python copies byte-equal at its commit, so a new copy disagreement is a regression to resolve. Qualify the packaged candidate on supported host/platform cells required by the root release contract. A focused local pass, a hosted aggregate pass, an installed exact-artifact observation, publication, and public readback are distinct states.

Completion evidence for each task includes its before/after reproducer, source commit, changed owner and derivative paths, meaningful focused tests, observed failure/retry behavior, preserved guards, compatibility/migration result, and rollback route. The whole effort remains on its integration branch until the root acceptance matrix is satisfied. The intended outcome is that users receive truthful recoverable results, the developer has one inspectable owner for each transition, and agents have exact next actions without inferred permission or lost state.
