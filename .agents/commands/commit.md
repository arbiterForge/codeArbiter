# /commit

## Purpose

Run the full commit gate before any `git commit` command executes. This command invokes the `commit-gate` skill (all 8 phases). No direct git commands are issued by codeArbiter without the skill completing first. "It looks good" is not permission to commit.

## Usage

```
/commit
```

No arguments. The commit-gate skill reads the current git state (staged files, diff, test results) and determines whether all gates are green.

## Routes To

`commit-gate` skill (`.agents/skills/commit-gate/SKILL.md`) — all 8 phases.

## What the Skill Does (8 Phases)

The `commit-gate` skill runs these phases in order — **all must pass**:

1. **Staged content check** — verifies staged files contain no secrets, no banned patterns, no accidentally staged files (e.g., `.env`, lock files that shouldn't change)
2. **Test gate** — runs the full test suite using the command in `projectContext/tech-stack.md`; MUST be green
3. **Coverage gate** — checks coverage meets the threshold for the current stage (read from `projectContext/stage`)
4. **Lint gate** — runs the lint command from `projectContext/tech-stack.md`; MUST be clean
5. **Type-check gate** — runs type-check command if applicable; MUST be clean
6. **Security scan** — runs secrets scan against staged diff; BLOCK on any secret
7. **Commit message check** — verifies message is present, meaningful, and follows project conventions from `projectContext/coding-standards.md`
8. **Final confirmation** — all 7 phases green; outputs commit command for user to confirm

## Hard Gates

- MUST NOT execute `git commit` without all 8 phases green
- MUST NOT skip, bypass, or `continue-on-error` any phase
- If test suite is not green: STOP, surface the failing tests, do not proceed
- If a secret is found in staged diff: STOP, surface the finding, do not proceed
- If coverage is below the stage threshold: STOP, surface the gap, do not proceed
- "The tests were green a moment ago" is NOT sufficient — tests must run in this session

## After All Gates Pass

The skill outputs:
- Summary of what was verified
- Proposed commit message
- The exact `git commit` command

The user must confirm before the commit executes.

## When NOT to Use

- Before writing code: use `/feature` or `/fix` first
- To check PR readiness: use `/pr` — it runs additional BLOCK-level reviews
- To run tests without committing: run the test command from `projectContext/tech-stack.md` directly
