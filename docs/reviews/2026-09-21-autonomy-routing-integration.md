# Autonomy and intent-routing integration

Date: 2026-09-21

Status: proposed integration, not a release claim or accepted architecture decision.

Source baseline: `arbiterForge/codeArbiter@5c876dd885598c248fa777e951dac4e628688d73`.

This document carries the sprint/farm and structured-artifact reassessment into a review branch. It is not a new runtime registry, skill, command, agent, or always-loaded instruction. The implementation must be verified against the actual checkout rather than treating the preceding audits as authority.

## Intended outcome

Enable quality autonomous work with fewer avoidable human interruptions. Infer the user's intended outcome, choose the applicable existing workflow, and satisfy its actual authorization and evidence requirements. Explicit commands remain useful entry points; they must not become a compulsory interaction ritual.

Reduce duplicate policy bodies and always-loaded context while preserving useful direct handoffs and private, path-loaded procedure cards. A scoped child may return evidence; a completed stage may forward into a shared continuation; a recoverable failure may branch into diagnosis and authorized repair. Neither universal return-to-caller nor unconditional commit-to-PR is correct.

For farm, improvement means better accepted work and reliable autonomous completion under explicit resources. Lower token expenditure is one possible benefit, not the sole objective.

## Evidence and scope

The historical integration review used `5e7b2dac4e0f82560c1301144f3a20c35b7e0878`. The HTML reassessment inspected `8f81df40efab1fb3cad22d1bed07c61ee1eb1f7d` and the subsequent release-only change at `5603019bb757269cc0457185c3c346a1d5892d94`. Their test results must not be represented as tests of this branch.

The current base includes the release-cohort repair merged as PR #841. The separate open hook-path work in PR #838 is not part of this change. No release workflow, hook implementation, version, accepted ADR, marketplace metadata, or public compatibility promise is to be changed incidentally.

Current source rechecked for the first integration slice:

| Owner at the source baseline | Observation |
|---|---|
| `core/surface/arbiter.md` | Requires every intent to enter a literal command/entry skill, treats a second plausible command as clarification-worthy, and describes ordinary Q&A as an exception. |
| `core/surface/includes/safety-core.md` | Its higher-priority decision rule requires one sensible answer even for a reversible parameter. The four irreversible-action protections and append-only history are separate requirements. |
| `core/surface/includes/routing-table.md` | Already resolves hidden skills by path. Public command names and internal operation ownership need not be identical. |
| `core/surface/includes/redirect.md` | Repeated command menus and an override suggestion remain in the redirect examples despite the same file prohibiting override for a missing owner. |
| `core/hosts.json` and `tools/build-surface.py` | Commands generate Claude entries but Codex/Pi public skills; internal skill bodies generate separate routines. Removing a wrapper alone can strand a host entry. |
| `.codearbiter/decisions/0022-auto-route-unambiguous-safe-intent-into-its-command.md` | Preserves governed routing and separates clarity from destructive-operation authority. Do not rewrite the accepted record. |
| `.github/scripts/test_routing_and_cleanup_surface.py` | Existing cross-host structural tests protect routing tiers, the destructive registry, cleanup, and ephemeral-tool exceptions. Preserve those protections when extending coverage. |

References in this table mean `arbiterForge/codeArbiter@5c876dd885598c248fa777e951dac4e628688d73:<path>`. They are development-source evidence, not distributed-artifact proof.

## First implementation slice: intent routing

1. Replace compulsory input syntax with selection of the existing owning workflow. Preserve wrapper-owned arguments, modes, reviews, and gates when routing directly to a skill or private resource.
2. Put the distinction between questions and mutation requests in the resident contract rather than only in a redirect file that an understood request never loads. A request to explain a commit is not authority to create one; a request to draft a message but not commit must remain non-mutating.
3. Clarify that multiple reasonable internal methods are not multiple user goals. Reversible implementation choices may be made only within already-granted scope and authority, with the workflow's required decision record. Material product choices, unresolved confirmations, and irreversible operations remain separately governed.
4. Ask about the missing outcome, fact, or authorization rather than making the user select or retype an internal command. Keep the exact four-operation destructive registry and its resident-copy parity.
5. Preserve existing direct resource loading and continuation ownership. Load the applicable body; do not infer hidden procedure behavior from its description, omit a wrapper's distinct obligations, or turn a routing gap into an override.
6. Regenerate every changed host projection. Add regression coverage to the existing routing surface test suite, retaining its security and cleanup assertions. Structural tests do not establish live model-routing quality.

This slice does not enable HTML farm, redesign initial approval, remove public compatibility entries, change typed state transitions, or claim to resolve every sprint stop clause. Those are separately testable work below, not hidden additions to a routing edit.

## Remaining implementation work

### Typed sprint continuation and recovery

Revalidate the current ordinary feature and sprint paths through spec approval, plan authoring/binding, task execution, receipts, scope acceptance, commit, and finishing. Reuse the installed artifact engine rather than adding a second state machine or shadow Markdown authority.

Resolve the initial spec/plan approval sequence against the planner's approved-spec prerequisite without letting delegated decision logic grant its own initial authority. Preserve the intended initial review experience rather than adding another default interview. A genuine change to approval semantics requires an explicit product decision.

For HTML, use the authored checkpoint partition as the acceptance scope. A presentation batch is not automatically an engine checkpoint; a sprint checkpoint is not automatically an attended user checkpoint. Keep the intentional inline small-feature lane.

A failing test or review blocks acceptance, not necessarily authorized diagnosis and repair. Trace the existing child stop clauses before changing them. Distinguish stale evidence, a missing capability, a reversible implementation failure, and missing authority. Use real policy events and current receipts; never invent a verdict, user statement, or approval event.

### Decomposition and proof freshness

Use existing typed source, criterion, constraint, and task references. Check whether relevant decomposition obligations were recorded during specification before assuming internal spec/plan consistency proves upstream completeness. Missing optional decomposition remains non-blocking.

Probe acceptance followed by normal sprint logging, task harvest, provenance healing, later-checkpoint work, commit, and finishing. Revalidate affected proof autonomously where authorized. Do not blanket-exclude governance files or ignore changed inputs to make a refusal disappear.

### Farm correctness before HTML enablement

Revalidate the historical scheduler and canary findings against current source and the rebuilt shipped bundle. The old defect-expecting probes are historical reproductions, not regression expectations for a corrected implementation.

Test dependency-ready scheduling before file-conflict arbitration; immutable prepared baselines across canary candidates; actual effective-model attribution; qualification before discarding useful alternatives; existing breaker draining; interruption recovery; and honest accounting of rejected/retried work.

Keep HTML farm disabled until its explicit qualification is complete. Projection support is not enablement. A new farm-only request cannot silently authorize a Markdown shadow, premium fallback, another provider, or additional spending. When qualified, connect farm as an author backend of the existing typed workflow, not another orchestrator.

### Compatibility-preserving surface reduction

Recheck the command/skill candidate relationships before deleting any entry. Commit remains a strong single-owner candidate, but preserve current acceptance preflight, explicit or validly delegated authority, host discovery, and caller-specific continuation. A standalone commit must not imply a PR.

Other candidates from the review include new-skill/skill-author; same-name debug, refactor, release, tribunal, decompose and context-check; create-context/context-creation; cleanup/post-merge-cleanup; threat-model/security-architecture; and the ADR-related entry family. These are candidates, not current deletion approvals. PR/finishing owns distinct behavior and an existing anti-reentry instruction.

Read complete child bodies, including late mode exclusions and terminal side effects. No-code investigation can still write metadata. Release dry-run and readonly inspection modes must retain their actual boundaries. Coordinate any release-body consolidation with its existing owner.

## Verification and reporting

Use source-unit, generated-surface, exact-bundle, installed-host, and model-backed results as separate evidence layers. Run targeted local checks appropriate to the changed paths and require the repository's exact-head hosted checks before merge. Do not report skipped or unexecuted tests as passes.

At minimum, evaluate: natural-language commit versus commit explanation versus message drafting; multiple internal methods for one clear goal; missing material inputs; all four irreversible operations; unresolved confirmations; hidden resource routing; scoped return versus full-plan forward; initial versus inherited authority; stale proof; and recovery without gratuitous user interruption.

Measure startup discovery metadata, per-invocation instructions, and retained conversation context separately. A smaller source file is not a measured token saving; returning from a skill does not prove its context was unloaded. Evaluate farm against accepted scope quality, escaped defects, human interventions, elapsed time, and total resources.

Record each touched audit item as confirmed, modified, refuted, already resolved, deferred, or blocked by a specific dependency. Leave untouched claims pending. Do not rename historical confidence as current proof.

## Rollback and publication boundaries

Review on the dedicated branch. Do not merge, publish releases, force-push, or delete unrelated work as part of this integration. A rollback should revert the isolated change and its generated projections together, not edit accepted ADR history or create an alternate artifact authority.

The PR description must state the implemented slice, exact commit, tests actually run, remaining work, and policy decisions still requiring review. Project-source and public-surface claims are not updated automatically by this document.

## Second slice: CI repair and bounded sprint recovery

The failed first-slice run was 35653563527 at cb8d6247807091c39dc92c96c2a8cb1bfbc587d1.
The official generator and original routing suite passed; broader composition tests
exposed the stale decision-authority anchor and missing ops-mode link. Artifact
startup checks still pinned the pre-review resident persona. That historical
baseline is retained, with a separate exact reviewed content digest for the changed
persona; registration parity and eager-artifact checks remain enforced.

Ordinary quality failures now return through the same original gate and invalidated
reviews under an approved sprint. Initial spec/plan approval, real authority/security
blocks, immutable records, and HTML farm restrictions remain unchanged. Typed
eligibility overrides the legacy ACCEPTED-dependency sentence explicitly. This does
not resolve initial approval choreography, all farm recovery, or commit delegation.

The three missing publication-ledger entries were recovered from the original
successful release run 35537578654, attempt 1, workflow/source commit
5c876dd885598c248fa777e951dac4e628688d73. Independently acquired artifacts:

| Tag | Original receipt artifact | Verified archive SHA-256 |
|---|---|---|
| v2.21.7 | 10613213900 | 55aeb520adb4ae6054455baf4b819eebb0d53e336ba994365e56c18dfa6e2b47 |
| ca-codex-v0.13.7 | 10613189302 | 4dc5adc7dda8729d20a3302992e23d8690867a075f7a3fdc256f0958c6c9c90d |
| ca-pi-v0.14.7 | 10612799631 | a9b77decc6036bc7ab044514061082bb54e344d251b3fa05cf17560adbb211d1 |

The existing reconcile_tag_receipt helper validates the append-only candidate. No
old identity is replaced, no legacy entry is promoted, and no tag is moved. The
next patch versions and their notes are candidate metadata, not publication proof.

A temporary branch-only preparation job uses a complete checkout and official
generators. It never updates a ref; the candidate removes its two helper files.
Its result must be inspected before the connector fast-forwards this PR branch.
Product tests, generated parity, installed-host behavior and live-model routing
remain distinct evidence layers. Exact executed commands/results are retained in
the preparation artifact and the PR update, not inferred from this document.


## 2026-09-23 revalidation: caller continuation and typed checkpoint scope

This follow-up inspected `arbiterForge/codeArbiter@d0a247f3a78d10b1fc2d0b2b823a58ec5c2a2e3f`.
PR #843 is merged, including its later durable blocked-state correction and live
candidate qualification. The earlier unpublished conformance patch was not applied:
brainstorming still used blob `1667edf9e220016f27705f89c706345c0d9d9f86` and the
attended executor still used `284b08805b10fe6ae4027e7b2f1c116e8609c08d`.
The former permitted initial sprint SMARTS approval and unconditional TDD handoff;
the latter constructed task-count batches without the authored HTML checkpoint partition.

The new correction is deliberately rebased, not a replay of the old patch. Main now
includes the production authority pipeline from #844. Its exact prompt approval,
Codex-only verification/review, qualified producer requirements, and supported
reconciliation mechanisms remain authoritative and are not relaxed here.

| Requirement | Current correction | Owning source |
|---|---|---|
| Preserve one coherent sprint rather than force repeated feature interviews | Caller scope explicitly distinguishes a feature from a coherent sprint; unrelated work is excluded | `core/surface/skills/brainstorming/SKILL.md` |
| Do not make the user select reversible internal methods | Remove the single-answer rule and indiscriminate later/confirmation instructions; retain actual user-owned decisions | same |
| No self-delegation or skipped planning | Initial spec approval precedes planning; full-lane continuation returns or forwards to writing-plans, not unconditionally TDD | same |
| Make the existing HTML approval sequence executable | Arm exact spec, observe exact reply and validate approval, create/bind plan, then separately arm and approve it before execution | `core/surface/SPRINT.md` |
| Keep actual authority distinct from scoring | A score/log is not a receipt; absent production producer is not granted by delegation | brainstorming and SPRINT |
| Preserve typed checkpoint membership across resume | Keep full task-ID membership including REVIEW and BLOCKED; eligible chooses work, not membership | `core/surface/skills/executing-plans/SKILL.md` |
| Preserve autonomy versus attended execution | Feature retains its acknowledgments; sprint still goes directly to subagent-driven-development without attended pauses | same |
| Do not enlarge discovery | Extend existing private procedures/index and generate existing host copies; no new command, skill, agent or persistent tool | `core/surface/skills/INDEX.md`, host projections |

The initial HTML instructions describe the already-implemented single-artifact
approval adapter, not a new combined authorization protocol. Two exact replies
within the initial planning phase do not become per-feature interviews or execution
checkpoints. The user may separately choose a redesigned combined approval experience;
this change does not invent one. A missing supported authority producer remains a
real boundary; no event, signature, user prompt or verdict may be fabricated.

### Verification scope

Thirteen additional methods in the existing routing suite pin the operative
caller, approval, selected-format and checkpoint contracts on core and all three
host projections. The original nine new methods failed in 36 host subtests against
unmodified main; four additional current-authority tests failed in 16 host subtests
before their corrections. The final routing suite has 53 tests. These are prose
contract regressions, not an authenticated model-driven sprint.

Current local authoring/workflow tests use the authentic Linux native engine from
producer run 35821596966, attempt 1, artifact 10734185200. Its `core/artifacts` source
subtree `2d36d8ec5ae04a72f39b14d92d446f5fa04cf5f5` is identical to the inspected main;
the artifact archive and selected native members were hash-verified. This establishes
only the native fixture basis, not equality of all host package bytes or live authority.
Local process-containment coverage hit an absent descendant PID file at the fixture's
0.5-second deadline; retain that failure and test the unchanged suite on the hosted
runner rather than weakening its timeout/containment obligation. Exact commands and
hosted results belong in the follow-up PR evidence, not an unconditional claim here.

### Candidate identity and original publication record

All changed payloads advance from the spent mainline .11 coordinates to candidates
ca 2.21.12, ca-codex 0.13.12 and ca-pi 0.14.12. Manifests, adapter-version literals,
generated shared copies, root Pi metadata, notes, badge and the three manifest
provenance claims advance together. These candidates are not published and the old
live Codex proof is not relabeled: exact final .12 bytes still require authentic
live qualification before release readiness.

The missing `v2.21.11` ledger entry is appended through the existing reconciliation
helper from the original publication artifact 10734983732 of run 35825602367,
attempt 1. ZIP SHA-256: `89f175f857af88a16a4d9f00b60bdd04c975c4e40eecfa13e3a87c89cca215ad`.
The successful original CA publisher job is 107066725601; the independently observed
tag object is `d0a6353cb0716c70fb6b2b627db4a9020645505e`, peeling to the inspected
main commit. Every prior ledger entry and top-level field is preserved. That release
run failed later at Codex publisher-token creation, so the successful CA publication
is not evidence of full cohort completion. No tag, publisher permission or release
execution is changed by recording its authentic receipt.

### Remaining boundaries

This does not enable HTML farm, implement a SMARTS authority producer, fix the farm
scheduler/canary runtime, remove public compatibility names, expand host support, or
complete every historical audit item. General decomposition completeness and
proof-freshness behavior remain separately testable. Revert the isolated correction
and generated projections together if rejected, preserving accepted decisions and
authenticated publication history. Project Sources and public maturity claims are
not changed. Temporary preparation files must be absent from the final PR tree.


## 2026-09-23: command-backed owner consolidation (PR #850)

Baseline: `arbiterForge/codeArbiter@f361d039d329a8a2932bd9dc14ec42d7b32d4ca3`.
The user requested adding this slice to the existing PR, not opening a second one.

D01 (`commit` / `commit-gate`) and D02 (`new-skill` / `skill-author`) now use a
whole-file SKILL_ENTRY declaration in the existing command source. The existing
surface generator composes the complete public entry from the owning skill's
single description, argument hint and body. It is not a runtime include mechanism.
No source schema registry, agent, command name, installed helper or permission was added.

The source review found an important approved exception: ADR-0028 retains the
owning commit skill for plain-language discovery. That decision is preserved.
Claude keeps `commit-gate` and `skill-author` discoverable, while only their
redundant command descriptions are model-disabled. Explicit command spellings and
manual skill compatibility names remain usable. Codex/Pi need their generated entry
skills discoverable because internal owners reside outside their discovery roots.
The generator derives this distinction from the existing host projection rule.
No `user-invocable` control or user-settings override was added.

Every generated entry contains the complete owner, so the model need not load a
wrapper and then reload the identical procedure. Existing explicit internal resource
paths remain valid and caller-owned return/forward/branch behavior is unchanged.
The commit owner's entire Pre-flight-through-Hard-rules suffix is byte-identical
to the baseline: actual permission, current HTML acceptance, selective staging,
verification, secrets, security reviewers and terminal commit receipt are preserved.

The compiler fails on non-whole declarations, missing or symlinked owners, duplicate
public ownership, nested composition, unsupported or repeated metadata, hidden owners
and unrooted supporting links. Validation happens before any generated files are written.
The existing independent host-descriptor oracle now understands this small grammar
without calling the production composition parser. It still detects independently
mutated generated content. The Codex agent-reference corpus counts increase only
because two full generated entries now contain the owner's existing references;
no new agent type, dispatch behavior or native registration was added.

The skill-author owner documents the same single-source convention and permits
supporting information cards without fabricating skill frontmatter or discovery
entries. Curated command/skill documentation describes ownership and negative intent
rather than copying another gate procedure. The resident persona, startup emitters,
canonical command registry, host descriptors, accepted ADR bodies, core gate code,
versions and release proof are unchanged by this slice.

Verification must separately cover synthetic compiler negatives, real full-entry
body equality and gate presence, public entry names and discovery flags, generated
resources/catalogs, current hook and artifact regressions, and installed-host
qualification. Byte/file reductions and suppression flags are source observations,
not measured model tokens or a model-backed routing improvement. The historical
Claude reserved-name/budget behavior in ADR-0028 means static counts alone cannot
establish a runtime context saving.

Remaining candidates are not silently migrated: same-named debug/refactor/release,
initialization/drift aliases, decision modes, cleanup and PR/finishing have meaningful
side-effect, mode or authority distinctions requiring their own current caller review.
HTML farm remains disabled. New `.12` package bytes still require genuine final-candidate
live proof under the existing release gate; no prior receipt can certify this slice.
Rollback the owner/declaration/compiler changes and generated derivatives together,
without changing stored artifacts, published-tag history or unrelated PR work.


## PR850: requested combined approval and SMARTS producer

The requester explicitly approved this slice on 2026-09-23. It supersedes this
review's earlier sequential-only initial-sprint constraint and deferral of a
SMARTS producer; those statements remain historical implementation boundaries.
No accepted ADR body or Project canon is rewritten by this note.

The private native operations `sprint-approval-context`, `sprint-approve` and
`smarts-apply` reuse the existing source/observation/receipt and journal stores.
One exact host-observed reply approves the complete ready spec/draft-plan pair,
projects its approved binding and optionally grants existing-task method changes.
The model cannot authorize its initial pair or reinterpret approve-only as a grant.
The grant protects every normative plan field except existing task steps. The
producer rejects changed criteria, paths, verification, prerequisites, checkpoint
membership and running affected writers; it never marks work accepted. The normal
permission and proof gates, HTML farm block and host-specific limitations remain.

The native regression suite covers one-transaction replay, stale members, wrong
sources, generic-capture/single-approve refusal, missing delegation, malformed or
dominated comparisons, ties, revocation by spec change and injected mid-pair crash
completion/rollback. The installed Python adapter suite exercises actual native
operations using clearly synthetic host events, including lost response recovery,
no observed reply, stale cancellation boundaries, cross-root prompt routing and
fresh method authority. Neither suite is authenticated model-turn release proof.

The earlier secret-scan findings were an exact verified hostapi Git blob hash in
removed preparation history. Its value-only anchored allowlist must not broaden
path/commit exclusions, alter generic scanner rules or hide adjacent values. The
current-candidate live-proof gate remains separate and cannot be satisfied by
relabelling the old .11 record or these fixture results.


### Concurrent upstream release correction

Main advanced to `786a1db5713adc16cdee58e6903fd16099039ccd` through PR #853 while
this slice was in validation. That merged correction places authenticated live
Codex proof after publication under ADR-0032, while retaining static candidate
provenance and exact-head cohort checks before publication. Preserve it when
reconciling this PR. Earlier sections that called the retained .11 live baseline
a mandatory .12 pre-tag blocker are historical and superseded, not current policy.
No old observation is relabeled; this slice does not claim an authenticated user
model turn, released .12 behavior, or successful publication.

The delegated-method implementation also preserves BLOCKED members and their
reasons: a new method cannot itself reconcile missing permission or security
state. It invalidates affected proof but leaves any true block for its existing
qualified authority path. The paired prompt transitions share the existing
private cross-process lock facility, outside ordinary input snapshots, to keep
concurrent observations/cancellation from removing a different pending request.


## 2026-09-24: dependency-ready farm scheduling and isolated canaries

Fresh baseline: `arbiterForge/codeArbiter@cf90ce4d79c5d87cb88f163535c1035da2315815`,
the merge of #850. The subsequent slice uses a new branch/PR and does not alter
the merged approval/SMARTS producer or command ownership. The old farm TypeScript
blob still contains both historical defects; they are revalidated here rather
than inferred from an old report.

F03 is addressed by selecting dependency-ready tasks before scope arbitration.
Only actual running work and dependency-ready predecessors reserve file scopes.
Lexical ordering of overlapping ready siblings, including overlap chains, remains
unchanged; an unready lower-ID dependent no longer deadlocks its prerequisite.
The scheduler writes no artificial dependency edge and does not manufacture a
green prerequisite. Existing capacity, escalation and circuit-breaker draining
remain in their owning runtime.

F05 is addressed through an internal evaluation context in the existing task
runner. Canary resolves the configured base to an immutable commit before
entitlement probes. Every candidate and sample uses a unique caller-owned
detached worktree from that commit. The candidate model explicitly wins over a
task-level override during the comparison only. The same authoring, containment,
immutable-test, drift, gate and risk checks run, but evaluation returns before
staging, committing or merging. It never initializes, resets or advances an
integration branch. Cleanup uses verified worktree teardown and empty-directory
removal, records failures, and cannot recursively erase retained scratch. The
report includes the frozen base identity; it is not a task-acceptance receipt.

Regression coverage belongs to the existing farm unit/integration suites. The
actual source CLI and shipped bundle are exercised against disposable repositories
and loopback stubs: dependent overlap, existing dirty legacy canary scratch, a
checked-out integration branch, per-task model overrides, best-of-N evaluation,
failed worker and real gate failure, named-base movement during probing, and
invalid-base refusal before any model request. Pure scheduler tests include all
3,072 enumerated three-task order/DAG/two-file-scope configurations. The original
source/bundle fail the new integration obligations. These fixtures do not measure
provider/model quality, total cost or live user interruption rates. Exact executed
commands, result counts and SHA identities belong in the new PR's evidence.

Candidate manifests, adapter literals, generated shared copies and the three
manifest provenance claims advance together under the existing spent-version
policy. This does not assert that a candidate has been released. The private farm
card and three projections document evaluation accurately; no public capability
or resident context is added.

Still separate: F09 best-of-N post-selection qualification, farm process resume,
heuristic quality improvements, actual model-era evaluation and HTML farm
enablement. HTML farm remains disabled and real provider/resource authority is
unchanged. This source correction alone supplies no new promotion evidence.
Rollback the runtime and rebuilt bundle together with their projections/metadata;
preserve unrelated worktrees, typed authority records and published-tag history.


## 2026-09-24: PR854 conflict repair and retained-candidate qualification

This continues the same PR from `6bf1be69352369e07f9c97a221605224d968a4e2`.
Main advanced to `29f84168ab7592a5d7bb0550cb1f25cf29608a9d` with the guide
discovery work. Its unrelated changes are retained through a preserving merge.
The sole conflict was key ordering in `.github/published-tags.json`: parsed
publication identities and all earlier records were equal. Retain main's bytes
rather than duplicate an original receipt or change an authenticated identity.

F09 is addressed inside the existing task runner. Best-of-N still shortlists
candidates using their isolated sample gates, then materializes them in stable
index order into the actual task worktree. One shared checker owns containment,
immutable-test identity, drift, the task gate and the existing literal/mutation
policy for both single-sample execution and retained alternatives. A rejected
gate/risk candidate can consume a generated alternative before another model
round. The selected result is already qualified before siblings are removed.
This is first-qualified selection, not a new comparative quality ranking.

Between alternatives the runner verifies reset/clean and reapplies the existing
setup contract; a failed reset/setup or task integrity check ends selection,
rather than concealing the failure with another sibling. Rejected-only
nonignored output cannot leak to the chosen result. Ignored setup caches retain
their existing contract. All sample teardowns are attempted even when a
qualification throws, and cleanup failures remain explicit. Known usage survives
post-response exceptions; total and selected-candidate usage remain separate.
A later retry consumes the configured retry allowance only after the retained
alternatives are exhausted. Existing mutation evidence floors and
infrastructure-warning semantics remain unchanged.

The actual source and rebuilt CLI fixtures cover literal rejection, mutation
rejection, a gate that fails only after task materialization, all-rejected
results, and detached canaries. In-process tests cover selected usage, stale-file
reset, actual evidence floors, unchanged warning policies, missing setup, task
test tampering, thrown qualification, cleanup outcomes and post-response usage.
They use temporary Git/filesystem fixtures and local provider stubs, not a paid
model or a new authority producer. Normal acceptance, caller review and the HTML
farm block remain unchanged.

The prior normal run `35963335302` passed the farm execution suites. Its inspected
macOS native qualification job reached passing package tests, then was cancelled
at the 15-minute job deadline during final cross-kind conformance. The narrow CI
repair changes that complete six-cell job budget to 30 minutes and adds a
contract test retaining every qualification stage, platform, fail-closed result
and independent matrix cell. It removes no assertion or required check and
does not change production operation deadlines. Normal final-head CI, not a
preparation run or a time-limit edit alone, must establish completion.

Coverage remains a distinct evidence obligation. The earlier Windows/Linux
union was 68.97% lines and 64.13% branches, below the declared stage-2 floor even
though the current union job reported it advisorially. Do not claim a floor pass
from test counts or child CLI execution. Re-measure the final candidate and
retain any remaining gap without lowering thresholds or excluding source.

Candidate .13 coordinates remain the same unmerged release targets. No
publication fact, permission, public registration, resident context, protected
artifact schema or pipeline-acceptance rule changes here. Testing may consume
additional bounded local gate/mutation work for each retained candidate; no
realized token, total-cost or output-quality gain is asserted. Roll back the
runtime, rebuilt bundle, private card and projections together if rejected;
preserve unrelated main changes, current artifact authority and publication
history. Farm process resume, heuristic redesign, broader command migration
and HTML farm enablement remain separate.


## 2026-09-24: PR854 retry-reset evidence correction

Revalidation of the continuation at `e57f006b7db585a2a2a0ad0181d8c2ed90b223c8`
confirmed the independent review's retry exception finding. Retained-candidate
qualification already recorded sample cleanup and known usage, but a subsequent
task-worktree reset could reject outside the result finalizer. The scheduler's
generic fallback then lost the previous attempt count, token totals and cleanup
record. This is an evidence-loss defect, not permission to continue in a worktree
whose reset failed.

The owning runner now returns that failure through its existing finalizer,
preserving last files, risk score, known usage and unresolved sample cleanup. No
additional worker, reset bypass, acceptance or user approval ceremony is added.
The note is redacted before being bounded. The private farm card clarifies that
an explicit zero temperature disables the automatic sampling-temperature bump,
without promising deterministic or distinct provider output.

Regression fixtures exercise failures after one and two rejected sampling
rounds, a single-worker retry, and real Git index-lock refusal through both the
TypeScript entry and rebuilt bundle. The CLI fixtures verify complete JSON and
streamed results, exactly the original two worker requests, preserved integration
identity, retained lock ownership and sample teardown. Unit fixtures independently
retain honest cleanup failures and reject leaking a synthetic credential-shaped
value through the returned error. These are disposable fixtures, not authenticated
provider journeys or measured production quality/cost gains.

The conflict merge, bounded CI job-budget repair and F09 first-qualified selection
remain intact. Public registrations, authority, thresholds, version coordinates,
input policies and the HTML farm block are unchanged. Coverage completion and
broader process resume remain separate. Rebuild/revert runtime and bundle together
with their owning private card; do not erase earlier proof or retained scratch.


## 2026-09-24 continuation: external mutation evidence and fixture isolation

Baseline: `a3e085c55d79a8bf8b253e2ccc783b66b00c967c` (normal CI run
35977213239 passed). This is a bounded part of F10, plus revalidation of the
reviewer's inherited-Git-environment finding; it does not finish F10 or the farm audit.

### Confirmed and corrected contracts

- An external mutation command could return a parseable score even after nonzero
  exit/timeout, and stderr JSON could replace the real stdout report. Measured
  results now require successful completion and finite normalized stdout scores.
  Diagnostics are redacted before bounding. Missing optional counts stay absent.
- Failed-hook stdout can contain important adverse evidence: some frameworks use
  nonzero exits to report a threshold break. Retain that report as unverified,
  never as `mutationScore`. The existing near-zero/explicit-five-evaluations floor
  still rejects the candidate pending successful remeasurement. Ordinary unknown
  measurements retain the warning policy, not another default user stop.
- Unverified timeout cleanup is a distinct fatal qualification outcome. It cannot
  be disguised by switching candidates, spending another retry or integrating
  work while a mutation writer may still exist. This uses the existing finalizer
  and candidate-selection flow, not another gate/state system.
- The fixture-only environment drops inherited Git repository/configuration
  redirection and real farm/provider settings, then pins signing/config behavior.
  All fixture Git commands and both source/bundle farm launchers use that boundary.
  Teardown only removes owned temporary trees, never a shared sibling directory.
  Production Git environment handling is not changed by this test repair.

### Verification obligations and boundaries

The added cases exercise actual local mutation processes and source/rebuilt-bundle
CLI runs using loopback providers and disposable Git repositories. They cover
nonzero low/high scores, stderr-only output and misleading stderr, a timeout after
printing a score, invalid numeric values, redaction before truncation, adverse
count preservation, and single/multiple-candidate containment refusals. Hostile
Git variables target only a separate disposable sentinel repository; its refs,
index, config, worktree list and untracked files must remain unchanged.

Run the complete current farm suite, official generators and relevant authority,
resource and release checks against the exact committed candidate. Record actual
results, platform skips, normal-head CI and advisory coverage separately in the
PR; do not substitute historical tests or parser fixtures for model-backed work.

The built-in text mutator's compiler-error/timeout classification and literal-leak
heuristic are not fixed here. No threshold, test, source-input contract, public
command/skill/agent, HTML-farm capability or resource authority is added or relaxed.
No output-quality, cost or context reduction has been measured. Roll back the
owning runtime, rebuilt bundle and private documentation/projections together if
rejected; preserve unrelated fixture/production work and actual approval evidence.


## 2026-09-24 continuation: built-in mutation deadlines and incomplete evidence

Source baseline: `e7ed9490dfb1106a96294c7b573dcc56f1731389`. Re-read the
built-in `mutationCheck` loop and shared writer/runner, not only the earlier
external-hook findings. The loop credited a timed-out process as a killed mutant
and checked its total budget only before launching a full gate timeout. A disabled
general gate timeout could leave a trial unbounded despite a mutation budget.

Use a monotonic elapsed budget, recalculate after each mutant write, and cap each
launch by the remaining budget or a shorter configured gate timeout. A zero
mutation budget launches nothing. A completed partial sample may still produce
its existing heuristic score after three reruns; an interrupted trial instead
returns a labeled failure without a measured score. Retain completed adverse
observations separately so interruption cannot erase the existing five-rerun
near-zero floor. Clean timeouts follow the warning/independent-review path;
unverified process cleanup still stops authoring and integration for that task.
No new user checkpoint, public entry, workflow state store or threshold change.

Counterevidence matters: the shared `writeWorktreeFile` already converts write
failures into unsafe-path refusals. Its restore guards and the task-level fatal
handling remain unchanged. Do not report a new filesystem containment mechanism
or claim the older catch swallowed arbitrary production restoration failures.
Process-tree teardown and restoration can outlast the trial launch allowance;
the budget is not permission to abandon either or claim they completed.

New tests cover tagged timeout/cleanup outcomes, no next mutant, restoration of
worker bytes, adverse-count preservation, zero/remaining budgets including write
time, and ordinary nonzero exits without invented timeout flags. Injected clock
and terminal-state tests are unit evidence, not live unkillable-process proof.
Actual source and rebuilt-bundle CLI cases exercise a bounded slow mutant with
general gate timeout disabled and enabled, preserve the implementation and Git
state, retain diagnostics and use exactly the existing worker call. The existing
unsafe-write/restore tests remain required preservation controls.

Compiler-versus-assertion validity remains unresolved in the language-agnostic
text mutator; the literal heuristic is not redesigned here. No completed nonzero
exit is relabeled as compiler-aware proof. Keep HTML farm disabled, actual receipt
and review authority, retry limits, candidate coordinates and shared process
runner unchanged. Run normal exact-head cross-platform CI separately from local
and preparation results; record platform skips and advisory coverage honestly.
Rollback runtime and its rebuilt bundle together with the canonical private card
and generated copies. Preserve previous evidence and unrelated repositories.


## 2026-09-24 continuation: literal evidence precision

Baseline: `d566f22ccf933cb4a2832f2b9e7e0f8accf1c812`. Normal CI run
35989708906 and docs completed successfully before this slice. Re-read the actual
`antiGamingCheck`, its consumers and existing threshold tests. The implementation
used substring inclusion, so identifiers, comments, larger values and cross-kind
values could falsely trigger rejection. Its high-risk note also named the first
match even when only a later, different file supplied the tiny-file evidence.

Keep one private, model-free lexical pass in the existing mutation module. Match
complete string/number spellings with distinct kinds. Recognize conventional
slash/hash comments only for the source suffixes declared by this helper, preserve
comment markers inside strings, and consume whole identifiers and numeric forms.
Do not turn interpolation, escape normalization or ambiguous language syntax into
invented semantic evidence. Preserve the existing five-code-line risk boundary,
single-character filter, read-only test exclusion, missing-file behavior, guarded
reads, mutation checks, independent review and caller-owned retry/selection.
High-risk diagnostics name the first actual tiny-file witness; warnings preserve
their own first substantial match. No new public entry, dependency, provider call,
authority producer, approval step or resident-context registry.

Regression fixtures compare real literal reuse with prefixes/suffixes, mixed
kinds, comments, numeric spellings, ordinary regex/template forms and Python floor
division. Source and rebuilt-bundle CLI tests execute real narrow tests in owned
repositories, preserve immutable tests and main, and count exactly one worker
call. A separate adverse mutation control must still reject a candidate after the
literal-only false positive is removed. These are deterministic fixture results,
not measured production savings, semantic code review or live model qualification.

Limits remain explicit: labels/inputs/shared constants may still match; this is
not assertion-aware, an AST parser or escape/constant-expression evaluator. JSX,
prefixed strings and arbitrary regex/language grammar are not fully interpreted.
Compiler-versus-assertion mutation validity, process resume, HTML farm enablement
and other audit work remain separate. Native approval/receipt code, thresholds,
public registry, lockfile, timing limits and candidate coordinates are unchanged.
Run the normal exact-head CI and independent review in addition to both platform
fixture runs. Preserve historical reports and coverage targets; no advisory green
status is a target achievement. Roll back the owning module and rebuilt bundle
with its private documentation/projections if rejected, retaining unrelated work.
