# Concepts overhaul: approved execution plan

## Approval and authority

- Approved by the product owner in the work-session conversation on 2026-09-24: "You just laid out the plan; approved; lock it in so it doesn't get lost and get started on the first PR".
- Authorized repository: `arbiterForge/codeArbiter`.
- Discovery baseline: `29f84168ab7592a5d7bb0550cb1f25cf29608a9d`, current main after merged PR #851.
- This file is the durable program plan. Tracking issue [#856](https://github.com/arbiterForge/codeArbiter/issues/856) and implementation PR [#857](https://github.com/arbiterForge/codeArbiter/pull/857) link here rather than maintaining independent specifications.
- Approval authorizes implementation and review PRs. It does not authorize merging, deployment, releases, changed runtime controls, invented host evidence, or organization-wide branding.
- This record is not a native artifact-engine approval, an accepted ADR, or an execution/verification receipt.

## Outcome

Make Concepts the explanatory front door into how codeArbiter composes work: entry, routing, durable artifacts, decisions, authorship, independent review, verification, commit and PR. Readers must understand why the pieces exist, how they relate, what they produce, and what their evidence does and does not establish. More words or more cards alone are not acceptance criteria.

Restore the lost execution-order meaning of the historical three-row diagrams. Commands, skills and agents are different kinds of participants, not three consecutive phases. A connector must follow the actual route between those rows. Reusable visuals should teach a complete path and its conditions rather than display categorized inventories.

Historical comparison, not current runtime authority:
`arbiterForge/codeArbiter@24439db4618d55fad289fe94f7303dcb3211cd3c:site/public/diagrams/lane-feature.svg`.

Current implementation and owning canonical contracts must be read at each PR baseline. Never restore old ordering solely because it existed in an old image. A current source map is not an exact installed-release certification.

## Approved scope

1. Rebuild the Concepts landing page around a coherent operating model and one worked change. Group discovery by work routing, decisions/authority, repository context, review/verification and durable evidence.
2. Redesign execution diagrams with commands, skills and agents as distinct rows. Show actual ordered handoffs, nested work, meaningful return/retry paths, conditional dispatch, human decisions and terminal outcomes. Preserve a readable narrow-screen alternative.
3. Deepen core concepts: gated lanes, project/change artifacts, SMARTS, ADRs, auditability, provenance/drift and just-in-time context. Include role separation and checkpoints where needed for the connected model.
4. Make project-level Markdown, the three decompose outputs, full-lane typed HTML, retained legacy pairs and inline small-lane work explicitly distinct. Representation, integrity, approval, implementation, verification and delivery are separate claims.
5. Connect Concepts to Guides and exact Reference entries, including feature, fix/TDD, sprint, decompose, artifact review, decisions and delivery. Edit curated/generator owners, never generated reference pages directly.
6. Preserve the site voice, tokens, product-specific exceptions, guide quality, responsive fixes, public addresses, compatibility routes and Academy contracts.

## Delivery sequence

### C01: orientation and execution-map foundation (first PR)

Status: MERGED. Implementation PR: [#857](https://github.com/arbiterForge/codeArbiter/pull/857).
Merge commit: `6860daa3c974ae32cd9584d3e60e0a51c185a613`, verified on 2026-09-24. The owner
merged C01; its earlier PR description's pending state is historical, not the current status.
Broader cross-browser, assistive-technology and reader-task validation remain separately scoped.

- Revalidate live main and the historical execution-map design.
- Rebuild the Concepts landing/navigation around connected questions.
- Deepen gated lanes and the project/change artifact model.
- Establish one source-bound, reusable execution-map implementation for the feature and test-first path through commit/PR, with explicit simplification and branch boundaries.
- Reuse that map where it replaces a misleading feature/TDD inventory, without claiming every other diagram is already converted.
- Cover source identities, map structure, mobile reading, semantics, no-script behavior, links and actual browser captures.

C01 is an independently reviewable foundation, not completion of C02-C04.

### C02: decisions, autonomy and retained evidence

Status: IN_PROGRESS. Implementation PR: [#859](https://github.com/arbiterForge/codeArbiter/pull/859).
Depends on merged C01. Branch: `docs/concepts-decisions-evidence`.
Current baseline: `6860daa3c974ae32cd9584d3e60e0a51c185a613`. C02 source tracing and known
contract discrepancies are recorded in `site/reviews/CONCEPTS-C02-SOURCES.md`. Implementation,
verification, owner review and merge remain distinct; the tracking issue receives the PR link.

- Deepen SMARTS, ADRs, checkpoints and auditability using concrete examples and inspection tasks.
- Trace sprint and reconcile separately. A recommendation is not user approval; an accepted decision is not implemented or verified work; a periodic checkpoint is not a task-acceptance receipt.
- Reconcile affected derivative explanations only against current owning implementation. Keep runtime contradictions separately recorded when this documentation work cannot resolve them.

### C03: repository knowledge and role separation

Status: NOT_STARTED. Depends on C01.

- Deepen provenance/drift, just-in-time context and persona/author/reviewer separation.
- Explain source freshness, governing-file selection, on-demand loading, context budgets, failure behavior and real inspection examples.
- Classify research and hardening-history claims as historical where appropriate. Preserve original attribution; reverify any retained numerical or current efficacy claim before promoting it.

### C04: diagram propagation and final cross-surface review

Status: NOT_STARTED. Depends on C01-C03.

- Apply the validated visual language to sprint, dependency, ADR, release and initialization diagrams, with each route traced independently.
- Restore semantic coverage, not blindly identical PR endings: initialization can end in populated context, a read-only review in a verdict, and a spike in findings. Only actual delivery paths should end in commit/PR.
- Verify Concepts, Guides and curated command/skill pages agree; retain direct image URLs or deliberate redirects where public assets change.
- Complete final accessibility, visual, browser, search and reader-task review. Record limits rather than declaring universal certification.

## Diagram contract

- A node has one documented role and an owning source. An edge has a meaning: sequence, dispatch/return, conditional continuation or repeat. A source reference validates a claimed relationship; shared membership does not imply a direct call.
- Display commands in the appropriate host spelling or clearly identify the illustrated convention. Do not imply every label is something the user must type.
- Keep work coordination separate from its author and reviewer calls. Tests occur inside the owning implementation cycle, not after a falsely complete authoring stage.
- Show the output and decision at important boundaries. A graphic control does not grant approval, mutate repository state or record completion.
- Show ordinary success plus important alternate exits and stops. Do not route every command to a PR merely to finish a picture.
- Provide an equivalent ordered HTML reading path from the same map data. Desktop rows and mobile steps must retain identical content and relationships.
- Use labelled links and visible focus, sensible text sizes, content-sized nodes, non-overlapping connectors, reduced-motion and forced-color treatment. No required autoplay, external assets or fabricated live activity.
- Preserve detailed source/reference access without making the visitor read raw implementation to understand the basic route.

## Acceptance criteria

AC01: The reader can explain commands versus skills versus agents and trace a specific change to its actual endpoint without guessing the order from three buckets.
AC02: The reader can name the three decompose documents, distinguish project scope from change scope, and find the appropriate owning guide.
AC03: The reader can distinguish readable HTML, current typed identity, approval authority, verification, task acceptance and PR delivery.
AC04: The feature/TDD map includes its execution coordinator, task-level implementation/review, commit gate and PR boundary with honest conditional/host limitations.
AC05: Retained public links and generated references resolve under both the apex deployment and `/docs/` base.
AC06: Diagram labels and explanatory content remain readable at 320, 390, 768, 1024 and 1440 pixels, with keyboard, no JavaScript, enlarged text, reduced motion, forced colors and print checks as applicable.
AC07: Tests reject missing owners, broken links, duplicate identities, invalid connections and missing terminal boundaries. They do not pretend source excerpts prove live host execution.
AC08: Actual desktop/mobile captures are inspected after the exact candidate build; no clipped text, shrinking-to-fit illegibility or first-card spacing regression is accepted.
AC09: Scope state, remaining slices, exact source/test identities, open contradictions and rollback are recorded in each PR.

## Verification and propagation

Trace canonical source first, update map data and explanatory prose second, generate derivative assets/reference third, then run targeted tests, the site unit/type/voice checks, build, link audit, non-root checks and hosted browser tests. Retain exact-candidate screenshots and geometry. Repository merge readiness remains a separate exact-head requirement. Impact-skipped jobs are not executed tests.

Do not introduce a runtime orchestration DSL or new public command to support documentation. Structure only the documented diagram relationships and stable content metadata needed for coherent presentation and tests. Use existing build/dependency and artifact-consumer accounting rather than changing qualification states.

## Non-goals and safeguards

No runtime, approval/gate weakening, host maturity promotion, release/tag manipulation, policy interpretation, Academy curriculum/verifier modification, repository reset, forced branch update, or downstream material. The old decompose complaint was addressed in earlier guide work; verify the current surface before calling it unresolved. Word counts are diagnostic, not a reason to pad pages.

## Rollback and continuation

Revert a slice with its map data, renderer, generator changes, asset outputs, consumers and tests as one coherent unit. Preserve public routes and previous guide/mobile improvements. Do not revert valid publication receipts or independent runtime work to roll back a website.

Before the next slice: read this plan, inspect the merged PR and fresh main, revalidate the owning contracts, and update only the relevant slice state with evidence. Do not reconstruct the program from conversation memory or silently expand its approval.
