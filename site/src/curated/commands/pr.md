---
entity: commands/pr
related: [commit, watch, skills/finishing-a-development-branch]
gates:
  - gate: current-head readiness
    when: before a PR is drafted
    effect: applicable tests, secrets scanning and specialized review cover the actual base-to-HEAD diff; missing or failing checks remain pending
  - gate: path-matrix review dispatch
    when: assessing the current branch
    effect: auth/crypto, CI/deploy/infrastructure, migration and dependency paths select their required reviewers, and a coverage check always runs
  - gate: BLOCK check
    when: after reviewers report
    effect: any CRITICAL or HIGH finding stops the PR from being drafted until you resolve it
---

## What it does

Explicit PR entry and a direct request to open a PR use the same branch-finishing owner.
Neither permits a direct push or force-push to the default branch. It establishes current-head
readiness from the actual base-to-HEAD diff, including secrets scanning and specialized checks
against that same subject. Reuse applicable observed results while source and inputs match, and
run missing or affected checks. An empty index does not establish branch readiness, and preparing
an already committed branch does not require a new commit.

The diff selects the required reviewers: authentication, crypto and CI/deploy/infrastructure
changes pull in security review, a migration
file pulls in a migration reviewer, a changed dependency manifest pulls in a supply-chain check, and
a coverage check runs on every PR regardless. Any finding at CRITICAL or HIGH severity stops the
draft cold until it's addressed. Once everything clears, the PR itself gets written with a real
summary, a test plan, and links to any decision record it touches — then, if you've opted into CI
babysitting, a watcher attaches to follow the checks through to green.

Unfinished plan work and pending verification remain explicit. An artifact acceptance receipt is
not a prerequisite for an ordinary authorized PR. Opening leaves the PR open; merge and discard
require explicit authority. Exact-head hosted CI must pass before an authorized merge.

Published releases from 0.7.5 include each packaged reviewer resource charter for Codex
host-provided agent threads. Exact static-package and route-closure checks gate release. A bounded
0.9.4 receipt proves one exact installed-charter review. The inline fallback applies only where the
canonical workflow explicitly permits it and isolation is not mandatory. See
[Claude Code + Codex → Intentional host
differences](/getting-started/claude-code-and-codex/#intentional-host-differences).

## Usage

```
/ca:pr ["title"]
/ca:pr --watch [PR]
/ca:pr --cleanup
```

An optional title selects the open-PR path, as does asking to open a PR directly; you
are not asked to choose the branch's fate again. With no title, the owner derives it
from the current branch, diff and commit history.

The mutually exclusive flags select existing lifecycle operations before creation
preflight: `--watch` follows the watcher, and `--cleanup` follows post-merge cleanup.
Neither creates a PR or requires a fresh creation gate just to enter its own flow.
Bare or quoted titles named `watch` or `cleanup` stay titles, not flags. Merge and
discard still require explicit authority and their applicable proof.

## Example

```text
> /ca:pr

Current-head checks cover the base-to-HEAD diff; tests and secrets scan passed.
Diff touches: src/auth/session.ts, src/auth/session.test.ts.
Path matrix: auth path detected — dispatching auth-crypto-reviewer and security-reviewer.
Dispatching coverage-auditor (all paths).
Reviewers report: 0 CRITICAL, 0 HIGH, 1 LOW (naming suggestion, non-blocking).
Drafting PR: "fix(auth): rotate session token on privilege change"...
PR opened: https://github.com/org/repo/pull/482
CODEARBITER_BABYSIT is off — no CI watcher attached. Run /ca:watch to follow it manually.
```

## When to reach for it

Reach for `/ca:pr` when you're ready to propose the branch for integration. Authorized uncommitted
work uses the commit owner first. To review a diff without opening a PR, use `/ca:review`.
