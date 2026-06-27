---
title: Checkpoints
description: "Periodic, read-only sweeps of the whole codebase by the reviewer fleet, consolidated into dated reports to catch drift and latent issues between feature work."
---

A **checkpoint** is a periodic, read-only sweep of the whole codebase by the reviewer fleet.
The findings are consolidated, classified by severity, and triaged into a single dated
report. The ones that block the current change are called out, the rest recorded.
Checkpoints are how drift and latent issues get caught between feature work, without
blocking any single change.
