# First-Class Documentation Site: Navigation, Brand, Diagrams, and Learning Quality

**Date:** 2026-07-30

**Status:** Approved design, awaiting written-spec review

**Branch:** `codex/docs-first-class-site`
**Deployment target:** GitHub Pages under `/codeArbiter/`

## Intent

The documentation site must take a reader from no prior codeArbiter knowledge to confident power-user operation. It must also present codeArbiter with the visual and editorial finish expected of a serious open-source infrastructure project.

This phase builds on the existing first-class landing page and learning path. It closes the remaining gaps in navigation, brand execution, diagram quality, page-level teaching coverage, generated reference usefulness, and README consistency.

## Goals

1. Give returning visitors immediate access to the complete documentation navigation from the splash page.
2. Restore the historic gate/commit-line mark as the core codeArbiter identity and finish it as a coherent logo system.
3. Redraw every operational SVG under one professional diagram system.
4. Audit every authored and generated page for task-level usefulness.
5. Keep every demonstration honest: runtime media must come from real product behavior, not an invented terminal sequence.
6. Bring the repository README into visual and editorial alignment after the site is complete.
7. Preserve the existing base-path-safe build, source-backed generator, accessibility, and verification guarantees.

## Non-goals

- No paid services, stock subscriptions, or externally hosted commercial assets.
- No change to codeArbiter's product behavior or governance semantics.
- No replacement documentation framework.
- No decorative rasterization of operational diagrams that need precise labels, accessibility, or future edits.
- No fabricated GIF, video, screenshot, or terminal transcript presented as product evidence.
- No merge to the default branch. Work remains on the isolated branch and draft pull request.

## Approved Design Decisions

### 1. Splash-page documentation rail

The splash page receives a persistent collapsed rail on the left edge below the site header.

- Desktop collapsed width: `38px`.
- Narrow-screen collapsed width: `31px`.
- The collapsed rail contains a gold right-pointing triangle and vertical `OPEN DOCS` label.
- Activating it opens an overlay drawer containing the real Starlight sidebar tree.
- The logo remains an ordinary home link. It does not double as a menu control.
- The rail appears only on the splash page. Normal documentation pages retain the existing desktop sidebar and mobile menu behavior.

The component must reuse `Astro.locals.starlightRoute.sidebar` through the existing `SidebarSublist` rendering path. It must not maintain a second navigation tree.

The open drawer uses:

- a desktop width of `292px`;
- a mobile width of `min(292px, calc(100vw - 31px))`;
- a backdrop;
- document scroll lock;
- Escape-to-close;
- focus trapping;
- focus restoration to the opener;
- `aria-expanded` and `aria-controls`;
- close-on-backdrop and close-button behavior.

If the generated sidebar is unavailable, the rail must still offer a base-path-safe link to **What Is codeArbiter**. A no-script fallback must expose the same direct link.

### 2. Historic gate brand system

The historical mark recovered from the repository is the fixed brand foundation. Its meaning is:

1. a hollow node represents an unproven change;
2. the horizontal segment represents the commit/work line;
3. twin posts and a beam form the governed gate;
4. the filled gold node represents a proven decision after the gate.

The mark already combines code and arbitration through one construction. It must not be replaced with an A monogram, gavel, courthouse, scales, shield, or literal code/legal mash-up.

The silhouette and element arrangement remain stable. One approved semantic adjustment is made:

- replace the small filled downward pivot triangle above the beam with an open gold terminal-prompt chevron pointing downward into the gate.

The production redraw may correct optical alignment, intervals, terminal shapes, stroke hierarchy, and small-size overshoot. It may use one restrained gold highlight in the full-size color mark, but must remove the fuzzy glow from small variants.

The delivered brand system includes:

- full horizontal wordmark;
- standalone icon;
- monochrome mark;
- favicon;
- reduced-detail `16px` master;
- light-on-dark color master used by the site.

The wordmark remains `codeArbiter`, with `code` in the light neutral and `Arbiter` in the gold accent. Logo and wordmark must read as one cohesive brand unit.

### 3. Fixed landing atmosphere

The landing page's generated gate artwork is atmosphere, not operational evidence. It remains visually behind the page while the foreground content scrolls over it.

Implementation must avoid the previously observed vertical seam/disturbance. The artwork must:

- cover the intended viewport without a central edge or repeated tile;
- remain fixed on desktop;
- use a mobile-safe fixed-layer or non-janky fallback where `background-attachment: fixed` is unreliable;
- preserve text contrast;
- respect reduced-motion preferences;
- never obscure interactive content.

### 4. Diagram system and complete redraw

SVG remains the correct medium for operational explanations because it provides precise geometry, sharp labels, accessibility, responsive behavior, and maintainable source.

Every current SVG is reviewed and redrawn as needed. No file survives merely because it already exists:

1. `activation-states.svg`
2. `commit-gate-phases.svg`
3. `core-fanout.svg`
4. `four-tier-map.svg`
5. `gate-model.svg`
6. `lane-add-dep.svg`
7. `lane-adr.svg`
8. `lane-feature.svg`
9. `lane-flow.svg`
10. `lane-opt-in.svg`
11. `lane-release.svg`
12. `lane-sprint.svg`
13. `provenance-drift-flow.svg`
14. `sandbox-boundary.svg`
15. `two-axis-model.svg`

`statusline.png` is runtime UI evidence rather than an operational SVG. It is audited separately for currency and provenance.

#### Diagram visual contract

- One shared near-black canvas, neutral text palette, and semantic accent palette.
- Gold indicates an allowed, selected, or governed path.
- Red is reserved for a real hard stop or security block.
- Slate indicates neutral structure and advisory context.
- A single type family is used throughout, drawing from the site's local Manrope and JetBrains Mono assets.
- Prose labels are no smaller than `14px` at the diagram's normal desktop rendering size.
- Monospace annotations are no smaller than `12px` at normal rendering size.
- Primary strokes use a shared scale; secondary dividers and leaders use a distinct shared scale.
- Nodes, cards, arrows, margins, and gutters align to an explicit spacing grid.
- Repeated elements use identical dimensions unless semantic weight requires a documented difference.
- Arrowheads, radii, labels, and status badges remain consistent across the family.
- Captions complement the visual; they do not repeat labels already visible in the SVG.
- Empty space must be intentional and balanced. Disconnected badges, unexplained dead zones, accidental asymmetry, and arbitrary scale changes fail review.
- Every diagram must remain understandable at its normal content-column width and usable through horizontal overflow on small screens when shrinking would make labels unreadable.
- Every image reference keeps an accurate alt description. Complex figures may add an adjacent prose explanation when alt text alone would become unwieldy.

`gate-model.svg` is the calibration diagram for the system. Its soft and hard gate halves must use matched geometry, explicit continuation/stop outcomes, and an integrated hard-stop statement rather than a disconnected badge.

### 5. Page-level teaching contract

Every documentation page is audited from the perspective of a reader encountering that part of codeArbiter for the first time.

An authored concept or guide page must make the following discoverable where applicable:

- what the mechanism or workflow is;
- when the reader should use it;
- the exact invocation or configuration;
- prerequisites and hard gates;
- what happens step by step;
- what success looks like;
- how to verify the result;
- common failure modes and recovery;
- the next relevant page or workflow.

The structure can vary when a page is conceptual rather than procedural, but no page may rely on unexplained internal vocabulary. Terms link to the glossary or their owning concept page.

The review includes every authored page under `site/src/content/docs/`, including the previously reported weak/broken **The Gated-Lane Model** and **Checkpoints** destinations.

### 6. Generated reference contract

Generated command, skill, agent, and hook pages remain source-backed. Hand editing generated output is prohibited.

When a generated page does not teach the reader how to use or interpret that surface, the generator or its source-extraction model must be improved. Generated pages should expose, where the source supports it:

- purpose;
- invocation;
- arguments;
- lane or ownership;
- phases and gates;
- state read and written;
- expected output;
- failure/stop conditions;
- related commands and concepts;
- provenance back to the source file and revision.

The generator must preserve deterministic output and existing slug/base-path behavior.

### 7. Real demonstrations only

Operational media is divided into two honest categories:

- **Conceptual art/diagram:** explicitly explanatory and not presented as a runtime capture.
- **Runtime evidence:** captured from a real invocation against the shipped code.

A GIF or training video is added only when the real workflow can be reproduced and recorded. Runtime media must carry enough adjacent context to identify:

- the command or interaction performed;
- the shipped code path exercised;
- capture date or source revision;
- the expected result;
- any limitation in what the recording proves.

The existing hook proof remains acceptable only if its checked-in proof data and media continue to match the shipped hook behavior. Invented terminal playback may be used only as a clearly labeled conceptual illustration, never as evidence.

### 8. README synchronization

The repository README is revised only after the site design and content audit stabilize.

It must:

- present the same value proposition and historic gate identity;
- provide a concise install-to-first-proof path;
- distinguish Claude Code, Codex, and Pi accurately;
- link to the learning path and generated reference;
- explain hard gates, repository-owned state, and auditability without duplicating entire docs pages;
- avoid claims not proven by the current repository;
- use repository-safe artwork that renders correctly on GitHub;
- reflect the final navigation names and current command syntax.

The README is an entry point, not a second documentation site.

## Component Boundaries

### `SplashDocsRail`

Owns the splash-only collapsed rail, drawer shell, open/close state, accessibility, and fallback link. It consumes the existing Starlight sidebar structure and delegates tree rendering to `SidebarSublist`.

### Brand assets

A shared SVG source defines the historical gate geometry. Wordmark, icon, monochrome, and favicon variants reuse that geometry rather than duplicating hand-tuned shapes across unrelated files.

### Diagram primitives

SVGs share a documented token vocabulary for color, typography, stroke, spacing, card geometry, arrowheads, and status treatment. The implementation may use a small local authoring helper or reusable SVG definitions if it keeps final assets deterministic and dependency-free.

### Generator

Source discovery/extraction remains separate from page rendering. Template changes operate on typed rendered-page data rather than parsing already-rendered Markdown.

## Interaction and Data Flow

1. Astro/Starlight produces the canonical sidebar tree.
2. Normal pages send that tree to the existing sidebar.
3. The splash page additionally sends the same tree to `SplashDocsRail`.
4. The rail's client behavior manages only presentation state; it does not fetch or construct navigation data.
5. Documentation generation reads source command/skill/agent/hook material, creates typed page data, renders Markdown, and creates the sidebar JSON before Astro starts.
6. Diagram and brand assets are built as static local assets and receive the `/codeArbiter/` base path through the existing asset pipeline or base-link transform.

## Failure Handling

- Missing sidebar generation degrades to a direct **What Is codeArbiter** link.
- Drawer script failure must not hide all documentation access.
- Focus and scroll state are restored even when navigation is cancelled.
- Asset links must remain base-path-safe locally and on GitHub Pages.
- Diagram overflow must be localized to its figure container; it must not create page-level horizontal scrolling.
- A generated page missing required source fields renders an explicit omission or omits the unsupported section; it must not invent content.
- Media whose provenance cannot be verified is removed or relabeled as conceptual.

## Verification

### Automated contracts

- Rail renders only on the splash page.
- Rail and drawer use the canonical sidebar entries.
- Drawer keyboard, focus, backdrop, scroll-lock, and ARIA behavior pass tests.
- No-script and missing-sidebar fallbacks resolve under `/codeArbiter/`.
- Historic gate masters contain the approved open downward chevron and preserve the six semantic elements.
- Diagram audit checks viewBox presence, approved font families, minimum label sizes, allowed palette, and prohibited fuzzy filters at reduced sizes.
- Every diagram filename referenced by content exists.
- Generated output remains deterministic.
- All internal links resolve.
- Favicon and hashed logo assets exist in the production build.
- Existing typecheck, unit, coverage, build, and link-audit suites remain green.

### Visual review

Capture and inspect at minimum:

- `1440x900` desktop;
- `1024x768` compact desktop/tablet;
- `390x844` mobile.

Review the splash at top, mid-scroll, and drawer-open states; the header wordmark; the rail; representative authored and generated pages; all fifteen diagrams; long tables; code blocks; and the README's GitHub rendering constraints.

Visual acceptance requires:

- no vertical hero seam;
- no clipped wordmark or rail label;
- no ambiguous navigation icon;
- no diagram label below the readability floor;
- no accidental horizontal page scroll;
- no misaligned repeated diagram elements;
- no broken or empty destination from the primary navigation;
- no decorative asset presented as runtime proof.

## Implementation Order

1. Add failing contracts for the brand, rail, diagram rules, base paths, and page-content requirements.
2. Restore and refine the historic gate brand system.
3. Implement the splash documentation rail and drawer.
4. Fix the landing background layer and verify the seam at target viewports.
5. Establish diagram tokens and redraw `gate-model.svg` as the calibration asset.
6. Redraw and review the remaining fourteen SVGs in coherent families.
7. Audit authored pages and repair content/navigation gaps.
8. Improve generator data/templates for any generated-page gaps.
9. Capture or validate only reproducible runtime media.
10. Synchronize and polish the README.
11. Run automated, visual, accessibility, and source/provenance verification.
12. Commit, push the isolated branch, and update the existing draft pull request without merging.

## Acceptance

The work is complete when a first-time reader can follow the site from orientation through a verified repository setup and onward to advanced operation; a returning reader can open the full docs navigation immediately from the splash; every diagram meets the shared visual contract; the historic gate identity is professionally executed and consistent; generated references explain how their surfaces are used; media claims are honest; the README matches the finished site; and all verification is green on the exact branch head.
