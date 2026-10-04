# First failure premortem: exercise-ready brownfield

**Review type:** author self-review of the actual draft, not independent spec-review authority.
**Question:** We finished the implementation, used it at the exercise, and failed hard. Which omissions in the specification allowed that?
**Disposition:** amend before implementation; revised draft is ready for maintainer and independent semantic review, not approved to execute.

## Exact review boundary

Initial specification: `SPEC-EXERCISE-BROWNFIELD`, revision 1, at `arbiterForge/codeArbiter@96f4a052ca057c2085c5241f6fcf7f5f616d5ce2:.codearbiter/specs/exercise-ready-brownfield.html`.
Initial model SHA-256: `fcad02ca1e8c0b54478c8642ac40c172427fbdd6af6e2989e3e273a3e87c2f2f`.
Initial HTML SHA-256: `2255a9b0fc9b369adc3a86044a8a38f833a96dc77d799aea56cbbc2b99f6173c`.

That candidate had 32 criteria and passed the engine's ready gate. It still admitted the failure stories below. These are projected implementation failures and spec omissions, not claims that the unimplemented feature has actually failed. The assessment's reproduced defects remain separately bound to its historical evidence.

The first draft is retained in Git history at the same canonical path, not as a second live specification. The resulting draft has 41 criteria and 84 positive/negative scenarios. Ten original criteria were tightened and nine new criteria were added. The engine performed all canonical HTML/model mutations; no rendered HTML or embedded JSON was edited directly. Revisions 2 through 4 are the same first review's amendments and owner/write-boundary follow-through, not independent reviews.

## Failure stories and spec corrections

### PM-01. We marked the repository ready before it was usable

**Failure:** every file was nonempty, so initialization completed, but the audit log was malformed, a stub example contained the sentinel, or a file changed after validation.
**What r1 missed:** completion-last was necessary but did not fully define the common marker parser and same-snapshot finalization across readers.
**Correction:** AC-005 now requires file-specific states, a shared parser and a real standalone body marker outside examples/frontmatter. AC-033 binds finalization to current relevant identities.
**Rejecting evidence:** partial-write fault injection, an embedded-sentinel stub, and a validation-to-finalization race must not result in initialized readiness.

### PM-02. Every scout returned, but the system either guessed or blocked everything

**Failure:** an ambiguous data-domain finding was counted as complete truth, or a valid no-database project could never pass the six-scout gate.
**What r1 missed:** report transport completion, evidence coverage and user-owned decisions were not explicit enough as separate dimensions.
**Correction:** AC-008 defines exact confidence normalization and separates transport status from category outcomes. AC-009 retains six reports and bounded joined coverage. AC-036 requires both solvable positive controls and genuine blocking controls.
**Rejecting evidence:** a static repository with valid test commands must complete a relevant task without a database interview; a missing required report must still block. Unknown is never converted into not applicable for convenience.

### PM-03. A read-only scout wrote files through its shell tool

**Failure:** the agent charter said read-only and the host type was named explorer, yet it had ordinary shell write access.
**What r1 missed:** it demanded containment but did not identify an implementable non-prompt-only alternative on hosts lacking a native sandbox mode.
**Correction:** AC-010 permits demonstrated read-only sandboxing or removing mutating/command-execution capability from this scout profile. Trusted deterministic hashing can provide identities without forwarding source to the synthesizer. Existing decision-variance behavior is not silently changed.
**Rejecting evidence:** harmless attempted writes must be denied and distinct child contexts observed. Prose roles, a preferred type name or agent self-report cannot qualify the path.

### PM-04. All reports cited the same commit, but different working trees

**Failure:** dirty changes, staged content, a lockfile or a newly added nested instruction changed while scouts ran. The reports were joined because HEAD matched.
**What r1 missed:** the required Git identity inventory did not define admission across collection, synthesis, preview and action boundaries.
**Correction:** AC-033 binds evidence and work to the relevant worktree content and membership, not only HEAD/common-dir/branch. Reacquire affected evidence on detected drift.
**Rejecting evidence:** deterministic mutations at each boundary must invalidate stale reuse. The cooperative model is retained; no hostile same-user ABA-resistance claim is made.

### PM-05. The host obeyed stale instructions before our freshness hook ran

**Failure:** a native AGENTS/CLAUDE file loaded eagerly. Later validation correctly detected staleness, but the specification had implied that prevented stale context from entering the model.
**What r1 missed:** the distinction between preventing initial injection and preventing reliance at a cooperating material-action boundary.
**Correction:** AC-034 states the limitation directly. Observe the stale load, then require qualified action admission; otherwise use stable pointers or no files. Non-Arbiter consumers are not silently covered by a new enforcement promise.
**Rejecting evidence:** a stale native sentinel is included in the request, but dependent action must stop. A post-load warning alone is not sufficient.

### PM-06. Atomic file writes still exposed a mixed publication

**Failure:** one subtree received generation B and another retained A after interruption. Each file was individually valid.
**What r1 missed:** journal/replay requirements did not by themselves define admission of a whole view set.
**Correction:** AC-025 now requires generation-set consistency; AC-034 rejects the mixed set before cooperating task reliance. E1's legacy per-file recovery explicitly makes no all-or-nothing filesystem claim.
**Rejecting evidence:** interrupt between every replacement and attempt a multi-subtree task. Single-file hashes or successful renames must not admit a mixed generation.

### PM-07. We made our new guidance cheap by truncating someone else's rules

**Failure:** the total-context cap was met by trimming human instructions, while the optional old map became a global blocker.
**What r1 missed:** budget ownership and advisory-versus-mandatory failure behavior.
**Correction:** AC-023 applies new managed budgets to added content/imports and measures existing human instructions separately. AC-016 preserves old content and permits bounded source orientation on an advisory miss without waiving task-critical constraints.
**Rejecting evidence:** a large human-owned root file remains unchanged; no silent truncation, takeover or blanket read denial is accepted.

### PM-08. Benchmarks improved only because we moved the work elsewhere

**Failure:** later tasks looked faster, but uncounted onboarding, retries, refresh, cache behavior or human interventions erased the gain.
**What r1 missed:** a concrete predeclared retention threshold and explicit no-go/inconclusive outcomes.
**Correction:** AC-028 separates shared B improvements from C. AC-037 fixes a five-task sequence and at least three independent retained-profile sequences, requires at least 20 percent lower later exploration response bytes with no higher sequence-total observed input-plus-output tokens, at most 2 KiB added startup guidance, no added required human interruption and no safety/correctness/preservation regression.
**Rejecting evidence:** omit a failed scout, choose the winning metric after running, or lack usage attribution and the result is no-go/inconclusive. Bytes are not tokens; token counts are not dollar savings. These proposed thresholds need approval and are not measured benefits. Paid trials require separate resource authorization.

### PM-09. We promoted an upstream convention into local policy

**Failure:** a high-confidence report copied an upstream accepted ADR or README rule into the fork and silently displaced a local approved constraint.
**What r1 missed:** the old context documents, not only P1 publication, could launder observed text into local authority.
**Correction:** AC-035 covers legacy synthesis as well as future views. Conflicts keep both sources; actual local normative adoption needs its existing authority boundary.
**Rejecting evidence:** HIGH confidence, matching hashes, accepted labels and model-authored approval fields must not settle a policy conflict.

### PM-10. Passive discovery executed code or contacted the network

**Failure:** a hash command invoked a configured clean filter, or activation installed Git hooks/started transport before the exercise's permission boundary was established.
**What r1 missed:** saying not to run install/test/deploy scripts did not cover implicit helpers and startup side effects.
**Correction:** AC-038 inventories activation separately, observes helper/network effects and requires an approved inert hash method or an explicit unavailable-evidence state. Hash methods cannot silently change meaning.
**Rejecting evidence:** benign sentinel filters and denied-network fixtures must remain unexecuted during passive discovery. No permission expansion or global setting change is used to make the test pass.

### PM-11. The optional experiment held the exercise hostage

**Failure:** Claude/map-only work was useful, but the team waited for every platform, greenfield feature and native-guidance pilot. Or skipping the pilot was called complete implementation.
**What r1 missed:** a criterion-level disposition rule for independently useful slices.
**Correction:** AC-039 permits exact E0-E2 acceptance while P1 is no-go and Codex is unverified. AC-028 and AC-037 explicitly condition C trials on pilot selection. Conditional work is not relabeled shipped.
**Rejecting evidence:** neither a skipped pilot nor an unqualified host can be hidden under an all-green campaign status.

### PM-12. Context delivery turned a review into an implementation project

**Failure:** a read-only review spawned files, or a test-only task changed product behavior just to manufacture RED or create a new spec pair.
**What r1 missed:** enumerating task classes was not enough to preserve their caller-specific authority and TDD boundaries.
**Correction:** AC-040 preserves read-only and existing test/bug-origin routes without waiving required TDD. Documented transient host state is measured separately from user-owned repository files. Coordinate with #871 rather than replacing its diagnostic contract.
**Rejecting evidence:** review conserves tracked and existing untracked user content; new canonical/native files and forced feature routing fail.

### PM-13. We governed the new kind but left legacy context as an unrestricted rewrite lane

**Failure:** the P1 JSON contract was strict, while an orchestrator still freely rewrote tech-stack or security-controls and erased human policy during refresh.
**What r1 missed:** file-level CAS preserves concurrency, not schema ownership or bounded semantic mutation.
**Correction:** AC-041 requires closed versioned file-specific helper inputs, allowed target/field identities, current evidence and the existing authority references. Unsupported shapes are preserved and reconciled; a new governed representation requires its per-kind transition, not a competing generic writer.
**Rejecting evidence:** whole-document arbitrary Markdown, unknown sections, stale identities and a new normative rule without authority all fail without changing existing content.

## Additional first-pass tightening

AC-020 adds exclusion/unscoped-rule negative controls. AC-023 makes Markdown/backtick/fence/@-import data inert or rejected. AC-029 explicitly requires exact installed kind/schema/renderer closure and real hook/authority/child behavior without access to the development checkout. The governs set now includes the shared engine, helper, consumer and generation owners; it identifies applicability, not blanket permission to edit every matching file.

## What remains unresolved by a good specification

The exact exercise profile, real host read-only containment, native eager-load/action-admission seams, provider usage attribution and actual comparative benefit still need qualification. The current Windows package resource/native-engine checks are not those host trials. The per-kind JSON/Markdown work is real engine work, not a one-line registry change. The bounded legacy helper contracts must demonstrate preservation before refresh is enabled.

This self-review cannot approve itself or substitute for an independent policy-owned review. All 41 criterion verification records remain planned. The next step is independent semantic review and actual maintainer approval of this exact spec, then an implementation plan with a criterion-to-work/test map. No implementation starts merely because native structural/ready validation passes.
