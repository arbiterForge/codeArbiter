---
title: "Trust & Lifecycle"
description: "A source-linked map for evaluating codeArbiter's enforcement boundaries, data flows, support evidence, license, and removal path."
journey:
  level: "Foundation"
  time: "5 minutes"
  outcome: "Find the canonical owner for a trust or lifecycle question without relying on duplicated policy prose."
  prerequisites: []
  proof: "You can reach the current enforcement, data-flow, support, licensing, and removal sources directly."
---

This documentation website describes the installed product; it is not an installed codeArbiter
adapter, a hosted governance service, or a codeArbiter account. This page is a map to the canonical
owners for trust and lifecycle details. Follow those sources for the current policy, evidence, and
procedures instead of treating this summary as another policy copy.

## Before installation

| Question | Canonical owner |
| --- | --- |
| What can codeArbiter block, and where are its limits? | [Enforcement & Security](/enforcement/) |
| Which activity uses the network, and what stays on disk? | [Compatibility: Network Calls](/getting-started/compatibility/#network-calls) and the repository's [Privacy Policy](https://github.com/arbiterForge/codeArbiter/blob/main/PRIVACY.md) |
| Which published versions and documentation build does the site currently support with evidence? | [Published release applicability](/getting-started/compatibility/#release-applicability-heading) and its [machine-readable record](/release-applicability.json) |
| What license governs the repository? | The canonical repository [LICENSE](https://github.com/arbiterForge/codeArbiter/blob/main/LICENSE) |

## While operating or removing codeArbiter

- To inspect a block or understand whether a control is blocking or advisory, use
  [Enforcement & Security](/enforcement/).
- To verify currently published support evidence after an update, use
  [Compatibility](/getting-started/compatibility/) and the
  [machine-readable applicability record](/release-applicability.json).
- To make one repository dormant, remove one host, or uninstall every host without accidentally
  deleting project-owned history, follow [Uninstall & Disable](/guides/uninstalling/).

These links intentionally remain the canonical owners. Changes to enforcement, data flows, support,
licensing, or removal belong in their owning source first; this route should continue to point to
them rather than restating their claims.

If a linked source changes, prefer that source over this navigation map.
