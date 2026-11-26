# codeArbiter as a machine: ownership and maintenance

`/concepts/machine/` explains the whole system as one machine: every part is a concept from AI
inference or a codeArbiter component, and every lane is one command's route. This file says what
the page owns, what it borrows from the plugin sources, and what to do when the build refuses it.

## Where it lives

| Piece | Path |
|---|---|
| Page | `src/content/docs/concepts/machine.mdx` |
| Static reading path and traced example | `src/components/CodeArbiterMachine.astro`, `src/styles/machine.css` |
| Curated model | `scripts/machine/machine-data/*.json` |
| Loader and drift checks | `scripts/machine/machine-model.ts`, `scripts/machine/machine-claims.ts` |
| Shared text and frame rendering | `scripts/machine/machine-render.ts` |
| Tests | `scripts/machine/*.test.ts`, `test/browser/machine.spec.ts` |

## What is curated and what is derived

The explanations are curated: part names, taglines, plain-terms summaries, how each part works,
tours and failure scenarios. Everything the page states about the shipped plugin is resolved from
the sources the reference generator already reads, every time the site builds:

- **Gates.** Gate IDs, whether each blocks or reminds, and the block messages come from the
  `block()` and `remind()` call sites in `plugins/ca/hooks` (`scripts/generator/extract-hook-gates.ts`).
  The traced example prints those messages directly, so a reworded message updates the page.
- **Commands and lanes.** Command identity, visibility and lane family come from
  `core/surface/command-routes.json`. Every core, advanced and internal command must have exactly
  one lane, filed under the family and tier the routes file gives it.
- **Hosts.** Command spelling and the commands each host leaves out come from `core/hosts.json`.
- **Version.** The page reads the version from `plugins/ca/.claude-plugin/plugin.json`.
- **Behavior claims.** `machine-data/claims.json` lists the statements that describe behavior
  rather than names: which calls write to `gate-events.log`, and when the rules are injected again.
  Each claim names the smallest source fact it depends on (a function that must or must not make a
  call, or text a file must contain), so unrelated edits to the same file do not fail the build.

`provenance.json` records the release the model was written against and the commit it was last
reviewed at. It is a record for reviewers, not a pin: the checks above run against the working tree.

## When the build refuses the model

`loadMachine()` lists every disagreement as one sentence, for example
`lane ca-spike names command spike, which core/surface/command-routes.json does not define`.
For each finding:

1. Read the source change that caused it.
2. Update the curated explanation so it is true again: rename or remove a lane, move it to its new
   family, drop a gate that no longer exists, or rewrite a claim and its check.
3. Run `npx vitest run scripts/machine` and `npm run build`, then
   `npx playwright test test/browser/machine.spec.ts`.
4. Advance `reviewedAt` in `provenance.json` to the commit you reviewed.

Do not weaken a check to silence a finding. If a claim is no longer true, change the sentence the
page shows, then change its check to match the new behavior.

## What stays illustrative

Token splits, token IDs, probabilities and attention patterns used as examples explain general
mechanisms. They are not measurements of any particular model, and the page says so in its
evidence layer.
