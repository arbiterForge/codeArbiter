---
entity: commands/pr
related: [commit, watch, skills/finishing-a-development-branch]
gates:
  - gate: commit gate cleared
    when: before a PR is drafted
    effect: the commit gate must have already passed this session; a PR is not the place to catch up on skipped verification
  - gate: path-matrix review dispatch
    when: after the commit gate check
    effect: the diff decides which reviewers run — auth/crypto paths, migrations, dependency manifests each pull in a dedicated reviewer, and a coverage check always runs
  - gate: BLOCK check
    when: after reviewers report
    effect: any CRITICAL or HIGH finding stops the PR from being drafted until you resolve it
---

## What it does

This is the only path to opening a pull request — there's no direct push or force-push to the
default branch anywhere in the system. Before anything gets drafted, it confirms the commit gate
already ran clean this session, then looks at what actually changed to decide which reviewers need
to weigh in: touching authentication or crypto code pulls in a security-focused pass, a migration
file pulls in a migration reviewer, a changed dependency manifest pulls in a supply-chain check, and
a coverage check runs on every PR regardless. Any finding at CRITICAL or HIGH severity stops the
draft cold until it's addressed. Once everything clears, the PR itself gets written with a real
summary, a test plan, and links to any decision record it touches — then, if you've opted into CI
babysitting, a watcher attaches to follow the checks through to green.

On Codex, the dispatched reviewers execute inline in the current thread rather than through
isolated `Task`-tool dispatch — see [Claude Code + Codex → Intentional host
differences](/getting-started/claude-code-and-codex/#intentional-host-differences).

## Usage

```
/ca:pr
```

Takes no arguments — it reads the current branch, its diff against the default branch, and the
commit history to determine what changed.

## Example

```text
> /ca:pr

commit-gate: confirmed clean this session.
Diff touches: src/auth/session.ts, src/auth/session.test.ts.
Path matrix: auth path detected — dispatching auth-crypto-reviewer and security-reviewer.
Dispatching coverage-auditor (all paths).
Reviewers report: 0 CRITICAL, 0 HIGH, 1 LOW (naming suggestion, non-blocking).
Drafting PR: "fix(auth): rotate session token on privilege change"...
PR opened: https://github.com/org/repo/pull/482
CODEARBITER_BABYSIT is off — no CI watcher attached. Run /ca:watch to follow it manually.
```

## When to reach for it

Reach for `/ca:pr` once work is committed and you're ready to open it for review. If changes are
still only staged, run `/ca:commit` first; to review a diff without opening a PR, use `/ca:review`.
