# Redirect

Canned messages for §6 when the user sends a direct instruction outside a slash command. Loaded only
when needed. Offer the command list — the user picks. No suggestions beyond it.

## Strike 1 — first off-channel message

```
Process required. Direct instructions outside a command channel are not accepted —
that path bypasses the gates that keep the project healthy.

What are you trying to do?
→ Start a new project:      /ca:decompose
→ Start a feature:          /ca:feature "describe it"
→ Ask a question:           /ca:btw "your question"
→ Fix a bug:                /ca:fix "describe it"
→ Bypass with audit trail:  /ca:override "reason"
→ See everything open:      /ca:status
→ See all commands:         /ca:commands
```

## Strike 2 — user insists after Strike 1

```
Direct instruction declined. Choose a channel:
/ca:decompose  /ca:create-context  /ca:feature  /ca:fix  /ca:refactor  /ca:debug
/ca:commit  /ca:pr  /ca:review  /ca:checkpoint  /ca:release  /ca:add-dep
/ca:threat-model  /ca:adr  /ca:adr-status  /ca:decision-variance  /ca:surface-conflict
/ca:new-skill  /ca:btw  /ca:status  /ca:init  /ca:commands
Or /ca:override "reason" to bypass with logging.
```
