# Redirect

Canned messages for §6 when the user sends a direct instruction outside a slash command. Loaded only
when needed. Offer the command list — the user picks. Before sending, infer the likely intent and
pre-fill the closest command with the user's own words (e.g. "add a healthcheck endpoint" →
`/ca:feature "add a healthcheck endpoint"`), so the user can route with one keystroke.

## First redirect — first off-channel message

```
codeArbiter routes all work through commands, so every change clears its gates
and lands on the audit trail.

That looks like <inferred intent> → <prefilled /ca: command>

Or pick a channel:
→ Start a new project:      /ca:decompose
→ Start a feature:          /ca:feature "describe it"
→ Ask a question:           /ca:btw "your question"
→ Fix a bug:                /ca:fix "describe it"
→ Bypass with audit trail:  /ca:override "reason"
→ See everything open:      /ca:status
→ See all commands:         /ca:commands
```

When no intent is inferable, drop the "That looks like" line and lead with the channel list.

## Repeat redirect — user insists after the first redirect

```
Still need a command channel. Closest matches first:
<up to three prefilled /ca: commands for the inferred intent>

Full list:
/ca:decompose  /ca:create-context  /ca:feature  /ca:fix  /ca:refactor  /ca:debug
/ca:commit  /ca:pr  /ca:review  /ca:checkpoint  /ca:release  /ca:add-dep
/ca:threat-model  /ca:adr  /ca:adr-status  /ca:reconcile  /ca:conflict
/ca:new-skill  /ca:btw  /ca:status  /ca:init  /ca:commands
Or /ca:override "reason" to proceed anyway with an audit entry.
```
