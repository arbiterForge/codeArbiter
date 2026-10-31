---
description: Add, select, start, complete, or reopen local work through its owning store.
argument-hint: "add <description> | list | start <WORK-ID> | done <WORK-ID> | reopen <WORK-ID>"
---

# /ca:task — selected local work

Use the installed `hooks/work.py` facade for ordinary work in both native and
legacy projects. It selects the current owner, gives new work a stable `WORK-ID`,
and performs one semantic action through that owner. Existing boards stay
legacy until an explicit adoption. Do not create a board beside native work or
write both owners. A mixed or unsafe store is a refusal to report, not a reason
to switch writers.

Before invoking the helper, read the installed helper card:
[helper-invocation.md](../includes/helper-invocation.md) relative to this loaded command.


Use this loaded command or skill as the card's resource input and resolve
`hooks/work.py` exactly once. Run it with the card's selected Python interpreter
from the intended project worktree. Keep caller text in literal arguments; do
not interpolate it into shell syntax or search for a source/cache copy.

## Ordinary actions

- **List or select:** `work.py list --limit 32`, then `work.py get <WORK-ID>`
  for the selected item. Use the returned `work_id`, not a title or dotted
  legacy alias. If the item is absent or selection is ambiguous, stop and
  report it.
- **Add:** `work.py create --title <description> --intent <description>
  --type unknown --operation-id <stable-request-id>`. Pass `--origin <source-key>`
  when work comes from a durable source. A distinct action gets a new request
  ID; an uncertain retry keeps the original ID. Use the returned `work_id` for
  later actions.
- **Start:** `work.py start <WORK-ID> --operation-id <stable-request-id>`.
- **Complete:** `work.py complete <WORK-ID> --operation-id <stable-request-id>`.
  Queued work already performed can be recorded complete directly. Do not
  invent a start event. This records local progress; checks remain unknown
  until their actual evidence is assessed.
- **Reopen:** `work.py reopen <WORK-ID> --operation-id <stable-request-id>`.

For a create, bind the caller's description and stable request ID as separate
variables after resolving the installed helper and interpreter from the card.
Pass each value as a literal argument from the intended worktree. A distinct
intent may be bound separately when its wording differs from the title.

### PowerShell create invocation
```powershell
$caCreateArgs = @('create', '--title', $caDescription, '--intent', $caDescription, '--type', 'unknown', '--operation-id', $caRequestId)
& $caPython -B $caHelper @caCreateArgs
if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
```

### POSIX create invocation
```sh
"$ca_python" -B "$ca_helper" create --title "$ca_description" --intent "$ca_description" --type unknown --operation-id "$ca_request_id"
```

The facade reads the selected revision for an ordinary update and applies the
owner's exact change check. When a caller already holds the preimage, pass
`--expected-revision` and `--expected-model-sha256` together for native work,
or `--expected-model-sha256` with the returned board hash for legacy work.
Keep the same request ID and preimage for an exact retry after an uncertain
result. A changed item is a conflict to inspect; do not overwrite it by
minting a fresh request ID.

For a historical ID-less board row that cannot be selected through a stable
`WORK-ID`, `hooks/taskwrite.py` remains an explicit compatibility or repair
path. Inspect the exact row and use its documented selector and board lock;
do not teach best-effort title matching as the normal /task route. Direct
board edits remain invalid.

## Related owners

- Harvest promotes selected follow-ups through the current work owner.
- `/ca:standup` owns archival. It uses selected native work or the
  legacy writer as appropriate and preserves undated historical rows.
- Work lifecycle changes ride their associated work commit under ADR-0008;
  do not open a separate board-only PR to make progress appear complete.

## Hard gate

- Never hand-edit the legacy board or a native work model.
- Never write two work owners for one action or silently adopt a board.
- Preserve the selected identity, real host stop, exact change check, and
  original request ID on an uncertain retry.
- Do not equate local completion with passed checks, remote sync, or delivery.
