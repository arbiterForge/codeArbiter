---
title: Just-in-Time Context Injection
description: "How codeArbiter's PreToolUse:Read hook injects a budgeted knowledge pointer for governed files using a four-tier priority map, without ever blocking the Read."
---

When any agent reads a file, a `PreToolUse:Read` hook fires first. It checks whether the file is governed by any knowledge document and, if so, injects a short pointer capped at a 150-token budget. The Read always proceeds. The hook is fail-open and never blocks it.

The check follows a four-tier priority map. Each tier is evaluated in order; the first match wins:

1. **Security controls:** if the file path is a security-entry point in `security-controls.md`, that document governs it.
2. **Accepted ADRs:** any accepted ADR whose `governs:` glob matches the path.
3. **Approved specs:** any spec carrying a `**Governs:**` header line whose glob matches the path. A spec opts in by adding that line.
4. **Provenance claims:** a provenance claim whose stored `git hash-object` hash still matches the current file.

A file that matches none of these tiers is non-governed. The hook injects nothing and makes no git call. Injection is deduplicated once per session and file, so repeated reads of the same file do not accumulate pointer tokens.

The hook is implemented as `pre-read.py`, backed by `_readinjectlib.py`; see the [hooks and gates reference](/reference/hooks-gates/) for the full gate catalog.

<figure class="ca-diagram">
  <img src="/codeArbiter/diagrams/four-tier-map.svg" alt="The four-tier file-to-knowledge map: a Read is matched against security-controls.md, accepted ADRs, approved specs, and provenance in priority order, and the highest-priority match's pointer is injected within a 150-token budget." loading="lazy" />
  <figcaption>Four tiers, evaluated in priority order. The highest match governs; a non-governed Read injects nothing.</figcaption>
</figure>
