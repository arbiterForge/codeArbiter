# Documentation Site Completion Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Complete the first-class codeArbiter documentation experience with the historic gate brand, splash docs rail, fixed hero atmosphere, professional diagram family, comprehensive page audit, source-backed generated references, and synchronized README.

**Architecture:** Keep Astro/Starlight as the site shell and reuse its canonical sidebar tree in a splash-only overlay component. Treat the historical gate as a shared SVG geometry system, retain static SVG for operational diagrams, and strengthen authored/generated content at its source. Add static-contract tests around visual assets, interactions, provenance, and page usefulness before each implementation slice.

**Tech Stack:** Astro 7, Starlight 0.41, TypeScript 5.7, Vitest 4.1, local SVG/WebP assets, Markdown/MDX, CSS.

## Global Constraints

- Work only in `C:\Users\brenn\projects\codeArbiter-worktrees\docs-first-class-site` on `codex/docs-first-class-site`.
- Spend no money beyond the user's ChatGPT subscription.
- Keep the pull request in draft state and never merge it.
- Preserve GitHub Pages base-path safety under `/codeArbiter/`.
- Reuse local Manrope and JetBrains Mono font assets.
- Runtime media must come from real product behavior and carry provenance.
- Do not stage `.superpowers/`.
- Use the historic commit-line gate silhouette; only its filled pivot triangle becomes an open downward terminal chevron.
- Operational explanations remain editable, accessible SVG.
- Use test-first changes and independently verifiable commits.

---

## File Structure

- `site/src/components/SplashDocsRail.astro`: splash-only rail, overlay drawer, fallback, accessibility, and client state.
- `site/src/components/SidebarSublist.astro`: canonical navigation tree renderer consumed by both normal sidebar and splash drawer.
- `site/src/assets/gate-mark.svg`: shared icon-only historical gate geometry.
- `site/src/assets/logo.svg`: horizontal wordmark using the shared geometry.
- `site/src/assets/favicon.svg`: reduced-detail small-size gate master.
- `site/src/styles/landing.css`: landing background layer and rail/drawer layout.
- `site/src/styles/design-system.css`: shared brand and diagram tokens.
- `site/src/content/docs/index.mdx`: splash integration only.
- `site/public/diagrams/*.svg`: fifteen operational diagrams.
- `site/scripts/diagram-audit.ts`: deterministic static SVG contract checker.
- `site/test/landing/landing-page.test.ts`: splash, rail, hero, and brand contracts.
- `site/test/generator/diagrams.test.ts`: complete diagram-family contracts.
- `site/test/content/documentation-presentation.test.ts`: authored-page usefulness regressions.
- `site/test/generator/render-*.test.ts`: generated-reference usefulness contracts.
- `README.md`, `docs/readme-hero.webp`: synchronized repository entry point.

### Task 1: Restore the historic gate brand system

**Files:**
- Create: `site/src/assets/gate-mark.svg`
- Modify: `site/src/assets/logo.svg`
- Modify: `site/src/assets/favicon.svg`
- Modify: `site/src/styles/design-system.css`
- Modify: `site/test/content/documentation-presentation.test.ts`
- Modify: `site/test/link-audit/lib.test.ts`

**Interfaces:**
- Produces: an icon master with commit line, hollow node, twin posts, beam, downward open chevron, and proven node.
- Produces: full wordmark and favicon variants derived from the same geometry.

- [ ] **Step 1: Replace the A-mark contract with a failing historic-gate contract**

Add assertions that the mark contains `data-brand-element` values for `commit-line`, `unproven-node`, `gate-posts`, `gate-beam`, `terminal-chevron`, and `proven-node`; contains no `<filter>`; and exposes `viewBox="0 0 160 28"` for the horizontal lockup.

- [ ] **Step 2: Run the focused test and verify RED**

Run: `npm test -- --run test/content/documentation-presentation.test.ts`

Expected: failure because the current A-shaped logo has no historic-gate semantic elements.

- [ ] **Step 3: Implement the three brand masters**

Restore the historical geometry from the predecessor of `7a0a089`, redraw it on a consistent grid, replace the filled pivot with:

```svg
<path
  data-brand-element="terminal-chevron"
  d="m12 3.5 2 3 2-3"
  fill="none"
  stroke="#f3c958"
  stroke-linecap="round"
  stroke-linejoin="round"
/>
```

Use thicker simplified geometry in `favicon.svg`; do not use glow filters.

- [ ] **Step 4: Run brand and link-audit tests**

Run: `npm test -- --run test/content/documentation-presentation.test.ts test/link-audit/lib.test.ts`

Expected: PASS.

- [ ] **Step 5: Commit the brand slice**

Commit message: `feat(site): restore the historic gate identity`

### Task 2: Add the splash documentation rail

**Files:**
- Create: `site/src/components/SplashDocsRail.astro`
- Modify: `site/src/content/docs/index.mdx`
- Modify: `site/src/styles/landing.css`
- Modify: `site/test/landing/landing-page.test.ts`

**Interfaces:**
- Consumes: `Astro.locals.starlightRoute.sidebar`.
- Consumes: `SidebarSublist` with `{ sublist: SidebarEntry[] }`.
- Produces: `.ca-docs-rail`, `#ca-docs-drawer`, and a base-safe fallback to `overview/`.

- [ ] **Step 1: Write failing rail structure and accessibility tests**

Assert that the landing imports `<SplashDocsRail />`, the component delegates to `<SidebarSublist sublist={sidebar} />`, the opener has `aria-controls="ca-docs-drawer"` and `aria-expanded="false"`, and the component includes Escape handling, focus restoration, scroll lock, backdrop close, and an overview fallback.

- [ ] **Step 2: Run the landing test and verify RED**

Run: `npm test -- --run test/landing/landing-page.test.ts`

Expected: failure because `SplashDocsRail.astro` does not exist.

- [ ] **Step 3: Implement semantic rail and drawer markup**

Use a button for the enhanced control, an `<aside id="ca-docs-drawer" aria-label="Documentation navigation">`, the existing `SidebarSublist`, and:

```astro
<noscript>
  <a href={`${import.meta.env.BASE_URL}overview/`}>Open docs</a>
</noscript>
```

Keep the header logo as an ordinary home link.

- [ ] **Step 4: Implement client interaction**

The client script must:

```ts
function openDrawer(): void;
function closeDrawer(options?: { restoreFocus?: boolean }): void;
function trapFocus(event: KeyboardEvent): void;
```

It sets `aria-expanded`, toggles `hidden`, locks body overflow, closes on Escape/backdrop/close button, traps Tab within the drawer, and restores focus.

- [ ] **Step 5: Implement responsive styling**

Use `38px` collapsed width on desktop, `31px` on narrow screens, `292px` drawer width, and `min(292px, calc(100vw - 31px))` on mobile. Render a gold triangle and vertical `OPEN DOCS`.

- [ ] **Step 6: Run focused tests and build**

Run: `npm test -- --run test/landing/landing-page.test.ts && npm run build`

Expected: PASS and a generated `/codeArbiter/` splash.

- [ ] **Step 7: Commit the navigation slice**

Commit message: `feat(site): add persistent splash docs rail`

### Task 3: Eliminate the hero seam and lock the background layer

**Files:**
- Modify: `site/src/styles/landing.css`
- Modify: `site/test/landing/landing-page.test.ts`

**Interfaces:**
- Produces: `.ca-landing::before` fixed atmosphere with no repeated image edge.

- [ ] **Step 1: Strengthen the failing background contract**

Assert `.ca-landing::before` has `position: fixed`, `background-repeat: no-repeat`, `background-size: cover`, pointer-events disabled, and a mobile fallback under an explicit media query.

- [ ] **Step 2: Run the focused test and record RED**

Run: `npm test -- --run test/landing/landing-page.test.ts`

Expected: failure on one or more missing seam/mobile declarations.

- [ ] **Step 3: Implement the fixed layer**

Keep the art on one fixed pseudo-element spanning the viewport. Do not split it across hero columns. Use an opaque base color behind it and a mobile fallback that avoids `background-attachment: fixed`.

- [ ] **Step 4: Run landing tests**

Run: `npm test -- --run test/landing/landing-page.test.ts`

Expected: PASS.

- [ ] **Step 5: Commit the background slice**

Commit message: `fix(site): stabilize the landing atmosphere`

### Task 4: Establish and enforce the professional diagram contract

**Files:**
- Create: `site/scripts/diagram-audit.ts`
- Modify: `site/package.json`
- Modify: `site/test/generator/diagrams.test.ts`
- Modify: `site/src/styles/design-system.css`
- Modify: `site/src/styles/theme.css`
- Modify: `site/public/diagrams/gate-model.svg`

**Interfaces:**
- Produces: `auditDiagram(svg: string, filename: string): string[]`.
- Produces: `npm run audit:diagrams`.
- Establishes the shared SVG token contract used by Task 5.

- [ ] **Step 1: Add failing diagram-contract tests**

For all fifteen SVGs, assert:

```ts
expect(svg).toMatch(/<title\b/);
expect(svg).toMatch(/<desc\b/);
expect(svg).toMatch(/viewBox=/);
expect(auditDiagram(svg, name)).toEqual([]);
```

The audit reports disallowed font families, text below `12px`, prose below `14px` unless marked `data-label-kind="annotation"`, fuzzy filters, and colors outside the approved palette.

- [ ] **Step 2: Run diagram tests and verify RED**

Run: `npm test -- --run test/generator/diagrams.test.ts`

Expected: current SVG family fails the shared contract.

- [ ] **Step 3: Implement the audit utility and script**

Export a pure parser/checker for tests and a CLI that prints `filename: violation` lines and exits nonzero on violations.

- [ ] **Step 4: Add diagram tokens and mobile overflow rules**

Document palette, font, stroke, node, and spacing values in `design-system.css`; retain local overflow on `.ca-diagram` without page-level horizontal scrolling.

- [ ] **Step 5: Redraw `gate-model.svg` as the calibration asset**

Use matched soft/hard halves, readable labels, integrated outcomes, and no disconnected hard-stop badge. Preserve accurate title/description and page alt text.

- [ ] **Step 6: Run the gate-model contract**

Run: `npm test -- --run test/generator/diagrams.test.ts`

Expected: only the remaining fourteen legacy diagrams fail.

- [ ] **Step 7: Commit the contract and calibration asset**

Commit message: `feat(site): establish the operational diagram system`

### Task 5: Redraw the remaining diagram family

**Files:**
- Modify: `site/public/diagrams/activation-states.svg`
- Modify: `site/public/diagrams/commit-gate-phases.svg`
- Modify: `site/public/diagrams/core-fanout.svg`
- Modify: `site/public/diagrams/four-tier-map.svg`
- Modify: `site/public/diagrams/lane-add-dep.svg`
- Modify: `site/public/diagrams/lane-adr.svg`
- Modify: `site/public/diagrams/lane-feature.svg`
- Modify: `site/public/diagrams/lane-flow.svg`
- Modify: `site/public/diagrams/lane-opt-in.svg`
- Modify: `site/public/diagrams/lane-release.svg`
- Modify: `site/public/diagrams/lane-sprint.svg`
- Modify: `site/public/diagrams/provenance-drift-flow.svg`
- Modify: `site/public/diagrams/sandbox-boundary.svg`
- Modify: `site/public/diagrams/two-axis-model.svg`
- Modify: page captions/alt text only where the redraw changes explanatory scope.

**Interfaces:**
- Consumes: Task 4 diagram tokens and `auditDiagram`.
- Produces: a complete fifteen-SVG family passing the same contract.

- [ ] **Step 1: Redraw shared lane-family diagrams**

Use one lane template for feature, sprint, ADR, release, opt-in, and dependency flows. Keep command-specific phases and gates sourced from the owning docs.

- [ ] **Step 2: Run the diagram audit**

Run: `npm run audit:diagrams`

Expected: lane-family files pass; remaining files are listed.

- [ ] **Step 3: Redraw state/system diagrams**

Redraw activation states, core fan-out, four-tier map, provenance drift, sandbox boundary, and two-axis model with shared nodes and arrows.

- [ ] **Step 4: Redraw pipeline/overview diagrams**

Redraw commit-gate phases and lane-flow using the same spacing and status language.

- [ ] **Step 5: Run diagram, link, type, and build verification**

Run:

```powershell
npm run audit:diagrams
npm test -- --run test/generator/diagrams.test.ts test/generator/diagram-href-convention.test.ts
npm run typecheck
npm run build
npm run link-audit
```

Expected: all commands PASS.

- [ ] **Step 6: Commit the complete diagram family**

Commit message: `feat(site): redraw the operational diagram family`

### Task 6: Audit every authored and generated page for task usefulness

**Files:**
- Modify: `site/test/content/documentation-presentation.test.ts`
- Modify: `site/test/content/learning-contract.test.ts`
- Modify: authored files under `site/src/content/docs/` that fail the page contract.
- Modify: `site/scripts/generator/render-command-page.ts`
- Modify: `site/scripts/generator/render-skill-page.ts`
- Modify: `site/scripts/generator/render-agent-page.ts`
- Modify: matching generator tests and typed data only when a generated gap exists.

**Interfaces:**
- Produces: authored pages covering what/when/how/verify/recover/next as applicable.
- Produces: generated reference pages that expose only source-backed purpose, invocation, gates, state, output, failures, relations, and provenance.

- [ ] **Step 1: Add page-contract inventory tests**

Build an explicit authored-page inventory and assert each guide has an invocation or configuration section, verification section, recovery/troubleshooting guidance, and next-step link where applicable. Add focused regressions for gated lanes and checkpoints.

- [ ] **Step 2: Run content tests and record the failing page list**

Run: `npm test -- --run test/content/documentation-presentation.test.ts test/content/learning-contract.test.ts`

Expected: RED with exact deficient pages.

- [ ] **Step 3: Repair authored pages in coherent groups**

Edit source Markdown/MDX only. Do not insert boilerplate headings when a page's concept type needs a different structure; satisfy the reader questions in context.

- [ ] **Step 4: Add generated-page contract tests**

For command, skill, and agent renderers, assert source-backed orientation, invocation/usage, phases or responsibilities, stop conditions when present, related docs, and source revision.

- [ ] **Step 5: Improve generator data and templates**

Change extraction/rendering rather than generated output. Unsupported source fields are omitted explicitly; no content is inferred.

- [ ] **Step 6: Regenerate and verify determinism**

Run:

```powershell
npm run gen
git diff --exit-code -- site/src/generated
npm test -- --run test/generator
```

If the first generation intentionally changes tracked output, review it, run `npm run gen` a second time, and require the second run to be clean.

- [ ] **Step 7: Run all site tests and commit**

Run: `npm test`

Commit message: `docs(site): complete the novice-to-power-user manual`

### Task 7: Validate runtime evidence and synchronize the README

**Files:**
- Modify: `site/test/landing/landing-page.test.ts`
- Modify: `site/src/assets/proof/hook-proof.json` and media only if recapture is required.
- Modify: `README.md`
- Modify: `docs/readme-hero.webp` only if the existing art no longer reflects the historic gate identity.
- Modify: `site/test/content/readme-professional.test.ts`

**Interfaces:**
- Consumes: final site navigation names, brand, learning path, and host claims.
- Produces: a concise GitHub entry point matching the verified site.

- [ ] **Step 1: Verify hook-proof provenance against the current shipped hook**

Run: `npm test -- --run test/landing/landing-page.test.ts`

If the digest fails, run `npm run capture:proof`, inspect the exact invocation data, and rerun the test. Never hand-edit proof results.

- [ ] **Step 2: Add failing README synchronization assertions**

Assert the historic gate identity, current host syntax, install-to-proof path, final navigation labels, learning path, and source-backed claims. Keep the detailed catalog collapsible.

- [ ] **Step 3: Rewrite the README as an adoption surface**

Lead with what codeArbiter does, route newcomers through choose/install/quickstart/learn, summarize enforcement and repository-owned state, distinguish hosts, and link rather than duplicate reference detail.

- [ ] **Step 4: Update README art only if required**

If updated, use repository-local rendered art derived from the approved gate system and verify GitHub-compatible dimensions and file size.

- [ ] **Step 5: Run README and landing proof tests**

Run: `npm test -- --run test/content/readme-professional.test.ts test/landing/landing-page.test.ts`

Expected: PASS.

- [ ] **Step 6: Commit the README/media slice**

Commit message: `docs: align the repository entry point with the site`

### Task 8: Full verification, review, and draft PR refresh

**Files:**
- Modify only files required by verified findings.

**Interfaces:**
- Produces: exact-head local evidence and an updated draft pull request.

- [ ] **Step 1: Run the full verification suite**

Run:

```powershell
npm test
npm run typecheck
npm run coverage
npm run build
npm run link-audit
npm run audit:diagrams
git diff --check
```

Expected: all commands PASS; coverage does not fall below the repository thresholds.

- [ ] **Step 2: Inspect representative built pages at target viewports**

Use the local site at `/codeArbiter/` and inspect `1440x900`, `1024x768`, and `390x844` for splash top/mid-scroll/drawer-open, header, rail, representative authored/generated pages, and all diagrams.

- [ ] **Step 3: Run the repository review workflow**

Review the exact diff for accessibility, correctness, security, source provenance, and visual quality. Fix every blocking finding and rerun affected tests.

- [ ] **Step 4: Commit any verified follow-up fixes**

Commit message: `fix(site): close documentation review findings`

- [ ] **Step 5: Push and refresh the existing draft pull request**

Push `codex/docs-first-class-site`, verify the remote head matches local HEAD, update the draft PR body with verification evidence, and leave it unmerged.
