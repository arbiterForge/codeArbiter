---
title: Compatibility
description: "Platform, interpreter, and dependency requirements for codeArbiter: what the plugin itself needs, versus what's only required to develop the docs site."
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
| **Pi** | Pi 0.80.5 or Pi 0.80.10 (this release line) | `ca-pi` is Git-only: `pi install git:arbiterForge/codeArbiter@ca-pi-v<version>`. Also requires Node.js 22.19+. Requires an affirmative project-trust decision before repository-aware startup. See [Install for Pi](/getting-started/pi/). |
| **Python** | Python 3, stdlib only, resolvable as `python3` **or** `python` on `PATH` | Every hook is registered twice in `hooks.json` — once under `python3`, once under a `python3 -c "" \|\| python` fallback — so it runs on a machine where only `python` resolves. No third-party Python packages are ever installed or imported (ADR-0004: database-free, stdlib-only architecture). On Pi, a missing interpreter blocks mutating calls and surfaces an interpreter breadcrumb rather than failing silently. |
| **Operating system** | Windows, macOS, or Linux | Hooks are pure Python stdlib and carry no OS-specific code path beyond the interpreter-name fallback above. The `.git/hooks` backstop shim is a POSIX `sh` script; on Windows this runs under Git for Windows' bundled `sh.exe`, which ships with every standard Git install. Windows is also a promoted, tested platform for `ca-pi`; see [Windows notes](/getting-started/pi/#windows). |
| **git** | Any reasonably current git | Required regardless of codeArbiter — the plugin reads repo state (`git config user.email`, branch, diff) via subprocess calls to your existing `git` binary, and installs the `.git/hooks` backstop through it. |
| **Node.js** | Not required for Claude Code or Codex | Node is required for `ca-pi` (22.19+) and is only otherwise needed to build or develop **this documentation site** (`site/`) and the optional pluggable-execution-farm TypeScript dispatcher (`plugins/ca/tools/`) if you use `/ca:sprint --farm`. Node is not a runtime dependency of the Claude Code/Codex enforcement hooks themselves. |
| **Network access** | Not required for enforcement | See [Network Calls](#network-calls) below — the gate-enforcement hook chain makes zero network calls; two clearly-scoped, opt-in-by-default exceptions exist outside that chain. |

## Host Differences

| Surface | Claude Code | Codex | Pi |
|---|---|---|---|
| Entry commands | `/ca:<name>` | `$ca-<name>` | `/ca-<name>` (generated alias); `/skill:ca-<name>` fallback |
| Plugin | `ca` | `ca-codex` | `ca-pi` |
| Distribution | Marketplace + npm-backed release | Marketplace + npm-backed release | Git tags only (`ca-pi-v<version>`); no npm release |
| Trust/approval | Claude Code plugin trust flow | Review through `/hooks`; start a fresh thread | Affirmative project-trust decision, then a fresh session |
| Statusline | Available | No statusline surface | No statusline; `ctx.ui.setStatus` reports compact governance state but does not replace Pi's footer |
| `/ca:sprint --farm` | `preview`, shared `farm.js` backend | `preview`, shared `farm.js` backend | `preview`, same shared `farm.js` backend through the trusted parent extension; no Pi-native farm engine |
| Subagent/child dispatch | Plugin agents dispatched directly | Roles run inline (packaging pending) | Fresh child Pi processes via the parent-only `codearbiter_dispatch` EXEC tool; single/chain/parallel modes share bounded depth, concurrency, timeout, cancellation, and process-tree cleanup |
| Transcript pruning / compaction | Claude transcript-pruning engine | No transcript pruning; host-neutral staleness warning | Native Pi compaction event; codeArbiter does not rewrite Pi session JSONL |
| Project state | Shared `.codearbiter/` store | Shared `.codearbiter/` store | Shared `.codearbiter/` store |

The full exception ledger with status and evidence for every host delta lives in
[`docs/parity.md`](https://github.com/arbiterForge/codeArbiter/blob/main/docs/parity.md).

## Prerequisites Checklist

Confirm both before installing, per [Install](/getting-started/install/):

- **Python 3 on `PATH`.** Without it, the gates and the session-startup injection silently do not
  run — <kbd>/ca:doctor</kbd> catches this as an interpreter-resolution failure.
- **`git config user.email` set.** Overrides and ADRs are attributed to this identity; an unset email
  is asked for once, interactively, rather than silently defaulting.

## Network Calls

Grepping every file under `plugins/ca/hooks/` for network-capable stdlib usage (`urllib`, `http.client`,
`socket`) turns up exactly one file that actually opens a connection: `_updatelib.py`. (`_ledgerlib.py`
matches a naive text search only because it uses the English word "requests" to mean tool-call
records — it imports nothing network-capable.)

- **The gate-enforcement hooks** — `pre-bash.py`, `pre-write.py`, `pre-edit.py`, `pre-read.py`,
  `post-write-edit.py`, and `session-start.py`'s activation/briefing logic — make **zero** network
  calls. Every check is a local file read, a local `git` subprocess call against your own repo, or an
  in-process regex/parse. This is the enforcement chain compatibility and security actually depend on.
- **The update-available notifier** (`_updatelib.py`) is a separate, non-blocking mechanism: a
  best-effort, once-a-day, fail-silent, unauthenticated HTTPS `GET` against GitHub's public Releases
  API (`api.github.com`), run as a **detached background process** off the `SessionStart` hot path so
  a slow or unreachable network never delays a session. It only ever displays a one-line notice; it
  never applies an update. This ships on by default but is easy to make fully offline — see
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

Zero, for the plugin itself. `plugins/ca/hooks/*.py` import only the Python standard library — no
`pip install`, no `requirements.txt`, no compiled binaries (ADR-0004). The one TypeScript toolchain in
the repo, `plugins/ca/tools/` (the farm dispatcher), carries its own `devDependencies` for its own
build and test — those are irrelevant to whether the enforcement hooks run, since the hooks never
import from that package.

The docs site (`site/`) has its own, larger `package.json` (Astro, Starlight, vitest) — that's a
dependency surface for **building this website**, never for using the plugin.
