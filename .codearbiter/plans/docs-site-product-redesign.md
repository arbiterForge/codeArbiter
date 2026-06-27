# Plan: docs-site product redesign

**Spec:** `.codearbiter/specs/docs-site-product-redesign.md` (APPROVED 2026-06-27)
**Lane:** `/ca:sprint` (autonomous). **Slug:** `docs-site-product-redesign`
**Standing quality gate:** every artifact routed through the `anti-slop-design` bundle per medium
(web / documents / diagram), `design-quality-reviewer` dispatched.
**Real commands** (from `tech-stack.md` / `site/package.json`): `cd site && npm run build`
(runs `gen` then `astro build`); `cd site && npm run link-audit`; `cd site && npm run gen`.
**Constraints:** build ON Starlight; keep `gen.ts`; no new test harness (reuse build + link-audit).

## AC ledger (verbatim from spec)

- **AC-01** — `npm run build` in `site/` (runs `gen` first) exits 0.
- **AC-02** — Build produces the full generated Reference (38 commands + 21 skills + 15 agents);
  generator pipeline contract unchanged (page count preserved).
- **AC-03** — No broken internal links in the built site (link check passes).
- **AC-04** — An Install page exists at a stable slug with the concrete install path
  (marketplace add + `/ca:init` + `arbiter: enabled` opt-in).
- **AC-05** — A Quickstart page exists and walks: opt a repo in → run a first command → observe a
  gate catching a real mistake.
- **AC-06** — Built sidebar renders exactly four curated top groups (Getting started, Guides,
  Concepts, Security) above the generated Reference group.
- **AC-07** — Reference subgroups (Commands, Skills, Agents) render collapsed by default.
- **AC-08** — `concepts.md` split: each of the nine concepts exists as its own page/slug under a
  Concepts group.
- **AC-09** — The Guides group contains each of the nine named guides as a real (non-stub) page —
  task-oriented title + ≥1 concrete step/command.
- **AC-10** — In built `index.html`, the first two content blocks in DOM order are the hero and the
  gate-catch terminal; command block, lane-flow diagram, and Forge showcase appear after.
- **AC-11** — Hero renders without the oversized glow dead-space and without empty side gutters at
  desktop width (`design-quality-reviewer` layout-leaf verdict).
- **AC-12** — `design-quality-reviewer` against landing (`medium-web`), a representative doc page
  (`medium-documents`), and diagrams (`medium-diagram`) returns no CRITICAL or HIGH.
- **AC-13** — Theme defines complete light AND dark token sets; both render with brand identity and
  contrast intact (reviewer core/color verdict).

## Task table

| id | path(s) | verification | maps-to (tdd obligation) | covers | depends-on | status |
|----|---------|--------------|--------------------------|--------|-----------|--------|
| **T-01** | `site/src/styles/theme.css` | `cd site && npm run build` exits 0; `design-quality-reviewer` (core+color) → no CRIT/HIGH on token system | theme exposes complete light+dark token sets; build clean | AC-13 | — | ACCEPTED |
| **T-02** | `site/src/content/docs/index.mdx` | after build, `site/dist/index.html` DOM order: hero + gate-catch terminal precede command-block, lane-flow, Forge | landing DOM order = hero, terminal first | AC-10 | T-01 | ACCEPTED |
| **T-03** | `site/src/styles/landing.css`, `site/src/styles/theme.css` (`.hero`) | `design-quality-reviewer` (medium-web+layout) → no CRIT/HIGH on landing layout (no dead gutters/glow); build clean | landing layout clears layout-leaf pre-flight | AC-11 | T-01, T-02 | ACCEPTED |
| **T-04** | `site/src/content/docs/getting-started/install.md` | after build, `site/dist/getting-started/install/index.html` exists and contains the marketplace-add + `/ca:init` + `arbiter: enabled` steps | Install page exists with concrete install path | AC-04 | — | ACCEPTED |
| **T-05** | `site/src/content/docs/getting-started/quickstart.md` | after build, quickstart page exists; contains opt-in → first command → a gate catch, in order | Quickstart tutorial exists with the 3 steps | AC-05 | T-04 | ACCEPTED |
| **T-06** | `site/astro.config.mjs`, `site/src/content/docs/overview.md` (retitle to "What is codeArbiter" under Getting started) | built sidebar shows Getting started (Install, Quickstart, What is codeArbiter) + Concepts + Security above Reference; Commands/Skills/Agents groups `collapsed: true`; build clean | sidebar interim groups + reference collapsed | AC-07, AC-06 (interim) | T-04, T-05 | ACCEPTED |
| **T-07** | `site/` (build output), `site/scripts/generator/` (contract unchanged, not edited) | `cd site && npm run build` exits 0; generated reference = 38+21+15 pages; `cd site && npm run link-audit` reports zero broken links | site builds clean; 74 ref pages; no broken links | AC-01, AC-02, AC-03 | T-01..T-06 | ACCEPTED |
| **T-08** | `site/src/content/docs/index.mdx`, `site/src/styles/*.css` | `design-quality-reviewer` (medium-web + core+typography+color+layout+images) → no CRIT/HIGH on landing | landing clears web-medium anti-slop review | AC-12 (landing) | T-02, T-03 | ACCEPTED |
| **T-09** | `site/src/content/docs/concepts/*.md` (9 pages: gated-lanes, feature-forge, smarts, adrs, checkpoints, provenance-drift, jit-injection, persona-context, auditability); retire `concepts.md` | after build, all 9 concept pages exist at their slugs; build clean; `npm run link-audit` passes | concepts split into 9 deep-linkable pages | AC-08 | T-01 | ACCEPTED |
| **T-10** | `site/astro.config.mjs` | built sidebar Concepts group lists the 9 concept pages; build clean | concepts sidebar group rewired | AC-08 | T-09 | ACCEPTED |
| **T-11** | `site/src/content/docs/guides/opt-in-a-repo.md` | guide page builds; task-oriented title + ≥1 concrete command (`/ca:init`); link-audit passes | guide: opt a repo in | AC-09 | T-06 | ACCEPTED |
| **T-12** | `site/src/content/docs/guides/feature-lane.md` | guide builds; title + ≥1 concrete command (`/ca:feature`); link-audit passes | guide: the feature lane end-to-end | AC-09 | T-06 | ACCEPTED |
| **T-13** | `site/src/content/docs/guides/autonomous-sprints.md` | guide builds; title + ≥1 concrete command (`/ca:sprint`, `--farm`); link-audit passes | guide: autonomous sprints | AC-09 | T-06 | ACCEPTED |
| **T-14** | `site/src/content/docs/guides/overriding-a-gate.md` | guide builds; title + ≥1 concrete command (`/ca:override`); link-audit passes | guide: overriding a gate safely | AC-09 | T-06 | ACCEPTED |
| **T-15** | `site/src/content/docs/guides/recording-adrs.md` | guide builds; title + ≥1 concrete command (`/ca:adr`); link-audit passes | guide: recording ADRs | AC-09 | T-06 | ACCEPTED |
| **T-16** | `site/src/content/docs/guides/adding-a-dependency.md` | guide builds; title + ≥1 concrete command (`/ca:add-dep`); link-audit passes | guide: adding a dependency | AC-09 | T-06 | ACCEPTED |
| **T-17** | `site/src/content/docs/guides/releasing-a-version.md` | guide builds; title + ≥1 concrete command (`/ca:release`); link-audit passes | guide: releasing a version | AC-09 | T-06 | ACCEPTED |
| **T-18** | `site/src/content/docs/guides/the-statusline.md` | guide builds; title + ≥1 concrete command (`/ca:statusline`); link-audit passes | guide: the statusline | AC-09 | T-06 | ACCEPTED |
| **T-19** | `site/src/content/docs/guides/troubleshooting.md` | guide builds; title + ≥1 concrete command (`/ca:doctor`); link-audit passes | guide: troubleshooting | AC-09 | T-06 | ACCEPTED |
| **T-20** | `site/astro.config.mjs` | built sidebar shows exactly 4 curated groups (Getting started, Guides, Concepts, Security) above Reference; build clean | sidebar reaches final 4-group form | AC-06 (full) | T-11..T-19, T-10 | ACCEPTED |
| **T-21** | a representative `site/src/content/docs/guides/*.md` + `site/public/diagrams/*.svg` | `design-quality-reviewer` (medium-documents) on a doc page + (medium-diagram) on diagrams → no CRIT/HIGH | doc-prose + diagram media clear anti-slop review | AC-12 (doc + diagram) | T-09, T-11..T-19 | ACCEPTED |
| **T-22** | `site/` (build output) | final `cd site && npm run build` exit 0 + `npm run link-audit` zero broken + 74 ref pages, with all slices merged | full-site integrity gate (re-run of T-07 over the complete site) | AC-01, AC-02, AC-03 | all | ACCEPTED |
| **T-23** | `site/src/styles/theme.css`, `site/src/styles/landing.css`, `site/src/content/docs/index.mdx` | central build + re-review: light-mode `.ca-forge h2` AA, callout labels AA, no nested `<p>`, distinct `<title>` | remediate T-08 MEDIUM/LOW + markup bug (SD-03) | AC-13, AC-12 | T-08 | ACCEPTED |

## Order & dependencies

No cycles. Three contiguous slices:

- **MVP slice (shippable floor):** T-01 → T-02 → T-03 → T-04 → T-05 → T-06 → T-07 → T-08.
  Satisfies AC-01..AC-05, AC-07, AC-10, AC-11, AC-13, AC-12(landing), and AC-06(interim: 3 groups
  + collapsed Reference). This is the first batch.
- **Slice B — Concepts split:** T-09 → T-10. Satisfies AC-08.
- **Slice C — Guides + final wiring:** T-11..T-19 (parallelizable) → T-20 → T-21 → T-22.
  Satisfies AC-09, AC-06(full), AC-12(doc+diagram), and re-proves AC-01/02/03 over the whole site.

## Coverage proof (bijective)

- Every AC covered: AC-01 (T-07,T-22) · AC-02 (T-07,T-22) · AC-03 (T-07,T-22) · AC-04 (T-04) ·
  AC-05 (T-05) · AC-06 (T-06 interim, T-20 full) · AC-07 (T-06) · AC-08 (T-09,T-10) ·
  AC-09 (T-11..T-19) · AC-10 (T-02) · AC-11 (T-03) · AC-12 (T-08 landing, T-21 doc+diagram) ·
  AC-13 (T-01). No uncovered criterion.
- Every task covers ≥1 AC: confirmed (column "covers" non-empty for all T-01..T-22). No scope creep.

## Out-of-scope notes

- `[NEEDS-TRIAGE]` The `anti-slop-design` bundle has no dedicated prose-*voice* leaf (only
  `medium-documents` copy-laws + `core` tells). A future bundle enhancement — a writing/voice leaf —
  would strengthen prose review for doc-heavy producers. Out of scope for this sprint; harvest to
  `open-tasks.md`.
