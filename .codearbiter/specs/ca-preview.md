# Spec — /ca:preview (zero-onboarding reviewer-fleet dry-run)

**Issue:** #81 · **Effort:** M · **Posture:** top time-to-first-value lever under ADR-0006.

## Problem

A prospective user cannot see what codeArbiter would do to their real code without first paying the
full onboarding cost: install, `/ca:init`, then a long `/ca:decompose` or `/ca:create-context`
interview. `/ca:doctor` only proves hooks fire; it says nothing about which reviewers or gates a real
diff would trip. The skeptic has no fast way to feel the value on their own code.

## Scope

**In:** a read-only `/ca:preview` command that, against the current uncommitted diff, prints which
reviewers the diff would dispatch and where it would BLOCK — with zero onboarding and zero state
written. Fidelity model is **hybrid**:

- **Predicted** — the reviewer-to-path matrix (which reviewers would dispatch and why), reasoned over
  the changed paths. This is the same reviewer-to-path mapping `/ca:review` uses; there is one source
  of truth, not a second copy.
- **Found (ran locally)** — the checks that need no `.codearbiter/` rules run for real against the
  diff: a secret/credential scan reusing the hooks' existing `SECRET_RE`, and a changed-source-without-
  a-test check. These run in-process (no subagent dispatch), so the command stays fast.
- **State-dependent reviewers** (security-reviewer, auth-crypto-reviewer, dependency-reviewer,
  migration-reviewer) are shown as "would run — sharper after onboarding," never run against guessed
  rules and never reporting fabricated findings.

**Diff source:** `git diff HEAD` (staged + unstaged tracked changes) plus untracked files. An empty
diff or a non-git directory yields a friendly "nothing to preview" message and a clean exit, not an
error.

**Out of scope:** does not write any `.codearbiter/` state; does not require or trigger `/ca:init`,
`/ca:decompose`, or `/ca:create-context`; does not build a second review engine (reuses the matrix and
the secret regex); does not replace `/ca:doctor` (hook probe) or `/ca:review` (the full gated review on
an onboarded repo); does not modify the diff, stage, or commit. Must function in a repo without
`arbiter: enabled` and without the orchestrator persona injected (it is a plugin command, available
regardless of activation).

## Acceptance criteria

1. **Runs without onboarding.** In a repo with no `.codearbiter/` directory and no `arbiter: enabled`
   flag, `/ca:preview` produces a report and does not require, trigger, or error on missing project
   state.
2. **Read-only / no state writes.** After a run, no file under `.codearbiter/` (or elsewhere) is
   created or modified; `git status` is unchanged by the command.
3. **Diff source incl. untracked.** Given a tracked-unstaged edit, a staged edit, and a new untracked
   file simultaneously present, all three appear in the report's reviewed-file set.
4. **Graceful empty/no-repo.** In a non-git directory, and in a git repo with no uncommitted changes,
   the command prints a "nothing to preview" message and exits 0 (no stack trace, no error).
5. **Matrix prediction by path.** A diff touching an auth/crypto path lists `security-reviewer` and
   `auth-crypto-reviewer` as would-dispatch with the triggering path named; a migration file lists
   `migration-reviewer`; a dependency manifest lists `dependency-reviewer`; `coverage-auditor` is
   listed for all paths.
6. **Single source of truth.** Given the same set of changed paths, the reviewer set `/ca:preview`
   predicts is identical to the set `/ca:review` would dispatch (the mapping is shared, not duplicated).
7. **Real secret finding.** A credential matching the hooks' `SECRET_RE` present in the diff is
   reported as a real, BLOCK-level secret finding marked as found/ran, not predicted.
8. **Real test-gap finding.** A changed source file with no corresponding test is reported by the
   changed-source-without-a-test check as a real finding marked found/ran.
9. **State-dependent honesty.** The four rule-dependent reviewers are shown as "would run — sharper
   after onboarding," visually distinct from found results, with no fabricated findings attributed to
   them.
10. **Distinct from doctor.** The report describes reviewer/gate behavior on the diff and makes no
    hook-probe claims; `/ca:doctor` behavior is unchanged.
11. **Onboarding nudge.** The report ends with a one-line upgrade path: the full gated review comes via
    `/ca:init` then `/ca:review`.

## Open questions

None blocking.

- `[NEEDS-TRIAGE]` Mechanism of matrix reuse (extract the reviewer-to-path mapping to a small testable
  module vs. a single cited prose reference both commands point at) is a HOW decision for
  `writing-plans`, not a spec-level open question — criterion 6 fixes the requirement either way.
- `[NEEDS-TRIAGE]` Future expansion of the run-locally check set (e.g., a generic banned-primitive
  scan) is a later enhancement, deliberately out of this feature.
