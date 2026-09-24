---
status: proposed
date: 2026-09-24
title: Publish qualified ca-codex packages to npm for marketplace installation
decided-by: SUaDtL@users.noreply.github.com
supersedes: 0029-publish-ca-pi-to-npm-under-arbiterforge
governs: .agents/plugins/marketplace.json, .github/workflows/release.yml, .github/workflows/npm-publish.yml, .github/actions/publish-release/action.yml, tools/build-host-packages.py, tools/promote-codex-marketplace.py, plugins/ca-codex/package.json
---

# ADR-0039 — Publish qualified ca-codex packages to npm for marketplace installation

## Status
Proposed

## Context
The normal Codex marketplace path installs the repository's `plugins/ca-codex` source tree. The
qualified GitHub Release archive is assembled later from the exact release cohort and adds the
installation-pinned structured-artifact engine under `helpers/artifacts/`. A marketplace install can
therefore report the released ca-codex version while omitting the required native engine and failing
closed with `CAPABILITY_MISSING`.

ADR-0029 publishes ca-pi to npm but explicitly excludes ca-codex because its host was expected to
install from a marketplace. Codex marketplaces now support npm package sources, so that exclusion
prevents the marketplace from selecting the same complete payload that release qualification proved.

## Decision
Publish ca-codex to npm as `@arbiterforge/ca-codex` from the exact already-qualified Codex member of
the release cohort. The publisher must derive the npm tarball from those retained cohort bytes,
preserve the plugin payload and native helper identity, and publish only through the protected release
workflow with npm provenance. Registry readback must verify the exact package name, version, integrity,
provenance source commit, and qualified cohort binding before the protected public marketplace channel
may point to that exact npm version.

The first publication may use the existing organization-wide `NPMJS_TOKEN` through the protected
release job. GitHub reports that the Actions secret is available to every repository in the
organization; the token's npm package/organization privileges are unknown. That broad GitHub secret
availability is accepted as a documented residual risk for the first publish. This decision does not
authorize a release run or any expansion of the token's access.

This decision partially supersedes only ADR-0029's clause excluding ca-codex from npm publication.
ADR-0029's ca-pi package, pinned-Git channel, token handling, provenance requirements, and exclusion of
ca and ca-sandbox remain in force.

## Alternatives considered
- **Keep the promoted Git-subdirectory distribution** — it can carry complete bytes, but it adds a
  second Git publication surface and does not use the package source Codex marketplaces natively
  support for immutable version selection.
- **Commit native binaries into `plugins/ca-codex`** — this would make source installs complete but
  would bypass the existing platform qualification and promotion boundary that chooses native-tested
  binaries after CI.
- **Publish a separately rebuilt npm package** — a second assembly path could drift from the qualified
  cohort, so it cannot establish that marketplace consumers receive the bytes already proven by the
  release lane.

## Consequences
The Codex marketplace publication step occurs only after npm publication and exact registry readback.
The repository-local marketplace may remain a development source, but the protected public marketplace
channel names an exact verified npm version rather than a source checkout or mutable range. The release
workflow gains a ca-codex npm publisher and a retained receipt tied to the existing three-host cohort.

The npm package contains the ca-codex plugin at package root, including `release.json` and the qualified
native binaries. Codex continues to install npm marketplace packages with lifecycle scripts disabled;
the package cannot depend on install-time compilation or downloads.

## Risks
An npm outage can delay marketplace promotion after the GitHub Release is qualified. The currently
available organization-wide `NPMJS_TOKEN` Actions secret has broader GitHub repository availability
than this route needs; the protected environment controls where this workflow consumes the value but
does not narrow that availability. The token's npm privileges remain unknown. This is an explicit
residual risk accepted for the first publication, not a claim about npm package scope. A compromised
npm credential could attempt publication, so registry
provenance plus integrity readback are mandatory. A stale or mutable marketplace selector could
install unverified bytes, so promotion must name one exact version and fail closed unless its retained
cohort and registry receipts agree.
