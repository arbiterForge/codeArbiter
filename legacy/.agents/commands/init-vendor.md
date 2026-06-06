<!--
Copyright (c) 2026 suadtl
Author: suadtl
Created: 2026-05-12
File: init-vendor.md
-->

# /init-vendor [--vendor-path=<path>] [--dry-run] [--force]

## Purpose

Wire the consuming project for codeArbiter after the framework has been added as a submodule (or subtree). This command:

1. Establishes a real `${PROJECT_ROOT}/.agents/` directory and symlinks its framework-owned subdirs (`skills/`, `agents/`, `commands/`, `hooks/`, `settings.json`) into the vendor path.
2. Ensures `${PROJECT_ROOT}/.agents/projectContext/` exists as a **real, consumer-owned directory** at the project root — NEVER a symlink into the vendor tree. This is what keeps consumer project state in the consumer's repo and out of the framework submodule.
3. Copies `AGENTS.md` to the project root and writes the `CLAUDE.md` shim.
4. Generates the `.claude/commands/*.md` and `.claude/agents/*.md` shim layers with the vendor path baked in, so every `/command` and dispatched subagent resolves into the vendored framework.

Run this after installing codeArbiter as a submodule and after every codeArbiter upgrade.

This command is idempotent — safe to re-run. By default it skips files and links that already exist.

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

1. Resolve `${FRAMEWORK_ROOT}` from `--vendor-path` (default: `vendor/codearbiter/`). Verify `${FRAMEWORK_ROOT}/.agents/AGENTS-CODEARBITER-ROOT` exists — if not, stop and report that the vendor path does not point to a codeArbiter installation.

2. **Establish `${PROJECT_ROOT}/.agents/` as a real directory.** If `${PROJECT_ROOT}/.agents` is a symlink (legacy whole-tree wiring from earlier versions of this command), stop and require the user to remove it explicitly — never silently replace, because that path may contain consumer projectContext writes that landed inside the vendor tree. Otherwise, `mkdir -p ${PROJECT_ROOT}/.agents`.

3. **Wire framework-owned subdirs as individual symlinks** into the vendor path. For each target listed below, apply this resolution table:

   | State at target | Action |
   |---|---|
   | Missing | Create the symlink. |
   | Existing symlink, points to the expected `<vendor-path>/.agents/<name>` | Skip (idempotent). |
   | Existing symlink, points elsewhere (e.g., stale path from a previous vendor location) | Error unless `--force`. With `--force`, replace the symlink. |
   | Existing real file or real directory | Error unless `--force`. With `--force`, back it up to `${PROJECT_ROOT}/.agents/<name>.backup-<timestamp>`, then create the symlink. |

   Targets:

   | Target | Symlink target (relative) |
   |---|---|
   | `${PROJECT_ROOT}/.agents/skills` | `<vendor-path>/.agents/skills` |
   | `${PROJECT_ROOT}/.agents/agents` | `<vendor-path>/.agents/agents` |
   | `${PROJECT_ROOT}/.agents/commands` | `<vendor-path>/.agents/commands` |
   | `${PROJECT_ROOT}/.agents/hooks` | `<vendor-path>/.agents/hooks` |
   | `${PROJECT_ROOT}/.agents/settings.json` | `<vendor-path>/.agents/settings.json` |

   Use relative symlink targets (relative to `${PROJECT_ROOT}/.agents/`) so the wiring survives the host repo being moved or cloned to a different absolute path.

4. **Ensure consumer-owned `projectContext/` exists.** Apply this resolution:

   | State at `${PROJECT_ROOT}/.agents/projectContext` | Action |
   |---|---|
   | Missing | Create as a real directory and add a `.gitkeep` so the empty dir is tracked. |
   | Existing real directory (already a consumer-owned dir) | Skip — leave contents untouched. Do NOT add a `.gitkeep` if other files are already present. |
   | Symlink (any target) | Stop and require manual cleanup. This is a broken state from legacy whole-tree wiring; the symlink target may contain consumer projectContext writes that need rescue before re-wiring. |

   Never copy framework dogfood content from `${FRAMEWORK_ROOT}/.agents/projectContext/` into `${PROJECT_ROOT}/.agents/projectContext/` — `/create-context` or `/decompose` is responsible for populating it.

5. **Wire `${PROJECT_ROOT}/.claude/settings.json`** as a symlink to `../.agents/settings.json` (which itself resolves through `.agents/` into the vendor tree). Apply the same four-row resolution table as step 3 (missing / correct symlink / stale symlink / real file).

6. **Copy `AGENTS.md` to project root.** Copy `${FRAMEWORK_ROOT}/AGENTS.md` → `${PROJECT_ROOT}/AGENTS.md`. Skip if `${PROJECT_ROOT}/AGENTS.md` already exists and `--force` is not set; overwrite if `--force`.

7. **Write `CLAUDE.md` at project root.** Write `${PROJECT_ROOT}/CLAUDE.md` containing exactly:
   ```
   @AGENTS.md
   ```
   Skip if `${PROJECT_ROOT}/CLAUDE.md` already exists and `--force` is not set; overwrite if `--force`.

8. **Generate `.claude/commands/*.md` shims.** List all command bodies at `${FRAMEWORK_ROOT}/.agents/commands/*.md` — exclude underscore-prefixed files (`_redirect.md`, `_paths.md`, `_reference-map.md`, `_routing-table.md`; internal includes that are not user commands).

   For each `<name>.md` found, generate `${PROJECT_ROOT}/.claude/commands/<name>.md` containing exactly:
   ```
   @<vendor-path>/.agents/commands/<name>.md
   ```
   Skip if the shim already exists and `--force` is not set; overwrite if `--force`.

9. **Generate `.claude/agents/*.md` shims.** List all agent bodies at `${FRAMEWORK_ROOT}/.agents/agents/*.md` — exclude `INDEX.md` (surface scan, not a dispatchable agent) and any underscore-prefixed files.

   For each `<name>.md` found, generate `${PROJECT_ROOT}/.claude/agents/<name>.md` containing exactly:
   ```
   @<vendor-path>/.agents/agents/<name>.md
   ```
   Create `${PROJECT_ROOT}/.claude/agents/` if it does not exist. Skip individual shims that already exist when `--force` is not set; overwrite if `--force`.

10. Check `${PROJECT_ROOT}/.gitignore` for entries `/.plan-tasks/` and `/revendor/`. Append missing entries (skipped if `--dry-run`).

11. Report:
    - Whether `.agents/` was created or already existed
    - Each subdir symlink: created, already correct, replaced (stale target), or backed up + replaced (real file/dir)
    - Whether `.agents/projectContext/` was created (real dir), already existed as a real dir (skipped), or errored (symlink found)
    - Whether `.claude/settings.json` symlink was created, already correct, replaced, or backed up + replaced
    - Whether `AGENTS.md` was copied, skipped, or overwritten
    - Whether `CLAUDE.md` was written, skipped, or overwritten
    - List of `.claude/commands/` shims written, skipped, or overwritten (or would be, in `--dry-run`)
    - List of `.claude/agents/` shims written, skipped, or overwritten (or would be, in `--dry-run`)
    - List of `.gitignore` entries added

## Monolith dogfood mode

With `--vendor-path=.`, this is the framework's own repo being wired against itself. In that case:
- Steps 2–5 (real `.agents/` + per-subdir symlinks + `.agents/projectContext/` + `.claude/settings.json` symlink) are skipped: the framework repo already has a real `.agents/` directory with all subdirs as real directories. Re-running `/init-vendor` in monolith mode does NOT replace those real directories with self-referential symlinks.
- The `AGENTS.md` copy and `CLAUDE.md` write are skipped (both files already exist at the project root and are the source of truth).
- The shim-generation steps (8 and 9) DO run and produce `@./.agents/commands/<name>.md` / `@./.agents/agents/<name>.md`, equivalent to the existing `@.agents/...` format already present in this repo. Without `--force` they are skipped because the existing shims match.

## Hard Rules

- MUST NOT overwrite `${PROJECT_ROOT}/AGENTS.md` unless `--force` is passed.
- MUST NOT overwrite `${PROJECT_ROOT}/CLAUDE.md` unless `--force` is passed.
- MUST NOT overwrite existing `.claude/commands/` or `.claude/agents/` shims unless `--force` is passed.
- MUST NOT silently replace an existing symlink pointing to an unexpected target. A stale symlink (e.g., previous vendor path before the user moved the submodule) requires `--force` and is reported in the output.
- MUST NOT replace an existing `${PROJECT_ROOT}/.agents/` symlink (legacy whole-tree wiring) silently under any condition, even with `--force`. Such a symlink may have absorbed consumer projectContext writes that need rescue before re-wiring — the user must remove it manually after following the migration procedure below.
- MUST NOT symlink `${PROJECT_ROOT}/.agents/projectContext/` into the vendor tree under any condition. Consumer project state stays in the consumer repo.
- MUST NOT copy framework dogfood content from `${FRAMEWORK_ROOT}/.agents/projectContext/` into `${PROJECT_ROOT}/.agents/projectContext/`. The consumer initializes their own via `/create-context` or `/decompose`.
- MUST print the dry-run report before writing anything when `--dry-run` is passed.
- MUST NOT modify any framework files. Only writes to `${PROJECT_ROOT}/AGENTS.md`, `${PROJECT_ROOT}/CLAUDE.md`, `${PROJECT_ROOT}/.agents/` (subdir symlinks + projectContext dir + backups under `<name>.backup-<timestamp>`), `${PROJECT_ROOT}/.claude/settings.json`, `${PROJECT_ROOT}/.claude/commands/`, `${PROJECT_ROOT}/.claude/agents/`, and `${PROJECT_ROOT}/.gitignore`.
- MUST NOT auto-invoke — this command is user-driven. `/onboard` does not call it automatically.

## Migrating from legacy whole-tree symlink

Earlier versions of the install docs instructed users to `ln -s vendor/codearbiter/.agents .agents`. That wiring caused every write to `${PROJECT_ROOT}/.agents/projectContext/...` to physically land inside the vendor submodule. To migrate:

1. **Rescue consumer projectContext first.** Inspect `vendor/codearbiter/.agents/projectContext/` for files the consumer authored (CONTEXT.md with their content, their ADRs, tickets, overrides.log, etc.). Copy them somewhere safe outside the vendor tree.
2. Remove the legacy symlink: `rm .agents`
3. Re-run `/init-vendor --vendor-path=vendor/codearbiter/` — it creates the new per-subdir wiring.
4. Move the rescued projectContext content into the new real `${PROJECT_ROOT}/.agents/projectContext/`.
5. In the vendor submodule, the previously-leaked consumer projectContext files remain as uncommitted noise in `vendor/codearbiter/`. Reset the submodule (`git -C vendor/codearbiter checkout -- .` or re-checkout the pinned SHA) to clean it up.

## Not in monolith mode

This command is primarily designed for consumers who have vendored codeArbiter. In monolith dogfood mode (this repo), the framework directories are already real and the `.claude/commands/` and `.claude/agents/` shims are already correct. You may run `/init-vendor --vendor-path=. --dry-run` to verify the shim output matches what would be generated.
