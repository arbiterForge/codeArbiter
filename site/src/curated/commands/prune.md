---
entity: commands/prune
related: [status]
gates:
  - gate: live-transcript refusal
    when: run <path> targets the current session's live transcript
    effect: refused by construction — a recently-modified file can't be pruned with --execute; only a copy or an inactive session can
  - gate: opt-in enable
    when: turning the after-each-turn service on (CODEARBITER_PRUNE=on)
    effect: never set on the user's behalf — explained, then left to the user's explicit choice
---

This is a Feature Forge preview command — the after-each-turn service ships **off** by default and
is promoted from `dry` to `on` only once the collected dry-run evidence shows a clean record.

## What it does

A long Claude Code session can exhaust its context window on pure bulk long before real content
does the damage: tool-result sidecars, oversized outputs, thinking blocks, MCP/shell noise, stale
file reads. This
command trims that bulk at safe quiescence boundaries — it always preserves the `uuid`/`parentUuid`
chain, every line type (including ones it doesn't recognize), and the K most recent tool-bearing
turns verbatim. The gain lands at the next `claude --resume`/restart or compaction, never on the
turn that ran the command, because the running CLI already sent its in-memory history to the API.

It has five modes, chosen by the first argument: `status` (default) reports cumulative reduction
and service state; `dry` copies the live transcript and analyzes the copy without touching the
original; `run <path>` prunes a target for real, but only a copy or an inactive session — a file that was
touched recently is rejected outright; `audit <path>` is a read-only integrity report;
`on`/`off` explain how to toggle the always-safe after-each-turn service.

## Usage

```
/ca:prune status | dry | run <path> | audit <path> | on | off
```

`status` is the default with no argument. `run` and `audit` take a transcript path.

## Example

```text
> /ca:prune status

service: off  (CODEARBITER_PRUNE unset)
this session: 0 prunes recorded

> /ca:prune dry

strategy                  lines      before       after  est. saved
sidecar-strip                214     412,880     301,440     111,440
oversize-clamp                31     301,440     288,110      13,330
reasoning-fold                 9     288,110     279,900       8,210

total: 403KB -> 273KB  (32% reduction)
verdict: dry-run — gains land at next --resume or compaction
```

## When to reach for it

Skip it when the context bar is nowhere near compaction — the most recent turns are protected
regardless. Install health is `/ca:doctor`'s job; project progress is `/ca:status`'s.
