# Academy Front Door Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Turn `/academy/` into a generated, accessible front door that begins with the real Academy setup contract and invites a learner into its first lesson.

**Architecture:** Extend the pinned-source loader with Home setup data, then extend the Academy generator to expose that source-backed payload to one new Astro overview component. The component owns the Academy route’s only H1 and composes the setup path, start card, track inventory, and practice loop; scoped CSS supplies responsive hierarchy inside the existing Starlight shell.

**Tech Stack:** Astro 7, Starlight, TypeScript, Vitest, existing CodeArbiter design tokens. No new dependency.

**Spec:** `.codearbiter/specs/academy-front-door.md`

## Global Constraints

- Keep the existing Astro/Starlight CodeArbiter shell, navigation rail, search, dark tokens, and generated Academy lesson routes.
- Load the authoritative Home setup contract from the pinned Academy source; do not invent a hosted sandbox, completion tracking, account, or certificate state.
- Preserve `complete-these-five-setup-steps-before-f01` as the generated Academy overview anchor expected by F01.
- The overview has exactly one H1, one visually primary CTA to setup, keyboard-reachable controls, native `<details>`, 44px targets, and no horizontal overflow at 390px.
- No package, remote runtime service, Academy-source edit, or plugin command change.
- Verify with `npm --prefix site run typecheck`, `npm --prefix site run test`, `npm --prefix site run build`, and `npm --prefix site run link-audit`.

---

## File structure

| Path | Responsibility |
| --- | --- |
| `site/scripts/academy-source.ts` | Validate and load source-backed Home setup data alongside the public lesson inventory. |
| `site/scripts/academy-source.test.ts` | Build pinned-source fixtures and characterize valid/missing Home setup behavior. |
| `site/scripts/generate-academy.ts` | Generate typed Academy overview payload and MDX route that imports the overview component. |
| `site/scripts/generate-academy.test.ts` | Assert generated route, canonical lesson inventory, Home anchor, and payload shape. |
| `site/src/components/AcademyOverview.astro` | Render the hero, authoritative setup, first lesson, tracks, and practice loop from generated data. |
| `site/src/components/PageTitle.astro` | Give `/academy/` to `AcademyOverview` as the sole H1 owner. |
| `site/src/styles/academy.css` | Scope hierarchy, focus, details, and responsive Academy front-door layout. |

### Task 1: Load and validate Academy Home setup data

**Files:**
- Modify: `site/scripts/academy-source.ts`
- Modify: `site/scripts/academy-source.test.ts`

**Interfaces:**
- Produces `AcademySource.home` with source-backed title, ordered setup steps, and the fixed setup anchor.
- `loadAcademySource(root: string): AcademySource` rejects an absent or malformed Home document before generation.

- [ ] **Step 1: Write failing fixture tests for Home setup.**

  Add a fixture Home guide and assertions that loading exposes all five ordered setup steps and the required anchor.

  ```ts
  expect(source.home.anchor).toBe("complete-these-five-setup-steps-before-f01");
  expect(source.home.steps).toHaveLength(5);
  expect(source.home.steps[0]).toMatchObject({ title: "Create your practice fork" });
  ```

- [ ] **Step 2: Run the focused test and verify it fails.**

  Run: `npm --prefix site run test:academy-source`

  Expected: FAIL because `AcademySource.home` does not exist.

- [ ] **Step 3: Add the minimal typed loader contract.**

  Parse the pinned `academy/guides/home.md` format into an ordered five-step structure, reject malformed shape, and retain the static anchor as a validated contract value.

  ```ts
  export type AcademyHome = {
    title: string;
    anchor: "complete-these-five-setup-steps-before-f01";
    steps: Array<{ title: string; instruction: string }>;
  };
  ```

- [ ] **Step 4: Run focused source tests.**

  Run: `npm --prefix site run test:academy-source`

  Expected: PASS, including missing/malformed Home rejection coverage.

- [ ] **Step 5: Commit Task 1 through `$ca-commit`.**

  Stage only `site/scripts/academy-source.ts` and `site/scripts/academy-source.test.ts` after the full gate clears.

### Task 2: Generate a typed Academy overview route and inventory

**Files:**
- Modify: `site/scripts/generate-academy.ts`
- Modify: `site/scripts/generate-academy.test.ts`

**Interfaces:**
- Consumes `AcademySource.home` and `AcademySource.lessons`.
- Produces `academyContent.home`, track-groupable typed lesson data, and generated `/academy/` MDX importing `AcademyOverview`.

- [ ] **Step 1: Write failing generator tests.**

  Assert that generated `academy/index.mdx` imports the component, preserves the Home anchor, includes one canonical record for each public lesson, and exposes source-backed Home data in `academy-content.ts`.

  ```ts
  expect(indexPage).toContain('import AcademyOverview from "../../../components/AcademyOverview.astro";');
  expect(indexPage).toContain("<AcademyOverview />");
  expect(generatedContent).toContain('anchor: "complete-these-five-setup-steps-before-f01"');
  ```

- [ ] **Step 2: Run the focused generator test and verify it fails.**

  Run: `npm --prefix site exec vitest run scripts/generate-academy.test.ts`

  Expected: FAIL because the old index is a Markdown list.

- [ ] **Step 3: Implement minimal generation changes.**

  Extend the typed literal generator with Home data and make `renderIndex` emit only frontmatter plus the `AcademyOverview` import/component. Keep lesson page generation and sidebar ordering unchanged.

- [ ] **Step 4: Run focused generator and source tests.**

  Run: `npm --prefix site exec vitest run scripts/generate-academy.test.ts scripts/academy-source.test.ts`

  Expected: PASS.

- [ ] **Step 5: Commit Task 2 through `$ca-commit`.**

  Stage only the two generator files and their tests after the full gate clears.

### Task 3: Render the accessible Academy overview and route title ownership

**Files:**
- Create: `site/src/components/AcademyOverview.astro`
- Modify: `site/src/components/PageTitle.astro`
- Modify: `site/scripts/generate-academy.test.ts`

**Interfaces:**
- Consumes `academyContent.home` and `academyLessons` from `src/generated/academy-content.ts`.
- Produces one H1, a setup anchor, one primary setup CTA, secondary F01 links, track anchors, descriptive disclosure controls, and a visible all-lessons route.

- [ ] **Step 1: Add route-level expectations before markup.**

  Extend the generation/build-oriented test to assert the overview route imports the new component and retains no generated H1. Add a build-output check that `/academy/index.html` has one H1 and the required setup anchor.

  ```ts
  expect(academyHtml.match(/<h1/g)).toHaveLength(1);
  expect(academyHtml).toContain('id="complete-these-five-setup-steps-before-f01"');
  ```

- [ ] **Step 2: Run the target test and verify it fails.**

  Run: `npm --prefix site exec vitest run scripts/generate-academy.test.ts`

  Expected: FAIL because the component and route exception do not exist.

- [ ] **Step 3: Implement the component and suppress the stock Academy title/context.**

  `AcademyOverview` groups lessons by `track`, calculates total minutes from source-backed values, renders the five Home setup steps, and uses native `<details>` only for extra inventory. In `PageTitle.astro`, treat `id === "academy"` like the existing bespoke home route so it does not render a duplicate title or context card.

  ```astro
  <a class="academy-overview__primary" href="#complete-these-five-setup-steps-before-f01">
    Set up your practice fork
  </a>
  <details>
    <summary>Show {remainingLessons.length} more {trackLabel} lessons</summary>
    <!-- secondary lesson cards -->
  </details>
  ```

- [ ] **Step 4: Run typecheck and focused tests.**

  Run: `npm --prefix site run typecheck; npm --prefix site exec vitest run scripts/generate-academy.test.ts scripts/academy-source.test.ts`

  Expected: PASS.

- [ ] **Step 5: Commit Task 3 through `$ca-commit`.**

  Stage only the component, `PageTitle.astro`, and the changed generator test after the full gate clears.

### Task 4: Apply responsive hierarchy and perform live product verification

**Files:**
- Modify: `site/src/styles/academy.css`
- Modify: `site/scripts/generate-academy.test.ts` only if static assertion coverage is still missing

**Interfaces:**
- Consumes the semantic structure from `AcademyOverview.astro`.
- Produces desktop and 390px layouts with native shell cohesion, readable progress hierarchy, visible focus, 44px targets, and no horizontal overflow.

- [ ] **Step 1: Add failing structural assertions for required interaction hooks.**

  Assert that generated overview markup includes the setup anchor, exactly one primary CTA class, `View all lessons`, and descriptive native `<summary>` controls.

- [ ] **Step 2: Run focused test and verify it fails.**

  Run: `npm --prefix site exec vitest run scripts/generate-academy.test.ts`

  Expected: FAIL until the overview structure exposes every required hook.

- [ ] **Step 3: Add scoped Academy front-door CSS.**

  Use existing `--ca-*` tokens only. Make the setup and F01 start card visually dominant, use grid cards at desktop, one column at 390px, and style focus with an outline that remains visible on dark panels.

  ```css
  .academy-overview__primary,
  .academy-overview__lesson-link,
  .academy-overview summary {
    min-block-size: 2.75rem;
  }

  @media (max-width: 24.375rem) {
    .academy-overview__tracks { grid-template-columns: 1fr; }
  }
  ```

- [ ] **Step 4: Run full local verification.**

  Run: `npm --prefix site run typecheck; npm --prefix site run test; npm --prefix site run build; npm --prefix site run link-audit`

  Expected: all commands exit 0.

- [ ] **Step 5: Inspect rendered output at the two required widths.**

  At 1440px and 390px, verify one H1, logical heading order, one visually primary setup CTA, keyboard focus order, `<details>` state/name, 44px targets, `scrollWidth <= innerWidth`, and a reachable `View all lessons` affordance.

- [ ] **Step 6: Commit Task 4 through `$ca-commit`.**

  Stage only the scoped CSS and any required structural test after the full gate clears.

## Coverage self-review

- AC 1–4: Tasks 1–3 cover source-backed setup, one primary CTA, F01 placement, canonical inventory, and truthful practice copy.
- AC 5–7 and 11–12: Tasks 3–4 cover route H1 ownership, keyboard semantics, disclosure behavior, mobile/desktop widths, overflow, and returning-learner retrieval.
- AC 8: Tasks 1–2 reject incomplete Home and lesson data.
- AC 9–10: Task 4 runs the full static suite without adding dependencies.

Plan self-review: no unresolved placeholders, all generated-data interfaces are named in their producing task, and every spec acceptance criterion maps to at least one independently verifiable task.
