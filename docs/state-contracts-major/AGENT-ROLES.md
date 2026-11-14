# CLI agent roles, parallel work and resume protocol

## Integrator

Own P-00/P-01/P-02, task dependencies, shared contract decisions, the final merged candidate and the evidence ledger. Assign one writer per source owner. Integrate reviewed task branches into `major/state-contracts`, never main. Reconcile overlapping changes before accepting a task as done.

## Domain owners

| Owner | Primary responsibility | Shared-boundary coordination |
|---|---|---|
| Native | Operation/output contracts, binding limits, retirement/history, progress/evidence decision, fresh reviewer attempts. | Hook producers and validators; no closed-schema field added by another owner. |
| Hooks/workflows | Mode/delivery, diagnostics/settings ownership, dependent-only conflict policy, corrected handoffs, durable harvest. | Native request identities and state registration; site generator projections. |
| Pi | Scoped delegation, parent authorization, transport, audit/outcome settlement, lifecycle/UI, installed qualification. | Native/Python bridge guards, parent mode/session state, packaging identity. |
| Farm/sandbox | Manifest interoperability, receipt recovery, process containment, unknown observations, cache/resource scope. | Native decoder contracts, actual package artifacts and shared process contracts. |
| Release/site/tooling | Publication completion/recovery, exact source/artifact selection, evidence verdicts, site claims, diagnostic measurements. | Integration CI and program readiness; host-specific publication differences. |
| Reviewer/qualifier | Independently challenge semantics, execute cross-owner sequences, inspect failure and recovery evidence. | Do not approve solely from the implementing agent's narration or unchanged keyword tests. |

## Parallelism

After baseline and contract boundaries are recorded, native closed mismatches, hooks mode/settings fixes, Pi design/transport, farm/sandbox fixes and release completion can proceed in parallel. The progress/evidence migration waits only for D-PROGRESS. HIGH disposition waits only for D-HIGH. The pre-tag policy change waits only for D-GOV-PRETAG. Independent work continues.

Tasks that share a canonical schema, decoder or source file must coordinate through the single owner. A common definition is approved before consumers independently edit their copies. Generated files are rebuilt from canonical owners, not used as separate implementation roots.

## Review handoff per slice

Record task ID, original finding IDs, intended behavior changes, exact changed files, old/new event traces, tests executed with result population, source/artifact identity and rollback limits. Mark a task implemented-but-unqualified when that is the actual state. Never use DONE for a future test command, an unavailable host or a documentation-only promise of a runtime capability.

## Resumption

Read the current branch, local status, execution/progress.json and execution/CHECKPOINT.md. The intake task specifications remain historical; completed work and later decisions are recorded under execution/. Observe any potentially committed external/local effect before retry. Reuse an operation ID only for exact replay. Use a new linked attempt for changed inputs. Keep partial results and debt visible. Do not reset task branches, truncate logs, re-run authors or replace receipts to get a clean-looking restart.

## Stop scope

Block only the affected work and state why it depends on the unresolved condition. A shared canonical store with pending multi-file recovery is an affected resource; arbitrary unrelated source inspection or independent work can continue. Genuine user/host-wide stops remain global. No agent may reinterpret a denial, cancellation, untrusted session or failed containment as permission.
