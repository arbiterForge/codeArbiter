---
entity: commands/sprint
related: [feature, commit, skills/subagent-driven-development]
gates:
  - gate: spec + plan approval
    when: before autonomous execution starts
    effect: hard stop; both the sprint spec and the resulting plan need your explicit sign-off
  - gate: hard gates
    when: a security boundary, crypto/secret handling, an irreversible operation, an override request, an unresolved confirmation point, or a merge to the default branch comes up mid-run
    effect: execution halts and surfaces the decision to you instead of choosing on your behalf
---

## What it does

This is codeArbiter's autonomy mode. It collapses the usual spec-plan-execute cycle into one
interactive checkpoint up front, then runs the rest of the arc — task selection, test-first
implementation, review, and landing the branch — without stopping between batches. Every call it
makes on your behalf along the way is scored and appended to a running log with a confidence
rating, so a low-confidence choice is easy to find and revisit later even though nobody was there
to approve it in the moment.

## Usage

```
/ca:sprint [goal] [--farm]
```

A short goal seeds the spec conversation that opens the sprint. Add `--farm` to send
implementation work to lower-cost worker agents while the same spec-authoring, test-writing, and
review responsibilities stay put.

## Example

```text
> /ca:sprint add rate limiting to the public webhook endpoint

Opening the sprint spec conversation...
[Socratic refinement — per-IP limit, window, response on exceed]
Spec written to .codearbiter/specs/webhook-rate-limit.md. Plan written with 5 tasks.
Approve spec and plan to begin autonomous execution? (y/n)
> y

Executing task 1/5... task 2/5... task 3/5 touches security-controls.md scope — this is a hard gate,
halting for your decision rather than choosing on your behalf.

Task 3 adds a Redis-backed limiter key derived from client IP. Confirm this fits the approved
security posture before I continue? (y/n)
> y

...task 4/5... task 5/5 complete. Every auto-decision logged to sprint-log.md (1 low-confidence entry).
Routing to commit-gate, then finishing-a-development-branch (opening a PR — sprint never merges).
```

## When to reach for it

Reach for `/ca:sprint` when the spec can be made concrete up front and you want the whole plan to run
without per-batch checkpoints. `/ca:feature` is the better fit when you want to review progress
between batches.
