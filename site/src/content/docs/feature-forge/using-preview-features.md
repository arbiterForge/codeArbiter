---
title: Using Features Still in the Forge
description: "How to turn on a codeArbiter preview feature, what to expect while it is in the Forge, and how it graduates to stable."
---

Features in the [Feature Forge](/feature-forge/overview/) are real and usable, but they stay off
until you ask for them. This guide covers how to turn one on, what to expect while it is in
preview, and how it eventually graduates.

## 1. Find What's Available

Check [What's in the Forge](/feature-forge/whats-in-the-forge/) for the current preview features.
Each is also marked with a <span class="ca-badge" data-kind="preview">preview</span> badge on its
reference page.

## 2. Turn It On

Preview features are opt-in by design; a new plugin version never switches one on for you. How you
opt in depends on the feature:

- **A preview flag** (for example `--farm` on `/ca:sprint`) is enabled by passing the flag when you
  run the command. Some flags need supporting configuration first: `--farm`, for instance, needs
  `FARM_API_KEY` set in your environment. See [Run an autonomous sprint](/guides/autonomous-sprints/)
  for the full walkthrough.
- **A preview command** (for example `/ca:prune`) is enabled simply by invoking it. It does nothing
  until you call it.

## 3. What to Expect While It's in Preview

A preview feature ships **dormant** and runs the same gates as everything else when you do use it:
the commit gate, the reviewer chain, and every hard stop are unchanged. What is not guaranteed is
stability of behavior. A preview feature's interface or output may change between releases while it
earns its evidence, so do not build an unattended workflow on one until it is promoted.

## 4. How It Graduates

A preview feature becomes **stable** (on by default) only when real-world evidence shows it holds
up. That promotion is a deliberate, recorded decision in the project's decision log, not a calendar
event and not something the plugin flips on its own. Until then it stays in the Forge.

## Related

- [What is the Feature Forge](/feature-forge/overview/): the two-axis model behind preview and stable.
- [What's in the Forge](/feature-forge/whats-in-the-forge/): the current preview features.
- [Run an autonomous sprint](/guides/autonomous-sprints/): the `--farm` preview in context.
