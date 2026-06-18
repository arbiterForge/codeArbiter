# Plan — farm feature-forge fixes (#90, #91, #93)

Spec: `.codearbiter/specs/farm-feature-forge-fixes.md`. Each task is test-first via `tdd`.
Status ledger: `PENDING` → `RED` (failing test in) → `GREEN` → `ACCEPTED` (reviewed + verified).
All paths relative to repo root. Tools cwd = `plugins/ca/tools/`.

## Landing structure

**One combined PR** (user decision at the gate, 2026-06-18): single branch
`fix/farm-feature-forge-90-91-93` off `main`, closing #90, #91, and #93. Zero `farm.js` merge friction,
one review, one rebuild of the bundle at the end. The per-branch headings below are kept as logical
task groups; all land in the one branch/PR.

---

## Branch 1 — #90 stale base URL  (`fix/farm-stale-base-url`)

- **T90-1** `[PENDING]` — RED: unit test in `farm.unit.test.ts` asserting the resolved default base URL is `https://opencode.ai/zen/v1`. Files: `plugins/ca/tools/farm.unit.test.ts`. Verify: test fails (still old URL). Maps: AC-90.1.
- **T90-2** `[PENDING]` — GREEN: change `ENV.defaultApiBaseUrl` default to `https://opencode.ai/zen/v1`. Files: `plugins/ca/tools/farm.ts`. Verify: T90-1 green. Maps: AC-90.1.
- **T90-3** `[PENDING]` — RED: unit test driving a 2xx-with-non-JSON-body response through `callApi` (export `callApi` or extract `parseApiResponse`), asserting an actionable error naming `FARM_API_BASE_URL`. Files: `farm.unit.test.ts`. Verify: fails. Maps: AC-90.2.
- **T90-4** `[PENDING]` — GREEN: in `callApi`, detect a non-JSON 2xx body and return the actionable message; keep diagnostics-to-stderr behavior. Files: `farm.ts`. Verify: T90-3 green, suite green. Maps: AC-90.2.
- **T90-5** `[PENDING]` — docs: update `plugins/ca/includes/farm.md` default URL; no `api.opencode.ai/v1` left. Files: `plugins/ca/includes/farm.md`. Verify: grep clean. Maps: AC-90.3.
- **T90-6** `[PENDING]` — build + land: `npm run typecheck && npm test && npm run build`; assert `git diff --quiet -- farm.js`; commit-gate; open PR closing #90. Maps: AC-90.4.

## Branch 2 — #91 CRLF drift  (`fix/farm-crlf-drift`)

- **T91-1** `[PENDING]` — RED: unit test for an exported `checkDrift(cwd, allowed, gitRunner)` — stub git returns an out-of-scope path on `stdout` and a `warning: ... LF will be replaced by CRLF ...` on `stderr` (also in merged `out`); assert only the real out-of-scope path returns and the warning never does; second case asserts in-scope-only + warning → `[]`. Files: `farm.unit.test.ts`. Verify: fails (checkDrift not exported / parses merged out). Maps: AC-91.1–91.3.
- **T91-2** `[PENDING]` — GREEN: `run()` returns `{ code, out, stdout, stderr }` (`out` stays merged for back-compat); export `checkDrift` with an injectable git runner defaulting to real `git`, parsing `stdout` only. Files: `farm.ts`. Verify: T91-1 green, full suite green (back-compat consumers unaffected). Maps: AC-91.1–91.3.
- **T91-3** `[PENDING]` — build + land: typecheck/test/build, `git diff --quiet -- farm.js`; commit-gate; open PR closing #91. Maps: AC-91.4.

## Branch 3 — #93 entitlement pre-check  (`feat/farm-entitlement-precheck`)

- **T93-1** `[PENDING]` — RED: unit test for exported `screenEntitlements(models, probeFn, opts)` — stub probe returns 401 for one model, 200 for another; assert 401 → skipped set with entitlement note, 200 → survivor; assert a probe exceeding the cap is handled as a drop, not a hang. Files: `farm.unit.test.ts`. Verify: fails (function absent). Maps: AC-93.1–93.4.
- **T93-2** `[PENDING]` — GREEN: implement `screenEntitlements` (one minimal `/chat/completions` probe per candidate, per-candidate wall-clock cap via new env knob defaulting ≤ `FARM_REQUEST_TIMEOUT_MS`, 401 → skip with distinct note). Files: `farm.ts`. Verify: T93-1 green. Maps: AC-93.1, 93.3, 93.4.
- **T93-3** `[PENDING]` — GREEN: wire `screenEntitlements` into `runCanary` before the candidate loop; include skipped entries distinctly in `canary-report.json` and the printed summary. Files: `farm.ts`. Verify: suite green; report-shape assertion. Maps: AC-93.2.
- **T93-4** `[PENDING]` — build + land: typecheck/test/build, `git diff --quiet -- farm.js`; commit-gate; open PR closing #93. Maps: AC-93.5.

---

## Execution order

One branch off `main`. Execute groups 1 → 2 → 3 sequentially (shared file `farm.ts`), each task
test-first (RED → GREEN). The build/land steps (T90-6, T91-3, T93-4) collapse into a SINGLE final
land: one `npm run typecheck && npm test && npm run build` + `git diff --quiet -- farm.js`, one
commit-gate (or grouped commits per issue), one PR closing #90/#91/#93. Morning summary lists the one
PR + its merge decision.

## Coverage check

Every AC maps to ≥1 task: 90.1→T90-1/2, 90.2→T90-3/4, 90.3→T90-5, 90.4→T90-6; 91.1-3→T91-1/2,
91.4→T91-3; 93.1-4→T93-1/2/3, 93.5→T93-4. ✔
