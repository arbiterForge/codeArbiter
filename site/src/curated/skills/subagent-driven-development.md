---
entity: skills/subagent-driven-development
related: [commands/sprint, executing-plans, tdd, dispatching-parallel-agents]
gates:
  - gate: fresh-run verification
    when: before any task is accepted
    effect: a task's own verification command must be re-run fresh and read directly — a subagent's self-reported success is never accepted as evidence
  - gate: quality review
    when: once per scope, after every task in it clears
    effect: no task in the scope is accepted until the combined diff clears review with no critical or high finding
---

## What it does

This is the engine that actually writes implementation code, invoked by an autonomous sprint over
a full plan and by the checkpointed batch coordinator over one batch at a time. Each task gets its
own fresh agent working test-first, so no single context accumulates drift across tasks, followed
by a compliance check against the task's obligation, a shared quality review over the whole
batch's combined diff, and a fresh verification run before anything is marked done.

## Phases

1. Select the next unblocked task in dependency order, confirming its dependencies are already
   accepted and it carries no unresolved open question.
2. Dispatch one fresh agent for that task, working test-first through the test-first gate — no
   implementation code exists before that gate's first phase clears.
3. Check the result against the task's specific obligation — nothing more, nothing less than what
   was asked.
4. Once every task in the current scope clears that check, run one quality review over the
   combined diff, dispatching only the reviewers the diff's content calls for.
5. Re-run the task's verification command fresh and confirm its output actually demonstrates the
   obligation.
6. Mark the task accepted, recording it directly in the plan file, and either move to the next
   task or hand the finished scope back to the caller.

## Exits

A scoped batch returns "all tasks accepted" to the checkpoint coordinator without ever reaching
the commit gate itself. A full, uncoped run instead hands the whole branch to the commit gate once
every task is accepted. A failed test-first gate, a critical security finding, or an unresolved
open question halts the loop and surfaces to you rather than being worked around.
