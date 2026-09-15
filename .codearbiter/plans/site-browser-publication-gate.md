# Site browser publication gate plan

**Spec:** `.codearbiter/specs/site-browser-publication-gate.md` (APPROVED 2026-09-15)

## Acceptance-criterion ledger

- `AC-01`: With the production site already built, one Playwright command starts that exact output on loopback, loads a representative documentation route, and observes its expected level-one heading; startup failure or a missing heading makes the command nonzero.
- `AC-02`: From a representative page, keyboard interaction opens the labelled documentation search surface, Escape closes it and returns focus to its opener, and a representative global-navigation link reaches its canonical route; a missing label, lost focus, or wrong route fails the test.
- `AC-03`: The Pagefind-backed search combobox accepts a stable query, exposes keyboard-reachable results, and Enter reaches the expected result route; after client navigation, reopening search and clearing or escaping removes stale visible results without duplicated shortcut behavior.
- `AC-04`: At both 1440x900 and 390x844, the representative Academy overview plus the search interaction complete with `scrollWidth <= clientWidth`; either viewport overflowing horizontally fails the test.
- `AC-05`: A structural workflow regression test proves the docs workflow records and uses GitHub runner-provided Chrome without any Playwright browser, FFmpeg, or operating-system dependency download, runs the browser command after the production build and before Pages artifact upload, and preserves an execution dependency that prevents upload/deploy after browser failure.
- `AC-06`: A structural policy regression test proves pull-request jobs remain `contents: read`, Pages and OIDC write permissions remain scoped to deployment, no local commit-gate command or automatic local setup path mandates the browser suite or a browser download, and the checked-in test/config wording identifies the Chrome-only local-build and runner-image evidence boundaries without claiming excluded proof or an exact hosted browser version.

Mechanical uncovered-intent result: empty.

Negative completeness judgment: if all six criteria pass, no in-scope publication-gate behavior remains broken. Broader WEB-035 failure injection and screen-reader, forced-color, zoom, visual, multi-browser, device, and performance evidence remain explicit later work, not hidden omissions.

## Ordered tasks

| id | path(s) | verification | maps-to | covers | depends-on | status |
| --- | --- | --- | --- | --- | --- | --- |
| T-01 | `site/package.json`; `site/package-lock.json`; `site/playwright.config.ts`; `.github/scripts/test_ci_impact.py` | `python .github/scripts/test_ci_impact.py` passes its browser dependency/config contract and `npm --prefix site ls --depth=2 @playwright/test playwright playwright-core` reports only exact 1.63.0 packages | TDD red/green for exact reviewed dependency, loopback production server, Chrome-only configuration, and candid local/hosted runner-image boundaries | AC-01, AC-05, AC-06 | none | ACCEPTED |
| T-02 | `site/test/browser/publication.spec.ts`; `site/src/components/Search.astro`; `site/package.json`; `site/playwright.config.ts`; `.github/scripts/test_ci_impact.py` | `npm --prefix site run build` followed by the focused `npm --prefix site run test:browser` passes the heading, keyboard search, focus restoration, canonical navigation, Pagefind result, client-navigation reset, and shortcut uniqueness scenarios | TDD red/green plus obligation verification for production-browser behavior, including an owned foreground preview in agent environments and the minimal focus-restoration correction proven necessary by the unchanged browser assertions | AC-01, AC-02, AC-03 | T-01 | ACCEPTED |
| T-03 | `site/test/browser/publication.spec.ts`; `.github/scripts/test_ci_impact.py` | The focused browser command passes Academy and search horizontal-overflow assertions at 1440x900 and 390x844, and `python .github/scripts/test_ci_impact.py` proves both viewports remain declared | TDD red/green plus obligation verification for responsive geometry | AC-04 | T-02 | ACCEPTED |
| T-04 | `.github/workflows/docs.yml`; `.github/scripts/test_ci_impact.py`; `site/package.json`; `site/playwright.config.ts`; `site/tsconfig.json` | `python .github/scripts/test_ci_impact.py` passes the exact workflow ordering, failure edge, permissions, runner-provided Chrome version evidence, zero browser/FFmpeg/OS-library download commands, and local-compute contract; `npm --prefix site run typecheck` passes with the Playwright config inside its checked scope | TDD red/green plus lint/typecheck for hosted publication wiring | AC-05, AC-06 | T-01, T-02, T-03 | ACCEPTED |

## Dependency order and MVP slice

`T-01 -> T-02 -> T-03 -> T-04` is acyclic. The complete contiguous set T-01 through T-04 is the MVP slice: the browser contract without the workflow edge cannot block publication, and the workflow edge without the behavioral contract proves nothing useful.

## Bijection proof

- Every criterion is covered: AC-01 by T-01/T-02; AC-02 and AC-03 by T-02; AC-04 by T-03; AC-05 and AC-06 by T-01/T-04.
- Every task advances at least one criterion; no task is administrative-only or unrelated.
- No `[NEEDS-TRIAGE]` item was introduced by plan decomposition.

## Accepted-batch evidence

- Controller fresh verification on Windows: structural 75/75, browser 5/5 using installed Chrome with no browser download, typecheck pass, production build 155 pages and 172 Pagefind files, link audit 26,333 internal links, production audit zero vulnerabilities, and clean diff formatting.
- Final combined-diff reviews: dependency PASS, security PASS, coverage/spec-compliance PASS, each with zero unresolved findings. The original Playwright-managed FFmpeg blocker was eliminated by the user-approved runner-provided Chrome method; no override or audit-log rewrite occurred.
- Numeric site coverage remains bounded to `site/scripts/**`, which this diff does not change. The prior exact-base Windows measurement was 78.79% lines and 79.45% branches; this is baseline evidence, not a current rerun. `Search.astro` has direct production-browser proof and `.github/scripts/*.py` uses the documented no-tooling exemption.
- `[NEEDS-TRIAGE]`: the pre-existing Vitest 4.1.9 moderate advisory should receive a separately reviewed coordinated Vitest/coverage update; it is not introduced or selected by this checkpoint.
