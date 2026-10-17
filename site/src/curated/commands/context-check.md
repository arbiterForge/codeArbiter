---
entity: commands/context-check
related: [skills/context-check, create-context, status]
---

## What it does

An optional, on-demand drift audit for the bypass case: a merge, a direct push, or a manual edit
outside a normal commit changed a tracked source file, so commit-gate's auto-heal never got a
chance to fire (that heal runs automatically on every commit that touches a `drift_trigger`
source — this command is not that routine path). It reports every stale provenance-tracked doc,
then for each one offers a choice: reinspect the affected source, re-baseline supported unchanged claims, or defer.

An audit-only request is read-only until you select an action. A direct request for a scoped or
full refresh already selects that work; there is no per-document approval ceremony. Use the safe
writer's preview and apply with current source identities, preserving unselected human content.
The owner never stages or commits.
The SessionStart drift line is the usual signal that this check is worth running.

## Usage

```
/ca:context-check
```

Takes no arguments. Prefer `/ca:status drift` where the installed catalog declares it, or request a provenance drift audit directly. Both reach the same owner as this retained compatibility entry; neither selects repairs on your behalf.

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
unsupported coverage remains unknown. The helper
reports concrete paths as changed or missing; it does not compute a commit-age history from a
hash mismatch. Confirm missing-file versus unavailable-hash evidence before choosing a disposition.
A re-baseline updates an available recorded hash; it does not verify that a claim is still correct.
A missing source is not repaired by re-baselining. Deferring leaves the mismatch in place, without
creating a new decision or follow-up record. See [Provenance and context drift](/concepts/provenance-drift/).

## When to reach for it

Skip it for routine maintenance — commit-gate's auto-heal already covers the common case with no
manual step. Explicit full refresh of initialized context uses this same owner and keeps the
initialization marker; `/ca:create-context` owns initial population. A project-state snapshot
without a drift focus is `/ca:status`'s.
