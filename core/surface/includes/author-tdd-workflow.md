# Author verification workflow

Use the caller's scoped obligations and selected verification approach from
`{{PLUGIN_ROOT}}/skills/tdd/SKILL.md`. Keep each obligation tied to its source and
proving check. Apply `{{PLUGIN_ROOT}}/includes/verification-boundary.md` for local
checks and exact-head hosted CI.

| Route | Required evidence |
|---|---|
| /fix | Observe genuine target RED before repair, then fresh GREEN for the same named regression with unchanged assertions. Reuse an adequate current bug-origin RED. |
| /feature | Keep the agreed spec and criteria. Prefer test-first work; existing implementation may use current criterion-focused checks and meaningful negative controls. Report the observed sequence accurately. |
| /refactor | Keep the approved surface and parity contract. Establish passing characterization before restructuring and preserve baseline assertions throughout implementation. |

For a bug-origin fix, carry the current expectation, cited evidence, supported
cause and regression oracle into the existing obligation ledger. Check the
original caller's repair authority and source freshness through the fix owner.
Do not fabricate a feature artifact. An ADR remains a user-attributed decision
through `/adr`.

Name the existing target test and reuse it when its assertion matches the defect;
add tests for uncovered obligations. An import, setup or unrelated failure is not
target RED. Retain unrelated baseline failures and their outputs. A material
fixture or setup change requires renewed target RED on the broken source before
claiming RED-to-GREEN. Preserve the regression's assertions between those runs.

For intermittent or timing defects, prefer a faithful deterministic seam.
Otherwise declare a finite repeated-trial bound and failure oracle before running
it. Report the sample limits; do not claim deterministic proof from a passing
sample or retry until GREEN.

Implement only the assigned scope. Run its proving checks and affected existing
contracts on the resulting source, then applicable coverage, lint and type checks.
Preserve failures and actual user stops; never skip tests, suppress failures or
waive required checks to obtain a pass.

Return changed paths, obligation evidence, actual commands/cwd/results and pending
checks to the caller. Stage only when that action is assigned and authorized;
committing and publication retain their own owners and permissions.
