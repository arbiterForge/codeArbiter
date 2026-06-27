---
title: Install
description: "Add the ca plugin to Claude Code and opt a repository into enforcement: prerequisites, plugin install, /ca:init, and the arbiter: enabled activation flag."
---

codeArbiter is a Claude Code plugin. It installs once, globally. Enabling it for a repository is a separate, per-repo step.

## Prerequisites

Confirm both before installing:

- **Python 3 on `PATH`**: every enforcement hook is pure Python. Without it, the gates and the session-startup injection silently do not run.
- **`git config user.email` set**: overrides and ADRs are attributed to this identity.

## 1. Add the marketplace and install the plugin

codeArbiter self-hosts a single-plugin marketplace from its GitHub repo. In any Claude Code session, run both commands:

```text
/plugin marketplace add arbiterForge/codeArbiter
/plugin install ca@codearbiter
```

Hooks, commands, and agents load automatically. All commands resolve under the `/ca:` namespace.

## 2. Scaffold the repo state store

Installing the plugin enforces nothing. To activate codeArbiter for a repository, open that repo in Claude Code and run:

```text
/ca:init
```

`/ca:init` scaffolds `.codearbiter/` at the repo root and routes to the right context populator for your situation:

| You have | Routed to | What it does |
|---|---|---|
| An existing codebase | `/ca:create-context` | Back-fills `.codearbiter/` from the source already there |
| A new project, no code yet | `/ca:decompose` | A layered interview that scaffolds `.codearbiter/` from scratch |

## 3. Confirm the activation flag

`/ca:init` writes `arbiter: enabled` into `.codearbiter/CONTEXT.md` frontmatter. This is the single activation mechanism. Enforcement is off until this flag is present; the plugin install alone changes nothing.

```yaml
---
arbiter: enabled
---
```

To verify, open `.codearbiter/CONTEXT.md` and confirm `arbiter: enabled` appears in a properly closed YAML frontmatter block (opening `---` on line 1, followed by a closing `---`). A file with no frontmatter at all is silently dormant. A frontmatter block that opens but never closes surfaces a malformed-state error.

Once the flag is set, the next session opens with the orchestrator active.

The [Enforcement & Security](/enforcement/) page covers which gates are blocking versus advisory and how the fail-loud posture works.
