# Blocker 5 Task and Security Rereview

Date: 2026-07-15
Scope: bounded closure review of the two findings in `blocker-5-task-security-review.md`, plus regression impact in the current source, tests, real Pi RPC fixture, and generated bundle.

## Verdict

- Spec compliance: **YES**
- Task quality: **APPROVED**
- Security gate: **PASS**
- Findings: **0 CRITICAL / 0 HIGH / 0 MEDIUM / 0 LOW**

Both prior MEDIUM findings are closed. No new finding was identified in the bounded rereview.

## Prior Finding 1: Pi READ Deduplication Was Not Session-Scoped

**Status: CLOSED**

The production wrapper now derives the authoritative Pi session ID from the actual tool execution context. The contract exposes `sessionManager.getSessionId` at `plugins/ca-pi/tools/src/contracts.ts:27-42`; `nativeSessionId` calls that API, rejects non-strings, blank IDs, and IDs over 1024 characters, and handles getter failure at `plugins/ca-pi/tools/src/tool-guard.ts:62-71`. Only READ bridge requests receive the selected value as `sessionId` at `plugins/ca-pi/tools/src/tool-guard.ts:110-117`.

The fallback is activation-lifecycle-local rather than process-global. It is created inside the enforcement installer at `plugins/ca-pi/tools/src/tool-guard.ts:181-188`, rotated by `beginBootstrap` at `plugins/ca-pi/tools/src/tool-guard.ts:204-208`, and cleared by `deactivate` at `plugins/ca-pi/tools/src/tool-guard.ts:214-218`. Installed built-ins close over that installer-local resolver at `plugins/ca-pi/tools/src/tool-guard.ts:232-243`. Pi `session_shutdown` invokes `deactivate` at `plugins/ca-pi/tools/src/extension.ts:148-156`. The session ID is sent only to the local bridge and is not included in notices, diagnostics, audit records, or test reports.

Unit coverage exercises the actual execution-context shape and exact native-ID forwarding at `plugins/ca-pi/tools/test/tool-guard.test.ts:420-477`. Missing, blank, oversized, and throwing getters use a stable bounded fallback within one lifecycle; deactivation makes enforcement dormant; the next bootstrap obtains a different fallback; and a valid native ID takes precedence at `plugins/ca-pi/tools/test/tool-guard.test.ts:479-528`.

The real Pi RPC fixture is non-tautological. Its provider issues three actual built-in READ calls and captures the corresponding next-turn `toolResult` messages at `.github/scripts/test_pi_package.py:287-389`; the harness leaves built-in tools enabled and reads Pi's real RPC state at `.github/scripts/test_pi_package.py:461-474` and `.github/scripts/test_pi_package.py:547-550`. The sequential-session proof uses the same governed repository for sessions A and B at `.github/scripts/test_pi_package.py:1211-1258`, validates real bounded session IDs without reporting their values at `.github/scripts/test_pi_package.py:1265-1274`, and confirms:

- first governed READ: native result plus exactly one governed context block per session (`.github/scripts/test_pi_package.py:1293-1302`);
- second READ in that same session: native result only (`.github/scripts/test_pi_package.py:1304-1308`);
- ungoverned READ: native result only (`.github/scripts/test_pi_package.py:1309-1313`);
- actual built-in start/end events and successful next-turn `toolResult` messages (`.github/scripts/test_pi_package.py:1276-1291`, `.github/scripts/test_pi_package.py:1315-1325`); and
- distinct Pi session IDs across the two runs without embedding either raw value in the report (`.github/scripts/test_pi_package.py:1327`).

This closes the cross-session sticky-deduplication defect while retaining once-per-session insertion.

## Prior Finding 2: Bridge Failures Could Expose Absolute Paths

**Status: CLOSED**

Model-visible locally generated bridge diagnostics are now restricted to the closed `BridgeFailureDetail` literal union at `plugins/ca-pi/tools/src/bridge.ts:11-20`. The shared failure constructors accept only that type at `plugins/ca-pi/tools/src/bridge.ts:110-120` and `plugins/ca-pi/tools/src/bridge.ts:144-152`, preventing arbitrary exception, path, or stderr text from being appended as failure detail.

All reviewed failure classes map to fixed text:

- path validation, serialization, overflow, and pre-abort at `plugins/ca-pi/tools/src/bridge.ts:154-168`;
- synchronous spawn failure at `plugins/ca-pi/tools/src/bridge.ts:170-188`;
- asynchronous child error, nonzero exit, timeout, cancellation, protocol overflow, and malformed output at `plugins/ca-pi/tools/src/bridge.ts:193-235`.

Stderr is byte-counted but never exposed. Audit records remain metadata-only—date, host, rule, audit class, correlation UUID, and byte counts—at `plugins/ca-pi/tools/src/bridge.ts:122-141`. The fixed failure output retains `/ca-doctor`; READ remains advisory while mutation failures remain fail-closed at `plugins/ca-pi/tools/src/bridge.ts:110-119`.

The tests assert against the actual patched READ result, not merely a raw bridge object. The wrapper helper is at `plugins/ca-pi/tools/test/bridge.test.ts:54-87`. Sentinel absolute paths are absent from patched READ output and audit records for path-validation failures at `plugins/ca-pi/tools/test/bridge.test.ts:167-214`, launch failures at `plugins/ca-pi/tools/test/bridge.test.ts:216-237`, and nonzero-process/stderr failures at `plugins/ca-pi/tools/test/bridge.test.ts:239-251`. Advisory READ behavior and fail-closed mutation behavior remain covered at `plugins/ca-pi/tools/test/bridge.test.ts:137-165` and `plugins/ca-pi/tools/test/bridge.test.ts:261-342`.

No equivalent model-visible `BridgeClient` branch accepting arbitrary diagnostic detail was found. This closes the raw local-path disclosure defect.

## Regression and Packaging Assessment

The previous review's authenticity, normalization, native-result preservation, no-post-result-injection, Pi 0.80.5 compatibility, and six-cell CI-matrix conclusions remain valid; the remediation did not invalidate them.

The generated bundle contains the fixed bridge implementation at `plugins/ca-pi/extensions/codearbiter.js:146-280` and the session-aware READ/lifecycle logic at `plugins/ca-pi/extensions/codearbiter.js:745-878`. Its current parent, child, and lockfile hashes match the second-pass addendum in `blocker-5-report.md`.

The implementer report records green focused tool-guard and bridge suites, typecheck, the upgraded real two-session RPC proof, the full Pi suite, and the package/RPC suite. Because this was a bounded read-only closure review and the evidence was internally consistent with the inspected source and tests, those suites were not rerun here.

## Final Assessment

The implementation now meets blocker 5's session-scoped READ-context requirement and prevents the reviewed classes of locally generated bridge diagnostics from exposing raw paths or stderr. Native READ results, `/ca-doctor` guidance, advisory READ handling, and fail-closed mutation handling are preserved. Blocker 5 is approved for this review gate.
