# Pi support Batch 2 cumulative checkpoint brief

Date: 2026-07-15
Branch: `feat/pi-support`

## Scope

Review the complete cumulative implementation for Tasks 3-5 plus all seven accepted remediation blocks. The checkpoint is not a collection of prior approvals: reviewers must inspect the current combined source, generated artifacts, tests, specifications, plans, decisions, security controls, and durable reports for cross-block regressions or contradictory claims.

## Required cumulative properties

1. No Python discovery, bridge execution, or project-cwd interpreter trust occurs before enabled activation.
2. TypeScript and Python use the same canonical activation contract, including Unicode case behavior.
3. Bootstrap is fail closed for potentially mutating tools; dormant and shutdown states are genuinely inactive; partial installs and retries cannot bypass enforcement.
4. Only exact Pi `0.80.5` and `0.80.6` runtime identities are admitted before module evaluation/API access; package/runtime provenance and canaries are authentic.
5. Pi tool names and payloads normalize to the shared hook contract; native READ execution remains native while bounded/redacted governed context becomes model-visible once per authoritative session.
6. Doctor reports only evidence they actually prove: wrapper self-test is distinct from unsupported active-dispatch live-fire, PI-AC-28/Task 5 remain blocked, and public/generated surfaces are truthful.
7. Model-visible doctor output passes the shared secret/control redactor and an explicit bound at the final sink.
8. Enforcement uses opaque lifecycle generations across resolved, rejected, and cancelled bridge work: stale mutators do not execute; stale reads use current execution context without old decoration; stale result effects are suppressed; same-generation faults remain visible.
9. Generated Pi parent bytes, host descriptors, surface/core parity, package metadata, the child placeholder, and dependency lock are deterministic and internally consistent.
10. Existing user-owned dirty files and unrelated artifacts remain preserved; no staging, commit, push, publish, branch switch, stash, reset, or clean occurred.

## Known honest limitation

Supported Pi 0.80.5/0.80.6 public extension APIs expose no deterministic active-dispatch submission method. The doctor must remain `DEGRADED` for `active-dispatch`; PI-AC-28 and Task 5 stay BLOCKED pending Task 13 real-host/promotion evidence. This limitation is accepted for the Batch 2 checkpoint and must not be relabeled as passing live-fire evidence.

## Reviewer outputs

- Integration/task reviewer: `batch-2-combined-integration-review.md`
- Security reviewer: `batch-2-combined-security-review.md`

Both reviews must be fresh, read-only, evidence-backed, and based on the actual current workspace. Any finding requires a fix and same-reviewer rereview before this checkpoint can close.

## Stop condition

After controller verification and both cumulative reviews are clean, stop and request user acknowledgement. Do not start Tasks 6-9 in this turn.
