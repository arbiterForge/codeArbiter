---
entity: skills/writing-plans
related: [commands/feature, commands/sprint, brainstorming, executing-plans]
gates:
  - gate: bijective coverage
    when: before the plan is written to disk
    effect: every acceptance criterion must map to at least one task, and every task must advance at least one criterion — a task covering nothing is scope creep and is cut
---

## What it does

This is the bridge between an approved spec and something the implementation engine can actually
execute. The feature command routes here once a spec is approved, and an autonomous sprint routes
here before execution begins. It breaks the spec into small, individually verifiable tasks — each
with an exact file path and a concrete verification step — orders them by dependency, and proves
every acceptance criterion is covered before the plan is written.

## Phases

1. Pull each acceptance criterion out of the spec word for word and give it a stable ID.
2. Break the work into small tasks, each carrying an exact path, a concrete verification step, the
   test-first obligation it maps to, and the criteria it advances.
3. Order the tasks by dependency and mark the minimal shippable slice within them.
4. Cross-check coverage both ways so nothing goes untested and nothing is added for no reason,
   then write the finished plan to disk with every task's status initialized as pending.

## Exits

A finished plan clears the path to either the checkpointed batch coordinator or the autonomous
implementation engine, which route every task through the test-first gate — this skill never hands
off to that gate directly. An uncovered criterion, or a task with no path or verification step,
keeps the plan from being written at all.
