---
title: Opt a Repository In
description: "Enable codeArbiter enforcement on an existing or new repository: scaffold .codearbiter/ and set the activation flag."
---

The plugin installs once, globally. Enabling enforcement is a per-repo step you run once inside each repository you want covered. Complete the [plugin install](/getting-started/install/) before starting here.

**You will need:** Python 3 on your `PATH`, `git config user.email` set, and the plugin installed.

<figure class="ca-diagram">
  <img
    src="/codeArbiter/diagrams/lane-opt-in.svg"
    alt="The /ca:init lane in two rows: Commands (/ca:init, which forks to /ca:create-context for existing code or /ca:decompose for a new project) and Skills (create-context backs the first path, decompose the second). Two connectors fork from /ca:init, one to each path."
    loading="lazy"
    width="920"
    height="190"
  />
  <figcaption>The <code>/ca:init</code> lane by piece type: commands (gold) and the skills behind them (violet). Init forks to one context-builder path: create-context for existing code, decompose for a new project.</figcaption>
</figure>

## 1. Scaffold the State Store

In a Claude Code session with the target repository open, run:

```text
/ca:init
```

`/ca:init` creates `.codearbiter/` at the repo root and routes to the right context builder for your situation. If the directory already exists, it will not overwrite what is there.

## 2. Complete the Context Build

`/ca:init` routes based on whether the repository has existing code:

| Your situation | Routed to | What it does |
|---|---|---|
| Existing codebase | `/ca:create-context` | Scouts the source and back-fills `.codearbiter/` |
| New project, no code yet | `/ca:decompose` | A layered interview that builds `.codearbiter/` from scratch |

Let the routed command finish before moving on. It populates the context files the enforcement gates read at commit time.

## 3. Confirm the Activation Flag

Open `.codearbiter/CONTEXT.md` and confirm the leading frontmatter:

```yaml
---
arbiter: enabled
---
```

Two things to verify:

- The frontmatter block opens on line 1 and closes with a matching `---`.
- `arbiter: enabled` appears inside that block.

A file with no frontmatter at all is silently dormant. A frontmatter block that opens but never closes surfaces a malformed-state error rather than treating the repo as disabled.

Once the flag is present and the block is closed, the next Claude Code session opens with the orchestrator active and every gate armed.

For the full catalog of what the gates enforce and how they fail, see [Enforcement & Security](/enforcement/).
