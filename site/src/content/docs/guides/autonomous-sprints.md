---
title: Run an Autonomous Sprint
description: "Approve one sprint package, then let codeArbiter execute the plan to a pull request while SMARTS records non-hard-gate decisions."
journey:
  level: Power user
  time: 15–20 min
  outcome: "a safe operating model for autonomous plan-to-PR work, including resumability, SMARTS decisions, hard stops, and exact-head evidence."
  prerequisites:
    - Comfortable with the feature lane
    - A scoped sprint goal
  proof: "You can identify the one interactive approval, every persisted restart artifact, and every condition that still stops for the user."
---

Use an autonomous sprint when you can describe a substantial outcome and want codeArbiter to carry
the approved work through implementation, review, commits, and a pull request without stopping
between task batches. The sprint is autonomous after one interactive approval package; it is never
authorized to merge.

<figure class="ca-diagram">
  <img
    src="/diagrams/lane-sprint.svg"
    alt="The autonomous sprint lane from one combined spec and plan approval through small implementation cells, SMARTS-logged decisions, review, verification, commit, and pull request."
    loading="lazy"
  />
  <figcaption>One interactive approval opens the autonomous lane; durable plan and log state make each later cell resumable.</figcaption>
</figure>

<div class="ca-host-syntax">
  <strong>Host syntax:</strong> Claude Code uses <code>/ca:sprint</code>; Codex uses
  <code>$ca-sprint</code>; Pi uses <code>/ca-sprint</code>. Examples below use Claude Code syntax.
</div>

## Before you begin

- Start on a non-default branch or allow the sprint to create an isolated worktree.
- State the outcome, boundaries, and any spending or external-side-effect limits.
- Resolve any existing `[CONFIRM-NN]` that the goal depends on.
- Expect one review package containing both the written spec and implementation plan.

Invoke the sprint with the outcome, not a list of implementation guesses:

```text
/ca:sprint "Add an export flow for saved searches, including empty-state behavior, audit records, and user documentation"
```

## The one interactive approval

codeArbiter investigates the repository and prepares two linked artifacts:

1. **Sprint spec:** the user outcome, scope, exclusions, acceptance criteria, and hard constraints.
2. **Implementation plan:** exact tasks, files, tests, dependencies, ordering, and verification
   mapped back to every acceptance criterion.

It presents the spec and plan together at one STOP. Approve the package, request changes, or decline.
Implementation does not begin until both artifacts are approved in that one decision.

This is not two approvals. If the plan exposes a weakness in the spec, codeArbiter revises the
package and presents the combined result again.

## What happens after approval

The sprint executes the plan in resumable task cells:

1. derive test obligations for the next task;
2. observe the new tests fail for the intended reason;
3. implement the smallest change that satisfies them;
4. run the task's verification and reviewer checks;
5. record the accepted task state on disk; and
6. continue to the next independent cell.

An interrupted session resumes from the approved spec, plan, task statuses, and sprint log. It does
not re-interview you or discard accepted work.

## How autonomous decisions work

For a choice that is not a hard gate, the sprint compares options with
[SMARTS](/concepts/smarts/): Scalable, Maintainable, Available, Reliable, Testable, and Securable.
The options, lens verdicts, decision, and confidence are appended to
`.codearbiter/sprint-log.md`.

Low-confidence decisions are called out in the pull request so you can review the places where the
evidence was genuinely close. Spending outside your stated limit is not treated as an ordinary
SMARTS choice.

## Stops that remain yours

Autonomy never clears these boundaries:

- authentication, cryptography, secrets, or a declared security control;
- irreversible deletion or another destructive operation;
- `/ca:override`, which is itself a user-authorized bypass;
- an unresolved `[CONFIRM-NN]`;
- external spending or side effects outside the approved scope; and
- merging to the default branch.

When one hard gate affects only one task, the sprint leaves that cell stopped and continues
independent safe work. It returns to the blocked cell once the required decision exists.

## Pull request and verification

The normal sprint exit is a pull request, not a merge. The PR should contain:

- the approved spec and plan;
- acceptance-criterion to task/test coverage;
- verification commands and results;
- reviewer findings and their dispositions;
- SMARTS decisions, with low-confidence calls highlighted; and
- remaining hard-gated or out-of-scope work.

Confirm the PR is draft when you want a deliberate merge barrier. Hosted checks still need to run
against the exact current PR head before the work is treated as ready.

## Optional farm backend

`--farm` replaces the normal premium-author execution with a configured OpenAI-compatible worker:

```text
/ca:sprint "Normalize the public API error contract" --farm
```

The same spec package, hard gates, task checks, review, and PR boundary apply. Farm use is a Feature
Forge preview and requires provider configuration. It may transmit secret-redacted, byte-capped
task context to the endpoint you configure; read [Compatibility: Network Calls](/getting-started/compatibility/#network-calls)
before enabling it.

## Verify and review

After the PR opens:

1. read the acceptance criteria and plan delta;
2. review low-confidence SMARTS entries in `.codearbiter/sprint-log.md`;
3. confirm every required local verification is present;
4. wait for hosted checks on the exact PR head; and
5. make the merge decision yourself.

For the exact orchestration contract, see the [`sprint` command](/reference/commands/sprint/) and
the [`subagent-driven-development` skill](/reference/skills/subagent-driven-development/).
