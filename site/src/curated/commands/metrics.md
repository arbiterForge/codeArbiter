---
entity: commands/metrics
related: [status, audit]
---

## What it does

A bare-numbers governance glance — three metrics, each with a trend arrow against the prior
20-commit window: override rate, small-lane rate, and sprint low-confidence ratio. It calls a thin
Python helper and prints only the numbers and arrows, never a verbatim override line, a commit
list, or any other log content, and it writes nothing to disk. It's meant for a glance, not
evidence — reach for `/ca:audit` when you need the full packet with quoted log lines.

## Usage

```
/ca:metrics [--window N]
```

`--window N` changes the commit-window size from the default of 20.

## Example

```text
> /ca:metrics

override rate:          0.05  →  (prior: 0.05)
small-lane rate:        0.30  ↓  (prior: 0.42)
sprint low-conf ratio:  n/a   →  (prior: n/a)

An upward arrow on override rate or sprint low-conf ratio is a worsening signal.
Window: 20 commits (default)
```

## When to reach for it

A fast trend check without leaving the terminal. For the full evidentiary packet with verbatim
overrides and a commit list, use `/ca:audit`; for live project state right now, use `/ca:status`.
