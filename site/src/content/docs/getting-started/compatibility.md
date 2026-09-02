---
title: Compatibility
description: "Platform, interpreter, and dependency requirements for codeArbiter: what the plugin itself needs, versus what's only required to develop the docs site."
journey:
  level: "Reference"
  time: "Lookup"
  outcome: "Confirm host, Python, platform, and optional-feature prerequisites before installation."
  prerequisites: []
  proof: "Your selected host and optional features meet every requirement in the relevant row."
---

codeArbiter's requirements are deliberately narrow: Claude Code, Codex, or Pi, plus Python 3 on
`PATH`. All three hosts share `.codearbiter/`; see the
[Claude Code + Codex evidence](/getting-started/claude-code-and-codex/) for the verified boundary
and the [Pi install page](/getting-started/pi/) for the `ca-pi` install flow.

## Requirements Matrix

| Requirement | What's needed | Notes |
|---|---|---|
| **Claude Code** | Any version with plugin support | `plugin.json` states no explicit minimum version; the plugin uses standard hook events (`SessionStart`, `PreToolUse`, `PostToolUse`) and the plugin/marketplace install commands documented in [Install](/getting-started/install/). |
| **Codex** | Minimum 0.143.0; live-verified on 0.144.1 | `ca-codex` uses one OS-specific handler per event and a Codex adapter that converts the shared guard verdict to structured deny output. Trust the hook set through `/hooks`. |
| **Pi** | 0.80.5 or 0.84.1 (this release line) | `ca-pi` is a Feature Forge `preview`, available and welcomed for real use while broader testing continues before stable status or a claim of 100% validation. Install it with `pi install npm:@arbiterforge/ca-pi`, or pin the reproducible Git tag: `pi install git:github.com/arbiterForge/codeArbiter@ca-pi-v<version>`. Also requires Node.js 22.19+. Requires an affirmative project-trust decision before repository-aware startup. Its human-readable generated catalog is `plugins/ca-pi/SKILLS.md`. See [Install for Pi](/getting-started/pi/). |
| **Python** | Python 3, stdlib only, available under the interpreter name your adapter registers | No minimum Python 3 minor is currently declared. CI exercises the runner's current Python 3 on Windows, macOS, and Linux; focused Windows hook evidence also covers CPython 3.10, 3.12, and 3.14. Claude Code carries its documented `python3`/`python` fallback shape. Codex uses OS-specific `command` and `commandWindows` handlers and fails loud if its selected interpreter is absent. Pi installs final TypeScript wrappers first, then blocks mutating calls with an interpreter breadcrumb until the Python bridge is healthy. No adapter treats that state as active enforcement. No third-party Python packages are installed or imported (ADR-0004). |
| **Operating system** | Native Windows, macOS, or Linux runtime with a checkout created and used by that runtime's Git | The `.git/hooks` backstop is a POSIX `sh` script. On Windows, Git for Windows runs it with its bundled `sh.exe`. Git Bash is part of that native Windows cell and is not WSL. Windows is also a promoted, tested platform for `ca-pi`; see [Windows notes](/getting-started/pi/#windows). Linked-worktree support uses Git's default `<main>/.git/worktrees` storage layout. See [Git runtime boundary](#git-runtime-boundary) for layout and mixed-runtime exclusions. |
| **git** | A Git binary that provides `rev-parse --git-path hooks`, `rev-parse --path-format=absolute --git-dir --git-common-dir`, and `git hook run` | codeArbiter asks the selected Git binary for its effective hook and shared-worktree paths, then doctor uses that same binary for a harmless managed `pre-push` live-fire probe with empty input. That binary's accepted `core.hooksPath` grammar is authoritative, including its expansion of values such as `~`, `%(prefix)`, absolute paths, and relative paths. The project does not maintain a second parser or claim a numeric Git version floor that has not been tested. |
| **Node.js** | Not required for Claude Code or Codex | Node is required for `ca-pi` (22.19+) and is only otherwise needed to build or develop **this documentation site** (`site/`) and the optional pluggable-execution-farm TypeScript dispatcher (`plugins/ca/tools/`) if you use `/ca:sprint --farm`. Node is not a runtime dependency of the Claude Code/Codex enforcement hooks themselves. |
| **Network access** | Not required for enforcement | See [Network Calls](#network-calls) below. The gate-enforcement hook chain makes zero network calls; two clearly-scoped, opt-in-by-default exceptions exist outside that chain. |

## Git Runtime Boundary

Hook registration and linked-worktree metadata are supported when one native runtime owns the
checkout and continues to use it with that runtime's Git, Python, and hook shell.

| Repository use | Status | Evidence and boundary |
|---|---|---|
| Windows checkout and linked worktrees created and used by Git for Windows | Supported with Git's default worktree layout | Actual Git for Windows tests resolve and execute managed hooks from both the primary checkout and a linked worktree. Both native absolute and native relative worktree-admin pointers resolve to the primary marker root. Git for Windows' bundled `sh.exe` is the hook shell. A live Git 2.55.0 probe also resolved a primary and linked worktree through a localhost UNC share after that path was explicitly trusted by Git's `safe.directory` policy; without Git trust, resolution fails closed. This is not a general claim for every remote SMB server. |
| Linux checkout and linked worktrees created and used by native Linux Git | Supported with Git's default worktree layout | The hook suite runs on the Ubuntu CI cell. Paths and registry entries remain in one native dialect. |
| macOS checkout and linked worktrees created and used by native macOS Git | Supported with Git's default worktree layout | The hook suite runs on the macOS CI cell. Paths and registry entries remain in one native dialect. |
| WSL-owned checkout and worktrees used only by WSL | Not separately verified | This resembles the native Linux cell, but WSL is not a named, proven product cell yet. Do not promote that inference to a support claim without WSL-specific end-to-end evidence. |
| One physical repository or shared `.git` alternated between Windows Git and WSL Git | Unsupported | Registry paths, generated shell paths, and trusted executable identities use one runtime's path dialect. codeArbiter does not translate or maintain parallel runtime identities. |
| Windows-created linked worktree used through WSL, or the reverse | Unsupported | Foreign `.git` pointer paths are rejected rather than treated as relative local paths. In the directly tested Windows-to-WSL direction, WSL Git itself rejects the foreign worktree metadata before codeArbiter runs. |
| Linked worktree backed by `git init --separate-git-dir` | Unsupported | Git can resolve this layout, but it may not retain the user-supplied primary as the main worktree. codeArbiter escalates only when both the linked checkout and Git's reported main candidate own real `CONTEXT.md` files that independently satisfy the canonical activation parser; ordinary separate storage lacks that identity and marker writes stay local. A storage directory deliberately carrying its own enabled identity is inside the local-filesystem trust boundary, not a promoted support cell. |

`core.hooksPath` follows the selected Git binary, not a codeArbiter-specific subset. Doctor checks
the effective directory reported by that binary, requires both current executable managed shims
there, requires at least one live registered enforcer, and asks Git to run the managed `pre-push`
shim with empty input before reporting the backstop healthy.

## Host Differences

| Surface | Claude Code | Codex | Pi |
|---|---|---|---|
| Entry commands | `/ca:<name>` | `$ca-<name>` | `/ca-<name>` (generated alias); `/skill:ca-<name>` fallback |
| Plugin | `ca` | `ca-codex` | `ca-pi` (Feature Forge `preview`) |
| Distribution | Marketplace + npm-backed release | Marketplace + npm-backed release | Git tags (`ca-pi-v<version>`) + npm (`@arbiterforge/ca-pi`) |
| Trust/approval | Claude Code plugin trust flow | Review through `/hooks`; start a fresh thread | Affirmative project-trust decision, then a fresh session |
| Statusline / footer | Available | No statusline surface | Rich footer in every interactive parent repository; governance row only when enabled and affirmatively trusted; rate-window telemetry is omitted |
| Mutation permission | Host permission flow plus gates | Codex approval plus gates | Execute mode asks before governed mutations or external side effects; hard blocks deny first |
| Plan mode | Host plan workflow | Read-only collaboration mode | Plan mode is read-only except for the current canonical spec, plan, and plan ledger |
| Background jobs | Host managed | Host managed | Bounded session-only jobs, never restored from Pi session entries; unverified cleanup blocks later launches with `/ca-doctor` direction |
| `/ca:sprint --farm` | `preview`, shared `farm.js` backend | `preview`, shared `farm.js` backend | `preview`, same shared `farm.js` backend through the trusted parent extension; no Pi-native farm engine |
| Subagent/child dispatch | Plugin agents dispatched directly | Current hosts provide agent threads: codeArbiter loads the role charter and retains the thread receipt; older hosts may fall back inline, but context creation blocks without isolated scouts | Fresh child Pi processes via the parent-only `codearbiter_dispatch` EXEC tool; single/chain/parallel modes share bounded depth, concurrency, timeout, cancellation, and process-tree cleanup |
| Transcript pruning / compaction | Claude transcript-pruning engine | No transcript pruning; host-neutral staleness warning | Native Pi compaction event; codeArbiter does not rewrite Pi session JSONL |
| Project state | Shared `.codearbiter/` store | Shared `.codearbiter/` store | Shared `.codearbiter/` store |

The full exception ledger with status and evidence for every host delta lives in
[`docs/parity.md`](https://github.com/arbiterForge/codeArbiter/blob/main/docs/parity.md).

:::note[Maintainer verification only]
When running Pi's repository-level platform aggregate, a tools workspace without its resolved
Vitest binary returns `missing_prerequisite` before fixtures start. Maintainers can prepare that
workspace with `npm --prefix plugins/ca-pi/tools ci --ignore-scripts`; the verification path never
installs dependencies itself. This setup is not required to install or use codeArbiter.
:::

Footer, permission UI, plan UI, and background jobs are parent-interactive only and absent from
JSON, RPC, print, and hardened children.

## Prerequisites Checklist

Confirm both before installing, per [Install](/getting-started/install/):

- **Python 3 on `PATH`.** Without it, Claude Code can be inactive, Codex's hook handler fails loud,
  and Pi blocks mutation. Run the host-native doctor command and require a healthy interpreter and
  live-fire row before treating the adapter as active.
- **`git config user.email` set.** Overrides and ADRs are attributed to this identity; an unset email
  is asked for once, interactively, rather than silently defaulting.

## Network Calls

Grepping every file under `plugins/ca/hooks/` for network-capable stdlib usage (`urllib`, `http.client`,
`socket`) turns up exactly one file that actually opens a connection: `_updatelib.py`. (`_ledgerlib.py`
matches a naive text search only because it uses the English word "requests" to mean tool-call
records. It imports nothing network-capable.)

- **The gate-enforcement hooks** (`pre-bash.py`, `pre-write.py`, `pre-edit.py`, `pre-read.py`,
  `post-write-edit.py`, and `session-start.py`'s activation/briefing logic) make **zero** network
  calls. Every check is a local file read, a local `git` subprocess call against your own repo, or an
  in-process regex/parse. This is the enforcement chain compatibility and security actually depend on.
- **The update-available notifier** (`_updatelib.py`) is a separate, non-blocking mechanism: a
  best-effort, once-a-day, fail-silent, unauthenticated HTTPS `GET` against GitHub's public Releases
  API (`api.github.com`), run as a **detached background process** off the `SessionStart` hot path so
  a slow or unreachable network never delays a session. It only ever displays a one-line notice; it
  never applies an update. This ships on by default but is easy to make fully offline: see
  [Staying up to date](https://github.com/arbiterForge/codeArbiter#staying-up-to-date) in the project
  README for the opt-out.
- **The pluggable execution farm** (`/ca:sprint --farm`, opt-in, requires `FARM_API_KEY`) sends
  byte-capped, secret-redacted task context to an OpenAI-compatible HTTP provider you configure. This
  is a separate, explicitly opt-in feature, not part of the gate chain, and inert unless you pass
  `--farm`.

No hook writes anything off your machine as a side effect of enforcement. `docs/hooks.md` documents the
same invariant per-hook, plus the one local, read-only `git fetch` `session-start.py` runs in the
background against your own configured remote (the repo-hygiene briefing).

## Third-Party Dependencies

Zero, for the plugin itself. `plugins/ca/hooks/*.py` import only the Python standard library: no
`pip install`, no `requirements.txt`, no compiled binaries (ADR-0004). The one TypeScript toolchain in
the repo, `plugins/ca/tools/` (the farm dispatcher), carries its own `devDependencies` for its own
build and test. Those are irrelevant to whether the enforcement hooks run, since the hooks never
import from that package.

The docs site (`site/`) has its own, larger `package.json` (Astro, Starlight, vitest). That's a
dependency surface for **building this website**, never for using the plugin.
