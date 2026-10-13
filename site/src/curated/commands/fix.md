---
entity: commands/fix
related: [feature, refactor, skills/tdd]
gates:
  - gate: regression test first
    when: before any fix code is written
    effect: a test reproducing the defect must exist and fail for the right reason
  - gate: root cause named
    when: before the failing test is written
    effect: a supported code cause and regression oracle must be established from current cited evidence, including a bounded internal diagnostic return when needed
  - gate: caller authority
    when: before repair continues after a debug handoff
    effect: independently check the original caller's repair scope; packet intent and a proposed fix route do not grant authority
---

## What it does

This is the entry point for an authorized repair of a confirmed code defect. Give the observed
behavior, supported expectation, and available trace or reproduction. If the cause still needs
investigation, an active fix may use one bounded internal diagnostic prerequisite and return to
the same caller. This does not recursively invoke the public debug and fix entries or expand the
caller's authority. A diagnosis-only request stops at the recommendation.

The fix owner checks the current evidence and derives the bug-origin TDD obligation. A supported
causal trace can establish the diagnosis without a runtime replay, but a target regression test
must fail at the production layer for the right reason before correction. An import or setup
error, unrelated failure, or merely proposed test does not clear that gate. Then the minimal fix
and the remaining TDD, review, and delivery gates apply.

## Usage

```
/ca:fix <what's happening vs. what should happen>
```

Describe observed and expected behavior and include the evidence source. A known trace helps;
an unknown trigger must stay unknown until evidence establishes it.

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

Reach for `/ca:fix` when repair is authorized and a code defect is supported. For a diagnosis-only
request, `/ca:debug` investigates and returns a recommendation without starting repair. A valid
debug handoff can return `confirmed_code_defect`, `confirmed_noncode_cause`, `design_question`,
`no_action`, or `unresolved`. Only a confirmed code defect with a supported regression obligation
can continue the original authorized fix. Other results return to their owner or stop with the
specified evidence, blocker, or resume condition. No-action makes no default board write.

If a handoff packet is available, resolve `debug-handoff.py` from the loaded installed package
and invoke Python with `-B`, its absolute path, and `validate`. Send at most 65,536 UTF-8
packet bytes through stdin and close it. Require exit 0, `valid: true`, and no errors. Exit 2
rejects the packet; exit 3 or an unavailable helper blocks validated transfer. Do not retry a
refusal through another interpreter. Structural validation does not establish truth, freshness,
or repair authority. A separately authorized task follow-up belongs to the existing `/ca:task`
owner and installed writer.

[Investigate and fix a defect](/guides/investigate-and-fix/) explains the evidence, regression
review and handoff; [Review and ship](/guides/review-and-ship/) covers delivery after verification.

For the connected operating model, read [gated lanes](/concepts/gated-lanes/) and
[test-first evidence](/concepts/test-first/). The map distinguishes a routed procedure
from a command you must type, and retains the caller’s review and delivery boundaries.
