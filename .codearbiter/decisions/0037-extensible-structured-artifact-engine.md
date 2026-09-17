---
status: proposed
date: 2026-09-16
title: Use an extensible internal engine for governed structured-file writes
decided-by: SUaDtL@users.noreply.github.com
supersedes: none
governs: core/artifacts/**, core/pysrc/_artifactlib.py, core/surface/includes/artifacts.md, tools/build-host-packages.py
---

# ADR-0037 — Use an extensible internal engine for governed structured-file writes

## Status
Proposed — explicitly approved by SUaDtL@users.noreply.github.com on 2026-09-16. This is Accepted/Planned: it records the architecture decision but does not authorize rollout or migration of any artifact kind.

## Context
codeArbiter currently writes several governed file families through separate prose-oriented helpers and workflow instructions. Feature specifications, implementation plans, open and completed task boards, tickets, decomposition documents, and other structured records all need some combination of stable identity, validation, bounded mutation, concurrency protection, recovery, migration, and generated-host parity.

The typed-HTML design initially introduces a Go helper for specifications and implementation plans. Treating that helper as permanently specific to those two kinds would force later structured files either to duplicate storage and mutation machinery or to create competing binaries and trust boundaries. The repository user instead directed that this binary be designed to expand to most structured file writes.

The first feature remains bounded by its approved specification and plan. Open tasks, done tasks, tickets, decomposition documents, ADRs, audit logs, and other existing files do not migrate merely because the engine can support additional artifact kinds.

## Decision
Create one internal, database-free structured-artifact engine, provisionally exposed as the `ca-artifact` binary, as the shared mechanism for governed structured-file reads and writes. Specifications and implementation plans are its first artifact kinds, not its permanent product boundary.

The engine has a small kind-neutral kernel for strict input decoding, canonical identity and hashing, trusted path resolution, bounded reads, compare-and-swap mutation, locking, journaled recovery, capability diagnostics, and version dispatch. Each artifact kind supplies a closed, compile-time repository-owned contract for its model, schema, semantic validation, canonical representation, permitted operations, compatibility, migration, and rendering where applicable.

Artifact kinds may use different canonical representations. Specifications and plans may use self-contained HTML with an embedded authoritative model; task boards, tickets, decomposition documents, and later kinds are not forced into HTML when another human-readable checked-in representation better preserves their workflow. One artifact has one declared canonical authority; generated views and projections remain derived and mechanically checked.

Extensibility is repository-governed, not dynamically pluggable. Adding or migrating an artifact kind requires an approved feature scope, explicit canonical/generated ownership, compatibility and rollback policy, authority-event mapping, negative and recovery tests, generated-host parity, native-platform evidence where writes are supported, and applicable release qualification. The engine has no runtime plugin loader, generic extension bag, remote schema fetch, resident daemon, database, ORM, or model-powered behavior.

The binary remains internal machinery behind existing governed commands, skills, agents, permissions, and execution tools. It adds no public command, agent, top-level skill, persistent model tool, or eagerly loaded schema surface. Operation help and kind contracts load on demand. The engine never executes commands or instructions stored in artifacts, never treats document state or a digest as authorization, and never creates a privilege path around existing user, SMARTS, review, TDD, commit, branch, or release authority.

Canonical shared sources and host descriptors remain authoritative under ADR-0031. Python integration stays standard-library-only and resolves a reviewed installed binary through existing host/package mechanisms. Generated adapters, packaged binaries, manifests, provenance, and release evidence remain host- and target-specific. A supported artifact kind stays disabled by default until its complete workflow, migration, native-host, cold-install, and release obligations are qualified.

## Alternatives considered
- **Keep the binary permanently limited to specifications and plans** — rejected because other structured file families would duplicate identity, validation, concurrency, recovery, and packaging mechanisms or create additional trusted executables.
- **Create one binary or bespoke writer per artifact family** — rejected because it multiplies trust boundaries, native payloads, release work, and cross-host drift while weakening common mutation guarantees.
- **Provide a dynamic artifact-plugin system or runtime-loaded schemas** — rejected because it creates a new extension and permission surface, complicates provenance, and allows unreviewed behavior to enter the trusted write path.
- **Continue direct prose mutation from Python and workflow prompts** — retained for files not yet migrated, but rejected as the long-term architecture for structured writes that require stable identity, conflict detection, transactional recovery, or mechanical parity.
- **Introduce a datastore or resident service** — rejected because checked-in files remain the durable project state and offline review boundary.

## Consequences
Shared mechanics can become more reliable once and serve multiple artifact families, while each kind keeps an explicit domain contract and human-readable canonical form. The initial specs/plans implementation must avoid assumptions that make the kernel HTML-specific or freeze a two-kind API. Future features can add kinds without adding public commands or another trusted executable.

The binary becomes high-leverage infrastructure with a correspondingly larger compatibility and supply-chain burden. Kernel changes can affect several artifact families, so version negotiation, kind-scoped tests, generated parity, native packaging, rollback, and release evidence become load-bearing. A new kind is still a product change with its own approval and proof; this ADR is not blanket authorization to convert existing files.

The architecture deliberately supports gradual adoption. Existing files and workflows remain authoritative until their specific migration is approved and qualified. Mixed legacy and engine-owned kinds must fail explicitly rather than being silently rewritten or interpreted under the wrong contract.

## Risks
The engine could become a monolith that absorbs domain policy better owned by workflows, or its generic kernel could acquire weak extension points that bypass closed validation. Review must keep authorization and domain decisions outside the kernel while preserving strict per-kind contracts.

A defect in shared storage, identity, or compatibility code could affect many artifact families. Discriminating fault tests, crash/replay tests, native-platform qualification, versioned journals, and conservative downgrade behavior are required before expanding rollout.

The decision is wrong if artifact families cannot share mutation and recovery mechanics without forcing unnatural representations, coupling unrelated release cadences, weakening existing authority, or making local project state unusable when the binary is unavailable. That evidence should split the engine along proven boundaries rather than preserve a generic abstraction at the expense of correctness.
