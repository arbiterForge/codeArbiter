---
title: Checkpoints
description: "Periodic, read-only sweeps of the whole codebase by the reviewer fleet, consolidated into dated reports to catch drift and latent issues between feature work."
---

A **checkpoint** is a periodic, read-only sweep of the whole codebase by the reviewer fleet.
The findings are consolidated, classified by severity, and triaged into a single dated
report. The ones that block the current change are called out, the rest recorded.
Checkpoints are how drift and latent issues get caught between feature work, without
blocking any single change.

When a lean sweep isn't enough, `/ca:tribunal` convenes the deep counterpart: a rare,
on-demand audit of the whole codebase by eleven specialist lens reviewers. Its run state
persists under `.codearbiter/reports/`, so an interrupted run resumes from disk, and its
findings become GitHub issues only on explicit approval. Like the checkpoint, it is
read-only review and never a required gate.
