---
entity: skills/context-check
related: [commands/context-check]
---

## What it does

Inspect provenance drift or refresh selected context. An audit-only request reports first and
changes nothing. A request to refresh named documents or the full context already supplies the
selection; it does not need repeated per-document approval. Routine commit-gate auto-heal keeps
its existing role.

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
