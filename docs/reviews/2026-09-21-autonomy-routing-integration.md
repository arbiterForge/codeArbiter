# Autonomy and intent-routing integration

Date: 2026-09-21

Status: proposed integration, not a release claim or accepted architecture decision.

Source baseline: `arbiterForge/codeArbiter@5c876dd885598c248fa777e951dac4e628688d73`.

This document carries the sprint/farm and structured-artifact reassessment into a review branch. It is not a new runtime registry, skill, command, agent, or always-loaded instruction. The implementation must be verified against the actual checkout rather than treating the preceding audits as authority.

## Current progress: skill-authoring retirement (2026-09-25)

This section supersedes earlier slice status only where stated. Baseline inspected:
`arbiterForge/codeArbiter@b075a61717f16ebb18c4f7f5e94b71b5a2ef56fe`.
The maintainer explicitly requested deletion of both `new-skill` and its owning
skill on the same PR. It is an intentional compatibility break for this one
workflow, not a removal of other aliases or permission to invent a replacement.

### Surface reduction, counted by kind

| Work | Current disposition |
|---|---|
| `commit` / `commit-gate`, `debug` / `debug`, `refactor` / `refactor` | Three retained single-source owners; explicit entries are generated derivatives. |
| `new-skill` / `skill-author` | Previously consolidated; now retired, including the template, host entries and public reference pages. |
| `watch`, `cleanup`, `decompose`, `create-context`, `context-check` | Five previously implemented catalog aliases to PR, init and status modes; bodies/windows unchanged. These are not five new deletions. |
| `release`, `tribunal`, `decompose`, `context-check`, `create-context`, `cleanup`, `threat-model` | Seven named owner-consolidation candidates still pending mode/authority/terminal-effect reconciliation. |
| ADR/ADR-status/reconcile family; PR/finishing relationship | Four further relationships (D12-D15), not assumed to be trivial wrappers. |

The original 17 September `REVIEW.html` names **fifteen** candidate relationships,
D01-D15, against archive baseline `5e7b2dac4e0f82560c1301144f3a20c35b7e0878`.
The earlier rollup grouped D12-D15 and obscured that total. Three are consolidated
and retained, one is explicitly retired, and eleven remain candidates, not eleven
preapproved deletions. The broader RA-11 umbrella-command proposal is a different
backlog from these ownership migrations. Counts below describe source ownership,
not live-model routing success or token savings.

| Original ID | Entry / procedure | Current disposition |
|---|---|---|
| D01 | commit / commit-gate | Single-source owner retained |
| D02 | new-skill / skill-author | Removed by maintainer instruction |
| D03 | create-context / context-creation | Owner consolidation pending; existing init alias retained |
| D04 | decompose / decompose | Owner consolidation pending; existing init alias retained |
| D05 | debug / debug | Single-source owner retained |
| D06 | refactor / refactor | Single-source owner retained |
| D07 | release / release | Pending; preserve current target and dry-run semantics |
| D08 | tribunal / tribunal | Pending; preserve cost, filing and telemetry boundaries |
| D09 | threat-model / security-architecture | Pending; reconcile verdict and constraint semantics |
| D10 | context-check / context-check | Owner consolidation pending; existing status alias retained |
| D11 | cleanup / post-merge-cleanup | Owner consolidation pending; existing PR alias retained |
| D12 | adr / decision-lifecycle | Pending; author mode remains distinct from inspection |
| D13 | adr-status / decision-lifecycle | Pending; preserve read-only status |
| D14 | reconcile / decision-variance | Pending; arbitration is not ADR recording |
| D15 | pr / finishing-a-development-branch | Pending; composite lifecycle, not a thin wrapper |

Active canonical command records go from 38 to 37 and top-level source skills
from 23 to 22. Host command-entry totals go from 38/36/37 to 37/35/36 for
Claude/Codex/Pi respectively. Public command classifications become 18 core,
12 advanced, five aliases, one internal and one deprecated. No token, model
quality, installed-host discovery or released-artifact result is inferred from
these source/package counts.

### HTML farm: integration work remains, not another general-hardening queue

The baseline already implements native `farm-project`, `farm-seal` and
`farm-verify` operations in `core/artifacts/internal/operations/farm_projection.go`.
The dispatcher checks source binding and exact execution bytes; ordinary typed
spec/plan approval, bounded method delegation, verification and review adapters
exist. Native packaging is exercised by normal CI. None of that by itself
qualifies an HTML-backed farm session.

Three remaining work packages should lead directly toward enablement:

1. **Farm-specific authority capture.** Wire actual user/authorized workflow intent
   and freshly executed RED results into the required `farm_authorization` event.
   The inspected approval CLI supports single/pair approval and method delegation;
   the production authority CLI handles verification and reviews. Neither exposes
   the farm authorization producer used synthetically by `test_artifact_farm.py`.
   A method grant is not implicit approval of arbitrary providers or new spending.
2. **Complete typed execution and reconciliation.** Exercise real approved HTML
   pair -> current checkpoint/slice projection -> authorized provider seal ->
   shared author backend -> task-ID reconciliation -> independent review and fresh
   verification -> checkpoint acceptance -> commit preflight. Test stale inputs,
   interruptions and resumed review without fabricating receipts, writing shadow
   Markdown or repeating approval when existing authority is still sufficient.
3. **Exact-payload and current-model qualification.** Run that whole path from the
   built installed candidate on the declared host cells, then execute the fresh
   frontier/low-tier matrix required by the existing rollout policy. Record output
   quality, escaped defects, interventions and known resources, not price alone.

The owning leaf cards `skills/writing-plans/references/farm-plan.md` and
`skills/subagent-driven-development/references/farm-dispatch.md` still explicitly
prohibit ordinary HTML farm use; their qualification descriptions are not proof
of completed integration. Current native farm tests explicitly label their
receipts synthetic. No honest completion percentage follows from this evidence.

Full billing accounting, more command migrations, universal language-aware
mutation analysis and a general durable process-resume feature are separate
improvements, not automatic prerequisites to the bounded HTML author backend.
Required interruption safety and typed acceptance still need their actual tests.
The next implementation priority after this retirement should be the farm-specific
authority producer and its end-to-end consumer, not another unrelated micro-fix.
HTML farm is not enabled or modified by this removal slice.

### Retirement propagation and verification boundary

The command, owning skill and bundled template are deleted from canonical and
generated trees. Callers, catalogs, the architecture diagram, curated references
and source documentation agree. Useful format conventions are in the existing
`core/surface/README.md`, outside installed discovery; the five-phase authoring
ceremony was not moved to another card. Ordinary authorized repository work owns
future edits. No other approval, commit or acceptance boundary was removed.

The immutable artifact-policy registration baseline and original digest remain.
Two named, attributed reviewed-removal records explain the current delta. Tests
reject any other removal and reintroduction of either retired registration.
The compatibility test keeps the original route set except this one approved
exception; its five alias bodies and clocks remain protected. Generic link/catalog
fixtures replace the deleted skill as test data, preserving those assertions.

Revert this removal, generated derivatives and documentation together if rejected.
Preserve earlier farm work, real artifact authority, accepted ADR/history and
unrelated resources. Source and generated checks do not substitute for current-head
CI, installed-host validation or a real-model farm qualification run.

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


## 2026-09-24 continuation: nonzero mutation exits are not assertion proof

Baseline: `01e91f4d053a531a62a7fc3ee085ffafb25440bf`. Re-read the
built-in mutation loop and the existing failed-evidence consumer. A completed
nonzero test command still incremented a killed-mutant counter and could publish
1.0 when every generated mutant failed to parse. Actual Node syntax and assertion
fixtures demonstrate that the same exit code cannot safely distinguish phases.

Keep the existing private mutator and failure envelope. Do not add language
runtimes, configuration, phase-name inference, an AST service or another public
operation. Count completed nonzero reruns as unclassified rejections, retain the
first bounded/redacted witness, restore the worker output and report the missing
measurement without a positive mutationScore. The existing external framework
hook remains available for a real operator-configured language-aware measurement.
Do not classify diagnostic words, code 124, or score-looking stdout as proof.

Preserve adverse completed evidence: R/(S+R) is an unverified upper bound under the
existing gate-outcome accounting, not a semantic framework score. Removing invalid
rejections can only reduce that fraction; equivalence and unexercised changes are
not classified. The current near-zero threshold and five-completed count still
reject a sufficiently adverse bound. Otherwise follow the existing warning and
independent review path, not another model round or user question. All-pass runs
with at least three reruns retain the existing zero-score weak-test signal.
Timeout and unverified-cleanup paths keep their own existing meaning; no interrupted
trial enters the completed denominator, and no containment limit is relaxed.

Preservation tests keep genuine low-result rejection, thin counts, external-hook
measurements, candidate retention, accumulated usage and guarded restoration. New
real source/bundle CLI fixtures exercise syntax failures, assertion failures,
a near-zero mixed upper bound and all-pass weak-test evidence in disposable Git
worktrees using loopback providers. They require one worker call, unchanged main
and immutable tests, and restored output for continued work. Injected terminal
cases are unit evidence, not live language qualification. Existing tests that
asserted 1.0 from a bare false command now assert the unverified result instead;
their completed counts, exact survivor tags and budget checks remain.

The dispatcher and its authority/acceptance/retry rules are unchanged. Keep HTML
farm disabled, literal thresholds and scanner behavior intact, and existing
versions, publication history, lockfiles, CI budgets and coverage floors unchanged.
No public surface or startup-context registry is added. Qualify the rebuilt bundle
and both supported test platforms, then observe ordinary current-head CI and
independent review separately. Roll back the owning mutation module, bundle and
private generated cards together if rejected, preserving unrelated work and
actual artifact authority. This fixes false score attribution without claiming
that a generic shell runner can classify arbitrary compiler/assertion semantics.


## 2026-09-24 continuation: preserve usage at the HTTP worker boundary (partial F12)

Baseline: `76fd953c605b20b140de826406833da190d32aa1`. A decoded response's
provider-reported usage was lost on invalid shape, a forbidden or escaping file
block, and guarded-write refusal. Non-text content could escape as an exception
before worker evidence reached the task finalizer. Reported string, negative or
non-integral counters also crossed the response boundary without validation.

Parse the untrusted response before the file-block reader. Keep only independently
validated nonnegative safe-integer prompt/completion counters; explicit zero is
valid and absent/invalid data remains unknown. Return a sanitized ordinary worker
failure for malformed first-choice/message/text shapes and carry known usage on
all response-derived exits. Empty choices or missing text retain the established
no-file-output failure. Preserve partial written-file lists and the original
worktree/read-only guards. Do not echo response content or private endpoint fields
in shape diagnostics. Retain the existing task retry limit, candidate selection,
acceptance, authority and containment contracts; no request is made solely to
recover a counter.

The current task/report reducers sum known fields. This slice does not establish
complete billing, price, transport-retry usage, absent-provider usage or a new
aggregate completeness schema. It adds no public operation, configuration,
dependency, model call or resident context. Independent verification and quality
checks still determine acceptance, not output shape or reported token counts.

Tests cover parsing and worker exits plus real source-and-rebuilt-bundle CLI
failures, bounded retry and retained-candidate accounting. Assert exact request
counts, accumulated known usage, winner-only counters where applicable, immutable
tests/main and no integration after failure. Exercise false/empty/zero controls
separately from malformed responses. A selected old-source run is regression
sensitivity, not current qualification; record exact outcomes in the PR. Qualify
both supported platforms and normal final-head CI, and preserve coverage floors.

The contemporaneous main merge includes Codex marketplace publication from #855.
Keep its npm package, pipeline, tests and .14-and-older Codex changelog intact.
Only the Codex candidate advances to .15 because .14 is already on main; CA and Pi
retain their independent .14 candidates. Synchronize manifest/runtime identity
and actual changed provenance hashes without changing authenticated tag records.
This is source/candidate preparation, not proof of new registry publication.

Rollback the isolated HTTP-worker parsing/accounting change with its rebuilt
bundle, tests and generated private cards if rejected. Preserve upstream release
work, actual artifact authority, unrelated worktrees and historical evidence.
Process resume, complete spend accounting, HTML farm qualification, remaining
command migrations and measured production improvement remain separate work.


## 2026-09-24 continuation: bounded provider retry lifecycle (partial F12)

Baseline: `4e7ff2139480c25fe28bca5def14b8f857f8ffd6`. The HTTP loop waited on
provider-controlled Retry-After after leaving an error stream open. The request
abort timer did not bound that separate sleep, HTTP dates fell back to one second,
and integer-overflow waits could collapse to an immediate runtime timer. Exhausted
transport retries also re-entered the task's authoring loop as if changing code
would repair a saturated provider.

Use the existing private worker/result seam, not a new router or settings surface.
Parse standard delay-seconds and HTTP-date forms; malformed input retains bounded
local backoff. Honor a valid wait only within the existing request timeout budget
and safe runtime timer range. Do not clamp a longer valid cooldown into an earlier
request: defer the task instead. Close discarded responses before backoff or return,
while keeping the successful-body read deadline. Keep request retry counts and
normal implementation verification/retry policy intact.

Carry that task-local non-retryable transport result through single-worker and
best-of-N paths. Already-produced candidates still receive the full existing
qualification; if no candidate qualifies, do not start another authoring round
that bypasses the provider cooldown or exhausted HTTP retry budget. Preserve all
known usage, failed-file evidence and cleanup reporting. Independently eligible
work can continue under the unchanged circuit breaker; prerequisites remain
unaccepted. This is not a provider-wide concurrency coordinator, automatic delayed
resume, initial approval change, new status authority or additional human gate.

Regressions use fake-clock policy tests, request-signal lifecycle tests, injected
worker dispositions and real loopback HTTP/source-and-rebuilt-bundle CLI fixtures.
Verify request counts, unchanged main/tests, pre-backoff stream closure, retained
candidate success, independent-task continuation and blocked prerequisites. Preserve
ordinary custom-worker retry, missing usage and successful-body timeout controls.
Reference semantics: RFC 9110 sections 5.6.7 and 10.2.3; Node's timer range and Fetch
abort/body lifecycle. No external provider or paid model call is required.

Qualify the exact rebuilt candidate and both existing platforms, then normal
current-head CI and review separately. Candidate versions, upstream release and
authority files, secret controls, HTML farm restriction, thresholds and discovery
registry remain unchanged. Roll back runtime, bundle, tests and private generated
cards together if rejected. Full accounting, process resume, HTML farm enablement,
coverage completion and measured quality/resource outcomes remain separate work.

The baseline normal run 36079154677 also exposed a Pi Windows test failure in
`test/runner-isolation.test.ts`, outside the farm runtime. A single test packed
three early refusals and eight asynchronous child-failure lifecycles into one
five-second budget. Its timeout left asynchronous cleanup able to touch the next
test's shared mocks. Split those exact scenarios into individual awaited tests;
retain every degraded-result, auth-preservation and cleanup assertion, including
the existing pending/idempotent cleanup controls. Do not enlarge test or product
deadlines, change runner containment, or skip the Windows cell. Qualify the full
Pi isolation file and its surrounding suite on native Windows in addition to the
farm matrix; treat any remaining failure as evidence rather than silencing it.


## 2026-09-24 continuation: transport failure coverage and current-main reconciliation

Baseline: `e2ddf7fdd2951d86d23b91aba56781d780482b35`; incorporated main:
`929229354e3a15ae3002c82116b66c837ab43729`. The older unpublished transport
patch is superseded by the baseline's bounded-retry implementation, not reapplied.
The baseline's normal CI run `36083254895` completed successfully. The earlier
Pi Windows failure is already repaired there; it is not an unresolved farm failure.

Thirteen cases added to the existing farm unit suite exercise connection-error
retries, exhausted network failures, stalled headers, body-read refusal after
headers, the original deadline across late headers, exact request counts and
payloads, fresh aborted signals, timer cleanup, and bounded/redacted diagnostics.
Missing usage remains unknown. Network errors retain their existing retry policy;
the tests do not extend task-local HTTP cooldown deferral to another failure class.
These are injected-fetch/clock tests of existing behavior, not a new provider
mechanism, authenticated model journey, production defect reproduction or spend proof.

The private farm card now distinguishes measured-score thresholds from unavailable
mutation measurements: a completed nonzero built-in rerun warns regardless of its
ratio unless the existing sufficient-count near-zero rejection condition applies.
Regenerate all three host cards. Preserve the actual runtime, bundle and thresholds.

Retain main's host workflow admission, package notices and policy corrections.
Both branches independently adopted the same 30-minute native qualification budget;
retain main's workflow bytes and reconcile its provenance rather than changing CI.
The existing payload guard requires new candidates because main consumed the old
coordinates: ca `2.21.16`, ca-codex `0.13.17`, ca-pi `0.14.16`. Keep main's
original changelog history and synchronize adapter/runtime/generated identities.

Run full farm coverage, official generators, relevant static/authority contracts,
payload-version guards and normal final-head CI. Record each platform/runtime and
actual outcomes independently; another platform's percentage is not coverage union.
No threshold, coverage exclusion, test deadline or production timeout changes here.
Keep HTML farm disabled. Broader accounting, durable process resume, framework-backed
mutation classification and model-quality/resource measurements remain separate.
Revert the isolated tests, private cards and matching candidate metadata together
if rejected; preserve upstream admission/policy fixes and authenticated history.


### Hosted follow-through: original tag receipts

Normal run `36085674014` at `b711bd432f5354080fe2b8546424710be95e19a4`
exposed two newly published tags absent from the ledger. Original publisher run
`36084996407`, attempt 1, used main/workflow revision
`929229354e3a15ae3002c82116b66c837ab43729`. Its tag-creation logs and authenticated
artifact metadata were checked before the existing `reconcile_tag_receipt.py`
prepared append-only candidates. No current-ref observation was substituted for
original history; all prior identities and the separate legacy ledger are intact.

| Tag | Original tag object | Artifact | Downloaded ZIP SHA-256 |
| --- | --- | --- | --- |
| `v2.21.15` | `f74de069c2aa47728667ebf8060b471df485fffd` | `10843288417` | `d7f343833e59cb27daaaa59fdc3d871db2aca59aa31919d64bb0cb28e1ea7468` |
| `ca-codex-v0.13.16` | `c3a34e1ff51412fc39d4a2a20978efa471f49d1e` | `10842718926` | `19f0cfe70d40cafbc6d07d568714a556cc19fd5170bdd61f867b8cbabed39bc1` |

Both tag objects peel to that main commit. This records tag publication only:
the original release run failed later during Codex publication and skipped Pi.
Do not call the release cohort complete or repair it by retagging. This PR does
not rerun publication, change permissions, weaken immutability, or claim a release.


### Codex publication preparation path correction

Original publisher job `107915186019` refused preparation with
`Codex npm package and metadata must be real sibling files`. The composite
action put stdout metadata in the runner temporary root while the builder
created the tarball inside its exclusive `codex-npm-package` directory.
Move that same metadata beside the tarball only after the builder succeeds;
do not pre-create the builder-owned directory or weaken the sibling validator.
The same existing source, cohort, archive, integrity and publication guards remain.

Three tests execute the actual owning shell with the real packager and metadata
validator. Only repository authorization and registry lookup are test fixtures;
no real publication or provider request runs. With the final tests, the unmodified
`b711bd4` action fails the expected sibling check while both refusal controls pass.
After correction, all three pass, including mismatched-cohort refusal, an existing
staging-directory sentinel, exact payload/digest binding and preserved sibling/
tampered-tarball rejection. The full Codex distribution suite passes 28 tests;
the release workflow suite passes 171. Tag audit/receipt/reconciliation suites
pass 74/16/20 tests. The unchanged live auditor verifies 168 original receipts and
44 legacy baselines after the append-only correction.

This is a correction to the owning action for review, not recovery of the already
partial release. Release continuation must separately establish its exact cohort,
trusted verifier revision and current publication state; no release run was retried.


## 2026-09-25: verified merge-conflict recovery (PR854)

Baseline: `arbiterForge/codeArbiter@fdec093d20476533ca58f3fd0a5f3e4ff912c0da`.
That preserving merge incorporates main `13013b2fb021df623f4ba328ddb15f8b287590ad`.
The three overlaps with #863 were duplicate Codex metadata handoff fixes, their
regressions, and semantically identical tag receipts. Keep main's exact action
and ledger bytes and both test sets; the combined distribution suite has 29 cases.
Neither an old pending CI description nor the Project bootstrap is current proof.

The integration phase of `runTask` ignored staging, rollback and rebase failures.
Its retry also replaced the candidate before collecting prior-output feedback and
kept the first attempt's test hash even when the integration baseline legitimately
changed that test. A single-sample retry could mislabel baseline content as its
previous output; best-of-N could lose the selected implementation context.

Check staging before committing. After a real failed merge, verify rollback and
tracked integration cleanliness inside the existing merge lock, then pin the exact
integration commit. Capture the current qualified candidate before reset, verify
reset/clean and the resulting task HEAD, and bind the replacement protected-test
hash before setup or worker execution. The next attempt sees new current source
and separately labeled prior output, reruns setup fingerprints and all normal
checks, and uses the original task retry budget. A worker still cannot change its
test. Failed Git recovery keeps attempt, file, known usage and cleanup evidence;
it does not purchase a blind retry or manufacture acceptance. Commit diagnostic
content retains its existing 200-character limit with redaction before bounding.

Sixteen new injected-boundary cases and six real source/bundle CLI cases cover
successful recovery, retained samples, exact baseline identity, actual reset-lock
refusal, test tampering, stage refusal and exhausted budgets. CLI fixtures advance
only their own integration branch while a loopback worker is active, execute real
Git and narrow tests, and assert unchanged main/tests, request counts, prior
candidate feedback and both receipt formats. The original source fails 12 of the
14 unit obligations with two preservation passes; all six CLI cases fail against
the prior source/bundle. These are genuine assertion failures, not missing-export
or collection errors. Corrected selected suites pass all twenty-two new cases.

The conflict-only head's normal CI run 36094315974 exposed one Windows concurrent
receipt-fixture failure: bravo1 failed to commit after the unchecked staging call.
The old diagnostic does not identify why staging failed. No cause is inferred
from that incomplete evidence. Five selected and thirty additional bounded local
repetitions passed without changing concurrency, deadlines or assertions; those
repetitions do not by themselves establish a fix. Staging now preserves its own
failure diagnostic and repeats only the identical explicit-path stage up to three
times with bounded 150/300 ms waits. Two extra cases prove transient refusal can
clear without another worker, commit retry or extra authoring allowance. Permanent
refusal still blocks commit; no existing lock is deleted. Exact-head hosted requalification and remaining failures must
be reported separately in the PR, not erased by a local green run.

No public command, skill, agent, resident registry, dependency or authority producer
is added. Ignored caches, gate/mutation policies, versions and real approval rules
are unchanged. HTML farm remains disabled. This is bounded merge recovery, not
durable process resume or a whole-run concurrency redesign. Revert runtime and
bundle with their private projections and tests if rejected, preserving unrelated
main changes, authenticated publication history and retained worktrees. Final-head
CI, installed-host and model-backed evidence remain distinct qualification layers.


## 2026-09-25 resume: complete merge recovery verification and Pi CI ordering

The recovered implementation is `932913ffb003e916eff0f6a604b88fdc7e975e10`
(tree `a51ebb11447427fcb44c5e5ad3bd795ad5498134`), incorporating main
`13013b2fb021df623f4ba328ddb15f8b287590ad`. Its final local farm run completed:
**852 passed / 3 existing platform skips**, including both bounded-staging cases.
The prior in-progress description is superseded by this result, not by assumption.

Normal run 36095844564 passed farm and required merge readiness but failed native
Windows Pi job 107947862340 and its coverage aggregate. The bridge test observed
its delayed write marker; that log does not establish when teardown was triggered.
Replace the two competing wall clocks in the fixture with a ready/release protocol:
a real grandchild exists before the unchanged deadline is armed, and the one-way
write is released only after the call settles. Keep the full six-second absence
observation, timeout/cancellation responses, and each existing 15-second case cap.
Positive controls prove that no cleanup and root-only cleanup both expose a live
writer. Production bridge/process cleanup code and all production deadlines are
unchanged. Unknown original-run scheduling details remain unknown.

A separate disposable worktree reproduced the old marker failure with an injected
4.2-second pre-deadline driver delay. Under that same delay, the ready/release
fixture passes with identical production cancellation. This proves the fixture
race, not the exact original CI root cause or a hard-real-time kill guarantee.
The new positive controls would still fail a cleanup implementation that leaves
a writer alive after settlement; an absent marker without priming cannot pass.

Full native Windows Pi coverage: **879 passed / 1 existing platform skips**,
880 cases. Typecheck and all 19 generation/static/closure commands pass locally.
This is local Node 24.18.0 evidence, not the normal CI's Node 22.19.0 qualification.
The full farm implementation and bundle are byte-identical to the recovered head.
No test exclusion, required check, runtime timeout, authority or dependency changes.

Also correct the reviewed FARM_REQUEST_TIMEOUT_MS table: a valid excessive
Retry-After defers the task; it is not shortened into an early retry. Regenerate
all three host cards. Normal final-head CI and independent review remain separate.

## 2026-09-25: rendered enrichment budget and neutral retry evidence

Baseline: `arbiterForge/codeArbiter@9be3880514256cc8a2273b9800d07840e55d0188`.
This continues the attributed-feedback slice without changing its snapshots,
selection, retry allowance, or authority. The remaining retry footer and prior-file
label still asserted a failed gate; both now describe an unaccepted attempt and
retain the actual failure details. CodeRabbit independently identified that wording.

The old cap budgeted individual file renderings before the final prompt assembled
its section text and separators. Its marker-only fallback could exceed a tiny
limit, and decoding an arbitrary UTF-8 byte prefix could insert replacement
characters. The new single rendering boundary budgets the actual enrichment,
including its joining separator, section text, complete file frames and notices.
It reserves an omission notice before consuming the available space, preserves
code-point boundaries, and retains current-before-prior ordering. Too-small limits
omit enrichment rather than exceed the operator's setting. Task instructions and
failure details remain outside this specific cap; JSON escaping, token counts and
local file-read memory are not claimed bounded by it.

The default setting and discovery footprint are unchanged. An optional argument on
the existing pure prompt builder is only a test seam; runtime callers use the
existing environment setting. No provider request, permission, new user checkpoint,
registered operation, configuration knob or dependency is introduced. Protected
tests, actual verification, independent review, redaction and integration remain.
The canonical private card and its host projections explain the budget's extent.
This is source behavior, not a release or measured quality/cost claim.

Verification added 21 unit cases and eight real source/bundle CLI cases, and
strengthened the existing transmitted-context assertion. The same 30-case selection
against unchanged baseline source/bundle produced 28 assertion failures and two
preservation passes; the candidate passes all 30. The baseline CLI transmitted
2137 enrichment bytes for a 2048-byte limit, and 214 for a one-byte limit. Its
runtime and bundle were unchanged in a separate disposable baseline worktree.
No import failure or unselected test is counted as reproduction or a pass.

The candidate's complete native-Windows farm suite passed 895 tests with three
existing platform skips (898 cases). Local Node was 24.18.0. Coverage measured
73.85% lines and 71.83% branches, with no threshold, exclusion, collector or
source-scope change. Typecheck, exact bundle rebuild, official generation, all
19 selected static/host/resource/version checks passed. Current-head normal CI and
independent review remain separate obligations; no hosted result is inferred from
this local run. Native fixtures do not establish real-model quality or billing.

Revert this renderer, rebuilt bundle, tests, private projections and affected input
hashes together if rejected. Preserve earlier PR work, release identities and
ledger history. HTML farm remains disabled; durable process resume, complete
accounting and remaining command consolidation are not implemented by this slice.

### Hosted follow-through: exact synthetic-source exception

The c428014 current-tree scan identified the deliberately non-key redaction
fixture. Commit 150c729 preserves its exact 2574-byte runtime input while constructing
the delimiters at runtime. The current-tree scan then passed, but the PR-range
scan still saw the original source expression in append-only history.

The sole exception now matches the exact 103-byte historical TypeScript expression,
not expanded key material, by a whole RE2 literal quote inside the existing absolute
anchors. The validator permits that closed literal form only; an earlier quote exit,
active regex suffix, path/commit/stopword exclusion or changed matching target still
fails. No default scanner rule is removed and no file or commit is exempted.
Four new contract methods cover punctuation, quote exits, forbidden scope changes
and the exact source-value digest. All 89 CI-impact tests pass. Native Gitleaks
8.30.1 independently matched the original value and then passed the actual 45-commit
PR range with the proposed exception. An optional extra scanner-canary script could
not be created by the tool and was not executed or counted as proof. The required
hosted pinned-scanner run remains the final check, separate from native results.
The renderer/bundle are unchanged by these fixture/CI follow-ups. Full final local
farm coverage again passed 895 cases with three existing platform skips.


## 2026-09-25: debug and refactor single-owner entries

Baseline: `arbiterForge/codeArbiter@76e8880fb434820d1a9450268cdcdd411f8b927c`.
This slice revalidates two more command/skill wrapper candidates from the original
routing review. It is not a command-removal release or a farm enablement change.

The canonical debug and refactor command templates now contain one whole-file
SKILL_ENTRY declaration each. Their owning skills supply descriptions, arguments,
entry boundaries and complete procedures through the existing compiler. No new
composition grammar, runtime router, registry or loader is added. Existing command
spellings and internal skill/routine paths remain. Claude owners stay discoverable;
generated explicit aliases use the compiler's existing host-specific metadata.
Codex/Pi retain their public entry skills and private routines.

Complete pre-flight-through-hard-rules bodies are byte-identical to the baseline.
Debug still requires cited evidence, its existing hypothesis breadth, a named exit,
regression-test handoff and explicit ADR attribution. Its no-action note uses the
existing task helper, not the wrapper's ambiguous direct-append wording. Refactor
retains approved scope, existing-test parity, coverage, seam, lint and review gates.
Wrapper-specific intent exclusions and cycle prevention now live with the owner.
Explanation-only requests do not enter an editing procedure or require command syntax.

Both routes are selected by intent or explicit entry; that does not authorize an
unrequested fix, decision record, commit, push or PR. No phase approval or threshold
is removed. Same-name command/skill paths pre-existed; their bodies now agree.
Static projection checks are not installed-host discovery or token measurements.
Other candidate migrations, relaxed refactor scope approval, and debug-policy redesign
remain separate. Farm runtime, paired authority, public registry and HTML farm limits
are unchanged. Revert declarations, owner introductions, generated entries and tests
together if rejected; preserve accepted decisions, unrelated work and real authority.

The caller trace covered the routing table, spike/fix/chore/feature entries and the
skill index. Fix already owns bug diagnosis through its TDD variant; this slice
adds no recursive debug call. The routing table now points debug, refactor and the
previously consolidated commit/new-skill entries directly at their existing owners.
Explicit entry spellings remain documented. Refactor's route and index now include
its existing Phase 2 coverage-backfill path, not only the Phase 3 new-seam path.

Four test methods were added and the three existing composition/host checks extended
to both new owners. The nine-method owner group fails against old wrappers and passes
against the correction; the additional direct-route assertion separately fails before
the table change and passes afterward. All 24 local static, generator, host, route,
resource, provenance and candidate-version commands passed on native Windows. Neither
subtest assertions nor unrun live-host/model journeys are counted as extra test cases.
Farm runtime/bundle, compiler, host descriptors, public registry, native authority,
CI configuration and scanner policy are unchanged. Hosted current-head checks and
independent review remain separate from these local results.

### Retirement completion and preserving release merge (2026-09-25)

The interrupted retirement reached `ecea23b514407a7bb8d0d7d727f411db0e871746`.
Normal CI 36120148565 passed, but docs 36120148588 failed because the sidebar
regression still expected 38 command entries. The recovered test now pins 37,
the exact reduced visibility distribution, and absence of both retired pages;
alphabetical ordering, uniqueness and source-to-sidebar parity remain checked.

Main advanced to `b4febae70c9d24fdf760032992b9aae0acbbf818` through PR #865.
The preserving merge retains its independent-release implementation and ADR-0040.
The three old npm-publisher shell cases are superseded by that upstream removal
of their action and validator APIs; current Git-distribution tests are retained.
Main's changelog sections remain intact below fresh ca 2.21.17, ca-codex 0.13.18
and ca-pi 0.14.17 candidate sections. These coordinates are not publication proof.
The farm runtime, bundle, authority implementations and retirement stay intact.

The original review's fifteen D01-D15 relationships are now enumerated above;
three retained owners, one retirement and eleven pending candidates are distinct
from previously implemented catalog aliases. No extra deletion is authorized.

Local validation passed 31 source/generator/compatibility/release/version checks,
the focused sidebar regression and site typecheck. The normal site npm test
pipeline passed all 790 tests in 78 files, the Academy base-path check, site build
and rendered release-applicability checks. Early direct invocations lacked the
required npm generation context and used CRLF representations of pinned fixtures;
they failed and are not counted as passes. A fresh disposable checkout replayed
only verified indexed bytes before the normal pipeline; no fixture hash, test
obligation, tracked attributes or production gate was relaxed. Final-head hosted
CI and review remain separate obligations. HTML farm is still disabled.

The final merge parent also retains `a4842fab60a6e6ee943341861ec4aed0a7b17a50`,
which restores original ADR-0040 ancestry and adds only DECISION-0072 beyond
`b4febae...`. Its decision log is copied exactly; no acceptance event is
rewritten or rebound. The already-tested release implementation is unchanged.

### Final retirement continuation and native teardown (2026-09-25)

The resumed remote head was `5ac5caafb320dae221030e8a48c02260ed445a15`;
retirement and the sidebar correction were already published. Current main
`d171126e71e48b78d242c3d95b218236fdd8f61d` merges without content conflicts.
Its publication-receipt, static-candidate and documentation changes are retained,
not described as newly authored by this retirement slice.

CI 36128798325 failed on Windows ARM64 during conformance teardown after all
seven farm-boundary cases passed. The copied executable raised WinError 32;
the identity of its holder is not established by that log. Only the test-owned
installation cleanup now retries that exact sharing violation for at most two
seconds and 41 attempts. Other errors and persistent holds still fail. Six new
regressions cover success, transient/persistent errors, the attempt cap, unrelated
errors and a real held Windows file while preserving an unrelated sibling.
The exact conformance test inventory includes all six; no test or skip is removed.
Production process containment and cleanup remain unchanged.

The complete 13-case farm-boundary suite and 24 source/generator/resource checks
passed locally. The normal site pipeline passed all 914 cases in 87 files,
its base-path and rendered-build checks, followed by typecheck. A first local
conformance attempt lacked its declared jsonschema dependency; it is not a pass.
A fresh environment installs the unchanged hash-pinned conformance lock, rather
than relaxing the reference validator. The first site attempt used CRLF checkout
representations; exact index-byte replay in this disposable worktree restored the
source bytes without modifying tracked attributes or expectations. Hosted final-
head CI and review remain separate obligations. HTML farm is still disabled.

### D08-D11 and D15: first discovery-overhead slice (2026-09-25)

Authorized baseline: `35a3cd18a327fe5aa306ba452cc21ae096a24b02`. The maintainer
prioritized frontmatter reduction and explicitly included PR in the first slice.
This supersedes the earlier HTML-farm-next priority, not its qualification rules.
Debug and decompose source, references, generated copies and index rows are outside
this slice. D12/D13 and D14 remain separate mode/arbitration work.

Five command declarations now compose tribunal, security-architecture, context-check,
post-merge-cleanup and finishing-a-development-branch owners. Descriptions carry
intent and a material side-effect boundary; detailed phases stay in the loaded body.
Claude suppresses duplicate explicit command metadata while retaining discoverable
owners. Codex/Pi retain their five discoverable entry names and private routines.
No discovery registry, new public capability, mode grammar or tool permission was added.

| Description values only | Before | Candidate |
|---|---:|---:|
| tribunal | 221 | 133 |
| threat-model | 149 | 128 |
| context-check | 193 | 109 |
| cleanup | 216 | 113 |
| pr | 148 | 140 |
| Five public-entry descriptions | 927 | 623 |

These Unicode-character counts exclude keys, names, paths, argument hints, host
formatting and tokenizer effects. The five Claude command files now explicitly
suppress model invocation; same-name resolution may already deduplicate a listing.
No live-session entry count, retained-context saving or model-routing score is claimed.
Command/skill inventories remain 37/22. Eight original relationships now retain a
single-source owner, one is retired, and six remain (D03/D04/D07/D12/D13/D14).

Tribunal evaluates applicability across the roster and roots support-card references;
its report writes, cost acknowledgment, independent triage, filing and telemetry
boundaries remain. Threat modeling retains read-only analysis and relevant ADR inputs,
with PROCEED / PROCEED-WITH-CONSTRAINTS / STOP rather than blanket binary clearance.
Missing required controls remains a separate prerequisite failure. Drift and cleanup
retain their complete preflight-through-hard-rules operational bytes.

PR dispatches watch/cleanup before creation prerequisites. A direct open-PR request
already chooses open, while feature/sprint handoffs retain their distinct authority.
The owner contains the common review/body/babysitter sequence, with no reference back
to its generated wrapper. Its original acceptance and ancestry preflight is unchanged.
The compiler validates mode closure against the same resolved template it renders;
missing, duplicate and extra markers still fail, as does exposing one owner twice.
No general include engine or new frontmatter dialect was introduced.

Fourteen regression methods exercise these boundaries and existing compatibility
checks explicitly account for the named ownership moves instead of discarding their
historical fingerprints. Exact package validation also caught a dynamic lens link:
the owner now names the verified lens directory and recorded slug, not a generated
Markdown destination containing an unsupported placeholder. The original route set,
reviewer resources and non-targeted owner bodies remain intact. Normal hosted CI,
independent review and live-model/installed-session measurements remain distinct.


### D12/D13 — one ADR owner, read-only status first (2026-09-25)

Baseline: `578065076e2e11a4e63f33256cb386a5cba1d7d2`, PR #854. The maintainer
approved D12/D13 together after the five-owner frontmatter slice. D14, debug,
decompose and the shared ADR template are outside this increment.

`adr` composes `decision-lifecycle`; `adr-status` is a small mode adapter into
that same owner, not a second procedure or composed-owner exception. Claude's
two explicit entries suppress redundant model descriptions; Codex/Pi retain their
two existing public names. No command, skill, agent or discovery registry is added.
One new source-only procedure reference and its three generated copies carry the
existing authoring/acceptance instructions without discovery frontmatter.

The owner selects read-only status before any writable preflight. Missing directories,
missing/invalid evidence, ambiguous numeric selectors and unresolved questions are
reported without creating or repairing records. Author titles are not mode selectors.
Only explicitly authorized authoring or stored-status transitions load the authoring
reference. Existing-record transitions do not allocate a new ADR number. A routine
finding or general trust remains insufficient decision authority. Two existing ADR
sentences in safety-core name the authorized workflow, rather than requiring the user
to spell a slash command; the marker, immutable-record and attribution rules remain.

The complete Accepted/Planned binding procedure and shared ADR template retain their
baseline bytes. The source lifecycle tests follow the extracted procedure rather than
dropping their ancestry/acceptance assertions. The twelve new source/host checks fail
against the original surface and pass against the candidate; those are prompt-contract
and resource tests, not proof of actual model intent routing or side-effect behavior.
The unchanged runtime lifecycle suite passed all 61 cases during discovery validation.

The source public descriptions and native loader evidence must be measured per host;
no prompt-token or model-quality improvement follows merely from file counts. The
same 37 command records and 22 top-level source skills remain. D12/D13 complete two
more ownership relationships, leaving D03/D04/D07/D14 separate. Exact final-head CI,
review and installed/model-backed qualification remain distinct obligations.

Rollback the two entries, shared owner, authoring reference/projections and targeted
source/documentation tests together; keep the original template, approval bindings,
other agents' work and unrelated farm behavior intact. No HTML-farm rollout change.


D12/D13 local source qualification completed 28 commands, including all 61 lifecycle
cases and 116 surface-compiler cases (one existing native-Windows skip). Three new
operator-documentation cases also passed. Before/after Codex 0.145.0 directory
metadata discovery retained both enabled entry names without skill errors; combined
descriptions fell from 232 to 174 characters. This excludes other frontmatter and
host framing, uses no model turn, and does not claim prompt-token savings. The full
site pipeline and final-head hosted checks are recorded separately on PR #854.


D12/D13 source-move documentation qualification: the ADR execution map retains its
historical main-ancestor revision and uses an explicit editorial `currentPath` for
its relocated procedure. Every cited quote must still occur in both the pinned
historical blob and current owner. The original ancestry test is unchanged; no
pre-merge commit becomes a durable documentation dependency. Two regressions cover
relocation and invalid current-path handling. This is site data, not a runtime or
model-facing routing registry. The normal site pipeline passed all 920 tests in
87 files plus base-path, build, rendered-output and type checks. One earlier local
sidebar import test exceeded its existing five-second limit; both its unchanged
isolated rerun and the final full run passed. No timeout or assertion was changed.
