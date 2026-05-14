<!--
Copyright (c) 2026 suadtl
Author: suadtl
Created: 2026-05-12
File: README.md
-->

# codeArbiter

**An orchestration framework for Claude Code that routes work through skills and agents, enforces TDD and commit gates, surfaces rule conflicts, and keeps a permanent audit trail.**

codeArbiter is opinionated infrastructure that sits on top of Claude Code. Instead of letting an AI assistant freelance across your repo, every user intent flows through a slash command that fans out to specialized skills (TDD, commit-gate, decision-lifecycle, etc.) and reviewer agents (security, migration, dependency, etc.). The framework refuses to commit without all gates green, refuses to resolve open questions by guessing, and refuses to silently reconcile contradictions between docs and code.

The full specification is in [`AGENTS.md`](./AGENTS.md). The command catalog is in [`COMMANDS.md`](./COMMANDS.md). Notable changes are tracked in [`CHANGELOG.md`](./CHANGELOG.md).

---

## How it works

```
.agents/                              (real directory, lives at ${PROJECT_ROOT})
├── projectContext/   # Consumer-owned state — REAL directory, never symlinked into the vendor tree
│   ├── CONTEXT.md          # Identity, scope, NOT-this-project (sentinel: <!--INITIALIZED-->)
│   ├── stage               # Single integer: current stage
│   ├── open-tasks.md       # In-flight, backlog, blocked
│   ├── open-questions.md   # Unresolved CONFIRM-NN items (block stage promotion)
│   ├── overrides.log       # Append-only audit log of every gate bypass
│   ├── decisions/          # ADRs
│   ├── tickets/            # Optional scope-overflow inbox
│   └── …                   # tech-stack, security-controls, audit-spec, etc.
├── agents/        → vendor/codearbiter/.agents/agents/      (symlink — framework code)
├── commands/      → vendor/codearbiter/.agents/commands/    (symlink — framework code)
├── hooks/         → vendor/codearbiter/.agents/hooks/       (symlink — framework code)
├── skills/        → vendor/codearbiter/.agents/skills/      (symlink — framework code)
└── settings.json  → vendor/codearbiter/.agents/settings.json (symlink — framework config)

.claude/              # Shim layer — what Claude Code natively reads
├── settings.json   → ../.agents/settings.json   (symlink — resolves into the vendor tree)
├── agents/         → ../.agents/agents/         (symlink in monolith; per-file @path shims after /init-vendor)
└── commands/       → ../.agents/commands/       (symlink in monolith; per-file @path shims after /init-vendor)
```

The `.claude/` directory is what Claude Code natively reads. The `.agents/` directory at the project root is **real** — only its framework-owned subdirs are symlinked into the vendor tree. `projectContext/` is always a real, consumer-owned directory at `${PROJECT_ROOT}/.agents/projectContext/` so consumer project state commits to the consumer repo, not the framework submodule. **In a consuming host project**, `/init-vendor` creates this entire structure: the real `.agents/` directory, the per-subdir symlinks, the empty `projectContext/`, and the per-file `.claude/commands/*.md` shims (`@vendor/codearbiter/.agents/commands/<name>.md` import lines) — so every `/command` resolves into the vendored framework without modifying `settings.json`.

---

## Quickstart

```sh
git clone <this-repo> my-project
cd my-project
claude   # opens Claude Code
```

Inside Claude Code:

- **New project, no code yet?** Run `/decompose` to scaffold `projectContext/`.
- **Existing codebase?** Run `/create-context` to back-fill `projectContext/` from what's already there.
- **Just want a tour?** Run `/onboard`.

Once `projectContext/CONTEXT.md` contains the `<!--INITIALIZED-->` marker, you're in normal operation. From there, all work flows through slash commands — see [`COMMANDS.md`](./COMMANDS.md).

---

## Installing codeArbiter into a host project

codeArbiter is designed to live inside another repo. The `/init-vendor` command handles the wiring after you bring it in.

### How the path model works

Two roots govern every file path in the framework:

| Root | What it is |
|---|---|
| `${FRAMEWORK_ROOT}` | The codeArbiter installation (e.g. `vendor/codearbiter/`) — contains skills, agents, commands, and hooks |
| `${PROJECT_ROOT}` | Your repo root — where `AGENTS.md`, `CLAUDE.md`, and `.agents/projectContext/` live |

Your project state (`projectContext/`, ADRs, tickets, overrides log) always lives at `${PROJECT_ROOT}/.agents/projectContext/`, separate from the framework files.

### What `/init-vendor` does

Running `/init-vendor --vendor-path=vendor/codearbiter/` inside Claude Code:

1. **Creates a real `${PROJECT_ROOT}/.agents/` directory** at your repo root (if it doesn't already exist as a real dir).
2. **Symlinks the framework-owned subdirs** inside it — `skills/`, `agents/`, `commands/`, `hooks/`, `settings.json` — into the vendor path. Upgrades to codeArbiter are then just `git submodule update`; no re-copying.
3. **Creates `${PROJECT_ROOT}/.agents/projectContext/` as a real directory** owned by the consumer. Your CONTEXT.md, ADRs, tickets, overrides log, etc. all live here, in your repo — never in the framework submodule.
4. **Symlinks `${PROJECT_ROOT}/.claude/settings.json`** to `../.agents/settings.json` so Claude Code picks up the framework's hooks and MCP config.
5. **Copies `AGENTS.md`** from the vendor path to your repo root — Claude Code must be able to find `AGENTS.md` at `$CLAUDE_PROJECT_DIR` to load the orchestrator.
6. **Writes `CLAUDE.md`** at your repo root containing `@AGENTS.md` — the standard Claude Code project-instructions shim.
7. **Generates `.claude/commands/*.md` shims** pointing into the vendor path so every `/command` resolves correctly.

Re-run with `--force` after every codeArbiter upgrade to keep `AGENTS.md` and all shims current. The framework subdir symlinks are stable — they don't need refreshing on upgrade since they always resolve into the current submodule SHA.

---

### Option A — `git submodule` (recommended)

```sh
# 1. Vendor codeArbiter
git submodule add <repo-url> vendor/codearbiter
git commit -m "vendor: add codeArbiter submodule"

# 2. Open Claude Code and run /init-vendor. This creates the real .agents/
#    directory at your repo root, symlinks the framework subdirs into the
#    vendor path, creates the real consumer-owned .agents/projectContext/,
#    copies AGENTS.md, writes CLAUDE.md, and generates .claude/commands/ shims.
claude
# → /init-vendor --vendor-path=vendor/codearbiter/

# 3. Commit the wiring (.agents/ subdir symlinks + projectContext placeholder + AGENTS.md + CLAUDE.md + .claude/)
git add .agents .claude AGENTS.md CLAUDE.md
git commit -m "vendor: wire codeArbiter"

# 4. Initialize project context
# → /create-context   (existing codebase)
# → /decompose        (new project, no code yet)
```

#### Submodule semantics — required reading for the team

When your host project lists codeArbiter as a submodule, anyone cloning or pulling the host project has to recurse into submodules explicitly, or the `vendor/codearbiter/` directory shows up empty (and Claude Code can't find any of the framework). Standard git submodule footguns; not codeArbiter-specific. Patterns that work:

```sh
# Fresh clone of a host project that uses codeArbiter
git clone --recurse-submodules <host-repo-url>

# Forgot --recurse-submodules at clone time? Fix retroactively:
git submodule update --init --recursive

# Day-to-day pulls — fetch host commits AND update submodule SHAs in one go
git pull --recurse-submodules

# Make recurse the default for this clone (run once per developer):
git config submodule.recurse true
#   → after this, plain `git pull` / `git checkout` / `git switch` recurse automatically
```

If a teammate bumps the codeArbiter submodule SHA on `main`, your `git pull` (without `--recurse-submodules` or the config above) will pull the host commit but leave your local `vendor/codearbiter/` at the old SHA — leading to confusing "but the docs say feature X exists" debugging. The `submodule.recurse = true` config makes this Just Work.

#### Upgrading codeArbiter in your host project

```sh
git -C vendor/codearbiter pull origin main      # fetch latest codeArbiter
git add vendor/codearbiter                      # stage the new submodule SHA in host
git commit -m "vendor: upgrade codeArbiter"
# Then in Claude Code: /init-vendor --vendor-path=vendor/codearbiter/ --force
```

After you push that host commit, teammates pick it up via `git pull --recurse-submodules` (or plain `git pull` if they set `submodule.recurse = true`).

### Option B — `git subtree` (vendored into your history, no submodule overhead)

```sh
git subtree add --prefix=vendor/codearbiter <repo-url> main --squash
# Then in Claude Code: /init-vendor --vendor-path=vendor/codearbiter/
# (creates .agents/ with per-subdir symlinks, real .agents/projectContext/,
#  AGENTS.md, CLAUDE.md, and .claude/ shims)
git add .agents .claude AGENTS.md CLAUDE.md && git commit -m "vendor: wire codeArbiter"
```

To upgrade:
```sh
git subtree pull --prefix=vendor/codearbiter <repo-url> main --squash
# Then in Claude Code: /init-vendor --vendor-path=vendor/codearbiter/ --force
```

### Option C — Plain copy (no upstream linkage)

```sh
cp -r path/to/codearbiter/.agents ./.agents
cp -r path/to/codearbiter/.claude ./.claude
cp path/to/codearbiter/AGENTS.md ./AGENTS.md
echo "@AGENTS.md" > CLAUDE.md
```

Everything is already at the root so `/init-vendor` is not needed. No path to pull future updates without manually re-copying.

---

**Why per-subdir symlinks instead of one big `.agents/` symlink?** Earlier versions of these install instructions had you `ln -s vendor/codearbiter/.agents .agents`. That looked simpler, but every write to `${PROJECT_ROOT}/.agents/projectContext/...` then physically landed inside `vendor/codearbiter/.agents/projectContext/` — i.e. inside the framework submodule. Consumer state (CONTEXT.md, ADRs, tickets, overrides.log) would not commit to the consumer's repo and would silently pollute the submodule. The current wiring keeps `.agents/` itself a real directory at the project root and only symlinks the framework-owned subdirs (`skills/`, `agents/`, `commands/`, `hooks/`, `settings.json`), so `projectContext/` is always a real consumer-owned directory. At runtime hooks resolve their own physical path via `pwd -P` and verify they sit under a directory containing the `${FRAMEWORK_ROOT}/.agents/AGENTS-CODEARBITER-ROOT` sentinel to discover `FRAMEWORK_ROOT`; `PROJECT_ROOT` comes from `git rev-parse --show-toplevel`.

**Migrating an existing install** that used the legacy whole-tree symlink: see the "Migrating from legacy whole-tree symlink" section in [`.agents/commands/init-vendor.md`](./.agents/commands/init-vendor.md). The short version: rescue any consumer projectContext that landed in the vendor tree, remove the `.agents` symlink, re-run `/init-vendor`, move the rescued content into the new real `${PROJECT_ROOT}/.agents/projectContext/`.

**Note on README/LICENSE:** these root files don't travel with the framework. Your host project has its own. Authoritative docs for framework components (statusline, etc.) live under `.agents/` so they follow the code. See [`.agents/hooks/STATUSLINE.md`](./.agents/hooks/STATUSLINE.md).

---

## Statusline

codeArbiter ships a custom Claude Code statusline that surfaces project state continuously, with no commands required.

```
Clean / initialized / no blockers:
● stage:3 │ tasks:0 q:0 │ ⎇ main │ over:0
└─┬─┘ └──┬──┘ └────┬────┘ └─┬─┘ └──┬──┘
  │     │          │        │     └─ overrides.log entry count (dim 0, red >0)
  │     │          │        └────── git branch; green=clean, yellow+* when dirty
  │     │          └─────────────── open-tasks count + CONFIRM-NN count
  │     └────────────────────────── .agents/projectContext/stage value
  └──────────────────────────────── ● green = initialized, ○ yellow = not yet

Pre-init, dirty tree, blockers present:
○ stage:1 │ tasks:4 q:2 │ ⎇ feature/foo* │ over:1
```

The bar is **on by default** when you clone this repo. To turn it off:

- **Per shell (transient):** `export CODEARBITER_STATUSLINE=off`
- **Per user (persistent):** add `{ "statusLine": null }` to `.claude/settings.local.json` (gitignored by Claude Code) — user-scope settings override the committed project default.

Full docs, including troubleshooting and the segment-by-segment color logic, live in [`.agents/hooks/STATUSLINE.md`](./.agents/hooks/STATUSLINE.md) (which travels with the framework on import).

---

## Slash commands (quick reference)

Grouped by intent. Full catalog with body links: [`COMMANDS.md`](./COMMANDS.md).

**Implementation:**

| Command | Purpose |
|---|---|
| `/feature "description"` | Start a new feature; runs the full TDD skill (6 phases). |
| `/fix "bug"` | Same workflow, bug-framed. |
| `/refactor "surface and motivation"` | Behavior-preserving change with parity-coverage proof gate. |
| `/debug "symptom"` | Investigate-then-decide RCA; outcomes route to `/fix`, `/ticket`, or `/adr`. |

**Pre-implementation review:**

| Command | Purpose |
|---|---|
| `/threat-model "scope"` | Pre-implementation threat model for a proposed change. |

**Commit / PR / review:**

| Command | Purpose |
|---|---|
| `/commit` | Commit staged changes after the full commit-gate runs green. |
| `/pr [title]` | Open a PR once all reviewer gates clear. |
| `/review [scope]` | Security + code review of a path or scope. |

**Architectural decisions:**

| Command | Purpose |
|---|---|
| `/adr "title"` | Record a new architectural decision (with user attribution). |
| `/adr-status [--adr N]` | Check ADR health — aged, unchallenged, unresolved CONFIRM-NN. |
| `/decision-variance ["scope"]` | Reconcile artifacts vs. scaffold; arbitrate ADR conflicts via SMARTS (user-attributed). |

**Checkpoints & promotions:**

| Command | Purpose |
|---|---|
| `/checkpoint [focus]` | Full 7-reviewer parallel checkpoint. |
| `/stage [target]` | Show current stage or promote to a target stage. |
| `/release ["ver" \| --auto \| --dry-run]` | SemVer bump, changelog, tag; deployment readiness gate (7 phases). |

**Lifecycle ops:**

| Command | Purpose |
|---|---|
| `/add-dep "package"` | Add a dependency after full vetting. |
| `/rotate "artifact-id"` | Rotate a secret / key / OIDC client / TLS cert / service token with audit + archival gates. |
| `/ticket "title" \| <sub>` | Optional scope-overflow inbox (in-repo or Plane variant). |

**Init / bootstrap:**

| Command | Purpose |
|---|---|
| `/init` | Re-run initialization detection (repair only). |
| `/init-vendor [--vendor-path=…]` | Wire codeArbiter into a host project after submoduling it (run once per install + on upgrades with `--force`). |
| `/decompose` | Scaffold `projectContext/` for a new project with no code yet. |
| `/create-context` | Back-fill `projectContext/` for an existing codebase (brownfield init). |

**Escapes & safety valves:**

| Command | Purpose |
|---|---|
| `/surface-conflict "..."` | Stop everything and surface a rule conflict between AGENTS.md and code/docs. |
| `/override "reason"` | Sanctioned bypass with mandatory audit logging. |
| `/hotfix "reason" --severity --escalation-tier --auto-revert-window` | Emergency bypass with two-identity audit and post-hoc ADR. |

**Developer aids:**

| Command | Purpose |
|---|---|
| `/onboard ["scope"]` | Engineer onboarding tour, full or scoped to one domain area. |
| `/new-skill "gap description"` | Author a new skill after gap validation. |
| `/commands` | Show the full quick-reference table from `COMMANDS.md`. |
| `/status` | Show stage, open tasks, open questions, available commands. |
| `/btw "question"` | Lightweight Q&A — no state change. |

---

## License

Licensed under the [MIT License](./LICENSE). Use it for anything.
