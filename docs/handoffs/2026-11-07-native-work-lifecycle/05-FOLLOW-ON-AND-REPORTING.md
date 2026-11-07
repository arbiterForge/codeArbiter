# 05. Follow-on queue and reporting contract

## Not part of the primary implementation PR

The following should be pursued only after the native work/lifecycle closure, using their own owning repositories and exact compatibility evidence:

1. **Academy normal-path verification.** At Preview 0.33, F04/P01/P05/U01 checks include workarounds for legacy board gate shapes. Once the producer fixes #1089, adjust lessons, action cards and verifier together to teach the ordinary workflow, with a new exact producer compatibility pin.
2. **Academy U04 HTML-default path.** The lesson explicitly requests Markdown because its Check reads the old Markdown context/plans. Build the HTML-native validator and update the lesson; do not remove the old form without migration/compatibility work.
3. **Project overview as an outcome-oriented briefing.** `work_view.go` is ahead of `project_view.go`: work pages already lead with situation/change/obstacle/next action, while project page is mainly an inventory. Aggregate evidenced outcomes *after* canonical work/plan records can be trusted.
4. **IDE product-specific derivative correction.** Fix current source's stale `SUaDtL/codeArbiter` link and prompt-only relationship language without broadening guarantees or rewriting historical ADRs.
5. **Pi publisher recovery.** If `ca-pi-v0.27.4` is still draft, treat the transparency log/publisher failure as a separate release operations issue, not a work-system PR.
6. **H-20 security/routed recovery (#1088).** A separate bounded security issue; do not exploit or casually suppress it.
7. **Stale installed Claude Auto-mode canary from #1091.** Capture a fresh exact-package model-host qualification where available; no replayed historical success claim.

## Report back to the owner

The implementation PR description and final message should use this structure:

### Confirmed findings
- Frozen repo head and exact source paths.
- Defects reproduced, with baseline command, exit and expected/observed result.

### Material contradictions
- Every remaining mismatch between source, plan, generated host, Academy and released channel.
- Keep unknown/unverified separate from broken.

### Code / canon / claim delta
- Files changed in source, schema, generated adapters, tests and docs.
- No new organization canon or legal/security marketing claim without explicit source evidence.
- Explicitly state if the native schema or source-origin representation changed.

### Affected surfaces
- Claude, Codex, Pi source packages; legacy and native consumers; Academy compatibility needs.
- List any intentionally deferred site/IDE and distribution changes.

### User decisions required
- Only decisions consequential to intended product outcome, security boundary, incompatible migration or publication.
- Do not ask routine approval questions simply to keep writing already-authorized code/tests.

### Verification
- Tests run and actual exit, exact head, environment.
- Baseline failures, current passing regressions, negative/adversarial cases.
- Package/installed-host canaries and missing evidence, if any.
- Migration row accounting and historical hash preservation.

### Rollback
- Code branch/commit revert plan.
- Persisted canonical files and transaction-specific forward recovery.
- Explicitly note that remote effects are not undone by Git revert.

### Recommended next action
- Provide PR URL, commit, CI results, issues expected to close, risks still open.
- Do not report main, release, hosted site or marketplace changed unless actually verified.

## Acceptance rubric

The work is acceptable when:
- #1084 and #1087 are resolved as **one compatible Python/Go adoption contract**;
- all source rows are accounted for in a disposable migration, preserving provenance, IDs, text and archive history;
- #1089's legitimate selected-item mutations pass, while deliberate scope-creep mutants remain refused;
- the current adapter and engine generated derivatives are coherent;
- a realistic existing-project journey completes without artifact-origin permission codes or spurious second approvals;
- progress/check/delivery state remains separately truthful;
- current-head CI and source verification are recorded; missing installed-host qualification is named, not claimed.

If one of those cannot be satisfied without new requirements or unsafe migration, keep the PR draft and report the exact blocker. Do not substitute more abstraction, a new permission workflow or documentation-only green checks for the missing behavior.
