# Blocker 3 task and security review

### Spec Compliance

- ❌ Issues found. The normal enabled/failure/retry path is substantially implemented: the bootstrap handler is installed before parent lifecycle registration (`plugins/ca-pi/tools/src/extension.ts:247-248`), enabled activation enters bootstrap before bridge/enforcement work and marks ready only after the production installer returns (`plugins/ca-pi/tools/src/extension.ts:80-97`), and the bootstrap handler blocks every non-`READ`/unknown/missing tool with a structured `/ca-doctor` refusal (`plugins/ca-pi/tools/src/tool-guard.ts:126-150`). However, two binding requirements are not met:
  - Dormant state is not reliably ungoverned after a partial enabled installation. `deactivate()` resets only `bootstrapActive` and `ready`; it leaves the final unknown-tool handler, result handler, registered wrappers, and wrapper definitions installed (`plugins/ca-pi/tools/src/tool-guard.ts:117-123`, `plugins/ca-pi/tools/src/tool-guard.ts:149-167`). A later dormant `session_start` calls only that incomplete deactivation (`plugins/ca-pi/tools/src/extension.ts:80-83`). If a prior install failed after any final components registered, dormant calls remain governed and can use wrappers bound to the earlier enabled cwd, contrary to the explicit dormant requirement (`.codearbiter/reports/2026-07-14-pi-support-handoff/blocker-3-brief.md:31-34`).
  - The new bootstrap failure text directly interpolates untrusted `event.toolName` (`plugins/ca-pi/tools/src/tool-guard.ts:129-134`). A secret-shaped or control-bearing opaque tool name is therefore copied verbatim into Pi's structured refusal/RPC failure text, violating the absolute no-raw-secret-in-RPC-or-failure-text constraint (`.codearbiter/reports/2026-07-14-pi-support-handoff/blocker-3-brief.md:47`, `plugins/ca/agents/security-reviewer.md:55-57`).
- ⚠️ Cannot fully verify “nothing extra” from the supplied baseline/current package because it contains a literal truncation marker in the middle of the Python diff (`.codearbiter/reports/2026-07-14-pi-support-handoff/blocker-3-review-package.md:569`). The reviewer-permitted direct read of the cut-off current-file region showed syntactically normal scanner/CI-contract code at `.github/scripts/test_pi_package.py:523-596`, but the omitted baseline comparison cannot be reconstructed from the package.
- ⚠️ The deterministic parent bundle's content-to-source equivalence cannot be verified from the package: it supplies only old/current hashes (`.codearbiter/reports/2026-07-14-pi-support-handoff/blocker-3-review-package.md:8-16`), not the generated bundle diff. The reported build/check results remain implementer claims for this review.

### Strengths

- Registration ordering is correct for the targeted real-Pi failure: the bootstrap handler is registered during extension initialization before `installParent`, while final enforcement is deferred to enabled `session_start` (`plugins/ca-pi/tools/src/extension.ts:247-248`, `plugins/ca-pi/tools/src/extension.ts:290-308`).
- A thrown installation attempt does not call `markReady`; retry re-enters bootstrap before attempting installation again (`plugins/ca-pi/tools/src/extension.ts:85-97`). The activation test verifies `begin`, failed-not-ready, then `begin`/`ready` on retry (`plugins/ca-pi/tools/test/activation.test.ts:340-367`).
- The real RPC fixture uses installed Pi, an isolated home, a one-shot `Map.prototype.set` registration fault, a real native `write` dispatch, an `extension_error`, `agent_settled`, an errored `tool_execution_end`, and a mutation sentinel observed before temporary-root cleanup (`.github/scripts/test_pi_package.py:182-198`, `.github/scripts/test_pi_package.py:1002-1048`). This is materially stronger than a fake-host-only test.
- Existing final-argument snapshots, final-source checking, and unknown-tool blocking remain present in the reviewed source (`plugins/ca-pi/tools/src/tool-guard.ts:35-92`, `plugins/ca-pi/tools/src/tool-guard.ts:187-206`).
- Focused read-only check: installed Pi `0.80.6`'s real `emitToolCall` walks handlers in order and immediately returns the first result whose `block` is true, so a later final handler cannot erase the earlier bootstrap block (`C:/Users/brenn/AppData/Roaming/npm/node_modules/@earendil-works/pi-coding-agent/dist/core/extensions/runner.js:648-665`). The short-circuit assumption is proven for the real version exercised by the fault regression; it remains unproven here for `0.80.5`.

### Issues

#### Critical (Must Fix)

None.

#### Important (Should Fix)

1. `plugins/ca-pi/tools/src/tool-guard.ts:117-123`, `plugins/ca-pi/tools/src/tool-guard.ts:149-167`, `plugins/ca-pi/tools/src/extension.ts:80-83` — deactivation does not deactivate final enforcement installed before a partial failure. Why it matters: the requested state machine includes dormant/enabled/failure/retry/shutdown, and “dormant” must mean silent and ungoverned, not merely “bootstrap guard inactive.” A partial failure followed by dormant activation leaves final handlers/wrappers live, potentially bound to stale cwd. Fix by making final handlers and wrappers state-aware/delegating while inactive, or by proving and enforcing a fresh installer/runtime boundary before any dormant activation; add a partial-install → deactivate/dormant regression that checks both handler results and actual executor/bridge inactivity.

2. `plugins/ca-pi/tools/src/tool-guard.ts:129-134` — the bootstrap refusal echoes the opaque tool name without `safeDiagnostic` or equivalent redaction. Why it matters: Pi serializes this reason into failed tool/RPC output, so attacker/model-controlled text can violate the explicit secret-handling boundary. Fix by sanitizing the complete reason (or omit the raw name) and add a bootstrap test using a secret-shaped/control-bearing tool name that proves the raw value never appears.

#### Minor (Nice to Have)

1. `.github/scripts/test_pi_package.py:182-198`, `.github/scripts/test_pi_package.py:1023-1048` — `faultArmed` becomes false only inside the injected throw, but the test never observes that state or the unique `CA_PI_TEST_ENFORCEMENT_REGISTRATION_FAILURE` cause. The outer install error plus refusal makes the intended path very likely, but an unrelated install failure could create a false green. Expose a test-only consumed-fault marker/event and assert it alongside the existing lifecycle/refusal/sentinel checks.

2. `plugins/ca-pi/tools/test/tool-guard.test.ts:109-123` — the deactivation test exercises only the bootstrap handler on a fresh installer; it does not install any final guard/result/wrapper component before deactivation. Extend it with each partial stage so lifecycle coverage matches the production state held by `EnforcementInstaller`.

### Assessment

**Task quality:** Needs fixes

**Reasoning:** The real-Pi catch-and-continue hole is addressed for the targeted first final-handler registration failure, and Pi 0.80.6 confirms handler blocks short-circuit. The task cannot be approved while partial final state survives a dormant transition and opaque tool names can enter refusal/RPC text unsanitized.

## Security Review — 2026-07-15

### CRITICAL findings (0)

None.

### HIGH findings (1)

**Severity:** HIGH
**File:** `plugins/ca-pi/tools/src/tool-guard.ts:129-134`
**Description:** The new bootstrap security boundary copies an untrusted opaque tool name verbatim into a structured refusal that Pi exposes as failed tool/RPC output. Secret-shaped or control-bearing input is not redacted.
**Control:** Blocker 3 no-raw-secret constraint (`blocker-3-brief.md:47`); security reviewer secret rule (`plugins/ca/agents/security-reviewer.md:55-57`).
**Remediation:** Pass the complete refusal through `safeDiagnostic` or omit the raw name, and add a regression proving a secret-shaped opaque name is absent from serialized failure output.

### MEDIUM findings (1)

**Severity:** MEDIUM
**File:** `plugins/ca-pi/tools/src/tool-guard.ts:117-123`, `plugins/ca-pi/tools/src/tool-guard.ts:149-167`
**Description:** The lifecycle deactivation transition disables only bootstrap readiness; partially installed final handlers/wrappers remain live. If the same installer reaches a dormant activation, governance can cross the declared dormant boundary and wrappers can retain the previous enabled cwd.
**Control:** Dormant repository boundary (`blocker-3-brief.md:31-34`); Pi adapter declared boundary (`.codearbiter/security-controls.md:278-299`).
**Remediation:** Make all final enforcement state honor inactive mode or enforce a fresh runtime/installer boundary, then cover partial-install → dormant behavior with a regression.

### LOW findings (1)

**Severity:** LOW
**File:** `.github/scripts/test_pi_package.py:182-198`, `.github/scripts/test_pi_package.py:1023-1048`
**Description:** The real-Pi regression does not independently prove its one-shot registration fault fired; it proves only the outer installation error and fail-closed result.
**Control:** Security-path test authenticity and false-green resistance.
**Remediation:** Emit and assert a test-only consumed-fault marker without introducing a production switch.

### Gate status

BLOCK (0 CRITICAL, 1 HIGH must resolve before merge)
