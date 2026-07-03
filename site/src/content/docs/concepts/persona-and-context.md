---
title: The Persona-Register Split
description: "How codeArbiter separates the orchestrator, author, and reviewer personas to keep each role sharp and its context footprint small."
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
- **The tribunal lenses.** Eleven `tribunal-*` agents, one per lens, dispatched only by
  [`/ca:tribunal`](/reference/commands/tribunal/). See the [tribunal command](/reference/commands/tribunal/)
  page for the full roster, starting with [`tribunal-appsec-reviewer`](/reference/agents/tribunal-appsec-reviewer/).
- **Internal analysts.** Never dispatched directly by a user: `scout`, `grader`,
  `decision-challenger`, `finding-triage`, `checkpoint-aggregator`, `map-structure`,
  `map-deps`.

## Where it's decided

The orchestrator persona itself lives in `plugins/ca/ORCHESTRATOR.md`. The split is a
recorded decision, not an accident of file layout. See ADR-0005.
