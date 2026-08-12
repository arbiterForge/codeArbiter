---
title: The Persona-Register Split
description: "How codeArbiter separates the orchestrator, author, and reviewer personas to keep each role sharp and its context footprint small."
journey:
  level: Power user
  time: 6 min
  outcome: "a clear model of who routes, who writes, who reviews, and how to inspect a dispatch without trying to invoke an internal role directly."
  prerequisites:
    - Understand command, skill, and agent terminology
  proof: "You can trace one lane from public command to owning skill to its author or reviewer role."
---

codeArbiter speaks with more than one voice, deliberately. The **orchestrator** persona is
terse and decisive; it routes, gates, and states. The **author** and **reviewer** agents
each carry their own focused register and tools, scoped to their job. Splitting the persona
register keeps each role sharp. The orchestrator isn't trying to also be a backend engineer,
and a security reviewer isn't trying to also be a copywriter. Each agent loads only the
context its role needs, which is also what keeps the standing footprint small.

## The roster

Every agent ships as its own file under `plugins/ca/agents/`. Each carries only the tools its
role needs.

Three agents carry write tools (`Edit`/`Write`): the authors.

- [`backend-author`](/reference/agents/backend-author/)
- [`frontend-author`](/reference/agents/frontend-author/)
- [`infra-author`](/reference/agents/infra-author/)

Every reviewer is read-only by construction. The roster splits into three families:

- **The review fleet.** The six checkpoint/review reviewers ([`security-reviewer`](/reference/agents/security-reviewer/),
  `auth-crypto-reviewer`, `dependency-reviewer`, `migration-reviewer`, `coverage-auditor`,
  `architecture-drift-reviewer`), plus [`design-quality-reviewer`](/reference/agents/design-quality-reviewer/)
  for generated, user-facing output.
- **The tribunal lens executor.** One [`tribunal-lens-reviewer`](/reference/agents/tribunal-lens-reviewer/)
  agent, dispatched once per active lens by [`/ca:tribunal`](/reference/commands/tribunal/). Each dispatch
  names one of the eleven lens cards, documented under [tribunal lenses](/reference/#tribunal-lenses).
- **Internal analysts.** Never dispatched directly by a user: `scout`, `grader`,
  `decision-challenger`, `finding-triage`, `checkpoint-aggregator`, `map-structure`,
  `map-deps`.

## Where it's decided

The orchestrator persona itself lives in `plugins/ca/ORCHESTRATOR.md`. The split is a
recorded decision, not an accident of file layout. See ADR-0005.

## What this means in practice

Invoke the lane command; do not try to dispatch a specialist agent by name. The orchestrator chooses
the owning skill, and that skill dispatches the author or reviewer with the narrow tools and context
it needs. A reviewer finding returns to the lane for triage; the reviewer does not silently edit the
author's files.

Generated [agent reference pages](/reference/#agents) show each role's purpose, tools, and exact
source. Use them to understand who may be dispatched, not as a second command surface.

## Inspect a Dispatch

Start at the public command reference and follow its owning skill. The skill body names each role it
may dispatch and the condition that activates it. Then open the generated agent page to inspect that
role's tools, model tier, constraints, and exact source.

Claude Code can dispatch packaged agents through its native task tool. Codex currently executes the
same reviewer and author charters in host-provided agent threads, with an inline fallback only on
older hosts where isolation is not mandatory; Pi uses its supervised child
path where supported. That host difference changes isolation mechanics, not ownership or the gate
that consumes the result. The [compatibility matrix](/getting-started/compatibility/#host-differences)
records the current boundary.
