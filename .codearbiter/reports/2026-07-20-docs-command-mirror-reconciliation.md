# Docs command mirror reconciliation - 2026-07-20

Scope: compare the canonical `task` and `standup` command contracts with their
curated docs-site pages after commit-gate board-transition co-location. This is
a semantic reconciliation, not a byte-identity requirement; curated pages use
the public documentation template rather than the command-source layout.

## Sources

| Command | Canonical source | Curated mirror |
| --- | --- | --- |
| task | `plugins/ca/commands/task.md` | `site/src/curated/commands/task.md` |
| standup | `plugins/ca/commands/standup.md` | `site/src/curated/commands/standup.md` |

## Evaluation contract

The `task` mirror must state that:

1. board mutations go through `taskwrite.py`, never free-hand edits;
2. lifecycle transitions are dated; and
3. task adds, starts, and completions ride the work commit instead of a
   board-only PR.

The `standup` mirror must state that:

1. the board-drift sweep is advisory and read-only;
2. standup never auto-flips a task; and
3. an operator resolves drift through the sanctioned `task done` command.

Record the introducing commit dates for the board-sync source contract and the
curated pages. If the mirrors predate or omit any required semantic, update the
curated page. If they postdate the source change and already carry every
semantic, record the task as stale-complete without rewriting equivalent prose.
