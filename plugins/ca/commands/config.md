---
description: Browse and change every codeArbiter setting — grouped, with current value, source, and default. Persists to Claude Code settings.json env blocks; changes apply at the next session start.
argument-hint: (none) | <KEY> | <KEY> <VALUE> | doctor | launch
---

# /ca:config — settings browser and editor

Every tunable behavior in the plugin family is an environment variable (`CODEARBITER_*`,
`FARM_*`, `CA_SANDBOX_*`), inventoried in one registry (`${CLAUDE_PLUGIN_ROOT}/config/registry.json`)
and driven by one backing tool. Values persist into Claude Code `settings.json` `env` blocks —
`~/.claude/settings.json` (user), `.claude/settings.json` (project, committable), or
`.claude/settings.local.json` (project-local, personal) — and become real environment variables
at the **next session start**. Nothing applies live; say so after every write.

## Argument

`$ARGUMENTS` is one of:

- _(none)_ — browse: show the grouped settings menu and let the user navigate and change values.
- `<KEY>` — explain that one setting (description, type, default, effective value, provenance).
- `<KEY> <VALUE>` — set it (after confirmation).
- `doctor` — validate everything currently set; flag typo'd variable names and invalid values.
- `launch` — open the standalone interactive picker in a new terminal window (best-effort;
  needs a display or tmux).

## Flow

1. Get the current state as data:
   ```
   python3 "${CLAUDE_PLUGIN_ROOT}/hooks/configtool.py" list --json || python "${CLAUDE_PLUGIN_ROOT}/hooks/configtool.py" list --json
   ```

2. **Browse mode** — drive the conversation with `AskUserQuestion` selectable prompts, not walls
   of prose; that is the whole point of this command. Pattern:
   - First question: which **group** to look at (option per group, label = group name,
     description = the group's one-liner plus how many of its settings are non-default). More
     than four groups → two rounds or lean on "Other".
   - Within a group: render a compact table (name, effective value, source, default, one-line
     description, `preview` badge where applicable), then ask what to change. Toggle-shaped
     settings batch well as one **multiSelect** question ("select the ones you want ON").
     Enum settings: one question, an option per allowed value, current value marked. Numeric,
     string, and path settings: free text via the "Other" field, validated by the tool on `set`.
   - A setting whose `requires` gate is unmet (e.g. `CODEARBITER_PRUNE_TIER` while
     `CODEARBITER_PRUNE` is `off`) is still settable — surface the tool's note so the user knows
     it is dormant until the prerequisite is on.

3. **Every write** goes through the tool — never edit any settings.json by hand:
   ```
   python3 "${CLAUDE_PLUGIN_ROOT}/hooks/configtool.py" set <KEY> <VALUE> --scope <user|project|local> || python "${CLAUDE_PLUGIN_ROOT}/hooks/configtool.py" set <KEY> <VALUE> --scope <user|project|local>
   ```
   Before running it, confirm with the user: key, old → new value, and which scope file it lands
   in (default scope = the registry's hint; `project` is committable and visible to the team,
   `local` is personal). Editing the user's settings is their call, not yours. After the write,
   relay the tool output verbatim — it names the file, the prior value, and the
   restart-to-apply notice.

4. **Provenance honesty** — `source=session` means the live session environment (ground truth for
   what hooks see right now). When the tool reports a settings-layer value pending against a
   different session value, present both; do not assert which one "wins" at the next start —
   shell exports and settings.json are merged by the host, and the tool deliberately reports
   rather than adjudicates.

5. **doctor** — run it, present findings verbatim, offer the obvious fixes (`unset` the typo'd
   name, correct the invalid value) as selectable options.

6. **launch / standalone** — on request (or when the user clearly wants to explore by hand),
   run the `launch` subcommand: it opens the arrow-key picker in a new terminal window (tmux
   split when inside tmux) and degrades to printing the copy-paste command when there is no
   display. The same picker also runs by just executing
   `python3 <plugin-root>/hooks/configtool.py` in any real terminal.

## When NOT to use

- Arbiter enablement or maturity stage (`arbiter:`/`stage:` in `.codearbiter/CONTEXT.md`) →
  `/ca:init`. Those are project governance state, not env knobs.
- Install health, hook wiring → `/ca:doctor`.
- Statusline install/uninstall → `/ca:statusline` (its `CODEARBITER_*` display knobs DO live here).

## Hard gate

- MUST route every change through `configtool.py set`/`unset` — MUST NOT edit any settings.json
  directly, and MUST NOT export the variable in the live shell as a "workaround" (it would
  silently diverge from the persisted layers).
- MUST confirm key, value, and scope with the user before every write.
- MUST NOT switch on any opt-in feature (`CODEARBITER_PRUNE`, `CODEARBITER_BABYSIT`,
  `CODEARBITER_PRUNE_NUDGE`, farm/sandbox knobs) unbidden — present, explain, and let the user
  choose. Off-by-default is a product guarantee.
- MUST NOT persist `sensitive` settings (`FARM_API_KEY`) anywhere — the tool refuses; do not
  work around it. Point the user to their shell profile.
- MUST surface the restart-to-apply notice after every successful write.
