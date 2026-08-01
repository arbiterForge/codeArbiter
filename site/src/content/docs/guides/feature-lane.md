---
title: Build a Feature End to End
description: "Take an idea through spec, plan, test-first implementation, and pull request using the /ca:feature lane."
journey:
  level: Practitioner
  time: 15 min
  outcome: "Run feature work from one-line intent through approved spec, obligation-mapped TDD, review, commit, and PR."
  prerequisites:
    - An opted-in repository
    - A behavior-changing product idea
  proof: "You can locate each persisted artifact and name the gate that must clear before the next phase begins."
---

`/ca:feature` is the one entry point for new implementation work. Run it with a one-line description of what you want built:

```text
/ca:feature "add rate limiting to the public search endpoint"
```

<div class="ca-callout ca-callout--host">
  <p class="ca-callout__label">Host syntax</p>
  Claude Code uses <code>/ca:feature "…"</code>; Codex uses <code>$ca-feature "…"</code>;
  Pi uses <code>/ca-feature "…"</code>. The persisted artifacts and gates are the same.
</div>

The lane runs in order and gates at each transition. Nothing moves until the previous gate clears.
Each piece loads only when the lane reaches it: the command you run, the skills it routes through,
and the author and reviewer agents it dispatches on demand.

<figure class="ca-diagram">
  <img
    src="/diagrams/lane-feature.svg"
    alt="The /ca:feature lane in three rows: Commands (/ca:feature, /ca:commit, /ca:pr), Skills (brainstorming, writing-plans, tdd, commit-gate), and Agents (author agents, reviewer agents), with a connector weaving through them in execution order."
    loading="lazy"
    width="920"
    height="250"
  />
  <figcaption>The <code>/ca:feature</code> lane by piece type: commands (gold), skills (violet), agents (green), each loaded in execution order.</figcaption>
</figure>

## First: full lane, small lane, or resume

The command classifies the request before it writes anything.

| Path | When it applies | First durable evidence |
|---|---|---|
| **Full lane** | Any scope touch, new public surface, new dependency, more than two implementation files, or uncertainty | An approved spec under `.codearbiter/specs/` |
| **Small lane** | At most two implementation files, no sensitive or architectural scope touch, and one to three testable criteria | Your confirmed mini-spec plus one append-only `triage.log` line |
| **Resume** | A matching spec or plan already exists | The existing pipeline re-enters at its furthest completed checkpoint |

The small lane trims ceremony, not gates: it still starts with test obligations, clears review and
commit-gate, and finishes through a PR. If the classifier is uncertain, the full lane wins.

An interrupted run is never silently restarted. Invoke the feature command with the same description,
or invoke it bare to list resumable pipelines. A plan with unfinished tasks resumes execution; a
fully accepted plan resumes at commit-gate; an approved spec without a plan resumes planning; an
unapproved spec returns to its approval gate.

## Refine the Idea Into a Spec

The [brainstorming skill](/reference/skills/brainstorming/) runs first. It takes your one-line prompt and drives it toward a concrete, approved spec through four gated phases: frame, refine, write, approve.

The skill asks focused clarifying questions, one area at a time. You answer and steer. When the scope is clear, the spec is written to disk and you approve it. No source file is touched until you do.

Each acceptance criterion in the approved spec becomes exactly one obligation in the tdd cycle. The spec is the binding definition of done for every task that follows.

## Break the Spec Into a Plan

With an approved spec, the [writing-plans skill](/reference/skills/writing-plans/) decomposes it into tasks, each 2 to 5 minutes of work. Every task carries the exact file path it touches and a concrete verification step that maps to a tdd obligation.

The plan is written to `.codearbiter/plans/<slug>.md`. Execution does not start until every task has a file path, a verification step, and the full task set covers every acceptance criterion.

## Implement Test-First, Batch by Batch

The [executing-plans skill](/reference/skills/executing-plans/) coordinates implementation. It groups the plan's tasks into batches and dispatches each batch. Each task runs with a fresh author agent and a full reviewer fleet, beginning with the [tdd skill](/reference/skills/tdd/).

The tdd skill runs six phases for each task, in order:

- **Obligation scan.** Extracts this task's obligations from the spec. No implementation code exists yet.
- **Red.** Writes a failing test for each obligation and confirms the failure before any feature code is written.
- **Green.** Writes the minimum code to pass the tests. Nothing beyond what the tests require.
- **Obligation verify.** Confirms every obligation from the scan has a corresponding passing test.
- **Coverage.** Confirms no obligation is left uncovered.
- **Lint.** Runs the project's lint and type-check commands clean.

After a batch completes, execution stops for a human checkpoint. You review what was built and signal to continue. The next batch does not start until you do.

This is what separates `/ca:feature` from `/ca:sprint`. Sprint runs the full plan autonomously, with every auto-decision SMARTS-scored and logged; feature stops between every batch and waits for you. Use feature when you want to stay in the loop at each increment. Use [sprint](/reference/commands/sprint/) when the plan is well-understood and autonomous execution is appropriate.

## Commit Each Batch

When a batch is ready, run:

```text
/ca:commit
```

The [commit-gate skill](/reference/skills/commit-gate/) is the only path to a git commit. It runs nine phases: permission, branch, classification, verification (tests, lint, secrets scan), behavioral proof, diff review, selective stage, message, and commit. A finding at any phase stops the commit.

The gate does not auto-decide hard gates. A secret in the diff, a crypto change, or a branch violation is a true stop that requires your explicit resolution. "It looks right" is not authorization.

## Open the Pull Request

Once all batches are committed, run:

```text
/ca:pr
```

The [pr command](/reference/commands/pr/) runs the review fleet and clears every BLOCK-level finding before the PR is staged. A PR is never written directly to the default branch. Unresolved BLOCK findings are resolved first, not deferred.

## Know that the lane is complete

Before calling the feature done, verify all of these:

- the spec's acceptance criteria are unchanged or explicitly re-approved;
- every plan task is `ACCEPTED`;
- each acceptance criterion maps to a passing test obligation;
- the focused checks and the repository's full verification are green on the current head;
- commit-gate created the commit from an explicitly reviewed stage;
- the PR exists and its BLOCK-level review findings are clear.

The presence of code or a green focused test is not completion. The persisted spec, plan status,
fresh verification, commit, and PR are the proof chain.

## Common stops

| Stop | What it means | Resume path |
|---|---|---|
| A blocking `[CONFIRM-NN]` | The user owns an unresolved fact | Answer it, update the spec or plan, and resume the same slug |
| A task has no exact path or verification | The plan is underspecified | Return that task to writing-plans |
| The test does not fail in Red | The obligation is not demonstrated | Repair the test or the premise before implementation |
| A reviewer reports BLOCK | The batch is not accepted | Resolve the finding and rerun fresh verification |
| The session ends | Durable state remains on disk | Reinvoke feature; do not start over |

## Related

| Skill or command | Where |
|---|---|
| `/ca:feature` | [commands/feature](/reference/commands/feature/) |
| `/ca:commit` | [commands/commit](/reference/commands/commit/) |
| `/ca:pr` | [commands/pr](/reference/commands/pr/) |
| brainstorming | [skills/brainstorming](/reference/skills/brainstorming/) |
| writing-plans | [skills/writing-plans](/reference/skills/writing-plans/) |
| tdd | [skills/tdd](/reference/skills/tdd/) |
| executing-plans | [skills/executing-plans](/reference/skills/executing-plans/) |
| commit-gate | [skills/commit-gate](/reference/skills/commit-gate/) |

For the concepts behind gated lanes and gate strengths, see [Concepts](/concepts/).
