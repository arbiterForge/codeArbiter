---
name: commit-gate
description: The only path to a commit. Routed to when the user invokes /commit or otherwise instructs codeArbiter to persist staged changes. Nine gated phases — permission, branch, classification, verification (test/lint/secrets), behavioral proof, diff review, selective stage, message, commit. Nothing reaches version control without clearing every gate; "it looks good" is not authorization.
---

# commit-gate

The only permitted path to a commit. Bypassing it is a hard-rule violation. Routed to when the user invokes `/commit` or any equivalent instruction to persist staged changes.

## Pre-flight

Read these, or STOP and surface the gap — never guess a command:

- `${CLAUDE_PROJECT_DIR}/.codearbiter/tech-stack.md` — test, lint, and secrets-scan invocations. Stop if missing; do not guess.
- A git repository must be present and `git status` available.
- The `tdd` skill must have cleared all six phases for any new or modified feature code in the staged set. If `tdd` is incomplete, STOP and surface the gap.

## Phase 1 — Permission · gate: BLOCK

Confirm the user explicitly authorized this commit. Speculative commits are prohibited.

Explicit instructions: "commit", "commit this", "go ahead and commit", "create the commit". Ambiguous signals — "looks good", "that should work" — are NOT authorization. Record the instruction text for the report.

Gate: explicit user authorization is on record. Inferred or assumed permission does not pass.

## Phase 2 — Branch · gate: BLOCK

Run `git branch --show-current`. If the branch is `main`, `master`, or any protected branch, STOP and instruct the user to create a feature branch. Record the branch name for the report.

Gate: the working branch is not protected.

## Phase 3 — Classification · gate: BLOCK

Read the staged set (`git diff --cached --name-only` and `--stat`). Classify the change into a commit type:

- `feat` — new capability or behavior
- `fix` — corrects a defect
- `test` — tests only
- `refactor` — restructures without behavior change
- `docs` — documentation only
- `chore` — build, tooling, dependency updates
- `ci` — pipeline changes

Derive the scope from the staged paths. If the staged set spans more than one type, split it — stage and commit each type separately.

Gate: the staged set is type-homogeneous with a single type and scope.

## Phase 4 — Verification · gate: BLOCK

Read the test, lint, and secrets-scan commands from `tech-stack.md`. Then:

- Run the test command. ALL tests green. Any failure blocks.
- Run lint, and the type-check if the project is statically typed. Zero errors.
- Run the secrets scan on ALL staged files, regardless of commit type. Any finding blocks.

Record each result (PASS / BLOCK) for the report.

Gate: test, lint, and secrets scan all PASS. Any failure halts the commit until fixed and re-run.

## Phase 5 — Behavioral proof · gate: BLOCK

A green suite proves the tests pass — not that the change does what it was asked to do. Before persisting, prove the behavior against the spec, not against a self-report.

- Identify the proving command or observable: the acceptance criterion from `${CLAUDE_PROJECT_DIR}/.codearbiter/specs/<slug>.md` (or the task's verification in the plan). If none exists, derive the smallest command that exercises the claimed behavior.
- Run it FRESH in this phase. Read the actual output and the exit code — do not infer success from "the tests pass," and never trust a subagent's self-report that it works.
- Confirm the observed behavior matches the spec's acceptance criteria. A mismatch, or an unverifiable claim, blocks.

Gate: the change is proven to do what it claimed by fresh evidence — command output and exit code read in this phase. A self-reported "it works" does not pass.

## Phase 6 — Diff review · gate: BLOCK

Read the complete staged diff (`git diff --cached`). Flag as blocking:

- Unexpected files — not discussed in the session.
- Credentials, tokens, API keys, or any secret — belt-and-suspenders to Phase 4.
- Incomplete changes — TODO markers, placeholder values, dead commented-out code, partial stubs.
- Tests disabled or skipped that were not intentionally disabled.
- Scope creep — changes outside the agreed feature or fix boundary.

On any blocking finding, unstage the affected files, surface the finding, and STOP. An out-of-scope change that should not be lost gets an inline `[NEEDS-TRIAGE]` marker before it is set aside.

Gate: the diff is clean — zero blocking findings.

## Phase 7 — Selective stage · gate: BLOCK

If files were unstaged in Phase 6, re-stage only the clean files by explicit path: `git add path/to/file`. Re-run `git diff --cached --name-only` and confirm the staged list matches the intended set exactly — no extra files. Unstage any extra and report the discrepancy.

Gate: the staged set contains exactly the intended files. MUST NOT use `git add -A`, `git add .`, or any wildcard.

## Phase 8 — Message · gate: BLOCK

Compose a Conventional Commits message:

- Subject: `<type>(<scope>): <imperative summary>`, MUST NOT exceed 72 characters.
- Blank line, then a body explaining WHY — not a restatement of what changed.
- For `feat` and `fix`, add a `CHANGELOG:` footer summarizing the user-visible impact.
- If the commit closes an issue or references a decision, add the footer (`Closes #NN`, `Ref: ADR-NNNN`).
- No content-free subjects — "fix bug", "update code", "changes" do not pass.

Gate: subject ≤ 72 chars, a body is present, and any `feat`/`fix` carries a `CHANGELOG:` footer.

## Phase 9 — Commit · gate: BLOCK

Commit with the approved message via `-m` or heredoc with proper quoting — never an interactive editor. Capture the resulting SHA.

If a pre-commit hook fails: read its output in full, fix the issue, re-stage by explicit path (Phase 7 rules apply), and create a NEW commit. MUST NOT `--amend` after a hook failure.

After a successful commit, run `git status` to confirm the tree is clean. Deliver the report: SHA, branch, explicit file list, gate results (test / lint / secrets), and the message used.

Gate: the commit lands and `git status` is clean. Unexpected uncommitted changes after the commit block closure — report the discrepancy.

## Hard rules

- MUST NOT commit without explicit user authorization. "It looks good" is not permission.
- MUST NOT commit to `main`, `master`, or any protected branch.
- MUST NOT run `git add -A`, `git add .`, or any wildcard staging.
- MUST NOT commit while any test is failing, any lint error stands, or any secret is present.
- MUST NOT accept a self-reported "it works" — prove the behavior against the spec with a fresh command run (Phase 5) before committing.
- MUST NOT skip, disable, or work around any automated gate.
- MUST NOT `--amend` after a pre-commit hook failure — create a new commit.
- MUST NOT guess the test, lint, or secrets-scan command — read `tech-stack.md` or STOP.
