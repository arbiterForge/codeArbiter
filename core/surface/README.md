# core/surface/ — canonical markdown-surface templates (ADR-0011, M3)

Every host-facing markdown surface is generated from this tree by
`tools/build-surface.py`:

| Template | Claude (`plugins/ca/`) | Codex (`plugins/ca-codex/`) | Pi (`plugins/ca-pi/`) |
|---|---|---|---|
| `commands/<n>.md` | `commands/<n>.md` | `skills/ca-<n>/SKILL.md` | `skills/ca-<n>/SKILL.md` |
| `skills/**` | `skills/**` | `routines/**` | `routines/**` |
| `includes/**` | `includes/**` | `includes/**` | `includes/**` |
| `agents/**` | `agents/**` | not rendered | `agents/**` (explicit child input, outside discovery roots) |
| `COMMANDS.md`, `SPRINT.md`, `ORCHESTRATOR.md` | same name | same name | same name |
| generated catalog | none | `skills/INDEX.md` | `SKILLS.md` |

**Never edit a rendered file.** Rendered trees carry no provenance banner — the
Claude tree is contractually byte-identical to the hand tree it replaced — so
the guard is CI running `python tools/build-surface.py --check` (binary
compare, all hosts, fails on template-vs-output drift in either direction,
including orphans). Workflow: edit the template here, run
`python tools/build-surface.py`, commit templates and outputs together.

## Grammar

- `{{PLUGIN_ROOT}}`, `{{PROJECT_DIR}}`, and `{{CMD:name}}` resolve from the
  selected descriptor's `tokens` and `command_form` values.
- The `IF:<host> … ELSE … END` conditional form accepts any name declared in
  `core/hosts.json`; an unknown condition tag is a hard schema error. Regions
  are single-level, and a marker alone on its line leaves no blank residue.
- Each descriptor's ordered `surface.rules` applies the first matching source
  prefix and expands `{relative}`, `{stem}`, and `{name}` in its output path.
  Exclusions and synthesized skill frontmatter are rule data, not host branches.
- Each descriptor's `surface.catalog` owns the generated human-readable skill
  catalog path; consumers must not assume it lives beneath `skills/`.
- `core/hosts.json` is the only host registry. Both surface generation and
  Python-core vendoring consume it through `tools/host_descriptors.py`.

## House rules for shared prose

1. **Name actions, not harness tool names.** Shared bodies say "dispatch a
   reviewer", "read the file", "update the task board" — never a host tool
   name (`Task`, `TodoWrite`, `apply_patch`). Host tool mapping lives in the
   per-host notes include, not in shared prose. A harness choking on another
   harness's tool names is a documented failure mode of multi-host skill
   libraries.
2. **Host-impossible references go inside a conditional**, never deleted from
   an existing host side and never left to render as a dead pointer elsewhere.
3. **New commands are authored here** (Claude form, tokens), never in the
   rendered trees. `tools/build-surface.py` + `--check` keep every payload
   honest.

## Adding a harness (porting contract)

A new host is a table entry, not a rewrite:

1. **Capability matrix first.** For each surface (persona injection, exec
   gate, write/edit gate, read hook, commands, skills, agents, statusline,
   transcript prune) decide: SHIPPED, DEGRADED, or LEDGERED OUT — and record
   every exception in `docs/parity.md`. Essential (non-negotiable): session
   bootstrap injection, exec + write gating, the shared `.codearbiter/` store.
2. **One descriptor entry plus one thin adapter.** Add the host once in
   `core/hosts.json`; never add a parallel list to either generator. A host may
   ship `_host.py` or a bridge for project-root resolution, tool normalization,
   and input translation, but governance bodies remain generated.
3. **Injection shape.** The persona must inject at session start with zero
   per-session opt-in; if stdout injection is unavailable, a generated,
   staleness-checked instructions file is the approved fallback (ADR-0011).
4. **Acceptance probes before shipping.** A fresh session must (a) present the
   persona unprompted, (b) route a feature request through `brainstorming`
   before any code is written, and (c) BLOCK a `git commit --no-verify` —
   captured as a transcript in the PR that adds the harness.
