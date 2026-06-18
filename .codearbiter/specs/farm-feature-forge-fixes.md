# Sprint spec — farm feature-forge fixes (#90, #91, #93)

**Status:** awaiting approval (Phase 1 gate)
**Mode:** `/ca:sprint` (premium subagent path — NOT `--farm`; we are fixing the farm tool itself)
**Author attribution:** user (brennonhuff@gmail.com), 2026-06-18
**Surface:** `plugins/ca/tools/farm.ts` (+ rebuilt `farm.js`), `plugins/ca/tools/farm.unit.test.ts`, `plugins/ca/includes/farm.md`
**Landing:** one PR per issue (see plan; final structure confirmed at the gate).

All three were filed during the `docs-site-mvp` `/ca:sprint --farm` run (2026-06-18, Windows) and
carry author-verified root causes and fix candidates. This sprint turns those candidates into gated,
test-first fixes. Premium path is mandatory here: `--farm` is broken until #90 lands, and dogfooding
the broken tool to fix itself is circular.

---

## Issue #90 — stale built-in default API base URL (bug)

**Root cause.** `ENV.defaultApiBaseUrl` (farm.ts ~L90) is `https://api.opencode.ai/v1`. That host now
returns HTTP 200 with body `Not Found` for `/models` and `/chat/completions`, so every worker dies with
the opaque `non-JSON response: SyntaxError ...`. Live endpoint is `https://opencode.ai/zen/v1`.

**Acceptance criteria.**
- **AC-90.1** — `ENV.defaultApiBaseUrl` default is `https://opencode.ai/zen/v1` (the `FARM_DEFAULT_API_BASE_URL` env override is preserved).
- **AC-90.2** — When `/chat/completions` returns a 2xx whose body is not valid JSON, `callApi` returns an actionable error that names the endpoint and points at `FARM_API_BASE_URL` (e.g. `endpoint returned a non-JSON body ("Not Found") — check FARM_API_BASE_URL / the endpoint path`), not the bare `non-JSON response: <SyntaxError>`.
- **AC-90.3** — `plugins/ca/includes/farm.md` documents `https://opencode.ai/zen/v1` as the default; no stale `api.opencode.ai/v1` reference remains.
- **AC-90.4** — `farm.js` rebuilt; `git diff --quiet -- farm.js` clean after build.

**Verification.** Unit test asserts the default constant resolves to the new URL. Unit test drives the
non-JSON-body path through an injectable fetch (export `callApi` or a small `parseApiResponse` helper)
and asserts the actionable message. `npm test` + `npm run typecheck` + rebuilt bundle.

---

## Issue #91 — git CRLF stderr pollutes drift detection (bug)

**Root cause.** The shared `run()` helper merges stdout+stderr into one `out` string. `checkDrift()`
parses `git diff --name-only HEAD` from `out`; on Windows with `core.safecrlf` warnings on, git prints
`warning: in the working copy of '<file>', LF will be replaced by CRLF ...` to **stderr**, which is then
parsed as a changed file path → false `drift:` escalation of a fully-correct worker.

**Acceptance criteria.**
- **AC-91.1** — `run()` captures stdout and stderr **separately** (e.g. returns `{ code, out, stdout, stderr }`, where `out` stays the merged string for back-compat consumers like `runGate`).
- **AC-91.2** — `checkDrift()` parses **stdout only** (`git diff --name-only`, `git ls-files`), so no stderr line — CRLF warning or otherwise — is ever treated as a changed path.
- **AC-91.3** — `checkDrift` is exported and accepts an injectable git runner (default = real `git`) so the behavior is unit-testable without a real repo.
- **AC-91.4** — `farm.js` rebuilt; `git diff --quiet -- farm.js` clean.

**Verification.** Unit test: stub git so `diff --name-only` returns a real in-scope-violating path on
`stdout` and a `warning: ... LF will be replaced by CRLF ...` line on `stderr` (merged into `out`).
Assert `checkDrift` returns only the real out-of-scope path and never the warning line. A second case:
worker touched only its in-scope file + a CRLF warning on stderr → `checkDrift` returns `[]` (no drift).

---

## Issue #93 — model discovery surfaces expired 'free promotion' models (enhancement)

**Root cause.** OpenCode Zen's `/models` lists models the key is not entitled to (`*-free` promos);
`/chat/completions` then returns HTTP 401 `"Free promotion has ended for ..."`. The canary cannot
distinguish entitlement-denial from a capability failure, so it burns full attempts/timeouts on dead
candidates (one 7-model canary ran for minutes before being killed).

**Acceptance criteria.**
- **AC-93.1** — Before the real canary loop, a cheap entitlement screen runs one minimal `/chat/completions` probe (≤ a few tokens) per candidate; any candidate whose probe returns **401** is dropped from the canary.
- **AC-93.2** — A dropped candidate is surfaced **distinctly** in `canary-report.json` — an entry marked as skipped-for-entitlement (e.g. `{ model, skipped: "entitlement", note: "401 — not entitled / promotion ended" }`) — never silently removed and never conflated with a capability `FAIL`.
- **AC-93.3** — The entitlement screen is bounded by a per-candidate wall-clock cap (own timeout, default ≤ `FARM_REQUEST_TIMEOUT_MS`, overridable via a new env knob) so one slow/dead model cannot dominate the probe.
- **AC-93.4** — Screening is a pure, exported function (`screenEntitlements(models, probeFn, ...)`) taking an injectable probe so it is unit-testable without the network; the real `runCanary` wires it in.
- **AC-93.5** — `farm.js` rebuilt; `git diff --quiet -- farm.js` clean.

**Verification.** Unit test: `screenEntitlements` with a stub probe returning 401 for one model and 200
for another → the 401 model is in the skipped set with an entitlement note, the 200 model survives.
Unit test: a probe that exceeds the cap is treated as a drop/handled (not a hang). `runCanary`'s report
shape includes the skipped entries.

---

## Cross-cutting hard rules (apply to all three)

- **No security-controls / auth / crypto / secrets surface is touched** by design. `assertSecureBaseUrl` and the secret-redaction path are NOT modified. If any task drifts into that surface, it is a hard-gate stop.
- The new default URL (#90) must still pass `assertSecureBaseUrl` (it is HTTPS — verified).
- Every task is test-first via `tdd`; the failing test is written and shown red before impl.
- Every PR's gate includes the full `tech-stack.md` tools sequence: `npm ci && npm run typecheck && npm test && npm run build` then `git diff --quiet -- farm.js`.
- `/ca:sprint` never merges and never discards — each PR's merge decision is surfaced to the user in the morning summary.
- Every non-hard-gate auto-decision is logged to `.codearbiter/sprint-log.md`.

## Out of scope (noted, not done)

- Reconciling `SAFE_TASK_ID` vs `plan.schema.json` id pattern (existing `[NEEDS-TRIAGE]`).
- The non-reporting-worker path-containment sandbox (existing `[NEEDS-TRIAGE]`).
- #92 (per-worktree dependency setup hook) and #61 (standup-at-session-start — needs `/ca:debug` first).
