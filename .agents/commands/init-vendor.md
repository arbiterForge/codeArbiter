<!--
Copyright (c) 2026 suadtl
Author: suadtl
Created: 2026-05-12
File: init-vendor.md
-->

# /init-vendor [--vendor-path=<path>] [--dry-run] [--force]

## Purpose

Generate or regenerate the consuming project's `.claude/commands/*.md` shim layer with the vendor path baked in. Run this after installing codeArbiter as a submodule and after every codeArbiter upgrade.

This command is idempotent — safe to re-run. By default it skips shims that already exist.

## Usage

```
/init-vendor
/init-vendor --vendor-path=vendor/codearbiter/
/init-vendor --vendor-path=vendor/codearbiter/ --dry-run
/init-vendor --vendor-path=vendor/codearbiter/ --force
```

## Arguments

| Argument | Default | Description |
|---|---|---|
| `--vendor-path` | `vendor/codearbiter/` | Path from `${PROJECT_ROOT}` to the codeArbiter installation root. Use `.` for monolith dogfood mode. |
| `--dry-run` | off | Print the shims that would be written without writing them. |
| `--force` | off | Overwrite existing shims. Without this flag, existing shims are skipped with a notice. |

## Behavior

1. Resolve `${FRAMEWORK_ROOT}` from `--vendor-path` (default: `vendor/codearbiter/`).
2. **Copy `AGENTS.md` to project root.** Copy `${FRAMEWORK_ROOT}/AGENTS.md` → `${PROJECT_ROOT}/AGENTS.md`. Skip if `${PROJECT_ROOT}/AGENTS.md` already exists and `--force` is not set; overwrite if `--force`.
3. **Write `CLAUDE.md` at project root.** Write `${PROJECT_ROOT}/CLAUDE.md` containing exactly:
   ```
   @AGENTS.md
   ```
   Skip if `${PROJECT_ROOT}/CLAUDE.md` already exists and `--force` is not set; overwrite if `--force`.
4. List all command bodies at `${FRAMEWORK_ROOT}/.agents/commands/*.md` — exclude `_redirect.md` (internal only).
5. For each `<name>.md` found, generate `${PROJECT_ROOT}/.claude/commands/<name>.md` containing exactly:
   ```
   @<vendor-path>/.agents/commands/<name>.md
   ```
   Skip if the shim already exists and `--force` is not set; overwrite if `--force`.
6. Check `${PROJECT_ROOT}/.gitignore` for entries `/.plan-tasks/` and `/revendor/`. Append missing entries (skipped if `--dry-run`).
7. Report:
   - Whether `AGENTS.md` was copied, skipped, or overwritten
   - Whether `CLAUDE.md` was written, skipped, or overwritten
   - List of shims written (or would be written, in `--dry-run`)
   - List of shims skipped because they already exist (unless `--force`)
   - List of `.gitignore` entries added

## Monolith dogfood mode

With `--vendor-path=.`, the AGENTS.md copy and CLAUDE.md write are skipped (both files already exist at the project root and are the source of truth). Generated shims contain `@./.agents/commands/<name>.md`, equivalent to the existing `@.agents/commands/<name>.md` format.

## Hard Rules

- MUST NOT overwrite `${PROJECT_ROOT}/AGENTS.md` unless `--force` is passed.
- MUST NOT overwrite `${PROJECT_ROOT}/CLAUDE.md` unless `--force` is passed.
- MUST NOT overwrite existing shims unless `--force` is passed.
- MUST print the dry-run report before writing anything when `--dry-run` is passed.
- MUST NOT modify any framework files (only writes to `${PROJECT_ROOT}/AGENTS.md`, `${PROJECT_ROOT}/CLAUDE.md`, and `${PROJECT_ROOT}/.claude/commands/`).
- MUST NOT auto-invoke — this command is user-driven. `/onboard` does not call it automatically.

## Not in monolith mode

This command is primarily designed for consumers who have vendored codeArbiter. In monolith dogfood mode (this repo), the `.claude/commands/` shims are already correct. You may run `/init-vendor --vendor-path=. --dry-run` to verify they match the expected output.
