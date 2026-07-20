---
entity: commands/task
related: [status, standup]
gates:
  - gate: writer-only mutation
    when: any add, start, or done invocation
    effect: the write goes through the taskwrite.py transforms only, never a free-hand edit — a malformed target, an already-matching state, or a bad --date is reported and writes nothing
---

## What it does

The only blessed way to mutate `.codearbiter/open-tasks.md`. It runs a thin writer over pure
board-transform logic, which keeps every entry schema-conformant and every transition dated —
`start` always stamps a started date so a task can never sit as a dateless in-progress item.
Board-only PRs filed just to flip a task's state are the anti-pattern this command eliminates: a
task's done-flip, start-flip, or new-task add is meant to ride the same commit as the work it
tracks.

## Usage

```
/ca:task add "<desc>" | start <id|"title"> | done <id|"title">
```

`add` appends a queued task (optionally minting a dotted ID with `--id`); `start` flips a task to
in-progress and stamps today's date (or mints an ID at pick-up with `--as`); `done` flips a task to
done and stamps the done date. Targeting by title is best-effort — prefer the dotted ID once one
exists.

## Example

```text
> /ca:task done poc.docs.0001

Flipped poc.docs.0001 to done, dated 2026-07-02.
open-tasks.md updated via taskwrite.py.
```

## When to reach for it

Any board write — adding, starting, or completing a task. To just read the board and its counts,
use `/ca:status` instead; it's read-only.
