# Post-build enforcement-registration fail-closed regression

Status: fixed and freshly verified on 2026-07-16.

## Symptom and reproduction

After rebuilding `plugins/ca-pi/extensions/codearbiter.js`, the real Pi RPC fault fixture reported the
expected `session_start` extension error but produced zero refused write events and allowed the
synthetic write to reach the native executor. The focused package case reproduced on three
consecutive pre-fix runs.

## Root cause

The enforcement-failure catch in `installParent` called
`enforcementReadiness.deactivate()`. `EnforcementInstaller.deactivate()` sets
`bootstrapActive = false`, so the preinstalled bootstrap `tool_call` handler stopped blocking after
Pi caught the `session_start` exception. The incomplete wrapper registration therefore fell through
to Pi's native write tool. The stale checked-in bundle had temporarily hidden this source regression.

The failed registration itself did not require a new guard: the bootstrap handler is installed at
extension load and `beginActivation`/`beginBootstrap` already place it in the active-unready,
fail-closed state. The catch was undoing that state.

## Minimal fix

Removed only the failure-path `deactivate()` call. A failed enabled activation now remains
bootstrap-active and unready, blocking potentially mutating tools until `session_shutdown` or the
next `session_start` performs the existing explicit deactivate/new-generation transition. Dispatch,
compaction, and farm leases remain unavailable because the failed lifecycle clears its ready and
active leases.

Updated the activation unit expectation to require this fail-closed failure state. The real RPC
package test was not weakened.

## Fresh evidence

- Focused real RPC failure case: passed three consecutive post-fix runs.
- Activation and tool-guard suite: 55 passed.
- Full Python package contract: 23 passed.
- Pi security/final-arguments/guard/activation/package slice: 84 passed.
- Static security harness: all eight `PI-SEC-*` checks passed.
- Full Pi tools suite: 253 passed, 1 platform skip.
- Typecheck, rebuild, and focused diff check exited 0.
