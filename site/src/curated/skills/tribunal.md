---
entity: skills/tribunal
related: [commands/tribunal]
gates:
  - gate: cost acknowledgment
    when: before anything is dispatched
    effect: you must acknowledge the estimated token cost and confirm the model before the run proceeds — an unacknowledged run does not start
  - gate: approval and filing
    when: after the report is presented
    effect: findings become tracked issues only on your explicit selection; silence or a vague "looks good" files nothing
---

## What it does

This is the deepest, most expensive review the project offers — convened rarely, on demand,
invoked through the tribunal command, and never required as a gate on ordinary work. Eleven
specialist reviewers each judge one lens of the codebase in parallel, every finding persisted to
its own file as it's found so the run survives an interruption and resumes from disk rather than
restarting.

## Phases

1. Check for a resumable prior run, size the job, and get your explicit acknowledgment of the
   estimated cost and confirmed model before dispatching anything.
2. Build an inventory of the codebase and a risk overlay that decides which areas get closer
   scrutiny, then fix the set of active specialist lenses.
3. Dispatch the active lenses in bounded waves, each one writing its findings straight to disk as
   they're found.
4. Triage every finding from disk as each wave finishes, independently recalibrating severity and
   confidence rather than trusting the lens's own numbers.
5. Regenerate the report from the triage record — never hand-authored — grouped by calibrated
   severity.
6. On your explicit selection, file the approved findings as tracked issues, skipping anything
   already filed or already tracked elsewhere.
7. Optionally, and only on your per-run authorization, send a scrubbed, aggregate-only telemetry
   payload.

## Exits

The run leaves a regenerated report and, only on your explicit approval, a set of filed tracked
issues — nothing is filed on silence. It never edits, refactors, or commits project code itself,
and it never blocks a commit or a merge; a critical finding here is a recommendation to fix, not a
pipeline stop.
