# Site browser publication gate

**Status:** APPROVED by the user on 2026-09-15; hosted runtime amended by explicit user approval on 2026-09-15

**Governs:** site/package.json, site/package-lock.json, site/playwright.config.ts, site/test/browser/**, .github/workflows/docs.yml, .github/scripts/test_ci_impact.py

## Problem

The documentation publication pipeline can ship navigation, search, keyboard-focus, or responsive-overflow defects because it validates source, unit behavior, links, and the static build without exercising the production output in a real browser. Contributors should receive that proof from the public repository's GitHub-hosted CI rather than running an exhaustive browser matrix on their own machines.

## Approach

Adopt exact `@playwright/test@1.63.0` as a site development dependency and run one Chrome project against the already-built Astro output on loopback. The existing GitHub-hosted docs build job will record and use the Chrome already provided by GitHub's Ubuntu runner, execute the browser suite after `npm run build` and before artifact upload, and therefore block Pages publication without adding deployment authority to pull-request code or downloading browser executables.

This adds a reviewed npm dependency but deliberately uses the browser already maintained on the GitHub runner. It avoids both Playwright's additional Chromium/headless-shell/FFmpeg/Ubuntu-library acquisition and a bespoke Chrome DevTools Protocol harness. A raw protocol client would avoid the package while creating custom synchronization, locator, browser-discovery, and failure-reporting code that is more fragile than the product behavior being tested; Vitest Browser would still require a browser provider and would blur the current unit-versus-publication boundary.

## Scope

- Add one production-browser test surface for the built documentation site.
- Exercise representative global navigation, Pagefind search lifecycle, keyboard focus, and desktop/compact horizontal overflow.
- Run the browser gate on GitHub-hosted pull-request and main publication workflows so failure blocks Pages deployment.
- Keep local validation impact-bounded and leave exhaustive browser execution to GitHub-hosted CI.
- Preserve fork-safe read-only pull-request permissions, existing Pagefind/static architecture, native search semantics, stable routes, Academy content, and explicit evidence limits.
- Review and pin the browser dependency and generated lockfile graph before adoption.

Out of scope: a multi-browser or operating-system matrix; screenshots as acceptance; live-production mutation; screen-reader certification; axe or other accessibility-engine adoption; forced-colors, zoom, print, glare, visual-regression, or performance measurement; comprehensive WEB-035 failure-mode remediation; changes to search ranking, navigation design, Academy content, public routes, releases, or tags.

## Decided parameters

- Pin `@playwright/test` and its resolved graph exactly; use only the approved npm registry.
- Use the Chrome already provided by GitHub's `ubuntu-latest` runner through Playwright's `chrome` channel; print its observed version in the job log. Do not download Playwright browsers, FFmpeg helpers, or operating-system dependencies, and do not claim an exact Chrome version, Firefox, WebKit, Windows, macOS, or real-device coverage.
- Treat the GitHub runner image and its maintained Chrome installation as the hosted executable trust boundary. The npm lock and SRI bind Playwright's packages, not the runner browser; record that limitation explicitly and never make browser installation an automatic local prerequisite.
- Test the local production build at `127.0.0.1`, never the mutable public site, so the result is bound to the PR or main checkout under test.
- Use 1440x900 and 390x844 as the initial desktop and compact viewports.
- Prefer role, label, heading, and canonical-route locators over CSS implementation selectors.
- Run the browser command after the existing build and before Pages artifact upload. The existing deploy job continues to need the build and site-check jobs and receives no new pull-request credentials.
- Keep the local contributor contract impact-bounded: focused browser execution is available, but the commit gate does not require a contributor to replay the hosted browser suite or repository matrix.
- Retain traces only for failed CI attempts; do not commit screenshots or golden pixels.
- Treat unavailable or unexecuted accessibility, visual, performance, device, or browser cells as explicit gaps rather than inferred passes.

## Acceptance criteria

1. `AC-01`: With the production site already built, one Playwright command starts that exact output on loopback, loads a representative documentation route, and observes its expected level-one heading; startup failure or a missing heading makes the command nonzero.
2. `AC-02`: From a representative page, keyboard interaction opens the labelled documentation search surface, Escape closes it and returns focus to its opener, and a representative global-navigation link reaches its canonical route; a missing label, lost focus, or wrong route fails the test.
3. `AC-03`: The Pagefind-backed search combobox accepts a stable query, exposes keyboard-reachable results, and Enter reaches the expected result route; after client navigation, reopening search and clearing or escaping removes stale visible results without duplicated shortcut behavior.
4. `AC-04`: At both 1440x900 and 390x844, the representative Academy overview plus the search interaction complete with `scrollWidth <= clientWidth`; either viewport overflowing horizontally fails the test.
5. `AC-05`: A structural workflow regression test proves the docs workflow records and uses GitHub runner-provided Chrome without any Playwright browser, FFmpeg, or operating-system dependency download, runs the browser command after the production build and before Pages artifact upload, and preserves an execution dependency that prevents upload/deploy after browser failure.
6. `AC-06`: A structural policy regression test proves pull-request jobs remain `contents: read`, Pages and OIDC write permissions remain scoped to deployment, no local commit-gate command or automatic local setup path mandates the browser suite or a browser download, and the checked-in test/config wording identifies the Chrome-only local-build and runner-image evidence boundaries without claiming excluded proof or an exact hosted browser version.

## Open questions

None. CONFIRM-05 concerns Feature Forge promotion and is unrelated to this feature.

## Completeness check

The mechanical uncovered-intent check returned empty. If every criterion passed and nothing else changed, no in-scope behavior would remain broken: broader WEB-035 failure injection and the screen-reader, forced-color, zoom, visual, multi-browser, device, and performance cells remain explicitly out of scope and visible for later checkpoints.
