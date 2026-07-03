---
entity: agents/map-deps
related: [skills/tribunal, map-structure]
---

## Role

Read-only extractor of a repository's dependency and integration-surface inventory — manifests,
lockfiles, outbound service calls, and where environment/secret-shaped identifiers are read (names
only, never values). It reports facts, never findings; judging license or security risk is out of
scope, left to `dependency-reviewer` and the tribunal secrets-supply lens. Dispatched only by the
`tribunal` skill's Phase 1, and only on a large or sprawling repo, to keep raw file-reading out of the
orchestrator's retained context.

## Why this model tier

Ships `model: inherit`, but the `tribunal` skill's own dispatch-time model guidance recommends Haiku
for this role — it is bulk fact extraction, not judgment, so a cheap tier is the right fit even though
the frontmatter leaves the choice to the dispatcher.

## What it emits

A terse structured summary — manifest list, dependency highlights, integration-surface list, and
env/secret-usage-surface list — sized to fold directly into the tribunal run's `inventory.md`, never a
file-by-file narrative.
