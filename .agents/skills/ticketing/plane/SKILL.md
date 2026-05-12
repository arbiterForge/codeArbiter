# Skill: ticketing (Plane variant — on-prem)

## Trigger

Loaded by the `ticketing` router when `mode: plane`. This file is never read
directly — invoke via the router.

This variant uses the **official Plane MCP server** (`@makeplane/plane-mcp-server`)
to talk to a self-hosted (on-prem) Plane instance over MCP. Auth is API-key-based
(OAuth in the upstream server is Plane Cloud only). Credentials live in shell
environment variables, never in the repo.

---

## Pre-Flight

Before any operation:

1. Confirm the MCP server is registered in `.claude/settings.json` (or
   `.agents/settings.json` — they are symlinked) under
   `mcpServers.plane`. If absent, STOP and instruct the user to follow the
   setup steps below.

2. Confirm the `mcp__plane__*` tool family is available in the current session.
   These tools are deferred — load schemas via `ToolSearch` on first use:

   ```
   ToolSearch query="select:mcp__plane__list_projects,mcp__plane__create_issue,mcp__plane__update_issue,mcp__plane__add_issue_comment,mcp__plane__list_issues"
   ```

   Exact tool names are determined by the installed `@makeplane/plane-mcp-server`
   version. If `ToolSearch` returns no matches for the `mcp__plane__` prefix,
   the MCP server is not running — STOP.

3. Confirm the env vars named in `ticketing-config.md` are non-empty in the
   MCP server process environment. The variant cannot read the user's shell
   directly, but if any MCP call returns an auth or URL error, treat it as
   evidence the env vars are missing or wrong.

4. Read from `ticketing-config.md` (frontmatter only): `plane_base_url`,
   `plane_workspace_slug`, `plane_project_id`. Pass `workspace_slug` and
   `project_id` to every MCP tool call that requires them.

---

## Operations

### Open (create a work item)

**Caller contract:** a subagent (out-of-scope finding) or a `/feature` / `/fix`
/ `/ticket open` invocation provides title and body.

**Actions:**

1. Compose the work item description from the same four sections used by the
   in-repo variant (Context / Finding / Why out of scope / Suggested handling).
   For `/feature` and `/fix`: use the command description as the body.
2. Call the MCP tool that creates a work item (`mcp__plane__create_issue` or
   the equivalent from the installed server) with `workspace_slug`,
   `project_id`, `title`, and `description`.
3. Capture the returned issue ID and short URL.
4. Hand the issue ID back to the caller. For `/feature` and `/fix`, the parent
   threads the ID into the commit message and PR body during subsequent gates.

**Gate:** BLOCK on MCP call failure — see Failure Modes below for the
fallback (`ticketing-sync-failures.md`).

### Comment (used by commit-gate Phase 8)

**Caller contract:** `commit-gate` Phase 8 produces a committed SHA and the
issue ID associated with the work.

**Actions:**

1. Call the MCP comment tool with the issue ID and a body of the form:
   `Committed: <SHA> (<commit subject>)`.
2. Return success/failure to the caller. Do not block the commit gate on this
   call — log and continue per the failure mode.

### Transition (used on PR merge)

**Caller contract:** PR-merge handling determines that an issue is now `done`.

**Actions:**

1. Call the MCP transition tool with the issue ID and the project's `done`
   state (read state ID from the MCP `list_states` tool the first time per
   session; cache for the session).
2. Return success/failure. Do not block on failure.

### List (surface scan)

**Caller contract:** `/ticket list` or `/status`.

**Actions:**

1. Call the MCP `list_issues` tool with a filter restricting to open states.
2. Output one line per issue: `<id> | <title> | <state> | <updated-date>`.
3. Do NOT fetch full bodies. The output is the index equivalent for Plane mode.

**Gate:** BLOCK if the caller asks for body details — redirect to a Plane
URL or `mcp__plane__get_issue` invoked explicitly.

### Move (manual transition)

**Caller contract:** `/ticket move <id> <state>`.

**Actions:** call the MCP transition tool with the user-supplied state name.

---

## Setup (one-time, documented for the user)

1. **Issue an API key in your on-prem Plane instance.** Plane admin UI →
   workspace settings → API tokens. Scope to the target workspace; record the
   key in your password manager.

2. **Export the env vars in your shell.** Add to `~/.bashrc`, `~/.zshrc`, or
   `~/.config/codeArbiter/plane.env` (gitignored, sourced manually). Example:

   ```sh
   export PLANE_API_URL="https://plane.internal.example.com"
   export PLANE_API_KEY="<your-api-key>"
   export PLANE_WORKSPACE_SLUG="<your-workspace-slug>"
   ```

3. **Register the MCP server.** Confirm `.claude/settings.json` has under
   `mcpServers`:

   ```json
   "plane": {
     "command": "npx",
     "args": ["-y", "@makeplane/plane-mcp-server"],
     "env": {
       "PLANE_API_URL": "${PLANE_API_URL}",
       "PLANE_API_KEY": "${PLANE_API_KEY}",
       "PLANE_WORKSPACE_SLUG": "${PLANE_WORKSPACE_SLUG}"
     }
   }
   ```

   The literal `${VAR}` references the shell env var by name; the MCP runner
   substitutes the value at process spawn time. The value never appears in any
   committed file.

4. **Fill `ticketing-config.md`.** Set `enabled: true`, `mode: plane`, and
   populate `plane_base_url`, `plane_workspace_slug`, `plane_project_id`.

5. **Start a fresh Claude Code session.** Confirm `mcp__plane__*` tools appear
   via `ToolSearch`.

---

## Hard Rules

- MUST NOT store any API key, token, or credential in `ticketing-config.md`,
  in any tracked file, in any committed file, or in any LLM prompt. Env vars
  only.
- MUST NOT pass env var values through the agent text — reference them by
  name (`${PLANE_API_KEY}`) in settings.json, never inline.
- MUST NOT call the Plane REST API directly. Always go through the MCP server.
- MUST NOT block `/feature`, `/fix`, `/commit`, or `/pr` on MCP failures.
  Log, queue, and continue.
- MUST NOT read work item bodies during `list` or surface scans. Body reads
  require explicit user intent.
- MUST NOT author an ADR as a side-effect of any Plane operation.

---

## Failure Modes

| Failure | Response |
|---|---|
| MCP server not running / not registered | STOP; instruct user to run setup steps |
| `ToolSearch` returns no `mcp__plane__*` matches | STOP; same as above |
| Auth error from MCP (401 / 403) | Append entry to `projectContext/ticketing-sync-failures.md`; instruct user to verify `PLANE_API_KEY` env var |
| Network / Plane on-prem unreachable | Append to `ticketing-sync-failures.md`; do NOT block the calling workflow |
| Issue ID not found on comment/transition | Append to `ticketing-sync-failures.md`; surface to caller as a warning |
| Workspace or project ID missing in config | STOP; instruct user to populate `ticketing-config.md` |

### `ticketing-sync-failures.md` format

Append-only at `.agents/projectContext/ticketing-sync-failures.md`:

```
[ISO-8601] | OP: <create_issue|comment|transition|list|move> | ARGS: <short summary> | ERROR: <short error text>
```

The variant retries each pending entry on its next successful MCP call. After
three consecutive retry failures for the same op, surface a `[NEEDS-TRIAGE]`
note to the user and stop retrying that entry.
