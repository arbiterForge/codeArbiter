<!--
Copyright (c) 2026 suadtl
Author: suadtl
Created: 2026-05-14
File: _paths.md

This file is an INTERNAL on-demand include extracted from AGENTS.md §0.1.1.
Underscore prefix denotes "not a user command — load only when path resolution
between ${FRAMEWORK_ROOT} and ${PROJECT_ROOT} is ambiguous." See also:
_redirect.md, _reference-map.md, _routing-table.md.
-->

# §0.1.1: Path Resolution

> **Loaded when:** vendor setup (`/init-vendor`), brownfield init, hook authoring,
> or any time `${FRAMEWORK_ROOT}` vs `${PROJECT_ROOT}` resolution is ambiguous in
> a framework file. AGENTS.md keeps a stub pointing here; the body lives here to
> avoid loading two worked examples and a sentinel-file paragraph on every session.

Two explicit roots govern every file path in framework files:

| Root | Definition | Monolith dogfood value | Vendored value (example) |
|---|---|---|---|
| **`${FRAMEWORK_ROOT}`** | The codeArbiter installation root — the directory that contains `.agents/skills/`, `.agents/agents/`, `.agents/commands/`, `.agents/hooks/`, and `AGENTS.md`. | `.` (the repo root) | `vendor/codearbiter/` |
| **`${PROJECT_ROOT}`** | The consuming project's repository root — the git toplevel. | `.` (the repo root) | `.` (the consumer's repo root) |

**Rule of thumb:**
- *Anything that is part of the framework source* (skill bodies, agent bodies, command bodies, hooks, AGENTS.md itself, templates) uses `${FRAMEWORK_ROOT}`.
- *Anything generated, populated, or referenced as project state* (projectContext/, ADRs, tickets, overrides.log, hotfixes.log, open-questions.md) uses `${PROJECT_ROOT}`.

**Worked example — monolith dogfood mode** (this repo dogfoods its own framework):
- `${FRAMEWORK_ROOT}/.agents/skills/tdd/SKILL.md` resolves to `./.agents/skills/tdd/SKILL.md`
- `${PROJECT_ROOT}/.agents/projectContext/audit-spec.md` resolves to `./.agents/projectContext/audit-spec.md`
- Both prefixes point to the same physical root; behavior is identical to the pre-vendoring layout.

**Worked example — vendored mode** (consumer mounts codeArbiter at `vendor/codearbiter/`):
- `${FRAMEWORK_ROOT}/.agents/skills/tdd/SKILL.md` resolves to `vendor/codearbiter/.agents/skills/tdd/SKILL.md`
- `${PROJECT_ROOT}/.agents/projectContext/audit-spec.md` resolves to `./.agents/projectContext/audit-spec.md` (the consumer's own projectContext)
- The prefixes diverge; skills read from the framework installation while project data is read from the consumer's repo root.

**Sentinel file:** `${FRAMEWORK_ROOT}/.agents/AGENTS-CODEARBITER-ROOT` — an empty marker file placed at the codeArbiter installation root. Shell hooks locate `FRAMEWORK_ROOT` at runtime by walking up from their script location until they find a directory containing `AGENTS-CODEARBITER-ROOT`.

**Consumer install:** After adding codeArbiter as a submodule, run `/init-vendor [--vendor-path=vendor/codearbiter/]`. This copies `AGENTS.md` to `${PROJECT_ROOT}/AGENTS.md`, writes `${PROJECT_ROOT}/CLAUDE.md` containing `@AGENTS.md`, and generates the `.claude/commands/*.md` shim layer with the vendor path baked in. Re-run after every codeArbiter upgrade to keep `AGENTS.md` current. Default vendor path is `vendor/codearbiter/`.

## Self-edit mode (cross-reference)

When editing the framework itself rather than building on top of it, see also
`${FRAMEWORK_ROOT}/.agents/SELF-EDIT-MODE` (sentinel file). Its presence tells the
orchestrator that `${FRAMEWORK_ROOT}/.agents/**` is in-scope code (not a
read-only consumer dependency) and suppresses the H-08 startup-hook nag for the
framework's own incomplete CONTEXT.md. See AGENTS.md §1 Phase 0 for the detection
clause.
