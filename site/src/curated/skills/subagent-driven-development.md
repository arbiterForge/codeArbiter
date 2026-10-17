---
entity: skills/subagent-driven-development
related: [commands/sprint, executing-plans, tdd, dispatching-parallel-agents]
gates:
  - gate: applicable checks
    when: assessing implemented work
    effect: run meaningful checks against current source and report actual outcomes; failures and unknown results remain visible
  - gate: relevant review
    when: the combined change warrants independent or specialist review
    effect: resolve applicable blocking findings and refresh affected conclusions when their source or requirements change
---

## What it does

Implements an existing plan, either a named batch from the feature coordinator or a full sprint
plan. Choose direct implementation for focused work and delegation when isolation, parallel work
or specialist knowledge is useful. Follow actual dependencies and keep pending checks distinct
from implementation progress.

## Phases

1. Read relevant criteria, task state, commands and actual dependencies. Inspect current work and
   outstanding workers on resume before starting another execution.
2. Check factual prerequisites with authorized tools. Use actual user choices for decision
   prerequisites; ask only about consequential unanswered choices. Continue independent work.
3. Implement directly or delegate a useful unit with bounded relevant context. Missing delivery
   receipts do not deny ordinary authorized work. Select the TDD verification approach appropriate
   to a fix, feature, refactor or non-executable change.
4. Compare the result with the criteria, run applicable checks and record command, working
   directory, output and limits. Correct failures and rerun affected checks. Review the combined
   diff at its actual risk and scope.
5. Persist progress through the selected representation. For HTML, `REVIEW` and `DONE` describe
   implementation progress; they are not proof of passing tests or independent review.

## Exits

A scoped invocation returns completed tasks, actual checks, unresolved issues and next work to the
feature coordinator. A full-plan invocation returns the same summary to the sprint caller, which
owns the authorized commit and PR handoff. This skill does not commit.

Keep pending checks visible and preserve explicit user stops, actual host permissions, requirements
and independent security controls. Neither advisory scheduling nor a progress label grants
authority to merge or publish.
