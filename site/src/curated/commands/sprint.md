---
entity: commands/sprint
related: [feature, commit, skills/subagent-driven-development]
gates:
  - gate: working scope
    when: specifying or resuming the sprint
    effect: maintain the requested outcome and ask only about consequential missing choices; reuse settled decisions
  - gate: hard gates
    when: an explicit stop, consequential unresolved choice, host denial, applicable security control or unauthorized irreversible action prevents affected work
    effect: stop affected work at its actual boundary and continue independent authorized tasks
---

## What it does

Your sprint request establishes the working scope. codeArbiter maintains a specification and
plan, implements coherent tasks, verifies their outcomes and prepares a pull request without
default pauses between batches. It asks about consequential missing choices and honors review
pauses you explicitly request.

Material decisions and uncertainty are recorded in the sprint log. SMARTS supports difficult
trade-offs when useful. Tests and reviews follow the affected work; current results can be reused
while their relevant inputs match. A progress label does not certify passing checks or a release.

## Usage

```
/ca:sprint [goal] [--farm]
```

A short goal seeds the spec conversation that opens the sprint. New full-lane
sprints author typed HTML by default. `--farm` remains blocked for HTML plans
until its separate current-model qualification closes; the flag continues to
name the existing legacy Markdown backend without changing that boundary.

## Example

```text
> /ca:sprint limit the public webhook to 60 requests per IP per minute; return 429 above that limit using our existing store

The request supplies the limit, window and rejection behavior.
Spec saved to .codearbiter/specs/webhook-rate-limit.html; plan contains 5 tasks.
Executing the independent tasks and recording observed checks.
Security review covers the changed limiter and its input handling.
The inspected results remain current through commit and PR preparation.
Five tasks implemented; checks and remaining limitations reported.
Routing through the authorized commit and PR handoff. Merge remains a separate decision.
```

## When to reach for it

Reach for `/ca:sprint` for autonomous work across a maintained plan. Use `/ca:feature` for a
single bounded capability. Both provide progress reports and respect explicit review pauses;
neither requires another artifact approval to continue ordinary authorized work.

For the complete source-traced sequence and its actual endpoint, use [the operator guide](/guides/autonomous-sprints/) and [Compare workflow routes](/concepts/workflow-routes/).
