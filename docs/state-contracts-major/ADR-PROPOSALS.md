# ADR successor and addendum suggestions

## Use the normal authority workflow

These are proposed decisions for the implementation branch, not accepted ADRs. Allocate the next valid IDs from the repository at execution time. Preserve accepted historical bodies and immutable approvals. Use the supported supersession/status/link mechanism and new current decisions. A decision's acceptance is not implementation or qualification evidence.

| Proposed decision | Existing records to reconcile | Required content | Acceptance evidence |
|---|---|---|---|
| Explicit owner transition/effect contracts | 0004, 0012, 0037, 0043 | Retain file/CAS/journal architecture; classify state axes; generate repeated contracts; distinguish old architecture claims from current implementation; preserve platform-specific integrity. | Writer/reader/capability closure, meaningful conformance and exact backward-read tests. |
| Dependent-only conflict and corrected submission | 0025/0043 and owning conflict/debug/reviewer instructions | Record B's approved stop scope and resubmission; keep true global host/user stops and shared-resource integrity dependencies; preserve immutable rejected attempts and current authority. | Dependent/independent work traces and fresh attempt versus exact replay/actual denial tests. |
| Progress and evidence semantics | 0043 and native task lifecycle | Populate only after SMARTS discussion with B. Record alternatives, evidence applicability, ordinary/strict review semantics, migration and downgrade boundary. | Exact old/new fixtures and tests selected by the accepted option. |
| Persona selection/delivery settlement | 0030 | Current selection epoch/content/generation must drive delivery; repeated unchanged events deduplicate; partially applied mode transitions expose raw/effective/debt state. | A→B→A, compaction/session, audit-write failure and retry. |
| Scoped parent delegation for Pi authors | 0036 plus Pi security/runtime owners | Supported exact tool/action scope, real parent trust/mode/authority, grant identity/expiry/revocation, effect channel/audit, uncertain outcome recovery and explicit threat/containment limits. | Actual supported-host write/edit/verification plus forged/wrong-scope/revoked/stale and interruption cases. |
| Durable nonblocking terminal harvest | 0008, 0036, 0043 plus harvest/storage owners | Registered obligations, exact identity, idempotent target reconciliation, bounded scan, failure/retention/cleanup, no authority expansion or universal progress gate. | Crash/restart/duplicate/unavailable/retention and ordinary-work continuity cases. |
| Publication completion and major-program readiness | 0040 and 0044 | One per-target completion predicate; receipt-only recovery; exact source/build/digest selection; explicit pre-tag enforcement policy; major-release-specific readiness barrier before first public effect. | Failure at every publication phase, exact-artifact identity and valid/invalid readiness evidence. |
| Compatibility retirement policy | Current compatibility owner and route registry | One approved retirement rule; observer evidence separate from removal permission; preserve existing aliases by default. | Declaration/tag/draft/published/unavailable/mismatch and separately authorized removal tests. |

Preserve ADR0045's legitimate timing distinction: manual Project sync-now is not an issue after-merge event. Preserve ADR0044's Pi provenance/identity gate. Durable recovery does not authorize broader deletion; ADR0036's later governed cleanup requirements remain applicable to any actual relaxation.

## Draft decision text: shared contract architecture

Each existing subsystem owns an explicit versioned transition/effect contract for the state and side effects it controls. Shared outcomes distinguish invalid input, refusal, unavailable capability/observation, partial application, committed effect, observed settlement and unknown outcome. Progress, evidence applicability, authority, delivery, containment and identity/generation remain independently represented. Derivative capabilities, schemas/limits, diagnostics and reference facts are generated from that owner where duplication currently causes drift.

Ordinary assistive progress does not require a second permission exchange or optional evidence prerequisite. Existing genuine authority, integrity and containment barriers remain. Extraction preserves behavior; each intentional behavior change is named and tested. State migrations preserve identity, historical evidence and bounded rollback/forward-recovery semantics. Simple local parsers and UI state stay local unless a cross-owner contract justifies extraction.

## Draft decision text: release completion

Publication completeness is an observed predicate over the exact target/source/artifact and all required effects/receipts. A public target missing a final receipt is incomplete and admits receipt-only recovery. Unknown outcome triggers readback before retry. Published tags/versions and conflicting bytes remain immutable.

For this major program, complete implementation and required installed-artifact qualification precede the first public release/channel effect. Readiness binds exact source, build/run/artifact identities, target versions, scenario population and accepted decisions. It is verified from a declared trusted producer and cannot be granted by an editable self-assertion. This program-readiness rule does not create an atomic cross-target publication transaction or an ordinary runtime permission layer.

## Decisions still needing B/maintainer disposition

- D-PROGRESS: the actual progress/evidence model and migration, using the complete SMARTS worksheet.
- D-HIGH: HIGH maintenance finding severity versus blocking disposition, independent from permission to resubmit.
- D-GOV-PRETAG: required versus advisory enforcement for declared pre-tag checks. Keep current required candidate behavior until the replacement is accepted.

Sources: [.codearbiter/decisions at the audit commit](https://github.com/arbiterForge/codeArbiter/tree/fd7eb34b2da439551443d09526ab48fd1d1bb9bf/.codearbiter/decisions), [assistive state decision](https://github.com/arbiterForge/codeArbiter/blob/fd7eb34b2da439551443d09526ab48fd1d1bb9bf/.codearbiter/decisions/0043-assistive-state-engine.md), [release decision](https://github.com/arbiterForge/codeArbiter/blob/fd7eb34b2da439551443d09526ab48fd1d1bb9bf/.codearbiter/decisions/0040-independent-per-target-release-with-consumer-safety-gates.md). Owner-specific detailed amendment suggestions remain in the native, Pi and recovery designs.
