# reliability — lens mandate

Executed by `tribunal-lens-reviewer` under the `reliability` assignment.

## Purpose / failure family
Find lost failures, corrupt or orphan state, unsafe concurrency and incomplete
resource lifecycles by tracing ownership and recovery semantics.

## Applicability
The assigned code performs fallible work, owns mutable state/resources, or
coordinates asynchronous, concurrent or restartable operations.

## Skip conditions
No relevant state transition, fallible boundary or lifecycle. Syntax alone does
not make a synchronous or pure helper a reliability risk.

## Scope emphasis
Follow operations from initiation through success, failure, cancellation,
deadline and restart, including direct callers and the resource/state owner.

## Required reading
- Finding record (`<plugin-root>/routines/tribunal/references/finding-record.md`) and review risk (`<plugin-root>/routines/tribunal/references/review-risk.md`).
- `<project-root>/.codearbiter/tech-stack.md` — async/concurrency model and
  persistence primitives; relevant error, lifecycle and recovery contracts.

## Deterministic probes
Enumerate state writers, acquisitions/releases, cancellation/deadline paths and
retry boundaries. Inspect caller and handler chains and existing failure tests;
counts of awaits or catches do not establish error ownership.

## Review questions
- Which boundary owns each failure, and does propagation or translation preserve
  its meaning for the caller? Can a swallowed failure masquerade as success?
- Are retries bounded and idempotent, with coherent timeout/cancellation outcomes?
- Can concurrent read-modify-write, reordering or duplicate delivery lose state?
- Are atomicity, partial failure and fail-open/fail-closed choices consistent with
  the actual contract? Can recovery or restart strand half-written state?
- Does the lifecycle owner release resources on every relevant terminal path?

## False-positive guards / non-findings
Intentional propagation to an owning boundary is valid; no local catch is required
at every await. A documented best-effort operation may intentionally fail silently.
Do not demand local cleanup when a parent owns the lifecycle, or locking when an
established transaction/serialization model already provides the invariant.

## Evidence requirements
Show a concrete failure or interleaving, the violated invariant and its observable
effect. Absence claims name the search universe and ownership trace through
callers, central handlers, transaction owners and cleanup/recovery paths.
Distinguish a plausible schedule from a reproduced race.

## Exposure metric
Count of operation/state lifecycles traced across their owning boundary,
including which terminal paths were inspected.

## Escalation / cross-lens handoff
Send exploitability to appsec, diagnosability to observability and inadequate
fault detection to coverage. Preserve a shared root cause when several lenses
observe the same lost error or state transition.

## Out of scope
Local-catch style, speculative speed improvements and unrelated authorization
claims without a runtime ownership defect.
