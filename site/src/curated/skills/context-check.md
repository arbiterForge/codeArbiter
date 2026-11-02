---
entity: skills/context-check
related: [commands/context-check]
use_when: "A merge, direct push or manual edit changed a tracked source file outside a normal commit, so a context document may be stale. The drift notice at session start is the usual signal."
avoid_when: "Routine maintenance, which the commit check already heals automatically; first-time population of project context, which is `/ca:create-context`; or a project snapshot without a drift focus, which is `/ca:status`."
asks: "For each stale document, whether to reinspect the source, re-baseline supported unchanged claims, or defer. A request that already names the documents to refresh needs no further per-document approval."
produces: "A list of stale provenance-tracked documents and, for any you chose to refresh, the changes, inspected scope and remaining uncertainty. It never stages or commits."
---

## What it does

An on-demand drift audit for the bypass case: a merge, a direct push, or a manual edit outside a
normal commit changed a tracked source file, so commit-gate's auto-heal never got a chance to
fire. It reports every stale provenance-tracked document, then offers a choice for each:
reinspect the affected source, re-baseline supported unchanged claims, or defer.

An audit-only request reports first and changes nothing until you select an action. A direct
request for a scoped or full refresh already selects that work; there is no per-document approval
ceremony. Routine commit-gate auto-heal keeps its existing role.

In an HTML-knowledge repository, `knowledge.py stale` lists the records whose cited sources
changed since their document's baseline commit. Update those records, then `knowledge.py
rebaseline` the document. Staleness is advisory and never blocks other work. The phases below
apply to Markdown-format repositories.

## Usage

```text
/ca:context-check
```

The command takes no arguments. Prefer `/ca:status drift` where the installed catalog declares it,
or request a provenance drift audit directly. Both reach the same owner as this retained
compatibility entry, and neither selects repairs on your behalf. An explicit full refresh of
initialized context uses this same owner and keeps the initialization marker;
`/ca:create-context` owns initial population.

## Example

```text
Illustrative output shape, not a captured host run:
> /ca:context-check

Stale provenance-tracked docs (2):
  tech-stack: package.json (changed)
  security-controls: src/auth/session.py (missing)

For tech-stack: re-scout / re-baseline / defer?
```

Legacy v1 entries with `drift_trigger: true` participate in the hash comparison. Managed v2
records also require their current document and source bindings to be assessed; missing or
unsupported coverage remains unknown. The helper reports concrete paths as changed or missing; it
does not compute a commit-age history from a hash mismatch. Confirm missing-file versus
unavailable-hash evidence before choosing a disposition. A re-baseline updates an available
recorded hash; it does not verify that a claim is still correct. A missing source is
not repaired by re-baselining. Deferring leaves the mismatch in place, without creating a new
decision or follow-up record.

## Phases

1. Inspect the actual document/provenance pairs and current source identities. Legacy v1 and
   managed v2 records have different checks; missing or unknown coverage is never called fresh.
2. Reinspect selected claims directly, using optional scoped agents when useful. Full refresh
   accounts for six logical categories and five content documents. Partial work stays partial.
3. Preserve actual user decisions and ask only unresolved material questions. Source hashes and
   role names do not establish semantic correctness or independent review.
4. Inspect the native preview and apply its exact reference and digest under existing authority.
   Explicit adoption can upgrade supported missing/v1 provenance while retaining its preimage;
   managed updates preserve unowned content and recheck current identities.
5. Read back the resulting pair, preserved initialization marker and unchanged unrelated history.

## Exits

Report changed documents, inspected scope, deferred work and remaining uncertainty. Deferral
changes nothing. A stale or unsupported preview refuses that write without blocking safe reading.
The owner never stages or commits; changes use the existing authorized commit workflow.

[Provenance and context drift](/concepts/provenance-drift/) explains the evidence limits.
