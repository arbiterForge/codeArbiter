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
4. Generates the `.claude/commands/*.md` shim layer with the vendor path baked in.

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

3. **Wire framework-owned subdirs as individual symlinks** into the vendor path. For each of the following, if a real file/directory already exists at the target, stop with a clear error unless `--force` (in which case back it up to `${PROJECT_ROOT}/.agents/<name>.backup-<timestamp>`); if an existing symlink already points to the correct vendor target, skip; if missing, create:

   | Target | Symlink target (relative) |
   |---|---|
   | `${PROJECT_ROOT}/.agents/skills` | `<vendor-path>/.agents/skills` |
   | `${PROJECT_ROOT}/.agents/agents` | `<vendor-path>/.agents/agents` |
   | `${PROJECT_ROOT}/.agents/commands` | `<vendor-path>/.agents/commands` |
   | `${PROJECT_ROOT}/.agents/hooks` | `<vendor-path>/.agents/hooks` |
   | `${PROJECT_ROOT}/.agents/settings.json` | `<vendor-path>/.agents/settings.json` |

   Use relative symlink targets (relative to `${PROJECT_ROOT}/.agents/`) so the wiring survives the host repo being moved or cloned to a different absolute path.

4. **Ensure consumer-owned `projectContext/` exists.** If `${PROJECT_ROOT}/.agents/projectContext` is a symlink (broken state from legacy whole-tree wiring), stop and require manual cleanup. If it does not exist, create the directory (real, not a symlink) and add a `.gitkeep` so it's tracked. Never copy framework dogfood content from `${FRAMEWORK_ROOT}/.agents/projectContext/` into it — `/create-context` or `/decompose` is responsible for populating it.

5. **Wire `${PROJECT_ROOT}/.claude/settings.json`** as a symlink to `../.agents/settings.json` (which itself resolves through `.agents/` into the vendor tree). Same conflict rules as step 3.

6. **Copy `AGENTS.md` to project root.** Copy `${FRAMEWORK_ROOT}/AGENTS.md` → `${PROJECT_ROOT}/AGENTS.md`. Skip if `${PROJECT_ROOT}/AGENTS.md` already exists and `--force` is not set; overwrite if `--force`.

7. **Write `CLAUDE.md` at project root.** Write `${PROJECT_ROOT}/CLAUDE.md` containing exactly:
   ```
   @AGENTS.md
   ```
   Skip if `${PROJECT_ROOT}/CLAUDE.md` already exists and `--force` is not set; overwrite if `--force`.

8. List all command bodies at `${FRAMEWORK_ROOT}/.agents/commands/*.md` — exclude `_redirect.md`, `_paths.md`, `_reference-map.md`, `_routing-table.md` (internal includes; underscore-prefixed).

9. For each `<name>.md` found, generate `${PROJECT_ROOT}/.claude/commands/<name>.md` containing exactly:
   ```
   @<vendor-path>/.agents/commands/<name>.md
   ```
   Skip if the shim already exists and `--force` is not set; overwrite if `--force`.

10. Check `${PROJECT_ROOT}/.gitignore` for entries `/.plan-tasks/` and `/revendor/`. Append missing entries (skipped if `--dry-run`).

11. Report:
    - Whether `.agents/` was created or already existed
    - Each subdir symlink: created, already correct, or backed up + replaced
    - Whether `.agents/projectContext/` was created (real dir) or already existed
    - Whether `AGENTS.md` was copied, skipped, or overwritten
    - Whether `CLAUDE.md` was written, skipped, or overwritten
    - List of `.claude/commands/` shims written (or would be written, in `--dry-run`)
    - List of `.claude/commands/` shims skipped because they already exist (unless `--force`)
    - List of `.gitignore` entries added

## Monolith dogfood mode

With `--vendor-path=.`, this is the framework's own repo being wired against itself. In that case:
- Steps 2–5 (real `.agents/` + per-subdir symlinks + `.agents/projectContext/`) are skipped: the framework repo already has a real `.agents/` directory with all subdirs as real directories. Re-running `/init-vendor` in monolith mode does NOT replace those real directories with self-referential symlinks.
- The `AGENTS.md` copy and `CLAUDE.md` write are skipped (both files already exist at the project root and are the source of truth).
- Generated shims contain `@./.agents/commands/<name>.md`, equivalent to the existing `@.agents/commands/<name>.md` format.

## Hard Rules

- MUST NOT overwrite `${PROJECT_ROOT}/AGENTS.md` unless `--force` is passed.
- MUST NOT overwrite `${PROJECT_ROOT}/CLAUDE.md` unless `--force` is passed.
- MUST NOT overwrite existing shims unless `--force` is passed.
- MUST NOT replace an existing `${PROJECT_ROOT}/.agents/` symlink (legacy whole-tree wiring) silently — stop and require the user to remove it manually. Such a symlink may have absorbed consumer projectContext writes that need rescue before re-wiring.
- MUST NOT symlink `${PROJECT_ROOT}/.agents/projectContext/` into the vendor tree under any condition. Consumer project state stays in the consumer repo.
- MUST NOT copy framework dogfood content from `${FRAMEWORK_ROOT}/.agents/projectContext/` into `${PROJECT_ROOT}/.agents/projectContext/`. The consumer initializes their own via `/create-context` or `/decompose`.
- MUST print the dry-run report before writing anything when `--dry-run` is passed.
- MUST NOT modify any framework files. Only writes to `${PROJECT_ROOT}/AGENTS.md`, `${PROJECT_ROOT}/CLAUDE.md`, `${PROJECT_ROOT}/.agents/` (subdir symlinks + projectContext dir), `${PROJECT_ROOT}/.claude/settings.json`, `${PROJECT_ROOT}/.claude/commands/`, and `${PROJECT_ROOT}/.gitignore`.
- MUST NOT auto-invoke — this command is user-driven. `/onboard` does not call it automatically.

## Migrating from legacy whole-tree symlink

Earlier versions of the install docs instructed users to `ln -s vendor/codearbiter/.agents .agents`. That wiring caused every write to `${PROJECT_ROOT}/.agents/projectContext/...` to physically land inside the vendor submodule. To migrate:

1. **Rescue consumer projectContext first.** Inspect `vendor/codearbiter/.agents/projectContext/` for files the consumer authored (CONTEXT.md with their content, their ADRs, tickets, overrides.log, etc.). Copy them somewhere safe outside the vendor tree.
2. Remove the legacy symlink: `rm .agents`
3. Re-run `/init-vendor --vendor-path=vendor/codearbiter/` — it creates the new per-subdir wiring.
4. Move the rescued projectContext content into the new real `${PROJECT_ROOT}/.agents/projectContext/`.
5. In the vendor submodule, the previously-leaked consumer projectContext files remain as uncommitted noise in `vendor/codearbiter/`. Reset the submodule (`git -C vendor/codearbiter checkout -- .` or re-checkout the pinned SHA) to clean it up.

## Not in monolith mode

This command is primarily designed for consumers who have vendored codeArbiter. In monolith dogfood mode (this repo), the framework directories are already real and the `.claude/commands/` shims are already correct. You may run `/init-vendor --vendor-path=. --dry-run` to verify the shim output matches what would be generated.
