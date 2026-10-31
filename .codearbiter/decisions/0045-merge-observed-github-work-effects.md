---
status: accepted
date: 2026-10-31
title: Defer contingent GitHub work effects until an observed merge
decided-by: SUaDtL@users.noreply.github.com
supersedes: none
governs: core/pysrc/_workgithub.py, core/pysrc/work.py, .codearbiter/specs/project-work-system.html
---

# ADR-0045 — Defer contingent GitHub work effects until an observed merge

## Status
Accepted — owner directed a full-lens SMARTS read on 2026-10-31 and chose its recommendation.

## Context
ADR-0008 co-locates local board changes with the work commit, so abandoning a branch also abandons its contingent local state. GitHub issues and Projects changes are network effects outside that atomic merge. Sending a contingent effect while its PR is open can leave remote state that the abandoned branch never justified.

## Decision
Local work changes remain co-located with their work commit. A new GitHub issue or status change tied to unmerged work is staged locally and defaults to delivery only after an explicit sync verifies a merged default-branch PR containing that exact work intent. A later ordinary sync can perform the send; no background watcher or automatic compensation is promised.

Independent discovery may use an explicitly configured immediate issue effect. Project item and field mutations require separate explicit sync commands against a verified bound issue; they are sync-now actions, not automatic consequences of staging a local intent. Their result is read back, and uncertain outcomes are reconciled before another mutation. Neither local staging nor a model recommendation grants provider permission or replaces the user's actual authorization.

This extends ADR-0008 to remote effects; it does not change its local commit coupling or independent-discovery rule.

## Alternatives considered
- **Send every effect when staged** — can publish branch-contingent intent before the work merges.
- **Send first and compensate on abandonment** — GitHub has no transaction spanning Git, and compensation can overwrite later human edits.
- **Add a second approval for each sync** — duplicates the existing user and provider permission boundaries without resolving merge timing.

## Consequences
Contingent issue effects remain pending until the merge is observed and an authorized sync runs. Independent issues can be filed promptly. Project mutations are deliberately invoked and have saved/read-back state. Invoking the separate Project sync command is the explicit sync-now choice; it can precede a PR merge only for independently authorized state. The interface must show pending, conflict, and outcome-unknown states truthfully.

## Risks
A merge may not be observed until the next sync, so remote tracking can lag. A mistaken immediate or sync-now choice can still publish early. GitHub readback cannot make concurrent human edits transactional; a later edit can race the observation, and the adapter must report conflicts or uncertain outcomes rather than claim guaranteed rollback.
