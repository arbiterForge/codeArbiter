---
entity: commands/arbiter
related: [dev]
gates:
  - gate: append-only audit
    when: exiting dev mode
    effect: an exit line is appended to overrides.log and the dev-active marker is removed before orchestration resumes
---

## What it does

The exit door for `/ca:dev`: it ends the maintainer override and restores normal orchestration.
It writes the exit line to `.codearbiter/overrides.log` before anything else, removes the
gitignored dev-active marker so the statusline drops out of alarm-red, then re-presents the
startup state — current stage, any blocking `[CONFIRM-NN]`, in-flight tasks — and waits for a
slash command with routing, gates, and skills all back in force. If dev mode wasn't active, this
command is a no-op.

If a prior session ended mid-dev, SessionStart already appended a synthetic close line
(`BY: session-cleanup | DEV: exit`) and cleared the marker for that orphaned entry; this command
does not write a second exit line for it.

## Usage

```
/ca:arbiter
```

Takes no arguments.

## Example

```text
> /ca:arbiter

[2026-07-02T14:41:03Z] | BY: dev@example.com | DEV: exit
dev-active marker removed; statusline back to normal.

stage: implementation · tasks: 2 open · q: 0 · overrides: 1 since last checkpoint
Orchestration restored. Awaiting a command.
```
