---
description: Wire codeArbiter's statusline into ~/.claude/settings.json, or remove it.
argument-hint: "install | uninstall | status"
---

# /ca:statusline — wire-up

A plugin cannot own a `statusLine`, and `${CLAUDE_PLUGIN_ROOT}` is not expanded inside
`settings.json`. So the renderer at `${CLAUDE_PLUGIN_ROOT}/hooks/statusline.py` is wired in by
resolving its absolute path at install time and writing it to the user's `statusLine.command`. The
backing script `${CLAUDE_PLUGIN_ROOT}/hooks/wire-statusline.py` performs the surgery deterministically
and never clobbers a settings file it cannot parse.

The renderer is global — its usage box (folder, git, model, rate limits, context, cumulative tokens,
API-equivalent cost, per-call token burn) renders in every repo. The arbiter segments
(`stage · tasks · q · over`) light up only where `.codearbiter/CONTEXT.md` sets `arbiter: enabled`.

Token and cost figures are reconstructed from the transcripts on disk: the parent session transcript
and every delegated subagent transcript under it. Each request is counted once, even when streaming
snapshots or forked subagents replay it. The dollar figure is the estimated pay-as-you-go
**API-equivalent**, meaning what the same tokens would have cost at the list API rates shipped with
codeArbiter. It is not a bill, and it is not what a subscription charges. Each Session and Today
figure carries its own label:

- `api≈$N` — every observed request was priced, so the figure is complete.
- `api≥$N` — a lower bound. Some usage could not be priced (an unknown model, tool, or price
  modifier), or the scanner is still catching up on a large transcript. The number only rises as
  coverage improves.
- `api≈?` — no defensible dollar figure: nothing has been reconstructed yet (grey), or usage exists
  but none of it could be priced (amber). The renderer never shows a precise number it cannot stand
  behind.
- `host≈$N` — Session only, and only when reconstruction is unavailable: Claude Code's own session
  estimate, the highest value it has reported. It is never mixed with `api` figures and never
  used for Today.
- A trailing `*` marks a stale figure. That render could not take the ledger lock, so it showed
  the last committed totals instead of zeros.

In a narrow box the words drop and the symbol stays (`≈$N`, `≥$N`, `h≈$N`), so a figure is never
cut off mid-number.

The statusline refreshes only when Claude Code redraws it, and codeArbiter adds no timer. Work that a
render defers (bounded reads on a large backlog) is never lost. It resumes on the next redraw, and
until then the figure reads `api≥`. The per-call burn sparkline tracks the parent session's own
requests only. Subagent usage counts toward the totals but not toward burn.

Each visible subagent row reports its recorded model. Claude IDs retain a compact family/version
label such as `model:sonnet-4-6`; multiple models report `model:mixed`, while absent or malformed
metadata reports `model:?`. The tag uses the active theme's bright accent, with no model-specific
colors.

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

   The script REFUSES to wire a plugin root that will not outlive the session — a git worktree, for
   instance. `settings.json` is global and the pin is absolute, so a worktree path breaks the
   statusline the moment that checkout is pruned. On a refusal, report it verbatim and re-run from
   the real install (the plugin cache, or the main checkout) rather than working around it.

3. **uninstall** — restore the backed-up line, or remove `statusLine` entirely if none existed.
   Never blocked, wherever it is run from — a user stuck with a dead pin must be able to clear it.

4. **status** — report the current `statusLine.command`, whether it is codeArbiter's, and any backup
   on file. Changes nothing.

5. Report the script's output verbatim, then state what changed. If install succeeded, tell the user
   the statusline takes effect on the next render (a new prompt or session). Tip: `CODEARBITER_COMPACT=1`
   drops the subagent rows; `CODEARBITER_STATUSLINE=off` disables it; `CODEARBITER_WIDTH`
   sets the box width.

## Hard gate

MUST NOT edit `~/.claude/settings.json` by hand for this — the backing script is the only sanctioned
path, so the backup/restore contract holds. MUST NOT proceed with `install` without first surfacing
the resolved command to the user and getting a go-ahead.
