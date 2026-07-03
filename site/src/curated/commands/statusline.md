---
entity: commands/statusline
related: [doctor]
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
frontmatter. Token and cost figures are read from the session transcript's real per-model
usage — the cost is an estimated pay-as-you-go equivalent, not a bill.

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

## When to reach for it

Confirming the wiring took effect, or diagnosing whether something else owns the statusline, is
`/ca:doctor`'s broader install-health check as well as this command's own `status` action.
