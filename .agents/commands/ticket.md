# /ticket

## Purpose

The user- and subagent-facing surface for the optional ticketing skill. Files
out-of-scope findings, lists open tickets, and closes them with a triage
disposition. Routes through the `ticketing` skill, which dispatches to the
in-repo or Plane variant based on `projectContext/ticketing-config.md`.

When ticketing is disabled (default), this command returns a disabled response
and otherwise has no effect.

## Subcommands

```
/ticket "title" -- "finding body"     # open a new ticket
/ticket close <id>                    # interactive close, prompts for disposition
/ticket show <id>                     # read a ticket body explicitly
/ticket list                          # surface scan from INDEX (in-repo) or Plane list
/ticket move <id> <state>             # (Plane mode only) transition issue state
/ticket config                        # open ticketing-config.md for editing
```

## What Each Subcommand Does

### `/ticket "title" -- "finding body"`

Files a new ticket. The body MUST contain the four sections required by the
variant: Context, Finding, Why it's out of scope, Suggested handling. Subagents
invoke this via the ticketing skill rather than as a slash command; the
command surface is primarily for user-initiated triage.

### `/ticket close <id>`

Interactive close. The command prompts for a disposition from the fixed set
(see below). It does NOT file the substance into the destination doc — that is
the caller's (parent's) responsibility BEFORE close. The close just records
that the substance landed.

**Valid dispositions:**

- `incorporated-to:03-task-backlog`
- `incorporated-to:open-tasks`
- `incorporated-to:gap-doc`
- `escalated-to:open-questions` (a CONFIRM-NN was appended)
- `escalated-to:user` (raised synchronously)
- `duplicate-of:<id>`
- `rejected`
- `other` (requires non-empty note)

**REJECTED dispositions:**
- `adr-opened:*`, `adr:*`, or any ADR-creation value. ADRs require user
  attribution and are authored only via `/adr`.

### `/ticket show <id>`

Opens the ticket body. This is the only sanctioned way to read a ticket body —
`/status` and `/ticket list` use the INDEX only.

### `/ticket list`

Surface scan. In-repo mode reads `tickets/INDEX.md`. Plane mode calls the MCP
`list_issues` tool with a filter for open states. Neither reads bodies.

### `/ticket move <id> <state>` (Plane mode only)

Manual transition of a Plane work item to a named state. No-op in in-repo
mode (the in-repo model has only `open` and `closed`).

### `/ticket config`

Opens `.agents/projectContext/ticketing-config.md` for editing. Toggle the
skill on/off, switch modes, or update Plane workspace/project settings here.

## Routes To

`ticketing` skill router (`.agents/skills/ticketing/SKILL.md`) → in-repo or
Plane variant per `ticketing-config.md`.

## Hard Gates

- MUST NOT read ticket bodies during `list`. Use `show` for explicit body
  reads.
- MUST NOT accept any `adr-*` disposition on close.
- MUST NOT close an `incorporated-to:*` ticket without confirming the target
  doc received the substance.
- Plane mode MUST NOT fall back to direct Plane REST calls if the MCP server is
  unavailable. Append to `ticketing-sync-failures.md` and continue.

## When NOT to Use

- For starting a new feature: use `/feature` — that command auto-creates a
  Plane work item (in Plane mode) without needing `/ticket`.
- For ADRs or decisions: use `/adr` or `/surface-conflict`.
- For commits: use `/commit`.
- For `CONFIRM-NN` items: use `/adr` or `/adr-status`.

## Disabled State

If `ticketing-config.md` has `enabled: false` (the default) or is absent, every
subcommand returns:

> Ticketing is disabled. Findings that would normally be filed as tickets are
> inlined in agent output with a `[NEEDS-TRIAGE]` marker. To enable, edit
> `.agents/projectContext/ticketing-config.md` and set `enabled: true`.
