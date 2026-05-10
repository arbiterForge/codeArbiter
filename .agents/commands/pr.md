# /pr

## Purpose

Stage a pull request after all BLOCK-level reviews clear. No PR is drafted until every BLOCK-level finding is resolved. After all BLOCK findings are cleared, codeArbiter stages the PR with title, summary, test plan, and link.

## Usage

```
/pr
```

No arguments. codeArbiter reads the current branch, its diff against the base branch, and the commit log to determine what changed and which reviewers to invoke.

## Routes To

`pr-ready` check sequence (see below), then `gh pr create` or equivalent.

## What Happens Step by Step

1. **Commit gate verified** — all commit-gate phases must be green (or `/commit` must have completed this session)
2. **Path matrix check** — codeArbiter inspects the diff to determine which reviewer agents apply:
   - Auth/crypto/middleware paths → `auth-crypto-reviewer` + `security-reviewer` (BLOCK-level)
   - Audit event paths → `audit-emitter` (BLOCK-level)
   - Migration files → `migration-reviewer` (BLOCK-level)
   - Dependency files → `dependency-reviewer` (BLOCK-level)
   - Trust zone crossing code → `trust-zone-reviewer` (BLOCK-level)
   - All paths → `test-audit-reviewer` + `standards-compliance-reviewer` (BLOCK-level)
3. **All reviewer agents run** — in parallel where there are no dependencies
4. **BLOCK finding check** — if any CRITICAL or HIGH finding is raised: STOP, present finding to user, do not proceed to PR draft
5. **User resolves BLOCK findings** — user addresses each finding and re-runs `/commit`, then `/pr`
6. **PR draft staged** — after all BLOCK findings cleared:
   - Title: concise, describes the change
   - Summary: what changed, why, what was tested
   - Test plan: bulleted checklist of what was tested
   - Non-obvious tradeoff citation (per `AGENTS.md` conflict resolution tier)
   - Link to relevant ADR(s) if the change implements or contradicts an architectural decision
7. **`gh pr create` executed** — PR is opened; URL returned to user

## PR Body Structure

```
## Summary
<1-3 bullets: what changed and why>

## Test plan
- [ ] <specific test or verification step>
- [ ] <specific test or verification step>

## Tradeoff citation (if applicable)
Level N — <brief description of tradeoff and why it was made at this level>

## Related decisions
ADR-NNNN — <title> (if applicable)
```

## Hard Gates

- MUST NOT open a PR if any BLOCK-level finding (CRITICAL or HIGH severity) is unresolved
- MUST NOT skip any reviewer agent required by the path matrix
- MUST NOT open a PR if the commit gate has not been run this session
- MUST NOT open a PR to `main` or `master` directly — branch must differ from target branch
- If `security-reviewer` raises a CRITICAL finding: all work halts until user resolves

## When NOT to Use

- To commit staged changes first: use `/commit`
- To review a specific file or diff without opening a PR: use `/review`
- To run a threat model before implementation: use `/threat-model`
