---
entity: commands/context-check
related: [skills/context-check, create-context, status]
---

## What it does

An optional, on-demand drift audit for the bypass case: a merge, a direct push, or a manual edit
outside a normal commit changed a tracked source file, so commit-gate's auto-heal never got a
chance to fire (that heal runs automatically on every commit that touches a `drift_trigger`
source — this command is not that routine path). It reports every stale provenance-tracked doc,
then for each one offers a choice: re-scout (a partial scout run), re-baseline (accept the new
hash into `.codearbiter/.provenance/`), or defer.

It's read-only until you pick one of those actions — nothing is modified or committed on its own.
The SessionStart drift line is the usual signal that this check is worth running.

## Usage

```
/ca:context-check
```

Takes no arguments. This is a retained compatibility route; prefer `/ca:status drift` where the installed command catalog declares that route.

## Example

```text
Illustrative output shape, not a captured host run:
> /ca:context-check

Stale provenance-tracked docs (2):
  tech-stack: package.json (changed)
  security-controls: src/auth/session.py (missing)

For tech-stack: re-scout / re-baseline / defer?
```

Only recorded entries with `drift_trigger: true` participate in this drift report. The helper
reports concrete paths as changed or missing; it does not compute a commit-age history from a
hash mismatch. Confirm missing-file versus unavailable-hash evidence before choosing a disposition.
A re-baseline updates an available recorded hash; it does not verify that a claim is still correct.
A missing source is not repaired by re-baselining. Deferring leaves the mismatch in place, without
creating a new decision or follow-up record. See [Provenance and context drift](/concepts/provenance-drift/).

## When to reach for it

Skip it for routine maintenance — commit-gate's auto-heal already covers the common case with no
manual step. A full brownfield re-scan from scratch is `/ca:create-context`'s job; a project-state
snapshot without a drift focus is `/ca:status`'s.
