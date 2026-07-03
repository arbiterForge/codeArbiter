---
entity: commands/sprint
related: [commit, skills/tdd]
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
