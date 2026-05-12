# Ticketing Configuration

<!-- Read by the `ticketing-router` skill. -->
<!-- If this file is absent OR `enabled: false`, the ticketing-router skill is a no-op. -->
<!-- Default ships with `enabled: false`; users opt in by editing the frontmatter below. -->

---
enabled: false
mode: in-repo
plane_base_url:
plane_workspace_slug:
plane_project_id:
plane_env_var_api_key: PLANE_API_KEY
plane_env_var_api_url: PLANE_API_URL
plane_env_var_workspace_slug: PLANE_WORKSPACE_SLUG
---

## Field Reference

| Field | Required when | Purpose |
|---|---|---|
| `enabled` | always | `true` activates the ticketing-router skill. `false` makes it a no-op. |
| `mode` | `enabled: true` | `in-repo` or `plane`. Selects which variant the router `@`-imports. |
| `plane_base_url` | `mode: plane` | On-prem Plane URL, e.g. `https://plane.internal.example.com`. |
| `plane_workspace_slug` | `mode: plane` | Plane workspace slug the variant targets. |
| `plane_project_id` | `mode: plane` | Plane project ID the variant targets. |
| `plane_env_var_*` | `mode: plane` | Names of shell env vars the MCP server reads. Values NEVER appear in this file. |

## Mode: `in-repo`

A lightweight scope-overflow inbox. Subagents file findings as tickets in `${PROJECT_ROOT}/.agents/projectContext/tickets/open/`. The parent reads each ticket, decides where the substance belongs (a task backlog entry, a `CONFIRM-NN` in `open-questions.md`, a gap doc, or a synchronous user escalation), files the substance there, and closes the ticket with a disposition note. The ticket itself is not a project tracker — it's an inbox.

## Mode: `plane`

Uses the official Plane MCP server (`@makeplane/plane-mcp-server`) over MCP. **We run Plane on-prem, so authentication is via API key supplied through environment variables** — OAuth is Plane Cloud only.

Required environment variables (names configurable above; values live in the user's shell, never in this file or any committed file):

- `PLANE_API_URL` — the on-prem Plane base URL
- `PLANE_API_KEY` — API key issued by the Plane admin UI
- `PLANE_WORKSPACE_SLUG` — workspace slug

See `${FRAMEWORK_ROOT}/.agents/skills/ticketing-router/plane/SKILL.md` for setup steps.

## Read-on-invocation guarantee

The router skill reads only the frontmatter from this file on every invocation. It `@`-imports the variant matching `mode` and never loads the unused variant. When `enabled: false`, neither variant is loaded.
