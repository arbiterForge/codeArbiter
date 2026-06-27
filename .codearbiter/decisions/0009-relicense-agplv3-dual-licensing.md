---
status: accepted
date: 2026-06-27
title: Relicense from MIT to AGPLv3 with proprietary dual-licensing
decided-by: SUaDtL@users.noreply.github.com
supersedes: 0006
governs: LICENSE, README.md, CLA.md
---

# ADR-0009 — Relicense from MIT to AGPLv3 with proprietary dual-licensing

## Status
Accepted — ratified 2026-06-27 by SUaDtL@users.noreply.github.com

## Context
The project shipped under MIT, which lets anyone close-source the code or fold it into a competing
hosted product with no reciprocity. The maintainer is preparing a closed-source SaaS built on this
codebase and needs two things at once: a copyleft strong enough to stop a third party from running a
closed-source hosted fork, and the freedom to license the same code commercially to themselves. As
sole copyright holder the maintainer can do both: distribute the open-source version under AGPLv3
(whose section 13 network-use clause closes the hosted-service loophole GPL leaves open) while
reserving the right to grant separate proprietary licenses. ADR-0006 set a broad-OSS-adoption posture
that declined a commercial vertical; this decision revises the licensing and commercial posture, so it
supersedes ADR-0006.

## Decision
The open-source distribution of codeArbiter is relicensed from MIT to GNU AGPLv3. Copyright is held
solely by the maintainer, who reserves the right to offer the same code under separate
proprietary/commercial terms (dual-licensing), including for an upcoming closed-source SaaS product.
Future community contributions require a Contributor License Agreement granting the maintainer the
right to relicense contributions under both AGPLv3 and proprietary terms. The project stays open
source — AGPLv3 is an OSI-approved license — so ADR-0006's core commitment to OSS is preserved; what
changes is the reciprocity strength of the license and the addition of a commercial path.

## Alternatives considered
- **Stay MIT** — declined. MIT lets a competitor run a closed-source hosted fork with zero obligation,
  the exact outcome the SaaS plan needs to prevent.
- **GPLv3 (not AGPL)** — declined. GPLv3 copyleft does not trigger on network use, so a competitor
  could host a modified version as a service without sharing changes. AGPLv3 section 13 closes that gap.
- **A non-OSI source-available license (BSL/SSPL-style)** — declined. It would abandon the OSS
  positioning ADR-0006 deliberately kept. AGPLv3 keeps the project genuinely open source while still
  deterring closed hosted forks.
- **Per-file AGPLv3 headers** — declined as an implementation choice. The repo convention
  (coding-standards.md) is a single root LICENSE with no per-file headers; adding headers reverses that
  convention for no legal benefit.

## Consequences
Easier: a third-party closed-source hosted fork now carries an AGPLv3 source-disclosure obligation,
and the maintainer keeps a clean commercial-licensing path as sole copyright holder. A CLA keeps future
contributions relicensable, protecting the dual-license model. Harder: AGPLv3 narrows adoption — many
organizations prohibit AGPL dependencies outright — so the broad-adoption goal of ADR-0006 is partially
traded for moat protection. Contribution friction rises, since a CLA is a barrier some contributors
decline. The relicense is forward-only.

## Risks
MIT is irrevocable for already-published code: anyone may fork the last MIT-licensed commit and
continue under MIT indefinitely, so the relicense protects future development, not what is already
public. The dual-licensing model depends on the maintainer holding all rights to every line; any
contribution not covered by the CLA or by clean sole authorship clouds the ability to relicense, so
contribution provenance must be tracked from here on. This decision is proven wrong if AGPL
adoption-hostility starves the project of the users and contributors ADR-0006 prioritized with no
offsetting commercial traction, at which point the license and commercial posture legitimately reopens.
