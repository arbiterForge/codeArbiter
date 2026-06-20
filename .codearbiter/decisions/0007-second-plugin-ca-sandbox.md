---
status: accepted
date: 2026-06-20
title: Host a second sibling plugin (ca-sandbox) in the codeArbiter repo/marketplace
decided-by: SUaDtL@users.noreply.github.com
supersedes: none
governs: .claude-plugin/marketplace.json, .codearbiter/CONTEXT.md, plugins/ca-sandbox/*
---

# ADR-0007 — Host a second sibling plugin (ca-sandbox) in the codeArbiter repo/marketplace

## Status
Accepted — ratified 2026-06-20 by SUaDtL@users.noreply.github.com.

## Context
The 2026-06-20 brainstorm produced `ca-sandbox`: a locally-hosted GitHub-Codespace equivalent that
pulls an untrusted repo into an ephemeral, isolated container (no host-FS access; configurable
network). This is **infrastructure**, not governance — it sits at the edge of codeArbiter's stated
identity. `CONTEXT.md` frames this repo as "the orchestration framework itself" and `marketplace.json`
describes a "Single-plugin marketplace." Shipping ca-sandbox therefore expands the repo's identity, and
the maintainer chose to do so rather than spin up a separate repo, because the marketplace `plugins`
array already supports multiple entries and ca-sandbox integrates tightly with arbiter (its exec seam
is the natural home for the farm dispatcher's deferred `item-3` process-level sandbox).

## Decision
codeArbiter's repo and marketplace host a **second, sibling plugin `plugins/ca-sandbox/`**, distinct
from the `ca` governance plugin. The two plugins are independent: CI is **path-scoped** so that a
change touching only sandbox paths skips every `ca` check (refs graph, version-bump guard, tools
tests) and a change touching only `ca` paths skips every ca-sandbox check. The `ca` governance
plugin's identity and gates are unchanged; ca-sandbox is infrastructure that arbiter knows about and
integrates with, not part of the governance kernel.

## Alternatives considered
- **Separate repository, referenced by the marketplace** — declined. Cleaner identity separation, but
  a second repo to manage for a solo dev and looser coupling to `farm.ts` (the intended `item-3`
  integration point).
- **A tool inside the `ca` plugin** (`plugins/ca/tools/sandbox`) — declined. It would fold
  infrastructure into the governance plugin, blurring the "orchestration, not infrastructure"
  boundary and coupling the two release cadences.
- **Standalone script, not a plugin** — declined. Loses marketplace distribution and the gated
  skill/command surface the feature warrants.

## Consequences
Easier: ca-sandbox ships through the existing marketplace, develops alongside arbiter, and has a clean
seam for the farm `item-3` sandbox. The `ca` plugin stays focused. Harder: the repo's identity is now
"a marketplace of a governance plugin plus an infrastructure sibling," which `CONTEXT.md` and the
marketplace description must state explicitly. CI must learn two plugins via path-scoped jobs, and the
version-bump guard must apply per-plugin. ca-sandbox adds host dependencies (Docker, nixpacks) that
`ca` never required — these are scoped to the sandbox plugin and must be detected-and-messaged, not
assumed.

## Risks
Scope creep: a second plugin invites a third, eroding the framework's focus. Mitigation: ca-sandbox is
the deliberate, recorded exception, not a precedent for arbitrary co-location. Path-scoped CI is the
load-bearing assumption — if it is mis-wired, a sandbox change could silently ship `ca` unvalidated (or
vice versa); the CI work must prove isolation. This decision is proven wrong if the two plugins'
coupling forces constant cross-plugin changes (showing they were never truly independent), at which
point either merging them or splitting to separate repos reopens.
