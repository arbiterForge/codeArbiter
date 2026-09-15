---
status: accepted
date: 2026-08-31
title: Use hosted static package evidence for ca-codex releases
decided-by: SUaDtL@users.noreply.github.com
supersedes: 0031-cross-host-plugin-root-and-agent-charter-resolution
governs: .github/workflows/release.yml, .github/workflows/ci.yml, .github/scripts/check_codex_skill_resources.py, .github/scripts/verify_codex_candidate_provenance.py, plugins/ca-codex/*
---

# ADR-0032 - Use hosted static package evidence for ca-codex releases

## Status
Accepted

## Context

ADR-0031 established the correct shared-kernel and host-adapter architecture, but its Decision 5
made an installed Windows Store/MSIX desktop cell mandatory before any `ca-codex` release. That
requirement expanded a static plugin publication into a protected self-hosted runner, Hyper-V VM,
Microsoft ADK, device-authorization, broker/driver/probe, teardown-attestation, and receipt system.
The pending 0.7.5 package is structurally complete and its hosted checks are green, yet publication
remains blocked on evidence that is not part of the shipped plugin contract.

The user explicitly revoked every use of their personal PC as repository CI or desktop-proof
infrastructure, rejected desktop application installation as release evidence, and approved a
hosted-only static package contract. They clarified that practical proof means updating the
supported local Codex marketplace plugin in this environment and loading it in a fresh task, not
installing or automating the Windows desktop app.

## Decision

This ADR supersedes only ADR-0031 Decision 5 and its corresponding desktop-proof consequence. Every
other ADR-0031 decision remains accepted and unchanged.

`ca-codex` release evidence is the exact deterministic plugin package built from the final release
tree. Trusted GitHub-hosted verifier code must fail closed unless the candidate has a valid plugin
manifest, required resource front matter, complete contained resource and route graph, deterministic
generated parity, valid hook declarations and targets, approved host-root vocabulary, and exact
manifest/changelog/tag/release/provenance/archive identity.

Candidate bytes selected by a workflow event are inert data. Verifier, packager, and publisher code
executes only from the trusted release tree. Existing hosted secret scanning, CodeQL, governance,
security, and merge-readiness gates remain applicable.

The self-hosted desktop candidate workflow, protected desktop environment dependency, broker,
driver, probe, Hyper-V/ADK boundary, desktop receipt, and attestation chain are retired from active
release infrastructure. They are not retained as optional publication gates or substituted with
synthetic evidence. Historical ADRs, plans, reports, audits, and release records remain immutable.

After publication, practical host proof uses the supported CodeArbiter marketplace update path. A
fresh Codex task must select the published version and `$ca-doctor` must verify package ownership,
resource completeness, hook enforcement, and its harmless live-fire route. No Store/MSIX desktop
installation, device authorization, API credential, billable API access, self-hosted runner, UAC,
Hyper-V, or network mutation is required or authorized.

## Alternatives considered

- **Keep desktop certification as an optional manual workflow** - rejected because it preserves an
  expensive, security-sensitive, misleading maintenance surface that is not needed to determine
  whether the static plugin package is valid.
- **Move desktop proof to organization-owned Windows infrastructure** - rejected because it adds
  cost and operational complexity while testing the desktop application rather than the plugin
  artifact's declared contract.
- **Leave the existing gate blocked until personal infrastructure is available** - rejected because
  the user withdrew that infrastructure and the gate is disproportionate to the object released.

## Consequences

Releases become reproducible on ordinary GitHub-hosted runners and no longer depend on a maintainer's
personal computer, interactive authorization, or mutable machine state. Static package validation
must become more explicit: manifest, front-matter, hook-target, route-closure, generator, and archive
identity failures are release blockers rather than assumptions delegated to a desktop exercise.

Removing the desktop stack deletes substantial workflow and PowerShell maintenance surface. The
repository no longer claims to certify Windows desktop UI behavior as part of a plugin release.
Plugin usability remains directly checked through the supported marketplace install and a fresh
Codex task.

## Risks

A future Codex host could change behavior in a way that a structurally valid package does not catch.
The required pinned real-host compatibility lanes, advisory latest-host lane, local marketplace
update, fresh-task load, and `$ca-doctor` provide the proportionate detection boundary. If those
checks stop exercising actual package selection or hook enforcement, this decision must be
revisited rather than silently weakening their assertions.

The static verifier itself becomes release-critical. It must parse candidate data without executing
it, enforce bounded archive reads and contained paths, run from trusted release-tree content, and
remain covered by adversarial malformed-package regressions.
