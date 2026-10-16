# Assistive state-engine overhaul

**Delivery:** one implementation PR against `arbiterForge/codeArbiter`, followed by the normal authorized release workflow.
**Branch:** `overhaul/assistive-state-engine`
**PR title:** `refactor(state)!: replace artifact permission gates with assistive orchestration`
**Product direction:** approved by the product owner on October 14, 2026.
**Source baseline:** `main` at `045c0812888f20f4c843677cfb37b802e2084770`. Reconcile with the actual checkout before editing. This is development evidence, not an installed-package claim.
**Progress:** this document defines the complete PR. Actual completed work, tests, and the next continuation point belong in `assistive-state-engine-progress.md`; unchecked tasks are not implemented or released claims.

## Assignment and fixed decisions

Implement the overhaul in **one branch and one PR**, using incremental commits. Do not deliver a planning-only PR or distribute the core correction across later releases. An initial draft PR may contain a bounded implementation slice, but must remain draft until the complete compatible overhaul is ready.

The engine must help the agent follow and maintain its plan, coordinate work, retain honest progress and evidence, render human-readable HTML, and retrieve small symbol-bound context packets. **It must not be a second permission system for already-authorized work.**

Replace the normal behavior, not an optional relaxed mode. Do not implement auto-approval, synthetic receipts, an environment-variable bypass, another permission broker, or a configurable enforcement framework. Do not preserve the old workflow as the default underneath friendlier wording.

Keep typed state, stable IDs and links, revision-conflict protection, transactional writes and recovery, evidence history, bounded retrieval, and safe HTML rendering. Preserve actual host permissions, user stop/deny instructions, sandbox and filesystem protections, and independently applicable repository/CI/publication controls. Remove artifact-origin permission dependencies even when surfaced indirectly through hooks, prerequisites, context delivery, commit preparation, or orchestration prompts. Do not make every check return success or disable every hook.

Observable facts are checked through ordinary authorized tools. Consequential unresolved product choices are asked in normal language. Existing authorization does not need to be recreated as an artifact receipt. Explicitly requested human checkpoints remain meaningful; the engine must not add checkpoints of its own.

Scope includes the engine, callers, generated adapters, tests, migration, product documentation, and release integration inside `arbiterForge/codeArbiter`, including public `ca-pi`. No other repository is part of this PR. Do not incorporate downstream or employer material. No universal state migration, database/daemon rewrite, Academy overhaul, catalog redesign, or new audit program.

## Target behavior

| Situation | Required behavior |
|---|---|
| Work is already authorized | Create/read/update the plan and execute ordinary in-scope work without artifact approval prompts. |
| An observable prerequisite exists | Check it, record the observation, and continue or explain the actual obstacle. No user certification code. |
| One task lacks a real dependency | Keep that task waiting; continue independent work. Checkpoint numbering is not a dependency. |
| The implementation method changes | Update steps, test commands, decomposition, or valid ordering with a concise reason. Preserve the agreed outcome. |
| The requested outcome would materially change | Surface the choice and consequence; ask once where necessary, without a digest-bound approval exchange. |
| Implementation is finished but checks are outstanding | Record implementation complete with verification pending/failed/unknown, not a fabricated success or forbidden state. |
| A check is rerun on unchanged relevant inputs | Attach the new result. No automatic code-review restart. New failures still affect the current assessment. |
| Relevant implementation changes | Mark affected evidence as needing refresh; preserve historical results and unaffected work. |
| Presentation or routine bookkeeping changes | Update the artifact without invalidating unrelated source evidence. |
| A session resumes | Inspect work, reconcile progress, and continue. No reconciliation code or mandatory review replay merely because the process restarted. |
| A write conflicts or cannot complete safely | Reject that write, preserve data, and report recovery/conflict details. Never claim it succeeded. |
| The host denies an operation | Respect the denial. The state engine cannot grant permission. |

Reuse existing fields where feasible. Separate work progress, verification assessment, and decision notes semantically; do not add another authorization state machine. Displayed completion must not imply unrun tests passed, a review occurred, or a release shipped.

## Ordered implementation tasks

### T01: Establish the replacement contract and trace callers

**Depends on:** none.

Inspect the branch and repository instructions; preserve unrelated work. Trace execution, resume, prerequisites, context delivery, and commit/push preparation from the source map below. Make a compact disposition table: **keep for data integrity**, **convert to advisory/workflow state**, or **remove as duplicate permission ceremony**. Record a concise decision using the existing repository convention; identify superseded decisions without rewriting historical bodies.

Capture a small before-change fixture with a spec/plan, dependent and independent tasks, one observable prerequisite, verification, and review. Count artifact prompts, engine calls, snapshots, and reviewer launches. Capture the base once; this is not a new benchmarking project.

**Done when:** blockers and owning callers are identified, the target contract is recorded, and implementation begins in this PR. Do not send the product direction back for approval.

### T02: Remove artifact permission gates from the core lifecycle

**Depends on:** T01.
**Entry points:** `core/artifacts/internal/operations/lifecycle.go`, `engine.go`, model/schema/validation/authority/evidence callees.

Decouple task selection/start/progress/resume, plan binding, and scope completion from approval receipts, blanket prerequisite approval, context-delivery tickets, and globally fresh predecessor-review chains. Replace ordinary execution use of `guards`, `prerequisites`, `priorScopes`, and `taskEligible`; do not make `authority.Approved` always succeed.

Make eligibility a scheduling assessment of actual dependencies and observations, not permission to mutate. Permit incomplete and failed work to be recorded accurately. In-scope method changes and plan maintenance preserve unrelated progress. Material requirement changes remain visible for real decisions; whole-document hashes do not make those decisions.

Keep structure/path/ID checks, safe writes, compare-and-swap, and replay/recovery. Distinguish diagnostics from operation failure so callers cannot treat every warning as STOP. Malformed or ambiguous data must not be reported as successfully saved.

**Done when:** a valid working spec/plan without artifact approval receipts supports authoring, starting, updating, revising, resuming, and implementation completion. Missing verification remains visible without prohibiting implementation.

### T03: Make prerequisites and plan changes useful

**Depends on:** T02.
**Entry points:** prerequisite/binding lifecycle operations; `_prerequisitelib`, `_approvallib`, and sprint-method callers.

Distinguish observable conditions from genuine human decisions using existing records and the smallest necessary schema change. Associate prerequisites with the tasks that need them. Preserve explicitly shared prerequisites where real; do not assume every prerequisite blocks the whole plan.

Allow the agent to record a factual observation with source and outcome. A failed check describes an obstacle, not a permission request. Reading a prerequisite must never execute embedded commands; checks run through ordinary host-governed tools.

Allow changes to steps, verification commands, decomposition, and dependency-valid ordering within the agreed outcome, retaining reasons and stable references. No score, method grant, renewed spec/plan pair approval, or receipt renewal is required for those edits. Do not silently remove requirements or acceptance criteria to manufacture completion.

**Done when:** a factual prerequisite needs no user prompt, unrelated work proceeds while another task waits, and an in-scope task split or runner change does not invalidate the entire plan.

### T04: Decouple evidence freshness from reviewer dispatch

**Depends on:** T02-T03.
**Entry points:** `core/artifacts/internal/evidence/`, completion/freshness operations, artifact include, verification/review callers.

Preserve results as historical observations. Assess applicability against the relevant subject rather than only artifact revision or receipt identity. Reuse task paths, criteria, and test/configuration inputs; include additions, deletions, renames, shared interfaces, and relevant configuration. Do not build a perfect AST graph or a new impact-analysis platform.

Separate presentation/bookkeeping from normative requirements and actual verification inputs. Unrelated edits do not invalidate everything. Insufficient scope or uncertain impact produces an unknown assessment and proportionate investigation, not false freshness or a reviewer fleet.

Remove fresh completed-task review requirements caused solely by a different verification receipt. Retain findings; revisit affected conclusions when reviewed code, requirements, or relevant results change. A new failing/flaky run must not be hidden behind an older pass.

Accept useful ordinary command results. Unsupported named-test parsing retains command, working directory, outcome, and bounded output at command-level fidelity. Do not invent named-test coverage or block all work until a custom collector exists. Distinguish observed tool results from model-reported notes; never fabricate host/reviewer events.

**Done when:** unchanged-input reruns and presentation edits cause zero automatic reviewer redispatches; relevant changes refresh affected assessments or scoped uncertainty; failed/skipped/unrun/unknown checks remain distinguishable.

### T05: Simplify actual orchestration and host paths

**Depends on:** T02-T04.
**Entry points:** `_artifactlib.py`, artifact-include callers, canonical planning/execution/TDD/resume/sprint/context-delivery instructions.

The normal sequence becomes: obtain task context, do or delegate useful work, run appropriate checks, update progress/evidence, continue. Do not require a fresh author plus spec reviewer plus quality reviewer for every small task. Prefer combined review for meaningful completed work when warranted, adding specialists for a concrete risk or explicit requirement. Corrections return to affected work, not an unrelated review chain.

Remove active requirements for approval/prerequisite/reconciliation codes and context-delivery authority. Remove artifact-only checks from indirect commit/push preparation while retaining independently applicable Git, CI, security, and publication controls. Do not disable all hooks.

Narrow installed-workflow admission to capabilities needed for the operation. HTML authoring must not require every future reviewer/authority producer. Remove obsolete Pi authority-adapter dependencies rather than implementing the unwanted protocol. A flag change does not prove host qualification.

Keep automatic context assembly, relevant constraints, honest command capture, and supported host invocation. Report missing binaries and failed writes accurately; do not create a competing canonical ledger. Authorized investigation/implementation may continue with an explicit bookkeeping gap where safe, never a claim that an unsaved artifact was saved.

**Done when:** the real caller path completes the fixture without artifact permission codes, compulsory per-task review chains, or stop-on-warning behavior. Host denials and requested human checkpoints still work.

### T06: Keep symbol reads compact and HTML useful

**Depends on:** T02; coordinate with T04-T05.
**Entry points:** existing `read`, `read-batch`, `outline`, `plan-verification`, read package, renderer, bridge.

Reuse bounded/batch reads and shared-observation locking. Provide a small task packet with referenced requirements, relevant dependencies/constraints, progress, outstanding checks, and next useful action. Extend the existing API, not the public command catalog or a persistent service.

Informational reads do not need authority tickets, receipt chains, or verification execution. Keep pagination and explicit omitted/missing-context indicators; no silent truncation. Relevant facts retain actual freshness; viewing state does not require a whole-repository verification snapshot.

Render the same content into readable HTML with stable anchors, separate progress/verification labels, outstanding decisions/checks, safe escaping, and existing styling. Models must not consume HTML/CSS or a complete schema dump for normal reads.

Measure the same fixture before/after: model-visible bytes, native calls, full snapshots, and elapsed time. Remove avoidable calls without arbitrary cross-platform latency promises or a database/cache release dependency.

**Done when:** normal task lookup returns bounded structured context without markup, permission receipts, or verification execution; HTML is accurate; counts demonstrate removed ceremony.

### T07: Upgrade existing work without reapproval or data loss

**Depends on:** T02-T05; design alongside T02.
**Entry points:** schema/reader, transactions/recovery, pending-state handlers, version negotiation.

Provide an idempotent upgrade for existing HTML pairs and unfinished tasks. Preserve IDs, links, edits, progress, findings, evidence, and history. Old approvals remain historical; do not fabricate consent, relabel stronger proof, or demand fresh approvals. Explicit denials/stops never become permission.

Separate pending prompts from unfinished writes/processes. Retire obsolete prompts with a superseded disposition; recover actual writes from durable outcomes. Do not delete `.codearbiter` or receipt/history directories. Avoid duplicate dispatch after response loss or while work is still running.

Do not force Markdown-to-HTML or universal context migration. Existing Markdown retains its representation without replacement ceremony. Derive API/schema changes from compatibility and prevent old clients silently writing new semantics; provide clear update/read-only guidance.

Back up affected state only. Document rollback before later edits and forward recovery/export after them. Reverting a package must not overwrite work performed after upgrade.

**Done when:** old interrupted HTML work resumes without an approval code or duplicate work; replay is safe; IDs/history survive; rollback and mixed-client behavior are tested.

### T08: Regenerate adapters and align documentation

**Depends on:** T05-T07; prepare documentation in parallel.
**Entry points:** canonical `core/surface/`, generators/packaging, `plugins/ca`, `plugins/ca-codex`, `plugins/ca-pi`, manifests, product docs.

Change canonical sources, then regenerate with current tooling. Do not independently patch generated copies. Update active descriptions, examples, metadata, capability checks, guidance, resources, and workflow diagrams/pages. Search active surfaces for obsolete codes and review-receipt coupling; historical examples remain clearly historical.

Remove dead ceremony-only code, registrations, fixtures, and references where safe. Keep small historical readers, not a permanently maintained second execution mode. Update README, relevant parity/compatibility and upgrade docs, and changelog. Preserve independent host versions and maturity; a major overhaul does not invent version numbers or declare every adapter stable.

Disclose changed applicability in codeArbiter-owned training links where needed. Record derivative follow-up for other authorized repositories without editing them, moving immutable Academy tags, or blocking this PR on separate curriculum work.

**Done when:** generated adapters, active docs, implementation, and installed resources agree; no active instruction recreates the approval loop.

### T09: Prove the streamlined journey and finish the release-ready PR

**Depends on:** T02-T08.

Add the acceptance scenarios below primarily in a small integration fixture with focused boundary tests. Rewrite tests that preserve removed ceremony. Keep integrity, actual permission-denial, and truthful-result tests. Do not delete failures wholesale, fake success, weaken protections, or bypass required CI.

Run targeted checks while iterating. Before marking ready, run applicable aggregate, generator/resource, and built-package checks against the final candidate using existing build/CI tooling. Fix relevant failures; identify exact unrelated blockers honestly.

Exercise an installed end-to-end canary on an available supported host, recording host/package identity. Test shared changes and packaging for shipped adapters. Do not invent an all-model/all-platform live matrix; preserve existing release policy and label unexercised cells unverified. Source tests are not installed-host proof.

Maintain this one PR with implementation, migration, generated changes, documentation, actual results, breaking changes, and rollback. Do not stop at a plan commit or an unexplained red CI run.

**Done when:** the compatible complete candidate is merge-ready under existing controls; exact remaining publication actions are recorded, not claimed complete.

## Execution order

### T10: Refresh project context and reconcile active guidance

The owner expanded this PR on 2026-10-16 to include context coverage and project
catch-up. Inspect all six context categories and refresh the five content
documents from current source. Extend ordinary native preview/apply to this
authorized work without per-document approval codes or compulsory qualified
scout exchanges. Preserve initialized state, source identities, explicit selected
scope, concurrent-edit checks, paired writes, before-images and recovery.

Reconcile active documentation, metadata and release declarations with the
implemented direction. Close inherited tasks only when their done-when is
actually evidenced, through their existing writer. Preserve historical accepted
results and unresolved user decisions. Fix concrete workflow defects exposed by
this traversal, without weakening host permissions or repository safeguards.

**Done when:** all five records bind the inspected current document/source bytes;
independent semantic review and its limits are recorded separately; active
callers and generated resources agree; relevant regressions, release-owner proof
and exact-head hosted checks pass. Unrelated features, unexercised live model
cells and publication are reported separately rather than declared complete.

Main integration: **T01 -> T02 -> T03 -> T04 -> T05 -> T07 -> T08 -> T09**. T06 may proceed when the T02 model contract is stable. Migration design starts with that contract. Add tests alongside owning changes; T09 is final integration, not the first testing step.

A secondary worker may own compact reads/HTML or docs/fixtures with separate file ownership and one integrator. Do not create coordination/review overhead larger than the work. All commits converge here; do not release half-updated engine/callers.

## Acceptance scenarios

| ID | Scenario | Required observation |
|---|---|---|
| A01 | Authorized feature, no artifact approvals | Author, execute, update HTML, continue with zero artifact permission prompts. Count host permissions separately. |
| A02 | Factual prerequisite plus unrelated task | Record the check; only actual dependent work waits when it fails. |
| A03 | In-scope method, runner, or decomposition change | No user code, whole-plan reset, or unrelated review restart. |
| A04 | Same-input rerun including later failure | Retain new result; zero automatic reviewer launches; no masking failure with older pass. |
| A05 | Relevant edit then presentation-only edit | Affected checks become stale/unknown; unrelated evidence remains useful; presentation causes no cascade. |
| A06 | Shared input, added/deleted file, uncertain impact | Relevant scope/uncertainty visible; no false freshness or default reviewer fleet. |
| A07 | Unrun/failed checks, unsupported named parser | Progress remains recordable; no invented verification or named-test proof. |
| A08 | Real decision, explicit stop, host denial | Normal-language decision handling; no prohibited action or synthetic authority. |
| A09 | Old interrupted plan, obsolete prompt, uncertain operation | Preserve work/history, avoid duplicate execution, resume without new ceremony. |
| A10 | Concurrent edit, malformed data, interrupted write, replay | No lost updates, unsafe writes, silent success, destructive rollback. |
| A11 | Task retrieval and HTML | Bounded context, stable anchors, safe escaping, accurate labels, no routine snapshot/receipt ceremony. |
| A12 | Built candidate and installed host | Generated resources agree; ordinary installed journey completes; identities and unverified coverage reported. |

These are scenarios, not twelve new frameworks or compulsory model runs. Retain compact evidence: candidate commit, fixture, commands/outcomes, prompt/reviewer/engine-call/snapshot counts, model-visible bytes, timing environment, migration/rollback result, and installed-canary identity. Link logs instead of copying huge transcripts into model context.

## Release and rollback

Use current release tooling and per-adapter version policy. Record intentional breaking behavior/API changes and keep engine, bridge, generated callers, and resources in a compatible cohort. A source checkout is not the binary-bearing distribution.

After merge, use normal authorized publication. Confirm each shipped tag, release, archive/package digest, contained engine/bridge versions, generated resources, and promoted marketplace/npm reference. Check clean install or documented upgrade from those bytes. Never move a published tag or relabel historical evidence.

Report implemented, candidate tested, published, and installed verified separately. Shipping requires distributed-artifact readback, not green main. This handoff grants no credentials or exemption from publication controls.

Rollback uses the supported previous-package path and preserves post-upgrade work. Restore backups only when no later edits are lost; otherwise use forward recovery/export. Record old-client write restrictions. Never delete history or silently revert project files.

## Source map and currentness

All entries are development source at `arbiterForge/codeArbiter@045c0812888f20f4c843677cfb37b802e2084770`:

| Path | Relevant ownership |
|---|---|
| `core/artifacts/internal/operations/lifecycle.go` | Approval guards, prerequisites, earlier scopes, task freshness, eligibility and progress. |
| `core/artifacts/internal/operations/engine.go` | Shared observations, bounded/batch reads, transactions, CAS and recovery. |
| `core/surface/includes/artifacts.md` | Admission, codes, context tickets, completion-review coupling and reconciliation. |
| `core/pysrc/_artifactlib.py` | Installation-pinned bridge, bounded envelopes, capability and workflow admission. |
| `core/surface/skills/subagent-driven-development/SKILL.md` | Author/reviewer sequence, eligibility/receipt dependency, context delivery and quality review. |
| `package.json` | Pi publication identity/resource inventory, not installed npm evidence. |

The October 7 Project baseline is historical. Its recommendation to preserve identical negative refusals is superseded for artifact-origin workflow restrictions by the October 14 owner direction. Keep its historical measurements. Its broad exclusive-lock description is not current: shared observations and batch reads already exist; reuse them.

For later Project Source maintenance, append this product-specific decision to `05-DECISIONS-AND-OPEN-LOOPS.md`, add a planned assistive-engine claim in `02-CROSS-SURFACE-CLAIMS.yaml`, and record superseded recommendations and actual implementation status in `04-AUDIT-AND-DRIFT-LEDGER.md`. Do not relabel old measurements/releases or assume this PR automatically replaces those private Project files.

## Final implementation report

Report confirmed results, contradictions resolved/remaining, canon or claim-registry delta, affected surfaces, decisions needing approval, verification still required, and the next action. Distinguish PR, merge, package, and release states. There is no remaining product-direction approval to request; surface only a genuinely consequential unresolved choice or actual authorization boundary.
