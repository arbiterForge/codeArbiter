---
title: Install
description: "Install codeArbiter for Claude Code, Codex, or Pi, opt into the shared .codearbiter/ store, and verify enforcement."
---

codeArbiter ships four sibling plugins from one marketplace: three governance hosts — `ca` (Claude
Code), `ca-codex` (Codex), and `ca-pi` (Pi) — plus `ca-sandbox`, an infrastructure plugin unrelated to
gate enforcement (see [ca-sandbox](/guides/ca-sandbox/)). This page covers Claude Code and Codex
install; Pi has its own dedicated walkthrough at [Install for Pi](/getting-started/pi/) (a different
distribution model — Git-only, no npm release). All three governance hosts enforce the same
`.codearbiter/` project store. The
[Claude Code + Codex evidence](/getting-started/claude-code-and-codex/) defines the verified boundary,
and [Compatibility](/getting-started/compatibility/) has the full host-differences matrix.

## Prerequisites

Confirm both before installing:

- **Python 3 on `PATH`**: every enforcement hook is pure Python. Without it, the gates and the
  session-startup injection silently do not run. Verify with:

  ```sh
  python3 --version || python --version
  ```

  Either succeeding is enough — hooks are registered under both names, falling back to whichever
  resolves.

- **`git config user.email` set**: overrides and ADRs are attributed to this identity. Verify with:

  ```sh
  git config user.email
  ```

  If that prints nothing, set one with `git config --global user.email "you@example.com"` (or
  `--local` for just this repo) before installing.

## 1. Install for Your Host

### Claude Code

codeArbiter self-hosts a multi-plugin marketplace from its GitHub repo. In any Claude Code session, run both commands:

```text
/plugin marketplace add arbiterForge/codeArbiter
/plugin install ca@codearbiter
```

Claude Code's own plugin trust flow governs whether the hooks fire at all — the standard prompt you
see when installing any plugin that registers hooks. Approve it once at install time (no separate
per-hook approval step, unlike Codex's `/hooks` review) and hooks, commands, and agents load
automatically from then on. All commands resolve under the `/ca:` namespace.

**Verify the install succeeded** before moving on. Run `/plugin list` (or `/plugin`) and confirm `ca`
appears as installed from the `codearbiter` marketplace; then verify enforcement itself with
`/ca:doctor` once the target repository is opted in (step 2 below).

### Codex

The public commands are **available now** and were verified against release `v2.8.13` with
`ca-codex 0.2.4`:

```text
codex plugin marketplace add arbiterForge/codeArbiter
codex plugin add ca-codex@codearbiter
```

To develop against an unpublished checkout, clone this repository, run
`codex plugin marketplace add .` from its root, then run
`codex plugin add ca-codex@codearbiter`. Open `/hooks`, trust the handlers, and start a fresh thread.
Verify an opted-in repository with `$ca-doctor`.

### Pi

Pi is a third governance host, `ca-pi`, distributed Git-only (no npm release) with its own version
line and prerequisites. It is not covered here — see [Install for Pi](/getting-started/pi/) for the
full flow, including `pi install git:arbiterForge/codeArbiter@ca-pi-v<version>` and the project-trust
step Pi requires before it activates.

## 2. Scaffold and Activate the Repo

Installing a plugin enforces nothing. In the target repository, run `/ca:init` in Claude Code or
`$ca-init` in Codex:

```text
/ca:init
$ca-init
```

The init command scaffolds `.codearbiter/` at the repo root, routes to the right context populator,
and writes the `arbiter: enabled` activation flag. Neither host needs the other plugin installed to
use existing project state. See [Opt a Repository In](/guides/opt-in-a-repo/) for the full walkthrough.

Once the flag is present, the next session opens with the orchestrator active.

The [Enforcement & Security](/enforcement/) page covers which gates are blocking versus advisory and how the fail-loud posture works.

## Updating codeArbiter

`claude plugin update` (and its Codex equivalent) can no-op on an unchanged marketplace version
string, leaving a stale cached payload behind even when you expect a new one. The clean path is
uninstall, then reinstall:

```text
claude plugin uninstall ca
/plugin marketplace add arbiterForge/codeArbiter
/plugin install ca@codearbiter
```

(Substitute `codex plugin remove ca-codex@codearbiter` / `codex plugin add ca-codex@codearbiter` for
Codex.) `.codearbiter/` in every repository is untouched by either uninstall or reinstall — only the
plugin payload moves. `/ca:doctor` reports the currently cached version so you can confirm the update
actually landed; see its [remediation ladder](/reference/commands/doctor/) if it still looks stale.
Pi updates differently — see [Uninstall, Upgrade, and Version Pinning](/getting-started/pi/#uninstall-upgrade-and-version-pinning).
