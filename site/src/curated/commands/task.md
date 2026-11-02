---
entity: commands/task
related: [status, standup]
use_when: "You need to add, start, complete or reopen a piece of local work, in a native project or on a legacy board."
avoid_when: "Only reading the board and its counts, which is `/ca:status`; or archiving finished work, which is `/ca:standup`."
asks: "The action and, for start, done and reopen, the WORK-ID that the listing returned; add takes a description. Select work by its returned WORK-ID, not by a title or a dotted legacy ID."
produces: "One lifecycle change (add, start, complete or reopen) saved through the work helper in the store the project already uses, native work or the legacy board. New work gets a stable WORK-ID. It records local progress only, and archiving is left to `/ca:standup`."
gates:
  - gate: one owner, no hand edits
    when: any add, start, done or reopen
    effect: the change goes through the work helper to the single selected owner, never a hand edit and never two owners for one action; a mixed or unsafe store or an ambiguous selection is reported as a stop, not worked around by switching writers
---

## What it does

Adds, selects, starts, completes or reopens local work through the one store that owns it. The
command runs the installed `hooks/work.py` helper, which selects the project's current owner, gives
new work a stable `WORK-ID`, and performs a single action through that owner. A project with a
legacy board stays on that board until it is explicitly adopted into native work. The command never
creates a board beside native work, never writes both owners for one action, and never edits either
store by hand.

A start, a completion or a new piece of work is meant to ride the same commit as the work it
tracks. A separate `chore(board)` pull request for an ordinary transition is the anti-pattern,
because it can claim progress before the work lands.

## Usage

```
/ca:task add <description> | list | start <WORK-ID> | done <WORK-ID> | reopen <WORK-ID>
```

- `list` pages through the listing until the item is found or the listing ends. The selected item
  is then read by its returned `WORK-ID`. If nothing matches, or the selection is ambiguous, the
  command stops and reports it.
- `add` creates new work from your description with the type `unknown` and returns its `WORK-ID`.
  Use that ID for every later action. When the work comes from a durable source, the source key is
  recorded as its origin.
- `start`, `done` and `reopen` take the returned `WORK-ID`, never a title or a dotted legacy ID.
  Queued work that was already performed can be recorded complete directly, with no invented start
  event. `done` records local progress only: checks stay unknown until their evidence is assessed,
  and it is not remote sync or delivery.

Every change carries a stable request ID. A new action gets a new one, and an uncertain retry keeps
the original so the change is not applied twice. When the caller already holds the item's preimage,
it is passed with the change: native work checks its revision and model hash, and a legacy board
checks its board hash and refuses a stale one, even one that was already applied. Inspect the
selected row before acting again. A changed item is never overwritten by minting a fresh request ID.

In a native project that has configured a transition map, starting, completing or reopening work
also saves the configured issue and Project intent, or a specific waiting reason, in the same local
transaction. That makes no GitHub request. Mapped targets are sent only when you explicitly ask for
it, and each target reports separately.

## Archiving and historical rows

`/ca:task` has no archive action. `/ca:standup` owns archival: it proposes completed work for a
named subset you choose, and it preserves undated historical rows. Native items are archived through
`work.py`, and legacy rows through `taskwrite.py`.

A historical legacy row that cannot be selected by a stable `WORK-ID`, including an originless row
that has a dotted ID, is an explicit compatibility or repair path through `hooks/taskwrite.py`.
Inspect the exact row first, then use its dotted ID, or the unique title for a row with no ID. That
is not the normal route for ordinary work.

## Example

```text
Illustrative exchange, not captured execution:
> /ca:task add "Update the contributor guide"

Created the work through the project's store. Its WORK-ID is <the ID the helper returns>.

> /ca:task start <WORK-ID>

Started. The change was saved through the work helper, under a new request ID.
```
