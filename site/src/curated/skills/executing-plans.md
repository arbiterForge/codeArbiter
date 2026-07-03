---
entity: skills/executing-plans
related: [commands/feature, subagent-driven-development, writing-plans]
gates:
  - gate: batch checkpoint
    when: after every batch completes
    effect: the next batch does not start until you acknowledge what landed, what's next, and what's still open
---

## What it does

This is the checkpointed coordinator behind the feature command, taking over once an approved
plan exists. It groups the plan's tasks into small batches, hands each batch to the implementation
engine for the actual test-first work and review, and stops for your acknowledgment between
batches. It never implements anything itself — only schedules and checkpoints.

## Phases

1. Group the plan's non-accepted tasks into small batches, respecting dependency order, and
   present the breakdown as information rather than a question.
2. Hand the current batch's task IDs to the implementation engine, which runs the test-first work,
   review, and verification for each task.
3. Stop and report what landed, what's next, and what's still open, and wait for your
   acknowledgment before starting the next batch.

## Exits

Once the final batch is acknowledged and every plan task is accepted, the branch moves on to the
commit gate — this skill never commits on its own. A halt inside the implementation engine, such
as a failed test-first gate or an unresolved open question, surfaces to you rather than being
worked around.
