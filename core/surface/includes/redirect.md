# Redirect

Canned messages for §6 when the user sends a direct instruction outside a slash command. Loaded only
when needed. Offer the command list — the user picks. Before sending, infer the likely intent and
pre-fill the closest command with the user's own words, so the user can route with one keystroke.
Match the channel to the *phrasing*, not just the topic — an interrogative is a question, not a build
request (e.g. "add a healthcheck endpoint" → `{{CMD:feature}} "add a healthcheck endpoint"`, but
"should we add a healthcheck?" → `{{CMD:btw}} "should we add a healthcheck?"`; "do my ADRs conflict?" →
`{{CMD:reconcile}}`). A question pulled into the heavy spec lane is a misroute.

## First redirect — first off-channel message

```
codeArbiter routes all work through commands, so every change clears its gates
and lands on the audit trail.

That looks like <inferred intent> → <prefilled {{IF:claude}}/ca: command{{ELSE}}$ca- skill{{END}}>

Or pick a channel:
→ Start a new project:      {{CMD:decompose}}
→ Start a feature:          {{CMD:feature}} "describe it"
→ Ask a question:           {{CMD:btw}} "your question"
→ Fix a bug:                {{CMD:fix}} "describe it"
→ Bypass with audit trail:  {{CMD:override}} "reason"
→ See everything open:      {{CMD:status}}
→ See all commands:         {{CMD:commands}}
```

When no intent is inferable, drop the "That looks like" line and lead with the channel list.

## Repeat redirect — user insists after the first redirect

```
Still need a command channel. Closest matches first:
<up to three prefilled {{IF:claude}}/ca: commands{{ELSE}}$ca- skills{{END}} for the inferred intent>

Full list:
{{CMD:decompose}}  {{CMD:create-context}}  {{CMD:feature}}  {{CMD:sprint}}  {{CMD:fix}}  {{CMD:refactor}}  {{CMD:debug}}  {{CMD:chore}}  {{CMD:spike}}
{{CMD:commit}}  {{CMD:pr}}  {{CMD:watch}}  {{CMD:review}}  {{CMD:checkpoint}}  {{CMD:release}}  {{CMD:add-dep}}
{{CMD:threat-model}}  {{CMD:adr}}  {{CMD:adr-status}}  {{CMD:reconcile}}  {{CMD:conflict}}
{{CMD:init}}  {{CMD:status}}  {{CMD:metrics}}  {{CMD:audit}}  {{CMD:preview}}  {{IF:claude}}{{CMD:statusline}}  {{CMD:prune}}  {{END}}{{CMD:doctor}}  {{CMD:standup}}  {{CMD:task}}
{{CMD:new-skill}}  {{CMD:btw}}  {{CMD:commands}}
Or {{CMD:override}} "reason" to proceed anyway with an audit entry.
```
