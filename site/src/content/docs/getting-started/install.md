---
title: Install
description: "Install codeArbiter for Claude Code or Codex, opt into the shared .codearbiter/ store, and verify enforcement."
---

codeArbiter installs once per host and enables separately per repository. Claude Code uses `ca`;
Codex uses `ca-codex`. Both enforce the same `.codearbiter/` project store. The
[Claude Code + Codex evidence](/getting-started/claude-code-and-codex/) defines the verified boundary.

## Prerequisites

Confirm both before installing:

- **Python 3 on `PATH`**: every enforcement hook is pure Python. Without it, the gates and the session-startup injection silently do not run.
- **`git config user.email` set**: overrides and ADRs are attributed to this identity.

## 1. Install for Your Host

### Claude Code

codeArbiter self-hosts a single-plugin marketplace from its GitHub repo. In any Claude Code session, run both commands:

```text
/plugin marketplace add arbiterForge/codeArbiter
/plugin install ca@codearbiter
```

Hooks, commands, and agents load automatically. All commands resolve under the `/ca:` namespace.

Verify an opted-in repository with `/ca:doctor`.

### Codex

The public commands are **available after the Codex-support release** reaches the default branch:

```text
codex plugin marketplace add arbiterForge/codeArbiter
codex plugin add ca-codex@codearbiter
```

Before that release, clone this repository, run `codex plugin marketplace add .` from its root,
then run `codex plugin add ca-codex@codearbiter`. Open `/hooks`, trust the handlers, and start a
fresh thread. Verify an opted-in repository with `$ca-doctor`.

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
