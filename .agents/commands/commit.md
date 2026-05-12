# /commit

## Purpose

Run the full commit gate before any `git commit`. No direct git commands are issued by codeArbiter without the `commit-gate` skill completing first. "It looks good" is not permission to commit.

## Usage

```
/commit
```

No arguments. The skill reads current git state (staged files, diff, test results) and determines whether all gates are green.

## Routes To

`commit-gate` skill (`.agents/skills/commit-gate/SKILL.md`) — all phases. Skill is canonical for phases, gates, and output format.

## When NOT to Use

- Before writing code: use `/feature` or `/fix` first
- To check PR readiness: use `/pr` — runs additional BLOCK-level reviews
- To run tests without committing: run the test command from `projectContext/tech-stack.md` directly
