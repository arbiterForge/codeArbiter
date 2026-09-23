---
name: brainstorming
description: The Socratic spec-refinement front of /feature, and the planning front of /sprint. Routed to BEFORE any code — it takes a one-line idea and drives it to an approved, concrete spec with testable acceptance criteria. Five gated phases — frame, shape, refine, write, review-and-approve. No implementation before an approved spec; the caller retains required planning, execution and delivery ordering. Each acceptance criterion becomes one tdd Phase 1 obligation.
disable-model-invocation: true
---

# brainstorming

## Structured-artifact boundary

For new full-lane work or an existing HTML spec/plan, load
`<plugin-root>/includes/artifacts.md` before artifact I/O. Before Phase 1, call
`_select_authoring_route` with the trusted project root, slug, invoking workflow,
and selected lane; use only its returned mode, format, and paths. For a selected
HTML route it checks the
installed capability before writing; missing or invalid HTML capability is a
STOP and the workflow must not fall back to Markdown. Its typed
ID, binding, readiness, receipt, contextual-read and scope-state rules replace
legacy Markdown parsing and direct status-cell edits for that pipeline. Keep all
other workflow gates, including human checkpoints, unchanged. Existing `.md`
artifacts remain on their legacy path. New full-lane specs use the installed
structured-artifact engine and default to canonical `.html`. HTML `--farm`
dispatch remains blocked.


Refine the idea before it touches code. Routed to by `/feature` and `/sprint` as their specification step.

## Caller scope and authority

Read the active caller's workflow, selected lane, scope and existing delegation before refining.
Initial sprint planning is not an approved sprint: this skill does not grant its own delegation.
A full-lane feature or sprint requires `writing-plans` after its spec is approved; a subordinate
specification step returns its result to the existing caller. Preserve direct handoffs when they
satisfy that caller's ordering, not an unconditional terminal route to implementation.

A sprint may contain several related features under one coherent goal. Keep their boundaries and
criteria explicit without converting the sprint into repeated feature interviews. Parameter and
method choices follow safety-core; material product decisions and missing authority are not inferred.
No new registered surface, runtime state or copied procedure is needed for this call contract.

## Pre-flight

Read these, or STOP and surface the gap — never guess scope or stack:

- `<project-root>/.codearbiter/CONTEXT.md` — the `stage:` frontmatter (the maturity value), domain vocabulary, and what the project is NOT building.
- `<project-root>/.codearbiter/tech-stack.md` — the stack the feature must fit; rule out incompatible designs early.
- `<project-root>/.codearbiter/open-questions.md` — existing `[CONFIRM-NN]` items; new ones number sequentially from here.

**Recorded intent — fail-soft, exempt from the read-or-STOP rule above (ADR-0025).** Also
consult, when present: the `decisions/` index (titles via `decision-log.md` or the filename
listing — load a full ADR body only when its subject touches this feature) and
`plans/02-phased-build-plan.md`'s section headings (plus `plans/01-architecture-breakdown.md`
when the feature touches component boundaries or integrations). Index-first, never a bulk read.
A missing file or directory here is NOT a gap to surface and never a STOP: record
`intent: silent — no decomposition record` in the running notes and proceed.

Scope-sized and light. NOT decompose's whole-project six-layer interview — five phases for the
caller's feature or coherent sprint. Depth scales with that scope, not the ceremony. The deliberately
inline small-feature lane remains owned by `/feature`; do not manufacture an HTML pair for it.

## Phase 1 — Frame the problem · gate: BLOCK

Take the one-line idea and pin its boundaries before designing or asking anything:

- State the problem in one sentence — the concrete pain, not the proposed solution.
- Name the user or caller who feels it, and what "done" looks like to them.
- Name what this feature explicitly does NOT do — the boundary that keeps scope honest.
- Check the framing against `CONTEXT.md`: it never contradicts the NOT-building list or redefines domain vocabulary. A contradiction is a conflict — surface it, do not reconcile it silently.
- Check the framing against the recorded intent (pre-flight, when present): an idea that resurrects a capability `plans/02` records as deferred, or that duplicates a backlog item, is a fork to ask — lead with the recorded deferral rationale and your recommendation; never proceed on it silently (ADR-0025).
- **Respect the caller's unit of work.** For a feature, split unrelated independently shippable
  concerns before refining them; record the selected piece and its exclusions. For a sprint, retain
  related features within the stated sprint goal and identify their separable criteria and dependencies
  for planning. Do not force one new user interview per feature or silently absorb unrelated work.
  Ask only when the intended scope or necessary product decision remains unresolved.

Gate: problem, caller, and out-of-scope boundary stated and consistent with `CONTEXT.md`; the unit is
the caller's selected feature or coherent sprint, with unrelated scope explicitly excluded.

## Phase 2 — Shape the approach · gate: BLOCK

Before drilling into details, establish WHICH design the details belong to:

- Propose the genuine candidate approaches — usually two or three — each with its real trade-off stated (`X gives you A but costs B`). Recommend exactly one, with the reasoning that picks it. The user rules on material product decisions during initial feature or sprint planning; within an already-approved sprint, its existing delegated decision rules apply and the choice is logged. A recommendation made before approval does not authorize execution.
- **Never manufacture alternatives.** When only one sane approach exists, say so and say why — a padded list of straw options is noise wearing the costume of rigor, and it trains the reader to skim the one section that matters.
- **Check each candidate against accepted ADRs** (the pre-flight index; ADR-0025). A contradicting candidate is surfaced WITH the ADR citation, never silently dropped — and it may not be recommended except paired with a supersession fork via `/adr`. When the contradicting candidate is the only sane approach, that IS the fork: present it (the user rules under `/feature`; under `/sprint` this surfaces at the interactive Phase 1 gate, where the user is present to rule).
- Apply the isolation lens to the recommended shape while it is still soft: can each part be understood without reading its internals, and can its internals change without breaking its consumers? A design that fails this here fails it again in review, after the code exists.
- Apply the YAGNI lens: strike anything the Phase 1 problem statement does not demand. A capability the caller never asked for is scope creep with a head start.

Gate: one approach selected under the caller's existing authority and recorded with its trade-off;
nothing in it exceeds the stated problem. Selection during initial planning is not execution authority.

## Phase 3 — Socratic refinement loop · gate: BLOCK

Turn the chosen approach concrete. The discipline is decide-or-ask, never drift:

- **Choose methods; ask missing decisions.** Select reversible parameters and implementation methods
  within safety-core's decision-authority limits; multiple reasonable methods alone do not require a
  user choice. Record material decisions in the running notes and the spec's **Decided parameters**.
  Use the existing delegated decision rules only where the approved sprint covers the choice. A
  missing product decision, unresolved `[CONFIRM-NN]`, scope expansion or irreversible operation is
  not a method choice: ask the actual question with its recommendation and counter-consideration.
- **Batch what is independent.** Forks whose answers do not depend on each other are asked together, not serialized into rounds. One round of three real questions beats three rounds of one.
- Run every answer through three lenses:
  - **Vague language** — make the required outcome observable: "fast", "secure" and "scalable"
    need acceptance boundaries. Only unresolved product requirements or missing user-owned decisions
    become `[CONFIRM-NN]`; a reversible implementation detail deliberately left to planning within
    the agreed constraints is not an unanswered user question. Do not invent unknowns to fill a template.
  - **Hidden complexity** — name what the user assumes is easy but is hard: state, concurrency, edge cases, failure modes, validation, idempotency, migration of existing data. Surface it now or it surfaces in `tdd`.
  - **Trade-off forcing** — identify the actual choice and its counter-consideration. Apply the caller's existing authority: ask material user-owned decisions, or choose and log an authorized delegated method. Never hide a choice or widen delegation.
- **The loop has a breaker.** When refinement stops converging, stop repeating the same question or
  hypothesis. Reuse an applicable recorded ruling; within delegation, diagnose and choose a different
  evidence-supported method. A genuine unresolved user decision or rule conflict is surfaced once
  through its owner, never guessed or treated as permission. Do not manufacture `[CONFIRM-NN]` for
  the agent's internal choice of method.
- **Closure is a checklist, not a feeling.** The reasons to stop asking that do not count, each with why:
  - *"The feature is simple enough."* — Simplicity shortens the spec; it does not waive it. The five-sentence spec still names its criteria.
  - *"I've asked enough questions."* — Question fatigue is not an exit condition. The exit is the Phase 5 review passing.
  - *"The user seems eager to move on."* — Eagerness is a signal to compress the asking (decide more parameters, batch harder), never to skip an unresolved fork.
  - *"We can settle it during implementation."* — Missing acceptance requirements cannot be deferred
    as implementation freedom. Record genuine user-owned unknowns; retain method selection within
    the existing planning and delegated-execution contract.

Record every genuinely-unresolved user-owned requirement or decision as `[CONFIRM-NN]` in `<project-root>/.codearbiter/open-questions.md`, numbered sequentially. A finding that belongs to a different feature or a future scope gets an inline `[NEEDS-TRIAGE]` marker in the notes — never route it to a ticket.

**Before closing this loop, check the criteria decided so far against their own stated intent, not merely against each other** (#566: `writing-plans` Phase 4 proves BIJECTION between a plan's tasks and the `AC-NN` ledger — every criterion has a task, every task has a criterion — and that proves the two AGREE, never that the ledger itself is COMPLETE. A criterion missed by both sides passes that check cleanly; catching the miss belongs here, at the source, before Phase 4 writes anything to freeze it in place.) Assemble a scratch file outside the working tree (`mktemp`) shaped like the spec sections Phase 4 is about to write — a `## Scope` heading over the Phase 1 framing, and an `## Acceptance criteria` heading over every criterion decided in this phase's running notes so far — and, when this feature traces to a GitHub issue, its body into a second scratch file (`gh issue view <N> --json body -q .body > <scratch-file>`; omitted when there is no linked issue). Run `"$PY" "<plugin-root>/hooks/_intentlib.py" uncovered-intent <scope-and-criteria-file> [--issue-body <scratch-file>]`. A non-empty result names an in-scope bullet or an issue acceptance checkbox no criterion's text cites — add the missing criterion now, or record it as a `[CONFIRM-NN]` if it is genuinely undecided, never carry it forward uncited. This mechanical pass is the CHEAP half; it catches only an uncited bullet or checkbox.

Then ask the half it cannot mechanize, explicitly, as its own step: **if every criterion decided so far passed and nothing else changed, what would still be broken?** A real answer names a criterion the ledger is still missing even though every scope bullet and checkbox is technically cited — a bullet reading "fix all three contaminated skills" against criteria for two of the three passes the citation check above cleanly, and only this question catches it. Finding nothing broken is a reportable result, stated in one line, never a silent skip.

Gate: every vague term made concrete; every material choice resolved under the caller's authority or recorded as a genuine `[CONFIRM-NN]`; every parameter decision recorded in the running notes that seed Phase 4's **Decided parameters** section; no unresolved user-owned acceptance requirement outside a `[CONFIRM-NN]`; the `uncovered_intent` backstop returns empty or every finding is resolved; and the negative question above has been asked and answered, not merely named. A blocking `[CONFIRM-NN]` that gates the spec's core stops the loop — surface it and STOP.

## Phase 4 — Write the spec · gate: BLOCK

Create or revise the agreed spec at the route-selected spec path, in its selected format.
New full-lane work uses `<project-root>/.codearbiter/specs/<slug>.html` through the installed
structured-artifact engine; do not write HTML or its embedded model directly. An existing `.md`
spec stays on its exact legacy path; never create a counterpart or implicitly convert it.
The spec holds:

- **Problem** — the Phase 1 framing in final form.
- **Approach** — the Phase 2 choice and the trade-off that picked it, in two or three sentences.
- **Scope** — what is in, and the explicit out-of-scope boundary.
- **Decided parameters** — the parameter-level choices made in Phase 3, each in one line, so the approval reads them instead of discovering them in code review.
- **Acceptance criteria** — a numbered list, each criterion concrete and testable: a specific input, the observable output, the boundary or failure behavior. Each criterion is verifiable by one or more focused tests. "It works well" is not a criterion. These become `tdd` Phase 1 obligations — one obligation per criterion, so an untestable criterion is a defect to fix here, not in `tdd`.
- **Open questions** — every `[CONFIRM-NN]` raised, cross-referenced to `open-questions.md`.
- **Governs** *(optional)* — a spec-header line `**Governs:** <comma-separated globs>` that enrolls the approved spec in file-scoped just-in-time context injection: on a Read of any file matching one of the listed globs, a pointer to this spec is surfaced to the agent (tier 3 of the file→knowledge map). Adding the line is sufficient to enroll; no other change required.

Gate: the spec file exists on disk under `specs/`, with at least one acceptance criterion and every criterion individually testable.

## Phase 5 — Review, approval & handoff · gate: STOP

The spec earns its approval; it is not waved through. Two passes over the FILE as written, then the stop:

1. **Mechanical self-review** — one pass, correct through the selected format's owning writer, no re-review: no placeholder text (`TBD`, `???`, an unfilled section); no criterion that contradicts the scope; nothing that crosses the `CONTEXT.md` NOT-building boundary; no criterion that contradicts an accepted ADR or `plans/01`'s recorded component boundaries (ADR-0025); every criterion still testable by one or more focused tests after the edits; the vague-language lens applied to the spec's own prose.
2. **Adversarial pass** — build the strongest case AGAINST the design before the user reads it: the failure mode most likely to be real, the criterion most likely to be wrong, the assumption that would invalidate the approach if false. Present what survives WITH the spec at approval — the user rules on a challenged design, not a defended one. Finding nothing is a reportable result, stated in one line, not a silent skip.
3. **Approval:**
   - **Under `/feature`** — present the spec and the adversarial findings, and request explicit user approval. Iterate on the file in place until the user approves. A blocking `[CONFIRM-NN]` must be resolved by the user before approval — never auto-resolve it.
   - **Initial `/sprint` planning** — present the spec and adversarial findings for explicit user
     approval within the caller's initial planning gate. For HTML, use the existing adapter in
     `<plugin-root>/includes/artifacts.md`: arm the exact current spec, require the exact returned reply,
     then verify its `approved` gate before planning. The plan is bound to that approved spec and armed
     separately; one generic reply does not approve both. Spec approval permits the required plan
     authoring; autonomy begins only after the caller's spec AND plan approval requirement is met.
   - **Within an already-approved sprint** — use its existing delegation only for an in-scope choice.
     For HTML, a supported policy-owned adapter must supply the actual event and engine receipt;
     follow `<plugin-root>/includes/artifacts.md`. A SMARTS score or log entry is not an approval receipt.
     Use only a qualified production producer for the requested authority and host; do not invent a capture event
     or reuse inspection-only evidence. A missing producer is not delegation: retain the pending state and use
     only the existing supported authority path. The native engine's presence does not qualify a host adapter.
     Blocking `[CONFIRM-NN]` decisions are never auto-approved in either phase.

**Continuation follows the caller.** For a full-lane feature or sprint, return the approved spec identity
and review outcome to its planning step, or forward directly to
`writing-plans` (`<plugin-root>/routines/writing-plans/SKILL.md`) when that is the caller's declared
next step. Do not skip required plan creation, binding or approval by jumping to `tdd`. A subordinate
invocation returns to the named checkpoint in its caller instead of launching another full workflow.
The inline small feature route belongs to `/feature` and can reach `tdd` without invoking this full-lane
specification procedure. Neither path grants commit, PR, merge or publication authority.

Gate: both review passes completed against the authoritative file, adversarial findings presented,
and actual approval verified with no unresolved blocking `[CONFIRM-NN]`. The next operation obeys
the active caller's sequence and authority.

## Hard rules

- MUST NOT write implementation code or route to `tdd` before the spec is on disk under `specs/` AND approved.
- MUST preserve the caller's feature or coherent sprint boundary; unrelated scope is split or excluded, not silently absorbed.
- MUST NOT manufacture alternatives in Phase 2 — when one sane approach exists, say so and why.
- MUST NOT write an acceptance criterion that cannot be verified by one or more focused tests.
- MUST record material parameter choices; ask genuine missing user decisions in full, not internal method-selection questions already covered by delegation.
- MUST stop a non-converging refinement strategy; reuse recorded rulings or authorized diagnosis rather than repeat an answered question. Genuine conflicts still route to their owner.
- MUST run the `uncovered_intent` mechanical backstop and ask the negative-judgment question ("if every criterion passed and nothing else changed, what would still be broken?") before closing Phase 3 — bijective coverage in `writing-plans` proves the plan and the ledger agree with each other, never that the ledger is complete (#566).
- MUST run the Phase 5 mechanical self-review and adversarial pass against the file as written, and present the adversarial findings at approval.
- MUST NOT resolve a `[CONFIRM-NN]` by guessing — surface it and record it in `open-questions.md`.
- MUST NOT auto-approve a spec carrying a blocking `[CONFIRM-NN]`, even under `/sprint` — it escalates to the user.
- MUST NOT contradict the NOT-building list or redefine domain vocabulary in `CONTEXT.md` — a contradiction is a conflict to surface, not reconcile.
- MUST NOT run decompose's six-layer whole-project interview or force a coherent sprint through repeated one-feature interviews.
- MUST NOT use SMARTS to approve the initial sprint; record delegated decisions in the existing audit trail and verify actual authority for the selected artifact format.
- MUST, at exit, run the follow-up harvest (`<plugin-root>/includes/harvest.md`) in the active caller's mode:
  batch-confirm interactive work; use autonomous promotion only under existing delegation. A blocking
  decision is never promoted into authority or silently demoted to a follow-up.
