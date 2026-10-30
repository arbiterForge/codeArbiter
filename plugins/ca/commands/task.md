---
description: Add, start, or complete selected local work through its owning store.
argument-hint: "add \"<desc>\" | start <work-id|legacy-id|\"legacy title\"> | done <work-id|legacy-id|\"legacy title\">"
---

# /ca:task — selected local work writer

# Owner selection

Check whether `${CLAUDE_PROJECT_DIR}/.codearbiter/open-tasks.md` exists. When it does,
that board remains the work owner. Before a board write, resolve the installed
`hooks/work.py` through the helper card below and run `work.py list --limit 1`
from the project worktree. Continue with the legacy board procedure only when
the result says `owner: legacy`; a refusal (including two owners) stops the
write without changing either store.
When it does not, use the installed `hooks/work.py` helper for native work.
Do not create a board as a side effect of a native task command, and do not
write both stores. If the selected helper reports two owners or an unsafe
store, preserve the state and report its refusal.

For native `add`, use `work.py create --title=<description>
--intent=<description> --type unknown --operation-id <stable-request-id>`.
Pass title and intent as separate literal arguments so leading hyphens stay
data. The request ID must be newly minted for a distinct action and reused unchanged after an
uncertain result; retain it with the request until the result is known. If the task came from
a durable source, also pass `--origin <source-key>` so later sessions can
reconcile the same item. Record the returned `work_id` as the selection key.
For native `start` and `done`, require that exact `work_id`. Read it once with
`work.py get <work_id>`, then invoke `work.py start <work_id>` or `work.py
complete <work_id>` with `--operation-id <stable-request-id>`,
`--expected-revision <revision>` and `--expected-model-sha256 <model_sha256>`
from that read. Retain all three values for an exact retry after an uncertain
result. A title or dotted board ID is not a safe native selector. A conflict
reports the affected identity and must not overwrite a later update.
Read the installed helper card described below for `hooks/work.py` too, and
invoke only the resolved installed copy with the selected Python interpreter.

## Legacy board procedure

The one blessed way to mutate `${CLAUDE_PROJECT_DIR}/.codearbiter/open-tasks.md`
(resolves D-1). Hand-editing the board is no longer the only path; this command keeps
every entry schema-conformant and every transition dated. The board LOGIC lives in the
pure `_taskboardlib` transforms; this command runs the thin writer
`taskwrite.py` from the selected installed package.

Before an authorized board mutation, read the installed helper card:
[helper-invocation.md](../includes/helper-invocation.md) relative to this loaded command.


Set its loaded-resource input
to the absolute path of this **loaded** command or skill, and select the literal
relative helper `hooks/taskwrite.py`. Resolve and check that helper exactly once
using the card, then run its interpreter-selection block for the current shell.
Run from the intended project worktree so the writer targets
that project's board. Do not switch to the plugin directory, use a root token
from a hook environment in an ordinary tool call, or search source/cache copies.

## Verbs

Always put `--` before user text (a desc or title) so a value beginning with `-` is not
parsed as a flag. Use the validated Python 3 interpreter selected by the card;
never retry a refused helper under another interpreter. Keep every option before `--` and
pass user text as one literal argument.

- **add** — append a queued task. ID-less by default; pass `--id <group>.<type>` to mint
  a dotted ID now, `--from <origin>` for a harvest back-ref, `--boundaries a,b` for the
  security/trust boundaries it touches. The description must be nonblank and
  single-line; origin and boundary values must also stay on one line.
  - Invoke the resolved helper with `add [--id group.type] [--from origin] [--boundaries a,b] -- <desc>`.
- **start** — flip a task to in-progress and **stamp the started date** (so it can never
  be a dateless `[~]`). On an ID-less item, pass `--as <group>.<type>` to mint its dotted
  ID at pick-up. `--date YYYY-MM-DD` overrides today.
  - Invoke the resolved helper with `start [--as group.type] [--date YYYY-MM-DD] -- <id|title>`.
- **done** — flip an in-progress task to done and stamp the done date (`--date`
  overrides today). A queued task must be `start`ed first.
  - Invoke the resolved helper with `done [--date YYYY-MM-DD] -- <id|title>`.

The following are literal minimal `add` invocations after the installed helper
and interpreter have been resolved. Bind the named text variable to the exact
caller-supplied description; do not paste that text into the command syntax.

### PowerShell add invocation
```powershell
& $caPython -B $caHelper add -- $caDescription
if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
```

### POSIX add invocation
```sh
"$ca_python" -B "$ca_helper" add -- "$ca_description"
```

When `add` needs fields, bind each value separately and keep all options before
`--`. Use the `--from=<value>` form if the origin begins with a hyphen. These
examples preserve quotes, metacharacters, and non-ASCII description text as
one argument; neither shell evaluates the variable's contents as a command.

### PowerShell add with options
```powershell
$caAddArgs = @('add', '--id', $caId, "--from=$caOrigin", '--boundaries', $caBoundaries, '--', $caDescription)
& $caPython -B $caHelper @caAddArgs
if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
```

### POSIX add with options
```sh
"$ca_python" -B "$ca_helper" add --id "$ca_id" "--from=$ca_origin" --boundaries "$ca_boundaries" -- "$ca_description"
```

For `start` and `done`, replace only the verb and its literal option array,
keeping the same resolved helper and `--` before the one title or ID argument.

A missing target, an already-matching state, an out-of-order transition, a malformed
add field or `--date`, or an invalid `GROUP.TYPE` namespace is reported and writes
nothing (exit 1).
A queued `done` identifies the task as queued and tells the caller to `start` it first.
**Targeting by title is best-effort:**
prefer the dotted ID, and
note that if two ID-less items share a title, `start`/`done` act on the first — give one
an ID (`/ca:task start --as <group>.<type> -- "<title>"`) to disambiguate.

## When NOT to use

- Promoting workflow follow-ups in bulk → that is the harvest
  (`${CLAUDE_PLUGIN_ROOT}/includes/harvest.md`), which calls this writer for you.
- Reading the board / counts → `/ca:status` (read-only).
- Archiving long-settled done items → `/ca:standup` owns the sweep (D-2,
  resolved 2026-07-31). It proposes dated complete work strictly more than 14
  calendar days old through the selected owner, then archives only the user's
  named subset on a dedicated branch. Native items use `work.py`; origin-backed
  legacy rows also use `work.py`, while exact-ID originless rows remain with
  `taskwrite.py`. Undated done items are never proposed automatically; standup's
  explicit-request and `--allow-undated` rules apply. Declined items stay put.
- Filing a separate `chore(board)` PR just to flip a task state → task-board transitions
  (`[x]` done-flip, `[~]` start-flip, new `[ ]` add) ride the **work commit** via
  commit-gate, co-located atomically with the code that completes, starts, or spawns the
  task (ADR-0008). A lagging board-only PR is the anti-pattern this design eliminates.

## Hard gate

- MUST write the board only through `taskwrite.py` (the pure transforms), never a
  free-hand Edit that can malform the schema.
- `start` MUST stamp a started date — never leave a dateless `[~]`.
- `done` MUST target an in-progress task — a queued task must go through `start` first.
- MUST NOT delete a task to "complete" it — mark it `done` so the record survives.
