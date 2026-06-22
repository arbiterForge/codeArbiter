# Spec — docs-site-polish: make the public docs site beautiful, functional, forge-forward

status: APPROVED — 2026-06-22, by repo owner (Phase 4 STOP gate cleared); build path: ultracode workflow
slug: docs-site-polish
created: 2026-06-22
lane: full → build path: **ultracode workflow** (multi-agent), owner-selected
scope-guard: **site-only** — no `plugins/ca/**` change (badge data lives in the site generator)
relates-to: [CONFIRM-05] (Feature Forge promotion bar for `--farm`) — the preview badges this spec adds
*surface* the preview status that CONFIRM-05 governs; promotion stays a separate owner decision and this
spec does not resolve it. Follows `specs/docs-site-mvp.md` (the #94 `--farm` Step-6 artifact this polishes).

## Problem

The docs site under `site/` was produced by the `/sprint --farm` Step-6 test (#94) — a functional MVP,
but it reads like a scaffold. It is now public-facing and does not earn a first-time visitor's
understanding:

- The landing page is stock Starlight chrome (a four-card grid) — it asserts "Gated" but never *shows*
  a gate doing its job, which is codeArbiter's actual conversion mechanic (adoption-strategy: *show a
  gate catch a real mistake*).
- The **Feature Forge** — the per-feature preview/maturity model that is a core differentiator — is
  mentioned **nowhere** on the site, even though the landing page literally prints `/ca:sprint --farm`
  with no explanation of what `--farm` or "preview" means.
- Stock chrome with no logo, favicon, or social link reads as unfinished; base-path-fragile links
  (hero actions hardcode `/codeArbiter/`) are a known GH-Pages breakage class (#109 "unbreak docs deploy").

## Caller

A first-time visitor — a Claude Code user evaluating adoption. "Done" = they land, *get it within one
screen* (what it is, why it matters, their first command), see the differentiator (gated lanes + the
transparent, data-promoted Feature Forge), and watch a gate catch a real mistake.

## Scope

**In scope** (the `site/` tree only):

- A **bespoke landing page** replacing the stock card grid: custom hero, an animated gate-catch terminal
  (the conversion centerpiece), and a Feature Forge showcase.
- An **inner-page visual pass** on Overview and Concepts: custom callouts (note / warn / gate / preview),
  a coherent **three-diagram set** (lane-flow, two-axis labeling model, gate model), and per-reference
  **preview badges**.
- **Feature Forge surfacing**: landing showcase + a Concepts section + automated preview badges driven by
  a **site-side generator allowlist**.
- **Functional integrity**: working logo/favicon/social config, base-path-safe internal links, working
  Pagefind search, and a green `site/` build + test + typecheck.

**Out of scope (the boundary that keeps this honest):**

- **No `plugins/ca/**` change.** Preview status is sourced from an allowlist inside `site/scripts/generator/`,
  *not* from new plugin frontmatter. (Owner-selected; the can't-drift frontmatter alternative was rejected
  to hold the site-only boundary — see Open questions / triage.)
- **No ejecting from Starlight** or replacing the theme engine. Customize *within* the framework.
- **No rewrite of the auto-generated reference bodies.** Their content is generator output; only the badge
  decoration and the generator allowlist are added.
- **No new framework/plugin behavior.** This is documentation presentation only.

## Acceptance criteria

Each is verifiable by a single test (automated unit/build check, or the named design reviewer where the
criterion is visual). Each becomes one `tdd` Phase-1 obligation.

**Functional integrity**

1. `npm run build` in `site/` exits 0 with `gen` having regenerated the reference pages (assert exit 0 +
   reference pages present in `dist`).
2. Every internal link in the built `site/dist` HTML resolves under `base: /codeArbiter` — a link-audit
   asserts each internal href is base-prefixed (or correctly relative) and its target file exists; zero
   dangling internal links.
3. Hero/primary action links derive from a single base-path source (or a test asserts each rendered hero
   action href maps to an existing `dist` page) — the hardcoded-base desync class is closed.
4. `astro.config` sets `favicon`, a `logo`, and a GitHub `social` link; the favicon/logo asset exists in
   `dist` (assert config fields present + asset emitted).
5. Pagefind search is present and indexed in `dist`, and a query for a known term (e.g. `gate`) is
   resolvable against the built index (assert index emitted + search UI present).

**Beautiful (within Starlight)**

6. The landing page is bespoke: the stock `CardGrid` is replaced by a custom hero + gate-catch terminal +
   forge showcase (assert the named landing components/markup exist in built `index.html`, stock card grid
   absent).
7. The gate-catch terminal honors `prefers-reduced-motion: reduce`: under that query the animation is
   disabled and the **full transcript renders statically** (assert the media query + static transcript
   present).
8. The gate-catch terminal transcript is real DOM text (not an image/canvas) and screen-reader readable;
   animation is presentational only (assert transcript text nodes present in `index.html`).
9. Three new diagrams exist as SVG assets — **lane-flow** (command→route→gate→ship), **two-axis labeling
   model** (SemVer vs Feature Forge), **gate model** — each referenced from its relevant page and each
   carrying an accessible `<title>`/alt (assert 3 SVGs exist, referenced, titled).
10. Overview and Concepts carry the custom callout treatment (≥1 `note`/`gate`/`preview` callout rendered;
    assert callout markup present).
11. **Visual design gate:** the `design-quality-reviewer` clears the landing + inner pages against the
    `anti-slop-design` reference with **no CRITICAL or HIGH** *visual* design-slop finding. (Reviewer is the
    verifier for this visual criterion. Prose slop is a separate axis — see AC-19/20; the visual reviewer
    does not gate copy voice.)

**Feature Forge (highlight the forge)**

12. The landing has a Feature Forge showcase stating preview features are **opt-in, ship dormant/off by
    default, and are promoted by real-world evidence**, plus the two-axis model (SemVer = whole payload;
    Feature Forge = per-feature preview) — assert showcase markup + those key claims present in `index.html`.
13. Concepts gains a "Feature Forge" section carrying the two-axis model and the preview→stable
    (evidence-promoted) idea (assert section heading + content present).
14. A site-side allowlist (`site/scripts/generator/` — no `plugins/ca` change) marks preview features; the
    generated `/ca:prune` reference page renders a **preview badge**, and the `/ca:sprint` page renders a
    "`--farm` — preview" callout. A generator vitest asserts the badge/callout appears for allowlisted
    features and **not** for stable ones.
15. The landing `--farm` command line is no longer context-free: it links to / sits adjacent to the Feature
    Forge showcase so a visitor can find what `--farm`/"preview" means (assert the link/adjacency in markup).

**UX (how adoption feels)**

16. Above the fold, the landing answers *what / why / first command* within one screen: hero tagline, the
    gate-catch demo, and a copy-able primary first command with a single primary CTA (Get started →
    overview) (assert the three elements + exactly one primary action variant in the hero markup).

**Copy anti-slop (prose voice — the separate axis from visual design)**

The current copy reads as AI-generated, the loudest tell being em-dash overuse (`index.mdx` 7, `overview.md`
16, `concepts.md` 10). Em-dashes are not banned — the goal is *sparing* use so commas, colons, periods, and
parentheses carry the load they should.

19. **Hard, automated em-dash cap.** Every user-facing site prose page (`index.mdx`, `overview.md`,
    `concepts.md`, and any new prose page) contains **≤ 3 em-dashes**, and no single paragraph uses more than
    one. A repeatable counting check (committed under `site/`) asserts the per-page ceiling and exits non-zero
    on a violation — this is the test for the criterion. (Code blocks, frontmatter, and the auto-generated
    reference bodies are exempt; the cap is on hand-written prose.)
20. **Copy-slop checklist pass.** The landing + inner copy clears a written copy anti-slop checklist:
    no "not just X, but Y" / "it's not A — it's B" template, no padded tricolons, no hedging filler
    ("perhaps", "arguably"), no LLM-tell vocabulary ("delve", "leverage", "seamless", "robust", "tapestry"),
    and varied sentence length (not a uniform medium-rhythm wall). The authoring agent self-applies the
    checklist and a reviewer confirms; the checklist ships in the workflow's verify stage as a named gate.

**Build/CI integrity (boundary + green)**

21. `site/` vitest (`npm test`) and `npm run typecheck` both exit 0, including the new badge/allowlist tests
    and the em-dash check (AC-19).
22. `git diff --name-only` for the change touches only `site/**` (and this spec/plan under `.codearbiter/**`)
    — **no `plugins/ca/**` file modified** (boundary held).

## Open questions

- **[CONFIRM-05]** (cross-ref, non-blocking here) — the preview badges (AC-14) *display* the preview status
  that CONFIRM-05's promotion bar governs. When `--farm` is promoted, the site allowlist must drop its
  preview entry. This spec surfaces the status; it does not set or resolve the promotion bar.

No new blocking `[CONFIRM-NN]` is raised by this spec.

## Deferred / triage (non-blocking)

- **[NEEDS-TRIAGE] Allowlist drift.** The generator allowlist (AC-14) is hand-maintained and can drift if a
  forge feature is promoted to stable and nobody updates it. Two follow-ups worth promoting: (a) a check
  (CI or `/ca:doctor`) that reconciles the site allowlist against actual preview status; (b) revisit the
  rejected `forge:` source-frontmatter approach if/when a `plugins/ca` change is otherwise warranted, to
  make preview status single-source / can't-drift.
