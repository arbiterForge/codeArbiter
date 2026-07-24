# Hackathon PR #313 consolidation

**Status:** APPROVED — user-directed 2026-07-20; integration choices delegated to SMARTS.

**Governs:** .codearbiter/reports/2026-07-20-hackathon-pr313/**, docs/reports/pi-support/**, docs/parity.md

## Problem

The hackathon work is fragmented across PR #313 and sixteen green corrective PRs. The submission needs one review surface that demonstrates both Pi parity and GPT-5.6 finding and repairing defects in older codeArbiter work.

The caller is the maintainer preparing the hackathon submission. Done means PR #313 contains every selected PR's unique change, carries one auditable source manifest and narrative, and returns to fully green final-promotion evidence.

## Scope

In scope:

- Consolidate PRs #347, #348, #349, #350, #351, #354, #356, #357, #358, #359, #360, #362, #363, #365, #367, and #368 into PR #313.
- Preserve their corrective behavior, tests, documentation, issue-closing references, and append-only sprint decisions.
- Present Pi parity and the broader GPT-5.6 remediation story as one hackathon submission.
- Rebind the two-phase Pi promotion evidence after the combined candidate passes hosted CI.
- Close the absorbed source PRs only after the final PR #313 head is green, leaving permanent comments that point to #313.

Out of scope:

- Dependabot PR #336. It is automated dependency maintenance, not GPT-authored corrective hackathon work.
- Merging PR #313 or any source PR into `main`.
- Tags, releases, marketplace publication, new dependency adoption, or new behavior beyond the selected PRs.
- The explicitly deferred clone refactor and unresolved feature/ADR decisions.

## Acceptance criteria

1. A machine-readable manifest records all sixteen source PR numbers, exact head and commit OIDs, exact changed paths, closing issues, and the explicit #336 exclusion.
2. Every unique source commit diff outside append-only audit logs is applied to the PR #313 integration tree, with no source hunk silently omitted.
3. Every source sprint-log addition is appended exactly once; no existing audit line is rewritten, truncated, or deleted.
4. The combined tree passes every test, typecheck, generator, reference, security, secret, diff, and package gate required by the union of changed paths.
5. Security-sensitive fixes from #347 and #354 retain their reviewed boundaries and pass fresh combined security-gate evidence without a bypass.
6. PR #313's title and body describe one hackathon submission, enumerate all absorbed PRs and issue closures, and distinguish Pi parity from older-work remediation.
7. Hosted CI is green on the combined implementation candidate, the sanitized promotion pair is rebound to that exact SHA, and final verification passes all Pi obligations.
8. After the final PR #313 head is green, each absorbed source PR is closed with a durable comment identifying #313 as its integration destination.
9. The primary checkout's user-owned modifications, untracked plans/specs, stashes, and pre-existing worktrees remain intact.

## Open questions

None. The user explicitly selected one-PR consolidation and delegated non-hard integration choices to SMARTS.
