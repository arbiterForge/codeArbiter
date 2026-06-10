---
description: Open a pull request the only sanctioned way — clear every BLOCK-level review finding, then stage the PR. Never a direct write to the default branch.
argument-hint: (none)
---

# /ca:pr — open a pull request

The only permitted path to a pull request. Every change lands through a PR — never a direct write or force-push to the default branch. No PR is drafted while any BLOCK-level review finding stands.

## Flow

Routes to the `finishing-a-development-branch` skill, open-PR path. The orchestrator reads the current
branch, its diff against the base, and the commit log to determine what changed and which reviewers
apply, then:

1. **Confirm the commit gate cleared** this session (`commit-gate` green, or `/ca:commit` completed).
2. **Path matrix** — inspect the diff and dispatch the reviewer agents the change demands:
   - auth / crypto / middleware paths → `auth-crypto-reviewer` + `security-reviewer`
   - migration files → `migration-reviewer`
   - dependency manifests → `dependency-reviewer`
   - all paths → `coverage-auditor`
3. **Run reviewers** in parallel where there are no dependencies.
4. **BLOCK check** — any CRITICAL or HIGH finding STOPs the flow; present it and do not draft the PR.
   The user resolves, re-runs `/ca:commit`, then `/ca:pr`.
5. **Stage the PR** once all BLOCK findings clear: concise title; summary of what changed and why; a
   bulleted test plan; a conflict-hierarchy tradeoff citation for any non-obvious tradeoff; a link to
   any ADR the change implements or contradicts. Then `gh pr create`; return the URL.

## Routes to

`finishing-a-development-branch` (`${CLAUDE_PLUGIN_ROOT}/skills/finishing-a-development-branch/SKILL.md`),
open-PR path.

## When NOT to use

- Staged changes not yet committed → `/ca:commit`.
- Review a diff without opening a PR → `/ca:review`.
- A pre-implementation security pass → `/ca:threat-model`.

## Hard gate

MUST NOT open a PR while any BLOCK-level (CRITICAL or HIGH) finding is unresolved. MUST NOT skip a
reviewer the path matrix requires. MUST NOT open a PR before the commit gate ran this session. MUST
NOT open a PR, write, or force-push directly to the default branch.
