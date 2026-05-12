# _redirect (internal)

Canned redirect messages emitted by the §6 User Interaction Protocol when a user
sends a direct instruction outside a slash command. Loaded only when needed.

Not user-invocable. Filename starts with `_` to signal "internal."

---

## Strike 1 — first off-channel message

```
Process required. Direct instructions outside a skill channel are not accepted
— that path bypasses the gates that keep the project healthy.

What are you trying to do?
→ Start a feature:          /feature "describe it"
→ Ask a question:           /btw "your question"
→ Fix a bug:                /fix "describe it"
→ Bypass with audit trail:  /override "reason"
→ See everything open:      /status
→ See all commands:         /commands
```

---

## Strike 2 — user insists after Strike 1

```
Direct instruction declined. Choose a channel:
/feature  /fix  /commit  /pr  /review  /threat-model  /adr  /adr-status
/checkpoint  /stage  /add-dep  /surface-conflict  /btw  /status  /init
/override  /onboard  /new-skill  /ticket  /commands
Or use /override "reason" to bypass with logging.
```

No suggestions beyond the command list. The user must pick.
