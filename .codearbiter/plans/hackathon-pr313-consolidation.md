# Plan — hackathon PR #313 consolidation

**Status:** APPROVED — user goal plus SMARTS auto-approval, 2026-07-20.

The normative exact-path inventory is `.codearbiter/reports/2026-07-20-hackathon-pr313/source-prs.json`. A task that names PR numbers below owns exactly the `paths[]` entries for those PR objects; the manifest resolves 126 unique paths without prose abbreviation.

## Acceptance-criterion ledger

| ID | Criterion |
|---|---|
| AC-01 | Record all included/excluded PRs, OIDs, paths, and issue closures. |
| AC-02 | Apply every non-audit source diff without silent omission. |
| AC-03 | Append every source sprint decision exactly once. |
| AC-04 | Pass the union's complete local gate suite. |
| AC-05 | Re-prove the absorbed security boundaries without bypass. |
| AC-06 | Make PR #313 the single explicit hackathon narrative and issue-closing surface. |
| AC-07 | Rebind final Pi promotion evidence to the green integrated candidate. |
| AC-08 | Close absorbed source PRs only after the final #313 head is green. |
| AC-09 | Preserve all user-owned checkout and recovery state. |

## Ordered tasks

| ID | Paths | Verification | Maps to | Covers | Depends on | Status |
|---|---|---|---|---|---|---|
| T-01 | `.codearbiter/reports/2026-07-20-hackathon-pr313/source-prs.json` | JSON parses; 16 unique PRs, 29 commits, 126 unique paths; #336 has one exclusion record. | OBL-01 | AC-01 | — | ACCEPTED |
| T-02 | `.codearbiter/specs/hackathon-pr313-consolidation.md`, `.codearbiter/plans/hackathon-pr313-consolidation.md`, `.codearbiter/sprint-log.md` | Spec/plan coverage is bijective; approval and SMARTS decisions are appended. | OBL-02 | AC-01, AC-09 | T-01 | ACCEPTED |
| T-03 | Manifest `paths[]` for PRs #347, #349, #350, #354 | Patch ledger reports every source commit applied; focused hook, provenance, farm, and security tests pass. | OBL-03 | AC-02, AC-04, AC-05 | T-02 | ACCEPTED |
| T-04 | Manifest `paths[]` for PRs #348, #351, #368 | Patch ledger reports complete application; docs contract, generator, site tests, and build pass. | OBL-04 | AC-02, AC-04 | T-02 | ACCEPTED |
| T-05 | Manifest `paths[]` for PRs #356, #357 | Both deterministic regression files match the selected heads; their focused tests pass. | OBL-05 | AC-02, AC-04 | T-02 | ACCEPTED |
| T-06 | Manifest `paths[]` for PRs #358, #359 | Codex and Claude tribunal telemetry regressions pass together; generated surfaces remain synchronized. | OBL-06 | AC-02, AC-04 | T-02 | ACCEPTED |
| T-07 | Manifest `paths[]` for PRs #360, #362, #363 | Prune metrics, malformed-state, and statusline evidence tests pass on the stacked result. | OBL-07 | AC-02, AC-04 | T-02 | ACCEPTED |
| T-08 | Manifest `paths[]` for PRs #365, #367 | Task writer, task board, board sync, Pi platform fixture, docs mirrors, and generated surfaces pass together. | OBL-08 | AC-02, AC-04 | T-07 | ACCEPTED |
| T-09 | `.codearbiter/sprint-log.md`, `.codearbiter/reports/2026-07-20-hackathon-pr313/integration.md` | Audit delta is additions-only with no duplicates; report maps every source commit to an applied receipt. | OBL-09 | AC-02, AC-03, AC-09 | T-03, T-04, T-05, T-06, T-08 | ACCEPTED |
| T-10 | All 126 manifest paths plus generated outputs under `plugins/ca/**`, `plugins/ca-codex/**`, `plugins/ca-pi/**`, `site/**` | Full tech-stack suite, typechecks, builds, generator checks, package checks, secret scan, and `git diff --check` pass. | OBL-10 | AC-04, AC-05 | T-09 | ACCEPTED |
| T-11 | Integration candidate commit; PR #313 title/body | Candidate commit passes commit-gate, pushes to `feat/pi-support`, and PR metadata enumerates all sixteen absorbed PRs and closures. | OBL-11 | AC-06, AC-09 | T-10 | PENDING |
| T-12 | GitHub checks for PR #313 candidate | `gh pr checks 313 --watch` exits zero; exact supported Pi matrix, security analysis, CodeQL, and aggregate gate pass. | OBL-12 | AC-07 | T-11 | PENDING |
| T-13 | `docs/reports/pi-support/promotion.json`, `docs/reports/pi-support/promotion.md`, `docs/parity.md`, `.codearbiter/sprint-log.md` | Evidence generator binds the candidate SHA; final verifier passes all repository gates and PI-AC-01..38. | OBL-13 | AC-07 | T-12 | PENDING |
| T-14 | Final evidence commit; PR #313 checks | Evidence-only commit passes commit-gate, pushes, and final `gh pr checks 313 --watch` exits zero. | OBL-14 | AC-07 | T-13 | PENDING |
| T-15 | GitHub PRs #347, #348, #349, #350, #351, #354, #356, #357, #358, #359, #360, #362, #363, #365, #367, #368 | Each is closed with a comment linking #313; coverage audit proves every manifest PR remains represented in #313. | OBL-15 | AC-08 | T-14 | PENDING |

## Dependency order and MVP slice

No cycles. T-01 through T-11 form the MVP integration candidate. T-12 through T-15 are mandatory promotion and single-PR finalization, not optional polish.
