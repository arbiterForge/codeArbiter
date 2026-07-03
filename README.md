<div align="center">

<img src="docs/banner.svg" alt="codeArbiter: discipline, mechanically enforced" width="100%">

**An orchestration layer for Claude Code that refuses to freelance.**

Every intent routes through a gated skill or reviewer agent. Nothing commits until the gates are green. Decisions go through SMARTS. The audit trail is append-only.

<img alt="Claude Code plugin" src="https://img.shields.io/badge/Claude_Code-plugin-d97757">
<img alt="version 2.8.11" src="https://img.shields.io/badge/version-2.8.11-2b7489">
<img alt="commands" src="https://img.shields.io/badge/commands-39-555">
<img alt="skills" src="https://img.shields.io/badge/skills-22-555">
<img alt="agents" src="https://img.shields.io/badge/agents-28-555">
<img alt="license AGPL v3" src="https://img.shields.io/badge/license-AGPL_v3-3da639">

### [Read the documentation →](https://arbiterforge.github.io/codeArbiter/)

<sub>Install it globally; it stays dormant until you opt a repo in.</sub>

</div>

---

> **License notice.** As of v2.6.0, codeArbiter is licensed under the [GNU AGPLv3](LICENSE), a change from its earlier MIT license. Copyright (C) 2026 SUaDtL, who reserves the right to dual-license under separate proprietary terms; commercial licenses are not offered at this time. See [Dual-Licensing & Contributions](#dual-licensing--contributions).

## What it is

codeArbiter is a native Claude Code plugin that sits between you and your codebase. Instead of letting the model freelance, you drive through slash commands. Each one routes to the skill or agent that owns the work (TDD, the commit gate, decision-variance/SMARTS, the reviewer fleet) and clears its gates before anything ships.

**Who it's for:** teams and power users who let agents write real code and need to prove what happened. The kind who'd rather a tool block than apologize.

It will not:

- write feature code before a failing test exists,
- commit on a red suite or without the commit gate,
- resolve an open question by guessing, or
- silently reconcile a contradiction between your docs and your code.

The gates are terse and non-negotiable. The thinking is not: it brainstorms a spec, works through a bug, and weighs a decision with you conversationally. When it enforces, it states the rule and holds the line.

The gates scale to the change: a one-line docs fix takes the small lane or `/ca:chore`, not the full spec-to-PR march. The weight exists because the failure mode of an eager AI assistant is *plausible-but-wrong work that ships*, and the gates make that hard.

## See it catch something

The first time codeArbiter blocks you, it can feel like friction, until you see what it caught. This exchange is a real one from this project's own history: a spec tried to skip ahead, and the gate stopped it before any code got written.

```text
you      /ca:fix the statusline keeps running the old version after an update

arbiter  Routing to tdd (bug variant): a regression test before any fix.
         → writes a failing test, confirms it's red for the right reason
         → minimal fix → suite green → coverage + lint gates clear

you      /ca:commit
arbiter  commit-gate: ✓ permission ✓ branch ✓ tests ✓ secrets
         ✓ behavioral proof ✓ clean diff → committed.

you      /ca:pr
arbiter  reviewer fleet over the diff: coverage-auditor flags an untested seam.
         BLOCK. Here's the gap. → (you resolve, re-run) → PR opened.
```

Every step is a gate you watch clear. You stay in the driver's seat; the gates keep the work honest.

## Install

codeArbiter self-hosts a marketplace of two sibling plugins from this repo: `ca`, the governance layer, and `ca-sandbox`, an optional isolated-container plugin (see [Feature Forge](#feature-forge)).

```text
/plugin marketplace add arbiterForge/codeArbiter
/plugin install ca@codearbiter
```

Hooks, commands, agents, and statusline wiring load automatically; everything resolves under the `/ca:` namespace.

**Prerequisites:** Python 3 on `PATH` (every hook is Python, so without it the gates and the startup
injection silently don't run) and `git config user.email` set (overrides and ADRs are attributed to
that identity). Full version matrix: [Compatibility](https://arbiterforge.github.io/codeArbiter/getting-started/compatibility/).
The optional <kbd>/ca:statusline</kbd> command writes the statusline entry into your
global `~/.claude/settings.json` (it backs up what was there and restores it on removal).

<details>
<summary><b>Install from a local clone</b> (for hacking on it)</summary>

<br>

```sh
git clone https://github.com/arbiterForge/codeArbiter
```
```text
/plugin marketplace add ./codeArbiter
/plugin install ca@codearbiter
```

</details>

## Enable codeArbiter in a repo

Installing the plugin does nothing until you opt a repo in. That silence is intentional. Open the
repo in Claude Code and run <kbd>/ca:init</kbd>: it scaffolds `.codearbiter/` with `arbiter: enabled`
and routes you to the right populator for your situation:

| You have… | /ca:init routes to | What it does |
|---|---|---|
| an existing codebase | <kbd>/ca:create-context</kbd> | back-fills `.codearbiter/` from the source already there |
| a new project, no code yet | <kbd>/ca:decompose</kbd> | a layered interview that scaffolds `.codearbiter/` (it's thorough; expect a long, resumable Q&A) |

Once `.codearbiter/CONTEXT.md` carries the `<!--INITIALIZED-->` marker, you're in normal operation: the next session opens with the orchestrator active and the startup state presented. From there, everything flows through commands.

## How it works

One plugin, named `ca`. Claude Code namespaces every plugin command, so you invoke it as <kbd>/ca:feature</kbd>, <kbd>/ca:commit</kbd>, <kbd>/ca:commands</kbd>, and so on.

Activation is **per-repo and explicit**. A `SessionStart` hook checks the repo for `.codearbiter/CONTEXT.md` carrying the frontmatter flag `arbiter: enabled`. Present → it injects the orchestrator persona and live startup state. Absent → it exits silently. Install the plugin globally and it stays out of the way everywhere you haven't opted in.

The first session of each local day also opens with a read-only repo-hygiene briefing: branch drift against the remote, merged-but-unpruned branches, stale worktrees, and uncommitted or stashed work, all surfaced, never acted on. The full briefing fires **once per day**; later sessions that day stay quiet, with a single-line offer (`run /ca:standup`) only if something is actionable, and **nothing at all when the repo is clean**. The briefing only *reports*; <kbd>/ca:standup</kbd> is the separate command that performs the cleanups under per-action confirmation (ff-only pull on a clean tree, branch and worktree pruning, never the default branch).

```mermaid
flowchart LR
    A(["SessionStart hook"]) --> B{"CONTEXT.md:<br/>arbiter enabled?"}
    B -->|yes| C["inject ORCHESTRATOR.md<br/>+ stage · tasks · questions"]
    B -->|no| D["dormant:<br/>generic statusline only"]
    C --> E["/ca: commands route to<br/>gated skills + reviewer agents"]
    E --> F(["gates clear → it ships"])
```

The same flag gates the statusline: the usage/context segment renders everywhere; the arbiter segments light up only in an enabled repo.

Project state lives in **your** repo, not the plugin: a single `.codearbiter/` directory at the repo root, so stage, specs, plans, ADRs, the decision log, tribunal reports, and the overrides audit trail commit alongside your code and survive uninstalling the plugin.

<table>
<tr><th align="left">Lands in a consumer repo</th><th align="left">Lives elsewhere</th></tr>
<tr>
<td valign="top">

Just `.codearbiter/`, nothing else

</td>
<td valign="top">

The plugin itself → `~/.claude/plugins/cache/`

</td>
</tr>
</table>

Three features extend what the plugin tracks across a session. [Provenance and context drift](https://arbiterforge.github.io/codeArbiter/concepts/provenance-drift/): derived docs record their sources; stale derivations surface at `SessionStart` and the commit gate auto-heals them. [Just-in-time context injection](https://arbiterforge.github.io/codeArbiter/concepts/jit-context-injection/): on a read of a governed file, the controlling decision or spec is surfaced at the point of touch. [Board transitions land with the work](https://arbiterforge.github.io/codeArbiter/concepts/hardening-history/): `/ca:task` flips ride the work commit (ADR-0008), not a separate trailing chore.

## The gates

The non-negotiables codeArbiter enforces in every enabled repo:

- **No feature code before `tdd` Phase 1**: a failing test comes first.
- **No commit without `commit-gate`**, and never on a red suite. "It looks good" is not permission.
- **No `[CONFIRM-NN]` resolved by guessing**: the question is surfaced and work stops.
- **No silent reconciliation** of a conflict between persona, docs, and code; it routes to `/ca:conflict`.
- **No direct-to-`main`, no force-push**: all changes via branch/PR.
- **ADRs only via `/ca:adr`**, with explicit user attribution; an ADR with a `governs:` field pushes back at edit time on the files it constrains.
- **Every `/ca:override`, `/ca:dev` session, and small-lane triage call is logged** to append-only audit logs the hooks mechanically protect from rewrite.

When rules pull apart, they resolve by a fixed hierarchy (security & audit-trail correctness first, then data integrity, maintainability, performance, velocity), and a non-obvious tradeoff cites the level it was made at.

## Commands

Every intent flows through a command; direct off-channel instructions get redirected to the catalog. The full list is in [`plugins/ca/COMMANDS.md`](./plugins/ca/COMMANDS.md), the [site reference index](https://arbiterforge.github.io/codeArbiter/reference/commands/commands/), and via <kbd>/ca:commands</kbd>.

| Command | Purpose |
|---|---|
| <kbd>/ca:feature "desc"</kbd> | Spec-driven feature: brainstorm → plan → test-first build → commit → finish. **The only path to implementation.** |
| <kbd>/ca:sprint "goal"</kbd> | **Autonomous sprint.** One interactive spec gate, then plan-to-PR execution, every auto-decision SMARTS-scored and logged with a confidence flag for your morning review. Security, irreversible ops, and merges still stop for you. |
| <kbd>/ca:fix "bug"</kbd> | Regression-test-first defect fix. |
| <kbd>/ca:commit</kbd> | The only path to a commit; routes through the nine-gate `commit-gate`. |
| <kbd>/ca:review</kbd> | Dispatch the reviewer fleet over the diff; BLOCK on CRITICAL/HIGH. |
| <kbd>/ca:adr "title"</kbd> | Author a numbered, user-attributed Architecture Decision Record. |
| <kbd>/ca:status</kbd> | Stage, open tasks, unresolved `CONFIRM-NN`, overrides since checkpoint. |
| <kbd>/ca:audit</kbd> | One command, one packet: every commit, override, ADR, and autonomous decision in a window, with attribution: the document an auditor actually asks for. |
| <kbd>/ca:metrics</kbd> | Read-only trend glance: override rate, small-lane rate, and sprint low-confidence ratio, each with a direction arrow vs. the prior 20-commit window. |

<details>
<summary><b>The full catalog</b>: 39 commands</summary>

<br>

**Implementation**

| Command | Purpose |
|---|---|
| `/ca:feature "desc"` | Spec-driven feature: the only entry to implementation; a logged small lane skips ceremony for small changes |
| `/ca:sprint "goal"` | Autonomous sprint: one spec gate, then plan-to-PR with every auto-decision logged |
| `/ca:fix "bug"` | Regression-test-first defect fix |
| `/ca:refactor "surface"` | Behavior-preserving restructure behind a parity-coverage gate |
| `/ca:debug "symptom"` | Investigate-then-decide root-cause analysis |
| `/ca:chore <docs\|deps\|revert>` | Non-behavioral lane: docs edits, dependency bumps, reverts; type-scaled gates |
| `/ca:spike "question"` | Throwaway exploration on a `spike/*` branch; never merges, exits to a findings note or `/ca:feature` |

**Commit &amp; ship**

| Command | Purpose |
|---|---|
| `/ca:commit` | The only path to a commit; routes through `commit-gate` |
| `/ca:pr` | Open / finish a branch; no direct-to-default |
| `/ca:watch <PR>` | Watch a PR's CI server-side: diagnose on red, notify and offer merge on green; never auto-merges |
| `/ca:review [path]` | Reviewer-fleet pass over the diff; BLOCK on CRITICAL/HIGH |
| `/ca:checkpoint` | Lean periodic multi-reviewer sweep |
| `/ca:tribunal [scope-path]` | Deep, rarely-run whole-codebase audit across eleven specialist lenses; one file per finding plus append-only run/triage logs, resumable from disk; files GitHub issues on approval; never a required gate |
| `/ca:release [--dry-run]` | SemVer bump + changelog + annotated tag |
| `/ca:add-dep "pkg"` | Vet a dependency (license, provenance, supply chain) |

**Decisions**

| Command | Purpose |
|---|---|
| `/ca:adr "title"` | Author a numbered, user-attributed ADR |
| `/ca:adr-status [--adr N]` | List/inspect ADR status and supersede chains |
| `/ca:reconcile ["scope"]` | Reconcile artifacts vs. scaffold via SMARTS |
| `/ca:conflict "description"` | Stop all work and surface a rule conflict |
| `/ca:threat-model "scope"` | Optional lightweight STRIDE pass |

**Project &amp; meta**

| Command | Purpose |
|---|---|
| `/ca:decompose` | Greenfield: layered interview to populate `.codearbiter/` |
| `/ca:create-context` | Brownfield: back-fill `.codearbiter/` from source |
| `/ca:init` | Scaffold the `.codearbiter/` state store |
| `/ca:status` | Maturity, open tasks, unresolved `CONFIRM-NN`, overrides |
| `/ca:task` | Task-board writer: add a queued task, start one (mints a dotted ID, stamps the date), or mark one done. The only blessed write to `open-tasks.md` |
| `/ca:statusline` | Install/wire the codeArbiter statusline |
| `/ca:doctor` | Prove the install is enforcing: payload, cache staleness, live-fire hook probe |
| `/ca:preview` | Zero-onboarding read-only dry-run of the reviewer fleet on the current diff: predicts reviewers, runs the state-free secret scan, writes nothing |
| `/ca:context-check` | Optional manual drift audit: report stale provenance-tracked docs, then per stale doc offer re-scout, re-baseline, or defer; not the daily loop, `commit-gate` auto-heal owns routine maintenance |
| `/ca:standup` | Daily hygiene: review repo state, then ff-only pull / prune merged branches / remove stale worktrees / surface stashes, each under per-action confirmation |
| `/ca:new-skill "gap"` | Author a new skill after the gap is proven uncovered |
| `/ca:btw "question"` | Lightweight Q&amp;A; no state change |
| `/ca:override "reason"` | Sanctioned, logged single-identity gate bypass |
| `/ca:audit [range]` | Assemble the governance packet for a window into `.codearbiter/audits/`; read-only |
| `/ca:metrics [--window N]` | Read-only trend glance: override rate, small-lane rate, sprint low-confidence ratio, each with a direction arrow vs. the prior 20-commit window |
| `/ca:prune [status\|dry\|run\|audit\|on\|off]` | Trim transcript clutter to extend session lifetime; dry-run by default, gains land at resume/compaction |
| `/ca:commands` | Show the catalog |

**Maintainer**

| Command | Purpose |
|---|---|
| `/ca:dev ["note"]` | Suspend orchestration to edit codeArbiter itself; requires `CODEARBITER_DEV=1`, entry/exit logged to `overrides.log` |
| `/ca:arbiter` | Exit dev mode: restore orchestration, log the exit |

</details>

## Decisions go through SMARTS

When the arbiter hits an architectural fork, such as two `accepted` ADRs that disagree or a spec that says one thing while the scaffold does another, it does not pick for you and it does not hand you a naked "A or B?" Every option is scored through **SMARTS** (Scalable, Maintainable, Available, Reliable, Testable, Securable), a fixed six-lens evaluation, and the choice it presents carries that analysis with it.

Each lens gets one cell per option: a verdict (`Strong`, `Adequate`, `Weak`, or `Indifferent`) plus at most 20 words of justification citing a specific property or failure mode, never "industry standard." That is what lands in front of you, a table, not an opinion:

| Lens | Bundle the auth engine | Customer-provided |
|---|---|---|
| Scalable | Adequate. Sub-ms decisions sufficient at 50-user scale. | Adequate. Same ceiling, adds a network hop. |
| Maintainable | Strong. One package owns versioning and integration. | Weak. Two release cycles must coordinate. |
| Available | Strong. Available whenever the system is. | Weak. Depends on customer infrastructure. |
| Reliable | Strong. Failure contained in the deployment boundary. | Weak. Failure surface includes customer network. |
| Testable | Strong. Local test env is one package install. | Weak. Requires standing up two services. |
| Securable | Strong. Self-contained mandate satisfied. | Weak. Cross-service auditing is harder. |

**Recommendation:** Bundle. Strength: **strong**. Securable and Available dominate cleanly, and no lens favors external enough to override.

Every recommendation carries exactly one strength label (`strong`, `moderate`, or `tied`; there is no `weak`) and a `Precedent:` line citing the most similar prior decisions.

**You still decide.** The arbiter recommends; it never records a decision you didn't explicitly make. "Use your best judgment" is declined, because the decision log is append-only and every entry is attributed to a person.

**Autonomy with a paper trail.** <kbd>/ca:sprint</kbd> reuses the same six-lens scoring to decide "as the user" on every non-hard-gate point, logging each call to `.codearbiter/sprint-log.md` with a confidence flag (`high` for `strong`, `low` for `moderate` or `tied`) so you know exactly what to skim in the morning. Security boundaries, irreversible operations, gate bypasses, and an unresolved `[CONFIRM-NN]` still stop and wait for you.

More detail and the full lens definitions: [SMARTS](https://arbiterforge.github.io/codeArbiter/concepts/smarts/) and [Autonomous sprints](https://arbiterforge.github.io/codeArbiter/guides/autonomous-sprints/).

## Statusline

codeArbiter ships a token-aware statusline. Wire it in with <kbd>/ca:statusline</kbd>:

<div align="center"><img alt="codeArbiter statusline" src="./site/public/diagrams/statusline.png" width="880"></div>

The folder, git/diff, rate limits, token usage, cost, and context segments render in every repo; the arbiter row (stage · tasks · open questions · overrides-since-checkpoint) lights up only in an enabled repo. Token counts come from the session transcript and the **cost is Claude Code's own `cost.total_cost_usd`** (what you actually pay); the context bar shifts toward red as you near compaction, the model pill carries the active model **and** its effort level, and session age sits beside the compaction headroom.

Remove it any time with <kbd>/ca:statusline</kbd>; it backs up and restores whatever statusline you had before.

## Staying up to date

codeArbiter self-hosts a **third-party** marketplace, and Claude Code's native plugin auto-update is
enabled by default only for official Anthropic marketplaces: it's **off by default** for a
third-party one like this. The official update mechanism is still the native one; you just have to
turn it on:

```text
/plugin marketplace update codearbiter
```

Run that whenever you want the latest release, or check whether your marketplace auto-updates are
enabled via `/plugin`. Release notes: [Changelog](https://arbiterforge.github.io/codeArbiter/changelog/).

Because that's opt-in, codeArbiter also checks for you: at session start (and in the statusline), it
surfaces a one-line notice when a newer release is published:

```text
codeArbiter: update available 2.8.11 -> 2.10.0 (run /plugin marketplace update codearbiter)
```

That check is one of exactly two background network touches the plugin makes (see
[What's inside](#whats-inside) for the other, a local `git fetch`): a best-effort, **once-a-day**,
fail-silent, unauthenticated HTTPS GET to the GitHub Releases API, no repo data sent, cached to a
small user-global file. It never blocks session start; it refreshes off to the side, so a slow or
unreachable network never delays your session, and it stays silent if the check fails or you're
already current. It only ever *tells* you; it never applies an update itself.

## Configuration

Every optional behavior is **off by default** and opt-in through an environment variable. codeArbiter never enables one on your behalf. Set them in your shell profile (or per session) to turn them on.

| Variable | Default | Effect |
|---|---|---|
| `CODEARBITER_BABYSIT` | `off` | When `on`, <kbd>/ca:pr</kbd> auto-attaches a CI watcher to the PR it opens (same as running <kbd>/ca:watch</kbd> by hand). Ad-hoc <kbd>/ca:watch</kbd> works regardless. |
| `CODEARBITER_BABYSIT_ONRED` | `propose` | The watcher's depth on a red check: `propose` (name the cause, suggest a fix, touch nothing) or `branch` (additionally stage the fix on an unmergeable `spike/fix-*`). |

Every flag is shipped off, never auto-enabled, and dormant in a repo without `arbiter: enabled`. Preview features carry their own opt-ins; see [Feature Forge](#feature-forge) below.

## Feature Forge

<div align="center"><img src="docs/feature-forge.svg" alt="The Feature Forge. Preview features: built, tested, shipping, not yet blessed" width="100%"></div>

Some features are built, tested, and shipping in the box, but not yet *blessed*. They live in the **Feature Forge**: off by default, fully dormant until you opt in, and labeled `preview` until real-world data earns them a promotion to a stable release. Nothing here touches your repo or your gates unless you turn it on. A preview graduates when real-world evidence says it's ready; each feature below names how to send that evidence back. Full detail: [What's in the Forge](https://arbiterforge.github.io/codeArbiter/feature-forge/whats-in-the-forge/).

| Feature | Opt-in | Status | How to help it graduate |
|---|---|---|---|
| Live transcript pruning | `CODEARBITER_PRUNE=dry` | `preview` | run `dry`, send the log |
| Pluggable execution farm | <kbd>/ca:sprint --farm</kbd> | `preview` | run it on a real sprint, report results |
| ca-sandbox (local Codespace) | install the `ca-sandbox` plugin | `preview` | explore real repos in it; run `--with-claude` and report |

**Live transcript pruning.** Long sessions bloat the transcript until Claude Code compacts early and you lose working headroom; `CODEARBITER_PRUNE=dry` computes every prune it would make and logs the evidence without touching your transcript. It's preview because the `dry → on` go/no-go needs that real-session evidence first. Details and tuning knobs: [What's in the Forge](https://arbiterforge.github.io/codeArbiter/feature-forge/whats-in-the-forge/).

#### Pluggable execution farm

**What it does.** <kbd>/ca:sprint --farm</kbd> runs the implementation step through a `Worker` seam in isolated git worktrees under the same hard gates, instead of a premium subagent. The cheap HTTP-chat worker ships today; the seam is built to admit **premium and agentic** workers behind the same gates (roadmap, not yet built). The worker prompt is enriched with the failing-test source and in-scope files, byte-capped and secret-redacted before transmission. Claude still writes the spec, failing tests, and plan, and **every green task still routes through the full spec-compliance + quality + fresh-verification chain**: a worker can pass the gates, never redefine them.

**Opt-in.** <kbd>/ca:sprint --farm</kbd> (needs `FARM_API_KEY`).

| Variable | Default | Purpose |
|---|---|---|
| `FARM_API_KEY` | _(required)_ | OpenAI-compatible provider key; never committed, never in audit files. |
| `FARM_MODEL` | _(unset)_ | Skip selection; otherwise the model is auto-selected by measured canary at dispatch. |
| `FARM_ENRICH_MAX_BYTES` | `131072` | Cap on test-source + in-scope context injected into the worker prompt (redacted for secrets). |
| `FARM_CONCURRENCY` | `4` | Max concurrent task workers. |
| `FARM_SAMPLES` | `1` | Parallel candidate draws per task, each in its own scratch worktree; the first to pass the gate is accepted. `FARM_SAMPLES=1` is byte-for-byte the single-candidate path. Total in-flight workers never exceed `FARM_CONCURRENCY`. |
| `FARM_TEMPERATURE` | `0` | Sampling temperature; auto-bumped to `0.7` when `FARM_SAMPLES>1` so samples diversify. Set explicitly to override. |
| `FARM_MAX_TOKENS` | _(unset)_ | Token ceiling per worker call; unset defers to the provider default. |

**Best-of-N sampling.** Because the gate is a deterministic pass/fail oracle, `FARM_SAMPLES` candidates are drawn in parallel and the first to pass is accepted; the N-fold token cost is recorded in `farm-report.json`.

Full config (endpoint, retries, circuit breaker, mutation guard, sovereignty note) is in <kbd>/ca:sprint</kbd> and the farm setup doc. It's preview because it is not yet validated on real runs; the promotion bar is the open question `CONFIRM-05`. **Help promote it:** run a real <kbd>/ca:sprint --farm</kbd> and report back the per-task pass rates and any gate escapes you see.

**ca-sandbox (local Codespace).** A locally-hosted GitHub-Codespace equivalent, shipped as a sibling plugin per ADR-0007: pull a repo you're curious about, including untrusted code, into an ephemeral, isolated Docker container. Your host filesystem is never mounted in (no bind mounts, no docker socket, never `--privileged`), and getting work back out is a host-initiated `cp` only. It ships with a full automated suite green, but the `--with-claude` path (running Claude Code inside the box) is verified only against a dummy token, not yet a real interactive session, so it stays preview until real-world runs earn it a promotion. **Help promote it:** explore real repos in it and report how `--with-claude` behaves in a real session. Install: the `ca-sandbox` plugin from the marketplace, then `/ca-sandbox:sandbox create <repo-url>`. Details: [`plugins/ca-sandbox/README.md`](./plugins/ca-sandbox/README.md).

## What's inside

```text
.claude-plugin/marketplace.json     two-plugin marketplace → ./plugins/ca, ./plugins/ca-sandbox
plugins/ca/                         the governance plugin (CLAUDE_PLUGIN_ROOT)
├── .claude-plugin/plugin.json
├── README.md                       plugin-directory summary (this file is the long form)
├── ORCHESTRATOR.md                 always-on persona, injected by the SessionStart hook
├── COMMANDS.md                     command catalog (+ user-facing glossary)
├── SPRINT.md                       /ca:sprint mode body — the autonomous-sprint procedure
├── commands/   (39)   skills/   (22)   agents/   (28)
├── includes/                       routing-table · reference-map · redirect · farm setup (loaded on demand)
├── hooks/                          session-start (activation linchpin) · pre/post gates · statusline → docs/hooks.md
└── tools/                          farm dispatcher (farm.js + TypeScript source and tests)
plugins/ca-sandbox/                 the local-Codespace plugin (Feature Forge, preview)
```

**Skills** encode gated processes: `tdd`, `commit-gate`, `decision-variance`/SMARTS, `debug`, `refactor`, and the dynamic brainstorm → plan → execute workflow layer. **Agents** are the dispatched reviewers and authors: security, auth/crypto, dependency, migration, coverage, and architecture-drift reviewers, the design-quality reviewer, plus the backend/frontend/infra authors and the scout/grader/triage plumbing.

**Hooks** are how the plugin stays active in your repo, and they run code on your machine, so they're documented in full: [`docs/hooks.md`](./docs/hooks.md) (also mirrored at [/hooks/](https://arbiterforge.github.io/codeArbiter/hooks/)) covers every hook, exactly what it reads and writes, and names the only two things any hook sends over a network: a detached local `git fetch` against your own remote, and a once-a-day fail-silent read of the GitHub Releases API (see [Staying up to date](#staying-up-to-date)). Neither blocks a hook, and no repo data leaves your machine either way.

## Turning it off

codeArbiter is dormant by default: a repo without `.codearbiter/CONTEXT.md` → `arbiter: enabled` never sees the orchestrator persona, never routes through a gate. To disable it in a repo that's already opted in, flip that frontmatter flag off; no reinstall needed. To remove the plugin entirely, uninstall it the normal Claude Code way. Either way, `.codearbiter/` survives: it's a plain directory in your repo, not plugin state, so your specs, ADRs, and audit trail stay put. Full walkthrough: [Uninstalling](https://arbiterforge.github.io/codeArbiter/guides/uninstalling/).

## Project history

codeArbiter v2 is a ground-up rebuild: from a ~13,600-line `.agents/` + vendoring framework into a native Claude Code plugin. The full story is in [`CHANGELOG.md`](./CHANGELOG.md) and the [site changelog](https://arbiterforge.github.io/codeArbiter/changelog/). The v1 framework is preserved in this repository's early commit history for reference.

## License

codeArbiter is licensed under the [GNU Affero General Public License v3.0](./LICENSE) (AGPLv3). You may use, study, modify, and redistribute it under those terms. Because AGPLv3 covers network use (section 13), running a modified version as a hosted service obligates you to offer that version's complete source under the same license.

The AGPLv3 transition applies from v2.6.0 forward. Earlier releases, through the last MIT-tagged commit, remain available under the MIT license they shipped with.

## Dual-Licensing & Contributions

**Open source.** codeArbiter is available under AGPLv3 for open-source use, free of charge.

**Commercial licensing.** The copyright holder (SUaDtL) retains sole ownership and reserves the right to offer the project under separate proprietary terms. Commercial licenses are not being offered at this time. If you have a use case that AGPLv3 does not fit, you may send an inquiry through GitHub (open an issue or reach the repository owner), and it will be considered if and when a commercial-licensing path is established.

**Contributions.** Future community contributions require a Contributor License Agreement granting the copyright holder the right to relicense the contribution under both AGPLv3 and proprietary terms, which is what keeps the dual-licensing model intact. See [CLA.md](./CLA.md). That CLA is a template pending legal review and is not yet in force.

<div align="center"><sub>Built for <a href="https://claude.com/claude-code">Claude Code</a>.</sub></div>
