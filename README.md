# codeArbiter

**An orchestration framework for Claude Code that routes work through skills and agents, enforces TDD and commit gates, surfaces rule conflicts, and keeps a permanent audit trail.**

codeArbiter is opinionated infrastructure that sits on top of Claude Code. Instead of letting an AI assistant freelance across your repo, every user intent flows through a slash command that fans out to specialized skills (TDD, commit-gate, decision-lifecycle, etc.) and reviewer agents (security, migration, dependency, etc.). The framework refuses to commit without all gates green, refuses to resolve open questions by guessing, and refuses to silently reconcile contradictions between docs and code.

The full specification is in [`AGENTS.md`](./AGENTS.md). The command catalog is in [`COMMANDS.md`](./COMMANDS.md).

---

## How it works

```
.agents/
├── agents/           # Reviewer subagent definitions (auth-crypto, migration, dependency, …)
├── commands/         # Slash command bodies (/feature, /fix, /commit, /pr, /stage, …)
├── hooks/            # Pre/post tool-use hooks + statusline + session-start
├── projectContext/   # The single source of truth for project state
│   ├── CONTEXT.md          # Identity, scope, NOT-this-project (sentinel: <!--INITIALIZED-->)
│   ├── stage               # Single integer: current stage
│   ├── open-tasks.md       # In-flight, backlog, blocked
│   ├── open-questions.md   # Unresolved CONFIRM-NN items (block stage promotion)
│   ├── overrides.log       # Append-only audit log of every gate bypass
│   ├── decisions/          # ADRs
│   ├── tickets/            # Optional scope-overflow inbox
│   └── …                   # tech-stack, security-controls, audit-spec, etc.
├── skills/           # Orchestration skills (tdd, commit-gate, ticketing-router, …)
└── settings.json     # Claude Code config: MCP servers, hooks, statusline

.claude/              # Shim layer — symlinks back into .agents/
├── settings.json   → ../.agents/settings.json
├── agents/         → ../.agents/agents/
└── commands/       → ../.agents/commands/
```

The `.claude/` directory is what Claude Code natively reads. All real content lives under `.agents/` so the framework can be lifted into another project as a single unit.

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

1. **Copies `AGENTS.md`** from the vendor path to your repo root — Claude Code must be able to find `AGENTS.md` at `$CLAUDE_PROJECT_DIR` to load the orchestrator
2. **Writes `CLAUDE.md`** at your repo root containing `@AGENTS.md` — the standard Claude Code project-instructions shim
3. **Generates `.claude/commands/*.md` shims** pointing into the vendor path so every `/command` resolves correctly

Re-run with `--force` after every codeArbiter upgrade to keep `AGENTS.md` and all shims current.

---

### Option A — `git submodule` (recommended)

```sh
# 1. Vendor codeArbiter
git submodule add <repo-url> vendor/codearbiter
git commit -m "vendor: add codeArbiter submodule"

# 2. Symlink .agents/ so hook commands (bash .agents/hooks/…) resolve at repo root
ln -s vendor/codearbiter/.agents .agents

# 3. Symlink .claude/settings.json so Claude Code picks up hooks and MCP config
mkdir -p .claude
ln -s ../vendor/codearbiter/.agents/settings.json .claude/settings.json

git add .agents .claude
git commit -m "vendor: wire codeArbiter hooks and settings"

# 4. Open Claude Code and run /init-vendor
claude
# → /init-vendor --vendor-path=vendor/codearbiter/
# This writes AGENTS.md and CLAUDE.md at your repo root and generates .claude/commands/ shims.

# 5. Initialize project context
# → /create-context   (existing codebase)
# → /decompose        (new project, no code yet)
```

To upgrade codeArbiter later:
```sh
git -C vendor/codearbiter pull origin main
git add vendor/codearbiter
git commit -m "vendor: upgrade codeArbiter"
# Then in Claude Code: /init-vendor --vendor-path=vendor/codearbiter/ --force
```

### Option B — `git subtree` (vendored into your history, no submodule overhead)

```sh
git subtree add --prefix=vendor/codearbiter <repo-url> main --squash
ln -s vendor/codearbiter/.agents .agents
mkdir -p .claude
ln -s ../vendor/codearbiter/.agents/settings.json .claude/settings.json
git add .agents .claude && git commit -m "vendor: wire codeArbiter"
# Then in Claude Code: /init-vendor --vendor-path=vendor/codearbiter/
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

**Why the `.agents/` symlink?** Hook commands in `settings.json` are resolved relative to `$CLAUDE_PROJECT_DIR` (your repo root) and reference bare paths like `bash .agents/hooks/session-start.sh`. The symlink makes those paths resolve without modifying `settings.json`. Your project state (`projectContext/`) is written by `/create-context` into the symlinked `.agents/` — if you want strict separation, copy instead of symlinking and point the hook paths at the vendor location manually.

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

| Command | Purpose |
|---|---|
| `/feature "description"` | Start a new feature; runs the full TDD skill (6 phases). |
| `/fix "bug"` | Same workflow, bug-framed. |
| `/commit` | Commit staged changes after the full commit-gate runs green. |
| `/pr [title]` | Open a PR once all reviewer gates clear. |
| `/review [scope]` | Security + code review of a path. |
| `/threat-model "scope"` | Pre-implementation threat model. |
| `/adr "title"` | Record a new architectural decision (with user attribution). |
| `/checkpoint [focus]` | Full 7-reviewer parallel checkpoint. |
| `/stage [target]` | Show current stage or promote to a target stage. |
| `/add-dep "package"` | Add a dependency after full vetting. |
| `/ticket "title"` | Optional scope-overflow inbox (in-repo or Plane). |
| `/surface-conflict "..."` | Stop everything and surface a rule conflict. |
| `/btw "question"` | Lightweight Q&A — no state change. |
| `/override "reason"` | Sanctioned bypass with mandatory audit logging. |
| `/create-context` | Back-fill `projectContext/` for an existing codebase (brownfield init). |
| `/decompose` | Scaffold `projectContext/` for a new project with no code yet. |
| `/onboard` | Tour the framework. |
| `/status` | Show stage, open tasks, open questions, available commands. |

Full catalog with body links: [`COMMANDS.md`](./COMMANDS.md).

---

## License

Licensed under the [MIT License](./LICENSE). Use it for anything.
