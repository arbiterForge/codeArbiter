---
status: accepted
date: 2026-10-02
title: Admit a Pi host that strictly reduces audit findings
decided-by: SUaDtL@users.noreply.github.com
supersedes: 0035-use-reviewed-host-locks-and-two-phase-pi-promotion
governs: .github/fixtures/pi-hosts/**, .github/scripts/pi_host_locks.py
---

# ADR-0041 — Admit a Pi host that strictly reduces audit findings

## Status
Accepted — decided by SUaDtL@users.noreply.github.com on 2026-10-02: "Go ahead and update the package is objectively the correct decision. It closes a high."

## Context

ADR-0035 admits a supported Pi host only when its reviewed graph has zero production and zero
complete-graph audit findings. On 2026-10-02 new advisories made the supported baseline itself fail
that rule: exact Pi 0.84.1 pins undici 8.9.0 (GHSA-3wwx-pv8p-q78v, GHSA-pmjh-fq2x-6v4x,
GHSA-r53p-7pc4-xj5r) and its shrinkwrap pins brace-expansion 5.0.9 (GHSA-q2hr-2g5m-vwhr,
GHSA-qhr7-859c-m2p7, GHSA-6j4f-fj2g-mc7p). Every published Pi release from 0.86.1 through 1.0.0
fixes undici but ships the same brace-expansion 5.0.9 in its shrinkwrap, which upstream fixed on
main (pi#10288) after 1.0.0. No published release can pass a zero-findings rule, so the rule left the
repository running the more vulnerable host and blocked every pull request's supported-host CI.

## Decision

This ADR supersedes only ADR-0035's zero-findings admission clause. Reviewed lockfile-v3 graphs,
isolated `npm ci` installation, disabled lifecycle scripts, signature and provenance verification,
and the two-phase promotion boundary remain exactly as ADR-0035 records them.

1. A Pi host candidate may be admitted when its production and complete-graph audit findings are a
   strict subset of the current supported baseline's findings, so admitting it closes at least one
   finding and opens none.
2. Each retained advisory is recorded in the candidate's review receipt by GHSA identifier, package,
   installed version, severity and reason. A finding that is not recorded there fails closed, at
   review and at CI installation.
3. A retained advisory's acceptance ends when a Pi release clears it; that release is then the next
   promotion. Because CI cannot observe future releases offline, each acceptance also carries a dated
   backstop, and installation fails closed after that date until the receipt is re-reviewed or the
   clearing release is promoted.
4. Applied now: Pi 1.0.0 replaces Pi 0.84.1. It closes the three undici advisories and retains the
   three brace-expansion 5.0.9 advisories that 0.84.1 already carries.

## Alternatives considered

- **Wait for Pi 1.0.1** — keeps a known high-severity finding running in supported CI and blocks every
  pull request until an upstream release that has no date.
- **Override Pi's published shrinkwrap** — ADR-0035 already rejected this: a downstream override or a
  hand-edited lock bypasses rather than resolves the reviewed dependency graph.

## Consequences

Supported-host security moves monotonically: a promotion can only remove findings. The review receipt
gains an accepted-advisory record, and the installer's audit compares findings against it instead of
requiring zero. Retained advisories stay visible and dated rather than silently tolerated, and the
next clearing release has a standing reason to be promoted.

## Risks

A mistaken or over-broad accepted-advisory record could hide a new finding; the exact-identifier match
and the strict-subset rule bound that. A backstop date set too far out would let an accepted advisory
outlive its fix. This decision is proven wrong if a promotion admits a finding the baseline lacked, if
an unrecorded finding passes review or installation, or if an accepted advisory survives past its
backstop date without failing CI.
