# Plan: checkpoint-2026-06-13-remediation

**Spec:** `.codearbiter/specs/checkpoint-2026-06-13-remediation.md`
**Branch:** `sprint/checkpoint-2026-06-13-remediation` (new branch off current `checkpoint-remediation-2026-06-12` HEAD)
**Status:** APPROVED — 2026-06-13 (executing)

Execution order: pre-flight hygiene (0) → autonomous A + E → hard-gate B → hard-gate C → hard-gate D
→ land. C and D HALT for interactive user action; A, B-code, E run test-first autonomously.

---

## Tasks

| # | Title | File(s) | Verification | Deps | Gate | Status |
|---|-------|---------|--------------|------|------|--------|
| 0 | Pre-flight: branch off HEAD; revert farm.js CRLF (artifacts carried to gated commit per SD-01) | `plugins/ca/tools/farm.js`, branch | New branch exists; `git diff farm.js` empty; artifacts staged for landing | — | auto | DONE |
| 1 | A: `test_pre_edit.py` — H-05 BLOCK (non-append to overrides.log/triage.log) | `plugins/ca/hooks/tests/test_pre_edit.py` (new) | Test: non-appending edit → exit 2, `H-05` tag | 0 | auto | DONE |
| 2 | A: H-05 ALLOW (pure-append) + arbiter-disabled ALLOW | `plugins/ca/hooks/tests/test_pre_edit.py` | Test: append edit → exit 0; disabled/unrelated path → exit 0 | 1 | auto | DONE |
| 3 | A: H-11 BLOCK no-marker + BLOCK stale-marker + ALLOW fresh-marker | `plugins/ca/hooks/tests/test_pre_edit.py` | Tests: no marker → 2; >30min marker → 2; fresh marker → 0 | 1 | auto | DONE |
| 4 | A: Windows `norm_path` backslash variant fires guard branch | `plugins/ca/hooks/tests/test_pre_edit.py` | Test: backslash path hits the Windows branch | 3 | auto | DONE |
| 5 | E: add `npm audit --omit=dev --audit-level=critical` to tools CI job | `.github/workflows/ci.yml` | CI job runs the audit step; step name present in workflow | 0 | auto | DONE |
| 6 | E: reference the audit command in tech-stack.md | `.codearbiter/tech-stack.md:57-58` | "no scanner configured" replaced by the enumerated command | 5 | auto | DONE |
| 7 | B: failing vitest — resolved `FARM_API_BASE_URL=http://` rejected pre-fetch | `plugins/ca/tools/farm.unit.test.ts` | New test red before impl: http env override throws before any fetch | 0 | auto | DONE |
| 8 | B: validate resolved apiBaseUrl (HTTPS-or-loopback) before first fetch | `plugins/ca/tools/farm.ts` (`assertSecureBaseUrl`, URL-parse) | Task 7 green; 69 vitest green; 2× security-reviewer PASS | 7 | **HARD: security-controls** | DONE |
| 9 | B: rebuild shipped `farm.js`, confirm in sync | `plugins/ca/tools/farm.js` | `farm.js` rebuilt from `farm.ts`; no drift | 8 | auto | DONE |
| 10 | B: surface the security-relevant change to user before landing | — | User acknowledges the TLS/secret-path fix | 9 | **HARD: surface** | DONE (surfaced in landing report) |
| 11 | C: boundary rows (shell-exec + loopback-http) + TLS-section update | `.codearbiter/security-controls.md` | 2 rows + TLS para; user-approved all three | 0 | **HARD: trust-boundary** | DONE |
| 12 | D: `/ca:adr` — Hybrid governance model (meta-decision) | `.codearbiter/decisions/0001-*.md` + decision-log.md | ADR authored, user-attributed; decision log initialized | 0 | **HARD: ADR / user-attributed** | DONE |
| 13 | D: `/ca:adr` — plan.json shell-exec boundary | `.codearbiter/decisions/0002-*.md` | ADR authored, user-attributed (pairs with task 11) | 12 | **HARD: ADR / user-attributed** | DONE |
| 14 | D: `/ca:adr` — TLS / secret-handling posture | `.codearbiter/decisions/0003-*.md` | ADR authored, user-attributed (relates to task 8) | 12 | **HARD: ADR / user-attributed** | DONE |
| 15 | D: `/ca:adr` — Database-free / stdlib-only architecture | `.codearbiter/decisions/0004-*.md` | ADR authored, user-attributed | 12 | **HARD: ADR / user-attributed** | DONE |
| 16 | Land: `commit-gate` → `finishing-a-development-branch` (auto open-PR) | — | Full suite green; PR opened; merge decision left to user | 1-15 | **HARD: merge-to-default deferred to user** | DONE (6 commits, version bumped to beta.3, PR opened; NOT merged) |

---

## Notes

- **MVP slice:** tasks 0–10 (hygiene + the two autonomous workstreams + the B code fix) form the
  shippable core. C (11) and D (12–15) are governance and gate on user action; they extend the same PR.
- **Hard-gate stops, in order:** task 8/10 (security-controls / surface B), task 11 (trust-boundary
  edit), tasks 12–15 (ADR authoring). Each halts and surfaces — none auto-decided. This density is
  expected for a governance-heavy checkpoint sprint and is flagged in the spec, not a planning miss.
- **Auto-decisions** (test shapes, file placement, CI step wording, ADR drafting structure) are
  SMARTS-scored and logged to `sprint-log.md` with a confidence flag; the ADR *content/attribution*
  is the user's, never auto-decided.
