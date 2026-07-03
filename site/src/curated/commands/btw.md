---
entity: commands/btw
related: [commands, feature]
---

## What it does

The one exception to codeArbiter's slash-command pipeline: a lightweight question-and-answer
channel that reads project context and answers, then returns control. No skill is routed to, no
agent is dispatched, no file changes. It is always safe to invoke, even mid-gate or mid-override,
because it never touches state.

Ask it anything about the repo's current shape — what stage a spec is in, what a hook does, why a
prior decision was made — and it answers directly from `.codearbiter/` (`CONTEXT.md`,
`tech-stack.md`, `coding-standards.md`, `security-controls.md`, decisions, specs, plans) instead of
guessing. If the answer to the question isn't in that context, it says so rather than
fabricating one.

## Usage

```
/ca:btw <question>
```

The question is free text; there is no other argument shape.

## Example

```text
> /ca:btw why does commit-gate block a wildcard git add?

H-03 in pre-bash.py blocks `git add -A` / `.` / `--all` / `-u` and any pathspec
that stages a non-explicit file set. The rule exists so a commit only ever
contains what was reviewed — a wildcard stage can silently pull in an
unrelated in-progress edit. Stage files explicitly, one path per file
(see the commit-gate skill).
```

## When to reach for it

A request to build or fix something is out of scope here — `/ca:btw` names the
question-only boundary and points to `/ca:feature` or `/ca:fix` instead of starting work.
