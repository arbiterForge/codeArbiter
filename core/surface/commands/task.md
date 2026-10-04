---
description: The sanctioned task-board mutator — add a queued task, start one (flips to in-progress and stamps the date, minting a dotted ID on pick-up), or mark an in-progress task done. The only blessed write to open-tasks.md.
argument-hint: "add \"<desc>\" | start <id|\"title\"> | done <id|\"title\">"
---

# {{CMD:task}} — task-board writer

The one blessed way to mutate `{{PROJECT_DIR}}/.codearbiter/open-tasks.md`
(resolves D-1). Hand-editing the board is no longer the only path; this command keeps
every entry schema-conformant and every transition dated. The board LOGIC lives in the
pure `_taskboardlib` transforms; this command runs the thin writer
`taskwrite.py` from the selected installed package.

Before an authorized board mutation, read the installed helper card:
{{IF:claude}}[helper-invocation.md](../includes/helper-invocation.md) relative to this loaded command.{{END}}
{{IF:codex}}`{{PLUGIN_ROOT}}/includes/helper-invocation.md` relative to this loaded skill.{{END}}
{{IF:pi}}[helper-invocation.md](../../includes/helper-invocation.md) relative to this loaded skill.{{END}}
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
an ID (`{{CMD:task}} start --as <group>.<type> -- "<title>"`) to disambiguate.

## When NOT to use

- Promoting workflow follow-ups in bulk → that is the harvest
  (`{{PLUGIN_ROOT}}/includes/harvest.md`), which calls this writer for you.
- Reading the board / counts → `{{CMD:status}}` (read-only).
- Archiving long-settled done items → `{{CMD:standup}}` owns the sweep (D-2,
  resolved 2026-07-31). It proposes dated done items strictly more than 14 calendar
  days old and requires a separate yes for each item before invoking
  the same installed `taskwrite.py` with `archive <id>`. This is the helper's
  archive verb, not a new public `{{CMD:task}} archive` mode. Undated done items are never
  proposed automatically; standup's explicit-request and `--allow-undated` rules
  apply. Declined items stay on the board.
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
