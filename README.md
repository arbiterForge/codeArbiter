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
├── skills/           # Orchestration skills (tdd, commit-gate, ticketing, …)
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

## Importing codeArbiter into another project

codeArbiter is designed to be lifted into a host project. Three options:

### Option A — `git submodule` (recommended for upstream tracking)

```sh
cd my-host-project
git submodule add <repo-url> vendor/codeArbiter
ln -s vendor/codeArbiter/.agents .agents
ln -s vendor/codeArbiter/.claude .claude
git add .gitmodules vendor/codeArbiter .agents .claude
git commit -m "vendor codeArbiter as submodule"
```

The symlinks keep `$CLAUDE_PROJECT_DIR` (the host repo root) as the working dir while letting hooks find `.agents/projectContext/` at the expected relative path. To update later: `git -C vendor/codeArbiter pull && git commit vendor/codeArbiter`.

### Option B — `git subtree` (vendored into your history)

```sh
cd my-host-project
git subtree add --prefix=vendor/codeArbiter <repo-url> main --squash
ln -s vendor/codeArbiter/.agents .agents
ln -s vendor/codeArbiter/.claude .claude
```

Same symlink pattern. Updates with `git subtree pull --prefix=vendor/codeArbiter <repo-url> main --squash`.

### Option C — Plain copy (no upstream linkage)

```sh
cp -r path/to/codeArbiter/.agents ./.agents
cp -r path/to/codeArbiter/.claude ./.claude
```

Easiest. No way to pull future updates without manually re-copying.

**Important in all three cases:** Claude Code resolves hook commands relative to `$CLAUDE_PROJECT_DIR`, which is your host repo root. The symlink pattern (Options A and B) puts `.agents/` at the expected location while the actual files live under `vendor/codeArbiter/`. If you skip the symlinks, you'll need to edit `.claude/settings.json` to use prefixed paths like `bash vendor/codeArbiter/.agents/hooks/...`.

**Note on the root README/LICENSE:** these files are not part of `.agents/` and do not travel via submodule/subtree imports. That's intentional — your host project has its own README and license. Authoritative docs for shipped components (like the statusline) live under `.agents/` so they follow the framework. See [`.agents/hooks/STATUSLINE.md`](./.agents/hooks/STATUSLINE.md) for an example.

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
| `/onboard` | Tour the framework. |
| `/status` | Show stage, open tasks, open questions, available commands. |

Full catalog with body links: [`COMMANDS.md`](./COMMANDS.md).

---

## License

Licensed under the [MIT License](./LICENSE). Use it for anything.
