---
title: What Is codeArbiter
description: How codeArbiter orchestrates shared gated workflows in Claude Code, Codex, and Pi.
---

codeArbiter ships four sibling plugins from one marketplace: three governance hosts — `ca` for Claude
Code, `ca-codex` for Codex, and `ca-pi` for Pi — plus `ca-sandbox`, an infrastructure plugin unrelated
to gate enforcement (see [ca-sandbox](/guides/ca-sandbox/)). All three governance hosts inject the
same orchestrator responsibilities, enforce the same policy core, and use one checked-in
`.codearbiter/` directory for project context and audit state. See the
[Claude Code + Codex evidence](/getting-started/claude-code-and-codex/) for the verified boundary
between those two, and [Pi](/getting-started/pi/) for the third host's install and trust model.

## codeArbiter Holds the Gates; You Hold the Decisions

This is the organizing principle. codeArbiter enforces process; you make the calls. It
holds the [gates](/glossary/#gate): the test-first rule, the review chain, the secret and crypto checks, the
commit and merge boundaries. Work does not pass a gate without clearing it. But the
decisions those gates surface belong to you. Which design? Which trade-off? Whether to
merge? Those are yours to make. When a gate finds something worth your attention, it
reports the finding plainly and waits for your call. It does not resolve the question on
your behalf.

## How a Request Flows

1. **Command.** Invoke `/ca:feature` in Claude Code or `$ca-feature` in Codex. The generated
   command surface differs in spelling, not ownership or policy.
2. **Route.** The orchestrator hands the command to the workflow that owns that lane.
   `/ca:fix` and `$ca-fix` both reach the same test-first obligations.
3. **Dispatch.** The owning skill calls the agents the change actually demands: an author
   to write code test-first, plus a reviewer fleet matched to the diff (security,
   auth/crypto, dependencies, migrations, coverage).
4. **Gate.** Nothing advances until its gates are green. A failing test, a CRITICAL
   security finding, an unresolved decision: each is a real stop.
5. **Ship.** Code reaches version control only through the commit gate, and the default
   branch only through a pull request. Never a direct write.

<figure class="ca-diagram">
  <img src="/codeArbiter/diagrams/lane-flow.svg" alt="Lane flow: a command invocation routes to the owning skill, clears its gate, then ships to version control." loading="lazy" />
  <figcaption>One lane, five steps: command, route, gate, ship to a PR.</figcaption>
</figure>

<div class="ca-callout ca-callout--gate">
  <p class="ca-callout__label">Gate</p>
  A gate is not advice you can wave off. It is the only path that kind of change takes to
  ship. When a gate trips, codeArbiter surfaces the decision and waits for you to resolve
  it.
</div>

## Context Minimization

codeArbiter is built so almost nothing loads until it is needed. The only always-loaded
context is one file, the orchestrator persona, injected by a `SessionStart` hook, and only
in repositories whose project state opts in. A repo that hasn't opted in loads nothing at
all.

Everything else is paid for on demand: the routing table, the reference map, every skill
body, every agent body, the design-quality reference bundle. A node loads only when an
entry point reaches it. A typical `/ca:fix` touches the persona, the test-first skill, one
author, and maybe one reviewer. It never pulls the whole payload. Read-only meta commands
like `/ca:status`, `/ca:btw`, and `/ca:commands` route to no skill at all.

## The Lanes

Work is organized into lanes. Each is a sanctioned path with gates scaled to its risk.

- **Implementation:** `/ca:feature` (checkpointed), `/ca:sprint` ([autonomous](/concepts/smarts/),
  every auto-decision SMARTS-scored), `/ca:fix`, `/ca:refactor`, `/ca:debug`, `/ca:chore`,
  `/ca:spike`.
- **Commit & ship:** `/ca:commit`, `/ca:pr`, `/ca:watch`, `/ca:checkpoint`, `/ca:tribunal`,
  `/ca:release`, `/ca:add-dep`. `/ca:checkpoint` is the lean periodic sweep;
  `/ca:tribunal` is its rare, deep counterpart: an on-demand, resumable whole-codebase
  audit by eleven specialist lenses that files findings as GitHub issues on your approval
  and is never a required gate.
- **Decisions:** `/ca:adr`, `/ca:adr-status`, `/ca:reconcile`, `/ca:conflict`,
  `/ca:threat-model`.
- **Project & meta:** `/ca:init`, `/ca:status`, `/ca:audit`, `/ca:doctor`, `/ca:btw`, and
  more.

See [Concepts](../concepts/) for the ideas behind the lanes, and the
[Reference](../reference/) for the full, auto-generated catalog of commands, skills, and
agents.
