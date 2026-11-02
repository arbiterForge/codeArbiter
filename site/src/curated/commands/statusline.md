---
entity: commands/statusline
related: [doctor]
use_when: "You want codeArbiter's status line wired into your Claude Code settings, removed again, or checked."
avoid_when: "Checking overall install health, which is `/ca:doctor`; this command covers only the status line wiring."
asks: "Which action to run: `install` (the default), `uninstall` or `status`. Before installing, it shows the resolved command and the existing line it will back up, and waits for your confirmation."
produces: "An edited `~/.claude/settings.json` with a backup of any existing `statusLine`, or the original restored on uninstall. `status` only reports."
---

## What it does

Wires codeArbiter's renderer into `~/.claude/settings.json`, or removes it. A plugin can't own a
`statusLine` directly and `${CLAUDE_PLUGIN_ROOT}` isn't expanded inside `settings.json`, so this
command resolves the renderer's absolute path and writes it in. It's the only sanctioned way to
make that edit: the backing script backs up any existing `statusLine` before overwriting it
(so `uninstall` can restore it later), and it never clobbers a settings file it can't parse.

The renderer itself is global — folder, git, model, rate limits, context, cumulative tokens, and
an estimated API-equivalent cost render in every repo. The arbiter-specific segments (stage,
tasks, open questions, overrides) show up only in a repo that has opted in via CONTEXT.md
frontmatter. Token and cost figures are reconstructed from the session transcript and its
subagent transcripts, each request counted once. The cost is an estimated pay-as-you-go
equivalent, not a bill, and its label says how complete it is: `api≈` complete, `api≥` a lower
bound, `api≈?` no defensible figure, `host≈` Claude Code's own estimate (Session only, when
reconstruction is unavailable). See the statusline guide for the full contract.

## Usage

```
/ca:statusline install | uninstall | status
```

`install` is the default. Before running `install`, the resolved command and the prior line it
will back up are shown for confirmation — editing global settings is the user's call.

## Example

```text
> /ca:statusline install

About to set statusLine.command to:
  python "/home/x/.claude/plugins/ca/hooks/statusline.py"
No prior statusLine to back up.
Proceed? y

WIRED codeArbiter statusline -> python ".../hooks/statusline.py"
no prior statusLine existed; uninstall will simply remove ours.

Takes effect on the next render (new prompt or session).
```
