---
title: Install
description: "Add the ca plugin to Claude Code and opt a repository into enforcement: prerequisites, plugin install, /ca:init, and the arbiter: enabled activation flag."
---

codeArbiter is a Claude Code plugin. It installs once, globally. Enabling it for a repository is a separate, per-repo step.

## Prerequisites

Confirm both before installing:

- **Python 3 on `PATH`**: every enforcement hook is pure Python. Without it, the gates and the session-startup injection silently do not run.
- **`git config user.email` set**: overrides and ADRs are attributed to this identity.

## 1. Add the Marketplace and Install the Plugin

codeArbiter self-hosts a single-plugin marketplace from its GitHub repo. In any Claude Code session, run both commands:

```text
/plugin marketplace add arbiterForge/codeArbiter
/plugin install ca@codearbiter
```

Hooks, commands, and agents load automatically. All commands resolve under the `/ca:` namespace.

## 2. Scaffold and Activate the Repo

Installing the plugin enforces nothing. To activate codeArbiter for a repository, open that repo in Claude Code and run:

```text
/ca:init
```

`/ca:init` scaffolds `.codearbiter/` at the repo root, routes to the right context populator, and — once that populator finishes — writes the `arbiter: enabled` activation flag that turns enforcement on. See [Opt a Repository In](/guides/opt-in-a-repo/) for the full walkthrough, including the two populator paths and how to confirm the flag is set correctly.

Once the flag is present, the next session opens with the orchestrator active.

The [Enforcement & Security](/enforcement/) page covers which gates are blocking versus advisory and how the fail-loud posture works.
