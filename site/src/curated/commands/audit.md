---
entity: commands/audit
related: [status, metrics, checkpoint]
---

## What it does

Assembles everything codeArbiter logs — `overrides.log`, `triage.log`, `decisions/`,
`sprint-log.md`, `checkpoints/` — into a single dated record: what happened during a window, who
signed off on it, and what's still outstanding. It's read-only over every source; its only write is
the packet itself, saved to
`.codearbiter/audits/<YYYY-MM-DD>.md` (a second run the same day appends `-2`, never overwriting).
Every override and low-confidence sprint entry is quoted verbatim, never paraphrased, and an empty
section is stated as empty — "no overrides in window" is itself part of the record.

`triage.log` contributes small-lane classifications; checkpoint findings come from the latest
checkpoint report. Currently unresolved questions and latest open findings accompany range-bound
events, so the packet is not wholly a reconstruction of past open state.

## Usage

```
/ca:audit [<from-ref> <to-ref> | --since-checkpoint | --since <date>]
```

Two tags/SHAs bound an explicit range; `--since <date>` selects a date to HEAD. The command
also declares `--since-checkpoint` and a checkpoint fallback. The checkpoint writer, however,
stores a bare override count in `last-checkpoint`, not a commit or date. Require a demonstrated
resolved commit/time window rather than interpreting that counter as history; use explicit refs
or a date while this source-contract discrepancy remains. With no usable boundary, the command
must ask for one.

[Auditability](/concepts/auditability/) explains range selection, temporal limits, missing inputs
and source-by-source packet validation.

## Example

```text
Illustrative packet summary, not captured execution:
> /ca:audit v2.4.0 v2.5.0

Window: v2.4.0..v2.5.0 (2026-06-15 to 2026-07-02)
Packet written: .codearbiter/audits/2026-07-02.md

Summary:
  Commits: 41 (12 feat, 9 fix, 6 docs, ...)
  Overrides: 2 (both routine, 0 SECURITY-OVERRIDE)
  Open items: 1 unresolved [CONFIRM-11], 3 checkpoint findings still open
```

## When to reach for it

You want an evidentiary packet for a range, not a live snapshot — for that, use `/ca:status`. This
command only reports what reviews already found; to trigger a fresh review sweep, use
`/ca:checkpoint`.
