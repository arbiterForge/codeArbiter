---
entity: commands/feature
related: [fix, refactor, skills/brainstorming, skills/writing-plans, skills/tdd]
gates:
  - gate: triage
    when: before any routing decision
    effect: the request is classified small-lane or full-lane against fixed criteria; an uncertain case always falls to the full lane
  - gate: consequential decision
    when: a required product choice is unresolved
    effect: ask once and keep affected work waiting; settled choices and independent work continue
  - gate: verification
    when: before implementation begins
    effect: select checks against the criteria, then record the actual test sequence and results before claiming completion
  - gate: requested checkpoint
    when: the user explicitly asks to review a group of tasks before continuation
    effect: pause at that checkpoint; routine progress reports otherwise continue into the next independent work
---

## What it does

The feature entry turns your requested outcome into testable criteria and a practical plan.
Your request supplies the authorization to work. codeArbiter asks about consequential missing
choices once, preserves settled decisions, and continues within the agreed scope.

A small change can use an inline mini-spec only when it touches at most two implementation files
plus tests, has one to three concrete criteria, and touches no protected scope or new dependency,
endpoint, command or configuration surface. Any uncertain condition selects the full lane, which
maintains a specification and matching task plan before implementation.

Tasks are implemented directly or delegated when useful. The caller selects an appropriate
verification approach, records the observed sequence and results, and routes applicable review.
Progress reports do not require acknowledgement unless you requested a pause. Interrupted work
resumes from the existing artifacts and actual remaining tasks. Local checks cover the affected
scope; exhaustive exact-head hosted CI remains mandatory before merge.

## Usage

```
/ca:feature <what you want to build>
```

A short description of the desired capability opens classification and supplies the intended
scope. Include any decisions or review pauses you want to reserve for yourself.

## Example

```text
> /ca:feature add alphabetical ordering to the existing saved-search CSV export

The existing exporter needs one implementation file and its tests; no protected scope
or new endpoint, dependency, command or configuration surface is involved.
Small-lane criterion: export rows in ascending search-name order and preserve each row's fields.

Logged to triage.log. Selected verification: focused ordering and existing CSV round-trip tests.
[ordering test fails because rows retain input order]
[exporter updated; ordering and round-trip tests pass]
The completion report names the checks and any remaining review or delivery work.
```

## When to reach for it

Reach for `/ca:feature` for a bounded capability with useful progress reports. For autonomous
execution across a whole plan, use `/ca:sprint`. Both preserve real user decisions and host
permissions; neither requires repeated artifact approval to continue ordinary work.

For the connected operating model, read [gated lanes](/concepts/gated-lanes/) and
[test-first evidence](/concepts/test-first/). The map distinguishes a routed procedure
from a command you must type, and retains the caller’s review and delivery boundaries.
