# Spec: Academy front door

**Status:** APPROVED 2026-08-26 by brennonhuff@gmail.com after independent hostile review
**Lane:** `/ca:feature`
**Slug:** `academy-front-door`
**Governs:** `site/scripts/academy-source.ts`, `site/scripts/generate-academy.ts`, `site/src/components/`, `site/src/styles/academy.css`, and their tests

## Problem

`/academy/` is technically accurate but fails as the entrance to a hands-on learning product.
The live page opens with a sparse title and abstract outcome card, then presents all 19 lessons as
one dense list. A first-time reader cannot quickly tell why to start, what the practice feels like,
or which lesson to take first. The page behaves as a reference index despite being the Academy's
main invitation.

## Decision

Keep Academy inside the Astro/Starlight CodeArbiter documentation shell. Do not create a separate
marketing application or duplicate the curriculum into hand-maintained landing-page content.

Replace the generated index's syllabus-first composition with a generated Academy front-door
component. It consumes the pinned Academy lesson metadata plus the authoritative Academy Home
setup material. Lesson title, track, order, time, and outcome remain source-backed; the invitation
copy and track introductions are explicitly reviewed editorial copy. The page must test the
source-backed fields it renders rather than claim that every sentence is source-derived.

## Reader outcome

A first-time visitor understands that Academy is safe, self-paced practice in their own fork;
can complete the required Home setup before beginning the first Foundation lesson; and can see the route from foundations through
practitioner and power-user work without needing to parse every lesson description. A returning
learner can still find any published lesson from the normal Academy rail or its matching track.

## Experience

### Entrance

1. A concise hero states the practical promise: learn CodeArbiter by doing bounded, verifiable
   work in a safe practice fork.
2. Exactly one visually primary call to action leads to the authoritative Home setup section, not
   directly to F01. A secondary in-page link leads to the curriculum overview.
3. A compact orientation strip makes the commitment legible: 19 hands-on lessons, three
   progressive tracks, self-paced pacing, and learner-owned proof.

### Required setup and first action

The Home setup appears immediately after the orientation and uses the authoritative five-step
readiness flow from the pinned Academy source. It owns the stable
`complete-these-five-setup-steps-before-f01` anchor expected by F01's source backlink. The setup
section clearly links to F01 only after the reader sees its prerequisites.
It also retains a tested `#setup` compatibility alias while any pinned Academy guide still links to it.

F01 then appears as the visually dominant first-lesson card. It shows title, outcome, estimated
time, and a clear start action. It must not pretend the exercise is a sandbox: the copy accurately
says the learner works in their own fork. The hero has the sole visually primary action; the F01
card and the Foundation inventory may link to F01 as ordinary secondary entry links.

### Curriculum

Three generated track sections follow: Foundation, Practitioner, and Power user. Each begins with
a capability-oriented explanation, identifies its lesson count and combined estimated time, and
shows a small, legible set of lesson cards. The first card in each track is always visible; the
remaining lessons are progressively disclosed with a native `<details>` control when needed.

Every lesson card links to the existing generated lesson URL and exposes title, outcome, and time.
F01 may appear in the start card and Foundation inventory, but has one canonical curriculum record.
Each disclosure names the number of additional lessons it reveals, and the page provides track
anchors plus a visible `View all lessons` route for returning learners.
The landing must not manufacture completion state, sign-in state, badges, or progress tracking.

### How practice works

One compact three-step section explains the actual learning loop: fork safely, follow a bounded
scenario, and keep evidence of the outcome. This reinforces the product's proof-first language
without competing with the start action.

### Responsive and accessible behavior

- Preserve the existing CodeArbiter docs navigation rail, headings, search, and dark design tokens.
- The Academy overview component owns its only H1. `PageTitle.astro` must suppress the stock title
  and page-context card for the `academy` route so the intended hero is first in content order.
- Use semantic links, headings, lists, and native `<details>` rather than client-side disclosure.
- The primary action, cards, and disclosure control must remain keyboard reachable in visual order,
  have visible AA-contrast focus states, and provide at least 44 by 44 CSS-pixel hit targets.
- Collapse multi-column layouts to one column without horizontal overflow at 390px; verify the
  desktop composition at 1440px. Disclosure summaries must have descriptive text and expose their
  native expanded/collapsed state to assistive technology.
- Respect reduced-motion preferences; no motion is required for comprehension.

## Architecture

1. Extend `academy-source.ts` to load and validate the pinned Academy Home guide and action source,
   and extend the Academy generator to emit that setup data plus the lesson data the landing
   component needs. The generator remains the only source of lesson ordering and public URLs.
2. Add one dedicated Astro component for the Academy overview. It owns page-specific markup and
small presentation helpers only; it does not reparse Academy files or independently infer tracks.
3. Add scoped front-door styles to `site/src/styles/academy.css`, reusing existing CodeArbiter
tokens and primitives. No separate CSS framework, new dependency, or competing site shell.
4. Update the generated `/academy/` index to render the component instead of a bare Markdown list,
   and update route-level title handling so that the page has one H1 and no displaced context card.
5. Extend generator and source tests to prove the Home setup anchor, the first published Foundation
   lesson, all three tracks, and all published lesson URLs reach the generated landing data.

## Acceptance criteria

1. `/academy/` has a practical hero, exactly one visually primary action to the Home setup section,
   and an orientation strip naming lesson count, tracks, self-paced pace, and learner-owned proof.
2. The authoritative five-step Home setup appears before F01 and preserves the exact
   `complete-these-five-setup-steps-before-f01` anchor expected by the pinned F01 source backlink,
   with a tested `#setup` compatibility alias for legacy guide links.
3. The first Foundation lesson is visible after setup and displays title, outcome, estimated time,
   and a link to its existing lesson route.
4. Foundation, Practitioner, and Power user each render from the pinned source with accurate
   lesson count and total estimated minutes. Each generated lesson has one canonical curriculum
   record; extra F01 links are permitted only for its contextual start card and its inventory card.
5. A compact three-step practice explanation appears without claiming simulated, hosted, or
   automatically tracked training state.
6. Desktop and mobile use the native CodeArbiter shell, design tokens, and navigation rail; at
   1440px and 390px neither layout has horizontal overflow or an inaccessible disclosure mechanism.
7. The built Academy overview contains exactly one H1, keeps a logical H1→H2 heading order, exposes
   keyboard-reachable primary/card/disclosure controls in visual order, and gives each disclosure a
   descriptive accessible name and native expanded/collapsed state.
8. The source-loading/generation pipeline rejects malformed or incomplete Home or lesson landing data rather
   than emitting a misleading overview.
9. No new package or remote runtime service is added.
10. `npm --prefix site run typecheck`, `npm --prefix site run test`, `npm --prefix site run build`,
   and `npm --prefix site run link-audit` pass. The existing Academy source and command-preference
   tests continue to pass.
11. A live 1440px and 390px inspection verifies first-click clarity, keyboard focus, disclosure
   behavior, target sizing, and `document.documentElement.scrollWidth <= window.innerWidth`.
12. A returning learner can reach all lessons from a visible `View all lessons` route or track
   anchor at both desktop and mobile widths.

## Out of scope

- Lesson content, learner data, accounts, certificates, progress persistence, and completion
  tracking.
- Changes to Academy's pinned source, its safe-training controls, or any plugin command.
- A separate Academy app, theme, navigation system, or marketing dependency.

## Evidence informing the design

- The 2026-08-26 live-page audit found a sparse opening followed by a 19-item syllabus list.
- Codecademy makes commitment legible before syllabus depth by exposing level, time, and outcomes.
- Microsoft Learn leads with a guided path and an explicit route into modules before its full
  inventory. The implementation borrows those interaction principles, not their visual identity.

## Open questions

None. The approved scope intentionally avoids learner accounts or persisted progress.
