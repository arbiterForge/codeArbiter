# Shared outcome axes (P-02 program contract)

Status: program design record, adopted for implementation on `major/state-contracts` 2026-11-12. It is not a product wire format and grants no authority. Owners keep their existing schema and wire conventions. A versioned wire change needs its own task evidence. D-PROGRESS = B (later_decisions in progress.json) fixes the progress/evidence split below.

## Rule

Each result reports six independent axes. A value on one axis never implies a value on another:

| Axis | Question it answers | Must never be inferred from |
|---|---|---|
| **progress** | What work was recorded as done? | evidence, review, exit code |
| **evidence** | What does current observed evidence support for a named claim, against which bound inputs? | progress labels such as REVIEW, DONE or ACCEPTED, or a stale receipt |
| **authority** | Which actual host or user grant, denial or scope applies? | progress, evidence, a digest, a recovery record, or a corrected input |
| **delivery / observation** | Did an effect happen, and was it read back? | an absent response (that is *unknown*, not *not-happened*), or a process exit |
| **execution / containment** | What ran, within which declared action scope? | command admission, which is not an OS sandbox guarantee |
| **identity / generation** | Which exact source, operation, attempt, artifact or version is this? | names, versions or labels without a digest or SHA |

Every axis keeps `unknown` or `unavailable` as an honest value. An unknown is never collapsed into pass, fail, absent or done.

## Existing owner representations (verified at 33abc347)

| Axis | Native owner today | Source |
|---|---|---|
| progress | Plan task `state` enum `PENDING/REVIEW/BLOCKED` in the progress request schema; work item `state` `queued/active/complete/archived` | `core/artifacts/internal/operations/protocol.go:292,470` |
| evidence | Reported check `outcome` `pass/fail/skip/unknown`; criterion `outcome` `satisfied/unsatisfied/unknown` | `protocol.go:436,503` |
| identity / generation | `operation_id` plus canonical request hash; exact replay returns the recorded result; a rolled-back id refuses replay (`OPERATION_ROLLED_BACK`) | `core/artifacts/internal/operations/engine.go:130-145` |
| integrity barrier (not a semantic stop) | `RECOVERY_REQUIRED` while a prepared multi-file journal is pending; only operations on that canonical store depend on it | `engine.go:147-151` |

The other owners record their current representation when their first task starts. That record goes in the task's `implemented` entry, together with the compatibility trace below: Pi in PI-D01, hooks/workflows in HW-01, farm/sandbox in FARM-R01 and SBX-C01, and release in R-01. Native records its full trace in NT-01.

## Compatibility trace each owner captures before changing a contract

- Command grammar, aliases and exit codes.
- Host exceptions.
- Operation IDs and replay.
- File output classes.
- Authority provenance.
- Remote-effect timing.
- Unavailable states.

For each of these, capture old and new traces on unchanged inputs for these cases: refusal, partial commit, lost response with exact retry, replay and cancellation.

## Non-goals (from PROGRAM.md)

- No global statechart DSL.
- No cross-product state enum.
- No universal workflow gate or new permission layer.
- No new ordinary-work approval ceremony.
