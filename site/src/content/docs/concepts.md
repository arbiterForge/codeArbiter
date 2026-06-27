---
title: Concepts
description: "The core ideas behind codeArbiter: gated lanes, the Feature Forge, SMARTS, ADRs, checkpoints, and the full governance model."
---

codeArbiter is built on a set of interlocking ideas. Each page covers one concept in full.

- [The gated-lane model](/concepts/gated-lanes/): every kind of work has a sanctioned path with gates scaled to its risk.
- [The Feature Forge](/concepts/feature-forge/): a two-axis model that separates version-payload governance from per-feature maturity.
- [SMARTS](/concepts/smarts/): the structured scoring rubric for autonomous decisions, recorded in the sprint log.
- [ADRs and the decision log](/concepts/adrs/): numbered, dated, user-attributed records of architecturally significant choices.
- [Checkpoints](/concepts/checkpoints/): periodic read-only sweeps that catch drift and latent issues between feature work.
- [The persona-register split](/concepts/persona-and-context/): separate orchestrator, author, and reviewer personas that keep each role sharp.
- [Provenance & context drift](/concepts/provenance-drift/): source-hash tracking that surfaces stale claims and heals them at commit time.
- [Just-in-time context injection](/concepts/jit-context-injection/): a four-tier map that injects a governance pointer on every governed-file Read.
- [Auditability](/concepts/auditability/): how the pieces compose into an auditable record for any range of work.
