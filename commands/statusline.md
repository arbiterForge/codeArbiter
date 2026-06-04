---
description: Wire codeArbiter's statusline into ~/.claude/settings.json, or remove it.
argument-hint: install | uninstall | status
---

# /ca:statusline — wire-up

A plugin cannot own a `statusLine`, and `${CLAUDE_PLUGIN_ROOT}` is not expanded inside
`settings.json`. So the renderer at `${CLAUDE_PLUGIN_ROOT}/hooks/statusline.py` is wired in by
resolving its absolute path at install time and writing it to the user's `statusLine.command`. The
backing script `${CLAUDE_PLUGIN_ROOT}/hooks/wire-statusline.py` performs the surgery deterministically
and never clobbers a settings file it cannot parse.

The renderer is global — its usage box (folder, git, model, rate limits, context, tokens, cost, burn)
renders in every repo. The arbiter segments (`stage · tasks · q · over`) light up only where
`.codearbiter/CONTEXT.md` sets `arbiter: enabled`.

## Argument

`$ARGUMENTS` is one of `install` (default), `uninstall`, or `status`.

## Procedure

1. Run the backing script with the requested action, passing the resolved plugin root so the absolute
   path is written correctly:

   ```
   python "${CLAUDE_PLUGIN_ROOT}/hooks/wire-statusline.py" <action> --plugin-root "${CLAUDE_PLUGIN_ROOT}"
   ```

   On non-Windows hosts the interpreter token defaults to `python3`; override with `--interp` only if
   neither `python` nor `python3` is the wanted interpreter.

2. **install** — back up any existing `statusLine` to `_codearbiterStatuslineBackup`, then set
   `statusLine.command` to `<python> "<abs>/hooks/statusline.py"`. Re-running install after a plugin
   upgrade just refreshes the path; it does not overwrite the backup. **Before running install,
   show the user the resolved command and the prior line it will back up, and confirm.** Editing the
   user's global settings is their call, not yours.

3. **uninstall** — restore the backed-up line, or remove `statusLine` entirely if none existed.

4. **status** — report the current `statusLine.command`, whether it is codeArbiter's, and any backup
   on file. Changes nothing.

5. Report the script's output verbatim, then state what changed. If install succeeded, tell the user
   the statusline takes effect on the next render (a new prompt or session). Tip: `CODEARBITER_COMPACT=1`
   drops the burn/reset/subagent rows; `CODEARBITER_STATUSLINE=off` disables it; `CODEARBITER_WIDTH`
   sets the box width.

## Hard gate

MUST NOT edit `~/.claude/settings.json` by hand for this — the backing script is the only sanctioned
path, so the backup/restore contract holds. MUST NOT proceed with `install` without first surfacing
the resolved command to the user and getting a go-ahead.
