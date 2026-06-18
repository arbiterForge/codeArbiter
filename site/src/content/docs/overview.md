---
title: Overview
description: How codeArbiter orchestrates gated software-engineering workflows in Claude Code.
---

codeArbiter is a Claude Code plugin. When enabled in a repository, it installs a
single orchestrator persona that mediates every request: it **orchestrates; it
does not freelance**. Every user intent flows through a slash command, routes to
the one skill or agent that owns it, and clears its gates before it ships.

## You hold the gates; the user holds the decisions

This is the organizing principle. codeArbiter is decisive about *process* and
deferential about *choices*. It holds the gates — the test-first rule, the review
chain, the secret and crypto checks, the commit and merge boundaries — and will
not wave work through them. But the decisions those gates surface (which design,
which trade-off, whether to merge) belong to the user. The plugin states; it does
not hedge. It stops; it does not silently reconcile.

## How a request flows

1. **Command.** The user invokes a namespaced slash command — `/ca:feature`,
   `/ca:fix`, `/ca:commit`, and so on. (The plugin is named `ca`; Claude Code
   namespaces every command behind it.)
2. **Route.** The orchestrator routes the command to the single skill or agent
   that owns that lane — `/ca:fix` to the test-first gate, `/ca:adr` to the
   decision-lifecycle skill, and so on.
3. **Dispatch.** The owning skill dispatches the agents the change actually
   demands — an author to write code test-first, a reviewer fleet matched to the
   diff (security, auth/crypto, dependencies, migrations, coverage).
4. **Gate.** Nothing advances until its gates are green. A failing test, a
   CRITICAL security finding, an unresolved decision — these are real stops.
5. **Ship.** Code reaches version control only through the commit gate, and the
   default branch only through a pull request — never a direct write.

## Context minimization

codeArbiter is built so that almost nothing loads until it is needed. The only
always-loaded context is a single file — the orchestrator persona — injected by a
`SessionStart` hook, and only in repositories whose project state opts in. A repo
that hasn't opted in loads nothing at all.

Everything else — the routing table, the reference map, all of the skill bodies,
all of the agent bodies, the design-quality reference bundle — is paid for on
demand, only when an entry point is invoked, and only for the nodes that entry
point actually reaches. A typical `/ca:fix` touches the persona, the test-first
skill, one author, and maybe one reviewer — not the whole payload. Read-only meta
commands like `/ca:status`, `/ca:btw`, and `/ca:commands` route to no skill at all.

## The lanes

Work is organized into lanes, each a sanctioned path with gates scaled to its
risk:

- **Implementation** — `/ca:feature` (checkpointed), `/ca:sprint` (autonomous),
  `/ca:fix`, `/ca:refactor`, `/ca:debug`, `/ca:chore`, `/ca:spike`.
- **Commit & ship** — `/ca:commit`, `/ca:pr`, `/ca:watch`, `/ca:checkpoint`,
  `/ca:release`, `/ca:add-dep`.
- **Decisions** — `/ca:adr`, `/ca:adr-status`, `/ca:reconcile`, `/ca:conflict`,
  `/ca:threat-model`.
- **Project & meta** — `/ca:init`, `/ca:status`, `/ca:audit`, `/ca:doctor`,
  `/ca:btw`, and more.

See [Concepts](../concepts/) for the ideas behind the lanes, and the
[Reference](../reference/) for the full, auto-generated catalog of commands,
skills, and agents.
