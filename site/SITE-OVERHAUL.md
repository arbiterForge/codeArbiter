# Site overhaul: one visual language, teaching motion, a connected machine

## Approval and authority

- Requested by the product owner in the work-session conversation on 2026-11-26 (America/Chicago;
  2026-11-27 UTC), after the 3D machine shipped: "Work over the rest of the site, holding nothing
  back, bring the same energy you put into the machine into everything, make my site wowing and
  educational".
- Decisions the owner chose in the same session, from offered options:
  - **Design latitude: "Bolder identity".** Revisit the landing structure and visual style (bigger
    animated hero, richer colour and cards), revising the October contracts wherever they hold the
    wow back.
  - **Merge authority: "Merge when green".** The implementer merges each PR once CI is green and an
    independent reviewer pass finds nothing blocking. The owner reviews on the live site and can
    revert any PR.
- This approval supersedes `DOCS-OVERHAUL.md` M3 (five-section landing) and M5 (quieter visual
  style) where this file says so. M1 (reader layer), M2 (one front door), M4 (lighter furniture)
  and M6 (split pages) stand.
- It does not authorize: Academy curriculum changes (`academy-source/` is separately owned),
  runtime, hook or gate behavior changes, releases or tags, invented evidence, ADRs (they are
  user-attributed), changes to search-pinned titles and descriptions, analytics, remote fonts or any
  new runtime network request.

## Thesis

The site is accurate and carefully governed, but it explains with prose where a picture would teach
faster, and its pages do not connect to the one model that ties them together. The overhaul gives
the site one visual language (the machine's symbols), motion that explains sequence, and explorers
over the long reference pages. The proof rules do not loosen: every fact shown in motion is bound
to its source by a test, exactly as the machine's model is.

## What stays fixed

- Proof before promise. Captured output is labelled captured; illustrative steps are labelled
  illustrative. No fabricated activity.
- A static reading path for every moving or interactive piece: complete without JavaScript, in
  print and for assistive technology.
- Keyboard operation, visible focus, `prefers-reduced-motion` (no movement, every step visible) and
  forced colours.
- Local-first delivery: no remote fonts, analytics or runtime requests. Motion is SVG, CSS and a
  small amount of script, with no new runtime dependency.
- Gold still means gates, decisions and primary actions. The richer palette adds the machine's
  meanings beside it rather than spending gold as decoration.

## Program

One pull request per theme, each independently reviewable and revertible.

| Slice | Theme | Outcome for the reader |
|---|---|---|
| S1 | Identity and front door | A landing that shows the machine working: an animated, source-bound trace of one command through the machine, the real captured replay, a render of the 3D machine, and richer cards that carry the machine's symbols. |
| S2 | Docs shell and machine joins | Every page says where it sits in the machine; every command and hook gate links to its part, with "Run this lane in 3D". |
| S3 | Reference explorers | A filterable hook-gate explorer, a command matrix with host spellings and a navigable changelog. Fixes the generator prose that escapes the voice gate. |
| S4 | Concept explainers | Each core concept opens with its idea as a step-through scene built on the S1 engine. |
| S5 | Glossary previews | Terms on concept and guide pages show their definition on hover or focus, from the one glossary. |
| S6 | Learning path map | The four stages as a visual route, with progress kept only in the reader's browser. |
| S7 | Polish | Consistent heading case, readable simple tables on phones, a final cross-site pass. |

## S1 done-criteria

- `scripts/scenes/` holds a typed scene model, a validator and a pure SVG renderer. A scene is a
  set of machine parts (nodes), handoffs (edges), terminal notes and ordered steps, drawn in a wide
  and a tall composition from the same data.
- The hero scene's nodes are machine parts. Their frames come from the machine key's kind frames,
  their zone labels from the machine layout, and every terminal string from the captured hook proof
  (`src/assets/proof/hook-proof.json`). Tests fail if any of them drifts.
- `SceneStage.astro` renders both compositions and an ordered step list. Without JavaScript the
  list is the complete reading path. With JavaScript the hero plays on its own only when motion is
  allowed and it is on screen, with a visible pause control; any control use hands the reader the
  steps.
- The landing tells one story in seven sections: hero with the animated trace; the real replay;
  the machine; outcomes; lanes with their real routes; hosts with every spelling; the closing call
  to action with fit. One primary action stays above the fold, and the search-pinned title,
  description and H1 are unchanged.
- `DESIGN-SYSTEM.md` records the bolder identity, the scene contract and the new landing structure.
  The landing tests assert the new contract rather than deleting the old checks.

## S2 done-criteria

- Joins come from the machine model, never a hand-kept list (`scripts/generator/machine-joins.ts`).
  A generated command page shows its lane's real route and links the lane part. A skill or agent
  page gains "In the machine" only where the model cites its own plugin file. Each hook gate names
  the parts whose hooks list carries it and the failure scenarios tagged with it.
- Hand-authored pages show "In the machine" chips in the orientation strip from
  `src/data/machine-map.json`; a test checks every page and part exists.
- Every link into `/concepts/machine/` resolves to an id there, checked against the build.
- Hook messages print character for character. Smart dash conversion is off site-wide, because it
  printed `--no-verify`, `--ff-only` and `--dry-run` as dashes; a build scan guards it.
- Inner pages carry the blueprint grid and a title that cools toward signal blue; gold stays on
  gates and decisions.

## Verification per slice

Site typecheck, the full `npm test` (build, vitest, Academy base, rendered release applicability),
the link audit, `.github/scripts/check_site_voice.py`, the production-browser suite including axe,
and inspected desktop and phone captures of every changed surface. Then an independent review
pass, green CI on the exact head, merge, the Pages deploy, and a read-back of the live page.
Browser automation is not screen-reader or real-user certification.

## Rollback

Each slice reverts as one unit: its data, renderer, components, styles and tests. Public URLs are
kept, so a revert never breaks an inbound link.
