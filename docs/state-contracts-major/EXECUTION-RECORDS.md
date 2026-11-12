# Execution records and immutable intake

The intake corpus records what was observed and proposed at the audited commit. Preserve its original audit, task specifications, decision record and manifest. The PLANNED and NOT_RUN values inside the intake remain historical facts about this handoff. They are not the live execution dashboard.

Create an execution/ directory beside the intake files on the integration branch. Initialize execution/progress.json from contracts/execution-state-template.json and execution/CHECKPOINT.md from CHECKPOINT.md. Commit these records with implementation slices through the same branch workflow. This is ordinary branch-owned implementation bookkeeping, not native evidence or an authority grant.

## What changes during execution

| Record | Required contents |
|---|---|
| execution/progress.json | Actual branch/head; task IDs and implemented/tested/qualified status; evidence references; current scoped blockers; next concrete actions. Missing entries inherit PLANNED from the intake. |
| execution/CHECKPOINT.md | Current Git state, completed and remaining tasks, actual tests/results, unknown outcomes, and the next action. |
| Decision entries | B’s actual progress/evidence choice and the narrower HIGH/pre-tag decisions, with source/date and affected tasks. Retain the original unresolved intake as history. |
| Added work | New finding/task/scenario/transition IDs, exact source observations, ownership, dependencies, authorization scope and acceptance evidence. Never discard a newly discovered regression to make the original 82-task count look complete. |
| Evidence records | Actual source/package/platform/run identities and observations using contracts/acceptance-record-template.json; preserve failures and substitutions. |
| Delivery state | Separate integration qualification, final exact-source readiness, and actual public settlement. A local status field does not certify itself. |

On resume, inspect actual Git state and the latest execution records before acting on older checkpoint claims. Read the intake for fixed intent and source evidence; use actual later decisions and implementation results for current status. Keep one authoritative progress record and link to detailed evidence instead of copying the same verdict into many files.

The packet validator checks the frozen intake and permits new files under execution/. It does not validate their product claims or authorize release. The implemented Q-02 readiness verifier must bind and verify the actual completed task population, including added required work, through trusted source/build/test evidence. New desired transition rows belong in execution records and the actual source-owned contract; never overwrite the original 1,748 rows to erase a discrepancy.
