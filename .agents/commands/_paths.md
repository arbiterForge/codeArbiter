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
- `${PROJECT_ROOT}/.agents/projectContext/audit-spec.md` resolves to `./.agents/projectContext/audit-spec.md` (the consumer's own projectContext — a REAL directory at the consumer's project root, never a symlink into the vendor tree)
- The prefixes diverge; skills read from the framework installation while project state is read from and written to the consumer's repo root.

**Layout in vendored mode:** `${PROJECT_ROOT}/.agents/` is a real directory. Its framework-owned subdirs (`skills/`, `agents/`, `commands/`, `hooks/`, `settings.json`) are individual symlinks into `vendor/codearbiter/.agents/...`. Its `projectContext/` is a real directory. This wiring is what keeps consumer state in the consumer repo and the framework submodule clean. `/init-vendor` creates the entire structure.

**Sentinel file:** `${FRAMEWORK_ROOT}/.agents/AGENTS-CODEARBITER-ROOT` — an empty marker file placed at the codeArbiter installation root. Shell hooks locate `FRAMEWORK_ROOT` at runtime by resolving their own script's physical path (`cd "$(dirname "${BASH_SOURCE[0]}")" && pwd -P`) and walking up until they find a directory containing `.agents/AGENTS-CODEARBITER-ROOT`. This works regardless of whether the script was invoked through a per-subdir symlink (vendored mode) or directly (monolith mode).

**Consumer install:** After adding codeArbiter as a submodule, run `/init-vendor [--vendor-path=vendor/codearbiter/]`. This:
1. Creates `${PROJECT_ROOT}/.agents/` as a real directory.
2. Symlinks `${PROJECT_ROOT}/.agents/{skills,agents,commands,hooks,settings.json}` individually into the vendor path.
3. Creates `${PROJECT_ROOT}/.agents/projectContext/` as a real consumer-owned directory.
4. Symlinks `${PROJECT_ROOT}/.claude/settings.json` to `../.agents/settings.json`.
5. Copies `${FRAMEWORK_ROOT}/AGENTS.md` to `${PROJECT_ROOT}/AGENTS.md` and writes `${PROJECT_ROOT}/CLAUDE.md` containing `@AGENTS.md`.
6. Generates the `${PROJECT_ROOT}/.claude/commands/*.md` shim layer with the vendor path baked in.

Re-run with `--force` after every codeArbiter upgrade to keep `AGENTS.md` and shims current. Default vendor path is `vendor/codearbiter/`.

## Self-edit mode (cross-reference)

When editing the framework itself rather than building on top of it, see also
`${FRAMEWORK_ROOT}/.agents/SELF-EDIT-MODE` (sentinel file). Its presence tells the
orchestrator that `${FRAMEWORK_ROOT}/.agents/**` is in-scope code (not a
read-only consumer dependency) and suppresses the H-08 startup-hook nag for the
framework's own incomplete CONTEXT.md. See AGENTS.md §1 Phase 0 for the detection
clause.
