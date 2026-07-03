---
entity: commands/fix
related: [feature, refactor, skills/tdd]
gates:
  - gate: regression test first
    when: before any fix code is written
    effect: a test reproducing the defect must exist and fail for the right reason
  - gate: root cause named
    when: before the failing test is written
    effect: the exact code path producing the wrong behavior must be located, not guessed at
---

## What it does

This is the entry point for a defect that already has a known cause, or one you can describe
precisely — what's happening versus what should happen, ideally with a stack trace or a way to
reproduce it. The work routes into the standard test-first pipeline, but the first obligation is
framed around proving the bug rather than building something new: a test has to fail, and fail for
the specific reason the defect causes, before any correction is written. Only after that red test is
confirmed does the minimal fix land, followed by the same review and verification steps every other
change goes through.

## Usage

```
/ca:fix <what's happening vs. what should happen>
```

Describe the observed behavior and the expected behavior; a stack trace or reliable reproduction
sharpens the diagnosis.

## Example

```text
> /ca:fix search results page shows a blank page instead of "no results" when a query matches nothing

Reproducing... confirmed: empty result set triggers an unhandled render path in SearchResults.
Root cause: the component assumes results.length > 0 and never checks the empty case.
Writing regression test: renders SearchResults with an empty array, expects "no matches" text.
Running... FAIL (expected reason: TypeError reading results[0], matches the observed defect)
Test is red for the right reason. Proceeding to the minimal fix.
```

## When to reach for it

Reach for `/ca:fix` once the cause is known or you can name a precise repro. If the cause is unknown,
`/ca:debug` investigates first and hands off a confirmed bug statement `/ca:fix` can act on.
