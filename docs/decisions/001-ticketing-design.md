---
id: ADR-001
title: Ticketing design — in-repo scope-overflow inbox + optional Plane on-prem
status: proposed
date: 2026-05-12
last_challenged:
authors: SUaDtL (user)
---

<!--
Copyright (c) 2026 suadtl
Author: suadtl
Created: 2026-05-12
File: 001-ticketing-design.md
-->


# ADR-001: Ticketing Design

## Context

codeArbiter previously had no clean channel for a subagent to log a finding that fell outside its scope. Such findings either inlined into the agent's response (lost in transcript), got tossed into `open-tasks.md` (which is general task tracking, not provenance-stamped overflow), or were silently dropped. The framework needed a sanctioned inbox for these out-of-scope observations.

A separate but related concern: existing artifacts under `${FRAMEWORK_ROOT}/.agents/agents/`, `${FRAMEWORK_ROOT}/.agents/commands/`, and `${PROJECT_ROOT}/.agents/projectContext/decisions/` are routinely read by agents during routing, even when only a one-line description is required. Eagerly loading bodies of artifacts that are only invoked occasionally is context-wasteful.

## Decision

Introduce an optional `ticketing-router` skill with two modes selectable via `${PROJECT_ROOT}/.agents/projectContext/ticketing-config.md`:

1. **`in-repo`** — a lightweight scope-overflow inbox. Subagents file tickets (four-section markdown files) in `${PROJECT_ROOT}/.agents/projectContext/tickets/open/`. The codeArbiter parent triages each ticket by filing the substance into the correct existing artifact (`03-task-backlog.md`, `open-questions.md` as a `CONFIRM-NN`, a gap doc, or by surfacing to the user) and then closing the ticket with a disposition note. The ticket itself is an inbox, not a project tracker.

2. **`plane`** — uses the official Plane MCP server (`@makeplane/plane-mcp-server`) to write to a self-hosted Plane instance. Tickets become Plane work items; `/feature` and `/fix` auto-create work items; `commit-gate` Phase 8 auto-comments with the commit SHA; PR merge auto-transitions to done.

The skill is structured as a **thin router** that reads `mode` from config and `@`-imports only the variant in use. The unused variant is never loaded.

A strict **no-read-without-reason** rule applies. The router exposes `INDEX.md` (in-repo) or `mcp__plane__list_issues` (Plane) for cheap surface scans; ticket bodies open only via explicit `/ticket show <id>`. This same pattern is retrofitted to `${FRAMEWORK_ROOT}/.agents/agents/` (new `INDEX.md`), `${FRAMEWORK_ROOT}/.agents/commands/` (existing `COMMANDS.md` formalized as the index), and `${PROJECT_ROOT}/.agents/projectContext/decisions/` (existing `README.md` index schema populated).

**Disposition vocabulary explicitly excludes ADR authoring.** A ticket close cannot result in a new ADR. Decision-worthy findings escalate to `open-questions.md` (as a `CONFIRM-NN`) or to the user. ADRs are authored only via `/adr` with explicit user attribution, consistent with AGENTS.md §5's existing "No decisions without user attribution" gate.

**Plane authentication is API-key-based via shell environment variables**, not OAuth. The official `@makeplane/plane-mcp-server` supports OAuth only for Plane Cloud; on-prem instances use API keys passed through env vars (`PLANE_API_URL`, `PLANE_API_KEY`, `PLANE_WORKSPACE_SLUG`). The `mcpServers` entry in `.claude/settings.json` references these env vars by name (`${PLANE_API_KEY}`), never inlining values. No token files are stored on disk under the framework's management.

## Alternatives Considered

- **Custom Plane REST adapter.** Rebuilds what `@makeplane/plane-mcp-server` already maintains. Rejected: maintenance burden and security surface (token file handling, chmod checks) we don't need to own. The MCP server costs us an MCP-capable-runner requirement but Claude Code is fine.
- **External integration with Jira or OpenProject at v1.** Deferred. Plane is sufficient for v1; Jira/OpenProject can be added as additional variants if needed without changing the router design.
- **Bulk `[NEEDS-TRIAGE]` markers inlined in agent output (no separate inbox).** Rejected: loses provenance, hard to triage, lossy across long sessions. The inbox model preserves the four-section context per finding.
- **Make ticketing always-on rather than opt-in.** Rejected: the framework should ship with `enabled: false` so that projects without a ticketing need don't carry the conceptual weight.
- **Permit `adr-opened:*` as a ticket disposition.** Rejected (this was an explicit user correction during planning): allowing parent agents to auto-author ADRs from subagent findings violates AGENTS.md §5's user-attribution requirement for decisions and would launder unattributed decisions into the project's permanent record.

## Consequences

**Positive:**
- Subagents have a sanctioned channel for out-of-scope observations. No more silent drops or transcript-only mentions.
- Context cost stays low. The router only loads the active variant; routine flows scan indexes, not bodies.
- The retrofits (`agents/INDEX.md`, formalized `COMMANDS.md`, populated `decisions/README.md`) extend the same pattern to high-traffic artifact directories.
- Plane integration is thin (a contract over MCP tools), so swapping or upgrading the MCP server is low-cost.

**Negative / Tradeoffs:**
- Plane mode constrains us to MCP-capable runners. Arbitrary CI agents that lack MCP support cannot use Plane mode; in-repo mode remains the zero-dependency fallback.
- The router + variant pattern is new for this repo. Other skills may adopt it, but each adoption is judgment-by-judgment.
- The ADR-disposition prohibition means decision-worthy findings take a two-step path: ticket → CONFIRM-NN → ADR. That's the desired flow but adds latency vs. an auto-author shortcut.

This tradeoff sits at §2 level 3 (Maintainability and reviewability) for the disposition prohibition and §2 level 1 (Security and compliance) for the credential-handling decision — see AGENTS.md §2 for the hierarchy.

## Implementation Notes

- New files: `ticketing-config.md`, `${FRAMEWORK_ROOT}/.agents/skills/ticketing-router/{SKILL.md,in-repo/SKILL.md,plane/SKILL.md}`, `${PROJECT_ROOT}/.agents/projectContext/tickets/{INDEX.md,open/,closed/}`, `${FRAMEWORK_ROOT}/.agents/commands/ticket.md`, `.claude/commands/ticket.md`, `${FRAMEWORK_ROOT}/.agents/agents/INDEX.md`.
- Modified: AGENTS.md (§3 hard rules, §4 map, §5 routing, §6 read-on-invocation note), `secrets-policy.md` (env-var approved location), `.gitignore` (`.env`, `.env.local`), `${FRAMEWORK_ROOT}/.agents/settings.json` (`mcpServers.plane`), 9 subagent definitions (out-of-scope clause), `decisions/README.md` (this ADR row), `COMMANDS.md` (normalized + `/ticket` row).
- Default ships disabled: `enabled: false` in `ticketing-config.md`. Users opt in.

## Followups

- First in-repo ticket once enabled: audit any code paths that read `${FRAMEWORK_ROOT}/.agents/agents/*.md` in bulk and update them to consult `INDEX.md` first.
- Validate that `@makeplane/plane-mcp-server` tool names match the names referenced in `${FRAMEWORK_ROOT}/.agents/skills/ticketing-router/plane/SKILL.md` on first real setup; correct any mismatches.
