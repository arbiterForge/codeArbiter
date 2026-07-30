---
title: Choose Your Host
description: "Pick the codeArbiter adapter for Claude Code, Codex, or Pi by comparing install path, command syntax, trust model, and current stability."
journey:
  level: Foundation
  time: 5 min
  outcome: "a host choice justified by stability, command syntax, trust, distribution, and status UI."
  prerequisites:
    - Know which coding host you already use
  proof: "You can name the adapter, command form, install channel, and trust step for your chosen host."
---

codeArbiter keeps one governance contract and one repository-owned `.codearbiter/` state store across
three supported hosts. Choose the adapter for the coding host you already use. Installing more than
one is optional; the checked-in project state remains shared.

## At a glance

| | Claude Code | Codex | Pi |
|---|---|---|---|
| **Adapter** | `ca` | `ca-codex` | `ca-pi` |
| **Status** | Stable | Stable | Feature Forge preview |
| **Command form** | `/ca:feature` | `$ca-feature` | `/ca-feature` |
| **Distribution** | codeArbiter marketplace | codeArbiter marketplace | Git tag |
| **Trust step** | Claude Code plugin trust | Review hooks, then start a fresh thread | Affirm project trust, then start a fresh session |
| **Project state** | Shared `.codearbiter/` | Same store | Same store |
| **Status UI** | Optional rich statusline | SessionStart briefing | Native rich footer |
| **Best fit** | Native Claude plugin agents and commands | Codex-native skills and structured hook verdicts | Pi users willing to run a promoted preview |

## Choose Claude Code when

You want the stable Claude-native plugin path, including packaged author/reviewer agents and the
optional statusline. Install commands and verification are on [Install: Claude Code](/getting-started/install/#claude-code).

## Choose Codex when

You want the same shared enforcement and project context inside Codex. Public skills use the
`$ca-<name>` form and the hook set is reviewed through `/hooks`. Install and verify through
[Install: Codex](/getting-started/install/#codex).

The dated [Claude Code + Codex verification record](/getting-started/claude-code-and-codex/) defines
the exact parity boundary and intentional host differences.

## Choose Pi when

You use Pi and accept a preview adapter with a green automated promotion matrix but less real-world
evidence than the two stable hosts. Pi uses Git tags, requires Node.js 22.19+, and will not activate
repository-aware behavior until project trust is affirmative.

Follow the dedicated [Pi install and trust guide](/getting-started/pi/).

## Use more than one host

Two adapters can open different checkouts of the same repository and read the same committed
context, decisions, tasks, and audit history. If two sessions mutate the exact same working tree at
the same time, sequence task-board and dev-mode changes; that race exists for same-host sessions too.
Append-only audit writes are designed for concurrent attribution.

For the complete surface matrix, platform requirements, network behavior, and preview flags, read
[Compatibility](/getting-started/compatibility/).
