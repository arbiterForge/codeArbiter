---
title: Overview
description: How codeArbiter orchestrates gated software-engineering workflows in Claude Code.
---

codeArbiter is a Claude Code plugin. When you enable it in a repository, it installs a
single orchestrator persona that mediates every request. It orchestrates. It does not
freelance. Every user intent flows through a slash command, routes to the one skill or
agent that owns it, and clears its gates before it ships.

## You hold the gates; the user holds the decisions

This is the organizing principle. codeArbiter is decisive about process and deferential
about choices. It holds the gates: the test-first rule, the review chain, the secret and
crypto checks, the commit and merge boundaries. It will not wave work through them. But
the decisions those gates surface belong to the user. Which design? Which trade-off?
Whether to merge? Those are yours. The plugin states; it does not hedge. It stops; it does
not silently reconcile.

## How a request flows

1. **Command.** You invoke a namespaced slash command: `/ca:feature`, `/ca:fix`,
   `/ca:commit`, and so on. (The plugin is named `ca`, and Claude Code namespaces every
   command behind it.)
2. **Route.** The orchestrator hands the command to the single skill or agent that owns
   that lane. `/ca:fix` goes to the test-first gate, `/ca:adr` to the decision-lifecycle
   skill.
3. **Dispatch.** The owning skill calls the agents the change actually demands: an author
   to write code test-first, plus a reviewer fleet matched to the diff (security,
   auth/crypto, dependencies, migrations, coverage).
4. **Gate.** Nothing advances until its gates are green. A failing test, a CRITICAL
   security finding, an unresolved decision: each is a real stop.
5. **Ship.** Code reaches version control only through the commit gate, and the default
   branch only through a pull request. Never a direct write.

<figure class="ca-diagram">
  <img src="../diagrams/lane-flow.svg" alt="Lane flow: a command invocation routes to the owning skill, clears its gate, then ships to version control." loading="lazy" />
  <figcaption>One lane, five steps: command, route, gate, ship to a PR.</figcaption>
</figure>

<div class="ca-callout ca-callout--gate">
  <p class="ca-callout__label">Gate</p>
  A gate is not advice you can wave off. It is the only path that kind of change takes to
  ship. When a gate trips, codeArbiter surfaces the decision and waits; it does not invent
  an answer and push past.
</div>

## Context minimization

codeArbiter is built so almost nothing loads until it is needed. The only always-loaded
context is one file, the orchestrator persona, injected by a `SessionStart` hook, and only
in repositories whose project state opts in. A repo that hasn't opted in loads nothing at
all.

Everything else is paid for on demand: the routing table, the reference map, every skill
body, every agent body, the design-quality reference bundle. A node loads only when an
entry point reaches it. A typical `/ca:fix` touches the persona, the test-first skill, one
author, and maybe one reviewer. It never pulls the whole payload. Read-only meta commands
like `/ca:status`, `/ca:btw`, and `/ca:commands` route to no skill at all.

## The lanes

Work is organized into lanes. Each is a sanctioned path with gates scaled to its risk.

- **Implementation:** `/ca:feature` (checkpointed), `/ca:sprint` (autonomous), `/ca:fix`,
  `/ca:refactor`, `/ca:debug`, `/ca:chore`, `/ca:spike`.
- **Commit & ship:** `/ca:commit`, `/ca:pr`, `/ca:watch`, `/ca:checkpoint`, `/ca:release`,
  `/ca:add-dep`.
- **Decisions:** `/ca:adr`, `/ca:adr-status`, `/ca:reconcile`, `/ca:conflict`,
  `/ca:threat-model`.
- **Project & meta:** `/ca:init`, `/ca:status`, `/ca:audit`, `/ca:doctor`, `/ca:btw`, and
  more.

See [Concepts](../concepts/) for the ideas behind the lanes, and the
[Reference](../reference/) for the full, auto-generated catalog of commands, skills, and
agents.
