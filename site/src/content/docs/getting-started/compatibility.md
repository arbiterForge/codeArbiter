---
title: Compatibility
description: "Platform, interpreter, and dependency requirements for codeArbiter: what the plugin itself needs, versus what's only required to develop the docs site."
---

codeArbiter's requirements are deliberately narrow: Claude Code or Codex, plus Python 3 on `PATH`.
Both hosts share `.codearbiter/`; see the
[Claude Code + Codex evidence](/getting-started/claude-code-and-codex/) for the verified boundary.

## Requirements Matrix

| Requirement | What's needed | Notes |
|---|---|---|
| **Claude Code** | Any version with plugin support | `plugin.json` states no explicit minimum version; the plugin uses standard hook events (`SessionStart`, `PreToolUse`, `PostToolUse`) and the plugin/marketplace install commands documented in [Install](/getting-started/install/). |
| **Codex** | Minimum 0.134.0; live-verified on 0.144.1 | `ca-codex` uses one OS-specific handler per event and a Codex adapter that converts the shared guard verdict to structured deny output. Trust the hook set through `/hooks`. |
| **Python** | Python 3, stdlib only, resolvable as `python3` **or** `python` on `PATH` | Every hook is registered twice in `hooks.json` — once under `python3`, once under a `python3 -c "" \|\| python` fallback — so it runs on a machine where only `python` resolves. No third-party Python packages are ever installed or imported (ADR-0004: database-free, stdlib-only architecture). |
| **Operating system** | Windows, macOS, or Linux | Hooks are pure Python stdlib and carry no OS-specific code path beyond the interpreter-name fallback above. The `.git/hooks` backstop shim is a POSIX `sh` script; on Windows this runs under Git for Windows' bundled `sh.exe`, which ships with every standard Git install. |
| **git** | Any reasonably current git | Required regardless of codeArbiter — the plugin reads repo state (`git config user.email`, branch, diff) via subprocess calls to your existing `git` binary, and installs the `.git/hooks` backstop through it. |
| **Node.js** | Not required for the plugin | Node is only needed to build or develop **this documentation site** (`site/`) and the optional pluggable-execution-farm TypeScript dispatcher (`plugins/ca/tools/`) if you use `/ca:sprint --farm`. Neither is a runtime dependency of the enforcement hooks themselves. |
| **Network access** | Not required for enforcement | See [Network Calls](#network-calls) below — the gate-enforcement hook chain makes zero network calls; two clearly-scoped, opt-in-by-default exceptions exist outside that chain. |

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
