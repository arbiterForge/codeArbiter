---
name: brainstorming
description: The Socratic spec-refinement front of /feature, and the planning front of /sprint. Routed to BEFORE any code — it takes a one-line idea and drives it to an approved, concrete spec with testable acceptance criteria. Five gated phases — frame, shape, refine, write, review-and-approve. No implementation and no handoff to tdd until the spec is on disk and approved; each acceptance criterion becomes one tdd Phase 1 obligation.
disable-model-invocation: true
---

# brainstorming

Refine the idea before it touches code. Routed to by `/feature` (before `tdd`) and by `/sprint` (the planning front).

## Pre-flight

Read these, or STOP and surface the gap — never guess scope or stack:

- `${CLAUDE_PROJECT_DIR}/.codearbiter/CONTEXT.md` — the `stage:` frontmatter (the maturity value), domain vocabulary, and what the project is NOT building.
- `${CLAUDE_PROJECT_DIR}/.codearbiter/tech-stack.md` — the stack the feature must fit; rule out incompatible designs early.
- `${CLAUDE_PROJECT_DIR}/.codearbiter/open-questions.md` — existing `[CONFIRM-NN]` items; new ones number sequentially from here.

**Recorded intent — fail-soft, exempt from the read-or-STOP rule above (ADR-0025).** Also
consult, when present: the `decisions/` index (titles via `decision-log.md` or the filename
listing — load a full ADR body only when its subject touches this feature) and
`plans/02-phased-build-plan.md`'s section headings (plus `plans/01-architecture-breakdown.md`
when the feature touches component boundaries or integrations). Index-first, never a bulk read.
A missing file or directory here is NOT a gap to surface and never a STOP: record
`intent: silent — no decomposition record` in the running notes and proceed.

Per-feature and light. NOT decompose's whole-project six-layer interview — one feature, five phases. Depth scales with the feature, not the ceremony: a small feature earns a short pass through every phase, never a skipped one. A spec can be five sentences; it cannot be zero — smallness changes the spec's length, not its existence.

## Phase 1 — Frame the problem · gate: BLOCK

Take the one-line idea and pin its boundaries before designing or asking anything:

- State the problem in one sentence — the concrete pain, not the proposed solution.
- Name the user or caller who feels it, and what "done" looks like to them.
- Name what this feature explicitly does NOT do — the boundary that keeps scope honest.
- Check the framing against `CONTEXT.md`: it never contradicts the NOT-building list or redefines domain vocabulary. A contradiction is a conflict — surface it, do not reconcile it silently.
- Check the framing against the recorded intent (pre-flight, when present): an idea that resurrects a capability `plans/02` records as deferred, or that duplicates a backlog item, is a fork to ask — lead with the recorded deferral rationale and your recommendation; never proceed on it silently (ADR-0025).
- **Split before you spend.** If the idea bundles more than one independently shippable concern — distinct callers, acceptance criteria that would partition into disjoint sets, separable data or surfaces — say so NOW and negotiate the split with the user before any refinement effort is spent on one piece. Each surviving piece is its own spec and its own run of this skill. A bundle discovered in Phase 4 has already wasted every question asked about the piece that gets cut.

Gate: problem, caller, and out-of-scope boundary stated and consistent with `CONTEXT.md`, and the idea is confirmed to be ONE feature — or the split is agreed and this run proceeds on exactly one piece.

## Phase 2 — Shape the approach · gate: BLOCK

Before drilling into details, establish WHICH design the details belong to:

- Propose the genuine candidate approaches — usually two or three — each with its real trade-off stated (`X gives you A but costs B`). Recommend exactly one, with the reasoning that picks it. The user chooses under `/feature`; under `/sprint`, SMARTS chooses and the choice is logged with its scoring.
- **Never manufacture alternatives.** When only one sane approach exists, say so and say why — a padded list of straw options is noise wearing the costume of rigor, and it trains the reader to skim the one section that matters.
- **Check each candidate against accepted ADRs** (the pre-flight index; ADR-0025). A contradicting candidate is surfaced WITH the ADR citation, never silently dropped — and it may not be recommended except paired with a supersession fork via `/adr`. When the contradicting candidate is the only sane approach, that IS the fork: present it (the user rules under `/feature`; under `/sprint` this surfaces at the interactive Phase 1 gate, where the user is present to rule).
- Apply the isolation lens to the recommended shape while it is still soft: can each part be understood without reading its internals, and can its internals change without breaking its consumers? A design that fails this here fails it again in review, after the code exists.
- Apply the YAGNI lens: strike anything the Phase 1 problem statement does not demand. A capability the caller never asked for is scope creep with a head start.

Gate: one approach chosen (user-chosen, or SMARTS-chosen and logged), its trade-off stated, and nothing in it the problem does not require.

## Phase 3 — Socratic refinement loop · gate: BLOCK

Turn the chosen approach concrete. The discipline is decide-or-ask, never drift:

- **Decide the parameters; ask the forks.** A parameter-level choice — a naming, a default, a threshold, an ordering with one sensible answer — is yours to make: decide it and record it in this phase's running notes; every recorded decision lands in the spec's **Decided parameters** section when Phase 4 writes the file, which is where the user reads them at approval. A genuine fork — a real trade-off, a scope boundary, anything irreversible or user-visible — is the user's: ask it IN FULL the first time, leading with your recommendation and its reasoning. Never merely mention that an open decision exists; a named-but-unasked question is an omission wearing a disclaimer.
- **Batch what is independent.** Forks whose answers do not depend on each other are asked together, not serialized into rounds. One round of three real questions beats three rounds of one.
- Run every answer through three lenses:
  - **Vague language** — force concrete nouns, numbers, and verbs. "Manage", "handle", "support" are not verbs. "Fast", "secure", "scalable" are not specifications. "We'll figure it out later" is not an answer — every "later" becomes a `[CONFIRM-NN]`.
  - **Hidden complexity** — name what the user assumes is easy but is hard: state, concurrency, edge cases, failure modes, validation, idempotency, migration of existing data. Surface it now or it surfaces in `tdd`.
  - **Trade-off forcing** — when a real decision exists, frame it with a recommendation and let the user rule. Do not pick for the user; do not hide that a pick exists.
- **The loop has a breaker.** When refinement stops converging — an answer contradicts an earlier one, or the same fork resurfaces after being answered — STOP the loop: restate the contradiction plainly, force one adjudication (a user ruling, or a recorded `[CONFIRM-NN]`), and only then continue. A loop that circles is not being thorough; it is failing to close.
- **Closure is a checklist, not a feeling.** The reasons to stop asking that do not count, each with why:
  - *"The feature is simple enough."* — Simplicity shortens the spec; it does not waive it. The five-sentence spec still names its criteria.
  - *"I've asked enough questions."* — Question fatigue is not an exit condition. The exit is the Phase 5 review passing.
  - *"The user seems eager to move on."* — Eagerness is a signal to compress the asking (decide more parameters, batch harder), never to skip an unresolved fork.
  - *"We can settle it during implementation."* — Every deferral is a `[CONFIRM-NN]` on record, or it is a guess that `tdd` will faithfully implement.

Record every genuinely-unresolved unknown as `[CONFIRM-NN]` in `${CLAUDE_PROJECT_DIR}/.codearbiter/open-questions.md`, numbered sequentially. A finding that belongs to a different feature or a future scope gets an inline `[NEEDS-TRIAGE]` marker in the notes — never route it to a ticket.

**Before closing this loop, check the criteria decided so far against their own stated intent, not merely against each other** (#566: `writing-plans` Phase 4 proves BIJECTION between a plan's tasks and the `AC-NN` ledger — every criterion has a task, every task has a criterion — and that proves the two AGREE, never that the ledger itself is COMPLETE. A criterion missed by both sides passes that check cleanly; catching the miss belongs here, at the source, before Phase 4 writes anything to freeze it in place.) Assemble a scratch file outside the working tree (`mktemp`) shaped like the spec sections Phase 4 is about to write — a `## Scope` heading over the Phase 1 framing, and an `## Acceptance criteria` heading over every criterion decided in this phase's running notes so far — and, when this feature traces to a GitHub issue, its body into a second scratch file (`gh issue view <N> --json body -q .body > <scratch-file>`; omitted when there is no linked issue). Run `"$PY" "${CLAUDE_PLUGIN_ROOT}/hooks/_intentlib.py" uncovered-intent <scope-and-criteria-file> [--issue-body <scratch-file>]`. A non-empty result names an in-scope bullet or an issue acceptance checkbox no criterion's text cites — add the missing criterion now, or record it as a `[CONFIRM-NN]` if it is genuinely undecided, never carry it forward uncited. This mechanical pass is the CHEAP half; it catches only an uncited bullet or checkbox.

Then ask the half it cannot mechanize, explicitly, as its own step: **if every criterion decided so far passed and nothing else changed, what would still be broken?** A real answer names a criterion the ledger is still missing even though every scope bullet and checkbox is technically cited — a bullet reading "fix all three contaminated skills" against criteria for two of the three passes the citation check above cleanly, and only this question catches it. Finding nothing broken is a reportable result, stated in one line, never a silent skip.

Gate: every vague term made concrete; every fork resolved by the user or recorded as `[CONFIRM-NN]`; every parameter decision recorded in the running notes that seed Phase 4's **Decided parameters** section; no unresolved "later" outside a `[CONFIRM-NN]`; the `uncovered_intent` backstop returns empty or every finding is resolved; and the negative question above has been asked and answered, not merely named. A blocking `[CONFIRM-NN]` that gates the spec's core stops the loop — surface it and STOP.

## Phase 4 — Write the spec · gate: BLOCK

Write the agreed spec to `${CLAUDE_PROJECT_DIR}/.codearbiter/specs/<slug>.md`. The slug is derived from the feature. The spec holds:

- **Problem** — the Phase 1 framing in final form.
- **Approach** — the Phase 2 choice and the trade-off that picked it, in two or three sentences.
- **Scope** — what is in, and the explicit out-of-scope boundary.
- **Decided parameters** — the parameter-level choices made in Phase 3, each in one line, so the approval reads them instead of discovering them in code review.
- **Acceptance criteria** — a numbered list, each criterion concrete and testable: a specific input, the observable output, the boundary or failure behavior. Each criterion is verifiable by a single test. "It works well" is not a criterion. These become `tdd` Phase 1 obligations — one obligation per criterion, so an untestable criterion is a defect to fix here, not in `tdd`.
- **Open questions** — every `[CONFIRM-NN]` raised, cross-referenced to `open-questions.md`.
- **Governs** *(optional)* — a spec-header line `**Governs:** <comma-separated globs>` that enrolls the approved spec in file-scoped just-in-time context injection: on a Read of any file matching one of the listed globs, a pointer to this spec is surfaced to the agent (tier 3 of the file→knowledge map). Adding the line is sufficient to enroll; no other change required.

Gate: the spec file exists on disk under `specs/`, with at least one acceptance criterion and every criterion individually testable.

## Phase 5 — Review, approval & handoff · gate: STOP

The spec earns its approval; it is not waved through. Two passes over the FILE as written, then the stop:

1. **Mechanical self-review** — one pass, fix inline, no re-review: no placeholder text (`TBD`, `???`, an unfilled section); no criterion that contradicts the scope; nothing that crosses the `CONTEXT.md` NOT-building boundary; no criterion that contradicts an accepted ADR or `plans/01`'s recorded component boundaries (ADR-0025); every criterion still testable by a single test after the edits; the vague-language lens applied to the spec's own prose.
2. **Adversarial pass** — build the strongest case AGAINST the design before the user reads it: the failure mode most likely to be real, the criterion most likely to be wrong, the assumption that would invalidate the approach if false. Present what survives WITH the spec at approval — the user rules on a challenged design, not a defended one. Finding nothing is a reportable result, stated in one line, not a silent skip.
3. **Approval:**
   - **Under `/feature`** — present the spec and the adversarial findings, and request explicit user approval. Iterate on the file in place until the user approves. A blocking `[CONFIRM-NN]` must be resolved by the user before approval — never auto-resolve it.
   - **Under `/sprint`** — approval may be granted automatically by SMARTS scoring, logged to the `.codearbiter/` audit trail. A blocking `[CONFIRM-NN]` is never auto-approvable; it escalates to the user and STOPs the sprint flow.

On approval, hand off to the `tdd` skill, which enters Phase 1 against the approved spec — one obligation per acceptance criterion.

Gate: both review passes run against the file on disk, adversarial findings presented, and the spec approved (by the user under `/feature`, or by logged SMARTS auto-approval under `/sprint`) with no unresolved blocking `[CONFIRM-NN]`. Only then does control pass to `tdd`.

## Hard rules

- MUST NOT write implementation code or route to `tdd` before the spec is on disk under `specs/` AND approved.
- MUST NOT refine a bundle — an idea holding more than one independently shippable concern splits in Phase 1, before any question budget is spent.
- MUST NOT manufacture alternatives in Phase 2 — when one sane approach exists, say so and why.
- MUST NOT write an acceptance criterion that cannot be verified by a single test.
- MUST decide parameter-level choices and record them in the spec; MUST ask genuine forks in full, with a recommendation, the first time — never name an open decision without asking it.
- MUST stop a non-converging refinement loop and force one adjudication — a contradiction or a resurfacing fork is a breaker, not a prompt to circle.
- MUST run the `uncovered_intent` mechanical backstop and ask the negative-judgment question ("if every criterion passed and nothing else changed, what would still be broken?") before closing Phase 3 — bijective coverage in `writing-plans` proves the plan and the ledger agree with each other, never that the ledger is complete (#566).
- MUST run the Phase 5 mechanical self-review and adversarial pass against the file as written, and present the adversarial findings at approval.
- MUST NOT resolve a `[CONFIRM-NN]` by guessing — surface it and record it in `open-questions.md`.
- MUST NOT auto-approve a spec carrying a blocking `[CONFIRM-NN]`, even under `/sprint` — it escalates to the user.
- MUST NOT contradict the NOT-building list or redefine domain vocabulary in `CONTEXT.md` — a contradiction is a conflict to surface, not reconcile.
- MUST NOT run decompose's six-layer whole-project interview — this is one feature, five phases.
- MUST log a `/sprint` auto-approval to the `.codearbiter/` audit trail.
- MUST, at exit, run the follow-up harvest (`${CLAUDE_PLUGIN_ROOT}/includes/harvest.md`) over any `[NEEDS-TRIAGE]` notes raised this run — batch-confirm promoting them to `open-tasks.md` (work) or `open-questions.md` (decisions) so out-of-scope ideas don't vanish.
