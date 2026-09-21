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
