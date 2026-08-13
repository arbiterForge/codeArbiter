# Redirect

Canned messages for §6 **tiers 2 and 3** — when a direct off-channel instruction is *not* both
unambiguous and non-destructive. Loaded only when needed.

Tier 1 does not use this file at all. An unambiguous, non-destructive intent is routed directly into
its command with a one-line statement of the route (ADR-0022): naming the command and then asking the
user to type it back is ceremony, not governance.

Match the channel to the *phrasing*, not just the topic. An interrogative is a question, not a build
request: "add a healthcheck endpoint" is tier 1 into `$ca-feature`, while "should we add a
healthcheck?" is tier 1 into `$ca-btw`, and "do my ADRs conflict?" is tier 1 into
`$ca-reconcile`. A question pulled into the heavy spec lane is a misroute.

## Tier 2 — probable intent, or an unambiguous but destructive one

One question, naming the command. The user approves; they do not retype.

```
That reads as <inferred intent> → <$ca- skill, prefilled with the user's own words>

Run it? Its own gates still apply.
```

Use this — not tier 1 — whenever the command is irreversible or gate-bypassing, however clear the
intent: `$ca-override`, merge to the default branch, branch or worktree deletion, release and tag
publication. There the confirmation is the gate, not friction. (A deterministic mode-token flip is
friction, not a gate, which is why `mode --dangerous`/`mode --ops` entry is not in this set — see
`includes/ops-mode.md` and `includes/dangerous-mode.md`.)

## Tier 3 — genuinely unclear

```
codeArbiter routes work through commands, so every change clears its gates
and lands on the audit trail. This one could go a few ways:

<up to three prefilled $ca- skills, closest first>

Or pick a channel:
→ Start a new project:      $ca-decompose
→ Start a feature:          $ca-feature "describe it"
→ Ask a question:           $ca-btw "your question"
→ Fix a bug:                $ca-fix "describe it"
→ Bypass with audit trail:  $ca-override "reason"
→ See everything open:      $ca-status
→ See all commands:         $ca-commands
```

When no intent is inferable at all, drop the candidate lines and lead with the channel list.

## Repeat — user insists off-channel after tier 3

```
Still need a channel for this one. Closest matches first:
<up to three prefilled $ca- skills>

Full list:
$ca-decompose  $ca-create-context  $ca-feature  $ca-sprint  $ca-fix  $ca-refactor  $ca-debug  $ca-chore  $ca-spike
$ca-commit  $ca-pr  $ca-watch  $ca-review  $ca-checkpoint  $ca-release  $ca-add-dep
$ca-threat-model  $ca-adr  $ca-adr-status  $ca-reconcile  $ca-conflict
$ca-init  $ca-status  $ca-metrics  $ca-audit  $ca-preview  $ca-doctor  $ca-standup  $ca-cleanup  $ca-task
$ca-new-skill  $ca-btw  $ca-commands
Or $ca-override "reason" to proceed anyway with an audit entry.
```

## Never

A missing owner is a **routing gap**, not an override case. When no command owns the operation, say
so and surface the gap — never steer the user toward `$ca-override` to get past a coverage hole.
That substitution is exactly what issue #308 recorded: a routine post-merge cleanup routed first to
`$ca-chore`, which does not accept it, and then to `$ca-override`, which exists to be rare.

## Exception — local runtime work

`npm run dev` and its kin have no owning command; in `arbiter` mode that is the routing gap above,
surfaced in one line. The runtime-operations token `mode --ops` narrows exactly that gap and no
other: once active, an operation that starts, observes, or exercises a running system and leaves no
change in tracked files or git history is performed in-channel, named in one line as it is taken —
see `includes/ops-mode.md`. Anything that mutates tracked files, the index, git history, or
published state is still a routing gap, `ops` or not.
