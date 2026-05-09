---
description: Run the full local CI gate set and produce a PR-ready summary
argument-hint: "[optional: branch name to compare against, default origin/main]"
---

Run the full FUSION pre-PR gate. Compare against `${1:-origin/main}`.

Procedure:

1. Read `.fusion/stage` and announce the current stage.
2. Run `make lockfile-check` and report.
3. Run `make backend-lint frontend-lint` and report.
4. Run `make backend-test frontend-test` and report coverage vs. stage threshold.
5. Run `make sast secrets-scan deps-scan license-scan container-scan` and report.
6. Run `make sbom` and confirm SBOM artifact path.
7. Run `make fips-check` and confirm FIPS provider active.
8. Run `make validate-definitions layout-check registry-check`.
9. Compute diff summary: `git diff --stat ${1:-origin/main}...HEAD`.
10. Identify which subagents should review this diff based on path matrix in
    `.claude/agents/security-reviewer.md` and emit invocation suggestions.
11. Produce a PR description draft with the four required fields:
    - what changed
    - why
    - what was tested
    - data classification touched
    - tradeoff level cited (per CLAUDE.md §0)

Do NOT push. Do NOT merge. Do NOT modify CI configuration. If any gate fails,
STOP and report the failure verbatim.
