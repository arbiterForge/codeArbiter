# Skill: commit-gate

## Trigger

> *"This section lists conditions under which the orchestrator routes work to this skill. The skill itself does not 'trigger' — it is routed to."*

Invoke this skill whenever the user says "commit", "commit this", "go ahead and
commit", or any equivalent instruction to persist staged changes to version control.

This skill is the only permitted path to a commit. Bypassing it is a hard rule
violation.

Triggers:
- User requests a commit of any kind
- The commit-gate skill is referenced in the routing table

---

## Pre-Flight

Before Phase 1 begins, confirm:

1. `${PROJECT_ROOT}/.agents/projectContext/tech-stack.md` is readable — stop if missing.
2. A git repository is present and `git status` is available.
3. The tdd skill has completed all six phases for any new or modified
   feature code in the staged set. If tdd phases are incomplete, stop and
   surface the gap before continuing.

If any pre-flight check fails, stop and report. Do not attempt the commit.

---

## Phase 1: Permission Gate

**Goal:** Confirm the user has explicitly authorized this commit. Speculative
commits on behalf of the user are prohibited.

**Inputs:**
- The user's message in the current session

**Actions:**

1. Confirm the user's message contains an explicit commit instruction. Examples
   of explicit instructions: "commit", "commit this", "go ahead and commit",
   "create the commit".
2. If the instruction is ambiguous (e.g., "looks good" or "that should work"),
   stop and ask for explicit confirmation before continuing.
3. Record the instruction text and session timestamp for the commit report.

**Output:** Confirmed explicit user authorization with instruction text logged.

**Gate:** BLOCK. No commit proceeds without explicit user instruction. Inferred
or assumed permission is not sufficient.

---

## Phase 2: Branch Gate

**Goal:** Confirm the working branch is not a protected branch.

**Inputs:**
- `git branch --show-current`

**Actions:**

1. Run `git branch --show-current` and capture the branch name.
2. If the branch is `main`, `master`, or any branch configured as protected in
   the project's CI configuration, stop immediately.
3. Report the current branch name in the commit report.

**Output:** Confirmed non-protected branch name.

**Gate:** BLOCK. MUST NOT commit directly to `main`, `master`, or any other
protected branch. Instruct the user to create a feature branch and retry.

---

## Phase 3: Classification

**Goal:** Determine the correct commit type, scope, and whether the staged
change set needs to be split.

**Inputs:**
- `git diff --cached --name-only`
- `git diff --cached --stat`

**Actions:**

1. Read the list of staged files.
2. Classify the change into one or more commit types:
   - `feat` — new capability or behavior
   - `fix` — corrects a defect
   - `test` — adds or modifies tests only
   - `refactor` — restructures without behavior change
   - `docs` — documentation only
   - `chore` — build, tooling, dependency updates
   - `ci` — CI/CD pipeline changes
3. If staged files span more than one commit type (e.g., feature code mixed
   with documentation), split the staged set into separate commits. Do not
   mix types in a single commit.
4. Derive the scope from the staged file paths (e.g., directory name, module
   name, or component name).

**Output:** Commit type, scope, and confirmation that the staged set is
type-homogeneous.

**Gate:** BLOCK if staged files span incompatible commit types. Stage and commit
each type separately.

---

## Phase 4: Verification Gates

**Goal:** Confirm all automated quality gates pass before committing.

**Inputs:**
- `${PROJECT_ROOT}/.agents/projectContext/tech-stack.md` — test, lint, and secrets-scan commands

**Actions:**

1. Read `${PROJECT_ROOT}/.agents/projectContext/tech-stack.md` to identify:
   - The test command
   - The lint command
   - The secrets-scan command
2. Run the test command. ALL tests must be green. Any failure blocks the commit.
3. Run the lint command. Zero errors permitted. Warnings that escalate to errors
   under the project's configuration must be resolved.
4. Run the secrets scan as specified in `${PROJECT_ROOT}/.agents/projectContext/tech-stack.md`
   on ALL staged files, regardless of commit type. A secrets finding always
   blocks the commit.
5. Record the result of each gate (PASS / BLOCK) in the commit report.

**Output:** All three gates (test, lint, secrets scan) in PASS status.

**Gate:** BLOCK on any test failure, lint error, or secrets finding. All three
must pass before Phase 5.

---

## Phase 5: Diff Review

**Goal:** Read the full staged diff and confirm it contains no surprises.

**Inputs:**
- `git diff --cached`

**Actions:**

1. Read the complete staged diff.
2. Flag any of the following as blocking findings:
   - Unexpected files (files not discussed in the session)
   - Credentials, tokens, API keys, or other secrets (even if already caught
     by Phase 4 secrets scan — belt-and-suspenders)
   - Incomplete changes (TODO markers, placeholder values, commented-out code
     that should be removed, partial function stubs)
   - Test files disabled or skipped that were not intentionally disabled
   - Scope creep (changes outside the agreed feature or fix boundary)
3. If any blocking finding is present, unstage the affected files, surface the
   finding to the user, and stop. Do not proceed until the user resolves it.

**Output:** Confirmed clean diff with no blocking findings.

**Gate:** BLOCK on any blocking finding. User must explicitly acknowledge and
resolve each finding before Phase 6.

---

## Phase 6: Selective Stage

**Goal:** Confirm only the intended files are staged using explicit paths.

**Inputs:**
- List of intended files confirmed in Phase 5

**Actions:**

1. If files were unstaged during Phase 5, re-stage only the clean files using
   explicit paths: `git add path/to/file`.
2. MUST NOT run `git add -A`, `git add .`, or any wildcard staging command.
3. Run `git diff --cached --name-only` again and confirm the staged list matches
   exactly the intended set. No extra files.
4. If the staged set differs from the intended set, unstage the extra files and
   report the discrepancy.

**Output:** Staged set confirmed to contain exactly the intended files.

**Gate:** BLOCK if any unintended file is staged. Exact staging is required.

---

## Phase 7: Commit Message

**Goal:** Compose a Conventional Commits-compliant commit message that explains
why the change was made.

**Inputs:**
- Commit type and scope from Phase 3
- Description of the change and its purpose

**Actions:**

1. Compose a subject line following Conventional Commits format:
   `<type>(<scope>): <imperative summary>`
2. Subject line MUST NOT exceed 72 characters.
3. Add a blank line after the subject, then a body paragraph explaining WHY
   the change was made — not a restatement of what changed.
4. For `feat` and `fix` commits, add a `CHANGELOG:` footer line summarizing
   the user-visible impact.
5. If the commit closes an issue or references a decision, add the appropriate
   footer (`Closes #NN`, `Ref: ADR-NNNN`, etc.).
6. MUST NOT use "fix bug", "update code", "changes", or other content-free
   subject lines.

**Output:** Draft commit message reviewed and confirmed by the user before
Phase 8.

**Gate:** BLOCK if subject line exceeds 72 characters, if no body is present,
or if a `feat`/`fix` commit lacks a `CHANGELOG:` footer.

---

## Phase 8: Commit and Report

**Goal:** Execute the commit and deliver a complete commit report.

**Inputs:**
- Clean staged set from Phase 6
- Approved commit message from Phase 7

**Actions:**

1. Run the commit using the approved message. Pass the message via heredoc or
   `-m` with proper quoting — never rely on an interactive editor in an
   automated context.
2. Capture the resulting commit SHA.
3. If a pre-commit hook fails:
   - Read the hook output in full.
   - Fix the reported issue.
   - Re-stage the affected files using explicit paths (Phase 6 rules apply).
   - Create a NEW commit. MUST NOT use `--amend` after a hook failure.
4. After a successful commit, run `git status` to confirm the working tree is
   clean.
5. Deliver the commit report:
   - Commit SHA
   - Branch name
   - Files committed (explicit list)
   - Gate results (test, lint, secrets scan)
   - Commit message used

**Output:** Commit report with SHA, branch, file list, and gate results.

**Gate:** BLOCK if `git status` shows unexpected uncommitted changes after the
commit. Report the discrepancy before closing.

---

## Decision Gates Summary

| Gate         | Condition                                              | Action if blocked               |
|--------------|--------------------------------------------------------|---------------------------------|
| Phase 1 exit | No explicit user commit instruction                    | Ask for explicit confirmation   |
| Phase 2 exit | On `main`, `master`, or protected branch               | Stop; instruct user to branch   |
| Phase 3 exit | Staged set spans multiple commit types                 | Split; commit separately        |
| Phase 4 exit | Test, lint, or secrets scan not fully PASS             | Fix; rerun before continuing    |
| Phase 5 exit | Unexpected file, credential, or incomplete change      | Unstage; surface to user        |
| Phase 6 exit | Unintended file in staged set                          | Unstage extra files             |
| Phase 7 exit | Subject > 72 chars, no body, or feat/fix lacks CHANGELOG | Revise message               |
| Phase 8 exit | Hook failure or dirty working tree after commit        | Fix; new commit (never --amend) |

---

## Hard Rules

- MUST NOT commit without explicit user authorization.
- MUST NOT commit to `main`, `master`, or any protected branch.
- MUST NOT run `git add -A`, `git add .`, or wildcard staging.
- MUST NOT skip, disable, or work around any automated gate.
- MUST NOT use `--amend` after a pre-commit hook failure — create a new commit.
- MUST NOT guess test, lint, or secrets-scan commands — always read
  `${PROJECT_ROOT}/.agents/projectContext/tech-stack.md`.
- MUST NOT commit if any secrets finding is present.
- MUST NOT commit if any test is failing.

---

## Failure Modes

| Failure                                        | Response                                                      |
|------------------------------------------------|---------------------------------------------------------------|
| `tech-stack.md` missing                        | Stop; surface gap; do not guess commands                      |
| Test failure                                   | Fix before committing; never skip or suppress                 |
| Secrets finding                                | Unstage affected file; surface to user; do not commit         |
| Pre-commit hook failure                        | Fix issue; re-stage explicitly; new commit; never --amend     |
| Staged set contains unintended files           | Unstage; re-stage explicitly; re-run Phase 6                  |
| User instruction ambiguous                     | Ask for explicit confirmation; do not infer permission        |
