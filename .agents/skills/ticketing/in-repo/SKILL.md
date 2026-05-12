# Skill: ticketing (in-repo variant)

## Trigger

Loaded by the `ticketing` router when `mode: in-repo`. This file is never read
directly — invoke via the router.

## Pre-Flight

Before any operation:

1. Confirm `.agents/projectContext/tickets/` exists. If absent, create it on
   first ticket open: `tickets/`, `tickets/open/`, `tickets/closed/`,
   `tickets/INDEX.md`.
2. For close/show/list: confirm `INDEX.md` exists; refuse with a clear message
   if it does not.

---

## Operations

### Open (file a new ticket)

**Caller contract:** a subagent or `/ticket` command provides:
- `title` (short, < 80 chars)
- `body` populated for all four required sections

**Actions:**

1. Compute `id = <YYYY-MM-DD>-<NNN>` where `<NNN>` is the next zero-padded
   integer not already used today. Scan both `open/` and `closed/` to compute.
2. Compute `slug` from the title: lowercase, non-alphanumerics to `-`, trim,
   truncate to 40 chars.
3. Write `tickets/open/<id>-<slug>.md` with this exact frontmatter and body
   shape (no extra fields, no extra sections):

   ```yaml
   ---
   id: <id>
   title: <title>
   opened_by: <caller agent name> via <caller skill or command>
   opened_at: <ISO-8601 UTC>
   status: open
   disposition:
   disposition_note:
   closed_at:
   closed_by:
   ---

   ## Context
   <what the caller was doing when it noticed the finding>

   ## Finding
   <the out-of-scope observation>

   ## Why it's out of scope
   <why the caller did not act on it>

   ## Suggested handling (optional)
   <hint, if any — may be empty>
   ```

4. Append a row to `tickets/INDEX.md` under `## Open`:

   `- <id> | <title> | opened by <caller> | <opened_at-date>`

5. Return the `id` to the caller. Do not echo the ticket body back.

**Gate:** BLOCK if any of the four sections is empty (`Suggested handling` may
contain a single dash but must exist as a section).

### Close (file substance to its real home, then close ticket)

**Caller contract:** the parent (codeArbiter) runs `/ticket close <id>` and
specifies a disposition.

**Actions:**

1. Locate the ticket file in `tickets/open/`. If not found, STOP and surface.
2. Prompt the parent for a disposition from this exact set:

   - `incorporated-to:03-task-backlog` — substance filed into
     `projectContext/decomposition/03-task-backlog.md`
   - `incorporated-to:open-tasks` — substance filed into
     `projectContext/open-tasks.md`
   - `incorporated-to:gap-doc` — recorded as a known gap (no immediate action)
   - `escalated-to:open-questions` — a `CONFIRM-NN` was appended to
     `projectContext/open-questions.md`
   - `escalated-to:user` — surfaced synchronously to the user
   - `duplicate-of:<other-ticket-id>`
   - `rejected`
   - `other` (requires a non-empty `disposition_note`)

3. **REJECT** any disposition starting with `adr-opened:` or `adr:`. ADRs
   require user attribution per AGENTS.md §3 and may never be created as a
   disposition. If the parent attempts this, refuse and re-prompt.

4. If `incorporated-to:*` or `escalated-to:open-questions`: confirm the target
   file has been updated with the substance BEFORE closing. The close
   operation does not file the substance — that is the parent's job. The
   close just records that it happened.

5. Update the ticket frontmatter:
   - `status: closed`
   - `disposition: <chosen value>`
   - `disposition_note: <free text, required for 'other'>`
   - `closed_at: <ISO-8601 UTC>`
   - `closed_by: <name from git config user.name>`

6. `git mv` (or equivalent file move) the ticket from `open/` to `closed/`.

7. Update `INDEX.md`:
   - Remove the row from `## Open`.
   - Insert a row at the top of `## Recently closed (last 30 days)`:
     `- <id> | <title> | disposition: <disposition> | <closed_at-date>`
   - Prune rows older than 30 days from the recently-closed section. The full
     files remain in `closed/` regardless.

**Gate:** BLOCK on any `adr-*` disposition attempt. BLOCK if `other` is chosen
without a `disposition_note`. BLOCK if `incorporated-to:*` is recorded but the
target file shows no corresponding edit in the current session.

### Show (read one ticket body)

**Caller contract:** `/ticket show <id>`.

**Actions:**

1. Locate the ticket in `open/` or `closed/`. If not found, STOP.
2. Output the full file contents to the user verbatim.
3. Do not update the index. Do not read other tickets.

### List (surface scan)

**Caller contract:** `/ticket list` or `/status`.

**Actions:**

1. Read `INDEX.md` only. Do not open any file under `open/` or `closed/`.
2. Output the index contents verbatim.

**Gate:** BLOCK if the caller asks for body details — redirect them to
`/ticket show <id>`.

---

## INDEX.md format (authoritative)

```markdown
# Tickets Index

<!-- Auto-maintained by the in-repo ticketing variant. Hand-edits are not -->
<!-- preserved on the next create/close. -->

## Open

- <id> | <title> | opened by <caller> | <opened-date>

## Recently closed (last 30 days)

- <id> | <title> | disposition: <disposition> | <closed-date>
```

When no tickets exist in a section, leave a single placeholder line:
`_None._`

---

## Hard Rules

- MUST NOT read ticket bodies unless the caller invoked `show`. `list` and
  surface scans use `INDEX.md` only.
- MUST NOT accept `adr-opened:*`, `adr:*`, or any ADR-creation disposition.
  ADRs require user attribution and are authored only via `/adr`.
- MUST NOT close a ticket marked `incorporated-to:*` without confirming the
  target file received the substance.
- MUST NOT modify frontmatter fields other than the close-time fields listed
  in the Close operation. Other fields are immutable once written.
- MUST NOT delete ticket files. Closed tickets remain in `closed/`
  indefinitely.
- MUST NOT bulk-read `open/*` or `closed/*` for any operation. INDEX is the
  surface contract.

---

## Failure Modes

| Failure | Response |
|---|---|
| `tickets/` missing | Create on first open |
| `INDEX.md` missing on close/show/list | STOP; instruct user to re-init via `/ticket list` after a fresh open |
| Ticket id not found on close/show | STOP; surface |
| Required body section empty on open | BLOCK; ask caller to populate |
| Disposition is `adr-*` | REJECT; re-prompt |
| `other` disposition without note | BLOCK; require note |
| `incorporated-to:*` without target file edit in session | BLOCK; require the parent to file the substance first |
