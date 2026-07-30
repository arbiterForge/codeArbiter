---
title: Using Features Still in the Forge
description: "How to turn on a codeArbiter preview feature, what to expect while it is in the Forge, and how it graduates to stable."
journey:
  level: Labs
  time: 10 min
  outcome: "a bounded preview trial with a known opt-in, observable success signal, documented off switch, and no confusion with stable guarantees."
  prerequisites:
    - A disposable or low-consequence repository
    - The preview's required environment and host version
  proof: "The feature works only while explicitly armed and is dormant again after you remove the opt-in."
---

Features in the [Feature Forge](/feature-forge/overview/) are real and usable, but they stay off
until you ask for them. This guide covers how to turn one on, what to expect while it is in
preview, and how it eventually graduates.

## 1. Find What's Available

Check [What's in the Forge](/feature-forge/whats-in-the-forge/) for the current preview features.
Preview commands and flags are also marked with a
<span class="ca-badge" data-kind="preview">preview</span> badge on their reference pages.

## 2. Turn It On

Preview features are opt-in by design; a new plugin version never switches one on for you. How you
opt in depends on the feature:

- **A preview flag** (for example `--farm` on `/ca:sprint`) is enabled by passing the flag when you
  run the command. Some flags need environment variables set first;
  [What's in the Forge](/feature-forge/whats-in-the-forge/) lists the required and optional variables
  for each preview feature (for `--farm`, `FARM_API_KEY` is required). See
  [Run an autonomous sprint](/guides/autonomous-sprints/) for the full walkthrough.
- **A preview command** (for example live transcript pruning) is opted into through an environment
  variable, not just by running the command. Pruning stays dormant until you set `CODEARBITER_PRUNE`
  (start with `dry`); [What's in the Forge](/feature-forge/whats-in-the-forge/) lists the modes.
- **A preview plugin** is a separate sibling plugin you install on its own. `ca-pi` is installed
  from a pinned Git tag, and `ca-sandbox` is installed from the marketplace. Installing `ca-pi`
  opts into its global rich footer; repository-aware governance still requires the normal
  `arbiter: enabled` marker and affirmative Pi project trust. Each plugin carries its own
  prerequisites.

## 3. What to Expect While It's in Preview

A preview feature ships **dormant** and runs the same gates as everything else when you do use it:
the commit gate, the reviewer chain, and every hard stop are unchanged. What is not guaranteed is
stability of behavior. A preview feature's interface or output may change between releases while it
earns its evidence, so do not build an unattended workflow on one until it is promoted.

## 4. How It Graduates

A preview feature becomes **stable** (on by default) only when real-world evidence shows it holds
up. That promotion is a deliberate, recorded decision in the project's decision log, not a calendar
event and not something the plugin flips on its own. Until then it stays in the Forge.

## 5. Verify and Turn It Back Off

Before using a preview on meaningful work:

1. Record the plugin version, host, exact flag or environment variable, and expected visible signal.
2. Exercise the least consequential mode first. For pruning, begin with `dry`; for a new host
   adapter, use a disposable repository.
3. Confirm hard gates still block the same unsafe calls.
4. Remove the flag or environment variable and restart any session-started service.
5. Confirm the feature is dormant and ordinary behavior returns.

If the off switch fails, stop the trial, capture the version and host, and report it as a defect.
Do not promote a local success into a stable claim; promotion requires the forge's broader evidence.

## Related

- [What is the Feature Forge](/feature-forge/overview/): the two-axis model behind preview and stable.
- [What's in the Forge](/feature-forge/whats-in-the-forge/): the current preview features.
- [Run an autonomous sprint](/guides/autonomous-sprints/): the `--farm` preview in context.
