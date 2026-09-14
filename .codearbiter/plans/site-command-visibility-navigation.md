# Command Visibility Navigation Implementation Plan

**Status:** READY
**Spec:** `.codearbiter/specs/site-command-visibility-navigation.md`
**Approved spec SHA-256:** `e8f1f2ebd89837019128ec4efaab8223013fb489335617f70c8d351a82affb85`
**Goal:** turn the flat 38-link Commands sidebar into registry-backed visibility disclosures while
preserving every route and the one canonical Sidebar used by normal pages and the homepage rail.

## Global constraints

- Work only in `C:\Users\brenn\projects\codeArbiter-worktrees\site-review-nav-rebaseline` on
  `codex/site-command-visibility-navigation`, based on exact
  `185175eaad273f044eab834e662b22cc34b0d5ae`.
- Treat `core/surface/command-routes.json` and its generated catalog as the sole visibility authority.
- Establish RED for each obligation before production changes; do not weaken an existing gate.
- Preserve all 38 direct command URLs, host projections, registry values, compatibility rules,
  route-base behavior, canonical Sidebar reuse, and unrelated user-owned state.
- Do not change Academy grouping, add navigation persistence, introduce a header/menu replacement,
  merge, release, tag, publish, deploy Pages, or perform destructive cleanup.

## Acceptance-criterion ledger

| ID | Verbatim criterion |
|---|---|
| AC-01 | Given command pages and a validated generated catalog, one focused generator test observes a `Commands` sidebar group whose immediate children are Core, Advanced, Compatibility aliases, Internal, and Deprecated in that order; every command link occurs exactly once, links are alphabetical within each child, and the production inventory totals 18, 13, 5, 1, and 1. |
| AC-02 | Given that generated nested data, one focused configuration test observes unchanged `reference/commands/<slug>` destinations, `collapsed: false` for Core, `collapsed: true` for the other four groups, and no alternate registry, persisted expansion state, workflow nesting, or route rewrite; the active command remains discoverable through the existing current-link ancestor expansion. |
| AC-03 | Given a Core command page and a non-Core command page, one rendered browser-matrix test at wide, standard, and compact widths observes the active page inside its open group, all five groups reachable, native disclosure keyboard operation, visible focus, scroll reachability, mobile Menu operation, deployment-base-correct links, and the same behavior in the homepage's branded docs rail. |

The mechanical `uncovered-intent` check returned empty. Negative check: if AC-01 through AC-03 pass
and nothing else changes, no checkpoint-031 defect remains; Academy grouping is a separate campaign
checkpoint, not missing scope here.

## Ordered task ledger

| ID | Paths | Verification | Maps to | Covers | Depends on | Status |
|---|---|---|---|---|---|---|
| T-01 | `site/test/generator/build-index.test.ts`; `site/test/generator/command-catalog-discovery.test.ts`; add `site/test/generator/command-sidebar-inventory.test.ts`; `site/test/generator/generate-forge.test.ts`; `site/test/generator/generate.test.ts`; `site/test/generator/lens-pages.test.ts`; add `site/test/fixtures/plugin/generated/command-catalog.json`; add `site/test/fixtures/plugin-collisions/generated/command-catalog.json`; `site/scripts/generator/types.ts`; `site/scripts/generator/build-index.ts`; `site/scripts/generator/generate.ts`; add `site/test/reference-sidebar.test.ts`; add `site/test/sidebar-navigation-presentation.test.ts`; add `site/scripts/reference-sidebar.ts`; modify `site/astro.config.mjs`; inspect-only contract paths `site/src/components/Sidebar.astro`, `site/src/components/SidebarSublist.astro`, `site/src/components/SplashDocsRail.astro`, `site/src/styles/design-system.css` | Retain the recorded generator and public-count RED evidence. Before editing the configuration projection, establish focused RED observations in the two new reference-sidebar tests, then implement the producer and consumer atomically. Make both focused commands pass: `npm --prefix site exec vitest run test/generator/build-index.test.ts test/generator/command-catalog-discovery.test.ts test/generator/command-sidebar-inventory.test.ts` and `npm --prefix site exec vitest run test/reference-sidebar.test.ts test/sidebar-navigation-presentation.test.ts`. Prove five canonical visibility groups, exactly 38 command links, the unchanged 38 Commands public count, nested collapse, unchanged routes, current-link ancestor behavior, native disclosure/focus/scroll prerequisites, and canonical Sidebar reuse without persistence or workflow nesting. Mutation-check missing, duplicated, misordered, wrongly classified, catalog-absent command generation, malformed JSON, noncanonical visibility projection, or top-level-group-counted membership fails. Before acceptance, `npm --prefix site run test`, `npm --prefix site run coverage`, and `npm --prefix site run typecheck` must pass so no producer/consumer-incompatible intermediate state is accepted. | OBL-01: generated grouping, exact inventory, and preserved public count; OBL-02: Starlight projection contract; OBL-03: canonical rendered-navigation prerequisites | AC-01, AC-02, AC-03 | none | ACCEPTED — 2026-09-12; controller independently verified 19 projector/config tests, 16 generator tests, 591 full-site tests, Stage 2 coverage (75.76% lines / 76.69% branches), typecheck, diff hygiene, exact single Commands-group fail-closed behavior, and the architecture-review correction. |
| T-02 | `site/src/generated/sidebar.json`; `site/src/content/docs/reference/**` generated outputs; all T-01 source/test paths; `site/package.json`; `site/scripts/link-audit.ts` | `npm --prefix site run gen` succeeds twice with byte-identical second output; all focused tests pass; `npm --prefix site run test`, `npm --prefix site run coverage`, `npm --prefix site run typecheck`, `npm --prefix site run build`, and `npm --prefix site run link-audit` pass at Stage 2; exact counts remain 18/13/5/1/1 and every direct command route exists once. | OBL-01, OBL-02, OBL-03 integrated and whole-site proof | AC-01, AC-02, AC-03 | T-01 | ACCEPTED — 2026-09-12; two consecutive generations were byte-identical, generated paths stayed clean, production build emitted 155 pages, link audit resolved 26,331 internal links across 172 pages, and the exact 38 unique command routes remain 18/13/5/1/1 with zero missing pages. |
| T-03 | Built routes for `/reference/commands/commit/`, one non-Core command route, and `/`; `site/src/components/Sidebar.astro`; `site/src/components/SidebarSublist.astro`; `site/src/components/SplashDocsRail.astro` | One recorded browser matrix at wide, standard, and compact widths verifies active-group expansion, all five groups, native keyboard toggling, visible focus, scroll reachability, compact mobile Menu, deployment-base-correct links, and parity in the branded homepage rail. | OBL-03: direct rendered behavior | AC-03 | T-02 | ACCEPTED — 2026-09-12; fresh 1440×1000, 1024×900, and 390×844 rendered checks passed for Core and Advanced current-page expansion, five native groups, Enter toggling, 2px solid gold focus indication, scroll containment/reachability, compact Menu, 38 unique direct command routes, and homepage docs-rail parity. |

## Order and MVP slice

The dependency chain is acyclic and linear: T-01 → T-02 → T-03. T-01 atomically owns the
producer and consumer RED-before-GREEN cycle because the nested producer schema cannot satisfy the
full-suite gate while the consumer remains flat. T-02 and T-03 independently verify the resulting
integrated surface.

**MVP slice:** T-01 through T-03. This is the smallest contiguous task set that implements all three
criteria, clears full-site validation, and proves the actual rendered behavior. Independent combined-
diff review is owned by subagent-driven-development after the scoped tasks; governed commit and PR
delivery remain the pipeline's later commit-gate and finishing steps rather than implementation tasks.

## Bijection proof

- AC-01 is advanced by T-01 and T-02.
- AC-02 is advanced by T-01 and T-02.
- AC-03 is advanced by T-01 through T-03, with T-03 owning the direct rendered matrix.
- Every task covers at least one AC; no task introduces Academy, persistence, route, registry,
  command, compatibility, release, deployment, or cleanup scope.

No follow-up triage item was introduced.
