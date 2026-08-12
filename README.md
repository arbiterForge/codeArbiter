<div align="center">

<img src="docs/readme-hero.webp" alt="codeArbiter. Hard gates for agentic coding." width="100%">

**Shared enforcement and project-context parity across Claude Code, Codex CLI, and Pi.**

One repository-owned governance layer for tests, reviews, security checks, decisions, and durable
project context. You decide. codeArbiter enforces.

<img alt="Claude Code plugin" src="https://img.shields.io/badge/Claude_Code-plugin-d97757">
<img alt="Codex plugin" src="https://img.shields.io/badge/OpenAI_Codex-plugin-10a37f">
<img alt="Pi Feature Forge preview" src="https://img.shields.io/badge/ca--pi-Feature_Forge_preview-d97757">
<img alt="version 2.14.0" src="https://img.shields.io/badge/version-2.14.0-2b7489">
<img alt="commands" src="https://img.shields.io/badge/commands-40-555">
<img alt="skills" src="https://img.shields.io/badge/skills-23-555">
<img alt="agents" src="https://img.shields.io/badge/agents-18-555">
<img alt="license AGPL v3" src="https://img.shields.io/badge/license-AGPL_v3-3da639">

[Start learning](https://arbiterforge.github.io/codeArbiter/learn/)
&nbsp;&nbsp;·&nbsp;&nbsp;
[Install](https://arbiterforge.github.io/codeArbiter/getting-started/install/)
&nbsp;&nbsp;·&nbsp;&nbsp;
[Browse the reference](https://arbiterforge.github.io/codeArbiter/reference/)

<sub>Install it globally. It stays dormant until a repository explicitly opts in.</sub>

</div>

> [!IMPORTANT]
> **License notice.** Since v2.6.0, codeArbiter is licensed under the
> [GNU AGPLv3](LICENSE), a change from its earlier MIT license. Copyright (C) 2026 SUaDtL, who
> reserves the right to dual-license under separate proprietary terms; commercial licenses are not
> offered at this time. See [License and contributions](#license-and-contributions).

## Agentic coding, with a record

codeArbiter is for teams and power users who let coding agents do consequential work and need more
than “the model said it passed.” Every request enters a named lane. The lane defines the evidence it
must produce, the reviewers it must dispatch, and the conditions that stop it.

This repository contains four sibling plugins:

- `ca` for Claude Code, `ca-codex` for Codex CLI, and `ca-pi` for Pi are the three governance hosts.
- `ca-sandbox` is the isolated local-Codespace infrastructure plugin.

The three governance hosts are generated from one shared surface and use one checked-in
`.codearbiter/` project store. A repository can move between hosts without losing its specs, plans,
ADRs, tasks, decisions, or audit history.

codeArbiter will not:

- write feature code before the required failing test exists;
- commit on a red suite or outside the commit gate;
- resolve a `[CONFIRM-NN]` question by guessing;
- silently reconcile a conflict between the rules, the docs, and the code; or
- push directly to the default branch or merge without the user.

The gates scale to the work. A prose edit takes the small docs lane. A security-sensitive feature
takes the full spec, test-first, review, and PR path.

The Codex path was live-verified on **Codex CLI 0.144.1** with trusted SessionStart injection and a
real `[H-03]` PreToolUse block. The dated
[Claude Code + Codex evidence](https://arbiterforge.github.io/codeArbiter/getting-started/claude-code-and-codex/)
separates continuously verified packaging from the live checks that require a model-backed turn.

## See it catch something

The landing page includes a
[faithful replay of a shipped hook invocation](https://arbiterforge.github.io/codeArbiter/#proof).
It invokes the real `pre-bash.py` guard, records the source digest, proves the blocked command never
ran, and preserves the exact stderr and audit effect. It does not pretend that a direct hook replay
proves host discovery or trust.

The operating loop looks like this:

```text
you      /ca:fix the statusline keeps running the old version after an update

arbiter  route to the regression-test-first fix lane
         failing test -> minimal fix -> focused proof -> full verification

you      /ca:commit
arbiter  permission -> branch -> tests -> behavioral proof -> diff review
         selective stage -> commit

you      /ca:pr
arbiter  reviewer fleet challenges the exact diff
         BLOCK findings are resolved before the draft PR can advance
```

The user owns the decision. The repository keeps the evidence.

## Get running

Choose the adapter for the coding host you already use. The
[host chooser](https://arbiterforge.github.io/codeArbiter/getting-started/choose-your-host/) covers
stability, command syntax, trust, and platform differences.

| Host | Adapter | Command form | Status |
|---|---|---|---|
| Claude Code | `ca` | `/ca:feature` | Stable |
| Codex CLI | `ca-codex` | `$ca-feature` | Stable |
| Pi | `ca-pi` | `/ca-feature` | Feature Forge `preview` |

**Prerequisites:** Python 3 on `PATH` and `git config user.email` set. Pi also requires Node.js
22.19+. If Python is missing, Pi installs its final wrappers but blocks mutating calls and points to
`/ca-doctor`; Claude Code and Codex surface an interpreter breadcrumb instead of silently claiming
governance is active.

### Claude Code

```text
/plugin marketplace add arbiterForge/codeArbiter
/plugin install ca@codearbiter
```

Approve the normal plugin trust prompt, open the target repository, and continue with
`/ca:init`.

### Codex CLI

The public GitHub-slug flow is **available now**. The repository currently ships `ca-codex 0.6.1`;
the dated end-to-end public-install record discovered `ca-codex 0.2.4` from release `v2.8.13`.
Current packaging and shared-core parity are continuously verified, while that dated live-install
record stays labeled rather than being silently promoted to evidence for a newer adapter:

```text
codex plugin marketplace add arbiterForge/codeArbiter
codex plugin add ca-codex@codearbiter
```

Open `/hooks`, review and trust the `ca-codex` handlers, then start a fresh task. Run `$ca-init` and
`$ca-doctor`.

For development against an unpublished checkout:

```text
git clone https://github.com/arbiterForge/codeArbiter
cd codeArbiter
codex plugin marketplace add .
codex plugin add ca-codex@codearbiter
```

### Pi

> [!NOTE]
> `ca-pi` is a Feature Forge `preview`. It is available for real use now, and you are welcome to
> install it, use it in repositories, and report what you find. Its automated and hosted promotion
> matrix is green; broader real-world evidence is still required before codeArbiter claims
> 100% validation or stable status.

The quickest install is the npm channel: `pi install npm:@arbiterforge/ca-pi` (ADR-0029). For the
reproducible pinned install, list the independently versioned tags, choose one exact result, then
inspect the installed package, grant project trust, and start a fresh session:

```sh
git ls-remote --tags --refs https://github.com/arbiterForge/codeArbiter.git "ca-pi-v*"
pi install git:github.com/arbiterForge/codeArbiter@ca-pi-v<version>
pi list
pi config
```

Replace `<version>` with the numeric suffix from the chosen tag while retaining the full
`ca-pi-v...` tag in the install source.

Pi 0.80.5 and Pi 0.84.1 are the supported hosts for this release line. Generated aliases use `/ca-*`;
`/skill:ca-*` is the host-native fallback. Every `ca-pi-v*` tag is also published to npm as
`npm:@arbiterforge/ca-pi` with provenance (ADR-0029); the pinned Git tag remains the reproducible
install. The [Pi runbook](./docs/pi-parity-testing.md) covers isolated install, trust, verification,
shared-state continuity, and uninstall.

### Protect the first repository

Use a disposable Git repository for the first run. Add at least one meaningful source file, then
invoke the host-native forms below:

| Outcome | Claude Code | Codex CLI | Pi |
|---|---|---|---|
| Scaffold project state | `/ca:init` | `$ca-init` | `/ca-init` |
| Prove enforcement | `/ca:doctor` | `$ca-doctor` | `/ca-doctor` |
| Read live state | `/ca:status` | `$ca-status` | `/ca-status` |

`init` creates `.codearbiter/` and routes an existing codebase to `create-context` or a greenfield
project to `decompose`. `doctor` must report a healthy interpreter, current payload, and H-03
live-fire probe before you treat the repository as governed.

Follow the complete
[first-repository walkthrough](https://arbiterforge.github.io/codeArbiter/getting-started/quickstart/)
for expected output, proof, and recovery.

## The docs are the operating manual

The site is designed as a continuous path from first contact to source-backed operation:

| Need | Start here | You finish able to... |
|---|---|---|
| Understand the promise | [What is codeArbiter](https://arbiterforge.github.io/codeArbiter/overview/) | explain command, route, dispatch, gate, and ship |
| Choose and install a host | [Start](https://arbiterforge.github.io/codeArbiter/getting-started/choose-your-host/) | install, trust, activate, and verify one adapter |
| Learn in order | [Learning path](https://arbiterforge.github.io/codeArbiter/learn/) | progress from foundation through the power-user capstone |
| Run daily work | [Workflows](https://arbiterforge.github.io/codeArbiter/guides/feature-lane/) | select and complete the smallest correct lane |
| Understand the model | [Concept map](https://arbiterforge.github.io/codeArbiter/concepts/) | trace routing, decisions, context, review, and audit evidence |
| Diagnose a problem | [Troubleshooting](https://arbiterforge.github.io/codeArbiter/guides/troubleshooting/) | follow a symptom to a deterministic recovery |
| Look up exact behavior | [Reference](https://arbiterforge.github.io/codeArbiter/reference/) | inspect generated commands, skills, agents, hooks, and configuration |
| Evaluate preview work | [Feature Forge](https://arbiterforge.github.io/codeArbiter/feature-forge/overview/) | opt in, verify the off switch, and understand the promotion bar |

Command, skill, agent, and hook-gate reference pages are generated from shipped source on every site
build. Hand-authored guides teach the workflow; generated pages define the exact current surface.

## How governance works

```mermaid
flowchart LR
    I["host-native command"] --> R["owning skill"]
    R --> A["author or operator action"]
    A --> V["tests + focused proof"]
    V --> F["matched reviewer fleet"]
    F --> G{"gate clear?"}
    G -->|no| X["named finding or user decision"]
    X --> A
    G -->|yes| P["selective commit + draft PR"]
```

Activation is explicit and per repository. Claude Code and Codex check
`.codearbiter/CONTEXT.md` at SessionStart. Pi checks the same file through its `session_start`
extension event and also requires affirmative project trust. Without `arbiter: enabled`, the global
install is dormant: no repository persona, no repository gates, and no governance row.

The project record lives beside the code:

```text
.codearbiter/
├── CONTEXT.md             activation, vocabulary, maturity, current objective
├── tech-stack.md          approved technologies and versions
├── coding-standards.md    implementation and verification rules
├── security-controls.md   security contract reviewers evaluate
├── open-tasks.md          durable task board
├── open-questions.md      unresolved [CONFIRM-NN] decisions
├── decisions/             numbered ADRs
├── specs/ and plans/      approved intent and execution
├── sprint-log.md          SMARTS-scored autonomous decisions
├── checkpoints/           periodic reviewer sweeps
├── audits/ and reports/   assembled evidence
└── overrides.log          append-only sanctioned bypass record
```

The [.codearbiter directory reference](https://arbiterforge.github.io/codeArbiter/codearbiter-directory/)
explains who creates, reads, and updates every artifact, plus its recovery rules.

### The hard gates

- No feature code before `tdd` Phase 1 completes.
- No commit outside `commit-gate`, and never with a red suite.
- No `[CONFIRM-NN]` resolved by guessing.
- No silent reconciliation of rule conflicts; route to `/ca:conflict`.
- No raw secret stored in the repository, logs, images, or prompts.
- No direct write to the default branch and no force-push.
- No ADR outside `/ca:adr`, with explicit user attribution.
- Every `/ca:override`, `/ca:dev` entry/exit, and sprint auto-decision is durable and attributable.
- H-18 activation protection has no in-session override path; disabling a repository requires an
  external editor and an explicit audit record.

Security and audit-trail correctness outrank data integrity, maintainability, performance, and
velocity. A non-obvious tradeoff cites the level at which it was made.

### SMARTS: bounded autonomy, explicit reasoning

SMARTS evaluates Scalable, Maintainable, Available, Reliable, Testable, and Securable properties.
Each option gets a concrete verdict and evidence, followed by a `strong`, `moderate`, or `tied`
recommendation. The user still decides.

`/ca:sprint` uses the same lenses for bounded non-hard decisions and writes every call to
`.codearbiter/sprint-log.md` with a confidence flag. Security boundaries, irreversible operations,
gate bypasses, merges, and unresolved questions remain true stops. See
[SMARTS](https://arbiterforge.github.io/codeArbiter/concepts/smarts/) and
[autonomous sprints](https://arbiterforge.github.io/codeArbiter/guides/autonomous-sprints/).

## Core lanes

| Intent | Claude Code | What the lane proves |
|---|---|---|
| New behavior | `/ca:feature "desc"` | approved spec and plan, test-first implementation, review, commit, PR |
| Autonomous delivery | `/ca:sprint "goal"` | one interactive design gate, persisted work, logged SMARTS decisions |
| Confirmed defect | `/ca:fix "bug"` | failing regression test before the minimal fix |
| Unknown cause | `/ca:debug "symptom"` | investigation and root-cause decision before any fix lane |
| Structural change | `/ca:refactor "surface"` | behavioral parity through unchanged pre-existing tests |
| Dependency | `/ca:add-dep "pkg"` | license, provenance, maintenance, CVE, and supply-chain review |
| Architecture decision | `/ca:adr "title"` | numbered, dated, user-attributed decision record |
| Commit | `/ca:commit` | the full commit gate and selective staging |
| Pull request | `/ca:pr` | cleared BLOCK findings and a draft PR, never a direct default-branch write |

Claude Code's catalog is [`plugins/ca/COMMANDS.md`](./plugins/ca/COMMANDS.md). Codex uses the
generated [`plugins/ca-codex/COMMANDS.md`](./plugins/ca-codex/COMMANDS.md), and Pi uses the generated
[`plugins/ca-pi/COMMANDS.md`](./plugins/ca-pi/COMMANDS.md). Current generated counts are `ca: 40`,
`ca-codex: 38`, and `ca-pi: 39`. Codex omits `statusline` and `prune`; Pi omits `statusline` and uses
native compaction for pruning.

<details>
<summary><strong>All 40 Claude Code commands</strong></summary>

### Implementation

| Command | Purpose |
|---|---|
| `/ca:feature "desc"` | Spec-driven feature; the only entry to new implementation |
| `/ca:sprint "goal"` | Autonomous spec-to-PR sprint with SMARTS-scored decisions |
| `/ca:fix "bug"` | Regression-test-first defect fix |
| `/ca:refactor "surface"` | Behavior-preserving restructure behind a parity gate |
| `/ca:debug "symptom"` | Investigate, identify root cause, then choose the owning lane |
| `/ca:chore <docs\|deps\|revert>` | Type-scaled non-behavioral lane |
| `/ca:spike "question"` | Throwaway exploration that never merges |

### Commit and ship

| Command | Purpose |
|---|---|
| `/ca:commit` | The only path to a commit |
| `/ca:pr` | Clear review findings and open or finish a pull request |
| `/ca:watch <PR>` | Watch hosted CI, diagnose red, offer merge on green |
| `/ca:review [path]` | Reviewer-fleet pass over the current diff |
| `/ca:checkpoint` | Lean periodic whole-codebase reviewer sweep |
| `/ca:tribunal [scope-path]` | Deep, resumable eleven-lens audit; never a routine gate |
| `/ca:release [--dry-run]` | Target-aware SemVer, changelog, and annotated tag |
| `/ca:add-dep "pkg"` | Vet license, provenance, maintenance, CVEs, and supply chain |

### Decisions

| Command | Purpose |
|---|---|
| `/ca:adr "title"` | Author a numbered, user-attributed ADR |
| `/ca:adr-status [--adr N]` | Inspect ADR health and supersession chains |
| `/ca:reconcile ["scope"]` | Reconcile architectural artifacts through SMARTS |
| `/ca:conflict "description"` | Stop work and surface an unresolvable rule conflict |
| `/ca:threat-model "scope"` | Optional lightweight STRIDE pass |

### Project and meta

| Command | Purpose |
|---|---|
| `/ca:decompose` | Greenfield interview that populates `.codearbiter/` |
| `/ca:create-context` | Brownfield source scout and context backfill |
| `/ca:init` | Scaffold the shared project-state store |
| `/ca:status` | Show stage, branch, tasks, questions, and recent overrides |
| `/ca:task` | The only sanctioned writer for `open-tasks.md` |
| `/ca:statusline` | Install or remove the Claude Code statusline |
| `/ca:doctor` | Prove interpreter, payload, hooks, cache, and live-fire behavior |
| `/ca:preview` | Read-only prediction of reviewers plus a state-free secret scan |
| `/ca:context-check` | Manual provenance-drift audit |
| `/ca:standup` | Read repo hygiene, then confirm safe cleanup actions one by one |
| `/ca:cleanup` | Finish an already-merged branch with ancestry proof |
| `/ca:new-skill "gap"` | Author a new skill only after proving the gap |
| `/ca:btw "question"` | Lightweight project Q&A with no state change |
| `/ca:override "reason"` | Logged, attributed bypass for one immediate action when the gate permits it; never H-18 |
| `/ca:audit [range]` | Assemble a dated governance packet |
| `/ca:metrics [--window N]` | Read-only override, small-lane, and confidence trends |
| `/ca:prune [status\|dry\|run\|audit\|on\|off]` | Inspect or trim transcript bulk |
| `/ca:commands` | Show the public catalog |

### Maintainer

| Command | Purpose |
|---|---|
| `/ca:dev ["note"]` | Enter the env-gated, logged maintainer override |
| `/ca:arbiter` | Exit dev mode and restore orchestration |

</details>

## Trust and host boundaries

The blocking enforcement core is local and Python-stdlib-only. It reads repository files and local
Git state. It does not send repository content to a codeArbiter account; there is no hosted
codeArbiter control plane.

Two background reads are separate from blocking evaluation:

- SessionStart may run a detached, read-only `git fetch` against the repository's configured remote
  to report hygiene state.
- A once-daily, fail-silent update check reads the public GitHub Releases API. It sends no repository
  content and never applies an update.

The optional `/ca:sprint --farm` preview is a distinct opt-in network feature. It sends byte-capped,
secret-redacted task context to the OpenAI-compatible endpoint you configure and is inert without
the flag and provider key.

See [Enforcement and Security](https://arbiterforge.github.io/codeArbiter/enforcement/) and the
[Hooks Reference](https://arbiterforge.github.io/codeArbiter/hooks/) for the exact event, read,
write, block, and network contract.

### Pi operational contract

`ca-pi` installs a rich footer in interactive parent sessions. The governance row appears only when
the repository is enabled and affirmatively trusted; rate-window telemetry is omitted rather than
fabricated. Execute mode asks before governed mutations and external side effects. Plan mode is
read-only except for the current canonical spec, plan, and plan ledger.

Background jobs are bounded and session-only, and are never restored from Pi session entries.
Unverified cleanup marks the manager unhealthy, blocks later launches, and points to `/ca-doctor`.
Footer, permission, plan, and background surfaces are parent-interactive only and never recurse into
hardened children.

The human-readable generated catalog is `plugins/ca-pi/SKILLS.md`. On a cold checkout, the platform
aggregate reports `missing_prerequisite` and directs the operator to
`npm --prefix plugins/ca-pi/tools ci --ignore-scripts`; it never installs dependencies on the
verification path.

## Feature Forge

<div align="center">
<img src="docs/feature-forge.webp" alt="A dark machined gate under controlled amber heat: preview work accumulating evidence before promotion." width="100%">
</div>

Preview features are built, tested, and shipping, but they remain opt-in and dormant until
real-world evidence earns stable status. A preview label never weakens a hard gate and never hides
spending or trust requirements.

| Feature | Opt-in | Promotion evidence still needed |
|---|---|---|
| `ca-pi` | install a pinned `ca-pi-v*` Git tag | diverse real repositories, providers, terminals, and workflows |
| Live transcript pruning | `CODEARBITER_PRUNE=dry` | real-session context savings and false-positive data |
| Pluggable execution farm | `/ca:sprint --farm` | per-task pass rates, cost, and gate-escape evidence |
| `ca-sandbox` | install the sibling plugin | real untrusted repositories and interactive `--with-claude` use |

The source-backed
[live Forge catalog](https://arbiterforge.github.io/codeArbiter/feature-forge/whats-in-the-forge/)
names every opt-in, off switch, dependency, trust boundary, and promotion signal.

The farm preview uses one checked-in `farm.js` backend across supported hosts. A Pi-native embedded
farm worker is a future spike, not a shipping dependency or second engine. `ca-pi` distributes as
the pinned Git tag plus the CI-published `npm:@arbiterforge/ca-pi` package (ADR-0029).

## Operator details

<details>
<summary><strong>Claude Code statusline</strong></summary>

Run `/ca:statusline` to install the optional token-aware statusline.

<div align="center">
<img alt="Annotated codeArbiter statusline" src="./site/public/diagrams/statusline.png" width="880">
</div>

Folder, Git state, rate limits, token use, cost, context headroom, model, effort, and session age
render globally. The governance row activates only in an enabled repository. Running
`/ca:statusline` again restores the previous statusline.

</details>

<details>
<summary><strong>Updates and configuration</strong></summary>

Update the Claude marketplace explicitly:

```text
/plugin marketplace update codearbiter
```

The operator-facing environment-variable catalog, defaults, accepted values, safety boundaries,
and verification steps live in the
[Configuration Reference](https://arbiterforge.github.io/codeArbiter/reference/configuration/).
Release notes are in the [Changelog](https://arbiterforge.github.io/codeArbiter/changelog/).

</details>

<details>
<summary><strong>Turn it off or uninstall it</strong></summary>

A repository without `.codearbiter/CONTEXT.md` carrying `arbiter: enabled` is dormant. Remove `ca`
with Claude Code's plugin manager, run `codex plugin remove ca-codex@codearbiter` for Codex, or use
`pi remove` with the pinned Git source for Pi. The repository-owned `.codearbiter/` record survives,
so another supported host can keep using it.

Follow [Uninstall and Disable](https://arbiterforge.github.io/codeArbiter/guides/uninstalling/) for
host-specific removal, pinning, and verification.

</details>

## Repository map

```text
.claude-plugin/marketplace.json     Claude marketplace
.agents/plugins/marketplace.json    Codex marketplace
core/                               canonical shared policy and generated surface
plugins/ca/                         Claude Code governance host
plugins/ca-codex/                   Codex governance host
plugins/ca-pi/                      Pi governance host (Feature Forge preview)
plugins/ca-sandbox/                 isolated local-Codespace plugin
site/                               Astro/Starlight documentation product
docs/                               architecture, parity runbooks, reports, and media
.codearbiter/                       this repository's own governed project state
```

`plugins/ca/` contains the always-on orchestrator, public commands, gated skills, dispatched agents,
hooks, and farm tooling. The [architecture docs](./docs/architecture.md), [parity ledger](./docs/parity.md),
and [full hook contract](./docs/hooks.md) are the maintainer entry points.

<details>
<summary><strong>OpenAI Build Week submission record</strong></summary>

codeArbiter predates OpenAI Build Week. The submitted work, added July 13 through July 21, 2026,
delivered the Pi host plus a corrective campaign over the shared governance core. It is consolidated
in [PR #313](https://github.com/arbiterForge/codeArbiter/pull/313) at verified implementation head
`ec64809c1b6c32f69e3d9787ab205f7bbd563d50`.

Codex was the primary development and orchestration environment. GPT-5.6 was used to design and
implement the Pi adapter, investigate live failures, review older paths, and consolidate corrections
across permissions, Windows process-tree cleanup, provenance, audit integrity, generated-source
drift, CI contracts, and documentation.

The final candidate passed the six Pi platform cells — both then-supported Pi versions on Windows,
macOS, and Linux (versions recorded in the linked artifacts), plus security analysis, CodeQL, shared-core contracts, generated-surface contracts, and
the repository's final verifier. Sanitized evidence:

- [`docs/reports/pi-support/promotion.md`](docs/reports/pi-support/promotion.md)
- [`docs/reports/pi-support/promotion.json`](docs/reports/pi-support/promotion.json)
- [`docs/pi-parity-testing.md`](docs/pi-parity-testing.md)

Judge quick start for the immutable candidate:

```text
pi install git:github.com/arbiterForge/codeArbiter@ec64809c1b6c32f69e3d9787ab205f7bbd563d50
pi list
pi config
```

Inspect the repository, grant project trust, start a fresh Pi session, then run `/ca-init` and
`/ca-doctor`.

</details>

## Project history

codeArbiter v2 is a ground-up rebuild of the earlier vendored `.agents/` framework as a native,
multi-host plugin system. The complete record is in [`CHANGELOG.md`](./CHANGELOG.md) and the
[site changelog](https://arbiterforge.github.io/codeArbiter/changelog/). The v1 implementation
remains available in early repository history.

## License and contributions

codeArbiter is licensed under the
[GNU Affero General Public License v3.0](./LICENSE) (AGPLv3). You may use, study, modify, and
redistribute it under those terms. AGPLv3 section 13 also applies when a modified version is run as a
network service.

The AGPLv3 transition applies from v2.6.0 forward. Earlier releases remain under the license they
shipped with.

**Open source.** codeArbiter is available under AGPLv3 for open-source use, free of charge.

**Commercial licensing.** SUaDtL retains the copyright and reserves the right to offer the project
under separate proprietary terms. Commercial licenses are not being offered at this time. Inquiries
may be made through GitHub if AGPLv3 does not fit a use case.

**Contributions.** Future community contributions require a Contributor License Agreement that
permits relicensing under AGPLv3 and proprietary terms. See [`CLA.md`](./CLA.md). The CLA is a
template pending legal review and is not yet in force.

<div align="center">
<sub>Built for Claude Code, Codex CLI, and Pi.</sub>
</div>
