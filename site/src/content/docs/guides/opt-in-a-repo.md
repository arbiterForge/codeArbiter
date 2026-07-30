---
title: Opt a Repository In
description: "Enable codeArbiter enforcement on an existing or new repository: scaffold .codearbiter/ and set the activation flag."
journey:
  level: Foundation
  time: 10–20 min
  outcome: "a repository-owned state store populated for the project and an activation flag that all supported hosts recognize."
  prerequisites:
    - A supported host adapter installed
    - Python 3 on PATH
    - Git identity configured
  proof: "A fresh session shows the startup briefing, and doctor completes its harmless live-fire probe."
---

The repository opt-in is shared by Claude Code, Codex, and Pi. Run `/ca:init` in Claude Code,
`$ca-init` in Codex, or `/ca-init` in Pi; all three create or observe the same `.codearbiter/`
directory. See the [Claude Code + Codex evidence](/getting-started/claude-code-and-codex/) for a
worked mixed-host example, and [Pi](/getting-started/pi/) for Pi's parent-process trust boundary.

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

Open the target repository in one supported host and invoke its native command:

| Host | Command |
|---|---|
| Claude Code | `/ca:init` |
| Codex | `$ca-init` |
| Pi | `/ca-init` |

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

Once the flag is present and the block is closed, the next supported-host session opens with the
orchestrator active and every gate armed.

## 4. Restart and Prove Enforcement

Close the current session and open a fresh one in the same repository. The first response should
include the codeArbiter startup briefing: stage, blocking questions, in-flight tasks, and a pointer
to the command catalog.

Then run doctor using the same host syntax convention:

| Host | Command |
|---|---|
| Claude Code | `/ca:doctor` |
| Codex | `$ca-doctor` |
| Pi | `/ca-doctor` |

Doctor's harmless H-03 probe should be blocked. If the briefing is absent or the probe executes,
the repository is not proven active. Follow [Troubleshooting](/guides/troubleshooting/) before
starting governed work.

## Common Stops

| Symptom | Meaning | Recovery |
|---|---|---|
| Init reports an existing `.codearbiter/` directory | Project state already exists | Inspect it; do not overwrite another session's context |
| The repo has source but no initialized marker | Brownfield context is incomplete | Complete the routed create-context flow |
| Frontmatter opens but does not close | Activation state is malformed | Repair the frontmatter structure, then restart |
| Fresh session has no briefing | Plugin trust, interpreter, cache, or activation failed | Run doctor and use the symptom table in Troubleshooting |

For the full catalog of what the gates enforce and how they fail, see [Enforcement & Security](/enforcement/).
