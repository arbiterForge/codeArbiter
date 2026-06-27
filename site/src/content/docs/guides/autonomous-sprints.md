---
title: "Run an Autonomous Sprint"
description: "Hand a goal to codeArbiter and have it plan, implement, and open a PR with one interactive gate at the start."
---

`/ca:sprint` runs a full development cycle without continuous input. You review a spec and approve a plan once, at the start. After that, codeArbiter handles every implementation task, scores every decision it makes in your place, logs the lot, and opens a PR when the gate chain clears. You come back at the end to decide whether to merge.

<figure class="ca-diagram">
  <img
    src="/codeArbiter/diagrams/lane-sprint.svg"
    alt="The /ca:sprint lane in three rows: Commands (/ca:sprint), Skills (writing-plans, subagent-driven-development, commit-gate, finishing-a-development-branch), and Agents (author subagent, reviewer fleet), with a connector weaving through them in execution order."
    loading="lazy"
    width="920"
    height="250"
  />
  <figcaption>The <code>/ca:sprint</code> lane by piece type: command (gold), skills (violet), agents (green), each loaded in execution order.</figcaption>
</figure>

## Before You Begin

Your repository must be opted in (`arbiter: enabled` in `.codearbiter/CONTEXT.md`). If it isn't yet, run `/ca:init`. The [Quickstart](/getting-started/quickstart/) walks through the opt-in.

## Approve the Spec and Plan

Run the sprint with your goal as the argument:

```text
/ca:sprint "add pagination to the /posts API endpoint: cursor-based, 50 items per page, expose Link header"
```

codeArbiter enters the spec and plan phase and works in two passes before touching any code.

First, it drafts a full spec from your goal and presents it for approval. Read it carefully. This is your primary opportunity to correct scope, add constraints, or reject and restate the goal. The sprint will not proceed until you approve.

Second, it runs the [`writing-plans`](/reference/skills/writing-plans/) skill. The approved spec is decomposed into individual tasks of roughly two to five minutes each. Every task carries the exact file paths it will touch and a concrete verification step that maps to a test obligation. The plan is written to `.codearbiter/plans/<slug>.md`, ordered with dependencies flagged. You review the plan and approve or send it back.

That plan approval is the last required interaction before execution begins.

## Autonomous Execution

Each task in the approved plan dispatches a fresh subagent through [`subagent-driven-development`](/reference/skills/subagent-driven-development/): test first via the `tdd` gate, then spec-compliance review, quality review, and a fresh-run verification. No single agent context accumulates state across tasks.

When the sprint must make a choice in your place, such as which approach to take for an edge case the spec didn't cover, it uses **SMARTS**: a structured, multi-lens scoring rubric. SMARTS weighs the available options, scores each against a set of lenses, picks the highest-scoring option, and flags its confidence in that call. Every auto-decision and its score lands in an append-only **sprint log**. Low-confidence calls are marked so you can find them quickly after the run.

Nothing hides behind the autonomy. Every choice the sprint made on your behalf is in the log.

## Hard Gates That Always Stop

Some decisions are never auto-decided, regardless of confidence. The sprint halts and waits when it encounters:

- A finding in the security controls, including any auth, crypto, or secret-handling change
- An irreversible operation
- A gate-bypass attempt
- An unresolved decision the spec does not cover and SMARTS cannot score with sufficient confidence

These stops are rare when the spec is thorough. A sprint that halts often on hard gates is a signal that the goal needed more detail before starting, not that the gates are miscalibrated.

## The Pull Request

When the commit gate clears on the final task, [`finishing-a-development-branch`](/reference/skills/finishing-a-development-branch/) runs. Under `/ca:sprint`, it auto-selects "open PR." It will not merge to the default branch. Direct merge is prohibited. A pull request is opened and the merge decision is yours to make on your own timeline.

## Route Implementation Through Farm Workers

<div class="ca-callout ca-callout--preview"><p class="ca-callout__label">Preview</p><p><code>--farm</code> is a Feature Forge preview feature. It ships dormant and is off by default. It has not been promoted to stable. Turn it on deliberately; do not rely on it for production workflows until promotion is tracked and recorded.</p></div>

The `--farm` flag routes each implementation task to a pool of lower-cost worker agents rather than the primary agent context. The review chain is identical to a standard sprint: the same commit gate, the same reviewer fleet, the same hard stops. Only the execution workers change.

To use it:

1. Set `FARM_API_KEY` in your environment to a valid farm API key.
2. Run:

```text
/ca:sprint --farm "add pagination to the /posts API endpoint: cursor-based, 50 items per page, expose Link header"
```

The spec and plan gate runs exactly as it does without the flag. Farm routing takes over for the execution phase.

Because `--farm` is a Feature Forge preview, its behavior may change between releases. Promotion to stable requires real-world evidence and is recorded as a deliberate tracked decision in the project, not an automatic calendar event.

## Review the Sprint Log

After the PR opens, read the sprint log before merging. It lists every auto-decision in order: the options considered, the SMARTS lens scores, the chosen option, and the confidence flag. The low-confidence entries are the ones worth reading first. They are where the sprint was least certain and where a brief review returns the most value.

## Related

- [`/ca:sprint` command](/reference/commands/sprint/): full command signature and flags
- [`writing-plans` skill](/reference/skills/writing-plans/): how the plan is built from the spec
- [`subagent-driven-development` skill](/reference/skills/subagent-driven-development/): the per-task implementation engine
- [`finishing-a-development-branch` skill](/reference/skills/finishing-a-development-branch/): how the PR decision is handled at the end
- [Concepts: SMARTS and the Feature Forge](/concepts/): the ideas behind scored decisions and the preview model
