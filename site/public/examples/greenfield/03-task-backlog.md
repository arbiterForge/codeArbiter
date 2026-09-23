# 03: Task backlog

Illustrative project-level backlog. Estimates are discussion inputs, not measured
completion times. IDs here are ordinary planning labels, not typed-engine IDs.

| Priority | Phase | Task | Role | Estimate | Dependency |
|---|---|---|---|---|---|
| 1 | MVP | Resolve persistence and deployment constraints | Architecture | 1 day | CONFIRM-01 |
| 2 | MVP | Implement saved-search persistence and ordering | Backend | 2 days | Task 1 |
| 3 | MVP | Build list and empty-state UI | Frontend | 2 days | Task 2 |
| 4 | v1 | Deliver CSV export through the user interface | Frontend/backend | 2 days | Task 3 |
| 5 | v2 | Time-box a collaboration and revocation investigation | Architecture | 1 day | MVP feedback |

Task 4 is still too broad for direct engine execution. A feature specification
must decide the observable behavior; its execution plan decomposes that behavior
into smaller named verification tasks. The tour's serializer fixture illustrates
one such boundary, not completion of this whole backlog item.

## Review

Assign each implementation task to one accountable owner before scheduling it.
The combined role above is an explicit gap to resolve, not a ready assignment.
Keep estimates, phase order, dependencies, spikes and unanswered questions
visible. Review through decompose, then use the governed task-board writer rather
than treating this document as the helper-owned open-tasks.md board.
