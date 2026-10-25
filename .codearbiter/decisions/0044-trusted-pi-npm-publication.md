---
status: accepted
date: 2026-10-24
title: Authenticate Pi npm publication with a trusted publisher and require provenance identity
decided-by: SUaDtL@users.noreply.github.com
supersedes: 0040-independent-per-target-release-with-consumer-safety-gates
governs: .github/workflows/release.yml, .github/actions/publish-target/action.yml, .github/scripts/_npm_publishlib.py, .codearbiter/security-controls.md
---

# ADR-0044 — Authenticate Pi npm publication with a trusted publisher and require provenance identity

## Status
Accepted — owner confirmed on 2026-10-24: "yes this is the more correct way to release".

## Context
Pi publication uses the long-lived `NPMJS_TOKEN` although its release job has
`id-token: write`. Integrity readback blocks, but npm attestation and signature
verification only warn. npm provenance attests origin and build, not code safety.

## Decision
Configure `@arbiterforge/ca-pi` on npm with a GitHub Actions trusted publisher
restricted to organization `arbiterForge`, repository `codeArbiter`, workflow
filename `release.yml`, no GitHub environment, and `npm publish` access. Verify
that account-side configuration before qualifying
a live Pi release. The publish invocation uses short-lived OIDC authentication
and receives no `NPMJS_TOKEN` or `NODE_AUTH_TOKEN`; unavailable trust fails closed.

Before completing a Pi release, require exact tarball integrity, npm signature
and provenance verification, and an attestation binding the tarball to this
repository, the release workflow, and the intended source commit. Existing
version recovery has the same identity gate. A failed check leaves the GitHub
Release unpublished for investigation, without moving a tag or changing bytes.

This supersedes ADR-0040 only for Pi's npm attestation and signature gate.
Independent release jobs and other advisory checks remain in force. It also
supersedes ADR-0029's `NPMJS_TOKEN` credential choice; its package name, Git pin
channel, package layout and provenance requirement remain in force.

## Alternatives considered
- **Keep token authentication and advisory provenance** — permits a reusable
  publish credential and an unverifiable package to complete release.
- **Keep a token fallback** — defeats the trusted publisher boundary on failure.
- **Require signatures without identity binding** — does not establish the
  intended repository, workflow and source commit.

## Consequences
The publish credential is short-lived and scoped to the GitHub workflow. An
immutable npm version may exist while its GitHub Release remains unpublished
until exact identity verification succeeds. The npm package owner must establish
the trusted publisher account setting before token-free publication works.

## Risks
An incorrect npm setting or Sigstore verification outage can halt Pi release
after npm accepts a version. npm does not validate the setting when saved; the
release run is the decisive live check. Recovery inspects the same version and
never republishes different bytes.
