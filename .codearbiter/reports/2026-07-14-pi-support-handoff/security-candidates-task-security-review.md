# Pi Batch 2 security-candidate remediation review

Date: 2026-07-15
Scope: narrow static review of the two remediated security candidates
Verification performed: source and focused-test inspection only; no suites run

## Spec compliance

**NO.** Candidate A satisfies the approved sink-level redaction and bounding contract. Candidate B
handles bridge responses that resolve after a lifecycle-generation change, but it does not handle
the equivalent rejection or cancellation completion path. The lifecycle-generation requirement is
therefore incomplete.

## Task verdict

**CHANGES REQUIRED**

## Candidate A - accepted

`renderPiDoctorReportBlock()` applies shared `safeDiagnostic()` normalization with the explicit
16,000-character bound before JSON encoding and fixed-boundary rendering
(`plugins/ca-pi/tools/src/extension.ts:161-167`). The adversarial sink test injects a shared-corpus
secret, owned-boundary markup, control characters, and oversized content, then proves redaction,
normalization, bounding, and exactly one report boundary
(`plugins/ca-pi/tools/test/activation.test.ts:127-149`). This closes Candidate A as specified.

## Finding

**Severity:** MEDIUM
**File:** `plugins/ca-pi/tools/src/tool-guard.ts:127` and `plugins/ca-pi/tools/src/tool-guard.ts:325`
**Description:** Both lifecycle-sensitive paths await `bridge.call()` without a rejection handler.
In `wrappedDefinition()`, the generation mismatch check at line 135 is reached only when the bridge
promise resolves; in `bridgeToolResults()`, the same is true of the check at line 333. If the old
bridge request rejects or is cancelled after `deactivate()` or a deactivate-to-reactivate transition,
the rejection bypasses the generation policy. A stale mutator remains fail-closed in the narrow
sense that native execution does not begin, but it escapes as the bridge rejection instead of the
fixed lifecycle diagnostic; a stale READ does not perform the specified current-context native
delegation; and a stale result handler propagates an old-lifecycle failure into the dormant or new
lifecycle instead of suppressing it. The focused `DelayedBridge` fixture always resolves
(`plugins/ca-pi/tools/test/tool-guard.test.ts:27-40`), so the delayed-resolution tests do not cover
this completion path.
**Control:** `.codearbiter/security-controls.md`, Pi adapter and child-process security - lifecycle
enforcement must remain the final authority, and cancellation/timeout behavior must be bounded and
must not spill work or diagnostics across the adapter boundary.
**Remediation:** Catch the bridge rejection at both awaits and compare the captured generation with
the live generation before deciding how to complete. On a mismatch, use the fixed safe lifecycle
failure for mutators, delegate READ once through the current execution-context native definition,
and return `undefined` from the result handler without notification or patch. Re-throw or otherwise
preserve the existing bridge/cancellation behavior only when the captured generation is still
active. Do not expose the stale bridge rejection text in the mismatch path.
**Required tests:** Add a deferred bridge that can reject after release, then prove (1) an old WRITE
rejection after deactivate-to-reactivate produces the fixed lifecycle failure and never executes
native code, (2) an old READ rejection after deactivate delegates once from the current context and
does not expose stale error text or decoration, (3) an old WRITE/EDIT result rejection after
deactivate and after deactivate-to-reactivate resolves to no patch and emits no notification, and
(4) the new lifecycle remains operational. Include an abort/cancellation-shaped rejection in at
least one transition case.

## Security gate

**PASS (0 CRITICAL, 0 HIGH)** under the security-reviewer severity gate, with **1 MEDIUM**
security-path coverage/control finding. The task remains **CHANGES REQUIRED** and must not enter the
combined Batch 2 checkpoint until the finding is remediated and re-reviewed.

---

## Rereview - 2026-07-15

This section supersedes the initial task and gate verdicts above for the current implementation.

### Final spec compliance

**YES.** Candidate A remains accepted at the final model-visible doctor boundary. Candidate B now
applies the lifecycle-generation policy to both resolved and rejected/cancelled bridge completions.

The wrapper captures one opaque generation before the bridge call and compares object identity in
both the catch path (`plugins/ca-pi/tools/src/tool-guard.ts:137-143`) and resolved path (lines
144-149). A stale mutator receives the same fixed, secret-independent lifecycle failure and never
starts native execution. A stale READ delegates once through `executeNativeFromContext()`, which
selects the native definition from the execution-context cwd (lines 100-109), and applies no stale
bridge decoration. The result handler likewise suppresses both rejected and resolved stale effects
before notification or patching (lines 334-352). Same-generation errors are rethrown unchanged.

`beginBootstrap()` creates a fresh frozen object identity for every lifecycle and `deactivate()`
removes it (`plugins/ca-pi/tools/src/tool-guard.ts:238-253`), so a deactivate-to-reactivate sequence
cannot satisfy an old request's identity comparison; there is no boolean or scalar ABA path.

### Focused verification

- Rejecting/cancellation regressions cover old mutator non-execution and fixed diagnostics, stale
  READ current-cwd delegation with preserved signal and no raw rejection, stale WRITE/EDIT result
  suppression after deactivate and deactivate-to-reactivate, and new-lifecycle operation
  (`plugins/ca-pi/tools/test/tool-guard.test.ts:460-635`).
- Same-generation wrapper and result-handler rejection object identity is preserved
  (`plugins/ca-pi/tools/test/tool-guard.test.ts:637-680`).
- Focused tool-guard suite: **34/34 passed**.
- TypeScript typecheck: **PASS**.

No broad suite was run during this narrow rereview.

### Final task verdict

**APPROVED**

### Final findings counts

- CRITICAL: 0
- HIGH: 0
- MEDIUM: 0
- LOW: 0

The prior MEDIUM finding is resolved. No new finding was identified in the rereview scope.

### Final security gate

**PASS (0 CRITICAL, 0 HIGH)**
