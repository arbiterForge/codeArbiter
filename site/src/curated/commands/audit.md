---
entity: commands/audit
related: [status, checkpoint]
use_when: "You need one dated record of what happened over a window of commits or dates: overrides, decisions, sprint auto-decisions and open items."
avoid_when: "A live snapshot of the project, which is `/ca:status`, or triggering a fresh review sweep, which is `/ca:checkpoint`."
asks: "Nothing when a tag or checkpoint gives it a window. With no tag and no usable checkpoint, it asks you for an explicit range or date."
produces: "An audit packet saved to `.codearbiter/audits/<YYYY-MM-DD>.md` with a short summary of commits, overrides and open items. An existing packet is never overwritten."
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
uses `--since-checkpoint` to select the report with the latest valid `recorded_at`. Its
`source_commit` must resolve to a commit and be an ancestor of HEAD; the report supplies the UTC
time anchor and `worktree_dirty` review-scope limitation. Cite the selected report. Missing or
invalid anchors require explicit refs or a date. `last-checkpoint` remains an override count,
not a commit or date, and never supplies the window. Without arguments, use the most recent tag
to HEAD, then a valid checkpoint fallback; ask for a window if neither is available.

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
