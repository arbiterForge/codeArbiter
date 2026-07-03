---
entity: commands/feature
related: [fix, refactor, skills/brainstorming, skills/writing-plans, skills/tdd]
gates:
  - gate: triage
    when: before any routing decision
    effect: the request is classified small-lane or full-lane against fixed criteria; an uncertain case always falls to the full lane
  - gate: spec approval
    when: after the Socratic refinement conversation
    effect: hard stop; a plan is not written until you sign off on the spec
  - gate: tdd obligation
    when: before implementation begins
    effect: each accepted criterion becomes a failing test the author must watch fail before writing code
  - gate: batch checkpoint
    when: between groups of tasks during execution
    effect: work pauses for your acknowledgement before the next batch starts
---

## What it does

This is the standard entry point for new work with a human in the loop at every step. A short
description of what you want gets classified first: a narrow change touching a couple of files with
no security, dependency, or schema surface can take a trimmed path that skips the full interview,
while anything broader goes through a Socratic conversation that turns a one-line idea into a spec
with testable criteria. From there the request becomes a task-by-task plan, and each task is
implemented test-first, reviewed, and checked in small groups — you're asked to confirm before the
next group starts. Nothing gets built without an approved plan behind it, and the pipeline can always
be resumed later from wherever it left off rather than starting over.

## Usage

```
/ca:feature <what you want to build>
```

A short description of the desired capability opens the classification step and, for the full path,
seeds the spec conversation.

## Example

```text
> /ca:feature let people export their saved searches as a CSV

This touches one new endpoint and a small UI control — no auth, schema, or dependency surface.
Proposed small-lane scope:
  1. GET /api/searches/export returns the current user's saved searches as CSV
  2. an "Export" button on the saved-searches page triggers the download
  3. an empty saved-search list returns a header-only CSV, not an error

Proceed on this scope? (y/n)
> y

Logged to triage.log. Routing to test-first implementation...
[failing test written for criterion 1 — red]
[failing test written for criterion 2 — red]
[failing test written for criterion 3 — red]
...implementation, review, and commit-gate follow before a PR opens.
```

## When to reach for it

Reach for `/ca:feature` for new, human-checkpointed capability work. For a fully autonomous run
across the whole plan, use `/ca:sprint` instead — the same spec-and-plan front, but without pausing
between batches.
