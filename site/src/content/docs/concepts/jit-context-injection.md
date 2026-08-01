---
title: Just-in-Time Context Injection
description: "How codeArbiter's PreToolUse:Read hook injects a budgeted knowledge pointer for governed files using a four-tier priority map, without ever blocking the Read."
journey:
  level: "Power user"
  time: "7 minutes"
  outcome: "Predict which repository rule a file read will surface and verify the mapping."
  prerequisites:
    - "An initialized repository"
    - "A security entry point, accepted ADR, approved spec, or provenance claim to inspect"
  proof: "A fresh-session Read surfaces the highest-priority governing document you predicted."
---

When any agent reads a file, a `PreToolUse:Read` hook fires first. It checks whether the file is governed by any knowledge document and, if so, injects a short pointer capped at a 150-token budget. The Read always proceeds. The hook is fail-open and never blocks it.

## How a governing document is chosen

The check follows a four-tier priority map. Each tier is evaluated in order; the first match wins:

1. **Security controls:** if the file path is a security-entry point in `security-controls.md`, that document governs it.
2. **Accepted ADRs:** any accepted ADR whose `governs:` glob matches the path.
3. **Approved specs:** any spec carrying a `**Governs:**` header line whose glob matches the path. A spec opts in by adding that line.
4. **Provenance claims:** a provenance claim whose stored `git hash-object` hash still matches the current file.

A file that matches none of these tiers is non-governed. The hook injects nothing and makes no git call. Injection is deduplicated once per session and file, so repeated reads of the same file do not accumulate pointer tokens.

## What you should expect

The additional context names the governing document and why it matched; it is a pointer, not the
entire policy. Open that document before making a scope-touching change. If no pointer appears, do
not infer that the file is safe or ungoverned: the hook is deliberately fail-open, so inspect the
repository's security controls, accepted ADRs, approved specs, and provenance map when the change is
sensitive.

To verify a mapping, run the read through a fresh session and compare the injected pointer with the
matching `governs:` glob or provenance record. The same file is injected only once per session, so
use a new session when repeating the check.

## Practice: predict one injection

1. Choose a file named by `security-controls.md`, an accepted ADR `governs:` glob, or an approved
   spec `**Governs:**` line.
2. If more than one source matches, use the priority order above to predict the winner.
3. Start a fresh host session and ask the host to read that exact file.
4. Confirm the additional context names the document you predicted and gives the same match reason.
5. Open the governing document before changing the file.

If the pointer is absent or different, do not work around it. Check the glob, ADR status, provenance
hash, and opt-in state; then use the [troubleshooting workflow](/guides/troubleshooting/) to inspect
the read hook.

## Where it fits

The hook is implemented as `pre-read.py`, backed by `_readinjectlib.py`; see the [hooks and gates reference](/reference/hooks-gates/) for the full gate catalog.

<figure class="ca-diagram">
  <img src="/diagrams/four-tier-map.svg" alt="The four-tier file-to-knowledge map: a Read is matched against security-controls.md, accepted ADRs, approved specs, and provenance in priority order, and the highest-priority match's pointer is injected within a 150-token budget." loading="lazy" />
  <figcaption>Four tiers, evaluated in priority order. The highest match governs; a non-governed Read injects nothing.</figcaption>
</figure>

See [Provenance and context drift](/concepts/provenance-drift/) for how the lowest tier stays fresh,
and [Enforcement & Security](/enforcement/) for the difference between this advisory read path and a
blocking hook.
