# codeArbiter

**An orchestration layer for Claude Code. It routes every intent through a gated skill or reviewer agent, refuses to commit until the gates are green, decides with SMARTS, and keeps an append-only audit trail.**

codeArbiter is a native Claude Code plugin. Installed, it sits dormant in every repo until you opt a repo in. In an opted-in repo it takes over: you stop freelancing across the codebase and start driving through slash commands. Every command routes to the skill or agent that owns the work — TDD, commit-gate, decision-variance/SMARTS, the reviewer fleet — and each clears its gates before anything ships. It will not write feature code before a failing test, will not commit on a red suite, will not resolve an open question by guessing, and will not silently reconcile a contradiction between your docs and your code.

It is decisive and terse by design. If you want an assistant that hedges, this is the wrong tool.

---

## How it works

codeArbiter is one plugin, named `ca`. Claude Code namespaces every plugin command, so you invoke it as `/ca:feature`, `/ca:commit`, `/ca:commands`, and so on.

- **Activation is per-repo and explicit.** A `SessionStart` hook checks the repo for `.codearbiter/CONTEXT.md` with the frontmatter flag `arbiter: enabled`. If present, the hook injects the orchestrator persona (`ORCHESTRATOR.md`) plus live startup state — stage, blocking questions, in-flight tasks. If absent, the hook exits silently. Install the plugin globally and it stays out of the way everywhere you haven't opted in.
- **The same flag gates the statusline.** The usage/context segment renders everywhere; the arbiter segments (stage, open tasks, open questions, overrides-since-checkpoint) light up only in an arbiter-enabled repo.
- **Project state lives in your repo, not the plugin.** Everything codeArbiter records about a project — stage, specs, plans, ADRs, the decision log, the overrides audit trail — lives in a single `.codearbiter/` directory at the repo root, so it commits alongside your code and survives even if you uninstall the plugin.

```
your-repo/
├── .codearbiter/              ← the ONLY footprint codeArbiter adds to your repo
│   ├── CONTEXT.md             ← identity, scope; `arbiter: enabled` + <!--INITIALIZED-->
│   ├── stage                  ← maturity value (a rigor knob, not ceremony)
│   ├── open-tasks.md  open-questions.md
│   ├── specs/  plans/  decisions/  decision-log.md
│   ├── security-controls.md   ← banned crypto, secret policy, security boundaries
│   └── overrides.log          ← append-only audit trail of every gate bypass
└── …your actual code…
```

The plugin itself installs to `~/.claude/plugins/cache/` — **nothing** else is dropped in your repo.

---

## Install

codeArbiter self-hosts a single-plugin marketplace from this repo.

```
# 1. Register the marketplace (GitHub shorthand)
/plugin marketplace add SUaDtL/codeArbiter

# 2. Install the plugin
/plugin install ca@codearbiter
```

That's it — the hooks, commands, agents, and statusline wiring load automatically. Command bodies and skills resolve under the `/ca:` namespace.

**Install from a local clone (for hacking on it):**

```
git clone https://github.com/SUaDtL/codeArbiter
/plugin marketplace add ./codeArbiter
/plugin install ca@codearbiter
```

---

## Enable codeArbiter in a repo

Installing the plugin does nothing until you opt a repo in. Open the repo in Claude Code and pick the path that matches:

- **Existing codebase** → `/ca:create-context` back-fills `.codearbiter/` from what's already there.
- **New project, no code yet** → `/ca:decompose` runs a layered interview to scaffold `.codearbiter/`.
- **Just scaffold the state store** → `/ca:init` writes `.codearbiter/` with `arbiter: enabled`.

Once `.codearbiter/CONTEXT.md` carries the `<!--INITIALIZED-->` marker, you're in normal operation. The next session opens with the orchestrator active and the startup state presented. From there, everything flows through commands — run `/ca:commands` for the catalog.

---

## Statusline

codeArbiter ships a token-aware statusline. Wire it in with:

```
/ca:statusline
```

The usage/context/cost segment renders in every repo. In an arbiter-enabled repo it also surfaces stage, open-task and open-question counts, the git branch, and overrides logged since the last checkpoint. Remove it any time with `/ca:statusline` (uninstall) — it backs up and restores whatever statusline you had before.

---

## Commands

Every user intent flows through a command; direct off-channel instructions get a redirect to the catalog. Full catalog: [`plugins/ca/COMMANDS.md`](./plugins/ca/COMMANDS.md). Highlights:

| Command | Purpose |
|---|---|
| `/ca:feature "desc"` | Spec-driven feature: brainstorm → plan → test-first build → commit → finish. The only path to implementation. |
| `/ca:fix "bug"` | Regression-test-first defect fix. |
| `/ca:refactor "surface"` | Behavior-preserving restructure behind a parity-coverage gate. |
| `/ca:debug "symptom"` | Investigate-then-decide root-cause analysis. |
| `/ca:commit` | The only path to a commit; routes through the nine-gate `commit-gate`. |
| `/ca:pr` · `/ca:review` · `/ca:checkpoint` | Open/finish a branch; dispatch the reviewer fleet; periodic sweep. |
| `/ca:adr "title"` · `/ca:decision-variance` | Author a user-attributed ADR; reconcile artifacts via SMARTS. |
| `/ca:add-dep` · `/ca:release` · `/ca:threat-model` | Vet a dependency; cut a SemVer release; optional STRIDE pass. |
| `/ca:status` · `/ca:override "reason"` · `/ca:btw "q"` | Show state; sanctioned logged bypass; lightweight Q&A. |

---

## What's inside

```
.claude-plugin/marketplace.json     ← single-plugin marketplace → ./plugins/ca
plugins/ca/                         ← the plugin (CLAUDE_PLUGIN_ROOT)
├── .claude-plugin/plugin.json
├── ORCHESTRATOR.md                 ← always-on persona, injected by the SessionStart hook
├── COMMANDS.md                     ← command catalog
├── commands/   (24)  skills/   (20)  agents/   (14)
├── includes/         ← routing-table, reference-map, redirect (loaded on demand)
└── hooks/            ← session-start (activation linchpin), pre/post gates, statusline
```

Skills encode gated processes (`tdd`, `commit-gate`, `decision-variance`/SMARTS, `debug`, `refactor`, the dynamic brainstorm→plan→execute workflow layer). Agents are the dispatched reviewers and authors (security, auth/crypto, dependency, migration, coverage, architecture-drift, plus the backend/frontend/infra authors and the scout/grader/triage plumbing).

Earlier history — the v1 `.agents/` framework this was rebuilt from — is preserved under [`legacy/`](./legacy/) for reference.

---

## License

[MIT](./LICENSE). Use it for anything.
