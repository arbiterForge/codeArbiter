# core/surface/ — canonical markdown-surface templates (ADR-0011, M3)

Every host-facing markdown surface is generated from this tree by
`tools/build-surface.py`:

| Template | Claude render (`plugins/ca/`) | Codex render (`plugins/ca-codex/`) |
|---|---|---|
| `commands/<n>.md` | `commands/<n>.md` | `skills/ca-<n>/SKILL.md` (frontmatter gains `name: ca-<n>`) |
| `skills/**` | `skills/**` | `routines/**` (kept out of the skill-discovery root: routine bodies must never register as unprefixed user-invocable skills, and six names collide with commands) |
| `includes/**` | `includes/**` | `includes/**` |
| `COMMANDS.md`, `SPRINT.md`, `ORCHESTRATOR.md` | same name | same name |
| — | — | `skills/INDEX.md` (generated catalog) |

**Never edit a rendered file.** Rendered trees carry no provenance banner — the
Claude tree is contractually byte-identical to the hand tree it replaced — so
the guard is CI running `python tools/build-surface.py --check` (binary
compare, both hosts, fails on template-vs-output drift in either direction,
including orphans). Workflow: edit the template here, run
`python tools/build-surface.py`, commit templates and outputs together.

## Grammar

- `{{PLUGIN_ROOT}}` → `${CLAUDE_PLUGIN_ROOT}` on both hosts (Codex ships the
  compat alias — source-verified, M0 spike item 6).
- `{{PROJECT_DIR}}` → `${CLAUDE_PROJECT_DIR}` (claude) | `<project-root>`
  (codex — hooks resolve it from the payload `cwd` → git toplevel).
- `{{CMD:name}}` → `/ca:name` (claude) | `$ca-name` (codex). Hard error if
  `name` is not a command template, or is excluded on the render host — that
  error is the mechanism that finds every spot needing a conditional.
- `{{IF:claude}} … {{ELSE}} … {{END}}` / `{{IF:codex}} …` — single level, no
  nesting. A marker alone on its line is removed together with the line.
- Codex renders rewrite `{{PLUGIN_ROOT}}/skills/…` → `…/routines/…` (except
  `skills/ca-*`, which is codex-native) and `{{PLUGIN_ROOT}}/commands/<n>.md`
  → `…/skills/ca-<n>/SKILL.md`.
- `CODEX_EXCLUDED_CMDS` (statusline, prune) render no Codex skill —
  ledgered in `docs/parity.md`. `CODEX_ONLY` templates (e.g.
  `includes/codex-host-notes.md`) render into the Codex tree only.

## House rules for shared prose

1. **Name actions, not harness tool names.** Shared bodies say "dispatch a
   reviewer", "read the file", "update the task board" — never a host tool
   name (`Task`, `TodoWrite`, `apply_patch`). Host tool mapping lives in the
   per-host notes include, not in shared prose. A harness choking on another
   harness's tool names is a documented failure mode of multi-host skill
   libraries.
2. **Host-impossible references go inside a conditional**, never deleted from
   the Claude side and never left to render as a dead pointer on Codex.
3. **New commands are authored here** (Claude form, tokens), never in the
   rendered trees. `tools/build-surface.py` + `--check` keep both payloads
   honest.

## Adding a harness (porting contract)

A new host is a table entry, not a rewrite:

1. **Capability matrix first.** For each surface (persona injection, exec
   gate, write/edit gate, read hook, commands, skills, agents, statusline,
   transcript prune) decide: SHIPPED, DEGRADED, or LEDGERED OUT — and record
   every exception in `docs/parity.md`. Essential (non-negotiable): session
   bootstrap injection, exec + write gating, the shared `.codearbiter/` store.
2. **One `_host.py` per plugin** (the only per-host Python file: project-root
   resolution, tool-name normalization, input-shape translation, capability
   flags) plus a `HOSTS`/token/`PLUGIN_DIR` entry in `tools/build-surface.py`
   and a vendor target in `tools/sync-core.py`.
3. **Injection shape.** The persona must inject at session start with zero
   per-session opt-in; if stdout injection is unavailable, a generated,
   staleness-checked instructions file is the approved fallback (ADR-0011).
4. **Acceptance probes before shipping.** A fresh session must (a) present the
   persona unprompted, (b) route a feature request through `brainstorming`
   before any code is written, and (c) BLOCK a `git commit --no-verify` —
   captured as a transcript in the PR that adds the harness.
