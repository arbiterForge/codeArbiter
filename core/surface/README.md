# core/surface/ — canonical markdown-surface templates (ADR-0011, M3)

Every host-facing markdown surface is generated from this tree by
`tools/build-surface.py`:

| Template | Claude (`plugins/ca/`) | Codex (`plugins/ca-codex/`) | Pi (`plugins/ca-pi/`) |
|---|---|---|---|
| `commands/<n>.md` | `commands/<n>.md` | `skills/ca-<n>/SKILL.md` | `skills/ca-<n>/SKILL.md` |
| `skills/**` | `skills/**` | `routines/**` | `routines/**` |
| `includes/**` | `includes/**` | `includes/**` | `includes/**` |
| `agents/**` | `agents/**` | `agents/**` (Markdown resource charters; never native registration) | `agents/**` (explicit child input, outside discovery roots) |
| `COMMANDS.md`, `SPRINT.md`, `arbiter.md` | same name | same name | same name |
| generated catalog | none | `skills/INDEX.md` | `SKILLS.md` |

**Never edit a rendered file.** Rendered trees carry no provenance banner — the
Claude tree is contractually byte-identical to the hand tree it replaced — so
the guard is CI running `python tools/build-surface.py --check` (binary
compare, all hosts, fails on template-vs-output drift in either direction,
including orphans). Workflow: edit the template here, run
`python tools/build-surface.py`, commit templates and outputs together.

## Grammar

- `{{PROJECT_DIR}}` and `{{CMD:name}}` resolve from the selected descriptor's
  `tokens` and `command_form` values. `{{PLUGIN_ROOT}}` remains Claude-native
  where Claude parses it; Codex renders ordinary Markdown resources as
  normalized POSIX links relative to the generated file and reserves
  `${PLUGIN_ROOT}` for hook configuration; Pi retains file-relative semantics.
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

## Single-source command-backed owners

A command template that only routes to a skill may contain just the whole-file
SKILL_ENTRY declaration (double braces, colon, then the skill directory name).
Examples include `commands/commit.md`, `commands/refactor.md`, and `commands/pr.md`.
The generator reads the named `skills/<name>/SKILL.md` at build time and emits the
complete procedure under the existing host-native command or entry-skill name.
There is no new runtime include service, route registry, or model-facing capability.

The owner contains the sole description, argument hint and behavior and stays
registry-visible on Claude as required by ADR-0028. Only the generated Claude command
gets `disable-model-invocation: true`: it remains explicitly usable without advertising
another description. No `user-invocable` flag or user-level setting is added. On
Codex/Pi the generated `ca-<command>` entry remains discoverable because its owning
routine lives outside their discovery directory. Natural-language discovery and
actual mutation permission remain different: every gate stays in the full body.
Existing direct resource paths and explicit names remain intact. Keep descriptions
focused on intent and the key side-effect boundary, not phase inventories.
For a multi-mode owner such as branch finishing, dispatch watch/cleanup before
creation prerequisites. Its PR-opening procedure belongs to the owner, not a
wrapper it must load again. Supporting cards remain without discovery frontmatter.

The declaration must occupy the entire command template. One owner has one composed public
entry. An existing mode-only adapter may select that owner without duplicating its
procedure, as `adr-status` selects read-only `decision-lifecycle` before authoring. Composition is non-recursive, rejects missing/symlinked owners and unsupported
frontmatter, and requires rooted resource links so rendering uses the actual output
location. It never adds `allowed-tools`, changes a mode, or drops a gate. Separate
wrappers with distinct modes, arguments or continuations must first reconcile those
obligations with the owner; they are not automatically eligible for consolidation.

Edit the owner, then run the normal generator and resource-closure tests. Generated
copies on disk are derivatives, not independently authored procedures. Retaining a
compatibility file does not imply its description is model-visible. Compare actual
host discovery, invoked payload and retained context separately; file/byte counts
alone are not measured token savings. A generated full public body avoids a second
load merely to reach the same owner, but supporting references still load on demand.

## Authoring governed resources

Resource authoring is ordinary scoped repository work, not a separate installed
workflow. Prefer improving the applicable owner to adding another public entry.
A directly referenced information card can live beneath that owner's `references/`
directory without skill frontmatter or a discovery/index entry. The existing
change, verification, review and commit requirements still apply.

For a genuine reusable skill, use its existing neighbors as format examples:
`name` and an intent-focused `description`, prerequisites, executable instructions,
observable completion evidence and material boundaries. A command-backed owner
also supplies `argument-hint`. Keep explanatory questions non-mutating; do not
require users to name or repeat a command to select the relevant procedure.

Use JSON-quoted frontmatter scalars when they start with `[` or `{`, contain
colon-space or ` | `, and preserve explicit string quoting. Chain-internal skills
are path-routed and registry-hidden under ADR-0028. Do not hide a discoverable
owning skill merely because an explicit alias also exists. Use the rooted
resource syntax above and the selected host's descriptor, not guessed host paths.

Update the applicable index and caller when adding a resource. Generate all host
copies, then run `check_routing_index_parity.py`, the surface/host-descriptor tests
and the three plugin-resource checks. New host metadata needs explicit compiler
support and tests. These are repository conventions, not a replacement authoring
command, skill, fixed-number interview, or additional approval ceremony.

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
