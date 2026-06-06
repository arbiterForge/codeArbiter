# codeArbiter — commands

All user intent flows through these commands. Direct instructions outside a command channel are
declined (see the §6 redirect). The plugin is named `ca`; every command is namespaced — invoke
`/ca:<name>`.

This table is the surface scan. A command body (`${CLAUDE_PLUGIN_ROOT}/commands/<name>.md`) loads
ONLY when that command is invoked — never bulk-read the directory.

## Implementation

| Command | Argument | Purpose |
|---|---|---|
| `/ca:feature` | `"description"` | Spec-driven feature: brainstorm → plan → test-first build → commit → finish. The only path to implementation. |
| `/ca:fix` | `"bug description"` | Fix a defect via `tdd`, regression-test-first. |
| `/ca:refactor` | `"surface and motivation"` | Behavior-preserving restructure behind a parity-coverage gate. |
| `/ca:debug` | `"symptom"` | Investigate-then-decide root-cause analysis; exits to `/ca:fix`, `/ca:adr`, or a no-action close. |

## Commit & ship

| Command | Argument | Purpose |
|---|---|---|
| `/ca:commit` | _(none)_ | The only path to a commit; routes to `commit-gate` (nine gates). |
| `/ca:pr` | `["title"]` | Finish a branch: open-PR / merge-via-PR / discard. No direct-to-default. |
| `/ca:review` | `[path or scope]` | Dispatch the reviewer fleet over the diff; BLOCK on CRITICAL/HIGH. |
| `/ca:checkpoint` | `[focus]` | Lean periodic reviewer sweep; surfaces a triaged report. |
| `/ca:release` | `[--dry-run]` | Lean SemVer release: bump-from-commits + changelog + annotated tag. |
| `/ca:add-dep` | `"package"` | Vet a dependency (license, provenance, supply chain) before install. |

## Decisions

| Command | Argument | Purpose |
|---|---|---|
| `/ca:adr` | `"title"` | Author a numbered, user-attributed ADR. |
| `/ca:adr-status` | `[--adr N]` | List/inspect ADR status and supersede chains. |
| `/ca:decision-variance` | `["scope"]` | Reconcile artifacts vs. scaffold; arbitrate via SMARTS, user-attributed. |
| `/ca:surface-conflict` | `"description"` | Stop all work and surface a rule conflict. |
| `/ca:threat-model` | `"scope"` | Optional lightweight STRIDE pass for a sensitive feature. |

## Project & meta

| Command | Argument | Purpose |
|---|---|---|
| `/ca:decompose` | _(none)_ | Greenfield: layered interview to populate `.codearbiter/`. |
| `/ca:create-context` | _(none)_ | Brownfield: back-fill `.codearbiter/` from existing source. |
| `/ca:init` | `[--stage N]` | Scaffold the root-level `.codearbiter/` state store. |
| `/ca:status` | _(none)_ | Show maturity, open tasks, unresolved `CONFIRM-NN`, overrides since checkpoint. |
| `/ca:statusline` | `[--check]` | Install/wire the codeArbiter statusline. |
| `/ca:new-skill` | `"gap"` | Author a new skill after the gap is proven uncovered. |
| `/ca:btw` | `"question"` | Lightweight Q&A; no state change. |
| `/ca:override` | `"reason"` | Sanctioned, logged single-identity gate bypass. |
| `/ca:commands` | _(none)_ | Show this catalog. |
