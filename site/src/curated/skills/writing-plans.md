---
entity: skills/writing-plans
related: [commands/feature, commands/sprint, brainstorming, executing-plans]
runs_inside: "`/ca:feature` and `/ca:sprint`, after the specification is saved."
produces: "A maintained plan whose tasks name outcomes, paths, criterion IDs, dependencies and a concrete verification, saved and read back, with open decisions and pending checks listed."
gates:
  - gate: criterion coverage
    when: assessing plan readiness
    effect: every required criterion has planned work and every task serves the agreed outcome; missing requirements and structural failures remain visible
---

## What it does

Turns a selected specification into a maintained plan under the existing authorization.
Tasks name useful outcomes, relevant paths, criterion IDs, actual dependencies and concrete
verification. The feature or sprint caller owns execution; this skill authors and maintains
the plan without implementing code.

## Draft and readiness

For typed work, reuse the specification's stable criterion IDs and preserve the selected identity.
A draft may be incomplete. Readiness diagnostics identify missing structure and coverage; they do
not create another permission request for independent authorized work. A conflicting write or
structural failure prevents claiming the plan was saved.

Check coverage in both directions, then ask whether the plan still misses part of the user's
intent. Choose useful task sizes and meaningful batches. Separate observable fact prerequisites
from consequential decisions that need their actual owner. Record shared source inputs only where
tasks genuinely depend on them; do not claim an exhaustive dependency graph.

Existing Markdown pairs retain their representation and one task ledger.

## What to review

Check each task's outcome, paths, dependencies, criteria and proving check. Use real repository
commands with a working directory and expected observation, or an explicitly described observable
check. An unavailable named-test parser limits the result claim; it does not justify invented
evidence or a command executed merely to author a plan.

## Exits

Save through the selected writer, read back the result and return the plan location, useful next
work, open decisions and pending checks. In-scope method changes can update the plan with a reason.
A changed outcome goes to its decision owner; explicit human pauses remain effective.

A plan or `DONE` label is not verification or release evidence. Resume at unfinished work without
restarting settled interviews. [Review specifications and plans](/guides/review-artifacts/) and
[Resume and recover](/guides/resume-and-recover/) explain inspection and continuation.
