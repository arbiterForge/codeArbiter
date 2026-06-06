<div align="center">

# codeArbiter

**An orchestration layer for Claude Code that refuses to freelance.**

Every intent routes through a gated skill or reviewer agent. Nothing commits until the gates are green. Decisions go through SMARTS. The audit trail is append-only.

<img alt="Claude Code plugin" src="https://img.shields.io/badge/Claude_Code-plugin-d97757">
<img alt="version 2.0.0" src="https://img.shields.io/badge/version-2.0.0-2b7489">
<img alt="commands" src="https://img.shields.io/badge/commands-24-555">
<img alt="skills" src="https://img.shields.io/badge/skills-20-555">
<img alt="agents" src="https://img.shields.io/badge/agents-14-555">
<img alt="license MIT" src="https://img.shields.io/badge/license-MIT-3da639">

<sub>Install it globally; it stays dormant until you opt a repo in.</sub>

</div>

---

## What it is

codeArbiter is a native Claude Code plugin that sits between you and your codebase. Instead of letting the model freelance, you drive through slash commands. Each one routes to the skill or agent that owns the work — TDD, the commit gate, decision-variance/SMARTS, the reviewer fleet — and clears its gates before anything ships.

It will not:

- write feature code before a failing test exists,
- commit on a red suite or without the commit gate,
- resolve an open question by guessing, or
- silently reconcile a contradiction between your docs and your code.

It is decisive and terse by design. If you want an assistant that hedges, this is the wrong tool.

## How it works

One plugin, named `ca`. Claude Code namespaces every plugin command, so you invoke it as <kbd>/ca:feature</kbd>, <kbd>/ca:commit</kbd>, <kbd>/ca:commands</kbd>, and so on.

Activation is **per-repo and explicit**. A `SessionStart` hook checks the repo for `.codearbiter/CONTEXT.md` carrying the frontmatter flag `arbiter: enabled`. Present → it injects the orchestrator persona and live startup state. Absent → it exits silently. Install the plugin globally and it stays out of the way everywhere you haven't opted in.

```mermaid
flowchart LR
    A(["SessionStart hook"]) --> B{"CONTEXT.md:<br/>arbiter enabled?"}
    B -->|yes| C["inject ORCHESTRATOR.md<br/>+ stage · tasks · questions"]
    B -->|no| D["dormant —<br/>generic statusline only"]
    C --> E["/ca: commands route to<br/>gated skills + reviewer agents"]
    E --> F(["gates clear → it ships"])
```

The same flag gates the statusline: the usage/context segment renders everywhere; the arbiter segments light up only in an enabled repo.

Project state lives in **your** repo, not the plugin — a single `.codearbiter/` directory at the repo root, so stage, specs, plans, ADRs, the decision log, and the overrides audit trail commit alongside your code and survive uninstalling the plugin.

<table>
<tr><th align="left">Lands in a consumer repo</th><th align="left">Lives elsewhere</th></tr>
<tr>
<td valign="top">

`.codearbiter/` &nbsp;— and nothing else

</td>
<td valign="top">

The plugin itself → `~/.claude/plugins/cache/`

</td>
</tr>
</table>

## Install

codeArbiter self-hosts a single-plugin marketplace from this repo.

```text
/plugin marketplace add SUaDtL/codeArbiter
/plugin install ca@codearbiter
```

Hooks, commands, agents, and statusline wiring load automatically; everything resolves under the `/ca:` namespace.

<details>
<summary><b>Install from a local clone</b> (for hacking on it)</summary>

<br>

```sh
git clone https://github.com/SUaDtL/codeArbiter
```
```text
/plugin marketplace add ./codeArbiter
/plugin install ca@codearbiter
```

</details>

## Enable codeArbiter in a repo

Installing the plugin does nothing until you opt a repo in. Open the repo in Claude Code and pick the path that matches:

| You have… | Run | What it does |
|---|---|---|
| an existing codebase | <kbd>/ca:create-context</kbd> | back-fills `.codearbiter/` from the source already there |
| a new project, no code yet | <kbd>/ca:decompose</kbd> | a layered interview that scaffolds `.codearbiter/` |
| just want the state store | <kbd>/ca:init</kbd> | writes `.codearbiter/` with `arbiter: enabled` |

Once `.codearbiter/CONTEXT.md` carries the `<!--INITIALIZED-->` marker, you're in normal operation: the next session opens with the orchestrator active and the startup state presented. From there, everything flows through commands.

## Statusline

```text
/ca:statusline
```

Wires a token-aware statusline. The usage/context/cost segment renders in every repo; in an arbiter-enabled repo it also surfaces stage, open-task and open-question counts, the git branch, and overrides logged since the last checkpoint.

```text
● stage:2 │ tasks:6 q:0 │ ⎇ rewrite/v2 │ over:0    ·  ctx 38%  $0.42
```

Remove it any time with <kbd>/ca:statusline</kbd> — it backs up and restores whatever statusline you had before.

## Commands

Every intent flows through a command; direct off-channel instructions get redirected to the catalog. The full list is in [`plugins/ca/COMMANDS.md`](./plugins/ca/COMMANDS.md) and via <kbd>/ca:commands</kbd>.

| Command | Purpose |
|---|---|
| <kbd>/ca:feature "desc"</kbd> | Spec-driven feature: brainstorm → plan → test-first build → commit → finish. **The only path to implementation.** |
| <kbd>/ca:fix "bug"</kbd> | Regression-test-first defect fix. |
| <kbd>/ca:commit</kbd> | The only path to a commit; routes through the nine-gate `commit-gate`. |
| <kbd>/ca:review</kbd> | Dispatch the reviewer fleet over the diff; BLOCK on CRITICAL/HIGH. |
| <kbd>/ca:adr "title"</kbd> | Author a numbered, user-attributed Architecture Decision Record. |
| <kbd>/ca:status</kbd> | Stage, open tasks, unresolved `CONFIRM-NN`, overrides since checkpoint. |

<details>
<summary><b>The full catalog</b> — 24 commands</summary>

<br>

**Implementation**

| Command | Purpose |
|---|---|
| `/ca:feature "desc"` | Spec-driven feature — the only entry to implementation |
| `/ca:fix "bug"` | Regression-test-first defect fix |
| `/ca:refactor "surface"` | Behavior-preserving restructure behind a parity-coverage gate |
| `/ca:debug "symptom"` | Investigate-then-decide root-cause analysis |

**Commit &amp; ship**

| Command | Purpose |
|---|---|
| `/ca:commit` | The only path to a commit; routes through `commit-gate` |
| `/ca:pr` | Open / finish a branch — no direct-to-default |
| `/ca:review [path]` | Reviewer-fleet pass over the diff; BLOCK on CRITICAL/HIGH |
| `/ca:checkpoint` | Lean periodic multi-reviewer sweep |
| `/ca:release [--dry-run]` | SemVer bump + changelog + annotated tag |
| `/ca:add-dep "pkg"` | Vet a dependency (license, provenance, supply chain) |

**Decisions**

| Command | Purpose |
|---|---|
| `/ca:adr "title"` | Author a numbered, user-attributed ADR |
| `/ca:adr-status [--adr N]` | List/inspect ADR status and supersede chains |
| `/ca:decision-variance` | Reconcile artifacts vs. scaffold via SMARTS |
| `/ca:surface-conflict` | Stop all work and surface a rule conflict |
| `/ca:threat-model "scope"` | Optional lightweight STRIDE pass |

**Project &amp; meta**

| Command | Purpose |
|---|---|
| `/ca:decompose` | Greenfield: layered interview to populate `.codearbiter/` |
| `/ca:create-context` | Brownfield: back-fill `.codearbiter/` from source |
| `/ca:init` | Scaffold the `.codearbiter/` state store |
| `/ca:status` | Maturity, open tasks, unresolved `CONFIRM-NN`, overrides |
| `/ca:statusline` | Install/wire the codeArbiter statusline |
| `/ca:new-skill "gap"` | Author a new skill after the gap is proven uncovered |
| `/ca:btw "question"` | Lightweight Q&amp;A; no state change |
| `/ca:override "reason"` | Sanctioned, logged single-identity gate bypass |
| `/ca:commands` | Show the catalog |

</details>

## The gates

The non-negotiables codeArbiter enforces in every enabled repo:

- **No feature code before `tdd` Phase 1** — a failing test comes first.
- **No commit without `commit-gate`**, and never on a red suite. "It looks good" is not permission.
- **No `[CONFIRM-NN]` resolved by guessing** — the question is surfaced and work stops.
- **No silent reconciliation** of a conflict between persona, docs, and code — it routes to `/ca:surface-conflict`.
- **No direct-to-`main`, no force-push** — all changes via branch/PR.
- **ADRs only via `/ca:adr`**, with explicit user attribution.
- **Every `/ca:override` is logged** to an append-only audit trail.

When rules pull apart, they resolve by a fixed hierarchy — security & audit-trail correctness first, then data integrity, maintainability, performance, velocity — and a non-obvious tradeoff cites the level it was made at.

## What's inside

```text
.claude-plugin/marketplace.json     single-plugin marketplace → ./plugins/ca
plugins/ca/                         the plugin (CLAUDE_PLUGIN_ROOT)
├── .claude-plugin/plugin.json
├── ORCHESTRATOR.md                 always-on persona, injected by the SessionStart hook
├── COMMANDS.md                     command catalog
├── commands/   (24)   skills/   (20)   agents/   (14)
├── includes/                       routing-table · reference-map · redirect (loaded on demand)
└── hooks/                          session-start (activation linchpin) · pre/post gates · statusline
```

**Skills** encode gated processes — `tdd`, `commit-gate`, `decision-variance`/SMARTS, `debug`, `refactor`, and the dynamic brainstorm → plan → execute workflow layer. **Agents** are the dispatched reviewers and authors — security, auth/crypto, dependency, migration, coverage, and architecture-drift reviewers, plus the backend/frontend/infra authors and the scout/grader/triage plumbing.

<details>
<summary><b>Why "decisive and terse"?</b></summary>

<br>

codeArbiter is built to be an enforcement layer, not a collaborator that talks you out of the rules. It states, it doesn't hedge; it enforces, it doesn't negotiate. The gates exist because the failure mode of an eager AI assistant is *plausible-but-wrong work that ships*. The orchestrator's job is to make that hard.

</details>

## Project history

codeArbiter v2 is a ground-up rebuild — from a ~13,600-line `.agents/` + vendoring framework into a native Claude Code plugin. The full story is in [`CHANGELOG.md`](./CHANGELOG.md). The v1 framework is preserved under [`legacy/`](./legacy/) for reference.

## License

[MIT](./LICENSE). Use it for anything.

<div align="center"><sub>Built for <a href="https://claude.com/claude-code">Claude Code</a>.</sub></div>
