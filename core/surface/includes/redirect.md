# Redirect

Canned messages for §6 **tiers 2 and 3** — when a direct off-channel instruction is *not* both
unambiguous and non-destructive. Loaded only when needed.

Tier 1 does not use this file at all. An unambiguous, non-destructive intent is routed directly into
its command with a one-line statement of the route (ADR-0022): naming the command and then asking the
user to type it back is ceremony, not governance.

Match the channel to the *phrasing*, not just the topic. An interrogative is a question, not a build
request: "add a healthcheck endpoint" is tier 1 into `{{CMD:feature}}`, while "should we add a
healthcheck?" is tier 1 into `{{CMD:btw}}`, and "do my ADRs conflict?" is tier 1 into
`{{CMD:reconcile}}`. A question pulled into the heavy spec lane is a misroute.

## Tier 2 — probable intent, or an unambiguous but destructive one

One question, naming the command. The user approves; they do not retype.

```
That reads as <inferred intent> → <{{IF:claude}}/ca: command{{ELSE}}$ca- skill{{END}}, prefilled with the user's own words>

Run it? Its own gates still apply.
```

Use this — not tier 1 — whenever the command is irreversible or gate-bypassing, however clear the
intent: `{{CMD:override}}`, merge to the default branch, branch or worktree deletion, release and tag
publication. There the confirmation is the gate, not friction. (A deterministic mode-token flip is
friction, not a gate, which is why `mode --dangerous`/`mode --ops` entry is not in this set — see
`includes/ops-mode.md` and `includes/dangerous-mode.md`.)

## Tier 3 — genuinely unclear

```
codeArbiter routes work through commands, so every change clears its gates
and lands on the audit trail. This one could go a few ways:

<up to three prefilled {{IF:claude}}/ca: commands{{ELSE}}$ca- skills{{END}}, closest first>

Or pick a channel:
→ Start a new project:      {{CMD:decompose}}
→ Start a feature:          {{CMD:feature}} "describe it"
→ Ask a question:           {{CMD:btw}} "your question"
→ Fix a bug:                {{CMD:fix}} "describe it"
→ Bypass with audit trail:  {{CMD:override}} "reason"
→ See everything open:      {{CMD:status}}
→ See all commands:         {{CMD:commands}}
```

When no intent is inferable at all, drop the candidate lines and lead with the channel list.

## Repeat — user insists off-channel after tier 3

```
Still need a channel for this one. Closest matches first:
<up to three prefilled {{IF:claude}}/ca: commands{{ELSE}}$ca- skills{{END}}>

Full list:
{{CMD:decompose}}  {{CMD:create-context}}  {{CMD:feature}}  {{CMD:sprint}}  {{CMD:fix}}  {{CMD:refactor}}  {{CMD:debug}}  {{CMD:chore}}  {{CMD:spike}}
{{CMD:commit}}  {{CMD:pr}}  {{CMD:watch}}  {{CMD:review}}  {{CMD:checkpoint}}  {{CMD:release}}  {{CMD:add-dep}}
{{CMD:threat-model}}  {{CMD:adr}}  {{CMD:adr-status}}  {{CMD:reconcile}}  {{CMD:conflict}}
{{CMD:init}}  {{CMD:status}}  {{CMD:metrics}}  {{CMD:audit}}  {{CMD:preview}}  {{IF:claude}}{{CMD:statusline}}  {{CMD:prune}}  {{END}}{{CMD:doctor}}  {{CMD:standup}}  {{CMD:cleanup}}  {{CMD:task}}
{{CMD:new-skill}}  {{CMD:btw}}  {{CMD:commands}}
Or {{CMD:override}} "reason" to proceed anyway with an audit entry.
```

## Never

A missing owner is a **routing gap**, not an override case. When no command owns the operation, say
so and surface the gap — never steer the user toward `{{CMD:override}}` to get past a coverage hole.
That substitution is exactly what issue #308 recorded: a routine post-merge cleanup routed first to
`{{CMD:chore}}`, which does not accept it, and then to `{{CMD:override}}`, which exists to be rare.

## Exception — local runtime work

`npm run dev` and its kin have no owning command; in `arbiter` mode that is the routing gap above,
surfaced in one line. The runtime-operations token `mode --ops` narrows exactly that gap and no
other: once active, an operation that starts, observes, or exercises a running system and leaves no
change in tracked files or git history is performed in-channel, named in one line as it is taken —
see `includes/ops-mode.md`. Anything that mutates tracked files, the index, git history, or
published state is still a routing gap, `ops` or not.
